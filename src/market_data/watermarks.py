"""Data freshness watermarks: last confirmed-good timestamp per dataset."""

from __future__ import annotations

import json
from pathlib import Path


def _read(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get(path: Path, dataset: str) -> int | None:
    value = _read(path).get(dataset)
    return int(value) if value is not None else None


def advance(path: Path, dataset: str, open_time_ms: int) -> None:
    """Move the watermark forward; never backward."""
    data = _read(path)
    current = data.get(dataset)
    if current is not None and open_time_ms <= int(current):
        return
    data[dataset] = int(open_time_ms)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
