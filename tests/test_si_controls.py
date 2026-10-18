"""SI routing controls, market/performance proxies, and whitelabel buyer-cost ledger.

Covers:
- si_intel: TTL-cached /api/markets, per-model market, performance analytics, providers merge
- gateway: routing-control validation (providers_blocked / provider_order / si_route), X-SI header
  forwarding, x-si-* response header surfacing, buyer-cost ledger recording
- user_accounts: buyer_cost_cents column, usage rows, dashboard aggregate
- provider_health: per-provider aggregation
- proxy: X-SI request-header passthrough and x-si-* response allowlist
"""

import asyncio
import json
import os
import sqlite3
import sys
import time
import types
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── fakes ────────────────────────────────────────────────────────────────────

FAKE_MARKET = {
    "model": "deepseek-v4-flash",
    "best_price_per_1m": 2628,
    "best_input_per_1m": 876,
    "best_output_per_1m": 1752,
    "healthy_seller_count": 54,
    "num_sellers": 36,
    "tps_p50": 54.3,
    "ttft_p50_ms": 3043,
    "uptime_pct": 99.0,
    "providers": [
        {"provider": "inferhub", "trusted": False, "best_price_per_1m": 2628,
         "healthy_seller_count": 17},
        {"provider": "venice", "trusted": True, "best_price_per_1m": 119700,
         "healthy_seller_count": 20},
    ],
}

FAKE_PROVIDERS = {"data": [
    {"id": "venice", "name": "Venice AI", "host": "api.venice.ai", "trusted": True},
    {"id": "inferhub", "name": "InferHub", "host": "inferhub.ai", "trusted": False},
]}

FAKE_PERF = {"model": "deepseek-v4-flash", "providers": [
    {"provider": "inferhub", "tps_p50": 54.3, "ttft_p50_ms": 3043, "uptime_pct": 99.7},
]}


def _fake_fetch(url, headers=None, timeout=20):
    async def run():
        if "/api/markets" in url:
            return 200, {"markets": [dict(FAKE_MARKET)]}
        if "/v1/providers" in url:
            return 200, FAKE_PROVIDERS
        if "/api/analytics/performance/" in url:
            return 200, FAKE_PERF
        return 404, {"error": "not found"}
    return run()


# ── si_intel ─────────────────────────────────────────────────────────────────

def test_si_intel_markets_cached_with_metadata(monkeypatch):
    import si_intel
    calls = {"n": 0}

    def fetch(url, **kw):
        calls["n"] += 1
        return _fake_fetch(url, **kw)

    monkeypatch.setattr(si_intel, "_fetch_json", fetch)
    out = asyncio.run(si_intel.markets())
    assert out["count"] == 1
    assert out["markets"][0]["model"] == "deepseek-v4-flash"
    assert out["cached_at"] > 0
    assert 0 <= out["age_seconds"] <= 2
    # Second call within TTL must not refetch.
    asyncio.run(si_intel.markets())
    assert calls["n"] == 1


def test_si_intel_market_for_returns_model_or_none(monkeypatch):
    import si_intel
    monkeypatch.setattr(si_intel, "_fetch_json", lambda url, **kw: _fake_fetch(url, **kw))
    m = asyncio.run(si_intel.market_for("deepseek-v4-flash"))
    assert m["model"] == "deepseek-v4-flash"
    assert any(p["provider"] == "venice" for p in m["providers"])
    assert asyncio.run(si_intel.market_for("no-such-model")) is None


def test_si_intel_performance_cached(monkeypatch):
    import si_intel
    calls = {"n": 0}

    def fetch(url, **kw):
        calls["n"] += 1
        return _fake_fetch(url, **kw)

    monkeypatch.setattr(si_intel, "_fetch_json", fetch)
    status, body = asyncio.run(si_intel.performance("deepseek-v4-flash"))
    assert status == 200
    assert body["model"] == "deepseek-v4-flash"
    asyncio.run(si_intel.performance("deepseek-v4-flash"))
    assert calls["n"] == 1


def test_si_intel_providers_merges_trusted_and_market_aggregates(monkeypatch):
    import si_intel
    monkeypatch.setattr(si_intel, "_fetch_json", lambda url, **kw: _fake_fetch(url, **kw))

    measured = {"venice": {"requests": 10, "failures": 1, "failure_rate": 0.1,
                           "p50_latency_ms": 1500, "tokens": 500}}
    monkeypatch.setattr(si_intel, "_measured_provider_stats", lambda: measured)

    out = asyncio.run(si_intel.providers())
    by_id = {p["id"]: p for p in out["providers"]}
    assert by_id["venice"]["trusted"] is True
    assert by_id["inferhub"]["trusted"] is False
    assert by_id["venice"]["market"]["models"] == 1          # from market aggregates
    assert by_id["inferhub"]["market"]["min_best_price_per_1m"] == 2628
    assert by_id["venice"]["measured"]["requests"] == 10
    assert "surplus_marketplace" in out["sources"] and "measured_by_surp" in out["sources"]


