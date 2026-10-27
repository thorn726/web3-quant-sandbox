import sqlite3

import pytest

from trading.ledger import IllegalTransition, Ledger


@pytest.fixture()
def ledger(tmp_path):
    led = Ledger(tmp_path / "ledger.db")
    yield led
    led.close()


def test_wal_mode_enabled(ledger, tmp_path):
    mode = ledger._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    assert (tmp_path / "ledger.db-wal").exists()


def test_order_lifecycle_legal_transitions(ledger):
    oid = ledger.open_order("BTCUSDT", "buy", 0.01)
    assert ledger.current_state(oid) == "pending"
    ledger.transition_order(oid, "submitted")
    ledger.transition_order(oid, "partially_filled")
    ledger.transition_order(oid, "filled")
    assert ledger.current_state(oid) == "filled"
    states = [rec.state for rec in ledger.order_history(oid)]
    assert states == ["pending", "submitted", "partially_filled", "filled"]


def test_illegal_transitions_rejected(ledger):
    oid = ledger.open_order("BTCUSDT", "buy", 0.01)
    with pytest.raises(IllegalTransition):
        ledger.transition_order(oid, "filled")  # pending -> filled is not legal
    ledger.transition_order(oid, "cancelled")
    with pytest.raises(IllegalTransition):
        ledger.transition_order(oid, "submitted")  # terminal state


def test_history_is_append_only_no_update(ledger):
    oid = ledger.open_order("ETHUSDT", "sell", 2.0)
    before = ledger._conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    ledger.transition_order(oid, "submitted")
    after = ledger._conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    assert after == before + 1
    with sqlite3.connect(ledger._path) as raw:
        first_state = raw.execute(
            "SELECT state FROM orders WHERE order_id = ? ORDER BY seq LIMIT 1", (oid,)
        ).fetchone()[0]
    assert first_state == "pending"  # original row untouched


def test_fill_updates_position_and_requires_known_order(ledger):
    oid = ledger.open_order("BTCUSDT", "buy", 0.5)
    ledger.record_fill(oid, "BTCUSDT", "buy", 34000.0, 0.3)
    ledger.record_fill(oid, "BTCUSDT", "buy", 34100.0, 0.2)
    assert ledger.position("BTCUSDT") == pytest.approx(0.5)
    sell = ledger.open_order("BTCUSDT", "sell", 0.1)
    ledger.record_fill(sell, "BTCUSDT", "sell", 34200.0, 0.1)
    assert ledger.position("BTCUSDT") == pytest.approx(0.4)
    with pytest.raises(KeyError):
        ledger.record_fill("no-such-order", "BTCUSDT", "buy", 1.0, 1.0)


def test_schema_version_recorded(ledger):
    version = ledger._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    assert version is not None
