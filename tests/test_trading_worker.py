import json

from scripts.trading_worker import check_freshness, daily_heartbeat
from trading.breaker import CircuitBreaker


def test_freshness_alerts_on_stale_or_missing(tmp_path):
    now_ms = 1_800_000_000_000
    import datetime as dt

    wm_path = tmp_path / "market_data" / "watermarks.json"
    wm_path.parent.mkdir(parents=True, exist_ok=True)
    fresh = now_ms - 1000
    stale = now_ms - 7 * 3600 * 1000
    wm_path.write_text(json.dumps({"binance:BTCUSDT:1d": fresh, "binance:ETHUSDT:1d": stale}))

    sent = []
    # freeze "now" by monkeypatching datetime in the worker module
    from scripts import trading_worker

    class FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime.fromtimestamp(now_ms / 1000, tz=dt.timezone.utc)

    orig = trading_worker.datetime
    trading_worker.datetime = FixedDatetime
    try:
        stale_list = check_freshness(tmp_path, ["binance:BTCUSDT:1d", "binance:ETHUSDT:1d"], notify=sent.append)
    finally:
        trading_worker.datetime = orig
    assert stale_list == ["binance:ETHUSDT:1d"]
    assert "STALE" in sent[0]


def test_freshness_silent_when_all_fresh(tmp_path):
    now_ms = 1_800_000_000_000
    import datetime as dt

    wm_path = tmp_path / "market_data" / "watermarks.json"
    wm_path.parent.mkdir(parents=True, exist_ok=True)
    wm_path.write_text(json.dumps({"binance:BTCUSDT:1d": now_ms - 1000}))
    from scripts import trading_worker

    class FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime.fromtimestamp(now_ms / 1000, tz=dt.timezone.utc)

    orig = trading_worker.datetime
    trading_worker.datetime = FixedDatetime
    try:
        assert check_freshness(tmp_path, ["binance:BTCUSDT:1d"], notify=lambda t: None) == []
    finally:
        trading_worker.datetime = orig


def test_heartbeat_once_per_day(tmp_path):
    breaker = CircuitBreaker(tmp_path / "breaker.json")
    sent = []
    # use a ledger-free path: heartbeat opens the real ledger path under data/
    # so point state_dir at tmp and accept it reads the repo ledger (empty -> 0.0)
    assert daily_heartbeat(tmp_path, breaker, notify=sent.append) is True
    assert "heartbeat" in sent[0]
    assert daily_heartbeat(tmp_path, breaker, notify=sent.append) is False  # same UTC day
    assert len(sent) == 1


def test_heartbeat_reports_tripped_breaker(tmp_path):
    breaker = CircuitBreaker(tmp_path / "breaker.json")
    breaker.trip("reconciliation failed: 1 fill missing")
    sent = []
    daily_heartbeat(tmp_path, breaker, notify=sent.append)
    assert "TRIPPED" in sent[0] and "1 fill missing" in sent[0]
