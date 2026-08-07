#!/usr/bin/env python3
"""Cache-affinity tracker: the ad-network layer for cached inference.

The orderbook prices the listing. It cannot price the fill. This module
implements the missing layer: a privacy-preserving prefix-hash index that
records which provider served which prefix with what latency, infers true
cache state from latency/token ratios, and proposes Vickrey-style bids
where providers with demonstrated cache affinity discount below list price.

Mapping to ad-network mechanics:

  - Prompt prefix → SHA-256 hash (like a cookie ID, never stored in plaintext)
  - Request → bid request broadcast ("who has prefix X cached, at what cost?")
  - Provider KV cache → DSP inventory match
  - Latency/token ratio → post-bid verification of cache state
  - Proposed bid → DSP bid based on match rate (cached → lower bid)
  - Vickrey settlement → winner pays second-lowest bid

Honesty is enforced by latency: a provider that claims cache (discounts its
bid) but serves with fresh-compute latency is penalized — the bid won't
discount because the latency doesn't support a cache claim. This is the
post-bid verification layer ad networks use to detect cookie fraud.
"""

from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

import combo_resolver as cr

DB_PATH = os.environ.get("SURP_AFFINITY_DB", str(Path(__file__).resolve().parent / "cache_affinity.db"))
WINDOW_SECONDS = int(os.environ.get("SURP_AFFINITY_WINDOW", "86400"))  # 24h
PRUNE_AFTER_SECONDS = int(os.environ.get("SURP_AFFINITY_PRUNE", "604800"))  # 7d