# ── provider_health aggregation ──────────────────────────────────────────────

def test_provider_health_provider_stats_groups_by_provider(tmp_path, monkeypatch):
    import provider_health as ph
    monkeypatch.setattr(ph, "DB_PATH", str(tmp_path / "ph.db"))
    ph._conn = None
    now = int(time.time())
    ph.record("m1", status="ok", latency_ms=100, tokens=10, provider="venice", ts=now - 5)
    ph.record("m1", status="failed", latency_ms=0, tokens=0, provider="venice", ts=now - 4)
    ph.record("m2", status="ok", latency_ms=200, tokens=20, provider="inferhub", ts=now - 3)
    stats = ph.provider_stats(window_seconds=3600)
    assert stats["venice"]["requests"] == 2
    assert stats["venice"]["failures"] == 1
    assert stats["venice"]["failure_rate"] == 0.5
    assert stats["venice"]["models"] == 1
    assert stats["inferhub"]["requests"] == 1
    assert stats["inferhub"]["models"] == 1


# ── user_accounts buyer-cost ledger ──────────────────────────────────────────

def test_usage_ledger_records_buyer_cost_cents(tmp_path, monkeypatch):
    import user_accounts as ua
    monkeypatch.setattr(ua, "_DB_PATH", str(tmp_path / "users.db"))
    ua._init_db()
    ua.upsert_user("privy-user-1", "0x" + "11" * 20, "a@example.com")
    uid = "privy-user-1"
    key = ua.create_api_key(uid, "test", budget_cents=100)
    assert key is not None
    ua.log_usage(uid, key["key_id"], "surp/best-chat", 10, 5, 3, "0xabc",
                 buyer_cost_cents=2)
    rows = ua.get_usage(uid)
    assert rows and rows[0]["buyer_cost_cents"] == 2
    stats = ua.get_dashboard_stats(uid)
    assert stats["buyer_cost_cents"] == 2
    assert stats["buyer_cost_usd"] == 0.02


def test_buyer_cost_micro_to_cents_conversion():
    import gateway as gw
    assert gw._buyer_cost_cents({"x-si-buyer-cost-micro": "12500"}) == 1
    assert gw._buyer_cost_cents({}) == 0
    assert gw._buyer_cost_cents({"x-si-buyer-cost-micro": "garbage"}) == 0


# ── gateway routing-control validation ───────────────────────────────────────

def test_routing_controls_accept_valid_shapes():
    import gateway as gw
    payload = {
        "providers_blocked": ["openrouter"],
        "provider_order": ["venice", "openai"],
        "provider": "zai",
        "si_route": {"objective": "latency", "price_tolerance_pct": 15},
    }
    assert gw._validate_si_controls(payload) is None


def test_routing_controls_reject_bad_shapes():
    import gateway as gw
    for bad in (
        {"providers_blocked": {"venice": True}},      # dict, SI refuses
        {"providers_blocked": [1, 2]},                 # non-strings
        {"provider_order": "venice"},                  # bare string is allowed by SI? order must be list
        {"si_route": "latency"},                       # not an object
        {"si_route": {"objective": 42}},               # non-string objective
        {"providers_blocked": ["p%d" % i for i in range(33)]},  # > 32 entries
    ):
        err = gw._validate_si_controls(bad)
        assert err is not None, bad
        assert err["error"]["type"] == "invalid_request"


def test_gateway_si_header_forwarding_allowlists():
    import gateway as gw
    inbound = {
        "X-SI-Mask-Secrets": "on",
        "X-SI-Route-Objective": "latency",
        "X-SI-Route-Tolerance-Pct": "15",
        "Authorization": "Bearer surp_x",
        "X-Evil": "drop me",
    }
    fwd = gw._si_request_headers(inbound)
    assert fwd == {
        "X-SI-Mask-Secrets": "on",
        "X-SI-Route-Objective": "latency",
        "X-SI-Route-Tolerance-Pct": "15",
    }


