import pandas as pd
import pytest

from market_data import silver, storage, watermarks


def _good_rows(open_times, base=100.0):
    return pd.DataFrame(
        {
            "open_time": open_times,
            "open": [base] * len(open_times),
            "high": [base + 1] * len(open_times),
            "low": [base - 1] * len(open_times),
            "close": [base + 0.5] * len(open_times),
            "volume": [10.0] * len(open_times),
            "close_time": [t + 59_999 for t in open_times],
            "quote_volume": [1000.0] * len(open_times),
            "trades": [5] * len(open_times),
        }
    )


def _write_bronze(root, rows, symbol="BTCUSDT", interval="1m"):
    for month, group in rows.groupby(rows["open_time"].map(storage.month_of)):
        path = storage.partition_path(root, "binance", symbol, interval, str(month))
        path.parent.mkdir(parents=True, exist_ok=True)
        group.to_parquet(path, index=False)


def test_good_bars_pass_with_gap_marking(tmp_path):
    t0 = 1_704_067_200_000
    times = [t0 + i * 60_000 for i in range(5)]
    times.append(t0 + 9 * 60_000)  # a hole between index 4 and this bar
    _write_bronze(tmp_path, _good_rows(times))
    result = silver.build_silver(tmp_path, "binance", "BTCUSDT", "1m")
    assert len(result) == 6
    assert list(result.columns) == silver.SILVER_COLUMNS
    assert result["gap_after"].tolist() == [False, False, False, False, True, False]


def test_bad_bars_quarantined_not_in_silver(tmp_path):
    t0 = 1_704_067_200_000
    good = _good_rows([t0 + i * 60_000 for i in range(3)])
    crossed = _good_rows([t0 + 3 * 60_000])
    crossed.loc[:, "high"] = 90.0  # high < low: ohlc_range violation
    negative = _good_rows([t0 + 4 * 60_000])
    negative.loc[:, "volume"] = -5.0
    _write_bronze(tmp_path, pd.concat([good, crossed, negative], ignore_index=True))

    result = silver.build_silver(tmp_path, "binance", "BTCUSDT", "1m")
    assert len(result) == 3  # bad rows never reach silver
    q_dir = tmp_path / "quarantine" / "binance:BTCUSDT:1m"
    files = sorted(p.name for p in q_dir.glob("*.parquet"))
    assert files == ["negative_volume.parquet", "ohlc_range.parquet"]
    quarantined = pd.read_parquet(q_dir / "negative_volume.parquet")
    assert len(quarantined) == 1
    # re-running is idempotent: quarantine does not duplicate rows
    silver.build_silver(tmp_path, "binance", "BTCUSDT", "1m")
    assert len(pd.read_parquet(q_dir / "negative_volume.parquet")) == 1


def test_watermark_visible_downstream(tmp_path):
    wm = tmp_path / "watermarks.json"
    watermarks.advance(wm, silver.dataset_key("binance", "BTCUSDT", "1m"), 1_704_067_200_000)
    assert silver.watermark(tmp_path, "binance", "BTCUSDT", "1m") == 1_704_067_200_000
    assert silver.watermark(tmp_path, "binance", "ETHUSDT", "1m") is None


def test_empty_bronze_returns_empty_silver(tmp_path):
    result = silver.build_silver(tmp_path, "binance", "ETHUSDT", "1m")
    assert result.empty and list(result.columns) == silver.SILVER_COLUMNS


def test_unknown_interval_rejected(tmp_path):
    _write_bronze(tmp_path, _good_rows([1_704_067_200_000]), interval="7m")
    with pytest.raises(ValueError):
        silver.build_silver(tmp_path, "binance", "BTCUSDT", "7m")
