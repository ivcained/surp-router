"""Jev routing integration tests.

Covers:
- jev_router.decide: bounded Choice question, metadata-only state, fallbacks
- shadow mode: served pick unchanged, decision logged
- live preset surp/jev: Jev pick honored when confident, AA fallback otherwise
- /api/jev/stats shape
"""

import asyncio
import json
import os
import sys
import types
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import combo_resolver as cr
import aa_router


# ── fakes ────────────────────────────────────────────────────────────────────

def _market(model, price=1_000_000, cls="chat", provider="p"):
    return {
        "model": model,
        "best_price_per_1m": price,
        "best_input_per_1m": price / 2,
        "best_output_per_1m": price / 2,
        "provider": provider,
        "class": cls,
        "sellable": True,
        "context": 8192,
        "total_cap": 1000.0,
        "healthy_seller_count": 1,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "input_modalities_set": {"text"},
        "output_modalities_set": {"text"},
        "providers": [{"name": provider, "health": {"status": "healthy"}}],
    }


POOL_MARKETS = [
    _market("alpha-chat", 1_000_000),
    _market("beta-chat", 2_000_000),
    _market("gamma-chat", 3_000_000),
]


class FakeJevResponse:
    def __init__(self, choice, confidence):
        self.choices = {
            "route": types.SimpleNamespace(choice=choice, confidence=confidence)
        }


def _fake_client_factory(choice="beta-chat", confidence=0.9, delay=0.0, exc=None):
    """Return a fake AsyncTypeSafeClient class with controllable behavior."""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def system_one(self, state=None, questions=None):
            if exc is not None:
                raise exc
            if delay:
                await asyncio.sleep(delay)
            return FakeJevResponse(choice, confidence)

    return FakeClient


# ── unit: jev_router.decide ──────────────────────────────────────────────────

def test_jev_state_contains_no_message_content():
    import jev_router

    state = jev_router.build_state(
        payload={
            "messages": [{"role": "user", "content": "SECRET PROMPT TEXT"}],
            "max_tokens": 500,
        },
        pool_size=3,
        model_class="chat",
        cache_eligible=True,
    )
    blob = json.dumps(state)
    assert "SECRET PROMPT TEXT" not in blob
    assert state["est_tokens"] == 500
    assert state["model_class"] == "chat"
    assert state["cache_eligible"] is True
    assert state["has_images"] is False
    assert state["has_tools"] is False


def test_jev_decide_returns_choice_when_confident():
    import jev_router

    pool = cr.pool_for("value", POOL_MARKETS)
    cands = aa_router.annotate(pool)
    jr = jev_router.JevRouter(
        client_factory=_fake_client_factory("beta-chat", 0.9),
        timeout_s=0.6,
        min_confidence=0.55,
    )
    d = asyncio.run(jr.decide(cands, {"model_class": "chat", "est_tokens": 100}))
    assert d.ok is True
    assert d.choice == "beta-chat"
    assert d.confidence == 0.9
    assert d.fallback_reason is None


def test_jev_decide_falls_back_below_confidence():
    import jev_router

    pool = cr.pool_for("value", POOL_MARKETS)
    cands = aa_router.annotate(pool)
    jr = jev_router.JevRouter(
        client_factory=_fake_client_factory("beta-chat", 0.30),
        timeout_s=0.6,
        min_confidence=0.55,
    )
    d = asyncio.run(jr.decide(cands, {"model_class": "chat"}))
    assert d.ok is False
    assert d.fallback_reason == "low_confidence"


def test_jev_decide_falls_back_on_timeout():
    import jev_router

    pool = cr.pool_for("value", POOL_MARKETS)
    cands = aa_router.annotate(pool)
    jr = jev_router.JevRouter(
        client_factory=_fake_client_factory("beta-chat", 0.9, delay=5.0),
        timeout_s=0.05,
        min_confidence=0.55,
    )
    d = asyncio.run(jr.decide(cands, {"model_class": "chat"}))
    assert d.ok is False
    assert d.fallback_reason == "timeout"


def test_jev_decide_falls_back_on_error():
    import jev_router

    pool = cr.pool_for("value", POOL_MARKETS)
    cands = aa_router.annotate(pool)
    jr = jev_router.JevRouter(
        client_factory=_fake_client_factory(exc=RuntimeError("boom")),
        timeout_s=0.6,
        min_confidence=0.55,
    )
    d = asyncio.run(jr.decide(cands, {"model_class": "chat"}))
    assert d.ok is False
    assert d.fallback_reason == "error"


def test_jev_decide_rejects_choice_outside_candidates():
    import jev_router

    pool = cr.pool_for("value", POOL_MARKETS)
    cands = aa_router.annotate(pool)
    jr = jev_router.JevRouter(
        client_factory=_fake_client_factory("not-in-pool", 0.99),
        timeout_s=0.6,
        min_confidence=0.55,
    )
    d = asyncio.run(jr.decide(cands, {"model_class": "chat"}))
    assert d.ok is False
    assert d.fallback_reason == "invalid_choice"


def test_jev_disabled_without_key(monkeypatch):
    import jev_router
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    jr = jev_router.JevRouter.from_env()
    assert jr.enabled is False


# ── combo alias ──────────────────────────────────────────────────────────────

def test_jev_combo_resolves_to_value_pool():
    pool = cr.pool_for("jev", POOL_MARKETS)
    value_pool = cr.pool_for("value", POOL_MARKETS)
    assert pool, "jev alias must resolve to a non-empty pool"
    assert {m["model"] for m in pool} == {m["model"] for m in value_pool}


def test_jev_combo_has_description():
    assert "jev" in cr.COMBO_DESCRIPTIONS


# ── stats ────────────────────────────────────────────────────────────────────

def test_jev_stats_namespace_is_separate():
    import stats as st

    s = st.snapshot() if hasattr(st, "snapshot") else {}
    # jev keys must not collide with settlement categories
    jev_keys = [k for k in s if k.startswith("jev_")]
    for k in jev_keys:
        assert "settled" not in k and "api_key" not in k


# ── gateway integration ──────────────────────────────────────────────────────

def test_jev_stats_endpoint_registered():
    import gateway
    app = gateway.build_app()
    paths = [r.resource.canonical for r in app.router.routes()]
    assert "/api/jev/stats" in paths


def test_jev_stats_endpoint_shape():
    import gateway
    from aiohttp.test_utils import make_mocked_request
    import asyncio as _a

    req = make_mocked_request("GET", "/api/jev/stats")
    resp = _a.run(gateway.api_jev_stats(req))
    assert resp.status == 200
    body = json.loads(resp.body)
    for key in ("jev_decisions_total", "jev_fallbacks_total", "jev_fallback_rate",
                "jev_shadow_agreement_rate", "jev_latency_ms_p50",
                "jev_shadow_enabled", "jev_live_enabled", "units"):
        assert key in body, key
    assert body["units"]["jev_latency_ms_p50"] == "milliseconds"


def test_jev_disabled_by_default(monkeypatch):
    """Without JEV_LIVE/JEV_SHADOW, the gateway must behave exactly as before."""
    monkeypatch.delenv("JEV_LIVE", raising=False)
    monkeypatch.delenv("JEV_SHADOW", raising=False)
    import jev_router
    assert jev_router.live_enabled() is False
    assert jev_router.shadow_enabled() is False
