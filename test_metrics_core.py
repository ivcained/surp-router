"""Unit tests for metrics_core (pure math — no I/O)."""
from __future__ import annotations

import pytest

from metrics_core import (
    StreamSample,
    WindowedStats,
    compute_f1000_h,
    compute_tps,
    estimate_tokens,
)


# --- compute_tps ---
def test_compute_tps_basic():
    assert compute_tps(10_000.0, 1000) == pytest.approx(100.0)


def test_compute_tps_none():
    assert compute_tps(None, 1000) is None
    assert compute_tps(0.0, 1000) is None
    assert compute_tps(10_000.0, 0) is None
    assert compute_tps(-5.0, 100) is None


# --- compute_f1000_h ---
def test_compute_f1000_h_known_value():
    # ttft 0.2s, 100 tps, 300 tokens/task
    # f1000 = (1000 * (0.2 + 300/100)) / 3600 = (1000 * 3.2) / 3600 = 0.8889 h
    assert compute_f1000_h(200.0, 100.0) == pytest.approx((1000 * (0.2 + 300 / 100)) / 3600)


def test_compute_f1000_h_none_on_missing():
    assert compute_f1000_h(None, 100.0) is None
    assert compute_f1000_h(200.0, None) is None
    assert compute_f1000_h(200.0, 0.0) is None
    assert compute_f1000_h(200.0, -5.0) is None


def test_compute_f1000_h_lower_is_better():
    fast = compute_f1000_h(50.0, compute_tps(5_000.0, 1000))   # 200 tps
    slow = compute_f1000_h(200.0, compute_tps(20_000.0, 1000))  # 50 tps
    assert fast is not None and slow is not None
    assert fast < slow


# --- estimate_tokens ---
def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("x" * 100) == 25


# --- StreamSample record ---
def test_streamsample_ts_autofill():
    s = StreamSample()
    assert s.ts > 0
    fixed = StreamSample(ts=123.0)
    assert fixed.ts == 123.0


def test_streamsample_defaults():
    s = StreamSample()
    assert s.provider == "" and s.model == "" and s.source == "request"
    assert s.success is True and s.estimated is False
    assert s.tps is None and s.f1000_h is None
    assert s.ttft_ms is None and s.completion_tokens == 0


def test_streamsample_stores_precomputed():
    s = StreamSample(provider="p1", model="m1", tps=42.0, f1000_h=0.5)
    assert s.tps == 42.0 and s.f1000_h == 0.5


# --- WindowedStats ---
def test_windowed_basic():
    w = WindowedStats(window_s=120.0)
    w.add(100.0, 200.0, ts=1.0)
    w.add(50.0, 100.0, ts=2.0)
    w.add(None, None, ts=3.0)  # ignored (no tps)
    assert w.sample_count(now=3.0) == 2
    assert w.tps_avg(3.0) == pytest.approx(75.0)
    assert w.tps_p95(3.0) == pytest.approx(100.0)  # nearest-rank p95 of 2
    assert w.ttft_min(3.0) == pytest.approx(100.0)


def test_windowed_prune():
    w = WindowedStats(window_s=10.0)
    w.add(100.0, 1.0, ts=1.0)
    w.add(200.0, 2.0, ts=20.0)  # outside window once now=25
    assert w.sample_count(now=25.0) == 1
    assert w.tps_avg(25.0) == pytest.approx(200.0)


def test_windowed_empty():
    w = WindowedStats()
    assert w.tps_avg(0.0) is None
    assert w.tps_p95(0.0) is None
    assert w.ttft_min(0.0) is None
    assert w.sample_count(0.0) == 0


def test_windowed_describe():
    w = WindowedStats()
    w.add(10.0, 5.0, ts=1.0)
    d = w.describe(now=2.0)
    assert d["count"] == 1
    assert d["tps_avg"] == pytest.approx(10.0)
