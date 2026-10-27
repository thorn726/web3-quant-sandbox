"""Bronze refresh pipeline: Binance Vision backfill + REST incremental.

Both writers are idempotent. Any fetch failure leaves bronze and the
watermark untouched and is reported to the caller via the result object —
the outage contract is "old data survives, watermark does not advance".
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

from market_data import storage, watermarks

logger = logging.getLogger(__name__)

VISION_BASE = "https://data.binance.vision/data/spot/monthly/klines"
REST_BASE = "https://api.binance.com/api/v3/klines"

VISION_COLUMN_INDEX = {
    "open_time": 0,
    "open": 1,
    "high": 2,
    "low": 3,
    "close": 4,
    "volume": 5,
    "close_time": 6,
    "quote_volume": 7,
    "trades": 8,
}


@dataclass(slots=True)
class RefreshResult:
    dataset: str
    months_written: list[str]
    rows: int
    ok: bool
    error: str = ""


def _parse_vision_csv(raw: bytes) -> pd.DataFrame:
    rows = []
    reader = csv.reader(io.StringIO(raw.decode("utf-8")))
    for row in reader:
        if not row:
            continue
        rows.append({col: row[idx] for col, idx in VISION_COLUMN_INDEX.items()})
    df = pd.DataFrame(rows, columns=list(VISION_COLUMN_INDEX))
    df["open_time"] = df["open_time"].astype("int64")
    for col in ("open", "high", "low", "close", "volume", "quote_volume"):
        df[col] = df[col].astype("float64")
    df["close_time"] = df["close_time"].astype("int64")
    df["trades"] = df["trades"].astype("int64")
    return df.sort_values("open_time").drop_duplicates("open_time").reset_index(drop=True)


def _months_between(start_ms: int, end_ms: int) -> list[str]:
    start = pd.Timestamp(start_ms, unit="ms", tz="UTC")
    end = pd.Timestamp(end_ms, unit="ms", tz="UTC")
    months = []
    cursor = pd.Timestamp(year=start.year, month=start.month, day=1, tz="UTC")
    while cursor <= end:
        months.append(f"{cursor.year:04d}-{cursor.month:02d}")
        cursor += pd.offsets.MonthBegin(1)
    return months


def _month_bounds(month: str) -> tuple[int, int]:
    start = pd.Timestamp(f"{month}-01", tz="UTC")
    end = start + pd.offsets.MonthBegin(1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1


def fetch_vision_month(symbol: str, interval: str, month: str, timeout: float = 60.0) -> bytes:
    name = f"{symbol}-{interval}-{month}.zip"
    url = f"{VISION_BASE}/{symbol}/{interval}/{name}"
    with urlopen(url, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        if resp.status != 200:
            raise RuntimeError(f"vision download failed: {resp.status} {url}")
        with zipfile.ZipFile(io.BytesIO(resp.read())) as zf:
            inner = zf.namelist()[0]
            return zf.read(inner)


def backfill_vision(root: Path, symbol: str, interval: str, start_ms: int, end_ms: int | None = None) -> RefreshResult:
    """One-pass historical backfill from Binance Vision monthly dumps."""
    dataset = f"binance:{symbol}:{interval}"
    end = end_ms if end_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    written: list[str] = []
    rows = 0
    for month in _months_between(start_ms, end):
        path = storage.partition_path(root, "binance", symbol, interval, month)
        if path.exists() and not storage.partition_path(root, "binance", symbol, interval, month, version=2).exists():
            existing = pd.read_parquet(path)
            lo, hi = _month_bounds(month)
            if int(existing["open_time"].min()) >= lo and int(existing["open_time"].max()) >= hi - 60_000:
                continue  # complete month already archived
        raw = fetch_vision_month(symbol, interval, month)
        df = _parse_vision_csv(raw)
        if storage.write_month(df, path):
            written.append(month)
        rows += len(df)
        lo, _ = _month_bounds(month)
        watermarks.advance(root / "watermarks.json", dataset, int(df["open_time"].max()))
    return RefreshResult(dataset=dataset, months_written=written, rows=rows, ok=True)


def fetch_rest_klines(symbol: str, interval: str, start_ms: int, timeout: float = 30.0) -> pd.DataFrame:
    """Incremental klines via Binance REST (ccxt-compatible shape, stdlib client)."""
    import json

    url = f"{REST_BASE}?symbol={symbol}&interval={interval}&startTime={start_ms}&limit=1000"
    with urlopen(url, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        if resp.status != 200:
            raise RuntimeError(f"rest fetch failed: {resp.status}")
        payload = json.loads(resp.read().decode("utf-8"))
    columns = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades"]
    rows = [
        {
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": int(k[6]),
            "quote_volume": float(k[7]),
            "trades": int(k[8]),
        }
        for k in payload
    ]
    return pd.DataFrame(rows, columns=columns)


def refresh_incremental(root: Path, symbol: str, interval: str) -> RefreshResult:
    """Append new klines since the watermark. Failure = no side effects."""
    dataset = f"binance:{symbol}:{interval}"
    wm_path = root / "watermarks.json"
    start = watermarks.get(wm_path, dataset)
    if start is None:
        raise RuntimeError(f"no watermark for {dataset}; run backfill first")
    try:
        df = fetch_rest_klines(symbol, interval, start + 1)
    except Exception as exc:  # outage path: log, no writes
        logger.warning("incremental refresh failed for %s: %s", dataset, exc)
        return RefreshResult(dataset=dataset, months_written=[], rows=0, ok=False, error=str(exc))
    if df.empty:
        return RefreshResult(dataset=dataset, months_written=[], rows=0, ok=True)
    for month, group in df.groupby(df["open_time"].map(storage.month_of)):
        path = storage.partition_path(root, "binance", symbol, interval, str(month))
        merged = group
        if path.exists():
            existing = pd.read_parquet(path)
            merged = (
                pd.concat([existing, group], ignore_index=True)
                .sort_values("open_time")
                .drop_duplicates("open_time", keep="last")
                .reset_index(drop=True)
            )
        storage.write_month(merged, path, append=True)
        watermarks.advance(wm_path, dataset, int(merged["open_time"].max()))
    return RefreshResult(dataset=dataset, months_written=[], rows=len(df), ok=True)
