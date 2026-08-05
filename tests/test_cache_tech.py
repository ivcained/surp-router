"""Tests for Surp cache innovation features."""

import json
import time

import pytest

import cache_tech as ct


def req(**overrides):
    body = {
        "model": "surp/best-chat",
        "messages": [
            {"role": "system", "content": "stable system prompt"},
            {"role": "user", "content": "hello"},
        ],
        "temperature": 0,
        "stream": False,
        "max_tokens": 64,
    }
    body.update(overrides)
    return body


def test_exact_cache_key_is_stable_for_equivalent_json():
    a = req()
    b = {"messages": a["messages"], "max_tokens": 64, "stream": False,
         "temperature": 0, "model": "surp/best-chat"}
    assert ct.request_cache_key(a) == ct.request_cache_key(b)


def test_cache_key_changes_when_prompt_changes():
    a = req()
    b = req(messages=[{"role": "user", "content": "different"}])
    assert ct.request_cache_key(a) != ct.request_cache_key(b)


def test_only_safe_deterministic_requests_are_cacheable():
    assert ct.is_response_cacheable(req()) is True
    assert ct.is_response_cacheable(req(stream=True)) is False
    assert ct.is_response_cacheable(req(temperature=0.7)) is False
    assert ct.is_response_cacheable(req(tools=[{"type": "function", "function": {"name": "x"}}])) is False
    assert ct.is_response_cacheable(req(n=2)) is False


def test_response_cache_round_trip_without_storing_prompt(tmp_path):
    db = tmp_path / "cache.db"
    cache = ct.ResponseCache(str(db), ttl_seconds=60, max_entries=10)
    payload = req(messages=[{"role": "user", "content": "PRIVATE PROMPT"}])
    key = ct.request_cache_key(payload)
    response = {"id": "abc", "choices": [{"message": {"content": "answer"}}]}
    cache.put(key, "best-chat", "model-a", response, tokens_in=10, tokens_out=2)
    hit = cache.get(key)
    assert hit["response"] == response
    assert hit["model"] == "model-a"
    raw_db = db.read_bytes()
    assert b"PRIVATE PROMPT" not in raw_db


def test_expired_cache_entries_are_not_returned(tmp_path):
    cache = ct.ResponseCache(str(tmp_path / "cache.db"), ttl_seconds=1, max_entries=10)
    key = ct.request_cache_key(req())
    cache.put(key, "best-chat", "model-a", {"ok": True})
    cache._conn.execute("UPDATE response_cache SET expires_at=?", (int(time.time()) - 1,))
    cache._conn.commit()
    assert cache.get(key) is None


def test_sticky_router_keeps_model_within_tolerance(tmp_path):
    router = ct.StickyRouter(str(tmp_path / "sticky.db"), ttl_seconds=300, tolerance_pct=30)
    markets = [
        {"model": "cheap", "best_price_per_1m": 100},
        {"model": "sticky", "best_price_per_1m": 120},
    ]
    router.remember("best-chat", "sticky")
    chosen, reason = router.choose("best-chat", markets)
    assert chosen["model"] == "sticky"
    assert reason == "sticky-within-tolerance"


def test_sticky_router_switches_when_old_model_is_too_expensive(tmp_path):
    router = ct.StickyRouter(str(tmp_path / "sticky.db"), ttl_seconds=300, tolerance_pct=30)
    markets = [
        {"model": "cheap", "best_price_per_1m": 100},
        {"model": "sticky", "best_price_per_1m": 150},
    ]
    router.remember("best-chat", "sticky")
    chosen, reason = router.choose("best-chat", markets)
    assert chosen["model"] == "cheap"
    assert reason == "live-cheapest"


def test_cache_stats_track_hits_misses_and_saved_tokens(tmp_path):
    cache = ct.ResponseCache(str(tmp_path / "cache.db"), ttl_seconds=60, max_entries=10)
    key = ct.request_cache_key(req())
    assert cache.get(key) is None
    cache.put(key, "best-chat", "model-a", {"ok": True}, tokens_in=1000, tokens_out=20)
    assert cache.get(key) is not None
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["tokens_saved"] == 1020
    assert stats["hit_rate_pct"] == 50.0
