"""Daily P&L derived from ledger fills (facts only, no separate state)."""

from __future__ import annotations

from datetime import datetime, timezone

from trading.ledger import Ledger


def utc_day(traded_at: str) -> str:
    return traded_at[:10]


def daily_pnl(ledger: Ledger, day: str | None = None) -> float:
    """Realized quote P&L for a UTC day from alternating buy/sell fills."""
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = ledger._conn.execute(
        "SELECT side, price, quantity, traded_at FROM fills ORDER BY traded_at, seq"
    ).fetchall()
    pnl = 0.0
    open_cost = 0.0
    holding = False
    for side, price, quantity, traded_at in rows:
        if utc_day(traded_at) != day:
            continue
        notional = float(price) * float(quantity)
        if side == "buy" and not holding:
            open_cost = notional
            holding = True
        elif side == "sell" and holding:
            pnl += notional - open_cost
            holding = False
    return pnl
