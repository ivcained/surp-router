#!/usr/bin/env python3
"""Verified LLM generation-throughput benchmarks.

Terminology is deliberately precise:

- output TPS: generated completion tokens / generation seconds
- request RPS: HTTP requests / wall-clock seconds (different metric)
- TTFT: time from request submission to first output token
- wall time: complete request duration

Only observed runs are published. No extrapolated vendor claims.
"""

from __future__ import annotations

import math
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

DB_PATH = os.environ.get("SURP_BENCHMARK_DB", str(Path(__file__).resolve().parent / "model_benchmarks.db"))
WINDOW_SECONDS = int(os.environ.get("SURP_BENCHMARK_WINDOW", str(7 * 86400)))

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _db()
        _conn.executescript("""
        CREATE TABLE IF NOT EXISTS benchmark_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            model TEXT NOT NULL,
            ttft_ms INTEGER NOT NULL DEFAULT 0,
            wall_ms INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            generation_ms INTEGER NOT NULL DEFAULT 0,
            output_tps REAL NOT NULL DEFAULT 0,
            price_usd_per_1m REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ok',
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_bench_model_ts ON benchmark_runs(model, ts);
        """)
        _conn.commit()
    return _conn


def output_tps(output_tokens: int, generation_seconds: float) -> float:
    """Return generated output tokens per second."""
    if output_tokens <= 0 or generation_seconds <= 0:
        return 0.0
    return round(output_tokens / generation_seconds, 2)


def tokens_per_dollar(price_usd_per_1m: float) -> int:
    """Output tokens purchasable for $1 at the quoted per-million price."""
    if price_usd_per_1m <= 0:
        return 0
    return int(1_000_000 / price_usd_per_1m)


def throughput_per_dollar(tps: float, price_usd_per_1m: float) -> int:
    """Value metric: output TPS multiplied by tokens purchasable per dollar."""
    return int(tps * tokens_per_dollar(price_usd_per_1m))


def record(model: str, ttft_ms: int, wall_ms: int, output_tokens: int,
           generation_ms: int, price_usd_per_1m: float, status: str,
           error: str = "", ts: Optional[int] = None) -> None:
    """Persist one observed benchmark run."""
    now = int(ts if ts is not None else time.time())
    tps = output_tps(output_tokens, generation_ms / 1000) if generation_ms > 0 else 0.0
    with _lock:
        c = conn()
        c.execute(
            "INSERT INTO benchmark_runs(ts,model,ttft_ms,wall_ms,output_tokens,"
            "generation_ms,output_tps,price_usd_per_1m,status,error) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (now, model, max(0, int(ttft_ms)), max(0, int(wall_ms)),
             max(0, int(output_tokens)), max(0, int(generation_ms)), tps,
             max(0.0, float(price_usd_per_1m)), status, error[:500]),
        )
        c.commit()


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    k = (len(vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - k) + vals[hi] * (k - lo)


def summary(model: str, window_seconds: int = WINDOW_SECONDS) -> dict[str, Any]:
    """Aggregate verified benchmark runs for a model."""
    since = int(time.time()) - window_seconds
    rows = conn().execute(
        "SELECT * FROM benchmark_runs WHERE model=? AND ts>=? ORDER BY ts DESC",
        (model, since),
    ).fetchall()
    ok = [r for r in rows if r["status"] == "ok" and r["output_tps"] > 0]
    tps_vals = [float(r["output_tps"]) for r in ok]
    ttft_vals = [float(r["ttft_ms"]) for r in ok]
    wall_vals = [float(r["wall_ms"]) for r in ok]
    prices = [float(r["price_usd_per_1m"]) for r in ok if r["price_usd_per_1m"] > 0]
    p50_tps = round(_percentile(tps_vals, 0.50), 2)
    median_price = round(_percentile(prices, 0.50), 6)
    return {
        "model": model,
        "runs": len(rows),
        "successful_runs": len(ok),
        "failure_rate": round((len(rows) - len(ok)) / max(1, len(rows)), 4),
        "p50_output_tps": p50_tps,
        "p95_output_tps": round(_percentile(tps_vals, 0.95), 2),
        "min_output_tps": round(min(tps_vals), 2) if tps_vals else 0.0,
        "max_output_tps": round(max(tps_vals), 2) if tps_vals else 0.0,
        "p50_ttft_ms": int(round(_percentile(ttft_vals, 0.50))),
        "p95_ttft_ms": int(round(_percentile(ttft_vals, 0.95))),
        "p50_wall_ms": int(round(_percentile(wall_vals, 0.50))),
        "median_price_usd_per_1m": median_price,
        "tokens_per_dollar": tokens_per_dollar(median_price),
        "throughput_value_score": throughput_per_dollar(p50_tps, median_price),
        "verified_at": int(rows[0]["ts"]) if rows else None,
        "window_seconds": window_seconds,
    }


def ranked(window_seconds: int = WINDOW_SECONDS) -> list[dict[str, Any]]:
    """Rank all benchmarked models by verified TPS-per-dollar value."""
    since = int(time.time()) - window_seconds
    models = [r["model"] for r in conn().execute(
        "SELECT DISTINCT model FROM benchmark_runs WHERE ts>=?", (since,)
    ).fetchall()]
    out = [summary(m, window_seconds) for m in models]
    out.sort(key=lambda x: (x["throughput_value_score"], x["p50_output_tps"]), reverse=True)
    return out


def recent_runs(model: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent raw observations for auditability."""
    rows = conn().execute(
        "SELECT ts,model,ttft_ms,wall_ms,output_tokens,generation_ms,output_tps,"
        "price_usd_per_1m,status,error FROM benchmark_runs WHERE model=? "
        "ORDER BY ts DESC LIMIT ?", (model, min(max(1, limit), 100)),
    ).fetchall()
    return [dict(r) for r in rows]
