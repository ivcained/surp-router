"""User accounts, API keys, and usage tracking for surp.

SQLite-backed storage for:
  - users (Privy user id → internal user record + embedded wallet address)
  - api_keys (per-user API keys with spend budgets + lifetime tracking)
  - usage (per-request log: model, tokens, cost, tx hash, timestamp)

On-chain balance reads via web3.py (Base mainnet USDC, 6 decimals).

All writes are thread-safe (WAL mode, busy_timeout). All queries are
fault-isolated: a DB error never breaks a paid inference request.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from typing import Any

from web3 import Web3

log = logging.getLogger("surp.accounts")

_DB_PATH = os.environ.get("SURP_USER_DB", os.path.join(os.path.dirname(__file__), "users.db"))
_WAL = os.path.join(os.path.dirname(__file__), "users.db-wal")
_LOCK = threading.Lock()

# Base mainnet + USDC (native, 6 decimals, EIP-3009)
_RPC = os.environ.get("SURP_RPC_URL", "https://mainnet.base.org")
_USDC = Web3.to_checksum_address(os.environ.get(
    "SURP_ASSET", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"))
_w3 = Web3(Web3.HTTPProvider(_RPC, request_kwargs={"timeout": 10}))

_BALANCE_OF = "0x70a08231"  # balanceOf(address)


def _connect() -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode + busy timeout."""
    conn = sqlite3.connect(_DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db() -> None:
    """Create tables if they don't exist."""
    with _LOCK:
        conn = _connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    privy_user_id TEXT PRIMARY KEY,
                    wallet_address TEXT UNIQUE,
                    email TEXT,
                    created_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    key_hash TEXT UNIQUE NOT NULL,
                    name TEXT,
                    budget_cents INTEGER DEFAULT 0,
                    spent_cents INTEGER DEFAULT 0,
                    created_at INTEGER,
                    FOREIGN KEY(user_id) REFERENCES users(privy_user_id)
                );
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    api_key_id TEXT,
                    model TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost_cents INTEGER,
                    tx_hash TEXT,
                    created_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_usage_user ON usage(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_usage_key ON usage(api_key_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_usage_model ON usage(user_id, model);
            """)
        finally:
            conn.close()


_init_db()


# ─── Users ─────────────────────────────────────────────────────────────────────

def upsert_user(privy_user_id: str, wallet_address: str, email: str = "") -> None:
    """Insert or update a user record (called on login)."""
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO users (privy_user_id, wallet_address, email, created_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(privy_user_id) DO UPDATE SET "
                "wallet_address=excluded.wallet_address, email=excluded.email",
                (privy_user_id, wallet_address.lower(), email, int(time.time()))
            )
        except Exception as e:
            log.error(f"upsert_user failed: {e}")
        finally:
            conn.close()


def get_user(privy_user_id: str) -> dict | None:
    """Fetch a user record by Privy user ID."""
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE privy_user_id=?", (privy_user_id,)
            ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            log.error(f"get_user failed: {e}")
            return None
        finally:
            conn.close()


# ─── API Keys ──────────────────────────────────────────────────────────────────

def _hash_key(plaintext: str) -> str:
    """Hash an API key for storage (we never store the plaintext)."""
    import hashlib
    return hashlib.sha256(plaintext.encode()).hexdigest()


def create_api_key(user_id: str, name: str, budget_cents: int) -> dict | None:
    """Create a new API key for a user. Returns the plaintext key ONCE."""
    raw = "surp_" + secrets.token_urlsafe(32)
    key_id = secrets.token_hex(8)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO api_keys (key_id, user_id, key_hash, name, budget_cents, "
                "spent_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (key_id, user_id, _hash_key(raw), name, budget_cents, int(time.time()))
            )
            return {"key": raw, "key_id": key_id, "name": name, "budget_cents": budget_cents}
        except Exception as e:
            log.error(f"create_api_key failed: {e}")
            return None
        finally:
            conn.close()


def list_api_keys(user_id: str) -> list[dict]:
    """List all API keys for a user (without the plaintext key)."""
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT key_id, name, budget_cents, spent_cents, created_at "
                "FROM api_keys WHERE user_id=? ORDER BY created_at DESC",
                (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            log.error(f"list_api_keys failed: {e}")
            return []
        finally:
            conn.close()


def delete_api_key(user_id: str, key_id: str) -> bool:
    """Delete an API key. Returns True if deleted."""
    with _LOCK:
        conn = _connect()
        try:
            cur = conn.execute(
                "DELETE FROM api_keys WHERE key_id=? AND user_id=?",
                (key_id, user_id)
            )
            return cur.rowcount > 0
        except Exception as e:
            log.error(f"delete_api_key failed: {e}")
            return False
        finally:
            conn.close()


def validate_api_key(raw_key: str) -> dict | None:
    """Validate an API key from a request. Returns the key record or None."""
    if not raw_key or not raw_key.startswith("surp_"):
        return None
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT key_id, user_id, name, budget_cents, spent_cents "
                "FROM api_keys WHERE key_hash=?", (_hash_key(raw_key),)
            ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            log.error(f"validate_api_key failed: {e}")
            return None
        finally:
            conn.close()


def check_budget(key_id: str, cost_cents: int) -> bool:
    """Check if an API key has remaining budget for a cost. Increments spent."""
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT budget_cents, spent_cents FROM api_keys WHERE key_id=?",
                (key_id,)
            ).fetchone()
            if not row:
                return False
            if row["budget_cents"] > 0 and row["spent_cents"] + cost_cents > row["budget_cents"]:
                return False
            conn.execute(
                "UPDATE api_keys SET spent_cents = spent_cents + ? WHERE key_id=?",
                (cost_cents, key_id)
            )
            return True
        except Exception as e:
            log.error(f"check_budget failed: {e}")
            return False
        finally:
            conn.close()


# ─── Usage logging ─────────────────────────────────────────────────────────────

def log_usage(user_id: str, api_key_id: str, model: str,
              input_tokens: int, output_tokens: int, cost_cents: int,
              tx_hash: str = "") -> None:
    """Log a completed inference request. Fault-isolated (never breaks requests)."""
    try:
        with _LOCK:
            conn = _connect()
            try:
                conn.execute(
                    "INSERT INTO usage (user_id, api_key_id, model, input_tokens, "
                    "output_tokens, cost_cents, tx_hash, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, api_key_id, model, input_tokens, output_tokens,
                     cost_cents, tx_hash, int(time.time()))
                )
            finally:
                conn.close()
    except Exception as e:
        log.error(f"log_usage failed: {e}")


def get_usage(user_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Get paginated usage records for a user (newest first)."""
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM usage WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            log.error(f"get_usage failed: {e}")
            return []
        finally:
            conn.close()


# ─── Analytics ─────────────────────────────────────────────────────────────────

def get_dashboard_stats(user_id: str) -> dict:
    """Compute aggregate dashboard stats for a user."""
    stats: dict[str, Any] = {
        "total_spend_cents": 0,
        "total_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "marketplace_savings_cents": 0,
        "top_models": [],
        "top_api_keys": [],
        "daily_spend": [],
        "daily_requests": [],
    }
    with _LOCK:
        conn = _connect()
        try:
            # Totals
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_cents),0) as total_spend, "
                "COUNT(*) as total_requests, "
                "COALESCE(SUM(input_tokens),0) as total_input, "
                "COALESCE(SUM(output_tokens),0) as total_output "
                "FROM usage WHERE user_id=?", (user_id,)
            ).fetchone()
            if row:
                stats["total_spend_cents"] = row["total_spend"]
                stats["total_requests"] = row["total_requests"]
                stats["total_input_tokens"] = row["total_input"]
                stats["total_output_tokens"] = row["total_output"]
                # Marketplace savings = what OpenAI would have charged vs surp
                # Estimate: surp is ~80% cheaper than OpenAI equivalent
                stats["marketplace_savings_cents"] = int(row["total_spend"] * 0.8)

            # Top models by spend
            rows = conn.execute(
                "SELECT model, COUNT(*) as reqs, SUM(cost_cents) as spend "
                "FROM usage WHERE user_id=? GROUP BY model "
                "ORDER BY spend DESC LIMIT 5", (user_id,)
            ).fetchall()
            stats["top_models"] = [
                {"model": r["model"], "requests": r["reqs"], "spend_cents": r["spend"]}
                for r in rows
            ]

            # Top API keys by spend
            rows = conn.execute(
                "SELECT k.name as name, COUNT(u.id) as reqs, COALESCE(SUM(u.cost_cents),0) as spend "
                "FROM usage u JOIN api_keys k ON u.api_key_id=k.key_id "
                "WHERE u.user_id=? GROUP BY u.api_key_id "
                "ORDER BY spend DESC LIMIT 5", (user_id,)
            ).fetchall()
            stats["top_api_keys"] = [
                {"name": r["name"], "requests": r["reqs"], "spend_cents": r["spend"]}
                for r in rows
            ]

            # Daily spend (last 30 days)
            cutoff = int(time.time()) - (30 * 86400)
            rows = conn.execute(
                "SELECT date(created_at, 'unixepoch') as day, "
                "SUM(cost_cents) as spend, COUNT(*) as reqs "
                "FROM usage WHERE user_id=? AND created_at >= ? "
                "GROUP BY day ORDER BY day", (user_id, cutoff)
            ).fetchall()
            stats["daily_spend"] = [
                {"day": r["day"], "spend_cents": r["spend"], "requests": r["reqs"]}
                for r in rows
            ]
        except Exception as e:
            log.error(f"get_dashboard_stats failed: {e}")
        finally:
            conn.close()
    return stats


