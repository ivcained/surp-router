#!/usr/bin/env python3
"""Advisory, privacy-preserving vote ledger for the cache flywheel proposal.

Voter identity is a salted SHA-256 hash of a caller-chosen handle or, for
anonymous voters, of their IP address. Raw handles and IPs are never stored.
One fingerprint = one current vote. A voter can change their choice, but they
cannot multiply their ballot.
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

_DB_PATH = os.environ.get("SURP_DB", rl.DB_PATH)
_SALT = os.environ.get("SURP_VOTE_SALT") or secrets.token_urlsafe(32)

_OPTIONS: dict[str, dict[str, str]] = {
    "offchain": {"label": "Keep it off-chain (safest for now)"},
    "juicebox": {"label": "Juicebox treasury + Merkle claims"},
    "revnet": {"label": "RevNet revenue-backed token"},
    "hybrid": {"label": "Hybrid: off-chain now, RevNet later"},
}

_MAX_COMMENT = 280
_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _db()
        _conn.executescript("""
        CREATE TABLE IF NOT EXISTS proposal_votes (
            voter_hash TEXT PRIMARY KEY,
            option      TEXT NOT NULL,
            comment     TEXT,
            ts          INTEGER NOT NULL,
            changed     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_votes_option ON proposal_votes(option);
        """)
        _conn.commit()
    return _conn


def _fingerprint(handle: str, ip: str) -> str:
    raw = (handle.strip() or ip or "anon").lower()
    return hashlib.sha256(f"{_SALT}:{raw}".encode()).hexdigest()


def reset_for_tests() -> None:
    """Wipe state and re-open the connection (test-only)."""
    global _conn, _SALT
    with _lock:
        _SALT = os.environ.get("SURP_VOTE_SALT") or secrets.token_urlsafe(32)
        _conn = None
        c = conn()
        c.executescript("DROP TABLE IF EXISTS proposal_votes;")
        c.commit()
        # Force schema recreation on the next conn() call.
        _conn = None
        conn()


def cast_vote(handle: str, option: str, comment: str, ip: str = "") -> dict[str, Any]:
    if option not in _OPTIONS:
        return {"ok": False, "error": f"invalid option; choose one of: {list(_OPTIONS)}"}
    identity = (handle or "").strip() or (ip or "").strip()
    if not identity:
        return {"ok": False, "error": "provide a handle or identify via IP"}
    comment = (comment or "").strip()[:_MAX_COMMENT]
    fp = _fingerprint(handle or "", ip)
    now = int(time.time())
    with _lock:
        c = conn()
        existing = c.execute("SELECT option FROM proposal_votes WHERE voter_hash=?", (fp,)).fetchone()
        if existing is None:
            c.execute(
                "INSERT INTO proposal_votes(voter_hash,option,comment,ts,changed) VALUES(?,?,?,?,0)",
                (fp, option, comment, now),
            )
        else:
            c.execute(
                "UPDATE proposal_votes SET option=?,comment=?,ts=?,changed=changed+1 WHERE voter_hash=?",
                (option, comment, now, fp),
            )
        c.commit()
        return {"ok": True, "option": option,
                "label": _OPTIONS[option]["label"], "changed_vote": existing is not None}


def results() -> dict[str, Any]:
    with _lock:
        c = conn()
        rows = c.execute("SELECT option,COUNT(*) AS n FROM proposal_votes GROUP BY option").fetchall()
        total = c.execute("SELECT COUNT(*) AS n FROM proposal_votes").fetchone()["n"]
        changed = c.execute("SELECT COALESCE(SUM(changed),0) AS s FROM proposal_votes").fetchone()["s"]
        options = {}
        for opt in _OPTIONS:
            options[opt] = {"label": _OPTIONS[opt]["label"], "votes": 0, "pct": 0.0}
        for r in rows:
            options[r["option"]]["votes"] = r["n"]
        if total:
            for opt in options:
                options[opt]["pct"] = round(options[opt]["votes"] * 100 / total, 2)
        return {
            "total_votes": total,
            "changed_votes": int(changed),
            "options": options,
            "max_comment": _MAX_COMMENT,
        }


def recent_comments(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        c = conn()
        rows = c.execute(
            "SELECT option,comment,ts FROM proposal_votes WHERE comment != '' "
            "ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"option": r["option"], "comment": r["comment"], "ts": r["ts"]} for r in rows]
