import pandas as pd
import pytest

from market_data import refresh, storage, watermarks


def _sample_rows(open_times_ms, base_price=100.0):
    return pd.DataFrame(
        {
            "open_time": open_times_ms,
            "open": [base_price] * len(open_times_ms),
            "high": [base_price + 1] * len(open_times_ms),
            "low": [base_price - 1] * len(open_times_ms),
            "close": [base_price + 0.5] * len(open_times_ms),
            "volume": [10.0] * len(open_times_ms),
            "close_time": [t + 59_999 for t in open_times_ms],
            "quote_volume": [1000.0] * len(open_times_ms),
            "trades": [5] * len(open_times_ms),
        }
    )


def test_write_month_idempotent_and_corrections_versioned(tmp_path):
    month = "2024-01"
    path = storage.partition_path(tmp_path, "binance", "BTCUSDT", "1m", month)
    df = _sample_rows([1_704_067_200_000 + i * 60_000 for i in range(10)])
    assert storage.write_month(df, path) is True
    assert storage.write_month(df, path) is False  # identical = no-op
    df_extra = _sample_rows([1_704_067_200_000 + i * 60_000 for i in range(11)])
    assert storage.write_month(df_extra, path) is True  # correction -> v2
    assert path.with_name("2024-01.v2.parquet").exists()
    # original v1 untouched
    assert len(pd.read_parquet(path)) == 10


def test_incremental_appends_rows_never_rewrites_history(tmp_path, monkeypatch):
    symbol, interval = "BTCUSDT", "1m"
    t0 = 1_704_067_200_000
    first = _sample_rows([t0 + i * 60_000 for i in range(5)])
    path = storage.partition_path(tmp_path, "binance", symbol, interval, storage.month_of(t0))
    path.parent.mkdir(parents=True)
    first.to_parquet(path, index=False)
    wm = tmp_path / "watermarks.json"
    watermarks.advance(wm, f"binance:{symbol}:{interval}", int(first["open_time"].max()))

    later = _sample_rows([t0 + i * 60_000 for i in range(5, 9)], base_price=105.0)
    monkeypatch.setattr(refresh, "fetch_rest_klines", lambda s, i, start, timeout=30.0: later)

    result = refresh.refresh_incremental(tmp_path, symbol, interval)
    assert result.ok and result.rows == 4
    merged = pd.read_parquet(path)
    assert len(merged) == 9
    # the original five rows keep their original values (append-only)
    assert merged["open"].iloc[:5].tolist() == first["open"].tolist()
    assert watermarks.get(wm, f"binance:{symbol}:{interval}") == int(later["open_time"].max())


def test_outage_leaves_bronze_and_watermark_untouched(tmp_path, monkeypatch):
    symbol, interval = "ETHUSDT", "1m"
    t0 = 1_704_067_200_000
    path = storage.partition_path(tmp_path, "binance", symbol, interval, storage.month_of(t0))
    path.parent.mkdir(parents=True)
    _sample_rows([t0]).to_parquet(path, index=False)
    wm = tmp_path / "watermarks.json"
    watermarks.advance(wm, f"binance:{symbol}:{interval}", t0)

    def unreachable(*args, **kwargs):
        raise ConnectionError("network unreachable")

    monkeypatch.setattr(refresh, "fetch_rest_klines", unreachable)
    result = refresh.refresh_incremental(tmp_path, symbol, interval)
    assert result.ok is False and result.error
    assert len(pd.read_parquet(path)) == 1  # old data survives
    assert watermarks.get(wm, f"binance:{symbol}:{interval}") == t0  # watermark frozen


def test_watermark_never_moves_backward(tmp_path):
    wm = tmp_path / "watermarks.json"
    watermarks.advance(wm, "d", 1000)
    watermarks.advance(wm, "d", 500)
    assert watermarks.get(wm, "d") == 1000


def test_backfill_idempotent(monkeypatch, tmp_path):
    symbol, interval = "BTCUSDT", "1m"
    t0 = 1_704_067_200_000  # 2024-01-01
    payload = _sample_rows([t0 + i * 60_000 for i in range(3)])

    def fake_fetch(sym, itv, month, timeout=60.0):
        return b""  # unused; parse is bypassed below

    monkeypatch.setattr(refresh, "fetch_vision_month", fake_fetch)
    monkeypatch.setattr(refresh, "_parse_vision_csv", lambda raw: payload)
    r1 = refresh.backfill_vision(tmp_path, symbol, interval, t0, end_ms=t0 + 60_000)
    assert r1.ok and r1.rows == 3
    r2 = refresh.backfill_vision(tmp_path, symbol, interval, t0, end_ms=t0 + 60_000)
    assert r2.rows == 0 and r2.months_written == []  # second pass: no rewrites


def test_append_never_overwrites_restatement(tmp_path, monkeypatch):
    from market_data import refresh as md_refresh

    symbol, interval = "BTCUSDT", "1m"
    t0 = 1_704_067_200_000
    original = _sample_rows([t0 + i * 60_000 for i in range(5)])
    path = storage.partition_path(tmp_path, "binance", symbol, interval, storage.month_of(t0))
    path.parent.mkdir(parents=True)
    original.to_parquet(path, index=False)
    watermarks.advance(tmp_path / "watermarks.json", f"binance:{symbol}:{interval}", int(original["open_time"].max()))

    # exchange restates an existing bar and adds a new one
    restated = _sample_rows([t0, t0 + 5 * 60_000], base_price=999.0)
    monkeypatch.setattr(md_refresh, "fetch_rest_klines", lambda s, i, start, timeout=30.0: restated)
    result = md_refresh.refresh_incremental(tmp_path, symbol, interval)
    assert result.ok
    merged = storage.read_symbol(tmp_path, "binance", symbol, interval)
    assert len(merged) == 6
    assert merged["open"].iloc[0] == original["open"].iloc[0]  # original preserved


def test_backfill_completeness_uses_interval_granularity(tmp_path, monkeypatch):
    from market_data import refresh as md_refresh

    symbol, interval = "BTCUSDT", "1d"
    t0 = 1_704_067_200_000  # 2024-01-01, daily bars
    payload = _sample_rows([t0, t0 + 86_400_000])
    monkeypatch.setattr(md_refresh, "fetch_vision_month", lambda s, i, m, timeout=60.0: b"")
    monkeypatch.setattr(md_refresh, "_parse_vision_csv", lambda raw: payload)
    md_refresh.backfill_vision(tmp_path, symbol, interval, t0, end_ms=t0 + 86_400_000)
    # second pass must NOT re-download: month complete at 1d granularity
    calls = []
    monkeypatch.setattr(
        md_refresh, "fetch_vision_month", lambda s, i, m, timeout=60.0: calls.append(m) or b""
    )
    result = md_refresh.backfill_vision(tmp_path, symbol, interval, t0, end_ms=t0 + 86_400_000)
    assert calls == [] and result.rows == 0