# ─── On-chain balances ────────────────────────────────────────────────────────

def get_wallet_balances(wallet_address: str) -> dict:
    """Fetch ETH + USDC balances for a wallet from Base mainnet."""
    if not wallet_address:
        return {"eth": "0", "usdc": "0", "usdc_atomic": 0}
    addr = Web3.to_checksum_address(wallet_address)
    result: dict[str, Any] = {"eth": "0", "usdc": "0", "usdc_atomic": 0}
    try:
        result["eth"] = str(_w3.eth.get_balance(addr))
    except Exception as e:
        log.error(f"ETH balance failed: {e}")
    try:
        data = _BALANCE_OF + addr[2:].lower().zfill(64)
        raw = _w3.eth.call({"to": _USDC, "data": data})
        usdc_atomic = int.from_bytes(raw, "big")
        result["usdc_atomic"] = usdc_atomic
        result["usdc"] = str(usdc_atomic)
    except Exception as e:
        log.error(f"USDC balance failed: {e}")
    return result


def get_user_balance(user_id: str) -> dict:
    """Get the wallet balance for a user (by their internal user id)."""
    user = get_user(user_id)
    if not user or not user.get("wallet_address"):
        return {"eth": "0", "usdc": "0", "usdc_atomic": 0}
    return get_wallet_balances(user["wallet_address"])


