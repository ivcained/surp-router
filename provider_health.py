#!/usr/bin/env python3
"""Provider latency, TPS, and failure-rate tracker.

Surplus Intelligence's marketplace dashboard exposes pricing, liquidity, and
24h volume — but NOT per-provider TPS, wall-clock latency, or failure rates.
This module fills that gap by measuring every routed request ourselves. The
resulting health scores power the free-model health board and feed back into
routing decisions (cheap-and-flaky loses to slightly-pricier-but-reliable).
"""

from __future__ import annotations

import math
import os
import pathlib
import secrets
import sqlite3
import threading
import time
from typing import Any, Optional

import combo_resolver as cr

DB_PATH = os.environ.get("SURP_HEALTH_DB", str(pathlib.Path(__file__).resolve().parent / "provider_health.db"))
WINDOW_SECONDS = int(os.environ.get("SURP_HEALTH_WINDOW", "3600"))  # 1h rolling
PRUNE_AFTER_SECONDS = int(os.environ.get("SURP_HEALTH_PRUNE", "86400"))  # 24h

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    import pathlib as _pl
    _pl.Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _db()
        _conn.executescript("""
        CREATE TABLE IF NOT EXISTS provider_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            model TEXT NOT NULL,
            provider TEXT,
            status TEXT NOT NULL DEFAULT 'ok',
            latency_ms INTEGER NOT NULL DEFAULT 0,
            tokens INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_samples_model_ts ON provider_samples(model, ts);
        """)
        _conn.commit()
    return _conn


def record(model: str, status: str = "ok", latency_ms: int = 0,
           tokens: int = 0, provider: str = "", ts: Optional[int] = None) -> None:
    """Record one routing sample. Called after every upstream response."""
    now = int(ts if ts is not None else time.time())
    with _lock:
        c = conn()
        c.execute(
            "INSERT INTO provider_samples(ts,model,provider,status,latency_ms,tokens) "
            "VALUES(?,?,?,?,?,?)",
            (now, model, provider or "", status, max(0, int(latency_ms)), max(0, int(tokens))),
        )
        c.commit()


def _percentile(sorted_vals: list[int], p: float) -> int:
    if not sorted_vals:
        return 0
    k = (len(sorted_vals) - 1) * p
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return int(sorted_vals[int(k)])
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return int(d0 + d1)


def stats(model: str, window_seconds: int = WINDOW_SECONDS) -> dict[str, Any]:
    """TPS, latency percentiles, failure rate, and token throughput for a model."""
    now = int(time.time())
    since = now - window_seconds
    c = conn()
    rows = c.execute(
        "SELECT status,latency_ms,tokens,ts FROM provider_samples "
        "WHERE model=? AND ts>=? ORDER BY ts ASC",
        (model, since),
    ).fetchall()
    if not rows:
        return {
            "model": model, "requests": 0, "failures": 0, "failure_rate": 0.0,
            "tokens": 0, "tps": 0.0, "p50_latency_ms": 0, "p95_latency_ms": 0,
            "mean_latency_ms": 0,
        }
    ok_latencies = sorted([r["latency_ms"] for r in rows if r["status"] == "ok" and r["latency_ms"] > 0])
    requests = len(rows)
    failures = sum(1 for r in rows if r["status"] != "ok")
    tokens = sum(r["tokens"] for r in rows)
    span = max(1, now - rows[0]["ts"])
    tps = requests / span
    mean_lat = (sum(ok_latencies) / len(ok_latencies)) if ok_latencies else 0
    return {
        "model": model,
        "requests": requests,
        "failures": failures,
        "failure_rate": round(failures / requests, 4),
        "tokens": tokens,
        "tps": round(tps, 2),
        "p50_latency_ms": _percentile(ok_latencies, 0.50),
        "p95_latency_ms": _percentile(ok_latencies, 0.95),
        "mean_latency_ms": round(mean_lat, 1),
    }


def health_score(model: str, window_seconds: int = WINDOW_SECONDS) -> float:
    """Composite 0-100 score: reliability × speed × throughput.

    Reliability (60%): 1 - failure_rate.
    Speed (30%): normalized so p50 of 50ms → 1.0, 2000ms+ → 0.
    Throughput (10%): normalized so TPS of 1.0+ → 1.0.
    """
    s = stats(model, window_seconds)
    if s["requests"] == 0:
        return 0.0
    reliability = 1.0 - s["failure_rate"]
    p50 = s["p50_latency_ms"]
    speed = max(0.0, min(1.0, (2000 - p50) / 1950)) if p50 > 0 else 0.0
    throughput = min(1.0, s["tps"])
    return round((reliability * 60 + speed * 30 + throughput * 10), 2)


def ranked(models: list[str], window_seconds: int = WINDOW_SECONDS) -> list[dict[str, Any]]:
    """Rank models by composite health score, descending."""
    out = []
    for m in models:
        s = stats(m, window_seconds)
        out.append({**s, "health_score": health_score(m, window_seconds)})
    out.sort(key=lambda x: x["health_score"], reverse=True)
    return out


def prune() -> int:
    """Delete samples older than the prune window. Returns rows deleted."""
    cutoff = int(time.time()) - PRUNE_AFTER_SECONDS
    with _lock:
        cur = conn().execute("DELETE FROM provider_samples WHERE ts < ?", (cutoff,))
        conn().commit()
        return cur.rowcount


def all_models(window_seconds: int = WINDOW_SECONDS) -> list[dict[str, Any]]:
    """Health stats for every model with samples in the window."""
    since = int(time.time()) - window_seconds
    models = [r["model"] for r in conn().execute(
        "SELECT DISTINCT model FROM provider_samples WHERE ts >= ?", (since,)
    ).fetchall()]
    return ranked(models, window_seconds)
