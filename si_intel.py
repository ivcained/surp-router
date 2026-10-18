#!/usr/bin/env python3
"""Server-side Surplus Intelligence data proxies with TTL caches.

The gateway's own market cache (GatewayMarketCache in gateway.py) feeds routing;
this module feeds the *public data API* — live market snapshots, per-model
order books, provider performance analytics, and a merged provider table.

Design constraints:
- Every response is cached (30s markets / 300s providers / 60s performance) so
  a burst of agent traffic cannot hammer SI.
- The SI API key never leaves this process; public responses carry only data.
- Failures raise SIError; handlers convert that to a 502 with the SI status.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

import aiohttp

log = logging.getLogger("surp.si_intel")

SURPLUS_BASE = os.environ.get("SI_BASE_URL", "https://api.surplusintelligence.ai")
MARKETS_URL = f"{SURPLUS_BASE}/api/markets"
PROVIDERS_URL = f"{SURPLUS_BASE}/v1/providers"
PERFORMANCE_URL = f"{SURPLUS_BASE}/api/analytics/performance"

MARKETS_TTL = float(os.environ.get("SI_MARKETS_TTL", "30"))
PROVIDERS_TTL = float(os.environ.get("SI_PROVIDERS_TTL", "300"))
PERFORMANCE_TTL = float(os.environ.get("SI_PERFORMANCE_TTL", "60"))
FETCH_TIMEOUT = float(os.environ.get("SI_FETCH_TIMEOUT", "20"))


class SIError(Exception):
    """SI fetch failed. Carries the upstream HTTP status when known."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


async def _fetch_json(url: str, headers: Optional[dict] = None) -> tuple[int, Any]:
    """GET a JSON document from SI. Returns (status, parsed body)."""
    hdrs = {"Accept": "application/json"}
    key = os.environ.get("SURPLUS_INTELLIGENCE_API_KEY", "").strip()
    if key:
        hdrs["Authorization"] = f"Bearer {key}"
    if headers:
        hdrs.update(headers)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=hdrs, timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT)
            ) as resp:
                try:
                    body = await resp.json()
                except Exception:
                    body = {"error": "non-JSON response from Surplus Intelligence"}
                return resp.status, body
    except Exception as e:
        raise SIError(f"surplus intelligence fetch failed: {e}") from e


class _TTLCache:
    """One cached JSON value with a TTL and single-flight refresh."""

    def __init__(self, ttl: float):
        self.ttl = ttl
        self._value: Any = None
        self._ts: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self, loader):
        if self._value is not None and (time.monotonic() - self._ts) < self.ttl:
            return self._value
        async with self._lock:
            if self._value is not None and (time.monotonic() - self._ts) < self.ttl:
                return self._value
            self._value = await loader()
            self._ts = time.monotonic()
            return self._value


_markets_cache = _TTLCache(MARKETS_TTL)
_providers_cache = _TTLCache(PROVIDERS_TTL)
_perf_cache: dict[str, _TTLCache] = {}
_perf_cache_lock = asyncio.Lock()


async def markets() -> dict:
    """Live market snapshot: {count, cached_at, age_seconds, markets}."""
    data = await _markets_cache.get(_load_markets)
    age = max(0, int(time.time() - data["_fetched_at"]))
    return {
        "count": len(data["markets"]),
        "cached_at": int(data["_fetched_at"]),
        "age_seconds": age,
        "ttl_seconds": int(MARKETS_TTL),
        "markets": data["markets"],
    }


async def _load_markets() -> dict:
    status, body = await _fetch_json(MARKETS_URL)
    if status != 200:
        raise SIError(f"markets fetch returned {status}", status=502)
    rows = body.get("markets", []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    return {"_fetched_at": time.time(), "markets": rows}


async def market_for(model: str) -> Optional[dict]:
    """One model's market record (order book with per-provider offers), or None."""
    data = await _markets_cache.get(_load_markets)
    for row in data["markets"]:
        if str(row.get("model", "")) == model:
            return row
    return None


async def performance(model: str) -> tuple[int, Any]:
    """SI analytics for one model: (status, body). Cached per model."""
    cache = _perf_cache.get(model)
    if cache is None:
        async with _perf_cache_lock:
            cache = _perf_cache.setdefault(model, _TTLCache(PERFORMANCE_TTL))
    return await cache.get(lambda: _load_performance(model))


async def _load_performance(model: str) -> tuple[int, Any]:
    status, body = await _fetch_json(f"{PERFORMANCE_URL}/{model}")
    if status == 404:
        return 404, body
    if status != 200:
        raise SIError(f"performance fetch returned {status}", status=502)
    return status, body


def _measured_provider_stats() -> dict:
    """Surp's own measured per-provider stats (provider_health), fault-isolated."""
    try:
        import provider_health as ph
        return ph.provider_stats()
    except Exception as e:
        log.debug(f"provider_health stats unavailable: {e}")
        return {}


async def providers() -> dict:
    """Merged provider table: SI trusted flags + market aggregates + our measurements."""
    data = await _providers_cache.get(_load_providers)
    return data


async def _load_providers() -> dict:
    status, body = await _fetch_json(PROVIDERS_URL)
    if status != 200:
        raise SIError(f"providers fetch returned {status}", status=502)
    si_rows = body.get("data", []) if isinstance(body, dict) else []

    # Market aggregates per provider (models offered, healthy sellers, best price).
    market_agg: dict[str, dict] = {}
    try:
        market_data = await _markets_cache.get(_load_markets)
        for m in market_data["markets"]:
            for p in m.get("providers") or []:
                pid = str(p.get("provider", ""))
                if not pid:
                    continue
                agg = market_agg.setdefault(
                    pid, {"models": 0, "healthy_sellers": 0, "min_best_price_per_1m": None}
                )
                agg["models"] += 1
                agg["healthy_sellers"] += int(p.get("healthy_seller_count") or 0)
                price = p.get("best_price_per_1m")
                if price is not None and (agg["min_best_price_per_1m"] is None or price < agg["min_best_price_per_1m"]):
                    agg["min_best_price_per_1m"] = price
    except Exception as e:
        log.debug(f"market aggregates for providers unavailable: {e}")

    measured = _measured_provider_stats()

    out = []
    for row in si_rows:
        pid = str(row.get("id", ""))
        out.append({
            "id": pid,
            "name": row.get("name", pid),
            "host": row.get("host", ""),
            "base_url": row.get("base_url", ""),
            "trusted": bool(row.get("trusted", False)),
            "cost_reference_url": row.get("cost_reference_url"),
            "market": market_agg.get(pid, {"models": 0, "healthy_sellers": 0,
                                           "min_best_price_per_1m": None}),
            "measured": measured.get(pid),
        })

    return {
        "providers": out,
        "sources": {
            "surplus_marketplace": f"{PROVIDERS_URL} (trusted flags)",
            "market_aggregates": f"{MARKETS_URL} (models, sellers, prices; 30s cache)",
            "measured_by_surp": "provider_health.py rolling window, measured on surp-routed requests",
        },
    }
