"""The treasury-sponsored free tier is removed.

Upstream (Surplus Intelligence) offers no free API: every request carries a
real buyer cost (verified live: 0 zero-priced sellable chat models in the
book; a test call reported x-si-buyer-cost-micro > 0). The free tier was
surp subsidizing paid inference, so it is gone end to end.

Covers: no free combos resolve, no free routes/pages/endpoints served,
paid paths unchanged.
"""

import asyncio
import json
import os
import sys

from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gateway as gw
import combo_resolver as cr


FREE_MODELS = ("surp/free", "surp/srup-free", "surp/free-coding", "surp/free-fast")
FREE_COMBOS = ("free", "srup-free", "free-coding", "free-fast")


def test_free_combos_are_unregistered():
    names = cr.all_combo_names()
    for c in FREE_COMBOS:
        assert c not in names, c
        assert cr.pool_for(c, _markets()) == [], c
    # Paid combos unaffected.
    for c in ("chat", "best-chat", "value", "fast", "coding", "jev"):
        assert c in names, c


def _markets():
    return [{
        "model": "deepseek-v4-flash",
        "best_price_per_1m": 3_000,
        "best_input_per_1m": 1_000,
        "best_output_per_1m": 2_000,
        "provider": "p",
        "sellable": True,
        "total_cap": 1000,
        "healthy_seller_count": 2,
    }]


def test_free_routes_are_not_served():
    async def exercise():
        client = TestClient(TestServer(gw.build_app()))
        await client.start_server()
        try:
            out = {}
            for model in FREE_MODELS:
                resp = await client.post("/v1/chat/completions", json={
                    "model": model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 8,
                })
                body = await resp.json()
                out[model] = (resp.status, "sponsored" not in json.dumps(body).lower())
            return out
        finally:
            await client.close()

    out = asyncio.run(exercise())
    for model, (status, not_sponsored) in out.items():
        assert status == 404, (model, status)
        assert not_sponsored, model


def test_free_surfaces_are_gone():
    async def exercise():
        client = TestClient(TestServer(gw.build_app()))
        await client.start_server()
        try:
            results = {}
            results["/free-models"] = (await client.get("/free-models")).status
            results["/api/free-models"] = (await client.get("/api/free-models")).status
            resp = await client.post("/api/free-key", json={"label": "x"})
            results["/api/free-key"] = resp.status
            models = await (await client.get("/v1/models")).json()
            ids = [m.get("id") for m in models.get("data", [])]
            results["models_clean"] = not any(str(i) in FREE_MODELS for i in ids)
            combos = await (await client.get("/api/combos")).json()
            names = [c.get("combo") for c in combos.get("combos", [])]
            results["combos_clean"] = not any(
                str(n).replace("surp/", "") in FREE_COMBOS for n in names
            )
            return results
        finally:
            await client.close()

    results = asyncio.run(exercise())
    for surface in ("/free-models", "/api/free-models", "/api/free-key"):
        assert results[surface] == 404, surface
    assert results["models_clean"] is True
    assert results["combos_clean"] is True


def test_homepage_and_docs_do_not_advertise_free_inference():
    import home_page
    blob = gw._HOME_CONTENT + home_page.CONTENT
    assert "/free-models" not in blob
    assert "surp/free" not in blob
    assert "api/free-key" not in blob.lower()


def test_studio_chat_no_longer_serves_free_completions():
    import inspect
    src = inspect.getsource(gw.api_studio_chat)
    assert "_serve_free_completion" not in src


def test_health_board_page_renders():
    """Regression: page_health_board must render after free-tier removal
    (it 500'd once when hbp.content's signature changed without this path
    being covered)."""
    from aiohttp.test_utils import make_mocked_request

    app = gw.build_app()
    paths = {r.resource.canonical for r in app.router.routes()}
    assert "/health" in paths
    req = make_mocked_request("GET", "/health")
    resp = asyncio.run(gw.page_health_board(req))
    assert resp.status == 200
    assert "health board" in resp.text.lower()
    assert "free" not in resp.text.lower() or "free" in "failure"  # no free-tier copy
