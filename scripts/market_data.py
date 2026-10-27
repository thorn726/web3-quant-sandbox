"""Market data pipeline CLI.

Usage:
    python scripts/market_data.py backfill --symbol BTCUSDT --interval 1d --start 2023-10-01
    python scripts/market_data.py refresh

Env: MARKET_DATA_SYMBOLS (comma separated, default "BTCUSDT,ETHUSDT"),
MARKET_DATA_INTERVAL (default "1d").
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_data import refresh as md_refresh  # noqa: E402

DATA_ROOT = ROOT / "data" / "market_data"
LOG = logging.getLogger("market_data")


def _symbols(explicit: str | None) -> list[str]:
    raw = explicit or os.environ.get("MARKET_DATA_SYMBOLS", "BTCUSDT,ETHUSDT")
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def _interval(explicit: str | None) -> str:
    return (explicit or os.environ.get("MARKET_DATA_INTERVAL", "1d")).strip()


def _parse_start(value: str) -> int:
    dt = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["backfill", "refresh"])
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--interval", default=None)
    parser.add_argument("--start", default="2020-01-01", help="backfill start date (YYYY-MM-DD)")
    args = parser.parse_args()
    interval = _interval(args.interval)

    failed = False
    for symbol in _symbols(args.symbol):
        if args.command == "backfill":
            result = md_refresh.backfill_vision(DATA_ROOT, symbol, interval, _parse_start(args.start))
        else:
            result = md_refresh.refresh_incremental(DATA_ROOT, symbol, interval)
        LOG.info("result: %s ok=%s rows=%d error=%s", result.dataset, result.ok, result.rows, result.error)
        failed = failed or not result.ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
