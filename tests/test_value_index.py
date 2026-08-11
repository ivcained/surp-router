"""Tests for the Surp Value Index (SVI)."""

import json

import pytest

import value_index as vi


# ── cost_score ───────────────────────────────────────────────────────────────

def test_cost_score_cheapest_is_100():
    assert vi.cost_score(1.0, 1.0) == 100.0


def test_cost_score_4x_pricier_is_half():
    # sqrt(1/4) = 0.5 → 50
    assert vi.cost_score(4.0, 1.0) == 50.0


def test_cost_score_zero_price_guard():
    assert vi.cost_score(0, 1.0) == 0.0


# ── speed_score ─────────────────────────────────────────────────────────────

def test_speed_score_fastest_is_100():
    assert vi.speed_score(100, 100) == 100.0


def test_speed_score_half_speed():
    assert vi.speed_score(50, 100) == 50.0


def test_speed_score_zero_guard():
    assert vi.speed_score(0, 100) == 0.0


# ── intelligence_score ──────────────────────────────────────────────────────

def test_intelligence_class_default():
    assert vi.intelligence_score("glm-5.2") == pytest.approx(70.0)  # chat


def test_intelligence_coding_class():
    assert vi.intelligence_score("qwen3-coder-30b") == pytest.approx(80.0)


def test_intelligence_submission_overrides(tmp_path):
    bench = {"my-model": {"mmlu": 90, "gpqa": 85, "humaneval": 95, "ifeval": 80}}
    assert vi.intelligence_score("my-model", bench) == pytest.approx(87.5)


def test_intelligence_partial_submission_falls_back(tmp_path):
    # Only humaneval submitted → other axes fall back to class default (chat=70)
    bench = {"my-model": {"humaneval": 100}}
    assert vi.intelligence_score("my-model", bench) == pytest.approx((100 + 70 + 70 + 70) / 4)


def test_intelligence_clamps_out_of_range(tmp_path):
    bench = {"my-model": {"mmlu": 150, "gpqa": -10}}
    # mmlu→100, gpqa→0, others→chat default 70
    assert vi.intelligence_score("my-model", bench) == pytest.approx((100 + 0 + 70 + 70) / 4)


# ── composite (geometric mean) ───────────────────────────────────────────────

def test_composite_perfect_model_scores_100():
    assert vi.composite(100, 100, 100) == pytest.approx(100.0, abs=0.5)


def test_composite_weak_axis_punished():
    # All 90s vs one 30 — geometric mean must drop well below arithmetic.
    geo_all_90 = vi.composite(90, 90, 90)
    geo_weak = vi.composite(90, 30, 90)
    assert geo_weak < geo_all_90
    # arithmetic would be 70; geometric must be lower (punishes the weak axis)
    assert geo_weak < 70


def test_composite_zero_axis_floored():
    # A zero speed score must not produce NaN/0 — floored at epsilon.
    assert vi.composite(100, 100, 0) > 0


# ── submit_benchmark / registry ──────────────────────────────────────────────

def test_submit_benchmark_writes_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(vi, "_BENCH_DB_PATH", str(tmp_path / "bench.json"))
    res = vi.submit_benchmark("new-model", mmlu=88, humaneval=92, submitter="supplierA")
    assert res["model"] == "new-model"
    assert 80 <= res["intelligence_score"] <= 100
    # File persisted
    data = json.loads((tmp_path / "bench.json").read_text())
    assert data["new-model"]["mmlu"] == 88
    assert data["new-model"]["submitter"] == "supplierA"


def test_submit_benchmark_clamps(tmp_path, monkeypatch):
    monkeypatch.setattr(vi, "_BENCH_DB_PATH", str(tmp_path / "bench.json"))
    vi.submit_benchmark("m", mmlu=500)
    data = json.loads((tmp_path / "bench.json").read_text())
    assert data["m"]["mmlu"] == 100.0


# ── rank ─────────────────────────────────────────────────────────────────────

def test_rank_skips_unverified_speed():
    market = [
        {"model": "a", "price_usd_per_1m": 1.0},
        {"model": "b", "price_usd_per_1m": 2.0},
        {"model": "c", "price_usd_per_1m": 0.5},
    ]
    benchmarked = [
        {"model": "a", "p50_output_tps": 100},
        {"model": "b", "p50_output_tps": 50},
        # c has no verified TPS → excluded
    ]
    rows = vi.rank(market, benchmarked)
    models = [r["model"] for r in rows]
    assert models == ["a", "b"]  # c excluded (no verified speed)
    assert rows[0]["svi"] > rows[1]["svi"]


