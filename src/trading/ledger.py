"""Append-only execution ledger on SQLite (WAL).

Orders, fills and positions are immutable rows: corrections and state
changes append new rows and advance a head pointer, never UPDATE history.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

_ORDER_STATES = ("pending", "submitted", "filled", "partially_filled", "cancelled", "rejected")
_LEGAL_TRANSITIONS = {
    "pending": {"submitted", "cancelled", "rejected"},
    "submitted": {"filled", "partially_filled", "cancelled", "rejected"},
    "partially_filled": {"filled", "cancelled"},
}
_TERMINAL_STATES = {"filled", "cancelled", "rejected"}


class IllegalTransition(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class OrderRecord:
    order_id: str
    symbol: str
    side: str
    quantity: float
    state: str
    seq: int
    created_at: str
    updated_at: str


class Ledger:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                    quantity REAL NOT NULL CHECK (quantity > 0),
                    state TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
                CREATE TABLE IF NOT EXISTS fills (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    fill_id TEXT NOT NULL UNIQUE,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                    price REAL NOT NULL CHECK (price > 0),
                    quantity REAL NOT NULL CHECK (quantity > 0),
                    traded_at TEXT NOT NULL,
                    exchange_trade_id TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS positions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )

    # -- orders ------------------------------------------------------------

    def open_order(self, symbol: str, side: str, quantity: float) -> str:
        order_id = uuid.uuid4().hex
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO orders (order_id, symbol, side, quantity, state, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (order_id, symbol, side, float(quantity), now, now),
            )
        return order_id

    def _current_state(self, order_id: str) -> tuple[int, str]:
        row = self._conn.execute(
            "SELECT seq, state FROM orders WHERE order_id = ? ORDER BY seq DESC LIMIT 1",
            (order_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown order: {order_id}")
        return int(row[0]), row[1]

    def transition_order(self, order_id: str, new_state: str, reason: str = "") -> None:
        if new_state not in _ORDER_STATES:
            raise IllegalTransition(f"unknown state: {new_state}")
        with self._lock:
            seq, state = self._current_state(order_id)
            allowed = _LEGAL_TRANSITIONS.get(state, set())
            if new_state not in allowed:
                raise IllegalTransition(f"{state} -> {new_state} is not a legal transition")
            if state in _TERMINAL_STATES:
                raise IllegalTransition(f"{state} is terminal")
            with self._conn:
                self._conn.execute(
                    "INSERT INTO orders (order_id, symbol, side, quantity, state, reason, created_at, updated_at)"
                    " SELECT order_id, symbol, side, quantity, ?, ?, created_at, ?"
                    " FROM orders WHERE seq = ?",
                    (new_state, reason, _now(), seq),
                )

    def order_history(self, order_id: str) -> list[OrderRecord]:
        rows = self._conn.execute(
            "SELECT order_id, symbol, side, quantity, state, seq, created_at, updated_at"
            " FROM orders WHERE order_id = ? ORDER BY seq",
            (order_id,),
        ).fetchall()
        return [OrderRecord(*row) for row in rows]

    def current_state(self, order_id: str) -> str:
        _, state = self._current_state(order_id)
        return state

    # -- fills and positions ----------------------------------------------

    def record_fill(
        self,
        order_id: str,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        exchange_trade_id: str = "",
    ) -> str:
        fill_id = uuid.uuid4().hex
        with self._lock, self._conn:
            exists = self._conn.execute(
                "SELECT 1 FROM orders WHERE order_id = ? LIMIT 1", (order_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(f"unknown order: {order_id}")
            self._conn.execute(
                "INSERT INTO fills (fill_id, order_id, symbol, side, price, quantity, traded_at, exchange_trade_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (fill_id, order_id, symbol, side, float(price), float(quantity), _now(), exchange_trade_id),
            )
            row = self._conn.execute(
                "SELECT quantity FROM positions WHERE symbol = ? ORDER BY seq DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            current = float(row[0]) if row else 0.0
            signed = quantity if side == "buy" else -quantity
            self._conn.execute(
                "INSERT INTO positions (symbol, quantity, updated_at) VALUES (?, ?, ?)",
                (symbol, current + signed, _now()),
            )
        return fill_id

    def position(self, symbol: str) -> float:
        row = self._conn.execute(
            "SELECT quantity FROM positions WHERE symbol = ? ORDER BY seq DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        return float(row[0]) if row else 0.0

    def close(self) -> None:
        self._conn.close()
