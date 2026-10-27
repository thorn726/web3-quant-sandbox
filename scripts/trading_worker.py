"""Trading worker: reconciliation + freshness checks + daily heartbeat.

Runs on a systemd timer (every 5 minutes). One-shot, idempotent:
- reconciliation against Binance (skipped without API keys, e.g. paper phase)
- data freshness check against watermarks (alerts when a dataset goes stale)
- daily heartbeat, once per UTC day (marker file)
Any reconciliation difference trips the circuit breaker and alerts.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading import alerts, daily_pnl, reconcile  # noqa: E402
from trading.breaker import CircuitBreaker  # noqa: E402
from trading.ledger import Ledger  # noqa: E402

DATA = ROOT / "data"
LOG = logging.getLogger("trading_worker")

STALE_AFTER_MS = int(os.environ.get("TRADING_STALE_AFTER_MS", str(6 * 3600 * 1000)))
WATERMARK_MIN_ROWS = 1


def _watermark_dataset(root: Path, dataset: str) -> int | None:
    import json

    path = root / "market_data" / "watermarks.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get(dataset)


def check_freshness(root: Path, datasets: list[str], notify=alerts.alert) -> list[str]:
    """Alert when a tracked dataset's watermark is older than the stale window."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    stale = []
    for dataset in datasets:
        wm = _watermark_dataset(root, dataset)
        if wm is None or now_ms - wm > STALE_AFTER_MS:
            stale.append(dataset)
    if stale:
        try:
            notify(f"[STALE] datasets overdue for refresh: {', '.join(stale)}")
        except Exception as exc:
            LOG.error("stale alert failed: %s", exc)
    return stale


def daily_heartbeat(state_dir: Path, breaker: CircuitBreaker, notify=alerts.alert) -> bool:
    """One heartbeat per UTC day; proves the worker is alive."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    marker = state_dir / "last_heartbeat.txt"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == today:
        return False
    state = breaker.state()
    pnl_ledger = Ledger(DATA / "trading" / "ledger.db")
    try:
        pnl = daily_pnl.daily_pnl(pnl_ledger, today)
    finally:
        pnl_ledger.close()
    text = (
        f"[heartbeat] {today} worker alive; breaker={'TRIPPED: ' + state['reason'] if state['tripped'] else 'clear'}; "
        f"today realized P&L: {pnl:.2f} quote"
    )
    try:
        notify(text)
    except Exception as exc:
        LOG.error("heartbeat alert failed: %s", exc)
    state_dir.mkdir(parents=True, exist_ok=True)
    marker.write_text(today + "\n", encoding="utf-8")
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    breaker = CircuitBreaker(DATA / "trading" / "breaker.json")

    if os.environ.get("BINANCE_API_KEY") and os.environ.get("BINANCE_API_SECRET"):
        ledger = Ledger(DATA / "trading" / "ledger.db")
        try:
            for symbol in [s.strip().upper() for s in os.environ.get("MARKET_DATA_SYMBOLS", "BTCUSDT").split(",")]:
                try:
                    trades = reconcile.fetch_exchange_trades(symbol)
                except Exception as exc:
                    LOG.error("exchange fetch failed for %s: %s", symbol, exc)
                    continue
                reconcile.reconcile(ledger, breaker, trades)
        finally:
            ledger.close()
    else:
        LOG.info("exchange keys not configured; skipping reconciliation (paper phase)")

    datasets = [
        f"binance:{symbol.strip()}:{os.environ.get('MARKET_DATA_INTERVAL', '1d')}"
        for symbol in os.environ.get("MARKET_DATA_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
        if symbol.strip()
    ]
    stale = check_freshness(DATA / "market_data", datasets)
    daily_heartbeat(DATA / "trading", breaker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
