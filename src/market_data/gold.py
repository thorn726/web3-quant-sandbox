"""Gold layer: feature tables derived from silver, for strategy consumption.

Each build writes a full, versioned feature table:
gold/{source}/{symbol}/{interval}/features-v{SCHEMA_VERSION}.parquet
plus a sidecar meta JSON recording the schema version and the source
watermark at build time. Rebuilds are idempotent: same input, same output.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import pandas as pd

from market_data import silver

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
FEATURE_COLUMNS = [
    "open_time",
    "log_return",
    "sma_5_20_ratio",
    "volatility_20",
    "volume_zscore_20",
]
MIN_BARS = 20


def _features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["open_time"] = df["open_time"].astype("int64")
    out["log_return"] = (df["close"] / df["close"].shift(1)).apply(lambda r: _safe_log(r))
    sma5 = df["close"].rolling(5).mean()
    sma20 = df["close"].rolling(20).mean()
    out["sma_5_20_ratio"] = sma5 / sma20
    out["volatility_20"] = out["log_return"].rolling(20).std()
    mean_vol = df["volume"].rolling(20).mean()
    std_vol = df["volume"].rolling(20).std()
    out["volume_zscore_20"] = (df["volume"] - mean_vol) / std_vol
    return out[FEATURE_COLUMNS]


def _safe_log(ratio: float) -> float:
    if pd.isna(ratio) or ratio <= 0:
        return float("nan")
    return math.log(ratio)


def gold_dir(root: Path, source: str, symbol: str, interval: str) -> Path:
    return root / "gold" / f"{source}:{symbol}:{interval}"


def table_path(root: Path, source: str, symbol: str, interval: str) -> Path:
    return gold_dir(root, source, symbol, interval) / f"features-v{SCHEMA_VERSION}.parquet"


def build_features(root: Path, source: str, symbol: str, interval: str) -> pd.DataFrame:
    """Derive the feature table from current silver; idempotent full rebuild."""
    bars = silver.build_silver(root, source, symbol, interval)
    features = _features(bars) if len(bars) >= 2 else pd.DataFrame(columns=FEATURE_COLUMNS)
    path = table_path(root, source, symbol, interval)
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(path, index=False)
    wm = silver.watermark(root, source, symbol, interval)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "source_watermark": wm,
        "rows": len(features),
    }
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    logger.info("gold build: %s rows=%d watermark=%s", path.name, len(features), wm)
    return features


def load_features(root: Path, source: str, symbol: str, interval: str) -> pd.DataFrame:
    path = table_path(root, source, symbol, interval)
    if not path.exists():
        raise FileNotFoundError(f"gold table not built: {path}")
    return pd.read_parquet(path)
