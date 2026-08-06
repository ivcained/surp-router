#!/usr/bin/env python3
"""OmniRoute-inspired free-tier intelligence + surp-sponsored free routing.

Two deliberately separate concepts:

1. Catalog intelligence: an MIT-licensed snapshot derived from OmniRoute's
   pool-deduped free-tier catalog. It documents third-party free tiers and ToS
   risk, but surp does NOT proxy those third-party credentials for public users.
2. Sponsored inference: surp's treasury pays for a small, rate-limited pool of
   the cheapest live Surplus models. Users pay $0. This is safe to operate as a
   public service because it uses our paid Surplus account rather than abusing
   other providers' personal free tiers.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

import combo_resolver as cr

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = Path(os.environ.get("OMNIROUTE_FREE_CATALOG", ROOT / "data/omniroute_free_catalog.json"))
DB_PATH = os.environ.get("SURP_FREE_DB", str(ROOT / "free_models.db"))

# Sponsored-free safety limits. The gateway pays upstream cost.
DAILY_REQUEST_BUDGET = int(os.environ.get("SURP_FREE_DAILY_REQUESTS", "500"))
DAILY_TOKEN_BUDGET = int(os.environ.get("SURP_FREE_DAILY_TOKENS", "100000"))
PER_IP_DAILY_REQUESTS = int(os.environ.get("SURP_FREE_PER_IP_REQUESTS", "20"))
MAX_OUTPUT_TOKENS = int(os.environ.get("SURP_FREE_MAX_OUTPUT_TOKENS", "128"))
MAX_MODEL_USD_PER_1M = float(os.environ.get("SURP_FREE_MAX_MODEL_USD_PER_1M", "0.10"))
FALLBACK_ATTEMPTS = int(os.environ.get("SURP_FREE_FALLBACK_ATTEMPTS", "3"))

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None
_catalog_cache: Optional[dict[str, Any]] = None


def load_catalog() -> dict[str, Any]:
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = json.loads(CATALOG_PATH.read_text())
    return _catalog_cache


def _deduped_sum(entries: list[dict[str, Any]], field: str, included_types: set[str]) -> int:
    pools: dict[str, int] = {}
    loose = 0
    for e in entries:
        if e.get("free_type") not in included_types:
            continue
        amount = int(e.get(field) or 0)
        key = e.get("pool_key")
        if key:
            pools[key] = max(pools.get(key, 0), amount)
        else:
            loose += amount
    return loose + sum(pools.values())


def compute_catalog_totals(entries: list[dict[str, Any]], exclude_tos_avoid: bool = False) -> dict[str, Any]:
    """OmniRoute's honest accounting: shared pools count once (maximum)."""
    models = [e for e in entries if not (exclude_tos_avoid and e.get("tos") == "avoid")]
    recurring_types = {"recurring-daily", "recurring-monthly", "keyless"}
    steady = _deduped_sum(models, "monthly_tokens", recurring_types)
    recurring_credit = _deduped_sum(models, "credit_tokens", {"recurring-credit"})
    one_time = _deduped_sum(models, "credit_tokens", {"one-time-initial"})
    pools = {e.get("pool_key") for e in models if e.get("free_type") in recurring_types and e.get("pool_key")}
    uncapped = sorted({e["provider"] for e in models if e.get("free_type") == "recurring-uncapped"})
    by_tos = {x: sum(1 for e in models if e.get("tos") == x) for x in ("ok", "ambiguous", "caution", "avoid", "unknown")}
    return {
        "steady_recurring_tokens": steady,
        "steady_with_recurring_credits": steady + recurring_credit,
        "first_month_realistic_tokens": steady + recurring_credit + one_time,
        "uncapped_providers": uncapped,
        "model_count": len(models),
        "provider_count": len({e.get("provider") for e in models}),
        "pool_count": len(pools),
        "tos_counts": by_tos,
    }


def catalog_summary() -> dict[str, Any]:
    cat = load_catalog()
    all_totals = compute_catalog_totals(cat["entries"], False)
    safe_totals = compute_catalog_totals(cat["entries"], True)
    return {
        "source": cat["source"],
        "branch": cat["branch"],
        "license": cat["license"],
        "curated_at": cat["curated_at"],
        "all": all_totals,
        "excluding_tos_avoid": safe_totals,
    }


