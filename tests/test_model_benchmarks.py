"""Tests for LLM generation-throughput benchmarking and aggregation."""

import pytest

import model_benchmarks as mb


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(mb, "DB_PATH", str(tmp_path / "bench.db"))
    monkeypatch.setattr(mb, "_conn", None)
    yield


def test_calculate_output_tps():
    assert mb.output_tps(output_tokens=100, generation_seconds=1.0) == 100.0
    assert mb.output_tps(output_tokens=50, generation_seconds=2.0) == 25.0


def test_output_tps_handles_zero_and_negative():
    assert mb.output_tps(100, 0) == 0.0
    assert mb.output_tps(0, 1) == 0.0
    assert mb.output_tps(-1, 1) == 0.0


def test_record_and_summary_percentiles():
    mb.record("model-a", ttft_ms=100, wall_ms=1100, output_tokens=100,
              generation_ms=1000, price_usd_per_1m=0.10, status="ok")
    mb.record("model-a", ttft_ms=200, wall_ms=2200, output_tokens=200,
              generation_ms=2000, price_usd_per_1m=0.10, status="ok")
    s = mb.summary("model-a")
    assert s["successful_runs"] == 2
    assert s["p50_output_tps"] == 100.0
    assert s["p50_ttft_ms"] == 150
    assert s["p95_ttft_ms"] == 195


def test_failed_runs_excluded_from_throughput():
    mb.record("model-a", 100, 1000, 100, 900, 0.10, "ok")
    mb.record("model-a", 0, 5000, 0, 0, 0.10, "failed")
    s = mb.summary("model-a")
    assert s["runs"] == 2
    assert s["successful_runs"] == 1
    assert s["failure_rate"] == 0.5


def test_tokens_per_dollar():
    # $0.10 per 1M output tokens -> 10M tokens per dollar.
    assert mb.tokens_per_dollar(0.10) == 10_000_000
    assert mb.tokens_per_dollar(0) == 0


def test_throughput_value_score():
    # 100 output TPS at $0.10/M => 1B TPS-per-dollar score units.
    assert mb.throughput_per_dollar(100, 0.10) == 1_000_000_000


def test_ranked_prefers_high_verified_tps_per_dollar():
    mb.record("fast-cheap", 50, 1050, 100, 1000, 0.10, "ok")
    mb.record("slow-pricey", 50, 2050, 100, 2000, 1.00, "ok")
    ranked = mb.ranked()
    assert ranked[0]["model"] == "fast-cheap"
    assert ranked[0]["p50_output_tps"] > ranked[1]["p50_output_tps"]


def test_empty_summary_is_safe():
    s = mb.summary("unknown")
    assert s["runs"] == 0
    assert s["p50_output_tps"] == 0.0
