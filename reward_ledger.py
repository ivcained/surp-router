"""Off-chain reward ledger for the surp cache flywheel.

Tracks reward-token ("SRP") balances per payer, minted when cache value is
created or realized. Moves no money on-chain — it is the accounting layer that
a later Juicebox/RevNet deployment can mirror or replace.

Token value floats against a rebate pool: value_per_srp = pool_usd_cents /
srp_outstanding. As protocol revenue flows in, each SRP appreciates. That is
the RevNet redemption mechanism done off-chain.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional


DB_PATH = os.environ.get("SURP_DB", "/root/.hermes/surp-router/combos.db")

# Reward policy — all configurable. SRP is an integer "point" unit; 1 SRP per
# token of cache value created/realized, scaled by these weights.
WRITE_REWARD_PER_TOKEN = float(os.environ.get("SURP_WRITE_REWARD_PER_TOKEN", "1.0"))
HIT_AUTHOR_REWARD_PER_TOKEN = float(os.environ.get("SURP_HIT_AUTHOR_REWARD_PER_TOKEN", "2.0"))
HIT_READER_REWARD_PER_TOKEN = float(os.environ.get("SURP_HIT_READER_REWARD_PER_TOKEN", "0.5"))

# Fraction of gateway markup (in microcents) earmarked to the rebate pool on
# every paid request. 0.5 = half of markup backs the token.
REBATE_POOL_SHARE = float(os.environ.get("SURP_REBATE_POOL_SHARE", "0.5"))

# Sybil guard: cap rewards per unique cache entry within this window.
DEDUP_WINDOW_S = int(os.environ.get("SURP_REWARD_DEDUP_WINDOW_S", "3600"))

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


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
        CREATE TABLE IF NOT EXISTS reward_ledger (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            payer       TEXT NOT NULL,
            role        TEXT NOT NULL,
            combo       TEXT NOT NULL,
            cache_key   TEXT NOT NULL,
            tokens_saved INTEGER NOT NULL DEFAULT 0,
            srp_minted  INTEGER NOT NULL DEFAULT 0,
            reason      TEXT
        );
        CREATE TABLE IF NOT EXISTS reward_balances (
            payer       TEXT PRIMARY KEY,
            balance     INTEGER NOT NULL DEFAULT 0,
            lifetime_earned INTEGER NOT NULL DEFAULT 0,
            lifetime_burned INTEGER NOT NULL DEFAULT 0,
            last_event_ts INTEGER
        );
        CREATE TABLE IF NOT EXISTS reward_pool (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            microcents INTEGER NOT NULL DEFAULT 0,
            total_srp_minted INTEGER NOT NULL DEFAULT 0,
            total_srp_burned INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO reward_pool(singleton) VALUES(1);
        CREATE INDEX IF NOT EXISTS idx_reward_payer ON reward_ledger(payer);
        CREATE INDEX IF NOT EXISTS idx_reward_cache ON reward_ledger(cache_key, role, ts);
        """)
        _conn.commit()
    return _conn


def _recent_reward_exists(cache_key: str, role: str, payer: str, window_s: int) -> bool:
    cutoff = int(time.time()) - window_s
    row = conn().execute(
        "SELECT 1 FROM reward_ledger WHERE cache_key=? AND role=? AND payer=? AND ts>=? LIMIT 1",
        (cache_key, role, payer, cutoff),
    ).fetchone()
    return row is not None


def mint(
    payer: str,
    role: str,
    combo: str,
    cache_key: str,
    tokens_saved: int,
    weight_per_token: float,
    reason: str = "",
) -> int:
    """Mint SRP to a payer for a cache event. Returns SRP minted (0 if deduped).

    role is 'cache_write', 'cache_hit_author', or 'cache_hit_reader'.
    A given (cache_key, role, payer) only earns once per DEDUP_WINDOW_S to
    prevent an agent from farming its own cache by re-reading it.
    """
    if not payer or tokens_saved <= 0 or weight_per_token <= 0:
        return 0
    if _recent_reward_exists(cache_key, role, payer, DEDUP_WINDOW_S):
        return 0
    srp = max(1, int(tokens_saved * weight_per_token))
    now = int(time.time())
    with _lock:
        c = conn()
        c.execute(
            "INSERT INTO reward_ledger(ts,payer,role,combo,cache_key,tokens_saved,srp_minted,reason) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (now, payer, role, combo, cache_key, int(tokens_saved), srp, reason),
        )
        # Upsert balance: on insert, balance/lifetime_earn the full srp; on
        # conflict, add srp to both. Using excluded.* keeps the math identical
        # for new vs existing rows.
        c.execute(
            "INSERT INTO reward_balances(payer,balance,lifetime_earned,lifetime_burned,last_event_ts) "
            "VALUES(?,?,?,0,?) "
            "ON CONFLICT(payer) DO UPDATE SET "
            "balance=balance+excluded.balance,"
            "lifetime_earned=lifetime_earned+excluded.lifetime_earned,"
            "last_event_ts=excluded.last_event_ts",
            (payer, srp, srp, now),
        )
        c.execute(
            "UPDATE reward_pool SET total_srp_minted=total_srp_minted+? WHERE singleton=1",
            (srp,),
        )
        c.commit()
    return srp