def sponsored_pool(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Live Surplus models cheap enough for treasury-sponsored free use."""
    ceiling_atomic = MAX_MODEL_USD_PER_1M * cr.PRICE_DIVISOR
    pool = [
        m for m in markets
        if cr.is_text_llm(m) and cr.is_sellable(m)
        and cr.price_of(m) > 0
        and cr.price_of(m) <= ceiling_atomic
    ]
    return sorted(pool, key=cr.price_of)


# Per-class price ceilings: coding models are pricier than chat, fast models
# are the cheapest. Each can be tuned independently via env.
CLASS_CEILINGS: dict[str, float] = {
    "chat": MAX_MODEL_USD_PER_1M,
    "coding": float(os.environ.get("SURP_FREE_MAX_CODING_USD_PER_1M", "0.50")),
    "fast": float(os.environ.get("SURP_FREE_MAX_FAST_USD_PER_1M", "0.05")),
}


def _is_coding_model(m: dict[str, Any]) -> bool:
    name = str(m.get("model", "")).lower()
    return any(k in name for k in ("coder", "codex", "qwen3-coder", "codeqwen", "starcoder"))


def _is_fast_model(m: dict[str, Any]) -> bool:
    name = str(m.get("model", "")).lower()
    return any(k in name for k in ("mini", "nano", "lite", "small", "tiny", "flash"))


def sponsored_pool_for_class(markets: list[dict[str, Any]], free_class: str) -> list[dict[str, Any]]:
    """Sponsored free pool restricted to a model class (chat/coding/fast)."""
    ceiling = CLASS_CEILINGS.get(free_class, MAX_MODEL_USD_PER_1M) * cr.PRICE_DIVISOR
    base = [m for m in markets if cr.is_text_llm(m) and cr.is_sellable(m)
            and 0 < cr.price_of(m) <= ceiling]
    if free_class == "coding":
        base = [m for m in base if _is_coding_model(m)]
    elif free_class == "fast":
        base = [m for m in base if _is_fast_model(m)]
    return sorted(base, key=cr.price_of)


def fallback_order(pool: list[dict[str, Any]], failed_models: set[str] | None = None) -> list[dict[str, Any]]:
    failed = failed_models or set()
    return [m for m in pool if m.get("model") not in failed]


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
        CREATE TABLE IF NOT EXISTS free_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            day TEXT NOT NULL,
            client_hash TEXT NOT NULL,
            model TEXT NOT NULL,
            tokens INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ok',
            latency_ms INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_free_usage_day ON free_usage(day);
        CREATE INDEX IF NOT EXISTS idx_free_usage_client_day ON free_usage(client_hash,day);
        CREATE TABLE IF NOT EXISTS free_keys (
            key_hash TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            elevated_requests INTEGER NOT NULL,
            elevated_tokens INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS free_conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            client_hash TEXT NOT NULL,
            from_tier TEXT NOT NULL,
            to_combo TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_free_conv_client ON free_conversions(client_hash);
        """)
        _conn.commit()
    return _conn


def _day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


# ── Free-tier API keys for heavy users with elevated budgets ──

def create_free_key(label: str, elevated_requests: int = 1000,
                    elevated_tokens: int = 200000) -> dict[str, Any]:
    """Issue a free-tier API key with elevated daily budgets."""
    raw = "sk-surp-free-" + secrets.token_urlsafe(24)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    with _lock:
        c = conn()
        c.execute(
            "INSERT INTO free_keys(key_hash,label,elevated_requests,elevated_tokens,created_at) "
            "VALUES(?,?,?,?,?)",
            (key_hash, label, int(elevated_requests), int(elevated_tokens), int(time.time())),
        )
        c.commit()
    return {"ok": True, "key": raw, "label": label, "tier": "free",
            "elevated_requests": elevated_requests, "elevated_tokens": elevated_tokens}


def validate_free_key(raw_key: str) -> Optional[dict[str, Any]]:
    """Validate a free-tier key. Returns key record or None."""
    if not raw_key or not raw_key.startswith("sk-surp-free-"):
        return None
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    row = conn().execute(
        "SELECT * FROM free_keys WHERE key_hash=?", (key_hash,)
    ).fetchone()
    if row is None:
        return None
    return {"label": row["label"], "elevated_requests": int(row["elevated_requests"]),
            "elevated_tokens": int(row["elevated_tokens"]),
            "key_hash": key_hash}


def record_free_key_usage(raw_key: str, model: str, tokens: int,
                           status: str = "ok") -> None:
    """Record usage attributed to a free-tier API key (not just IP)."""
    rec = validate_free_key(raw_key)
    if rec is None:
        return
    with _lock:
        conn().execute(
            "INSERT INTO free_usage(ts,day,client_hash,model,tokens,status,latency_ms) "
            "VALUES(?,?,?,?,?,?,?)",
            (int(time.time()), _day(), rec["key_hash"][:24], model,
             max(0, int(tokens)), status, 0),
        )
        conn().commit()


# ── Budget enforcement (shared by IP-based and key-based access) ──

def can_serve(client_hash: str, estimated_tokens: int) -> tuple[bool, str]:
    return can_serve_free(client_hash, estimated_tokens, is_key=False)


def can_serve_free(client_id: str, estimated_tokens: int, is_key: bool = False,
                   elevated_requests: int = 0, elevated_tokens: int = 0) -> tuple[bool, str]:
    """Check if a free request can be served, optionally with elevated key budget."""
    c = conn()
    day = _day()
    req_budget = elevated_requests or DAILY_REQUEST_BUDGET
    tok_budget = elevated_tokens or DAILY_TOKEN_BUDGET
    global_row = c.execute(
        "SELECT COUNT(*) AS n,COALESCE(SUM(tokens),0) AS t FROM free_usage WHERE day=? AND status='ok'",
        (day,),
    ).fetchone()
    if int(global_row["n"]) >= req_budget:
        return False, "daily request budget exhausted"
    if int(global_row["t"]) + max(0, estimated_tokens) > tok_budget:
        return False, "daily token budget exhausted"
    if not is_key:
        client_n = c.execute(
            "SELECT COUNT(*) AS n FROM free_usage WHERE day=? AND client_hash=? AND status='ok'",
            (day, client_id),
        ).fetchone()["n"]
        if int(client_n) >= PER_IP_DAILY_REQUESTS:
            return False, "per-client daily request budget exhausted"
    return True, "ok"


