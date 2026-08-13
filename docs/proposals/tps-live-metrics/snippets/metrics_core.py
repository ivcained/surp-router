"""Shared metric sample for surp-router TPS feed (drop-in: metrics_core.py)."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass
class StreamSample:
    provider: str
    model: str
    source: str  # "request" | "benchmark"
    success: bool
    ttft_ms: float | None
    gen_ms: float | None
    total_ms: float
    completion_tokens: int
    prompt_tokens: int
    estimated: bool
    error: str | None = None
    ts: float = 0.0

    def __post_init__(self):
        if not self.ts:
            self.ts = time.time()

    @property
    def tps(self) -> float | None:
        if self.gen_ms and self.completion_tokens and self.gen_ms > 0:
            return self.completion_tokens / (self.gen_ms / 1000)
        return None

    @property
    def f1000_h(self) -> float | None:
        """Ai-speedometer parity: (1000 * (ttft_s + 300/tps)) / 3600 hours."""
        tps = self.tps
        if not tps or self.ttft_ms is None or tps <= 0:
            return None
        return (1000 * (self.ttft_ms / 1000 + 300 / tps)) / 3600


def estimate_tokens(text: str) -> int:
    """Ai-speedometer fallback: ceil(len/4), min 1 for non-empty."""
    return max(1, math.ceil(len(text) / 4)) if text else 0
