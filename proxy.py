#!/usr/bin/env python3
"""
Surplus Intelligence live-price router proxy.

Sits between Hermes and https://api.surplusintelligence.ai/v1. Hermes sends
OpenAI-compatible requests with model="surp/<combo>"; this proxy fetches the
public Surplus market book (GET /api/markets), resolves the combo to the
cheapest concrete model in the combo's class, rewrites the `model` field in
the request body, and forwards to Surplus's /v1/chat/completions.

Combos (15):
  best-coding, best-reasoning, best-fast, best-vision, best-chat,
  best-coding-fast, pro-coding, pro-reasoning, pro-vision, pro-chat,
  pro-fast, coding, fast, chat, srup-free

  best-*  -> cheapest model in the class
  pro-*   -> cheapest *frontier-tier* model in the class
  coding  -> alias of best-coding
  fast    -> alias of best-fast
  chat    -> alias of best-chat
  srup-free -> zero-price model if any, else the absolute cheapest text LLM

Run:
  SURPLUS_INTELLIGENCE_API_KEY=inf_xxx python3 proxy.py [--port 20129]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Optional

import aiohttp
from aiohttp import web

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

SURPLUS_BASE = "https://api.surplusintelligence.ai"
MARKETS_URL = f"{SURPLUS_BASE}/api/markets"
FORWARD_BASE = f"{SURPLUS_BASE}/v1"

COMBOS: list[str] = [
    "best-coding", "best-reasoning", "best-fast", "best-vision", "best-chat",
    "best-coding-fast",
    "pro-coding", "pro-reasoning", "pro-vision", "pro-chat", "pro-fast",
    "coding", "fast", "chat",
    "srup-free",
]

# Price cache TTL in seconds. The market book moves, but 30s is a reasonable
# trade-off between freshness and not hammering the public endpoint.
CACHE_TTL = 30.0

# ──────────────────────────────────────────────────────────────────────────────
# Combo resolution is delegated to combo_resolver so the resolver and the
# x402 gateway can never disagree about what a combo means.
# ──────────────���───────────────────────────────────────────────────────────────

import combo_resolver as cr

COMBOS = cr.BUILTIN_COMBOS


def _resolve(combo: str, markets: list[dict]):
    """Adapter kept for the existing call sites / tests."""
    model, dbg, _price, _pool = cr.resolve(combo, markets)
    return model, dbg


# ──────────────────────────────────────────────────────────────────────────────
# Market cache
# ──────────────────────────────────────────────────────────────────────────────

class MarketCache:
    def __init__(self) -> None:
        self._markets: Optional[list[dict]] = None
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> list[dict]:
        async with self._lock:
            now = time.monotonic()
            if self._markets is None or (now - self._fetched_at) > CACHE_TTL:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(MARKETS_URL, timeout=aiohttp.ClientTimeout(total=15)) as r:
                            r.raise_for_status()
                            data = await r.json()
                    self._markets = data.get("markets", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    self._fetched_at = now
                    logging.getLogger("surp").info(f"market cache refreshed: {len(self._markets)} markets")
                except Exception as e:
                    logging.getLogger("surp").warning(f"market fetch failed: {e}")
                    if self._markets is None:
                        raise
            return self._markets or []


CACHE = MarketCache()


# ──────────────────────────────────────────────────────────────────────────────
# HTTP handlers
# ──────────────────────────────────────────────────────────────────────────────

async def health(request: web.Request) -> web.Response:
    markets = CACHE._markets or []
    return web.json_response({
        "status": "ok",
        "cached_markets": len(markets),
        "cache_age_s": round(time.monotonic() - CACHE._fetched_at, 1) if CACHE._markets else None,
        "combos": COMBOS,
    })


async def models_endpoint(request: web.Request) -> web.Response:
    """Advertise the 15 combos as virtual models (OpenAI /v1/models shape)."""
    return web.json_response({
        "object": "list",
        "data": [
            {"id": f"surp/{c}", "object": "model", "owned_by": "surplus-intelligence"}
            for c in cr.all_combo_names()
        ],
    })


async def chat_completions(request: web.Request) -> web.StreamResponse:
    """Resolve surp/<combo> -> cheapest concrete model, forward to Surplus."""
    log = logging.getLogger("surp")
    api_key = os.environ.get("SURPLUS_INTELLIGENCE_API_KEY", "").strip()
    if not api_key:
        return web.json_response({"error": "SURPLUS_INTELLIGENCE_API_KEY not set on proxy"}, status=500)

    try:
        body = await request.read()
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as e:
        return web.json_response({"error": f"invalid JSON body: {e}"}, status=400)

    model = payload.get("model", "")
    if not model.startswith("surp/"):
        # Passthrough — don't resolve, just forward with the key.
        resolved_model = model
        log.info(f"passthrough model={model}")
    else:
        combo = model[len("surp/"):]
        try:
            markets = await CACHE.get()
        except Exception as e:
            return web.json_response({"error": f"market data unavailable: {e}"}, status=502)
        resolved_model, debug = _resolve(combo, markets)
        if resolved_model is None:
            return web.json_response({"error": f"combo resolution failed: {debug}"}, status=404)
        log.info(debug)
        payload["model"] = resolved_model
        if combo.startswith("my/"):
            cr.bump_hits(combo[3:])

    # Forward to Surplus
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # Carry through Accept and other innocuous headers
    for h in ("Accept", "User-Agent"):
        v = request.headers.get(h)
        if v:
            headers[h] = v

    is_stream = bool(payload.get("stream"))
    timeout = aiohttp.ClientTimeout(total=None, sock_read=600)
    fwd_body = json.dumps(payload).encode()

    try:
        session = aiohttp.ClientSession()
    except Exception as e:
        return web.json_response({"error": f"session create failed: {e}"}, status=500)

    try:
        upstream = await session.post(
            f"{FORWARD_BASE}/chat/completions",
            headers=headers,
            data=fwd_body,
            timeout=timeout,
        )
    except Exception as e:
        await session.close()
        return web.json_response({"error": f"upstream connection failed: {e}"}, status=502)

    # Pipe the response back. streaming -> SSE chunk pass-through;
    # non-streaming -> buffered JSON.
    out = web.StreamResponse(status=upstream.status, headers={
        k: v for k, v in upstream.headers.items()
        if k.lower() in ("content-type", "cache-control", "x-request-id")
    })
    if is_stream:
        out.content_type = "text/event-stream"
        out.headers["Cache-Control"] = "no-cache"
    await out.prepare(request)
    try:
        async for chunk in upstream.content.iter_chunked(4096):
            await out.write(chunk)
    except Exception as e:
        log.warning(f"stream pipe error: {e}")
    finally:
        await session.close()
        await out.write_eof()
    return out


async def prices_passthrough(request: web.Request) -> web.Response:
    """GET /v1/prices -> forward to Surplus /v1/prices (no auth needed)."""
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{FORWARD_BASE}/prices", timeout=aiohttp.ClientTimeout(total=15)) as r:
            return web.json_response(await r.json(), status=r.status)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/healthz", health)
    app.router.add_get("/v1/models", models_endpoint)
    app.router.add_get("/v1/prices", prices_passthrough)
    app.router.add_post("/v1/chat/completions", chat_completions)
    # Also support /v1/completions and /anthropic/v1/messages? Not yet —
    # Hermes chat uses /v1/chat/completions. Add when needed.
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=20129)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("surp")

    key = os.environ.get("SURPLUS_INTELLIGENCE_API_KEY", "").strip()
    if not key:
        log.error("SURPLUS_INTELLIGENCE_API_KEY env var not set; forwarding will fail")
    else:
        log.info(f"SURPLUS_INTELLIGENCE_API_KEY set (len={len(key)})")

    log.info(f"starting surp-router on {args.host}:{args.port}")
    web.run_app(build_app(), host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