def fund_pool(microcents: int) -> None:
    """Earmark gateway revenue to the rebate pool that backs SRP value."""
    if microcents <= 0:
        return
    with _lock:
        c = conn()
        c.execute("UPDATE reward_pool SET microcents=microcents+? WHERE singleton=1", (microcents,))
        c.commit()


def burn(payer: str, srp: int) -> dict[str, Any]:
    """Burn SRP for a redemption claim. Off-chain: just debits the balance.

    Returns the claim details. The actual USDC transfer still requires a signed
    transaction — this function only authorizes the bookkeeping.
    """
    srp = int(srp)
    if srp <= 0 or not payer:
        return {"error": "invalid burn amount"}
    with _lock:
        c = conn()
        row = c.execute("SELECT balance FROM reward_balances WHERE payer=?", (payer,)).fetchone()
        if not row or row["balance"] < srp:
            return {"error": "insufficient SRP balance",
                    "balance": int(row["balance"]) if row else 0}
        pool = c.execute("SELECT * FROM reward_pool WHERE singleton=1").fetchone()
        outstanding = int(pool["total_srp_minted"]) - int(pool["total_srp_burned"])
        value_per_srp = (float(pool["microcents"]) / outstanding) if outstanding else 0.0
        claim_microcents = int(srp * value_per_srp)
        now = int(time.time())
        c.execute(
            "UPDATE reward_balances SET balance=balance-?,lifetime_burned=lifetime_burned+?,"
            "last_event_ts=? WHERE payer=?",
            (srp, srp, now, payer),
        )
        c.execute(
            "UPDATE reward_pool SET microcents=microcents-?,total_srp_burned=total_srp_burned+? "
            "WHERE singleton=1",
            (claim_microcents, srp),
        )
        c.execute(
            "INSERT INTO reward_ledger(ts,payer,role,combo,cache_key,tokens_saved,srp_minted,reason) "
            "VALUES(?,?,?,?,0,?,0,?)",
            (now, payer, "redemption", "—", "—", f"burn {srp} SRP"),
        )
        c.commit()
        return {
            "burned_srp": srp,
            "claim_usd_cents": claim_microcents / 10_000,
            "value_per_srp_cents": round(value_per_srp / 10_000, 6),
            "remaining_balance": int(row["balance"]) - srp,
        }


def cache_author(cache_key: str) -> Optional[str]:
    """Return the payer who originally funded this cache entry, if recorded."""
    row = conn().execute(
        "SELECT payer FROM reward_ledger WHERE cache_key=? AND role='cache_write' "
        "ORDER BY ts ASC LIMIT 1",
        (cache_key,),
    ).fetchone()
    return str(row["payer"]) if row else None


def balance(payer: str) -> dict[str, Any]:
    if not payer:
        return {"payer": "", "balance": 0}
    c = conn()
    row = c.execute("SELECT * FROM reward_balances WHERE payer=?", (payer,)).fetchone()
    pool = c.execute("SELECT * FROM reward_pool WHERE singleton=1").fetchone()
    outstanding = int(pool["total_srp_minted"]) - int(pool["total_srp_burned"]) if pool else 0
    value_per_srp = (float(pool["microcents"]) / outstanding) if pool and outstanding else 0.0
    bal = int(row["balance"]) if row else 0
    pending_claim_cents = (bal * value_per_srp) / 10_000
    return {
        "payer": payer,
        "balance_srp": bal,
        "lifetime_earned": int(row["lifetime_earned"]) if row else 0,
        "lifetime_burned": int(row["lifetime_burned"]) if row else 0,
        "value_per_srp_cents": round(value_per_srp / 10_000, 6),
        "pending_claim_usd": round(pending_claim_cents / 100, 4),
        "rebate_pool_usd": round((float(pool["microcents"]) if pool else 0) / 1_000_000, 4),
    }


def global_stats() -> dict[str, Any]:
    c = conn()
    pool = c.execute("SELECT * FROM reward_pool WHERE singleton=1").fetchone()
    outstanding = int(pool["total_srp_minted"]) - int(pool["total_srp_burned"]) if pool else 0
    value_per_srp = (float(pool["microcents"]) / outstanding) if pool and outstanding else 0.0
    holders = c.execute("SELECT COUNT(*) AS n FROM reward_balances WHERE balance>0").fetchone()
    top = c.execute(
        "SELECT payer,balance,lifetime_earned FROM reward_balances ORDER BY balance DESC LIMIT 10"
    ).fetchall()
    return {
        "rebate_pool_usd": round((float(pool["microcents"]) if pool else 0) / 1_000_000, 4),
        "total_srp_minted": int(pool["total_srp_minted"]) if pool else 0,
        "total_srp_burned": int(pool["total_srp_burned"]) if pool else 0,
        "srp_outstanding": outstanding,
        "value_per_srp_cents": round(value_per_srp / 10_000, 6),
        "holders": int(holders["n"]),
        "top_holders": [dict(r) for r in top],
    }