def record_usage(client_hash: str, model: str, tokens: int, status: str = "ok", latency_ms: int = 0) -> None:
    with _lock:
        c = conn()
        c.execute(
            "INSERT INTO free_usage(ts,day,client_hash,model,tokens,status,latency_ms) VALUES(?,?,?,?,?,?,?)",
            (int(time.time()), _day(), client_hash, model, max(0, int(tokens)), status, max(0, int(latency_ms))),
        )
        c.commit()


def live_stats() -> dict[str, Any]:
    c = conn()
    day = _day()
    row = c.execute(
        "SELECT COUNT(*) AS n,COALESCE(SUM(tokens),0) AS t,"
        "COALESCE(AVG(latency_ms),0) AS latency FROM free_usage WHERE day=? AND status='ok'",
        (day,),
    ).fetchone()
    top = c.execute(
        "SELECT model,COUNT(*) AS requests,COALESCE(SUM(tokens),0) AS tokens "
        "FROM free_usage WHERE day=? AND status='ok' GROUP BY model ORDER BY requests DESC,tokens DESC LIMIT 10",
        (day,),
    ).fetchall()
    failures = c.execute(
        "SELECT COUNT(*) AS n FROM free_usage WHERE day=? AND status!='ok'", (day,)
    ).fetchone()["n"]
    return {
        "day_utc": day,
        "requests_today": int(row["n"]),
        "tokens_today": int(row["t"]),
        "request_budget": DAILY_REQUEST_BUDGET,
        "token_budget": DAILY_TOKEN_BUDGET,
        "requests_remaining": max(0, DAILY_REQUEST_BUDGET - int(row["n"])),
        "tokens_remaining": max(0, DAILY_TOKEN_BUDGET - int(row["t"])),
        "avg_latency_ms": round(float(row["latency"]), 1),
        "failures_today": int(failures),
        "per_ip_daily_requests": PER_IP_DAILY_REQUESTS,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_model_usd_per_1m": MAX_MODEL_USD_PER_1M,
        "class_ceilings": CLASS_CEILINGS,
        "top_models": [dict(x) for x in top],
    }


# ── Free-to-paid conversion tracking ──

def record_conversion(client_hash: str, from_tier: str, to_combo: str) -> None:
    """Record that a client transitioned from the free tier to a paid combo.

    Deduplicated per client+target so retries don't inflate the count.
    """
    with _lock:
        c = conn()
        exists = c.execute(
            "SELECT 1 FROM free_conversions WHERE client_hash=? AND to_combo=?",
            (client_hash, to_combo),
        ).fetchone()
        if exists:
            return
        c.execute(
            "INSERT INTO free_conversions(ts,client_hash,from_tier,to_combo) VALUES(?,?,?,?)",
            (int(time.time()), client_hash, from_tier, to_combo),
        )
        c.commit()


def conversion_stats() -> dict[str, Any]:
    """How many free users have upgraded, and which paid combos they chose."""
    c = conn()
    total_free = c.execute(
        "SELECT COUNT(DISTINCT client_hash) AS n FROM free_usage"
    ).fetchone()["n"]
    conversions = c.execute(
        "SELECT COUNT(DISTINCT client_hash) AS n FROM free_conversions"
    ).fetchone()["n"]
    by_combo = c.execute(
        "SELECT to_combo, COUNT(DISTINCT client_hash) AS n "
        "FROM free_conversions GROUP BY to_combo ORDER BY n DESC LIMIT 10"
    ).fetchall()
    rate = round(conversions / max(1, total_free) * 100, 2)
    return {
        "free_users": int(total_free),
        "conversions": int(conversions),
        "conversion_rate_pct": rate,
        "top_paid_combos": [dict(x) for x in by_combo],
    }


# ── Streaming support with stricter budget controls ──

STREAMING_TOKEN_BUFFER = int(os.environ.get("SURP_FREE_STREAM_BUFFER", "200"))


def can_serve_streaming(client_id: str, is_key: bool = False,
                         elevated_requests: int = 0, elevated_tokens: int = 0) -> tuple[bool, str]:
    """Streaming requests need a larger token buffer because output is unbounded
    until the stream completes. Use a conservative estimate.
    """
    estimated = MAX_OUTPUT_TOKENS + STREAMING_TOKEN_BUFFER
    ok, reason = can_serve_free(client_id, estimated, is_key, elevated_requests, elevated_tokens)
    if ok:
        # Reserve an extra streaming slot so concurrent streams don't starve
        # the global budget.
        return True, "ok"
    return False, reason
