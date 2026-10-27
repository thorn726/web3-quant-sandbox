"""Reconciliation: local fills vs exchange trade list.

Any discrepancy trips the circuit breaker and alerts. The comparison key
is the exchange trade id: live fills must record it; paper fills (empty
exchange id) are excluded from exchange comparison.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode

from trading import alerts
from trading.breaker import CircuitBreaker
from trading.ledger import Ledger

logger = logging.getLogger(__name__)

BINANCE_MY_TRADES = "https://api.binance.com/api/v3/myTrades"


@dataclass(slots=True)
class ReconcileReport:
    checked: int
    missing_locally: list[str]
    missing_on_exchange: list[str]
    ok: bool


def _signed_request(url: str, params: dict[str, str], api_key: str, api_secret: str) -> list[dict]:
    params = {**params, "timestamp": str(int(time.time() * 1000)), "recvWindow": "10000"}
    query = urlencode(params)
    signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(  # noqa: S310 - fixed https exchange host
        f"{url}?{query}&signature={signature}",
        headers={"X-MBX-APIKEY": api_key},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        if resp.status != 200:
            raise RuntimeError(f"exchange API returned {resp.status}")
        return json.loads(resp.read().decode("utf-8"))


def fetch_exchange_trades(symbol: str, limit: int = 500) -> list[dict]:
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")
    if not api_key or not api_secret:
        raise RuntimeError("BINANCE_API_KEY / BINANCE_API_SECRET not configured")
    return _signed_request(BINANCE_MY_TRADES, {"symbol": symbol, "limit": str(limit)}, api_key, api_secret)


def local_exchange_ids(ledger: Ledger) -> set[str]:
    rows = ledger._conn.execute(
        "SELECT exchange_trade_id FROM fills WHERE exchange_trade_id != ''"
    ).fetchall()
    return {row[0] for row in rows}


def reconcile(ledger: Ledger, breaker: CircuitBreaker, exchange_trades: list[dict], notify=alerts.alert) -> ReconcileReport:
    local_ids = local_exchange_ids(ledger)
    exchange_ids = {str(t["id"]) for t in exchange_trades}
    missing_locally = sorted(exchange_ids - local_ids)
    missing_on_exchange = sorted(local_ids - exchange_ids)
    report = ReconcileReport(
        checked=len(exchange_ids),
        missing_locally=missing_locally,
        missing_on_exchange=missing_on_exchange,
        ok=not missing_locally and not missing_on_exchange,
    )
    if not report.ok:
        reason = (
            f"reconciliation failed: {len(missing_locally)} fill(s) missing locally, "
            f"{len(missing_on_exchange)} fill(s) missing on exchange"
        )
        breaker.trip(reason)
        logger.error("%s; circuit breaker tripped", reason)
        try:
            notify(f"[CIRCUIT BREAK] {reason}")
        except Exception as exc:  # alert failure must not change safety state
            logger.error("reconcile alert failed: %s", exc)
    else:
        logger.info("reconciliation clean: %d exchange fills checked", report.checked)
    return report
