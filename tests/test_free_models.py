"""Tests for OmniRoute-inspired free model catalog and surp free routing."""

import time

import pytest

import free_models as fm


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(fm, "DB_PATH", str(tmp_path / "free.db"))
    monkeypatch.setattr(fm, "_conn", None)
    monkeypatch.setattr(fm, "DAILY_REQUEST_BUDGET", 10)
    monkeypatch.setattr(fm, "DAILY_TOKEN_BUDGET", 1000)
    yield


def test_omniroute_catalog_loads_and_has_license_attribution():
    cat = fm.load_catalog()
    assert len(cat["entries"]) >= 500
    assert cat["license"] == "MIT"
    assert "OmniRoute" in cat["source"]


def test_pool_dedup_uses_max_not_sum():
    entries = [
        {"monthly_tokens": 100, "credit_tokens": 0, "free_type": "recurring-daily", "pool_key": "shared", "provider": "a", "tos": "ok"},
        {"monthly_tokens": 100, "credit_tokens": 0, "free_type": "recurring-daily", "pool_key": "shared", "provider": "a", "tos": "ok"},
        {"monthly_tokens": 50, "credit_tokens": 0, "free_type": "recurring-monthly", "pool_key": None, "provider": "b", "tos": "ok"},
    ]
    totals = fm.compute_catalog_totals(entries)
    assert totals["steady_recurring_tokens"] == 150
    assert totals["pool_count"] == 1


def test_tos_avoid_entries_are_excluded_from_safe_totals():
    entries = [
        {"monthly_tokens": 100, "credit_tokens": 0, "free_type": "recurring-daily", "pool_key": "safe", "provider": "a", "tos": "ok"},
        {"monthly_tokens": 1000, "credit_tokens": 0, "free_type": "recurring-daily", "pool_key": "bad", "provider": "b", "tos": "avoid"},
    ]
    assert fm.compute_catalog_totals(entries, exclude_tos_avoid=False)["steady_recurring_tokens"] == 1100
    assert fm.compute_catalog_totals(entries, exclude_tos_avoid=True)["steady_recurring_tokens"] == 100


def test_uncapped_providers_are_listed_but_not_summed():
    entries = [
        {"monthly_tokens": 0, "credit_tokens": 0, "free_type": "recurring-uncapped", "pool_key": "u", "provider": "uncapped", "tos": "ok"},
    ]
    totals = fm.compute_catalog_totals(entries)
    assert totals["steady_recurring_tokens"] == 0
    assert totals["uncapped_providers"] == ["uncapped"]


def test_sponsored_free_pool_only_uses_sellable_text_models():
    markets = [
        {"model":"good","best_price_per_1m":10,"best_input_per_1m":5,"best_output_per_1m":5,"healthy_seller_count":2,"total_cap":1000,"best_media_unit_price":None},
        {"model":"dead","best_price_per_1m":1,"best_input_per_1m":1,"best_output_per_1m":1,"healthy_seller_count":0,"total_cap":0,"best_media_unit_price":None},
    ]
    pool = fm.sponsored_pool(markets)
    assert [m["model"] for m in pool] == ["good"]


def test_sponsored_pool_excludes_models_above_price_ceiling(monkeypatch):
    monkeypatch.setattr(fm, "MAX_MODEL_USD_PER_1M", 0.00005)
    markets = [
        {"model":"cheap","best_price_per_1m":10,"best_input_per_1m":5,"best_output_per_1m":5,"healthy_seller_count":1,"total_cap":100,"best_media_unit_price":None},
        {"model":"expensive","best_price_per_1m":100,"best_input_per_1m":50,"best_output_per_1m":50,"healthy_seller_count":1,"total_cap":100,"best_media_unit_price":None},
    ]
    assert [m["model"] for m in fm.sponsored_pool(markets)] == ["cheap"]


def test_daily_budget_allows_then_rejects():
    assert fm.can_serve("ip1", estimated_tokens=100)[0] is True
    for _ in range(10):
        fm.record_usage("ip1", "model", 100)
    ok, reason = fm.can_serve("ip1", estimated_tokens=100)
    assert ok is False
    assert "daily" in reason


def test_usage_stats_report_requests_tokens_and_models():
    fm.record_usage("a", "model-1", 100)
    fm.record_usage("b", "model-2", 200)
    fm.record_usage("a", "model-1", 50)
    s = fm.live_stats()
    assert s["requests_today"] == 3
    assert s["tokens_today"] == 350
    assert s["top_models"][0]["model"] == "model-1"


def test_fallback_advances_after_failure():
    pool = [{"model":"a"},{"model":"b"},{"model":"c"}]
    assert fm.fallback_order(pool, failed_models={"a"})[0]["model"] == "b"
