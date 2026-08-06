"""Tests for provider health tracking, per-class free routes, free keys, streaming, conversion."""

import time

import pytest

import provider_health as ph
import free_models as fm


@pytest.fixture(autouse=True)
def fresh_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "DB_PATH", str(tmp_path / "health.db"))
    monkeypatch.setattr(ph, "_conn", None)
    monkeypatch.setattr(fm, "DB_PATH", str(tmp_path / "free.db"))
    monkeypatch.setattr(fm, "_conn", None)
    monkeypatch.setattr(fm, "DAILY_REQUEST_BUDGET", 100)
    monkeypatch.setattr(fm, "DAILY_TOKEN_BUDGET", 10000)
    monkeypatch.setattr(fm, "PER_IP_DAILY_REQUESTS", 5)
    yield


# ── provider_health: TPS, latency, failure rate ──

def test_records_success_and_computes_stats():
    ph.record("model-a", status="ok", latency_ms=100, tokens=50)
    ph.record("model-a", status="ok", latency_ms=300, tokens=100)
    stats = ph.stats("model-a")
    assert stats["requests"] == 2
    assert stats["failures"] == 0
    assert stats["tokens"] == 150
    # p50 of [100,300] interpolates to 200; p95 interpolates toward 300.
    assert stats["p50_latency_ms"] == 200
    assert stats["p95_latency_ms"] == 290
    assert stats["failure_rate"] == 0.0


def test_failure_rate_computed():
    ph.record("model-b", status="ok", latency_ms=50, tokens=10)
    ph.record("model-b", status="ok", latency_ms=50, tokens=10)
    ph.record("model-b", status="failed", latency_ms=0, tokens=0)
    stats = ph.stats("model-b")
    assert stats["requests"] == 3
    assert stats["failures"] == 1
    assert stats["failure_rate"] == pytest.approx(0.333, rel=0.01)


def test_tps_from_window():
    now = int(time.time())
    for _ in range(10):
        ph.record("model-c", status="ok", latency_ms=10, tokens=5, ts=now)
    stats = ph.stats("model-c")
    assert stats["requests"] == 10
    assert stats["tps"] >= 0  # computed within the rolling window


def test_health_score_penalizes_failures_and_slow_latency():
    ph.record("good", status="ok", latency_ms=50, tokens=10)
    ph.record("bad", status="failed", latency_ms=500, tokens=0)
    good = ph.health_score("good")
    bad = ph.health_score("bad")
    assert good > bad


def test_ranking_orders_by_composite_score():
    ph.record("fast-cheap", status="ok", latency_ms=30, tokens=10)
    ph.record("slow", status="ok", latency_ms=2000, tokens=10)
    ph.record("flakey", status="failed", latency_ms=10, tokens=0)
    ranked = ph.ranked(["fast-cheap", "slow", "flakey"])
    assert ranked[0]["model"] == "fast-cheap"
    assert ranked[-1]["model"] == "flakey"


def test_old_records_expire_outside_window():
    old = int(time.time()) - 86400 - 1
    ph.record("stale", status="ok", latency_ms=50, tokens=10, ts=old)
    ph.record("fresh", status="ok", latency_ms=50, tokens=10)
    stale_stats = ph.stats("stale")
    assert stale_stats["requests"] == 0  # expired


# ── per-class free routes ──

def test_free_coding_pool_filters_to_coding_models():
    markets = [
        {"model": "qwen3-coder", "best_price_per_1m": 10, "best_input_per_1m": 5, "best_output_per_1m": 5, "healthy_seller_count": 1, "total_cap": 100, "best_media_unit_price": None},
        {"model": "deepseek-chat", "best_price_per_1m": 5, "best_input_per_1m": 2, "best_output_per_1m": 3, "healthy_seller_count": 1, "total_cap": 100, "best_media_unit_price": None},
    ]
    pool = fm.sponsored_pool_for_class(markets, "coding")
    assert [m["model"] for m in pool] == ["qwen3-coder"]


def test_free_fast_pool_filters_to_small_models():
    markets = [
        {"model": "mini-tiny", "best_price_per_1m": 5, "best_input_per_1m": 2, "best_output_per_1m": 3, "healthy_seller_count": 1, "total_cap": 100, "best_media_unit_price": None},
        {"model": "huge-frontier", "best_price_per_1m": 5, "best_input_per_1m": 2, "best_output_per_1m": 3, "healthy_seller_count": 1, "total_cap": 100, "best_media_unit_price": None},
    ]
    pool = fm.sponsored_pool_for_class(markets, "fast")
    assert "mini" in pool[0]["model"]


# ── free-tier API keys with elevated budgets ──

def test_free_key_creation_and_validation():
    rec = fm.create_free_key("heavy-user", elevated_requests=1000, elevated_tokens=200000)
    assert rec["ok"] is True
    assert rec["tier"] == "free"
    assert rec["elevated_requests"] == 1000
    validated = fm.validate_free_key(rec["key"])
    assert validated is not None
    assert validated["label"] == "heavy-user"


def test_free_key_grants_elevated_budget(monkeypatch):
    monkeypatch.setattr(fm, "PER_IP_DAILY_REQUESTS", 5)
    rec = fm.create_free_key("power-user", elevated_requests=50, elevated_tokens=10000)
    key = rec["key"]
    # With the key, should be allowed well past the default per-IP limit.
    for _ in range(10):
        fm.record_free_key_usage(key, "model", 100, "ok")
    ok, reason = fm.can_serve_free(key, estimated_tokens=100, is_key=True)
    assert ok is True


# ── free-to-paid conversion ──

def test_conversion_tracking():
    fm.record_conversion("user-a", "free", "best-chat")
    fm.record_conversion("user-a", "free", "best-chat")
    fm.record_usage("user-a", "model", 100)
    fm.record_usage("user-a", "model", 100)
    stats = fm.conversion_stats()
    assert stats["conversions"] == 1  # deduped per user
    assert stats["free_users"] >= 1


# ── streaming budget enforcement ──

def test_streaming_blocked_when_budget_low(monkeypatch):
    monkeypatch.setattr(fm, "DAILY_TOKEN_BUDGET", 50)
    monkeypatch.setattr(fm, "MAX_OUTPUT_TOKENS", 128)
    fm.record_usage("ip1", "model", 50)
    ok, reason = fm.can_serve_free("ip1", estimated_tokens=100, is_key=False)
    assert ok is False
    assert "token" in reason.lower()
