"""Tests for cache-affinity tracking and auction-style routing."""

import pytest

import cache_affinity as ca


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "DB_PATH", str(tmp_path / "affinity.db"))
    monkeypatch.setattr(ca, "_conn", None)
    yield


def test_prefix_hash_is_deterministic_and_private():
    h1 = ca.prefix_hash("system prompt", "user message part 1")
    h2 = ca.prefix_hash("system prompt", "user message part 1")
    h3 = ca.prefix_hash("system prompt", "user message part 2")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 16
    assert "system" not in h1  # no plaintext leakage


def test_records_sample_and_computes_affinity():
    # Provider serves prefix P with very low latency → high cache affinity.
    ca.record_sample("prefix-A", "model-1", tokens=1000, latency_ms=50)
    ca.record_sample("prefix-A", "model-1", tokens=1000, latency_ms=55)
    aff = ca.affinity("prefix-A", "model-1")
    assert aff["samples"] == 2
    assert aff["inferred_cache_hit"] is True
    assert aff["affinity_score"] >= 0.8


def test_fresh_compute_has_low_affinity():
    # High latency per token → no cache hit.
    ca.record_sample("prefix-B", "model-1", tokens=2000, latency_ms=3000)
    aff = ca.affinity("prefix-B", "model-1")
    assert aff["inferred_cache_hit"] is False
    assert aff["affinity_score"] < 0.3


def test_mixed_samples_blend_toward_moderate():
    ca.record_sample("prefix-C", "model-1", tokens=1000, latency_ms=50)   # cached
    ca.record_sample("prefix-C", "model-1", tokens=1000, latency_ms=2000)  # fresh
    aff = ca.affinity("prefix-C", "model-1")
    assert 0.2 < aff["affinity_score"] < 0.8


def test_ranking_prefers_high_affinity_provider():
    ca.record_sample("prefix-D", "model-good", tokens=1000, latency_ms=50)
    ca.record_sample("prefix-D", "model-slow", tokens=1000, latency_ms=3000)
    ranked = ca.rank_for_prefix("prefix-D", ["model-good", "model-slow"])
    assert ranked[0]["model"] == "model-good"
    assert ranked[0]["affinity_score"] > ranked[1]["affinity_score"]


def test_proposed_bid_lower_for_cached_provider():
    # A provider with cache affinity should bid lower than list price.
    ca.record_sample("prefix-E", "model-cached", tokens=1000, latency_ms=50)
    ca.record_sample("prefix-E", "model-cached", tokens=1000, latency_ms=55)
    ca.record_sample("prefix-E", "model-fresh", tokens=1000, latency_ms=3000)
    ca.record_sample("prefix-E", "model-fresh", tokens=1000, latency_ms=3100)
    cached_bid = ca.proposed_bid("prefix-E", "model-cached", list_price_atomic=10000)
    fresh_bid = ca.proposed_bid("prefix-E", "model-fresh", list_price_atomic=10000)
    assert cached_bid < fresh_bid
    assert cached_bid < 10000  # cached provider discounts below list


def test_unknown_prefix_returns_neutral_bid():
    bid = ca.proposed_bid("unknown-prefix", "model-x", list_price_atomic=10000)
    assert bid == 10000  # no data → bid at list


def test_dishonest_bidder_detected_by_latency():
    # Provider claims cache (low bid) but latency proves fresh compute.
    ca.record_sample("prefix-F", "liar", tokens=1000, latency_ms=3000)
    ca.record_sample("prefix-F", "liar", tokens=1000, latency_ms=3100)
    aff = ca.affinity("prefix-F", "liar")
    assert aff["inferred_cache_hit"] is False
    # The proposed bid should NOT discount because latency doesn't support cache.
    bid = ca.proposed_bid("prefix-F", "liar", list_price_atomic=10000)
    assert bid == 10000


def test_global_stats_report_prefixes_and_models():
    ca.record_sample("prefix-G", "model-1", tokens=1000, latency_ms=50)
    ca.record_sample("prefix-H", "model-2", tokens=2000, latency_ms=100)
    s = ca.global_stats()
    assert s["distinct_prefixes"] >= 2
    assert s["distinct_models"] >= 2
    assert s["total_samples"] >= 2
