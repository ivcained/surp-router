"""Surp Value Index (SVI) — a single composite score per model.

SVI = weighted geometric mean of three normalized sub-scores:

  cost_score        : how cheap per 1M tokens (inverse price, normalized)
  intelligence_score: benchmarked capability (MMLU/GPQA/HumanEval/IFEval)
                      mapped to a 0-100 scale, per model class
  speed_score       : verified p50 output TPS from our own benchmark runner

Why a geometric mean? A model that is weak in one axis (e.g. fast but
dumb, or smart but slow) must not hide it behind a strong other axis —
an arithmetic mean lets a cheap-but-unusable model score highly. The
geometric mean punishes weak axes proportionally.

The index creates competitive engagement:
  - Buyers get one number to optimize (highest SVI in class = best value).
  - Suppliers can climb the leaderboard by submitting benchmark results
    (quantized/original runs) that raise their intelligence_score or by
    improving real served TPS.

Weights (env-overridable) default to value-for-money emphasis:
  cost 45%, intelligence 40%, speed 15%.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Optional

# ── Weights ──────────────────────────────────────────────────────────────────
W_COST = float(os.environ.get("SURP_SVI_W_COST", "0.45"))
W_INTEL = float(os.environ.get("SURP_SVI_W_INTEL", "0.40"))
W_SPEED = float(os.environ.get("SURP_SVI_W_SPEED", "0.15"))

# ── Benchmark registry (intelligence scores) ────────────────────────────────
# Mapped to a 0-100 scale per class. These are community/built-in submitted
# scores — the "competitive engagement" surface. Suppliers submit their
# quantized/original model benchmark runs; verified entries land here.
# Each entry: model id → {mmlu, gpqa, humaneval, ifeval} (0-100 each).
_BENCH_DB_PATH = os.environ.get(
    "SURP_SVI_BENCH_DB", os.path.join(os.path.dirname(__file__), "svi_benchmarks.json")
)

# Default fallback intelligence for models without a submission.
_DEFAULT_INTEL: dict[str, float] = {
    "frontier": 95.0,
    "strong": 85.0,
    "coding": 80.0,
    "reasoning": 85.0,
    "chat": 70.0,
    "fast": 60.0,
    "small": 45.0,
    "vision": 75.0,
}

_lock = None  # simple file lock via atomic writes


def _load_benchmarks() -> dict[str, dict[str, float]]:
    """Load submitted benchmark scores from the registry file."""
    try:
        with open(_BENCH_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def submit_benchmark(model: str, mmlu: Optional[float] = None,
                     gpqa: Optional[float] = None,
                     humaneval: Optional[float] = None,
                     ifeval: Optional[float] = None,
                     submitter: str = "") -> dict[str, Any]:
    """Record a supplier/community benchmark submission.

    Scores are clamped 0-100. Returns the updated intelligence score for
    the model. This is the competitive surface: verified submissions
    move the leaderboard.
    """
    bench = _load_benchmarks()
    entry = bench.get(model, {})
    for key, val in (("mmlu", mmlu), ("gpqa", gpqa),
                     ("humaneval", humaneval), ("ifeval", ifeval)):
        if val is not None:
            entry[key] = max(0.0, min(100.0, float(val)))
    entry["submitter"] = submitter
    bench[model] = entry
    # atomic-ish write
    tmp = _BENCH_DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(bench, f, indent=2)
    os.replace(tmp, _BENCH_DB_PATH)
    return {"model": model, "intelligence_score": intelligence_score(model, bench)}


def _class_of(model: str) -> str:
    m = model.lower()
    if "vision" in m or "vl" in m or "5v" in m:
        return "vision"
    if any(k in m for k in ("coder", "codex", "qwen3-coder")):
        return "coding"
    if any(k in m for k in ("thinking", "r1", "reason", "reasons")):
        return "reasoning"
    if any(k in m for k in ("mini", "nano", "lite", "flash", "small")):
        return "fast"
    if any(k in m for k in ("gpt-5", "claude-opus", "gemini-2.5-pro", "opus")):
        return "frontier"
    return "chat"


def intelligence_score(model: str, bench: Optional[dict] = None) -> float:
    """Composite 0-100 intelligence score from the benchmark registry.

    Uses a submitted entry if present, else the class default. The four
    axes are equally weighted; a missing axis falls back to the class
    default for that axis so partial submissions still count.
    """
    bench = bench if bench is not None else _load_benchmarks()
    cls = _class_of(model)
    default = _DEFAULT_INTEL.get(cls, 60.0)
    entry = bench.get(model, {})
    axes = ["mmlu", "gpqa", "humaneval", "ifeval"]
    vals = []
    for ax in axes:
        if ax in entry and entry[ax] is not None:
            vals.append(max(0.0, min(100.0, float(entry[ax]))))
        else:
            # Missing axis → class default (partial submissions still count).
            vals.append(default)
    return round(sum(vals) / len(vals), 1)


def cost_score(price_usd_per_1m: float, cheapest_price: float) -> float:
    """0-100 cost score: cheapest model scores 100, others proportionally."""
    if price_usd_per_1m <= 0:
        return 0.0
    if cheapest_price <= 0:
        return 100.0
    # sqrt softens the penalty — a 4x pricier model is 50, not 25.
    return round(100.0 * math.sqrt(cheapest_price / price_usd_per_1m), 1)


def speed_score(p50_tps: float, fastest_tps: float) -> float:
    """0-100 speed score: fastest model scores 100, others proportionally."""
    if p50_tps <= 0 or fastest_tps <= 0:
        return 0.0
    return round(100.0 * (p50_tps / fastest_tps), 1)


def composite(cost: float, intel: float, speed: float,
              weights: Optional[tuple[float, float, float]] = None) -> float:
    """Weighted geometric mean → 0-100 SVI.

    weights: optional (cost, intel, speed) override. Defaults to the
    module-level W_COST/W_INTEL/W_SPEED.
    """
    if weights is not None:
        wc, wi, ws = weights
    else:
        wc, wi, ws = W_COST, W_INTEL, W_SPEED
    wsum = wc + wi + ws
    if wsum <= 0:
        return 0.0
    # Guard against zero axes (log of 0). Floor at a small epsilon.
    c = max(cost, 0.01)
    i = max(intel, 0.01)
    s = max(speed, 0.01)
    raw = (c ** (wc / wsum)) * (i ** (wi / wsum)) * (s ** (ws / wsum))
    return round(raw, 1)


# ── Routing modes ─────────────────────────────────────────────────────────────
# Users can route by their own lens, not just the default SVI. Each mode is a
# (cost, intel, speed) weight triple. 'cost' is special-cased to pure cheapest
# in pick_winner (agents running overnight genuinely want minimum price).

MODE_WEIGHTS: dict[str, tuple[float, float, float]] = {
    "value":    (0.45, 0.40, 0.15),   # default SVI
    "balanced": (1/3, 1/3, 1/3),
    "speed":    (0.15, 0.15, 0.70),   # interactive work
    "intel":    (0.20, 0.60, 0.20),   # hard problems
    "cost":     (0.80, 0.10, 0.10),   # overnight batch (pure cheapest in pick_winner)
}


def parse_weights(spec: Optional[str]) -> Optional[tuple[float, float, float]]:
    """Parse a custom weight spec like '0.3:0.4:0.3' → (cost, intel, speed).

    Returns None if invalid/absent.
    """
    if not spec:
        return None
    try:
        parts = [float(x.strip()) for x in spec.split(":")]
        if len(parts) != 3 or any(x < 0 for x in parts):
            return None
        return (parts[0], parts[1], parts[2])
    except (ValueError, AttributeError):
        return None


def pick_winner(models: list[dict[str, Any]], mode: str = "value",
                weights: Optional[tuple[float, float, float]] = None,
                bench: Optional[dict] = None) -> tuple[Optional[str], str, Optional[dict]]:
    """Pick the best model to route to, by the requested mode.

    models: [{model, price_usd_per_1m, p50_tps}] — p50_tps 0 means the model
            has no verified benchmark (speed unknown).
    mode:   'cost' | 'value' | 'balanced' | 'speed' | 'intel'
    weights: optional (cost, intel, speed) override — takes precedence over mode.

    Returns (model_id, reason, breakdown) where reason explains the choice
    (e.g. 'value', 'cost', 'speed-fallback-to-cost').
    """
    bench = bench if bench is not None else _load_benchmarks()
    if not models:
        return None, "empty-pool", None

    # Pure cost: minimum price, no benchmark needed.
    if mode == "cost" and weights is None:
        best = min(models, key=lambda m: m.get("price_usd_per_1m", float("inf")))
        return best["model"], "cost", None

    # Reference values from the pool.
    prices = [m.get("price_usd_per_1m", 0) for m in models if m.get("price_usd_per_1m", 0) > 0]
    tps_vals = [m.get("p50_tps", 0) for m in models if m.get("p50_tps", 0) > 0]
    cheapest = min(prices) if prices else 0.0
    fastest = max(tps_vals) if tps_vals else 0.0

    # Intelligence-only mode needs no speed.
    if mode == "intel" and weights is None:
        best = max(models, key=lambda m: intelligence_score(m["model"], bench))
        return best["model"], "intel", None

    # Speed / value / balanced / custom need verified TPS. If none of the pool
    # is benchmarked, fall back to cheapest so routing never fails.
    if fastest <= 0:
        best = min(models, key=lambda m: m.get("price_usd_per_1m", float("inf")))
        return best["model"], "cost-fallback", None

    w = weights if weights is not None else MODE_WEIGHTS.get(mode, MODE_WEIGHTS["value"])

    def score(m: dict) -> float:
        c = cost_score(m.get("price_usd_per_1m", 0), cheapest)
        i = intelligence_score(m["model"], bench)
        s = speed_score(m.get("p50_tps", 0), fastest)
        return composite(c, i, s, w)

    best = max(models, key=score)
    reason = "custom-weights" if weights is not None else mode
    return best["model"], reason, None


def index_for(model: str, price_usd_per_1m: float, p50_tps: float,
              cheapest_price: float, fastest_tps: float,
              bench: Optional[dict] = None) -> dict[str, Any]:
    """Compute the full SVI breakdown for one model."""
    c = cost_score(price_usd_per_1m, cheapest_price)
    i = intelligence_score(model, bench)
    s = speed_score(p50_tps, fastest_tps)
    return {
        "model": model,
        "price_usd_per_1m": price_usd_per_1m,
        "p50_tps": p50_tps,
        "cost_score": c,
        "intelligence_score": i,
        "speed_score": s,
        "svi": composite(c, i, s),
    }


def rank(market_models: list[dict[str, Any]],
         benchmarked: list[dict[str, Any]],
         bench: Optional[dict] = None) -> list[dict[str, Any]]:
    """Rank marketplace models by SVI.

    market_models: [{model, price_usd_per_1m}] from the live Surplus feed.
    benchmarked:   [{model, p50_output_tps}] from our verified benchmark runner.
    Models without a verified TPS get speed_score 0 (not ranked) — we never
    publish an SVI for unverified speed.
    """
    bench = bench if bench is not None else _load_benchmarks()
    price_by_model = {m["model"]: float(m.get("price_usd_per_1m", 0)) for m in market_models}
    tps_by_model = {b["model"]: float(b.get("p50_output_tps", 0)) for b in benchmarked}

    # Normalize against the models actually being ranked (those with verified
    # speed), not the whole market feed — otherwise a handful of ultra-cheap
    # unbenchmarked models would compress every ranked model's cost score
    # toward zero and dominate the index.
    ranked_models = [m for m in price_by_model if tps_by_model.get(m, 0) > 0]
    cheapest = min((price_by_model[m] for m in ranked_models), default=0.0) if ranked_models else 0.0
    fastest = max(tps_by_model.values()) if tps_by_model else 0.0

    rows = []
    for model, price in price_by_model.items():
        tps = tps_by_model.get(model, 0.0)
        if tps <= 0:
            continue  # unverified speed → not ranked
        rows.append(index_for(model, price, tps, cheapest, fastest, bench))
    rows.sort(key=lambda r: r["svi"], reverse=True)
    return rows
