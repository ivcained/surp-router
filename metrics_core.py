"""Shared metric sample for surp-router TPS feed (drop-in: metrics_core.py).

Pure data + math only — no I/O, no asyncio.

Design (single sample type):
  * ``StreamSample`` is a PLAIN record. ``tps`` and ``f1000_h`` are stored as
    attributes, precomputed by the producer (the gateway) via the pure
    helpers :func:`compute_tps` / :func:`compute_f1000_h`. The writer and the
    tests therefore deal with concrete values, never derived methods.
  * ``estimate_tokens`` is the ai-speedometer char-fallback for missing usage.
  * ``WindowedStats`` is a small rolling aggregator for the live dashboard.

Mirrors docs/proposals/tps-live-metrics/snippets/metrics_core.py (the
authoritative design), flattened to one record type for review simplicity.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StreamSample:
    """One measured generation event (live request or benchmark run).

    ``ts`` is second-resolution unix time (float), used as the DB/rollup
    bucket key; the SSE publisher converts to ms when framing. ``tps`` and
    ``f1000_h`` are precomputed by the producer (see compute_tps/compute_f1000_h)
    so the store persists plain columns and tests inject concrete values.
    """

    provider: str = ""
    model: str = ""
    source: str = "request"  # "request" | "benchmark"
    success: bool = True
    ttft_ms: Optional[float] = None
    gen_ms: Optional[float] = None
    total_ms: float = 0.0
    completion_tokens: int = 0
    prompt_tokens: int = 0
    tps: Optional[float] = None
    f1000_h: Optional[float] = None
    estimated: bool = False
    error: Optional[str] = None
    ts: float = 0.0

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = time.time()


def compute_tps(gen_ms: Optional[float], completion_tokens: int) -> Optional[float]:
    """Generation token rate (tokens/sec) or None when unmeasurable."""
    if gen_ms and gen_ms > 0 and completion_tokens > 0:
        return completion_tokens / (gen_ms / 1000)
    return None


def compute_f1000_h(ttft_ms: Optional[float], tps: Optional[float]) -> Optional[float]:
    """Ai-speedometer parity: hours to finish (1000 * task) at this perf.

    F1000_h = (1000 * (ttft_s + 300 / tps)) / 3600. Lower is better.
    Returns None when ttft or tps is missing/non-positive.
    """
    if not tps or tps <= 0 or ttft_ms is None:
        return None
    return (1000 * (ttft_ms / 1000 + 300 / tps)) / 3600


def estimate_tokens(text: str) -> int:
    """Ai-speedometer fallback: ceil(len/4), min 1 for non-empty."""
    return max(1, math.ceil(len(text) / 4)) if text else 0


def _pct(sorted_vals: list, pct: float) -> float:
    """Nearest-rank percentile (pct in 0..100) over a sorted list."""
    if not sorted_vals:
        return 0.0
    k = max(1, math.ceil(pct / 100 * len(sorted_vals)))
    return sorted_vals[min(k, len(sorted_vals)) - 1]


@dataclass
class WindowedStats:
    """Rolling-window aggregator for the live dashboard (pure, time-injected).

    Feed it (tps, ttft_ms, ts) samples; it keeps a bounded ring keyed by ts
    and exposes the headline numbers. Caller (dashboard/gateway) owns timing;
    ts is seconds, monotonic-ish acceptable for the window.
    """

    window_s: float = 120.0
    max_samples: int = 1000
    _samples: list = field(default_factory=list)  # (ts, tps, ttft_ms)

    def add(self, tps: Optional[float], ttft_ms: Optional[float], ts: float) -> None:
        if tps is not None and tps > 0:
            self._samples.append((ts, tps, ttft_ms))
        if len(self._samples) > self.max_samples:
            self._samples.pop(0)

    def prune(self, now: float) -> None:
        cutoff = now - self.window_s
        self._samples = [s for s in self._samples if s[0] >= cutoff]

    def tps_avg(self, now: float) -> Optional[float]:
        self.prune(now)
        vals = [s[1] for s in self._samples]
        return sum(vals) / len(vals) if vals else None

    def tps_p95(self, now: float) -> Optional[float]:
        self.prune(now)
        vals = sorted(s[1] for s in self._samples)
        return _pct(vals, 95) if vals else None

    def ttft_min(self, now: float) -> Optional[float]:
        self.prune(now)
        ttfts = [s[2] for s in self._samples if s[2] is not None]
        return min(ttfts) if ttfts else None

    def sample_count(self, now: float) -> int:
        self.prune(now)
        return len(self._samples)

    def describe(self, now: float) -> dict:
        """Compact payload for the SSE/dashboard render path."""
        return {
            "count": self.sample_count(now),
            "tps_avg": self.tps_avg(now),
            "tps_p95": self.tps_p95(now),
            "ttft_min": self.ttft_min(now),
        }
