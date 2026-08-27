"""AA catalog matching and route picker."""

import combo_resolver as cr
import aa_catalog
import aa_router


def _cat():
    return aa_catalog.catalog_from_payload({
        "fetched_at": 1,
        "intelligence_index_version": 4.1,
        "models": [
            {"slug": "cheap-ok", "name": "Cheap OK", "intelligence": 40, "tps": 50,
             "price_in": 1.0, "price_out": 1.0, "list_usd": 1.0},
            {"slug": "mid", "name": "Mid", "intelligence": 48, "tps": 80,
             "price_in": 2.0, "price_out": 2.0, "list_usd": 2.0},
            {"slug": "frontier-model", "name": "Frontier Model", "intelligence": 50, "tps": 30,
             "price_in": 10.0, "price_out": 10.0, "list_usd": 10.0},
            {"slug": "flash", "name": "Flash", "intelligence": 42, "tps": 200,
             "price_in": 0.5, "price_out": 0.5, "list_usd": 0.5},
        ],
    }, fetched_at=1, source="test")


def _row(model, usd):
    return {"model": model, "best_price_per_1m": usd * cr.PRICE_DIVISOR, "best_input_per_1m": 1, "best_output_per_1m": 1}


def _pool():
    # Surplus cheaper than AA list so discount is positive.
    return [
        _row("cheap-ok", 0.40),       # 60% off list 1.0
        _row("mid", 0.40),            # 80% off list 2.0
        _row("frontier-model", 8.00), # 20% off list 10
        _row("flash", 0.40),          # 20% off list 0.5
    ]


def test_norm_matches_dotted_surplus_ids():
    cat = aa_catalog.catalog_from_payload({
        "models": [{"slug": "claude-3-5-haiku", "name": "Claude 3.5 Haiku", "intelligence": 20}]
    }, 0, "t")
    hit = aa_catalog.match_model("anthropic/claude-3.5-haiku", cat)
    assert hit is not None
    assert hit.slug == "claude-3-5-haiku"


def test_blended_list_price_3_to_1():
    assert aa_catalog.blended_list_usd(3, 15) == 6.0


def test_value_picks_max_discount_inside_20pct_band():
    # Best intel = 50. Floor = 40. All four are in band except none drop.
    # cheap-ok 40 is exactly at floor. mid 48, frontier 50, flash 42.
    # Discounts: cheap-ok 60%, mid 80%, frontier 20%, flash 20% -> mid wins.
    p = aa_router.pick("value", _pool(), catalog=_cat())
    assert p.model == "mid"
    assert p.reason.startswith("value")
    assert p.discount_pct == 80.0


def test_value_drops_models_below_band():
    cat = aa_catalog.catalog_from_payload({
        "models": [
            {"slug": "weak", "name": "Weak", "intelligence": 10, "tps": 10, "list_usd": 5.0},
            {"slug": "strong", "name": "Strong", "intelligence": 50, "tps": 10, "list_usd": 5.0},
        ]
    }, 1, "t")
    pool = [_row("weak", 0.1), _row("strong", 2.0)]  # weak has huge discount
    p = aa_router.pick("value", pool, catalog=cat)
    assert p.model == "strong"


def test_frontier_picks_highest_intelligence():
    p = aa_router.pick("frontier", _pool(), catalog=_cat())
    assert p.model == "frontier-model"
    assert p.reason == "frontier"


def test_fast_picks_highest_tps_in_band():
    p = aa_router.pick("fast", _pool(), catalog=_cat())
    assert p.model == "flash"


def test_free_picks_highest_intelligence_then_cheap():
    p = aa_router.pick("free", _pool(), catalog=_cat())
    assert p.model == "frontier-model"


def test_custom_speed_heavy_picks_flash():
    p = aa_router.pick("custom", _pool(), catalog=_cat(), weights=(0.1, 0.1, 0.8))
    assert p.model == "flash"


def test_custom_discount_heavy_picks_mid():
    p = aa_router.pick("custom", _pool(), catalog=_cat(), weights=(0.9, 0.05, 0.05))
    assert p.model == "mid"


def test_empty_pool():
    assert aa_router.pick("value", [], catalog=_cat()) is None


def test_pool_for_fast_is_all_sellable_text():
    markets = [
        {"model": "big-reasoner", "best_price_per_1m": 2e6, "best_input_per_1m": 1,
         "best_output_per_1m": 1, "healthy_seller_count": 1, "total_cap": 1},
        {"model": "llama-mini", "best_price_per_1m": 1e6, "best_input_per_1m": 1,
         "best_output_per_1m": 1, "healthy_seller_count": 1, "total_cap": 1},
    ]
    names = {m["model"] for m in cr.pool_for("fast", markets)}
    assert names == {"big-reasoner", "llama-mini"}
    mini_only = [m["model"] for m in cr.pool_for("best-fast", markets)]
    assert mini_only == ["llama-mini"]


def test_pool_for_value_and_vision():
    markets = [
        {"model": "chat-one", "best_price_per_1m": 1e6, "best_input_per_1m": 1,
         "best_output_per_1m": 1, "healthy_seller_count": 1, "total_cap": 1},
        {"model": "qwen3-vl", "best_price_per_1m": 2e6, "best_input_per_1m": 1,
         "best_output_per_1m": 1, "healthy_seller_count": 1, "total_cap": 1},
    ]
    assert {m["model"] for m in cr.pool_for("value", markets)} == {"chat-one", "qwen3-vl"}
    assert [m["model"] for m in cr.pool_for("vision", markets)] == ["qwen3-vl"]


def test_no_aa_match_falls_back_to_cheapest():
    cat = aa_catalog.catalog_from_payload({"models": []}, 1, "t")
    pool = [_row("unknown-b", 2.0), _row("unknown-a", 0.5)]
    p = aa_router.pick("value", pool, catalog=cat)
    assert p.model == "unknown-a"
    assert "fallback" in p.reason
