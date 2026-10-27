import pytest

from trading import daily_pnl
from trading.executor import OrderDenied, PaperExecutor, assert_live_ready
from trading.breaker import CircuitBreaker
from trading.ledger import Ledger
from trading.risk import RiskLimits


def _breaker(tmp_path):
    return CircuitBreaker(tmp_path / "breaker.json")


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger.db")
    yield led
    led.close()


def _limits(env=None):
    return RiskLimits.from_env(
        env
        or {
            "TRADING_MAX_ORDER_QUOTE": "100",
            "TRADING_MAX_POSITION_QUOTE": "500",
            "TRADING_DAILY_LOSS_QUOTE": "50",
        }
    )


def test_limits_require_all_three_configured():
    with pytest.raises(ValueError, match="TRADING_MAX_ORDER_QUOTE"):
        RiskLimits.from_env({"TRADING_MAX_POSITION_QUOTE": "500", "TRADING_DAILY_LOSS_QUOTE": "50"})
    with pytest.raises(ValueError, match="must be > 0"):
        RiskLimits.from_env(
            {
                "TRADING_MAX_ORDER_QUOTE": "0",
                "TRADING_MAX_POSITION_QUOTE": "500",
                "TRADING_DAILY_LOSS_QUOTE": "50",
            }
        )


def test_order_size_cap_enforced(ledger, tmp_path):
    ex = PaperExecutor(ledger, _limits(), _breaker(tmp_path))
    with pytest.raises(OrderDenied, match="max_order_quote"):
        ex.submit("BTCUSDT", "buy", 2.0, 100.0)  # 200 > 100


def test_position_cap_blocks_projection_above_limit(ledger, tmp_path):
    limits = RiskLimits.from_env(
        {
            "TRADING_MAX_ORDER_QUOTE": "100",
            "TRADING_MAX_POSITION_QUOTE": "450",
            "TRADING_DAILY_LOSS_QUOTE": "50",
        }
    )
    ex = PaperExecutor(ledger, limits, _breaker(tmp_path))
    for _ in range(4):
        ex.submit("BTCUSDT", "buy", 1.0, 100.0)  # position 400
    with pytest.raises(OrderDenied, match="max_position_quote"):
        ex.submit("BTCUSDT", "buy", 1.0, 100.0)  # projected 500 > 450


def test_daily_loss_halts_for_the_day(ledger, tmp_path):
    ex = PaperExecutor(ledger, _limits(), _breaker(tmp_path))
    ex.submit("BTCUSDT", "buy", 1.0, 100.0)
    ex.submit("BTCUSDT", "sell", 1.0, 45.0)  # realized -55, limit is -50
    assert daily_pnl.daily_pnl(ledger) == pytest.approx(-55.0)
    with pytest.raises(OrderDenied, match="daily loss"):
        ex.submit("ETHUSDT", "buy", 0.5, 100.0)
    with pytest.raises(OrderDenied, match="daily loss"):
        ex.submit("BTCUSDT", "sell", 0.5, 90.0)  # halt blocks everything new


def test_paper_happy_path_records_ledger_history(ledger, tmp_path):
    ex = PaperExecutor(ledger, _limits(), _breaker(tmp_path))
    oid = ex.submit("BTCUSDT", "buy", 1.0, 100.0)
    states = [r.state for r in ledger.order_history(oid)]
    assert states == ["pending", "submitted", "filled"]
    assert ledger.position("BTCUSDT") == pytest.approx(1.0)


def test_live_path_refuses_until_reconciliation_lands(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(SystemExit, match="issue 07"):
        assert_live_ready()


def test_daily_pnl_carries_cost_across_days(ledger, tmp_path):
    from datetime import datetime, timedelta, timezone

    ex = PaperExecutor(ledger, _limits(), _breaker(tmp_path))
    oid = ex.submit("BTCUSDT", "buy", 1.0, 100.0)
    # rewrite yesterday's timestamps directly: buy yesterday, sell today
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ledger._conn.execute("UPDATE fills SET traded_at=? WHERE order_id=?", (yesterday, oid))
    ledger._conn.commit()
    ex.submit("BTCUSDT", "sell", 1.0, 60.0)
    # sell today against yesterday's 100 cost: -40 today, not 0
    assert daily_pnl.daily_pnl(ledger) == pytest.approx(-40.0)


def test_sell_cannot_short_past_position_cap(ledger, tmp_path):
    limits = RiskLimits.from_env(
        {
            "TRADING_MAX_ORDER_QUOTE": "100",
            "TRADING_MAX_POSITION_QUOTE": "100",
            "TRADING_DAILY_LOSS_QUOTE": "50",
        }
    )
    ex = PaperExecutor(ledger, limits, _breaker(tmp_path))
    ex.submit("BTCUSDT", "sell", 1.0, 100.0)  # short to -100 == cap, allowed
    with pytest.raises(OrderDenied, match="max_position_quote"):
        ex.submit("BTCUSDT", "sell", 0.5, 100.0)  # projected -150 > cap


