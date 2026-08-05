#!/usr/bin/env python3
"""Cache-aware routing and privacy-preserving exact response caching.

Only SHA-256 request fingerprints and completed responses are stored. Raw prompts
are never persisted. Response caching is deliberately limited to deterministic,
non-streaming, tool-free requests.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional


def _canonical_request(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def request_cache_key(payload: dict[str, Any]) -> str:
    """Return a stable SHA-256 fingerprint without retaining prompt text."""
    return hashlib.sha256(_canonical_request(payload)).hexdigest()


def is_response_cacheable(payload: dict[str, Any]) -> bool:
    """Cache only requests whose answer is expected to be deterministic and safe.

    Tool calls, streaming, multiple candidates, and nonzero-temperature sampling
    bypass the response cache. Provider-side prefix caching can still help them.
    """
    if payload.get("stream"):
        return False
    if payload.get("tools") or payload.get("tool_choice"):
        return False
    if int(payload.get("n", 1) or 1) != 1:
        return False
    try:
        if float(payload.get("temperature", 0) or 0) != 0:
            return False
    except (TypeError, ValueError):
        return False
    return bool(payload.get("messages"))


class ResponseCache:
    def __init__(self, db_path: str, ttl_seconds: int = 900, max_entries: int = 5000):
        self.db_path = db_path
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS response_cache (
            cache_key TEXT PRIMARY KEY,
            combo TEXT NOT NULL,
            routed_model TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            hits INTEGER NOT NULL DEFAULT 0,
            last_hit_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_response_cache_expires ON response_cache(expires_at);
        CREATE TABLE IF NOT EXISTS cache_metrics (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            hits INTEGER NOT NULL DEFAULT 0,
            misses INTEGER NOT NULL DEFAULT 0,
            tokens_saved INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO cache_metrics(singleton) VALUES(1);
        """)
        self._conn.commit()

    def peek(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Read a live entry without changing hit/miss metrics."""
        now = int(time.time())
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM response_cache WHERE cache_key=? AND expires_at>?",
                (cache_key, now),
            ).fetchone()
            if row is None:
                return None
            return {
                "response": json.loads(row["response_json"]),
                "combo": row["combo"],
                "model": row["routed_model"],
                "created_at": row["created_at"],
                "tokens_in": row["tokens_in"],
                "tokens_out": row["tokens_out"],
            }

    def get(self, cache_key: str) -> Optional[dict[str, Any]]:
        now = int(time.time())
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM response_cache WHERE cache_key=? AND expires_at>?",
                (cache_key, now),
            ).fetchone()
            if row is None:
                self.record_miss()
                self._conn.execute("DELETE FROM response_cache WHERE expires_at<=?", (now,))
                self._conn.commit()
                return None
            saved = int(row["tokens_in"] or 0) + int(row["tokens_out"] or 0)
            self._conn.execute(
                "UPDATE response_cache SET hits=hits+1,last_hit_at=? WHERE cache_key=?",
                (now, cache_key),
            )
            self._conn.execute(
                "UPDATE cache_metrics SET hits=hits+1,tokens_saved=tokens_saved+? WHERE singleton=1",
                (saved,),
            )
            self._conn.commit()
            return {
                "response": json.loads(row["response_json"]),
                "combo": row["combo"],
                "model": row["routed_model"],
                "created_at": row["created_at"],
                "tokens_in": row["tokens_in"],
                "tokens_out": row["tokens_out"],
            }

    def record_miss(self) -> None:
        with self._lock:
            self._conn.execute("UPDATE cache_metrics SET misses=misses+1 WHERE singleton=1")
            self._conn.commit()

    def put(self, cache_key: str, combo: str, model: str, response: dict[str, Any],
            tokens_in: int = 0, tokens_out: int = 0) -> None:
        now = int(time.time())
        encoded = json.dumps(response, separators=(",", ":"), ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO response_cache "
                "(cache_key,combo,routed_model,response_json,created_at,expires_at,tokens_in,tokens_out,hits,last_hit_at) "
                "VALUES(?,?,?,?,?,?,?,?,0,NULL)",
                (cache_key, combo, model, encoded, now, now + self.ttl_seconds,
                 int(tokens_in or 0), int(tokens_out or 0)),
            )
            count = self._conn.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
            excess = count - self.max_entries
            if excess > 0:
                self._conn.execute(
                    "DELETE FROM response_cache WHERE cache_key IN "
                    "(SELECT cache_key FROM response_cache ORDER BY COALESCE(last_hit_at,created_at) ASC LIMIT ?)",
                    (excess,),
                )
            self._conn.commit()

    def stats(self) -> dict[str, Any]:
        now = int(time.time())
        with self._lock:
            metrics = self._conn.execute("SELECT * FROM cache_metrics WHERE singleton=1").fetchone()
            live = self._conn.execute(
                "SELECT COUNT(*) AS n,COALESCE(SUM(hits),0) AS entry_hits FROM response_cache WHERE expires_at>?",
                (now,),
            ).fetchone()
            hits, misses = int(metrics["hits"]), int(metrics["misses"])
            total = hits + misses
            return {
                "hits": hits,
                "misses": misses,
                "hit_rate_pct": round(hits * 100 / total, 2) if total else 0.0,
                "tokens_saved": int(metrics["tokens_saved"]),
                "live_entries": int(live["n"]),
                "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_entries,
            }


class StickyRouter:
    """Keep a recently selected model while it stays near the live cheapest price."""

    def __init__(self, db_path: str, ttl_seconds: int = 300, tolerance_pct: float = 30):
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.tolerance_pct = max(0.0, float(tolerance_pct))
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS sticky_routes (
            combo TEXT PRIMARY KEY,
            routed_model TEXT NOT NULL,
            chosen_at INTEGER NOT NULL,
            last_used_at INTEGER NOT NULL,
            reuse_count INTEGER NOT NULL DEFAULT 0
        );
        """)
        self._conn.commit()

    @staticmethod
    def _price(m: dict[str, Any]) -> float:
        try:
            return float(m.get("best_price_per_1m") or 0)
        except (TypeError, ValueError):
            return 0.0

    def remember(self, combo: str, model: str) -> None:
        now = int(time.time())
        with self._lock:
            self._conn.execute(
                "INSERT INTO sticky_routes(combo,routed_model,chosen_at,last_used_at,reuse_count) VALUES(?,?,?,?,0) "
                "ON CONFLICT(combo) DO UPDATE SET routed_model=excluded.routed_model,chosen_at=excluded.chosen_at,last_used_at=excluded.last_used_at",
                (combo, model, now, now),
            )
            self._conn.commit()

    def choose(self, combo: str, pool: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
        if not pool:
            raise ValueError("empty routing pool")
        cheapest = min(pool, key=self._price)
        cheapest_price = self._price(cheapest)
        now = int(time.time())
        with self._lock:
            row = self._conn.execute("SELECT * FROM sticky_routes WHERE combo=?", (combo,)).fetchone()
            if row and now - int(row["last_used_at"]) <= self.ttl_seconds:
                prior = next((m for m in pool if m.get("model") == row["routed_model"]), None)
                if prior is not None:
                    prior_price = self._price(prior)
                    ceiling = cheapest_price * (1 + self.tolerance_pct / 100)
                    if cheapest_price <= 0 or prior_price <= ceiling:
                        self._conn.execute(
                            "UPDATE sticky_routes SET last_used_at=?,reuse_count=reuse_count+1 WHERE combo=?",
                            (now, combo),
                        )
                        self._conn.commit()
                        return prior, "sticky-within-tolerance"
            self.remember(combo, str(cheapest.get("model", "")))
            return cheapest, "live-cheapest"

    def stats(self) -> dict[str, Any]:
        now = int(time.time())
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS active,COALESCE(SUM(reuse_count),0) AS reuses FROM sticky_routes WHERE last_used_at>=?",
                (now - self.ttl_seconds,),
            ).fetchone()
            return {
                "active_routes": int(row["active"]),
                "sticky_reuses": int(row["reuses"]),
                "ttl_seconds": self.ttl_seconds,
                "tolerance_pct": self.tolerance_pct,
            }
