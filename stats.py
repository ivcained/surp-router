#!/usr/bin/env python3
"""
Stats, API keys, and combo history for surp.ivc.lol.

SQLite-backed. Three tables:
  - requests:      every paid inference request (combo, model, price, payer, tx)
  - combo_snapshots: periodic cheapest-model record per combo (for sparklines)
  - api_keys:      prepaid-balance keys for non-x402 access

All writes are fire-and-forget safe — a stats failure must never break a request.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from typing import Any, Optional

DB_PATH = os.environ.get("SURP_DB", "/root/.hermes/surp-router/combos.db")

_schema = """
CREATE TABLE IF NOT EXISTS requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    combo       TEXT NOT NULL,
    routed_model TEXT,
    payer       TEXT,
    amount_usdc_microcents INTEGER,
    tx_hash     TEXT,
    payment_method TEXT DEFAULT 'x402',
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    latency_ms  INTEGER
);

CREATE TABLE IF NOT EXISTS combo_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    combo       TEXT NOT NULL,
    routed_model TEXT NOT NULL,
    price_per_1m INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash    TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    balance_usdc_microcents INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL,
    last_used   INTEGER,
    total_requests INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rate_limits (
    ip          TEXT NOT NULL,
    bucket      TEXT NOT NULL,
    ts          INTEGER NOT NULL,
    PRIMARY KEY (ip, bucket)
);

CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts);
CREATE INDEX IF NOT EXISTS idx_requests_payer ON requests(payer);
CREATE INDEX IF NOT EXISTS idx_snapshots_combo_ts ON combo_snapshots(combo, ts);
"""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# Module-level connection — safe with WAL + busy_timeout
_conn: Optional[sqlite3.Connection] = None

def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _db()
        for stmt in _schema.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                _conn.execute(stmt)
        _conn.commit()
    return _conn


# ──────────────────────────────────────────────────────────────────────────────
# Request logging
# ──────────────────────────────────────────────────────────────────────────────

def log_request(combo: str, routed_model: str = "", payer: str = "",
                amount_usdc_microcents: int = 0, tx_hash: str = "",
                payment_method: str = "x402", tokens_in: int = 0,
                tokens_out: int = 0, latency_ms: int = 0) -> None:
    try:
        conn().execute(
            "INSERT INTO requests (ts, combo, routed_model, payer, amount_usdc_microcents, "
            "tx_hash, payment_method, tokens_in, tokens_out, latency_ms) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (int(time.time()), combo, routed_model, payer.lower() if payer else "",
             amount_usdc_microcents, tx_hash, payment_method, tokens_in, tokens_out, latency_ms),
        )
        conn().commit()
    except Exception:
        pass  # stats are best-effort


# ──────────────────────────────────────────────────────────────────────────────
# Combo snapshots (for history sparklines)
# ──────────────────────────────────────────────────────────────────────────────

_last_snapshot_ts: float = 0.0
SNAPSHOT_INTERVAL = 300  # 5 minutes — don't snapshot more often than this


def maybe_snapshot(combos: list[tuple[str, str, float]]) -> None:
    """Take a snapshot of current combo resolutions if enough time passed.

    combos: list of (combo_name, routed_model, price_per_1m_atomic)
    """
    global _last_snapshot_ts
    now = time.time()
    if now - _last_snapshot_ts < SNAPSHOT_INTERVAL:
        return
    _last_snapshot_ts = now
    try:
        ts = int(now)
        for combo, model, price in combos:
            if model:
                conn().execute(
                    "INSERT INTO combo_snapshots (ts, combo, routed_model, price_per_1m) VALUES (?,?,?,?)",
                    (ts, combo, model, int(price)),
                )
        conn().commit()
    except Exception:
        pass


def combo_history(combo: str, hours: int = 24) -> list[dict]:
    """Return snapshots for a combo, sampled for a sparkline."""
    try:
        since = int(time.time()) - hours * 3600
        rows = conn().execute(
            "SELECT ts, routed_model, price_per_1m FROM combo_snapshots "
            "WHERE combo=? AND ts >= ? ORDER BY ts ASC",
            (combo, since),
        ).fetchall()
        return [{"ts": r[0], "model": r[1], "price": r[2]} for r in rows]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Global stats
# ──────────────────────────────────────────────────────────────────────────────

def global_stats() -> dict:
    try:
        c = conn()
        total = c.execute("SELECT COUNT(*) as n FROM requests").fetchone()["n"]
        total_usd = c.execute(
            "SELECT COALESCE(SUM(amount_usdc_microcents), 0) as s FROM requests"
        ).fetchone()["s"]
        last_24h = c.execute(
            "SELECT COUNT(*) as n FROM requests WHERE ts >= ?", (int(time.time()) - 86400,)
        ).fetchone()["n"]
        unique_payers = c.execute(
            "SELECT COUNT(DISTINCT payer) as n FROM requests WHERE payer != ''"
        ).fetchone()["n"]
        top_combos = c.execute(
            "SELECT combo, COUNT(*) as n FROM requests GROUP BY combo ORDER BY n DESC LIMIT 5"
        ).fetchall()
        top_models = c.execute(
            "SELECT routed_model, COUNT(*) as n FROM requests WHERE routed_model != '' "
            "GROUP BY routed_model ORDER BY n DESC LIMIT 5"
        ).fetchall()
        last_request_ts = c.execute(
            "SELECT MAX(ts) as t FROM requests"
        ).fetchone()["t"]
        return {
            "total_requests": total,
            "total_usdc_cents": total_usd // 100 if total_usd else 0,
            "requests_24h": last_24h,
            "unique_payers": unique_payers,
            "top_combos": [{"combo": r["combo"], "count": r["n"]} for r in top_combos],
            "top_models": [{"model": r["routed_model"], "count": r["n"]} for r in top_models],
            "last_request_ts": last_request_ts,
        }
    except Exception as e:
        return {"error": str(e)}


def payer_stats(address: str) -> dict:
    """Usage stats for a specific wallet address."""
    try:
        addr = address.lower().strip()
        c = conn()
        total = c.execute(
            "SELECT COUNT(*) as n, COALESCE(SUM(amount_usdc_microcents),0) as s FROM requests WHERE payer=?",
            (addr,),
        ).fetchone()
        recent = c.execute(
            "SELECT ts, combo, routed_model, amount_usdc_microcents, tx_hash, payment_method "
            "FROM requests WHERE payer=? ORDER BY ts DESC LIMIT 50",
            (addr,),
        ).fetchall()
        return {
            "address": address,
            "total_requests": total["n"],
            "total_spent_usd_cents": total["s"] // 100 if total["s"] else 0,
            "recent": [
                {
                    "ts": r["ts"], "combo": r["combo"], "model": r["routed_model"],
                    "cents": r["amount_usdc_microcents"] // 100 if r["amount_usdc_microcents"] else 0,
                    "tx": r["tx_hash"], "method": r["payment_method"],
                }
                for r in recent
            ],
        }
    except Exception as e:
        return {"error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# API keys (prepaid balance, non-x402 access)
# ──────────────────────────────────────────────────────────────────────────────

def create_api_key(label: str, initial_balance_microcents: int = 0) -> dict:
    """Create a new API key. Returns the raw key once (store the hash only)."""
    raw_key = "sk-surp-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    try:
        conn().execute(
            "INSERT INTO api_keys (key_hash, label, balance_usdc_microcents, created_at) VALUES (?,?,?,?)",
            (key_hash, label[:60], initial_balance_microcents, int(time.time())),
        )
        conn().commit()
        return {"key": raw_key, "key_hash": key_hash, "label": label[:60],
                "balance_microcents": initial_balance_microcents}
    except Exception as e:
        return {"error": str(e)}


def validate_api_key(raw_key: str) -> Optional[dict]:
    """Validate a key and return its record, or None."""
    if not raw_key or not raw_key.startswith("sk-surp-"):
        return None
    key_hash = hashlib.sha256(raw_key.strip().encode()).hexdigest()
    try:
        row = conn().execute(
            "SELECT key_hash, label, balance_usdc_microcents, created_at, last_used, total_requests "
            "FROM api_keys WHERE key_hash=?",
            (key_hash,),
        ).fetchone()
        if not row:
            return None
        return dict(row)
    except Exception:
        return None


def charge_api_key(key_hash: str, microcents: int) -> bool:
    """Deduct from balance. Returns True if sufficient balance, False otherwise."""
    try:
        row = conn().execute(
            "SELECT balance_usdc_microcents FROM api_keys WHERE key_hash=?",
            (key_hash,),
        ).fetchone()
        if not row or row["balance_usdc_microcents"] < microcents:
            return False
        conn().execute(
            "UPDATE api_keys SET balance_usdc_microcents = balance_usdc_microcents - ?, "
            "total_requests = total_requests + 1, last_used = ? WHERE key_hash=?",
            (microcents, int(time.time()), key_hash),
        )
        conn().commit()
        return True
    except Exception:
        return False


def top_up_api_key(key_hash: str, microcents: int) -> bool:
    """Add to a key's balance."""
    try:
        conn().execute(
            "UPDATE api_keys SET balance_usdc_microcents = balance_usdc_microcents + ? WHERE key_hash=?",
            (microcents, key_hash),
        )
        conn().commit()
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Rate limiting (sliding window per IP per endpoint bucket)
# ──────────────────────────────────────────────────────────────────────────────

RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 60     # requests per window per IP on free endpoints


def check_rate_limit(ip: str, bucket: str = "free") -> tuple[bool, int]:
    """Returns (allowed, remaining_in_window)."""
    try:
        now = int(time.time())
        cutoff = now - RATE_LIMIT_WINDOW
        c = conn()
        # Purge old entries for this ip+bucket
        c.execute("DELETE FROM rate_limits WHERE ip=? AND bucket=? AND ts < ?", (ip, bucket, cutoff))
        # Count current window
        row = c.execute(
            "SELECT COUNT(*) as n FROM rate_limits WHERE ip=? AND bucket=? AND ts >= ?",
            (ip, bucket, cutoff),
        ).fetchone()
        count = row["n"] if row else 0
        if count >= RATE_LIMIT_MAX:
            c.commit()
            return False, 0
        # Keep one row per IP+bucket and update its timestamp instead of trying
        # to insert duplicate primary keys. This is a coarse 60-second limiter,
        # but crucially never leaves a failed transaction holding the DB lock.
        c.execute(
            "INSERT INTO rate_limits (ip, bucket, ts) VALUES (?,?,?) "
            "ON CONFLICT(ip,bucket) DO UPDATE SET ts=excluded.ts",
            (ip, bucket, now),
        )
        c.commit()
        return True, RATE_LIMIT_MAX - count - 1
    except Exception:
        try:
            conn().rollback()
        except Exception:
            pass
        return True, 999  # fail open
