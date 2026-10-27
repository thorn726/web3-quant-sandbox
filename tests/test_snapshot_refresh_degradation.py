from __future__ import annotations

import hashlib
from pathlib import Path

from dashboard.catalog import SNAPSHOT_NAMES, offline_status
from dashboard.refresh import refresh_all
from dashboard.snapshot import SNAPSHOT_DIR, load_offline, snapshot_path


def _digests() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(SNAPSHOT_DIR.glob("*.json"))
        if path.is_file()
    }


def test_refresh_failure_keeps_old_snapshots_and_serves_stale_data(monkeypatch) -> None:
    import dashboard.refresh as refresh

    def unreachable(*args, **kwargs):
        raise RuntimeError("simulated network outage")

    monkeypatch.setattr(refresh.dashboard_api, "ai_picks", unreachable)
    monkeypatch.setattr(refresh.dashboard_api, "sector_fund", unreachable)
    monkeypatch.setattr(refresh.dashboard_api, "token_fund", unreachable)
    monkeypatch.setattr(refresh.dashboard_api, "onchain", unreachable)
    monkeypatch.setattr(refresh.dashboard_api, "web3_news", unreachable)
    monkeypatch.setattr(refresh, "fetch_full_dex_trending", unreachable)
    monkeypatch.setattr(refresh, "fetch_full_market_tickers", unreachable)
    monkeypatch.setattr(refresh, "fetch_full_kucoin_markets", unreachable)
    monkeypatch.setattr(refresh, "fetch_full_exchange_markets", unreachable)
    monkeypatch.setattr(refresh, "fetch_full_opportunity_scan", unreachable)
    monkeypatch.setattr(refresh, "fetch_full_market_candles", unreachable)
    monkeypatch.setattr(refresh, "fetch_full_valuescan_global", unreachable)
    monkeypatch.setattr(refresh, "fetch_full_valuescan_token", unreachable)
    monkeypatch.setattr(refresh.valuescan, "configured", lambda: False)

    before = _digests()
    assert before, "offline snapshots should exist on disk"

    result = refresh_all(save=True, data_mode="auto")

    assert result["ok"] is False
    assert result["saved"] == []
    error_names = {item["name"] for item in result["errors"]}
    assert "opportunity_scan" in error_names
    assert all(item["error"] for item in result["errors"])

    assert _digests() == before, "failed refresh must not modify snapshot files"

    stale = load_offline("opportunity_scan")
    assert stale is not None
    assert stale.get("source") in {"snapshot", "fixture"}

    status = offline_status()
    assert status["ok"] is True
    assert set(SNAPSHOT_NAMES).issubset(status["datasets"])


def test_snapshot_paths_resolve_inside_snapshot_dir() -> None:
    for name in ("opportunity_scan", "market_tickers"):
        path = snapshot_path(name)
        assert Path(path).parent == SNAPSHOT_DIR
