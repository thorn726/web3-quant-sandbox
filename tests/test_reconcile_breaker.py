import json

import pytest

from trading import reconcile
from trading.breaker import CircuitBreaker
from trading.executor import OrderDenied, PaperExecutor
from trading.ledger import Ledger
from trading.risk import RiskLimits


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger.db")
    yield led
    led.close()


def _limits():
    return RiskLimits.from_env(
        {
            "TRADING_MAX_ORDER_QUOTE": "1000",
            "TRADING_MAX_POSITION_QUOTE": "10000",
            "TRADING_DAILY_LOSS_QUOTE": "500",
        }
    )


def test_breaker_persists_and_first_reason_wins(tmp_path):
    breaker = CircuitBreaker(tmp_path / "breaker.json")
    assert not breaker.is_tripped()
    breaker.trip("reconciliation failed")
    assert breaker.is_tripped()
    breaker.trip("second reason")
    assert breaker.state()["reason"] == "reconciliation failed"
    breaker.reset()
    assert not breaker.is_tripped()


def test_tripped_breaker_blocks_all_orders(tmp_path, ledger):
    breaker = CircuitBreaker(tmp_path / "breaker.json")
    ex = PaperExecutor(ledger, _limits(), breaker)
    breaker.trip("manual halt")
    with pytest.raises(OrderDenied, match="circuit breaker tripped"):
        ex.submit("BTCUSDT", "buy", 0.1, 100.0)


def test_reconcile_detects_missing_fills_and_trips(tmp_path, ledger):
    breaker = CircuitBreaker(tmp_path / "breaker.json")
    ex = PaperExecutor(ledger, _limits(), breaker)
    oid = ex.submit("BTCUSDT", "buy", 0.1, 100.0)

    sent = []

    def fake_alert(text):
        sent.append(text)
        return {"wecom": True, "email": True}

    exchange_trades = [{"id": "ex-1"}, {"id": "ex-2"}]  # ex-1 unknown locally
    report = reconcile.reconcile(ledger, breaker, exchange_trades, notify=fake_alert)
    assert not report.ok
    assert report.missing_locally == ["ex-1", "ex-2"]  # paper fill has no exchange id
    assert breaker.is_tripped()
    assert "CIRCUIT BREAK" in sent[0]
    assert ledger.current_state(oid) == "filled"  # safety state unaffected by alerts


def test_reconcile_detects_local_fill_missing_on_exchange(tmp_path, ledger):
    breaker = CircuitBreaker(tmp_path / "breaker.json")
    ex = PaperExecutor(ledger, _limits(), breaker)
    oid = ex.submit("BTCUSDT", "buy", 0.1, 100.0)
    # attach an exchange id to the local fill that the exchange does not know
    ledger._conn.execute("UPDATE fills SET exchange_trade_id='ghost' WHERE order_id=?", (oid,))
    ledger._conn.commit()
    report = reconcile.reconcile(ledger, breaker, [], notify=lambda t: {"wecom": False, "email": False})
    assert not report.ok
    assert report.missing_on_exchange == ["ghost"]
    assert breaker.is_tripped()  # trip happens even when both alert channels fail


def test_clean_reconciliation_keeps_breaker_open(tmp_path, ledger):
    breaker = CircuitBreaker(tmp_path / "breaker.json")
    ex = PaperExecutor(ledger, _limits(), breaker)
    oid = ex.submit("BTCUSDT", "buy", 0.1, 100.0)
    ledger._conn.execute("UPDATE fills SET exchange_trade_id='ex-1' WHERE order_id=?", (oid,))
    ledger._conn.commit()
    report = reconcile.reconcile(ledger, breaker, [{"id": "ex-1"}], notify=lambda t: {})
    assert report.ok and report.checked == 1
    assert not breaker.is_tripped()


def test_paper_fills_excluded_from_exchange_comparison(ledger, tmp_path):
    ex = PaperExecutor(ledger, _limits(), CircuitBreaker(tmp_path / "breaker.json"))
    ex.submit("BTCUSDT", "buy", 0.1, 100.0)  # no exchange id (paper)
    assert reconcile.local_exchange_ids(ledger) == set()


def test_breaker_state_file_shape(tmp_path):
    breaker = CircuitBreaker(tmp_path / "breaker.json")
    breaker.trip("x")
    state = json.loads((tmp_path / "breaker.json").read_text())
    assert set(state) == {"tripped", "reason", "tripped_at"}
