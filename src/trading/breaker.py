"""Circuit breaker: reconciliation differences halt trading.

State lives in data/trading/breaker.json. Tripping is automatic on any
reconciliation discrepancy; resetting is manual only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class CircuitBreaker:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def state(self) -> dict:
        if not self._path.is_file():
            return {"tripped": False, "reason": "", "tripped_at": ""}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def is_tripped(self) -> bool:
        return bool(self.state().get("tripped"))

    def trip(self, reason: str) -> None:
        if self.is_tripped():
            return  # first reason wins; keep original evidence
        self._path.write_text(
            json.dumps(
                {
                    "tripped": True,
                    "reason": reason,
                    "tripped_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def reset(self) -> None:
        """Manual-only reset after human review."""
        self._path.write_text(
            json.dumps({"tripped": False, "reason": "", "tripped_at": ""}, indent=2) + "\n",
            encoding="utf-8",
        )
