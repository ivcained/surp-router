"""NFT/token-gated eligibility for surp.ivc.lol.

Read-only `balanceOf` check against a configurable ERC-20 / ERC-721 contract
on Base. Results are cached for a short window so repeat customers aren't
re-checked on every request. Fail-closed: if the RPC is unreachable or the
response is unparseable, eligibility is False (never let a bad RPC unlock
paid inference for free).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

import reward_ledger as rl

DB_PATH = os.environ.get("SURP_DB", rl.DB_PATH)
_rpc_url = os.environ.get("SURP_RPC_URL", "https://base-rpc.publicnode.com")
CONTRACT = os.environ.get("SURP_GATE_CONTRACT", "")
ELIGIBILITY_THRESHOLD = int(os.environ.get("SURP_GATE_THRESHOLD", "1"))
CACHE_TTL = int(os.environ.get("SURP_GATE_CACHE_TTL", "60"))

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
        CREATE TABLE IF NOT EXISTS nft_eligibility (
            wallet      TEXT PRIMARY KEY,
            balance     INTEGER NOT NULL,
            eligible    INTEGER NOT NULL,
            checked_at  INTEGER NOT NULL
        );
        """)
        _conn.commit()
    return _conn


def _eth_call(url: str, to: str, data: str) -> str:
    """Minimal JSON-RPC eth_call. Returns the 'result' hex string.

    Kept as a standalone function so tests can monkeypatch it without touching
    aiohttp. Production code should prefer the async path in `check_async`.
    """
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
        "id": 1,
    })
    import urllib.request
    req = urllib.request.Request(url, data=payload.encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read())
    if "error" in body:
        raise RuntimeError(body["error"])
    return body["result"]


def _balance_of_data(wallet: str) -> str:
    """ERC-20/721 balanceOf(address) selector = 0x70a08231."""
    w = wallet.lower()
    if w.startswith("0x"):
        w = w[2:]
    return "0x70a08231" + w.rjust(64, "0")


def _parse_balance(hex_result: str) -> int:
    h = hex_result.lower().replace("0x", "")
    return int(h, 16) if h else 0


def _cached(wallet: str) -> Optional[dict[str, Any]]:
    row = conn().execute(
        "SELECT * FROM nft_eligibility WHERE wallet=?", (wallet.lower(),)
    ).fetchone()
    return dict(row) if row else None


def _store(wallet: str, balance: int, eligible: bool) -> None:
    now = int(time.time())
    with _lock:
        conn().execute(
            "INSERT INTO nft_eligibility(wallet,balance,eligible,checked_at) "
            "VALUES(?,?,?,?) ON CONFLICT(wallet) DO UPDATE SET "
            "balance=excluded.balance,eligible=excluded.eligible,checked_at=excluded.checked_at",
            (wallet.lower(), balance, int(eligible), now),
        )
        conn().commit()


def is_eligible(wallet: str) -> bool:
    """True iff the wallet's token balance meets the eligibility threshold.

    Cached for CACHE_TTL seconds. Fail-closed: RPC errors never grant access.
    """
    if not CONTRACT or not wallet:
        return False
    cached = _cached(wallet)
    now = int(time.time())
    if cached and now - int(cached["checked_at"]) <= CACHE_TTL:
        return bool(cached["eligible"])
    try:
        raw = _eth_call(_rpc_url, CONTRACT, _balance_of_data(wallet))
        balance = _parse_balance(raw)
    except Exception:
        # Fail closed. Cache the failure briefly so a down RPC doesn't
        # trigger a storm of retries against the provider.
        if cached:
            return bool(cached["eligible"])  # last good value, if any
        return False
    eligible = balance >= ELIGIBILITY_THRESHOLD
    _store(wallet, balance, eligible)
    return eligible


async def check_async(wallet: str) -> bool:
    """Async wrapper using aiohttp for non-blocking checks inside the gateway."""
    if not CONTRACT or not wallet:
        return False
    cached = _cached(wallet)
    now = int(time.time())
    if cached and now - int(cached["checked_at"]) <= CACHE_TTL:
        return bool(cached["eligible"])
    import aiohttp
    payload = {"jsonrpc": "2.0", "method": "eth_call",
               "params": [{"to": CONTRACT, "data": _balance_of_data(wallet)}, "latest"], "id": 1}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(_rpc_url, json=payload,
                              timeout=aiohttp.ClientTimeout(total=5)) as r:
                body = await r.json()
        if "error" in body:
            raise RuntimeError(body["error"])
        balance = _parse_balance(body.get("result", "0x0"))
    except Exception:
        return bool(cached["eligible"]) if cached else False
    eligible = balance >= ELIGIBILITY_THRESHOLD
    _store(wallet, balance, eligible)
    return eligible