# Heuristic thresholds for inferring cache hits from latency.
# These are deliberately conservative: a true cache hit for a 1K-token prefix
# typically completes in <100ms, while fresh compute on a modern GPU is
# ~1-3ms/token → 1000-3000ms for 1K tokens. We set the boundary at
# CACHE_HIT_MS_PER_1K = 200ms (generous to avoid false positives).
CACHE_HIT_MS_PER_1K = float(os.environ.get("SURP_AFFINITY_HIT_MS_PER_1K", "200"))
MIN_SAMPLES_FOR_INFERENCE = int(os.environ.get("SURP_AFFINITY_MIN_SAMPLES", "2"))

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
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
        CREATE TABLE IF NOT EXISTS affinity_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            prefix_hash TEXT NOT NULL,
            model TEXT NOT NULL,
            provider TEXT,
            tokens INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            inferred_hit INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_aff_prefix_model ON affinity_samples(prefix_hash, model);
        CREATE INDEX IF NOT EXISTS idx_aff_ts ON affinity_samples(ts);
        """)
        _conn.commit()
    return _conn


def prefix_hash(system_prompt: str, user_content: str) -> str:
    """Hash a prompt prefix into a privacy-preserving 16-char fingerprint.

    Like a cookie ID: the hash is deterministic (same prompt → same hash) but
    cannot be reversed to recover the prompt. Only the first N tokens of the
    user content are hashed, so variations in the tail don't break affinity.
    """
    # Normalize whitespace and take the first 512 chars of user content to
    # establish a stable prefix boundary.
    norm_sys = (system_prompt or "").strip()[:256]
    norm_user = (user_content or "").strip()[:512]
    raw = f"{norm_sys}\x00{norm_user}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _infer_hit(tokens: int, latency_ms: int) -> bool:
    """Infer whether a response was served from cache based on latency.

    A cache hit for a K-token prefix completes in roughly CACHE_HIT_MS_PER_1K
    per 1K tokens. Fresh compute is ~10x slower. We use the ratio.
    """
    if tokens <= 0 or latency_ms <= 0:
        return False
    ms_per_1k = (latency_ms / tokens) * 1000
    return ms_per_1k < CACHE_HIT_MS_PER_1K


def record_sample(prefix_hash: str, model: str, tokens: int, latency_ms: int,
                   provider: str = "", ts: Optional[int] = None) -> None:
    """Record one fill: which model served which prefix with what latency."""
    now = int(ts if ts is not None else time.time())
    hit = _infer_hit(tokens, latency_ms)
    with _lock:
        c = conn()
        c.execute(
            "INSERT INTO affinity_samples(ts,prefix_hash,model,provider,tokens,latency_ms,inferred_hit) "
            "VALUES(?,?,?,?,?,?,?)",
            (now, prefix_hash, model, provider or "", max(0, int(tokens)),
             max(0, int(latency_ms)), 1 if hit else 0),
        )
        c.commit()


def affinity(prefix_hash: str, model: str, window: int = WINDOW_SECONDS) -> dict[str, Any]:
    """Compute cache affinity for a (prefix, model) pair over the window."""
    since = int(time.time()) - window
    rows = conn().execute(
        "SELECT tokens,latency_ms,inferred_hit,ts FROM affinity_samples "
        "WHERE prefix_hash=? AND model=? AND ts>=?",
        (prefix_hash, model, since),
    ).fetchall()
    if not rows:
        return {"prefix_hash": prefix_hash, "model": model, "samples": 0,
                "affinity_score": 0.0, "inferred_cache_hit": False,
                "avg_latency_ms": 0, "avg_tokens": 0}
    hits = sum(1 for r in rows if r["inferred_hit"])
    total = len(rows)
    score = hits / total
    avg_lat = sum(r["latency_ms"] for r in rows) / total
    avg_tok = sum(r["tokens"] for r in rows) / total
    return {
        "prefix_hash": prefix_hash,
        "model": model,
        "samples": total,
        "affinity_score": round(score, 3),
        "inferred_cache_hit": score >= 0.5 if total >= MIN_SAMPLES_FOR_INFERENCE else False,
        "avg_latency_ms": round(avg_lat, 1),
        "avg_tokens": round(avg_tok, 0),
    }


def rank_for_prefix(prefix_hash: str, models: list[str],
                     window: int = WINDOW_SECONDS) -> list[dict[str, Any]]:
    """Rank models by cache affinity for a given prefix (highest first)."""
    out = []
    for m in models:
        a = affinity(prefix_hash, m, window)
        out.append(a)
    out.sort(key=lambda x: x["affinity_score"], reverse=True)
    return out


def proposed_bid(prefix_hash: str, model: str, list_price_atomic: int,
                  window: int = WINDOW_SECONDS) -> int:
    """Propose a bid below list price if the model has demonstrated cache affinity.

    In an ad-network auction, a DSP bids lower when it has inventory match
    (cached prefix). Here: if the model's affinity score is high, discount the
    bid proportionally — up to 50% off list price for a confirmed cache hit.
    If there's no data or latency doesn't support cache, bid at list (no discount).
    """
    a = affinity(prefix_hash, model, window)
    if a["samples"] < MIN_SAMPLES_FOR_INFERENCE:
        return list_price_atomic
    if not a["inferred_cache_hit"]:
        return list_price_atomic
    # Discount proportional to affinity score, capped at 50%.
    discount = min(0.50, a["affinity_score"] * 0.50)
    return int(list_price_atomic * (1.0 - discount))


def global_stats() -> dict[str, Any]:
    """Global cache-affinity statistics for the public dashboard."""
    c = conn()
    since = int(time.time()) - WINDOW_SECONDS
    total = c.execute("SELECT COUNT(*) AS n FROM affinity_samples WHERE ts>=?", (since,)).fetchone()["n"]
    prefixes = c.execute("SELECT COUNT(DISTINCT prefix_hash) AS n FROM affinity_samples WHERE ts>=?", (since,)).fetchone()["n"]
    models = c.execute("SELECT COUNT(DISTINCT model) AS n FROM affinity_samples WHERE ts>=?", (since,)).fetchone()["n"]
    hits = c.execute("SELECT COUNT(*) AS n FROM affinity_samples WHERE ts>=? AND inferred_hit=1", (since,)).fetchone()["n"]
    return {
        "window_seconds": WINDOW_SECONDS,
        "total_samples": int(total),
        "distinct_prefixes": int(prefixes),
        "distinct_models": int(models),
        "inferred_cache_hits": int(hits),
        "cache_hit_rate": round(hits / max(1, total), 3),
        "methodology": "Prefix-hash affinity: SHA-256 of normalized prefix (cookie-like). "
                       "Cache state inferred from latency/token ratio (post-bid verification). "
                       "Providers with high affinity discount below list price (Vickrey-style).",
    }


def prune() -> int:
    """Delete samples older than the prune window."""
    cutoff = int(time.time()) - PRUNE_AFTER_SECONDS
    with _lock:
        cur = conn().execute("DELETE FROM affinity_samples WHERE ts < ?", (cutoff,))
        conn().commit()
        return cur.rowcount
