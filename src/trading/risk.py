"""Hard risk boundaries enforced on the order path.

All limits are quote (USDT) amounts injected via environment config; the
strategy layer cannot override or bypass them. Missing limits block live
trading entirely — an unset limit is treated as zero tolerance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

LIMIT_ENV_VARS = {
    "max_order_quote": "TRADING_MAX_ORDER_QUOTE",
    "max_position_quote": "TRADING_MAX_POSITION_QUOTE",
    "daily_loss_quote": "TRADING_DAILY_LOSS_QUOTE",
}


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_order_quote: float
    max_position_quote: float
    daily_loss_quote: float

    @staticmethod
    def from_env(env: dict[str, str] | None = None) -> "RiskLimits":
        env = os.environ if env is None else env
        values: dict[str, float] = {}
        for field, var in LIMIT_ENV_VARS.items():
            raw = env.get(var, "").strip()
            if not raw:
                raise ValueError(f"risk limit unset: {var} must be configured before trading")
            value = float(raw)
            if value <= 0:
                raise ValueError(f"risk limit invalid: {var} must be > 0, got {value}")
            values[field] = value
        return RiskLimits(**values)


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reason: str


class RiskGate:
    def __init__(self, limits: RiskLimits):
        self._limits = limits

    def check_order(self, symbol: str, side: str, quantity: float, price: float, position_quote: float) -> RiskDecision:
        notional = quantity * price
        if notional > self._limits.max_order_quote:
            return RiskDecision(False, f"order notional {notional:.2f} exceeds max_order_quote {self._limits.max_order_quote:.2f}")
        projected = position_quote + notional if side == "buy" else position_quote
        if projected > self._limits.max_position_quote:
            return RiskDecision(False, f"projected position {projected:.2f} exceeds max_position_quote {self._limits.max_position_quote:.2f}")
        return RiskDecision(True, "ok")

    def check_daily_loss(self, daily_pnl_quote: float) -> RiskDecision:
        if daily_pnl_quote <= -self._limits.daily_loss_quote:
            return RiskDecision(False, f"daily loss {daily_pnl_quote:.2f} hit limit {self._limits.daily_loss_quote:.2f}; trading halted for the day")
        return RiskDecision(True, "ok")