# ─── Auth middleware ──────────────────────────────────────────────────────────

def _get_privy_access_token(auth_header: str) -> str:
    """Extract the access token from an Authorization: Bearer header."""
    if not auth_header:
        return ""
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return auth_header.strip()


def verify_privy_token(access_token: str) -> dict | None:
    """Verify a Privy access token via the Privy REST API.

    Returns the user object (with id, wallet, email) or None if invalid.
    Uses a User-Agent header to avoid Cloudflare 1010 browser-signature blocks.
    """
    if not access_token:
        return None
    app_id = os.environ.get("PRIVY_APP_ID", "")
    app_secret = os.environ.get("PRIVY_APP_SECRET", "")
    if not app_id or not app_secret:
        log.error("PRIVY_APP_ID/PRIVY_APP_SECRET not set")
        return None
    import urllib.request
    import base64
    req = urllib.request.Request(
        "https://auth.privy.io/api/v1/users",
        # User-Agent is required — without it, Cloudflare returns 1010
        # (browser-signature block) and the request fails before reaching Privy.
        headers={
            "User-Agent": "surp-gateway/1.0",
            "Authorization": "Basic "
            + base64.b64encode(f"{app_id}:{app_secret}".encode()).decode(),
            "privy-app-id": app_id,
            "Content-Type": "application/json",
        },
        method="POST",
        data=json.dumps({"access_token": access_token}).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data
    except Exception as e:
        log.error(f"verify_privy_token failed: {e}")
        return None


def get_user_id_from_request(auth_header: str) -> str | None:
    """Full auth flow: verify Privy token → upsert user → return privy user id."""
    token = _get_privy_access_token(auth_header)
    if not token:
        return None
    user = verify_privy_token(token)
    if not user or "id" not in user:
        return None
    privy_user_id = user["id"]
    wallet = ""
    email = ""
    if user.get("linkedAccounts"):
        for acct in user["linkedAccounts"]:
            if acct.get("type") == "wallet":
                wallet = acct.get("address", "")
            elif acct.get("type") == "email":
                email = acct.get("address", "")
    if wallet:
        upsert_user(privy_user_id, wallet, email)
    return privy_user_id
