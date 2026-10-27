"""Trading mode gate: research-only by default, live execution by explicit opt-in.

The system ships with execution capability off. Real trading is reachable
only when TRADING_MODE=live is set explicitly in the server environment.
"""

from __future__ import annotations

import os
from typing import Literal

TradingMode = Literal["research_only", "live"]

RESEARCH_ONLY: TradingMode = "research_only"
LIVE: TradingMode = "live"

_MODE_ENV_VAR = "TRADING_MODE"
_KNOWN_MODES = (RESEARCH_ONLY, LIVE)


def get_trading_mode() -> TradingMode:
    raw = os.environ.get(_MODE_ENV_VAR, "").strip().lower()
    if raw in _KNOWN_MODES:
        return raw  # type: ignore[return-value]
    if raw:
        raise ValueError(f"unsupported {_MODE_ENV_VAR}: {raw!r}; expected one of {', '.join(_KNOWN_MODES)}")
    return RESEARCH_ONLY


def execution_enabled() -> bool:
    """True only when real-order execution is explicitly enabled."""
    return get_trading_mode() == LIVE
