"""Bronze storage: monthly Parquet partitions under data/market_data/bronze.

Layout: bronze/{source}/{symbol}/{interval}/{YYYY-MM}.parquet
Closed months are immutable; a re-download that differs becomes a new
version file (.v2, .v3, ...) — bronze is append-only by construction.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
]

# Binance Vision kline dump columns (12 fields, no header).
VISION_COLUMNS = KLINE_COLUMNS[:7] + ["ignore", "quote_volume", "trades", "ignore2", "ignore3"]


def partition_path(root: Path, source: str, symbol: str, interval: str, month: str, version: int = 1) -> Path:
    name = f"{month}.parquet" if version == 1 else f"{month}.v{version}.parquet"
    return root / "bronze" / source / symbol / interval / name


def month_of(open_time_ms: int) -> str:
    ts = pd.Timestamp(open_time_ms, unit="ms", tz="UTC")
    return f"{ts.year:04d}-{ts.month:02d}"


def _next_version(path: Path) -> int:
    stem = path.stem  # YYYY-MM
    siblings = path.parent.glob(f"{stem}.v*.parquet")
    versions = [int(p.stem.rsplit(".v", 1)[1]) for p in siblings]
    return max(versions, default=1) + 1


def write_month(df: pd.DataFrame, path: Path, *, append: bool = False) -> bool:
    """Write a monthly partition.

    Default (backfill corrections): identical content is a no-op, differing
    content for an existing partition becomes the next immutable version.
    append=True (incremental merge): the new frame must be a superset of the
    existing rows (append-only contract), so it overwrites in place.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = pd.read_parquet(path)
        if existing.reset_index(drop=True).equals(df.reset_index(drop=True)):
            return False
        if append:
            df.to_parquet(path, index=False)
            logger.info("bronze append: %s (%d rows)", path.name, len(df))
            return True
        version = _next_version(path)
        new_path = path.with_name(f"{path.stem}.v{version}.parquet")
        df.to_parquet(new_path, index=False)
        logger.info("bronze correction: wrote %s (v%d)", new_path.name, version)
        return True
    df.to_parquet(path, index=False)
    logger.info("bronze write: %s (%d rows)", path.name, len(df))
    return True


def read_symbol(root: Path, source: str, symbol: str, interval: str) -> pd.DataFrame:
    frames = []
    directory = root / "bronze" / source / symbol / interval
    if not directory.is_dir():
        return pd.DataFrame(columns=KLINE_COLUMNS)
    for path in sorted(directory.glob("*.parquet")):
        frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame(columns=KLINE_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values("open_time").reset_index(drop=True)
