"""Community feedback board for the token-gating proposal.

Salted-hash identities (no raw wallet/IP stored), categorized feedback,
upvotes deduplicated per voter, recent feed. Same privacy stance as the
advisory vote ledger.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
import time
from typing import Any

import reward_ledger as rl

DB_PATH = os.environ.get("SURP_DB", rl.DB_PATH)
_SALT = os.environ.get("SURP_FEEDBACK_SALT") or secrets.token_urlsafe(32)
_MAX_MESSAGE = 280
_CATEGORIES = ("idea", "concern", "question", "support")

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
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
        CREATE TABLE IF NOT EXISTS community_feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            identity    TEXT NOT NULL,
            category    TEXT NOT NULL,
            message     TEXT NOT NULL,
            upvotes     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_feedback_ts ON community_feedback(ts);
        CREATE TABLE IF NOT EXISTS feedback_upvotes (
            feedback_id INTEGER NOT NULL,
            voter       TEXT NOT NULL,
            PRIMARY KEY (feedback_id, voter)
        );
        """)
        _conn.commit()
    return _conn


def _fingerprint(handle: str, ip: str) -> str:
    raw = (handle.strip() or ip or "anon").lower()
    return hashlib.sha256(f"{_SALT}:{raw}".encode()).hexdigest()


def submit(handle: str, category: str, message: str, ip: str = "") -> dict[str, Any]:
    if category not in _CATEGORIES:
        return {"ok": False, "error": f"invalid category; choose one of {list(_CATEGORIES)}"}
    message = (message or "").strip()
    if not message:
        return {"ok": False, "error": "message cannot be empty"}
    message = message[:_MAX_MESSAGE]
    identity = _fingerprint(handle or "", ip)
    now = int(time.time())
    with _lock:
        c = conn()
        cur = c.execute(
            "INSERT INTO community_feedback(ts,identity,category,message,upvotes) VALUES(?,?,?,?,0)",
            (now, identity, category, message),
        )
        c.commit()
        return {"ok": True, "id": cur.lastrowid, "category": category}


def upvote(feedback_id: int, handle: str, ip: str = "") -> dict[str, Any]:
    voter = _fingerprint(handle or "", ip)
    with _lock:
        c = conn()
        try:
            c.execute(
                "INSERT INTO feedback_upvotes(feedback_id,voter) VALUES(?,?)",
                (feedback_id, voter),
            )
            c.execute(
                "UPDATE community_feedback SET upvotes=upvotes+1 WHERE id=?",
                (feedback_id,),
            )
            c.commit()
            return {"ok": True, "id": feedback_id}
        except sqlite3.IntegrityError:
            return {"ok": False, "error": "already upvoted"}


def recent(limit: int = 20) -> list[dict[str, Any]]:
    rows = conn().execute(
        "SELECT id,ts,category,message,upvotes FROM community_feedback "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def summary() -> dict[str, int]:
    c = conn()
    counts: dict[str, int] = {cat: 0 for cat in _CATEGORIES}
    for row in c.execute(
        "SELECT category, COUNT(*) AS n FROM community_feedback GROUP BY category"
    ).fetchall():
        counts[row["category"]] = int(row["n"])
    return counts
