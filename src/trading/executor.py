"""Paper-trading executor: signal -> risk gate -> ledger.

Paper mode records simulated fills in the ledger; no exchange API is
touched. Real-order execution additionally requires TRADING_MODE=live and
lands with the reconciliation/alerting milestone — until then the live
path refuses explicitly.
"""

from __future__ import annotations

import logging

from config.trading_mode import execution_enabled
from trading import daily_pnl
from trading.breaker import CircuitBreaker
from trading.ledger import Ledger
from trading.risk import RiskDecision, RiskGate, RiskLimits

logger = logging.getLogger(__name__)


class OrderDenied(Exception):
    pass


class PaperExecutor:
    def __init__(self, ledger: Ledger, limits: RiskLimits, breaker: "CircuitBreaker | None" = None):
        self._ledger = ledger
        self._gate = RiskGate(limits)
        self._limits = limits
        self._breaker = breaker

    def submit(self, symbol: str, side: str, quantity: float, price: float) -> str:
        if self._breaker is not None and self._breaker.is_tripped():
            state = self._breaker.state()
            raise OrderDenied(f"circuit breaker tripped: {state.get('reason', 'unknown')}")
        pnl = daily_pnl.daily_pnl(self._ledger)  # today's UTC realized P&L
        loss = self._gate.check_daily_loss(pnl)
        if not loss.allowed:
            raise OrderDenied(loss.reason)
        position_quote = max(self._ledger.position(symbol), 0.0) * price
        decision: RiskDecision = self._gate.check_order(symbol, side, quantity, price, position_quote)
        if not decision.allowed:
            raise OrderDenied(decision.reason)
        order_id = self._ledger.open_order(symbol, side, quantity)
        self._ledger.transition_order(order_id, "submitted")
        self._ledger.record_fill(order_id, symbol, side, price, quantity)
        self._ledger.transition_order(order_id, "filled")
        logger.info("paper fill: %s %s %s %.6f @ %.2f", order_id[:8], side, symbol, quantity, price)
        return order_id


def assert_live_ready() -> None:
    """Explicit gate for the future live path; refuses until 07 lands."""
    if execution_enabled():
        raise SystemExit(
            "live execution is not wired yet; reconciliation and circuit breaker "
            "(trading-data-platform issue 07) must land first"
        )