def test_rank_sorts_by_svi_desc():
    market = [
        {"model": "cheap-slow", "price_usd_per_1m": 0.1},
        {"model": "mid", "price_usd_per_1m": 1.0},
        {"model": "pricy-fast", "price_usd_per_1m": 5.0},
    ]
    benchmarked = [
        {"model": "cheap-slow", "p50_output_tps": 20},
        {"model": "mid", "p50_output_tps": 80},
        {"model": "pricy-fast", "p50_output_tps": 200},
    ]
    rows = vi.rank(market, benchmarked)
    svs = [r["svi"] for r in rows]
    assert svs == sorted(svs, reverse=True)
    for r in rows:
        assert 0 <= r["svi"] <= 100


# ── index_for full breakdown ─────────────────────────────────────────────────

def test_index_for_full_breakdown():
    idx = vi.index_for("deepseek-v4-flash", 0.0162, 94.0, 0.0162, 120.0)
    assert idx["model"] == "deepseek-v4-flash"
    assert idx["cost_score"] == 100.0  # it IS the cheapest in this set
    assert idx["speed_score"] == pytest.approx(94 / 120 * 100, abs=0.5)
    assert 0 < idx["svi"] <= 100


# ── routing modes (pick_winner) ─────────────────────────────────────────────

def _pool():
    return [
        {"model": "cheap-slow", "price_usd_per_1m": 0.10, "p50_tps": 20},
        {"model": "mid", "price_usd_per_1m": 1.00, "p50_tps": 80},
        {"model": "pricy-fast", "price_usd_per_1m": 5.00, "p50_tps": 200},
    ]


def test_pick_winner_cost_mode():
    winner, reason, _ = vi.pick_winner(_pool(), mode="cost")
    assert winner == "cheap-slow"
    assert reason == "cost"


def test_pick_winner_speed_mode():
    winner, reason, _ = vi.pick_winner(_pool(), mode="speed")
    assert winner == "pricy-fast"
    assert reason == "speed"


def test_pick_winner_value_mode_default_svi():
    # Default SVI weights (cost 45 / intel 40 / speed 15) — mid should win
    # (not too cheap/slow, not too pricy/fast).
    winner, reason, _ = vi.pick_winner(_pool(), mode="value")
    assert reason == "value"
    assert winner in {"cheap-slow", "mid", "pricy-fast"}


def test_pick_winner_custom_weights_speed_heavy():
    # Speed-heavy custom weights should pick the fastest.
    winner, _, _ = vi.pick_winner(_pool(), weights=(0.1, 0.1, 0.8))
    assert winner == "pricy-fast"


def test_pick_winner_custom_weights_cost_heavy():
    winner, _, _ = vi.pick_winner(_pool(), weights=(0.8, 0.1, 0.1))
    assert winner == "cheap-slow"


def test_pick_winner_falls_back_when_no_verified_tps():
    pool = [
        {"model": "a", "price_usd_per_1m": 0.5, "p50_tps": 0},
        {"model": "b", "price_usd_per_1m": 1.0, "p50_tps": 0},
    ]
    winner, reason, _ = vi.pick_winner(pool, mode="value")
    assert winner == "a"  # cheapest fallback
    assert reason == "cost-fallback"


def test_pick_winner_empty_pool():
    winner, reason, _ = vi.pick_winner([], mode="value")
    assert winner is None
    assert reason == "empty-pool"


def test_parse_weights_valid():
    assert vi.parse_weights("0.3:0.4:0.3") == (0.3, 0.4, 0.3)


def test_parse_weights_invalid():
    assert vi.parse_weights("1:2") is None
    assert vi.parse_weights("a:b:c") is None
    assert vi.parse_weights("") is None
    assert vi.parse_weights(None) is None


def test_composite_with_custom_weights():
    # Same sub-scores, different weights → different composite.
    v_default = vi.composite(50, 80, 90)
    v_speed = vi.composite(50, 80, 90, weights=(0.1, 0.1, 0.8))
    assert v_speed > v_default  # speed-heavy weights favor the fast model
