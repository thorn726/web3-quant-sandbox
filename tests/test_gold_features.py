import json

import pandas as pd
import pytest

from market_data import gold, silver, storage, watermarks


def _bars(n=60, t0=1_704_067_200_000, base=100.0):
    times = [t0 + i * 60_000 for i in range(n)]
    prices = [base + (i % 7) * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "open_time": times,
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [10.0 + (i % 3) for i in range(n)],
            "close_time": [t + 59_999 for t in times],
            "quote_volume": [1000.0] * n,
            "trades": [5] * n,
        }
    )


@pytest.fixture()
def seeded(tmp_path):
    _write_bronze(tmp_path, _bars())
    watermarks.advance(
        tmp_path / "watermarks.json", silver.dataset_key("binance", "BTCUSDT", "1m"), 1_704_067_200_000 + 59 * 60_000
    )
    return tmp_path


def _write_bronze(root, rows, symbol="BTCUSDT", interval="1m"):
    for month, group in rows.groupby(rows["open_time"].map(storage.month_of)):
        path = storage.partition_path(root, "binance", symbol, interval, str(month))
        path.parent.mkdir(parents=True, exist_ok=True)
        group.to_parquet(path, index=False)


def test_features_derived_and_versioned(seeded):
    features = gold.build_features(seeded, "binance", "BTCUSDT", "1m")
    assert list(features.columns) == gold.FEATURE_COLUMNS
    assert len(features) == 60
    # rolling(20) columns are NaN before MIN_BARS-1 rows
    assert features["volatility_20"].iloc[18] != features["volatility_20"].iloc[18]  # NaN before 20 bars
    assert features["volatility_20"].iloc[25] == features["volatility_20"].iloc[25]  # not NaN after
    meta = json.loads(gold.table_path(seeded, "binance", "BTCUSDT", "1m").with_suffix(".meta.json").read_text())
    assert meta["schema_version"] == gold.SCHEMA_VERSION
    assert meta["source_watermark"] == 1_704_067_200_000 + 59 * 60_000


def test_rebuild_idempotent(seeded):
    p = gold.table_path(seeded, "binance", "BTCUSDT", "1m")
    first = gold.build_features(seeded, "binance", "BTCUSDT", "1m")
    stamp1 = p.read_bytes()
    second = gold.build_features(seeded, "binance", "BTCUSDT", "1m")
    assert p.read_bytes() == stamp1
    pd.testing.assert_frame_equal(first, second)


def test_load_requires_build(tmp_path):
    with pytest.raises(FileNotFoundError):
        gold.load_features(tmp_path, "binance", "BTCUSDT", "1m")
    gold.build_features(tmp_path, "binance", "BTCUSDT", "1m")  # empty silver -> empty table
    assert gold.load_features(tmp_path, "binance", "BTCUSDT", "1m").empty


def test_features_consumable_by_backtest(seeded):
    gold.build_features(seeded, "binance", "BTCUSDT", "1m")
    df = gold.load_features(seeded, "binance", "BTCUSDT", "1m")
    assert "open_time" in df.columns
    tail = df["sma_5_20_ratio"].dropna()
    assert len(tail) > 0 and (tail > 0).all()
