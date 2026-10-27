"""Silver layer: clean standard bars from bronze.

Rules (spec decision 13):
1. integrity: high >= low, open/close within [low, high], volume >= 0
2. failures go to quarantine, never into silver
3. downstream sees each dataset's freshness watermark

Output schema: bronze kline columns plus ``gap_after`` (True when the next
bar's open_time is not exactly one interval later) — gaps are marked, not
fabricated.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from market_data import storage, watermarks

logger = logging.getLogger(__name__)

SILVER_COLUMNS = storage.KLINE_COLUMNS + ["gap_after"]

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def dataset_key(source: str, symbol: str, interval: str) -> str:
    return f"{source}:{symbol}:{interval}"


def watermark(root: Path, source: str, symbol: str, interval: str) -> int | None:
    """Downstream-visible freshness for a dataset."""
    return watermarks.get(root / "watermarks.json", dataset_key(source, symbol, interval))


def _violations(df: pd.DataFrame) -> pd.DataFrame:
    problems = pd.Series("", index=df.index, dtype="object")
    problems.where(
        (df["high"] >= df["low"])
        & (df["high"] >= df[["open", "close"]].max(axis=1))
        & (df["low"] <= df[["open", "close"]].min(axis=1)),
        "ohlc_range",
        inplace=True,
    )
    problems.where(df["volume"] >= 0, problems + ";negative_volume", inplace=True)
    duplicated = df["open_time"].duplicated(keep="last")
    problems.where(~duplicated, problems + ";duplicate_open_time", inplace=True)
    non_positive_time = df["open_time"] <= 0
    problems.where(~non_positive_time, problems + ";bad_open_time", inplace=True)
    return problems


def _mark_gaps(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    step = INTERVAL_MS.get(interval)
    if step is None:
        raise ValueError(f"unknown interval: {interval}")
    df = df.sort_values("open_time").reset_index(drop=True)
    gap_after = df["open_time"].shift(-1).sub(df["open_time"]).ne(step)
    if len(df) > 0:
        gap_after.iloc[-1] = False  # no next bar yet
    df = df.copy()
    df["gap_after"] = gap_after.astype(bool)
    return df


def quarantine(df: pd.DataFrame, reasons: pd.Series, root: Path, dataset: str) -> int:
    """Park bad rows under quarantine/{dataset}/{reason}.parquet. Returns count."""
    if df.empty:
        return 0
    total = 0
    bad = df.assign(reason=reasons)
    for reason, group in bad[bad["reason"] != ""].groupby("reason"):
        slug = str(reason).replace(";", "_").strip("_") or "misc"
        out_dir = root / "quarantine" / dataset
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{slug}.parquet"
        combined = group if not out_path.exists() else pd.concat([pd.read_parquet(out_path), group], ignore_index=True)
        combined.drop_duplicates(subset=["open_time", "reason"], keep="last").to_parquet(out_path, index=False)
        logger.warning("quarantined %d rows (%s) for %s", len(group), slug, dataset)
        total += len(group)
    return total


def build_silver(root: Path, source: str, symbol: str, interval: str) -> pd.DataFrame:
    """Clean bronze into silver. Bad rows go to quarantine and are dropped."""
    dataset = dataset_key(source, symbol, interval)
    bronze = storage.read_symbol(root, source, symbol, interval)
    if bronze.empty:
        return pd.DataFrame(columns=SILVER_COLUMNS)

    reasons = _violations(bronze)
    quarantine(bronze, reasons, root, dataset)
    clean = bronze[reasons == ""].reset_index(drop=True)
    if clean.empty:
        return pd.DataFrame(columns=SILVER_COLUMNS)
    silver = _mark_gaps(clean, interval)
    return silver[SILVER_COLUMNS]
