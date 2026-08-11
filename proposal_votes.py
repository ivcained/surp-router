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

# Second proposal: should surp deploy the SRP reward token contract on Base?
_SRP_OPTIONS: dict[str, dict[str, str]] = {
    "deploy": {"label": "Deploy SRP on Base mainnet now (custom ERC-20)"},
    "deploy-testnet": {"label": "Deploy on Base Sepolia first, mainnet after audit"},
    "wait": {"label": "Wait — keep off-chain until volume justifies cost"},
    "no": {"label": "Don't deploy a token at all"},
}

_PROMPTS: dict[str, dict[str, dict[str, str]]] = {
    "flywheel": _OPTIONS,
    "srp-contract": _SRP_OPTIONS,
}

_DEFAULT_PROPOSAL = "flywheel"

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
            voter_hash TEXT NOT NULL,
            proposal    TEXT NOT NULL DEFAULT 'flywheel',
            option      TEXT NOT NULL,
            comment     TEXT,
            ts          INTEGER NOT NULL,
            changed     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (voter_hash, proposal)
        );
        CREATE INDEX IF NOT EXISTS idx_votes_option ON proposal_votes(proposal, option);
        """)
        # Migration for DBs created before the multi-proposal change.
        cols = [r["name"] for r in _conn.execute("PRAGMA table_info(proposal_votes)").fetchall()]
        if "proposal" not in cols:
            _conn.execute("ALTER TABLE proposal_votes ADD COLUMN proposal TEXT NOT NULL DEFAULT 'flywheel'")
        # PK migration: old schema had voter_hash as sole PK. SQLite can't alter
        # a PK, so rebuild the table (safe: single-column PK rows are unique).
        pks = [r["name"] for r in _conn.execute("PRAGMA table_info(proposal_votes)").fetchall()
               if r["pk"]]
        if pks == ["voter_hash"]:
            _conn.executescript("""
            CREATE TABLE proposal_votes_new (
                voter_hash TEXT NOT NULL,
                proposal    TEXT NOT NULL DEFAULT 'flywheel',
                option      TEXT NOT NULL,
                comment     TEXT,
                ts          INTEGER NOT NULL,
                changed     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (voter_hash, proposal)
            );
            INSERT INTO proposal_votes_new (voter_hash, proposal, option, comment, ts, changed)
                SELECT voter_hash, 'flywheel', option, comment, ts, changed FROM proposal_votes;
            DROP TABLE proposal_votes;
            ALTER TABLE proposal_votes_new RENAME TO proposal_votes;
            CREATE INDEX IF NOT EXISTS idx_votes_option ON proposal_votes(proposal, option);
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
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
        c = _db()
        c.executescript("DROP TABLE IF EXISTS proposal_votes;")
        c.commit()
        c.close()


def _options_for(proposal: str) -> dict[str, dict[str, str]]:
    return _PROMPTS.get(proposal, _PROMPTS[_DEFAULT_PROPOSAL])


def cast_vote(handle: str, option: str, comment: str, ip: str = "",
              proposal: str = _DEFAULT_PROPOSAL) -> dict[str, Any]:
    opts = _options_for(proposal)
    if option not in opts:
        return {"ok": False, "error": f"invalid option; choose one of: {list(opts)}"}
    identity = (handle or "").strip() or (ip or "").strip()
    if not identity:
        return {"ok": False, "error": "provide a handle or identify via IP"}
    comment = (comment or "").strip()[:_MAX_COMMENT]
    fp = _fingerprint(handle or "", ip)
    now = int(time.time())
    with _lock:
        c = conn()
        existing = c.execute(
            "SELECT option FROM proposal_votes WHERE voter_hash=? AND proposal=?",
            (fp, proposal),
        ).fetchone()
        if existing is None:
            c.execute(
                "INSERT INTO proposal_votes(voter_hash,proposal,option,comment,ts,changed) VALUES(?,?,?,?,?,0)",
                (fp, proposal, option, comment, now),
            )
        else:
            c.execute(
                "UPDATE proposal_votes SET option=?,comment=?,ts=?,changed=changed+1 "
                "WHERE voter_hash=? AND proposal=?",
                (option, comment, now, fp, proposal),
            )
        c.commit()
        return {"ok": True, "option": option,
                "label": opts[option]["label"], "changed_vote": existing is not None}


def results(proposal: str = _DEFAULT_PROPOSAL) -> dict[str, Any]:
    opts = _options_for(proposal)
    with _lock:
        c = conn()
        rows = c.execute(
            "SELECT option,COUNT(*) AS n FROM proposal_votes WHERE proposal=? GROUP BY option",
            (proposal,),
        ).fetchall()
        total = c.execute(
            "SELECT COUNT(*) AS n FROM proposal_votes WHERE proposal=?", (proposal,)
        ).fetchone()["n"]
        changed = c.execute(
            "SELECT COALESCE(SUM(changed),0) AS s FROM proposal_votes WHERE proposal=?",
            (proposal,),
        ).fetchone()["s"]
        options = {}
        for opt in opts:
            options[opt] = {"label": opts[opt]["label"], "votes": 0, "pct": 0.0}
        for r in rows:
            options[r["option"]]["votes"] = r["n"]
        if total:
            for opt in options:
                options[opt]["pct"] = round(options[opt]["votes"] * 100 / total, 2)
        return {
            "proposal": proposal,
            "total_votes": total,
            "changed_votes": int(changed),
            "options": options,
            "max_comment": _MAX_COMMENT,
        }


def recent_comments(limit: int = 20, proposal: str = _DEFAULT_PROPOSAL) -> list[dict[str, Any]]:
    with _lock:
        c = conn()
        rows = c.execute(
            "SELECT option,comment,ts FROM proposal_votes "
            "WHERE comment != '' AND proposal=? ORDER BY ts DESC LIMIT ?",
            (proposal, limit),
        ).fetchall()
        return [{"option": r["option"], "comment": r["comment"], "ts": r["ts"]} for r in rows]
