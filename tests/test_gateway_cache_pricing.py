"""Regression tests for gateway-level cache pricing and observability."""

import asyncio
import json

from aiohttp.test_utils import TestClient, TestServer

import cache_tech as ct
import gateway as gw


def test_payment_required_accepts_exact_cache_hit_amount():
    """A 0.1¢ cache hit must not be raised to the normal 1¢ floor."""
    amount_microcents = int(gw.CACHE_HIT_CENTS * 10_000)
    quote = gw._build_payment_required(
        "best-chat",
        "cached-model",
        1_000_000,
        8,
        routing_reason="cache-hit",
        required_microcents=amount_microcents,
        cache_status="HIT",
    )

    accepted = quote["body"]["accepts"][0]
    assert accepted["amount"] == "1000"  # USDC has six decimals: $0.001
    assert quote["body"]["price_usd"] == "$0.0010"
    assert quote["body"]["cache_status"] == "HIT"
    assert quote["headers"]["X-Surp-Cache"] == "HIT"


def test_unpaid_cached_request_quotes_discount_without_upstream_spend(tmp_path, monkeypatch):
    """The live HTTP path should detect a seeded hit before payment and quote 0.1¢."""
    cache = ct.ResponseCache(str(tmp_path / "cache.db"), ttl_seconds=60, max_entries=10)
    monkeypatch.setattr(gw, "_RESPONSE_CACHE", cache)
    # Keep the regression deterministic and independent of Surplus market
    # availability. The cache path still resolves the combo before quoting.
    monkeypatch.setattr(gw.GCACHE, "get", lambda: _markets())
    monkeypatch.setattr(
        gw,
        "resolve_combo",
        lambda combo, markets, strategy=None: ("cached-model", {}, 1_000_000, markets),
    )
    monkeypatch.setattr(gw.cr, "pool_for", lambda combo, markets: markets)

    payload = {
        "model": "surp/best-chat",
        "messages": [{"role": "user", "content": "gateway cache price regression"}],
        "temperature": 0,
        "stream": False,
        "max_tokens": 8,
    }
    cache.put(
        ct.request_cache_key(payload),
        "best-chat",
        "cached-model",
        {
            "id": "cached-test",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "cached"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        },
        tokens_in=3,
        tokens_out=1,
    )

    async def exercise():
        client = TestClient(TestServer(gw.build_app()))
        await client.start_server()
        try:
            response = await client.post("/v1/chat/completions", json=payload)
            body = await response.json()
            return response.status, dict(response.headers), body
        finally:
            await client.close()

    status, headers, body = asyncio.run(exercise())
    assert status == 402
    assert body["accepts"][0]["amount"] == "1000"
    assert body["price_usd"] == "$0.0010"
    assert body["cache_status"] == "HIT"
    assert headers["X-Surp-Cache"] == "HIT"


def _markets():
    async def result():
        return [{
            "model": "cached-model",
            "best_price_per_1m": 1_000_000,
            "provider": "test-provider",
            "sellable": True,
            "media_type": "text",
        }]
    return result()


def test_cache_stats_expose_current_configuration_and_window(tmp_path):
    cache = ct.ResponseCache(str(tmp_path / "cache.db"), ttl_seconds=900, max_entries=5000)
    stats = cache.stats()

    assert stats["ttl_seconds"] == 900
    assert stats["ttl_minutes"] == 15
    assert stats["max_entries"] == 5000
    assert "oldest_live_entry_age_seconds" in stats
    assert "historical_lookups" in stats


def test_cache_key_ignores_gateway_transport_controls_but_not_generation_inputs():
    base = {
        "model": "surp/best-chat",
        "messages": [{"role": "user", "content": "same semantic request"}],
        "temperature": 0,
        "stream": False,
        "max_tokens": 32,
    }
    with_controls = {
        **base,
        "surp_bypass_cache": True,
        "surp_mode": "cost",
        "surp_weights": "1:2:3",
        "max_price_per_1m": 0.5,
    }
    assert ct.request_cache_key(base) == ct.request_cache_key(with_controls)

    changed_output = {**base, "response_format": {"type": "json_object"}}
    assert ct.request_cache_key(base) != ct.request_cache_key(changed_output)