def test_gateway_si_response_header_surfacing():
    import gateway as gw
    upstream = {
        "Content-Type": "application/json",
        "x-si-served-by": "marketplace",
        "x-si-attempts": "inferhub:off1:timeout",
        "x-si-buyer-cost-micro": "12500",
        "x-ratelimit-limit": "1200",   # not in allowlist
        "X-Request-Id": "abc",
    }
    out = gw._si_response_headers(upstream)
    assert out["x-si-served-by"] == "marketplace"
    assert out["x-si-buyer-cost-micro"] == "12500"
    assert "x-ratelimit-limit" not in out
    assert "Content-Type" not in out


# ── proxy passthrough ────────────────────────────────────────────────────────

def test_proxy_forwards_si_request_headers():
    import proxy
    fwd = proxy._si_passthrough_headers({
        "X-SI-Mask-Secrets": "on",
        "X-SI-Route-Objective": "latency",
        "X-Something-Else": "x",
    })
    assert fwd == {"X-SI-Mask-Secrets": "on", "X-SI-Route-Objective": "latency"}


def test_proxy_response_allowlist_includes_si_telemetry():
    import proxy
    out = proxy._si_response_allowlist({
        "content-type": "application/json",
        "x-si-served-by": "marketplace",
        "x-si-buyer-cost-micro": "999",
        "x-ratelimit-remaining": "5",
    })
    assert out["x-si-served-by"] == "marketplace"
    assert out["x-si-buyer-cost-micro"] == "999"
    assert "x-ratelimit-remaining" not in out
    assert "content-type" in out


# ── gateway endpoint registration and behavior ──────────────────────────────

def test_new_api_routes_registered():
    import gateway as gw
    app = gw.build_app()
    paths = {r.resource.canonical for r in app.router.routes()}
    for p in ("/api/markets", "/api/markets/{model}", "/api/performance/{model}", "/api/providers"):
        assert p in paths, p


def test_api_markets_endpoint_serves_cache(monkeypatch):
    import gateway as gw
    import si_intel
    from aiohttp.test_utils import make_mocked_request

    monkeypatch.setattr(si_intel, "markets", lambda: _async({
        "count": 1, "cached_at": 1, "age_seconds": 0, "markets": [FAKE_MARKET],
    }))
    req = make_mocked_request("GET", "/api/markets")
    resp = asyncio.run(gw.api_markets(req))
    assert resp.status == 200
    body = json.loads(resp.text)
    assert body["count"] == 1
    assert body["markets"][0]["model"] == "deepseek-v4-flash"


def test_api_markets_model_found_and_404(monkeypatch):
    import gateway as gw
    import si_intel
    from aiohttp.test_utils import make_mocked_request

    async def fake_get(model):
        return dict(FAKE_MARKET) if model == "deepseek-v4-flash" else None

    monkeypatch.setattr(si_intel, "market_for", fake_get)
    req = make_mocked_request("GET", "/api/markets/deepseek-v4-flash")
    req._match_info = {"model": "deepseek-v4-flash"}
    resp = asyncio.run(gw.api_markets_model(req))
    assert resp.status == 200
    body = json.loads(resp.text)
    assert body["market"]["model"] == "deepseek-v4-flash"
    req404 = make_mocked_request("GET", "/api/markets/none")
    req404._match_info = {"model": "none"}
    resp404 = asyncio.run(gw.api_markets_model(req404))
    assert resp404.status == 404


def test_api_performance_endpoint_proxies(monkeypatch):
    import gateway as gw
    import si_intel
    from aiohttp.test_utils import make_mocked_request

    async def fake_perf(model):
        return 200, dict(FAKE_PERF)

    monkeypatch.setattr(si_intel, "performance", fake_perf)
    req = make_mocked_request("GET", "/api/performance/deepseek-v4-flash")
    req._match_info = {"model": "deepseek-v4-flash"}
    resp = asyncio.run(gw.api_performance_model(req))
    assert resp.status == 200
    body = json.loads(resp.text)
    assert body["model"] == "deepseek-v4-flash"
    assert body["providers"][0]["tps_p50"] == 54.3


def test_api_providers_endpoint_merges(monkeypatch):
    import gateway as gw
    import si_intel
    from aiohttp.test_utils import make_mocked_request

    monkeypatch.setattr(si_intel, "providers", lambda: _async({
        "providers": [{"id": "venice", "trusted": True}], "sources": {},
    }))
    resp = asyncio.run(gw.api_providers(make_mocked_request("GET", "/api/providers")))
    assert resp.status == 200
    body = json.loads(resp.text)
    assert body["providers"][0]["id"] == "venice"


def _async(value):
    async def run():
        return value
    return run()
