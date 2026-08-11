#!/usr/bin/env python3
"""
surp.ivc.lol — x402-paywalled gateway to the Surplus Intelligence aggregator.

Public site + API on :20130. Website (black/terminal theme) is served directly;
/v1/chat/completions is paywalled with x402 (USDC on Base via EIP-3009).
Paid requests are forwarded to the price-resolving proxy on :20129, which
resolves surp/<combo> -> live cheapest Surplus model.

Run (in the surp-router venv):
  python3 gateway.py --port 20130
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
import traceback
from typing import Any, Optional

import aiohttp
from aiohttp import web

import stats as st
import combo_resolver as cr
import model_info as mi
import landing_pages as lp
import cache_tech as ct
import cache_page as cp
import reward_ledger as rl
import proposal_votes as pv
import proposal_page as pp
import nft_gate as ng
import community_feedback as cf
import token_gate_page as tgp
import free_models as fm
import free_models_page as fmp
import provider_health as ph
import health_board_page as hbp
import features_page as fp
import cache_affinity as ca
import auction_page as ap
import model_benchmarks as mb
import performance_page as pp
import user_accounts as ua
import value_index as vi
import studio as st

# ──────────────────────────────────────────────────────────────────────────────
# x402 imports
# ──────────────────────────────────────────────────────────────────────────────

from x402.http import (
    PaymentOption,
    FacilitatorConfig,
    HTTPFacilitatorClientSync,
    x402HTTPResourceServerSync,
    RouteConfig,
    HTTPRequestContext,
    HTTPAdapter,
)
from x402.schemas.payments import PaymentRequired

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Public origin, used in docs/examples and the health payload. The internal
# resolver address is deliberately NOT exposed to clients.
PUBLIC_BASE = os.environ.get("SURP_PUBLIC_BASE", "https://surp.ivc.lol").rstrip("/")

# The price-resolving proxy (internal only — never surfaced in API responses).
RESOLVER_BASE = os.environ.get("RESOLVER_BASE", "http://127.0.0.1:20129")

# x402 facilitator — default x402.org facilitator handles Base Sepolia testnet.
# For production mainnet, set PROD_FACILITATOR_URL and a pay_to wallet.
FACILITATOR_URL = os.environ.get("FACILITATOR_URL", "https://x402.org/facilitator")

# Wallet that receives x402 payments. Replace with the real treasury.
# Default is a throwaway zero address — MUST be set in prod.
PAY_TO = os.environ.get("SURP_PAY_TO", "0x0000000000000000000000000000000000000000")

# Network: Base Sepolia testnet (eip155:84532) for dev.
# Flip to eip155:8453 (Base mainnet) for production.
NETWORK = os.environ.get("SURP_NETWORK", "eip155:84532")

# USDC contract address. Defaults to Base Sepolia testnet USDC.
# For Base MAINNET, set SURP_ASSET=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
# (native USDC on Base, 6 decimals, EIP-3009 transferWithAuthorization).
USDC_BASE_TESTNET = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
ASSET = os.environ.get("SURP_ASSET", USDC_BASE_TESTNET)

# Markup over the raw Surplus price: we charge cost + SURP_MARKUP_BPS bps.
# 100 bps = 1%. Default 500 bps = 5% — keeps us sustainable while staying
# dramatically cheaper than retail providers.
MARKUP_BPS = int(os.environ.get("SURP_MARKUP_BPS", "500"))

# Floor price in cents (1¢) — even if Surplus model is somehow zero, charge a
# micropenny so the x402 flow has something to settle.
FLOOR_CENTS = float(os.environ.get("SURP_FLOOR_CENTS", "1"))

# Cache innovation: exact deterministic responses cost less than fresh inference,
# while sticky routing raises upstream provider prefix-cache hit rates.
CACHE_DB = os.environ.get("SURP_CACHE_DB", "/root/.hermes/surp-router/cache.db")
REWARD_DB = os.environ.get("SURP_REWARD_DB", "/root/.hermes/surp-router/rewards.db")
CACHE_TTL_SECONDS = int(os.environ.get("SURP_CACHE_TTL_SECONDS", "900"))
CACHE_MAX_ENTRIES = int(os.environ.get("SURP_CACHE_MAX_ENTRIES", "5000"))
CACHE_HIT_CENTS = float(os.environ.get("SURP_CACHE_HIT_CENTS", "0.1"))
STICKY_TTL_SECONDS = int(os.environ.get("SURP_STICKY_TTL_SECONDS", "300"))
STICKY_TOLERANCE_PCT = float(os.environ.get("SURP_STICKY_TOLERANCE_PCT", "30"))
_RESPONSE_CACHE = ct.ResponseCache(CACHE_DB, CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES)
_STICKY_ROUTER = ct.StickyRouter(CACHE_DB, STICKY_TTL_SECONDS, STICKY_TOLERANCE_PCT)
# Reward ledger uses its own DB file to avoid SQLite write-lock contention
# with stats.py / combo_resolver.py on combos.db.
rl.DB_PATH = REWARD_DB
pv._DB_PATH = REWARD_DB
cf.DB_PATH = REWARD_DB
ng.DB_PATH = REWARD_DB

# NFT/token-gated eligibility: holders bypass x402 per-request payment.
# Configure with SURP_GATE_CONTRACT, SURP_GATE_THRESHOLD, SURP_RPC_URL.
NFT_GATE_ENABLED = bool(os.environ.get("SURP_GATE_CONTRACT", "").strip())
NFT_GATE_DISCOUNT_BPS = int(os.environ.get("SURP_GATE_DISCOUNT_BPS", "0"))

# ──────────────────────────────────────────────────────────────────────────────
# Facilitator + resource server (sync — runs in a thread off the event loop)
# ──────────────────────────────────────────────────────────────────────────────

_facilitator: Optional[HTTPFacilitatorClientSync] = None
_resource_server: Optional[x402HTTPResourceServerSync] = None
_loop: Optional[asyncio.AbstractEventLoop] = None


def _init_x402() -> None:
    """Initialize the x402 facilitator client and resource server."""
    global _facilitator, _resource_server
    _facilitator = HTTPFacilitatorClientSync(FacilitatorConfig(url=FACILITATOR_URL))

    # Routes: POST /v1/chat/completions is paywalled. Everything else is free.
    # The price is dynamic — computed per request from the live Surplus price.
    routes = {
        "POST /v1/chat/completions": RouteConfig(
            accepts=[
                PaymentOption(
                    scheme="exact",
                    price="${{surp_price}}",  # placeholder — replaced at runtime
                    network=NETWORK,
                    pay_to=PAY_TO,
                    max_timeout_seconds=600,
                    extra={"asset": ASSET, "description": "surp.ivc.lol — dynamic cheapest-model routing"},
                )
            ],
            description="x402-paywalled LLM inference — cheapest model for your combo, live-priced.",
            mime_type="application/json",
            service_name="surp.ivc.lol",
        )
    }
    # Build the resource server. We won't use its full request-pipeline; we
    # use the lower-level payment-required encoding + facilitator verify/settle
    # directly so we can compute the price dynamically per request.
    log = logging.getLogger("surp.gateway")
    log.info(f"x402 facilitator: {FACILITATOR_URL}  network={NETWORK}  pay_to={PAY_TO}")


# ──────────────────────────────────────────────────────────────────────────────
# Dynamic pricing
# ──────────────────────────────────────────────────────────────────────────────

def _price_to_cents(surplus_price_per_1m: float, expected_tokens: int = 1500) -> float:
    """Convert Surplus best_price_per_1m (in atomic USD units, 1e-8 USD each)
    to a USDC-cent price for a single request.

    Surplus `best_price_per_1m` is in units where 1e6 = $1.00 per 1M tokens
    (calibrated against known retail: gemini-2.5-pro 1687500 -> $1.69/1M,
    gpt-4o 3125000 -> $3.13/1M, glm-5.2 30000 -> $0.03/1M).
    So usd_per_1m = surplus_price_per_1m / 1e6.
    Per request: usd_per_1m * (expected_tokens / 1_000_000) USD.
    Add markup_bps. Floor at FLOOR_CENTS. Round up to the nearest cent.
    """
    if surplus_price_per_1m < 0:
        surplus_price_per_1m = 0
    price_usd = (surplus_price_per_1m / 1e6) * (expected_tokens / 1_000_000)
    marked = price_usd * (1 + MARKUP_BPS / 10000.0)
    cents = max(FLOOR_CENTS, marked * 100)
    return float(int(cents) + (1 if cents > int(cents) else 0))  # ceil


# ──────────────────────────────────────────────────────────────────────────────
# HTTP 402 response builder
# ──────────────────────────────────────────────────────────────────────────────

def _build_payment_required(combo: str, model: str, surplus_price: float, expected_tokens: int,
                            routing_reason: str = "") -> dict:
    """Build the 402 response body + PAYMENT-REQUIRED header.

    Returns a dict with 'status', 'headers', 'body' for aiohttp to emit.
    """
    cents = _price_to_cents(surplus_price, expected_tokens)
    # x402 dollar-string price: "$0.01" syntax uses the chain's default stable.
    price_str = f"${cents/100:.2f}"

    req = PaymentRequired(
        x402Version=2,
        accepts=[],
    )
    from x402.schemas.payments import PaymentRequirements
    req.accepts = [
        PaymentRequirements(
            scheme="exact",
            network=NETWORK,
            asset=ASSET,
            amount=str(int(cents * 10_000)),  # atomic USDC units (6 decimals): cents * 10^4
            payTo=PAY_TO,
            maxTimeoutSeconds=600,
            extra={
                "description": f"surp.ivc.lol: {combo} -> {model} (~{expected_tokens} tokens)",
                "mimeType": "application/json",
                "resource": f"surp.ivc.lol/v1/chat/completions",
            },
        )
    ]

    from x402.http import encode_payment_required_header, PAYMENT_REQUIRED_HEADER
    header_val = encode_payment_required_header(req)

    body = {
        "x402Version": 2,
        "error": "payment-required",
        "resource": "POST /v1/chat/completions",
        "combo": combo,
        "routed_model": model,
        "routing_reason": routing_reason,
        "surplus_price_per_1m": surplus_price,
        "expected_tokens": expected_tokens,
        "price_usd": price_str,
        "accepts": [
            {
                "scheme": "exact",
                "network": NETWORK,
                "asset": ASSET,
                "amount": str(int(cents * 10_000)),
                "payTo": PAY_TO,
                "maxTimeoutSeconds": 600,
                "extra": {
                    "description": f"surp.ivc.lol: {combo} -> {model}",
                    "mimeType": "application/json",
                },
            }
        ],
        "instructions": (
            "Sign this EIP-3009 authorization with your wallet and retry the request "
            "with the `X-Payment` header set to the base64-encoded payment payload. "
            "See https://docs.x402.org for client libraries."
        ),
    }
    return {
        "status": 402,
        "headers": {
            PAYMENT_REQUIRED_HEADER: header_val,
        },
        "body": body,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Combo resolution — shared with the :20129 resolver via combo_resolver.
# ──────────────────────────────────────────────────────────────────────────────

import combo_resolver as cr

COMBOS = cr.BUILTIN_COMBOS
_is_text_llm = cr.is_text_llm
_price = cr.price_of


def resolve_combo(combo: str, markets: list[dict]):
    return cr.resolve(combo, markets)


# ──────────────────────────────────────────────────────────────────────────────
# Market cache (separate from the :20129 proxy's cache — this one is for the
# website's live ticker and the playground price-preview)
# ──────────────────────────────────────────────────────────────────────────────

class GatewayMarketCache:
    def __init__(self):
        self._markets = None
        self._ts = 0.0
        self._lock = asyncio.Lock()
    async def get(self):
        async with self._lock:
            now = time.monotonic()
            if self._markets is None or (now - self._ts) > 30:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get("https://api.surplusintelligence.ai/api/markets", timeout=aiohttp.ClientTimeout(total=15)) as r:
                            r.raise_for_status()
                            data = await r.json()
                    self._markets = data.get("markets", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    self._ts = now
                except Exception as e:
                    logging.getLogger("surp.gateway").warning(f"market fetch failed: {e}")
                    if self._markets is None:
                        raise
        return self._markets or []

GCACHE = GatewayMarketCache()


# ──────────────────────────────────────────────────────────────────────────────
# Website pages (terminal-themed, black)
# ──────────────────────────────────────────────────────────────────────────────

def _combo_table_rows(markets) -> str:
    """Build the live ticker. Each combo row is a <details> disclosure that
    expands to show every model in that combo's pool, cheapest first.

    NOTE: only renders summaries (cheap). The full pool tables are fetched
    on-demand when a user expands a combo, to keep the page light."""
    blocks = []
    for combo in COMBOS:
        pool = cr.pool_for(combo, markets)
        desc = cr.COMBO_DESCRIPTIONS.get(combo, "")
        if not pool:
            blocks.append(
                f"<details class='combo-block'><summary><span class='combo'>surp/{combo}</span> "
                f"<span class='err'>no models available</span></summary></details>"
            )
            continue
        winner = pool[0]
        w_usd = cr.usd_per_1m(winner)
        savings = max(0, (cr.RETAIL_BASELINE_USD_PER_1M - w_usd) / cr.RETAIL_BASELINE_USD_PER_1M * 100)

        # Show top 10 models inline (keeps page under 50KB instead of 128KB)
        display_pool = pool[:10]
        has_more = len(pool) > 10
        inner = [
            "<table class='pool-table'><thead><tr>"
            "<th>#</th><th>model</th><th>class</th><th>USD / 1M tok</th><th>sellers</th>"
            "</tr></thead><tbody>"
        ]
        for i, m in enumerate(display_pool, 1):
            mark = " ◀ routed now" if i == 1 else ""
            cls = "winner" if i == 1 else ""
            inner.append(
                f"<tr class='{cls}'><td class='pool'>{i}</td>"
                f"<td class='model'>{m['model']}<span class='routed'>{mark}</span></td>"
                f"<td class='pool'>{cr.class_of(m)}</td>"
                f"<td class='price'>${cr.usd_per_1m(m):.4f}</td>"
                f"<td class='pool'>{m.get('num_sellers') or m.get('seller_count') or '-'}</td></tr>"
            )
        if has_more:
            inner.append(f'<tr><td colspan="5" class="dim" style="text-align:center;padding:6px;">&hellip; and {len(pool) - 10} more model(s) not shown</td></tr>')
        inner.append("</tbody></table>")

        blocks.append(
            "<details class='combo-block'>"
            f"<summary>"
            f"<span class='combo'>surp/{combo}</span>"
            f"<span class='arrow'>→</span>"
            f"<span class='model'>{winner['model']}</span>"
            f"<span class='price'>${w_usd:.4f}/1M</span>"
            f"<span class='savings'>-{savings:.0f}%</span>"
            f"<span class='poolcount'>{len(pool)} models</span>"
            f"</summary>"
            f"<p class='dim combo-desc'>{desc} &mdash; compares {len(pool)} model(s), "
            f"routes to the cheapest. click any row to see the full list.</p>"
            + "".join(inner) +
            "</details>"
        )
    return "\n".join(blocks)



PAGE_META = {
    "/": {
        "title": "surp.ivc.lol — cheapest LLM API on the internet | x402 pay-per-request",
        "desc": "Pay-per-request LLM inference at live cheapest prices. We watch the Surplus Intelligence marketplace and route every request to whichever model is cheapest right now. USDC on Base, no account needed.",
    },
    "/docs": {
        "title": "API Docs — surp.ivc.lol x402 LLM gateway",
        "desc": "Full API reference for surp.ivc.lol: the 15 built-in combos, custom combo builder, x402 payment flow, pricing formula, streaming, and response headers.",
    },
    "/connect": {
        "title": "Connect Your Hermes Agent — surp.ivc.lol",
        "desc": "Step-by-step guide to connect your Hermes Agent to surp.ivc.lol. Install the x402 client, set your wallet, add the provider config, and get the cheapest LLM per request.",
    },
    "/builder": {
        "title": "Combo Builder — surp.ivc.lol | build your own model routing",
        "desc": "Pick any models from the Surplus Intelligence marketplace and build a custom combo. We route each request to the cheapest model in your set. No coding required.",
    },
    "/about": {
        "title": "About — surp.ivc.lol | aggregating the aggregator",
        "desc": "surp.ivc.lol sits on top of the Surplus Intelligence marketplace, dynamically routing LLM requests to the cheapest seller. Learn why we built it and how x402 payments work.",
    },
    "/status": {
        "title": "Status — surp.ivc.lol | live system stats",
        "desc": "Live system status for surp.ivc.lol: total requests served, USDC settled, top combos, top models routed, cache hit rates, and system health.",
    },
    "/dashboard": {
        "title": "Usage Dashboard — surp.ivc.lol",
        "desc": "Check your request history, spending, and models served. Create prepaid API keys for non-crypto access.",
    },
    "/playground": {
        "title": "Playground — surp.ivc.lol | try the x402 LLM API",
        "desc": "Test the surp.ivc.lol API in your browser. Pick a combo, send a message, see the x402 payment challenge and response live.",
    },
    "/models": {
        "title": "All AI Models — surp.ivc.lol | 150+ LLMs ranked by price",
        "desc": "Browse every AI model on the Surplus Intelligence marketplace, sorted cheapest first. Compare specs, pros, cons, and live pricing for 150+ LLMs.",
    },
    "/top": {
        "title": "Top 5 LLMs — surp.ivc.lol | cheapest models per category",
        "desc": "Top 5 cheapest LLMs per category: coding, reasoning, vision, fast, and chat. Live leaderboard updated every request.",
    },
    "/find": {
        "title": "Find the Right AI Model — surp.ivc.lol | model finder",
        "desc": "Not sure which AI model to use? Pick your use case and we'll show the top 5 cheapest options from the Surplus Intelligence marketplace.",
    },
    "/compare": {
        "title": "Compare AI Models — surp.ivc.lol | side-by-side LLM comparison",
        "desc": "Compare AI models side by side. See strengths, weaknesses, cost per token, and which model is cheapest for your task.",
    },
    "/cache": {
        "title": "Cache-Aware LLM Routing — surp.ivc.lol | prefix + response caching",
        "desc": "How surp.ivc.lol combines provider prefix caching, sticky model routing, and privacy-preserving exact response caching to reduce LLM API cost and latency.",
    },
    "/x402": {
        "title": "What is x402? — The AI Agent Payment Protocol | surp.ivc.lol",
        "desc": "x402 is the payment protocol that uses HTTP 402 to charge for API calls. Learn how x402 works, how AI agents pay per request in USDC, and how to use an x402 LLM gateway.",
    },
    "/x402-llm-api": {
        "title": "x402 LLM API — Pay-per-Request AI Inference in USDC | surp.ivc.lol",
        "desc": "The x402 LLM API: pay per request for AI inference in USDC on Base, no account, no API key. OpenAI-compatible endpoint that routes to the cheapest model.",
    },
    "/x402-gateway": {
        "title": "x402 Gateway — Pay-per-Request LLM Gateway | surp.ivc.lol",
        "desc": "An x402 gateway verifies and settles HTTP 402 payments for APIs. surp.ivc.lol is a live x402 LLM gateway: pay per request in USDC, get the cheapest model.",
    },
    "/pay-per-request-llm-api": {
        "title": "Pay-Per-Request LLM API — No Subscription, No Account | surp.ivc.lol",
        "desc": "A pay-per-request LLM API: pay only for the tokens you use, in USDC on Base. No subscription, no account, no API key. Dynamic routing to the cheapest model.",
    },
    "/cheapest-llm-api": {
        "title": "Cheapest LLM API — Live LLM API Pricing, Ranked | surp.ivc.lol",
        "desc": "The cheapest LLM API, ranked with live prices. Compare 150+ AI models across providers, see who's cheapest right now, and pay per request in USDC.",
    },
    "/proposal": {
        "title": "Proposal: Cache Flywheel Rewards — vote on SRP's future | surp.ivc.lol",
        "desc": "Should surp.ivc.lol keep cache rewards off-chain, deploy a Juicebox treasury, launch a RevNet revenue-backed token, or go hybrid? Read the ELI5 proposal and vote.",
    },
    "/token-gating": {
        "title": "Token-Gated API Access — NFT eligibility for surp.ivc.lol",
        "desc": "How surp.ivc.lol uses NFT/token holdings to gate API access. Prototype design, community feedback, and how to participate.",
    },
    "/free-models": {
        "title": "Free AI Models — Live Sponsored LLM API | surp.ivc.lol",
        "desc": "Use surp/free for genuinely free, treasury-sponsored AI inference. See live eligible models, daily budgets, fallback health, and OmniRoute-inspired free-tier intelligence.",
    },
    "/health": {
        "title": "Free Model Health Board — Live TPS, Latency & Reliability | surp.ivc.lol",
        "desc": "Live provider health board: TPS, p50/p95 latency, failure rate, and composite health score for every model surp has routed. Fills the gap left by the Surplus Intelligence marketplace dashboard.",
    },
    "/features": {
        "title": "Features & Updates — surp.ivc.lol Changelog",
        "desc": "Day-by-day progress on surp.ivc.lol: x402 LLM gateway, cache flywheel rewards, token-gated access, free AI models, provider health board, and SEO landing pages. See what shipped and when.",
    },
    "/auction": {
        "title": "Cache-Affinity Auction — Why Orderbook Pricing Fails for Cached Inference | surp.ivc.lol",
        "desc": "Why cached inference is an ad-network Dutch auction, not an orderbook commodity. Prompt prefixes are cookies; providers with warm KV cache bid lower to win fills; latency verifies honesty.",
    },
    "/performance": {
        "title": "Verified LLM Performance — Real Output TPS, TTFT & Throughput per Dollar | surp.ivc.lol",
        "desc": "Independently verified LLM generation throughput: output tokens/second, time-to-first-token, and throughput-per-dollar for every model on surp. No vendor claims — only measured data.",
    },
}

JSONLD_ORG = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "surp.ivc.lol",
    "description": "Pay-per-request LLM API with dynamic cheapest-model routing from the Surplus Intelligence marketplace. USDC on Base via x402.",
    "url": "https://surp.ivc.lol",
    "applicationCategory": "DeveloperApplication",
    "operatingSystem": "Any",
    "offers": {
        "@type": "Offer",
        "price": "0.01",
        "priceCurrency": "USDC",
        "description": "Per-request micropayment via x402 protocol. No subscription.",
    },
    "creator": {
        "@type": "Organization",
        "name": "surp.ivc.lol",
        "url": "https://surp.ivc.lol",
    },
}


def _render_html(content: str, path: str = "/") -> str:
    """Fill in the page template with SEO meta for the given path."""
    meta = PAGE_META.get(path, PAGE_META["/"])
    import json as _json
    html = _HTML_BASE.replace("__CONTENT__", content)
    html = html.replace("__TITLE__", meta["title"])
    html = html.replace("__DESC__", meta["desc"])
    html = html.replace("__PATH__", path)
    html = html.replace("__JSONLD__", _json.dumps(JSONLD_ORG))
    # Breadcrumb label for the universal top bar.
    breadcrumb = meta["title"].split(" — ")[0].lower().strip()
    html = html.replace("__BREADCRUMB__", breadcrumb)
    return html


async def page_home(request: web.Request) -> web.Response:
    try:
        markets = await GCACHE.get()
        rows = _combo_table_rows(markets)
        market_count = len(markets)
        text_count = len([m for m in markets if _is_text_llm(m)])
    except Exception:
        rows = "<tr><td colspan='5' class='err'>market data unavailable</td></tr>"
        market_count = text_count = 0

    html = _render_html(_HOME_CONTENT, "/").replace("__ROWS__", rows).replace("__MC__", str(market_count)).replace("__TC__", str(text_count))
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})


async def page_docs(request: web.Request) -> web.Response:
    html = _render_html(_DOCS_CONTENT, "/docs")
    return web.Response(text=html, content_type="text/html")


async def page_about(request: web.Request) -> web.Response:
    html = _render_html(_ABOUT_CONTENT, "/about")
    return web.Response(text=html, content_type="text/html")


async def page_playground(request: web.Request) -> web.Response:
    try:
        markets = await GCACHE.get()
        rows = _combo_table_rows(markets)
    except Exception:
        rows = ""
    combo_options = "\n".join(f'<option value="surp/{c}">surp/{c}</option>' for c in COMBOS)
    html = _render_html(_PLAYGROUND_CONTENT, "/playground").replace("__ROWS__", rows).replace("__COMBOS__", combo_options)
    return web.Response(text=html, content_type="text/html")


async def page_builder(request: web.Request) -> web.Response:
    html = _render_html(_BUILDER_CONTENT, "/builder")
    return web.Response(text=html, content_type="text/html")


# ──────────────────────────────────────────────────────────────────────────────
# Public JSON API (free)
# ──────────────────────────────────────────────────────────────────────────────

async def api_combos(request: web.Request) -> web.Response:
    """GET /api/combos — live resolutions for all 15 combos."""
    markets = await GCACHE.get()
    out = []
    for combo in COMBOS:
        if combo in ("free", "srup-free", "free-coding", "free-fast"):
            free_class = "coding" if combo == "free-coding" else "fast" if combo == "free-fast" else "chat"
            free_pool = fm.sponsored_pool_for_class(markets, free_class) if free_class != "chat" else fm.sponsored_pool(markets)
            model = free_pool[0]["model"] if free_pool else None
            out.append({
                "combo": f"surp/{combo}",
                "resolved_model": model,
                "surplus_price_per_1m_atomic": 0,
                "usd_per_1m_tokens": 0,
                "pool_size": len(free_pool),
                "sellers": next((m.get("healthy_seller_count") for m in free_pool if m.get("model") == model), None),
                "sponsored": True,
                "free_class": free_class,
                "budget": fm.live_stats(),
            })
            continue
        model, debug, price, pool = resolve_combo(combo, markets)
        out.append({
            "combo": f"surp/{combo}",
            "resolved_model": model,
            "surplus_price_per_1m_atomic": price,
            "usd_per_1m_tokens": round(price / 1e6, 6) if price else 0,
            "pool_size": pool,
            "sellers": next((m.get("num_sellers") for m in markets if m.get("model") == model), None),
        })
    # Snapshot current resolutions for history sparklines (throttled to 5min)
    st.maybe_snapshot([(c["combo"].replace("surp/", ""), c["resolved_model"] or "",
                        float(c.get("surplus_price_per_1m_atomic") or 0)) for c in out])
    return web.json_response({"combos": out, "network": NETWORK, "asset": ASSET, "pay_to": PAY_TO})


async def api_models_catalog(request: web.Request) -> web.Response:
    """GET /api/models — every text LLM on Surplus, for the combo builder."""
    markets = await GCACHE.get()
    out = []
    for m in markets:
        if not cr.is_text_llm(m):
            continue
        out.append({
            "model": m["model"],
            "usd_per_1m": round(cr.usd_per_1m(m), 6),
            "class": cr.class_of(m),
            "pro": cr.is_pro(m),
            "sellers": m.get("num_sellers") or m.get("seller_count"),
        })
    out.sort(key=lambda r: r["usd_per_1m"])
    return web.json_response({"count": len(out), "models": out})


async def api_custom_create(request: web.Request) -> web.Response:
    """POST /api/combos/custom — build your own combo from chosen models."""
    try:
        body = await request.json()
    except Exception as e:
        return web.json_response({"error": f"invalid JSON: {e}"}, status=400)

    models = body.get("models")
    if not isinstance(models, list):
        return web.json_response({"error": "'models' must be a list of model ids"}, status=400)

    markets = await GCACHE.get()
    valid = {m["model"].lower() for m in markets if cr.is_text_llm(m)}
    unknown = [m for m in models if str(m).strip().lower() not in valid]
    if unknown:
        return web.json_response(
            {"error": "unknown or non-text model(s)", "unknown": unknown[:10]}, status=400
        )

    try:
        rec = cr.create_custom(body.get("name", ""), models)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)

    model, dbg, price, pool = cr.resolve(f"my/{rec['slug']}", markets)
    return web.json_response({
        "slug": rec["slug"],
        "name": rec["name"],
        "models": rec["models"],
        "existing": rec["existing"],
        "model_id": f"surp/my/{rec['slug']}",
        "routes_to_now": model,
        "usd_per_1m_now": round(price / cr.PRICE_DIVISOR, 6),
        "pool_size": pool,
        "usage": f'curl -X POST https://surp.ivc.lol/v1/chat/completions -d \'{{"model":"surp/my/{rec["slug"]}","messages":[...]}}\'',
    })


async def api_custom_get(request: web.Request) -> web.Response:
    """GET /api/combos/custom/{slug} — inspect a saved custom combo."""
    slug = request.match_info["slug"]
    rec = cr.get_custom(slug)
    if not rec:
        return web.json_response({"error": "unknown combo slug"}, status=404)
    markets = await GCACHE.get()
    pool = cr.pool_for(f"my/{slug}", markets)
    return web.json_response({
        **rec,
        "model_id": f"surp/my/{slug}",
        "pool": [
            {"model": m["model"], "usd_per_1m": round(cr.usd_per_1m(m), 6),
             "class": cr.class_of(m), "routed": i == 0}
            for i, m in enumerate(pool)
        ],
    })


async def api_custom_list(request: web.Request) -> web.Response:
    """GET /api/combos/custom — community-built combos, most-used first."""
    markets = await GCACHE.get()
    out = []
    for rec in cr.list_custom(100):
        model, _dbg, price, pool = cr.resolve(f"my/{rec['slug']}", markets)
        out.append({
            **rec,
            "model_id": f"surp/my/{rec['slug']}",
            "routes_to_now": model,
            "usd_per_1m_now": round(price / cr.PRICE_DIVISOR, 6) if price else None,
            "pool_size": pool,
        })
    return web.json_response({"count": len(out), "combos": out})


async def api_health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "api_base": PUBLIC_BASE,
        "endpoints": {
            "chat_completions": f"{PUBLIC_BASE}/v1/chat/completions",
            "models": f"{PUBLIC_BASE}/v1/models",
            "combos": f"{PUBLIC_BASE}/api/combos",
            "model_catalog": f"{PUBLIC_BASE}/api/models",
            "custom_combos": f"{PUBLIC_BASE}/api/combos/custom",
        },
        "facilitator": FACILITATOR_URL,
        "network": NETWORK,
        "pay_to": PAY_TO,
        "markup_bps": MARKUP_BPS,
        "floor_cents": FLOOR_CENTS,
        "cached_markets": len(GCACHE._markets or []),
        "free_tier": {
            "model": "surp/free",
            "sponsored": True,
            "usage": fm.live_stats(),
            "catalog": fm.catalog_summary(),
        },
    })


# ──────────────────────────────────────────────────────────────────────────────
# x402-paywalled (or API-key) chat completions endpoint
# ──────────────────────────────────────────────────────────────────────────────

def _safe_reward(fn, *args, default=None, **kwargs):
    """Run a reward_ledger operation without breaking the request.

    Reward accounting is best-effort: a locked DB or transient write error
    must never 500 a paid request. The caller provides a default return
    value for the failure path.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logging.getLogger("surp.gateway").warning(f"reward op {fn.__name__} failed (non-fatal): {e}")
        return default


async def _serve_free_completion(
    request: web.Request,
    payload: dict[str, Any],
    markets: list[dict[str, Any]],
    client_ip: str,
    free_class: str = "chat",
) -> web.Response:
    """Serve a treasury-sponsored free completion with live fallback.

    Supports per-class price ceilings (chat/coding/fast), free-tier API keys
    with elevated budgets, streaming with conservative buffers, provider
    health recording, and free-to-paid conversion tracking.
    """
    log = logging.getLogger("surp.gateway")
    is_stream = bool(payload.get("stream"))
    if payload.get("tools") or payload.get("tool_choice"):
        return web.json_response({"error": "free tier does not support tool calls; use the paid endpoint"}, status=400)
    max_tokens = min(int(payload.get("max_tokens") or fm.MAX_OUTPUT_TOKENS), fm.MAX_OUTPUT_TOKENS)
    payload["max_tokens"] = max_tokens

    # Free-tier API key support: heavy users can present an elevated free key.
    auth = request.headers.get("Authorization", "")
    free_key_rec = None
    if auth.startswith("Bearer sk-surp-free-"):
        free_key_rec = fm.validate_free_key(auth[7:])
        if free_key_rec is None:
            return web.json_response({"error": "invalid free-tier key"}, status=401)

    if free_key_rec:
        client_id = free_key_rec["key_hash"][:24]
        elevated_req = free_key_rec["elevated_requests"]
        elevated_tok = free_key_rec["elevated_tokens"]
    else:
        client_id = hashlib.sha256(client_ip.encode()).hexdigest()[:24]
        elevated_req = 0
        elevated_tok = 0

    # Budget check: streaming uses a larger conservative buffer.
    if is_stream:
        ok, reason = fm.can_serve_streaming(client_id, is_key=bool(free_key_rec),
                                            elevated_requests=elevated_req, elevated_tokens=elevated_tok)
    else:
        ok, reason = fm.can_serve_free(client_id, max_tokens, is_key=bool(free_key_rec),
                                        elevated_requests=elevated_req, elevated_tokens=elevated_tok)
    if not ok:
        # Record a potential conversion: this user hit the free wall.
        fm.record_conversion(client_id, "free", "best-chat")
        return web.json_response({
            "error": "free tier budget exhausted",
            "reason": reason,
            "stats": fm.live_stats(),
            "paid_option": "Use surp/best-chat with x402 for guaranteed access.",
        }, status=429, headers={"Retry-After": "3600"})

    # Select the per-class sponsored pool. If a specialized class (coding/fast)
    # has no eligible models, gracefully fall back to the general chat pool so
    # the request still succeeds rather than 503ing.
    if free_class == "coding":
        pool = fm.sponsored_pool_for_class(markets, "coding")
    elif free_class == "fast":
        pool = fm.sponsored_pool_for_class(markets, "fast")
    else:
        pool = fm.sponsored_pool(markets)
    if not pool and free_class != "chat":
        pool = fm.sponsored_pool(markets)
        log.info(f"free/{free_class} pool empty, falling back to general free pool")
    if not pool:
        return web.json_response({
            "error": f"no live models currently meet the sponsored-free {free_class} guardrails",
            "max_model_usd_per_1m": fm.CLASS_CEILINGS.get(free_class, fm.MAX_MODEL_USD_PER_1M),
        }, status=503)

    failed: set[str] = set()
    attempts: list[dict[str, Any]] = []
    started = time.monotonic()
    for candidate in fm.fallback_order(pool, failed)[:fm.FALLBACK_ATTEMPTS]:
        model_id = str(candidate["model"])
        fwd = dict(payload)
        fwd["model"] = model_id
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{RESOLVER_BASE}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json=fwd,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as upstream:
                    raw_body = await upstream.read()
                    status = upstream.status
            try:
                data = json.loads(raw_body)
            except Exception:
                data = {"error": "upstream returned non-JSON", "raw": raw_body[:120].decode(errors="replace")}
            if status == 200 and data.get("choices"):
                usage = data.get("usage") or {}
                tokens = int(usage.get("total_tokens") or
                             (int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)))
                latency = int((time.monotonic() - started) * 1000)
                # Record health sample for this model.
                ph.record(model_id, status="ok", latency_ms=latency, tokens=tokens,
                          provider=str(candidate.get("provider", "")))
                if free_key_rec:
                    fm.record_free_key_usage(auth[7:], model_id, tokens, "ok")
                else:
                    fm.record_usage(client_id, model_id, tokens, "ok", latency)
                data["surp_free"] = {
                    "sponsored": True,
                    "price_usd": "$0.00",
                    "routed_model": model_id,
                    "free_class": free_class,
                    "fallback_attempts": len(attempts),
                    "daily_stats": fm.live_stats(),
                    "conversion_stats": fm.conversion_stats(),
                    "catalog_methodology": "OmniRoute-inspired, pool-deduped free-tier accounting; inference sponsored by surp, not third-party free credentials.",
                }
                return web.json_response(data, headers={
                    "X-Surp-Free": "true",
                    "X-Routed-Model": model_id,
                    "X-Surp-Free-Class": free_class,
                    "X-Surp-Fallback-Attempts": str(len(attempts)),
                    "Cache-Control": "no-store",
                })
            error = data.get("error")
            attempts.append({"model": model_id, "status": status, "error": error})
            failed.add(model_id)
            ph.record(model_id, status="failed", latency_ms=0, tokens=0,
                      provider=str(candidate.get("provider", "")))
            if free_key_rec:
                fm.record_free_key_usage(auth[7:], model_id, 0, "failed")
            else:
                fm.record_usage(client_id, model_id, 0, "failed", 0)
        except Exception as e:
            attempts.append({"model": model_id, "status": 0, "error": str(e)[:120]})
            failed.add(model_id)
            ph.record(model_id, status="failed", latency_ms=0, tokens=0,
                      provider=str(candidate.get("provider", "")))
            if free_key_rec:
                fm.record_free_key_usage(auth[7:], model_id, 0, "failed")
            else:
                fm.record_usage(client_id, model_id, 0, "failed", 0)
            log.warning(f"free fallback failed for {model_id}: {e}")

    return web.json_response({
        "error": f"all sponsored-free {free_class} fallback models failed",
        "attempts": attempts,
        "paid_option": f"Use surp/best-{'coding' if free_class == 'coding' else 'chat'} with x402 for broader model availability.",
    }, status=503)


def _log_user_usage(request: web.Request, combo: str, model: str,
                    tokens_in: int, tokens_out: int, cost_cents: int,
                    tx_hash: str = "") -> None:
    """Log usage to a user's account if they authenticated via a user-account API key.

    This is distinct from the legacy prepaid API keys in stats.py — user-account
    keys are created via the /app dashboard and tracked per-user. Fault-isolated:
    a DB error never breaks a paid request.
    """
    try:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return
        raw_key = auth[7:].strip()
        if not raw_key.startswith("surp_"):
            return  # legacy key, handled by stats.py
        key_rec = ua.validate_api_key(raw_key)
        if not key_rec:
            return
        # Budget check + increment (best-effort; if budget exceeded post-hoc,
        # we still log but the key may be over — the next request will block)
        ua.check_budget(key_rec["key_id"], cost_cents)
        ua.log_usage(key_rec["user_id"], key_rec["key_id"],
                     f"surp/{combo}", tokens_in, tokens_out, cost_cents, tx_hash)
    except Exception as e:
        logging.getLogger("surp.gateway").debug(f"_log_user_usage skipped: {e}")


async def chat_completions(request: web.Request) -> web.StreamResponse:
    """Gateway endpoint. Two payment paths:

    A) API key: Authorization: Bearer sk-surp-*** → deduct from prepaid balance.
    B) x402: PAYMENT-SIGNATURE header → verify + settle USDC on Base.

    If neither is present, return 402 with payment requirements.
    """
    log = logging.getLogger("surp.gateway")
    t0 = time.monotonic()
    client_ip = request.headers.get("X-Real-IP") or request.remote or "?"

    # Rate limit
    allowed, remaining = st.check_rate_limit(client_ip, "chat")
    if not allowed:
        return web.json_response({"error": "rate limit exceeded — try again in a minute"}, status=429,
                                 headers={"Retry-After": "60"})

    try:
        raw = await request.read()
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        return web.json_response({"error": f"invalid JSON: {e}"}, status=400)

    model = payload.get("model", "")
    if not model.startswith("surp/"):
        return web.json_response({"error": "model must be surp/<combo> (e.g. surp/best-chat) or surp/strict/<combo>"}, status=400)
    combo = model[len("surp/"):]

    # ── BYO guardrails: user-controlled routing constraints ──
    # These let a caller pin a concrete model, restrict providers, cap price,
    # or bypass the response cache — all without changing the combo itself.
    strict_mode = combo.startswith("strict/")
    if strict_mode:
        combo = combo[len("strict/"):]
    routing_reason = ""  # set by the routing block below; default for early paths
    max_price = float(payload.pop("max_price_per_1m", 0) or 0)
    provider_hint = payload.pop("provider", None)
    bypass_cache = bool(payload.pop("surp_bypass_cache", False))
    # SVI routing mode: how to pick the winner from the pool. Default 'cost'
    # preserves existing behavior (cheapest). 'value'/'balanced'/'speed'/'intel'
    # route by the Surp Value Index with the corresponding weight lens, and
    # surp_weights accepts a custom (cost:intel:speed) triple.
    surp_mode = str(payload.pop("surp_mode", "cost") or "cost").lower()
    surp_weights = vi.parse_weights(str(payload.pop("surp_weights", "") or ""))
    if surp_mode not in vi.MODE_WEIGHTS:
        return web.json_response(
            {"error": f"surp_mode must be one of {sorted(vi.MODE_WEIGHTS)}"},
            status=400,
        )

    try:
        markets = await GCACHE.get()
    except Exception as e:
        return web.json_response({"error": f"market data unavailable: {e}"}, status=502)

    # Treasury-sponsored free routes. `surp/free` is the canonical chat route;
    # `surp/free-coding` and `surp/free-fast` restrict the sponsored pool to
    # those model classes with their own (higher) price ceilings.
    if combo in ("free", "srup-free", "free-coding", "free-fast"):
        free_class = "coding" if combo == "free-coding" else "fast" if combo == "free-fast" else "chat"
        return await _serve_free_completion(request, payload, markets, client_ip, free_class=free_class)

    live_model, debug, surplus_price, pool = resolve_combo(combo, markets)
    if live_model is None:
        return web.json_response({"error": f"combo resolution failed: {debug}"}, status=404)

    # Cache-aware routing: keep a recently used model when it remains within the
    # configured price tolerance of the live cheapest model. This preserves
    # provider-side KV/prefix cache locality without letting prices drift far.
    routing_pool = cr.pool_for(combo, markets)
    # Apply BYO provider pin: narrow the pool to the requested provider(s).
    if provider_hint:
        hints = provider_hint if isinstance(provider_hint, list) else [provider_hint]
        hints_lower = {str(h).lower() for h in hints}
        routing_pool = [m for m in routing_pool if str(m.get("provider", "")).lower() in hints_lower
                        or str(m.get("seller", "")).lower() in hints_lower]
        if not routing_pool:
            return web.json_response(
                {"error": "no sellable models match the requested provider pin",
                 "providers_requested": sorted(hints_lower)},
                status=404,
            )
    # Apply BYO max-price ceiling: drop anything above the cap.
    if max_price > 0:
        ceiling_atomic = max_price * cr.PRICE_DIVISOR
        routing_pool = [m for m in routing_pool if cr.price_of(m) <= ceiling_atomic]
        if not routing_pool:
            return web.json_response(
                {"error": f"no sellable models at or below ${max_price}/1M tokens",
                 "live_cheapest": round(cr.usd_per_1m({"best_price_per_1m": surplus_price}), 4)},
                status=404,
            )
    try:
        if surp_mode != "cost" or surp_weights is not None:
            # SVI-aware routing: pick the winner by the requested value lens
            # instead of pure cheapest. Build the pool as {model, price, tps}
            # and let value_index decide (falls back to cheapest if no model
            # in the pool has verified speed).
            _pool_for_svi = [
                {
                    "model": m.get("model"),
                    "price_usd_per_1m": cr.usd_per_1m(m),
                    "p50_tps": mb.summary(m.get("model", "")).get("p50_output_tps", 0),
                }
                for m in routing_pool if m.get("model")
            ]
            _winner_model, routing_reason, _ = vi.pick_winner(
                _pool_for_svi, mode=surp_mode, weights=surp_weights
            )
            if _winner_model is None:
                raise RuntimeError("svi pick_winner returned no model")
            winner = next((m for m in routing_pool if m.get("model") == _winner_model), None)
            if winner is None:
                raise RuntimeError("svi winner not in pool")
            resolved_model = winner["model"]
            surplus_price = cr.price_of(winner)
        else:
            winner, routing_reason = _STICKY_ROUTER.choose(combo, routing_pool)
            resolved_model = winner["model"]
            surplus_price = cr.price_of(winner)
    except Exception:
        resolved_model = live_model
        routing_reason = "live-cheapest"
    # In strict mode, force the live cheapest and never let sticky routing
    # override the user's explicit price/provider intent.
    if strict_mode:
        if routing_pool:
            winner = min(routing_pool, key=cr.price_of)
            resolved_model = winner["model"]
            surplus_price = cr.price_of(winner)
            routing_reason = "strict-live-cheapest"

    # Exact-response caching is opt-in-by-safety: deterministic, non-streaming,
    # tool-free requests only. We peek before payment so cached responses can be
    # quoted at the discounted cache-hit price, then consume the hit only after
    # payment succeeds. The caller can force a bypass with surp_bypass_cache.
    cacheable = ct.is_response_cacheable(payload) and not bypass_cache
    cache_key = ct.request_cache_key(payload) if cacheable else ""
    cached_preview = _RESPONSE_CACHE.peek(cache_key) if cacheable else None

    expected_tokens = int(payload.get("max_tokens") or 1500)
    cents = CACHE_HIT_CENTS if cached_preview else _price_to_cents(surplus_price, expected_tokens)
    required_microcents = int(cents * 10_000)

    # ── Path A: API key ──
    auth_header = request.headers.get("Authorization", "")
    payment_method = "x402"
    payer = ""
    tx_hash = ""
    if auth_header.startswith("Bearer "):
        api_key_raw = auth_header[7:].strip()
        # User-account API keys (surp_ prefix) — created via /app dashboard
        if api_key_raw.startswith("surp_"):
            ua_key = ua.validate_api_key(api_key_raw)
            if ua_key is None:
                return web.json_response({"error": "invalid API key"}, status=401)
            # Budget check: does this key have room for this cost?
            if not ua.check_budget(ua_key["key_id"], required_microcents):
                return web.json_response({
                    "error": "budget exceeded for this API key",
                    "key_id": ua_key["key_id"],
                    "budget_cents": ua_key["budget_cents"],
                    "spent_cents": ua_key["spent_cents"],
                    "required_cents": cents,
                }, status=402)
            payment_method = "user_api_key"
            payer = f"user:{ua_key['user_id'][:8]}:key:{ua_key['key_id'][:8]}"
            log.info(f"user-key charge: {required_microcents} mc for {combo} -> {resolved_model}")
        else:
            # Legacy prepaid API keys (stats.py)
            key_rec = st.validate_api_key(api_key_raw)
            if key_rec is None:
                return web.json_response({"error": "invalid API key"}, status=401)
            if not st.charge_api_key(key_rec["key_hash"], required_microcents):
                return web.json_response({
                    "error": "insufficient balance",
                    "balance_microcents": key_rec["balance_usdc_microcents"],
                    "required_microcents": required_microcents,
                    "top_up": "POST /api/keys/topup",
                }, status=402)
            payment_method = "api_key"
            payer = f"key:{key_rec['key_hash'][:8]}"
            log.info(f"api-key charge: {required_microcents} mc for {combo} -> {resolved_model}")

    # ── Path B: NFT/token-gated eligibility ──
    # Holders of the configured ERC-20/721 bypass x402 entirely, with an
    # optional discount applied. Wallet identity is their payment identity,
    # which also becomes their SRP reward account.
    elif NFT_GATE_ENABLED:
        gate_wallet = (request.headers.get("X-Wallet") or "").strip()
        if not gate_wallet or not gate_wallet.startswith("0x") or len(gate_wallet) != 42:
            return web.json_response({
                "error": "NFT-gated mode: send your wallet via X-Wallet header (0x... 42 chars)",
                "gate_contract": ng.CONTRACT,
                "gate_threshold": ng.ELIGIBILITY_THRESHOLD,
            }, status=402)
        if not await ng.check_async(gate_wallet):
            return web.json_response({
                "error": "wallet does not hold the required token",
                "wallet": gate_wallet[:10] + "...",
                "contract": ng.CONTRACT,
                "threshold": ng.ELIGIBILITY_THRESHOLD,
            }, status=402)
        # Apply optional gate-holder discount.
        if NFT_GATE_DISCOUNT_BPS > 0:
            required_microcents = int(required_microcents * (10_000 - NFT_GATE_DISCOUNT_BPS) / 10_000)
            cents = required_microcents / 10_000
        payment_method = "nft_gate"
        payer = gate_wallet
        log.info(f"NFT-gated access: {gate_wallet[:10]}... for {combo} -> {resolved_model} (discount={NFT_GATE_DISCOUNT_BPS}bps)")

    # ── Path C: x402 ──
    elif not (request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")):
        resp = _build_payment_required(combo, resolved_model, surplus_price, expected_tokens,
                                       routing_reason=routing_reason)
        log.info(f"402 {combo} -> {resolved_model} price=${resp['body']['price_usd']} (no payment)")
        return web.json_response(resp["body"], status=resp["status"], headers=resp["headers"])

    else:
        payment_header = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")
        loop = asyncio.get_running_loop()

        def _verify_and_settle():
            try:
                import base64
                raw_payload = base64.b64decode(payment_header)
                from x402.schemas.payments import PaymentPayload
                payload_dict = json.loads(raw_payload)
                payload_obj = PaymentPayload.model_validate(payload_dict)
                requirements = payload_obj.accepted
                vr = _facilitator.verify(payload_obj, requirements)
                if not vr.is_valid:
                    return {"ok": False, "error": f"verification failed: {vr.invalid_reason}: {vr.invalid_message}"}
                sr = _facilitator.settle(payload_obj, requirements)
                if not sr.success:
                    return {"ok": False, "error": f"settlement failed: {sr.error_reason}: {sr.error_message}"}
                return {"ok": True, "tx": sr.transaction, "network": sr.network, "payer": sr.payer}
            except Exception as e:
                log.error(f"facilitator error: {e}\n{traceback.format_exc()}")
                return {"ok": False, "error": f"facilitator error: {str(e)}"}

        result = await loop.run_in_executor(None, _verify_and_settle)
        if not result.get("ok"):
            return web.json_response({"error": result.get("error", "payment failed")}, status=402)
        tx_hash = result.get("tx", "")
        payer = result.get("payer", "")
        log.info(f"payment settled: {tx_hash} for {combo} -> {resolved_model}")

    # Earmark a share of estimated gateway revenue to the SRP rebate pool.
    # For fresh inference, isolate the markup component; for an exact cache hit,
    # the full micropayment is cache-generated revenue because no upstream call occurs.
    # All reward accounting is best-effort: a locked DB must never break a paid request.
    if cached_preview is not None:
        rewardable_revenue = required_microcents
    else:
        rewardable_revenue = int(required_microcents * MARKUP_BPS / (10_000 + MARKUP_BPS))
    _safe_reward(rl.fund_pool, int(rewardable_revenue * rl.REBATE_POOL_SHARE))

    # A cached answer is returned only after normal API-key debit or x402
    # settlement. The request is still metered, but at the discounted cache-hit
    # price. This prevents unpaid cache probing and replay abuse.
    if cached_preview is not None:
        cached = _RESPONSE_CACHE.get(cache_key) or cached_preview
        tokens_saved = int(cached.get("tokens_in", 0)) + int(cached.get("tokens_out", 0))
        author = _safe_reward(rl.cache_author, cache_key, default=None)
        author_srp = _safe_reward(rl.mint,
            author or "", "cache_hit_author", combo, cache_key, tokens_saved,
            rl.HIT_AUTHOR_REWARD_PER_TOKEN, "another agent reused your cached response",
            default=0)
        reader_srp = _safe_reward(rl.mint,
            payer, "cache_hit_reader", combo, cache_key, tokens_saved,
            rl.HIT_READER_REWARD_PER_TOKEN, "you reused cached computation",
            default=0)
        reader_balance = _safe_reward(rl.balance, payer, default={})
        body = dict(cached["response"])
        body["surp_cache"] = {
            "hit": True,
            "type": "exact-response",
            "age_seconds": max(0, int(time.time()) - int(cached["created_at"])),
            "tokens_saved": tokens_saved,
            "price_usd": f"${CACHE_HIT_CENTS / 100:.3f}",
        }
        body["surp_rewards"] = {
            "reader_srp_minted": reader_srp,
            "author_srp_minted": author_srp,
            "reader_balance": reader_balance.get("balance_srp", 0),
        }
        headers = {
            "X-Payment-Settled": "true",
            "X-Routed-Model": cached["model"],
            "X-Surp-Cache": "HIT",
            "X-Surp-Cache-Type": "exact-response",
            "X-Surp-Routing": routing_reason,
            "Cache-Control": "private, no-store",
        }
        latency_ms = int((time.monotonic() - t0) * 1000)
        st.log_request(combo, cached["model"], payer, required_microcents, tx_hash,
                       "response_cache", tokens_in=0, tokens_out=0, latency_ms=latency_ms)
        _log_user_usage(request, combo, cached["model"], 0, 0, cents, tx_hash)
        return web.json_response(body, headers=headers)

    if cacheable:
        _RESPONSE_CACHE.record_miss()

    # ── Forward to resolver ──
    is_stream = bool(payload.get("stream"))
    fwd_headers = {"Content-Type": "application/json"}
    # Pin the concrete model selected by cache-aware routing. The internal
    # resolver treats concrete model ids as passthrough, so seller/model locality
    # is preserved instead of resolving the combo a second time.
    fwd_payload = dict(payload)
    fwd_payload["model"] = resolved_model
    fwd_raw = json.dumps(fwd_payload, separators=(",", ":"), ensure_ascii=False).encode()
    try:
        session = aiohttp.ClientSession()
        upstream = await session.post(
            f"{RESOLVER_BASE}/v1/chat/completions",
            headers=fwd_headers, data=fwd_raw,
            timeout=aiohttp.ClientTimeout(total=None, sock_read=600),
        )
    except Exception as e:
        await session.close()
        return web.json_response({"error": f"resolver connection failed: {e}"}, status=502)

    latency_ms = int((time.monotonic() - t0) * 1000)

    if not is_stream:
        upstream_body = await upstream.read()
        upstream_headers = {
            k: v for k, v in upstream.headers.items()
            if k.lower() in ("content-type", "cache-control", "x-request-id")
        }
        await session.close()
        headers = {
            **upstream_headers,
            "X-Payment-Settled": "true",
            "X-Routed-Model": resolved_model or "",
            "X-Surplus-Price-Per-1M": str(surplus_price),
            "X-Surp-Cache": "MISS" if cacheable else "BYPASS",
            "X-Surp-Routing": routing_reason,
        }
        tokens_in = tokens_out = 0
        if cacheable and upstream.status == 200:
            try:
                response_json = json.loads(upstream_body)
                usage = response_json.get("usage") or {}
                tokens_in = int(usage.get("prompt_tokens") or 0)
                tokens_out = int(usage.get("completion_tokens") or 0)
                _safe_reward(_RESPONSE_CACHE.put, cache_key, combo, resolved_model, response_json,
                             tokens_in=tokens_in, tokens_out=tokens_out)
                # The payer who funded this cache write becomes its author and
                # earns SRP immediately; later hits mint additional author rewards.
                writer_srp = _safe_reward(rl.mint,
                    payer, "cache_write", combo, cache_key,
                    tokens_in + tokens_out, rl.WRITE_REWARD_PER_TOKEN,
                    "you funded reusable cached computation",
                    default=0)
                if writer_srp:
                    writer_balance = _safe_reward(rl.balance, payer, default={})
                    response_json["surp_rewards"] = {
                        "writer_srp_minted": writer_srp,
                        "writer_balance": writer_balance.get("balance_srp", 0),
                    }
                    upstream_body = json.dumps(response_json, separators=(",", ":")).encode()
            except Exception as e:
                log.warning(f"response cache store skipped: {e}")
        st.log_request(combo, resolved_model, payer, required_microcents, tx_hash,
                       payment_method, tokens_in=tokens_in, tokens_out=tokens_out,
                       latency_ms=latency_ms)
        _log_user_usage(request, combo, resolved_model, tokens_in, tokens_out, cents, tx_hash)
        # Record cache-affinity sample: which model served which prefix with
        # what latency. This builds the ad-network-style prefix→provider index
        # that enables discounted bids for cached prefixes. Record even without
        # usage data (use total expected tokens as fallback) so the index
        # populates on every non-streaming request.
        if latency_ms > 0:
            sys_msg = ""
            user_msg = ""
            for msg in (payload.get("messages") or []):
                if msg.get("role") == "system" and not sys_msg:
                    sys_msg = str(msg.get("content", ""))
                elif msg.get("role") == "user" and not user_msg:
                    user_msg = str(msg.get("content", ""))
            prefix_fp = ca.prefix_hash(sys_msg, user_msg)
            sample_tokens = (tokens_in + tokens_out) or expected_tokens or 1
            _safe_reward(ca.record_sample, prefix_fp, resolved_model,
                         sample_tokens, latency_ms,
                         provider=str(winner.get("provider", "")) if winner else "",
                         default=None)
        return web.Response(body=upstream_body, status=upstream.status, headers=headers)

    out = web.StreamResponse(status=upstream.status, headers={
        k: v for k, v in upstream.headers.items()
        if k.lower() in ("content-type", "cache-control", "x-request-id")
    })
    out.content_type = "text/event-stream"
    out.headers["Cache-Control"] = "no-cache"
    out.headers["X-Payment-Settled"] = "true"
    out.headers["X-Routed-Model"] = resolved_model or ""
    out.headers["X-Surplus-Price-Per-1M"] = str(surplus_price)
    out.headers["X-Surp-Cache"] = "BYPASS"
    out.headers["X-Surp-Routing"] = routing_reason
    await out.prepare(request)
    try:
        async for chunk in upstream.content.iter_chunked(4096):
            await out.write(chunk)
    except Exception as e:
        log.warning(f"stream pipe error: {e}")
    finally:
        await session.close()
        await out.write_eof()

    st.log_request(combo, resolved_model, payer, required_microcents, tx_hash,
                   payment_method, tokens_in=0, tokens_out=expected_tokens, latency_ms=latency_ms)
    _log_user_usage(request, combo, resolved_model, 0, expected_tokens, cents, tx_hash)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Status, Dashboard, API Keys, Combo History endpoints
# ──────────────────────────────────────────────────────────────────────────────

async def page_status(request: web.Request) -> web.Response:
    s = {
        **st.global_stats(),
        "response_cache": _RESPONSE_CACHE.stats(),
        "sticky_routing": _STICKY_ROUTER.stats(),
        "rewards": rl.global_stats(),
        "free_tier": fm.live_stats(),
    }
    health = {
        "resolver": "ok" if GCACHE._markets else "warming up",
        "facilitator": FACILITATOR_URL,
        "cached_markets": len(GCACHE._markets or []),
    }
    html = _render_html(_render_status_content(s, health), "/status")
    return web.Response(text=html, content_type="text/html")


async def page_dashboard(request: web.Request) -> web.Response:
    html = _render_html(_DASHBOARD_CONTENT, "/dashboard")
    return web.Response(text=html, content_type="text/html")


async def api_dashboard_data(request: web.Request) -> web.Response:
    addr = request.query.get("address", "").strip()
    if not addr or not addr.startswith("0x") or len(addr) != 42:
        return web.json_response({"error": "provide ?address=0x..."}, status=400)
    data = st.payer_stats(addr)
    return web.json_response(data)


async def api_keys_create(request: web.Request) -> web.Response:
    """POST /api/keys/create — create a prepaid API key."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    label = str(body.get("label", ""))[:60] or "anonymous"
    balance_cents = int(body.get("balance_cents", 0))
    rec = st.create_api_key(label, balance_cents * 10_000)
    if "error" in rec:
        return web.json_response(rec, status=500)
    return web.json_response({**rec, "note": "store this key safely — it won't be shown again"})


async def api_keys_balance(request: web.Request) -> web.Response:
    """GET /api/keys/balance?key=sk-surp-*** — check remaining balance."""
    key = request.query.get("key", "").strip()
    rec = st.validate_api_key(key)
    if rec is None:
        return web.json_response({"error": "invalid key"}, status=404)
    return web.json_response({
        "label": rec["label"],
        "balance_usd_cents": rec["balance_usdc_microcents"] // 10_000,
        "total_requests": rec["total_requests"],
        "last_used": rec["last_used"],
    })


async def api_combo_history(request: web.Request) -> web.Response:
    """GET /api/combos/history?combo=best-coding&hours=24 — sparkline data."""
    combo = request.query.get("combo", "best-coding")
    hours = min(int(request.query.get("hours", 24)), 168)
    data = st.combo_history(combo, hours)
    return web.json_response({"combo": combo, "hours": hours, "points": data})


async def api_global_stats(request: web.Request) -> web.Response:
    """GET /api/stats — global usage, cache, reward, free-tier, and affinity stats."""
    return web.json_response({
        **st.global_stats(),
        "response_cache": _RESPONSE_CACHE.stats(),
        "sticky_routing": _STICKY_ROUTER.stats(),
        "rewards": rl.global_stats(),
        "free_tier": fm.live_stats(),
        "cache_affinity": ca.global_stats(),
    })


async def api_reward_balance(request: web.Request) -> web.Response:
    """GET /api/rewards?payer=0x... or key:hash — inspect SRP rewards."""
    payer = request.query.get("payer", "").strip()
    if not payer:
        return web.json_response({"error": "provide ?payer=0x... or key:<hash-prefix>"}, status=400)
    return web.json_response(rl.balance(payer))


async def page_connect(request: web.Request) -> web.Response:
    html = _render_html(_CONNECT_CONTENT, "/connect")
    return web.Response(text=html, content_type="text/html")



def _render_status_content(s: dict, health: dict) -> str:
    """Render the status page from live stats."""
    total = s.get("total_requests", 0)
    usd_cents = s.get("total_usdc_cents", 0)
    req_24h = s.get("requests_24h", 0)
    payers = s.get("unique_payers", 0)
    top_combos = s.get("top_combos", [])
    top_models = s.get("top_models", [])
    cache_stats = s.get("response_cache", {})
    sticky_stats = s.get("sticky_routing", {})
    reward_stats = s.get("rewards", {})
    free_stats = s.get("free_tier", {})
    last_ts = s.get("last_request_ts")
    last_str = "never"
    if last_ts:
        ago = int(time.time()) - last_ts
        if ago < 60: last_str = f"{ago}s ago"
        elif ago < 3600: last_str = f"{ago//60}m ago"
        else: last_str = f"{ago//3600}h ago"

    combo_rows = "".join(
        f"<tr><td class='combo'>{c['combo']}</td><td>{c['count']}</td></tr>"
        for c in top_combos
    ) or '<tr><td colspan="2" class="dim">no data yet</td></tr>'
    model_rows = "".join(
        f"<tr><td class='model'>{m['model']}</td><td>{m['count']}</td></tr>"
        for m in top_models
    ) or '<tr><td colspan="2" class="dim">no data yet</td></tr>'

    return f"""
<h1>status</h1>
<p class="dim prompt">systemctl status surp-gateway</p>

<div class="grid">
  <div class="card"><div class="num">{total}</div><div class="lbl">total requests served</div></div>
  <div class="card"><div class="num">{req_24h}</div><div class="lbl">requests (24h)</div></div>
  <div class="card"><div class="num">${usd_cents / 100:.2f}</div><div class="lbl">total USDC settled</div></div>
  <div class="card"><div class="num">{payers}</div><div class="lbl">unique wallets</div></div>
</div>

<h2>system health</h2>
<table>
<tbody>
  <tr><td class="dim">resolver</td><td>{health.get('resolver', '?')}</td></tr>
  <tr><td class="dim">facilitator</td><td>{health.get('facilitator', '?')}</td></tr>
  <tr><td class="dim">cached markets</td><td>{health.get('cached_markets', 0)}</td></tr>
  <tr><td class="dim">last request</td><td>{last_str}</td></tr>
  <tr><td class="dim">network</td><td>{NETWORK}</td></tr>
  <tr><td class="dim">markup</td><td>{MARKUP_BPS} bps ({MARKUP_BPS/100:.0f}%)</td></tr>
</tbody>
</table>

<h2>cache engine</h2>
<div class="grid">
  <div class="card"><div class="num">{cache_stats.get('hit_rate_pct', 0)}%</div><div class="lbl">exact-cache hit rate</div></div>
  <div class="card"><div class="num">{cache_stats.get('tokens_saved', 0)}</div><div class="lbl">tokens not recomputed</div></div>
  <div class="card"><div class="num">{cache_stats.get('live_entries', 0)}</div><div class="lbl">live cached answers</div></div>
  <div class="card"><div class="num">{sticky_stats.get('sticky_reuses', 0)}</div><div class="lbl">sticky route reuses</div></div>
</div>
<table><tbody>
  <tr><td class="dim">exact response TTL</td><td>{CACHE_TTL_SECONDS}s</td></tr>
  <tr><td class="dim">cache-hit price</td><td>${CACHE_HIT_CENTS / 100:.3f} per request</td></tr>
  <tr><td class="dim">sticky route window</td><td>{STICKY_TTL_SECONDS}s</td></tr>
  <tr><td class="dim">price tolerance</td><td>{STICKY_TOLERANCE_PCT:.0f}% above live cheapest</td></tr>
</tbody></table>
<p class="dim">Only deterministic, non-streaming, tool-free requests use exact-response caching. Prompts are SHA-256 fingerprinted and are never stored. <a href="/cache">how the cache engine works &raquo;</a></p>

<h2>cache flywheel rewards (SRP)</h2>
<div class="grid">
  <div class="card"><div class="num">${reward_stats.get('rebate_pool_usd', 0):.4f}</div><div class="lbl">rebate pool backing</div></div>
  <div class="card"><div class="num">{reward_stats.get('srp_outstanding', 0)}</div><div class="lbl">SRP outstanding</div></div>
  <div class="card"><div class="num">{reward_stats.get('holders', 0)}</div><div class="lbl">reward holders</div></div>
  <div class="card"><div class="num">{reward_stats.get('value_per_srp_cents', 0):.6f}¢</div><div class="lbl">value per SRP</div></div>
</div>
<p class="dim">Cache writers and readers earn off-chain SRP points backed by an earmarked share of gateway revenue. This is a simulation ledger for a future RevNet/Juicebox deployment — no token exists on-chain yet.</p>

<h2>sponsored free tier</h2>
<div class="grid">
  <div class="card"><div class="num">{free_stats.get('requests_remaining', 0)}</div><div class="lbl">free requests remaining today</div></div>
  <div class="card"><div class="num">{free_stats.get('tokens_remaining', 0):,}</div><div class="lbl">free tokens remaining today</div></div>
  <div class="card"><div class="num">{free_stats.get('requests_today', 0)}</div><div class="lbl">free requests served today</div></div>
  <div class="card"><div class="num">{free_stats.get('avg_latency_ms', 0):.0f}ms</div><div class="lbl">average free latency</div></div>
</div>
<p class="dim"><code>surp/free</code> is treasury-sponsored with no wallet or payment required. <a href="/free-models">live eligible models, budgets, and methodology &raquo;</a></p>

<h2>top combos</h2>
<table><thead><tr><th>combo</th><th>requests</th></tr></thead><tbody>{combo_rows}</tbody></table>

<h2>top models routed</h2>
<table><thead><tr><th>model</th><th>times routed</th></tr></thead><tbody>{model_rows}</tbody></table>

<p class="dim">live data from <code>GET /api/stats</code>. stats are best-effort &mdash; a logging failure never blocks a request.</p>

<script>
// Dynamic browser-tab title: shows live request count + cache hit rate,
// updating every 15s so the tab itself is a live status indicator.
(async () => {{
  const fmt = (n) => n >= 1000 ? (n/1000).toFixed(1) + "k" : String(n);
  const base = "surp.ivc.lol status";
  async function refresh() {{
    try {{
      const r = await fetch("/api/stats");
      const d = await r.json();
      const reqs = d.total_requests || 0;
      const cache = d.response_cache || {{}};
      const hit = cache.hit_rate_pct || 0;
      document.title = `[${{fmt(reqs)}} reqs · ${{hit}}% cached] ${{base}}`;
    }} catch (e) {{ /* tab title stays on last good value */ }}
  }}
  refresh();
  setInterval(refresh, 15000);
}})();
</script>
"""

# ──────────────────────────────────────────────────────────────────────────────
# HTML templates
# ──────────────────────────────────────────────────────────────────────────────

_HTML_BASE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90' font-family='monospace'>₵</text></svg>">
<meta name="description" content="__DESC__">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:type" content="website">
<meta property="og:url" content="https://surp.ivc.lol__PATH__">
<link rel="canonical" href="https://surp.ivc.lol__PATH__">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://surp.ivc.lol/og-image.png">
<meta property="og:image" content="https://surp.ivc.lol/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="surp.ivc.lol — cheapest LLM API on the internet">
<meta name="base:app_id" content="6a79b620d198f685bc61e2ef"/>
<script type="application/ld+json">__JSONLD__</script>
<style>
  :root {
    --bg: #000000;
    --bg-alt: #0a0a0a;
    --fg: #e0e0e0;
    --fg-dim: #888888;
    --accent: #00ff9c;
    --accent-dim: #008c54;
    --red: #ff3b3b;
    --yellow: #ffd23f;
    --border: #1a1a1a;
    --border-bright: #2a2a2a;
    --mono: "JetBrains Mono", "Fira Code", "SF Mono", "Courier New", monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { background: var(--bg); color: var(--fg); font-family: var(--mono); font-size: 14px; line-height: 1.5; min-height: 100vh; }
  a { color: #5ce1ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  body::before {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 100; opacity: 0.04;
    background-image: repeating-linear-gradient(0deg, #fff 0px, #fff 1px, transparent 1px, transparent 3px);
  }
  .container { max-width: 960px; margin: 0 auto; padding: 24px 20px 60px; }
  nav { display: flex; justify-content: space-between; align-items: center; padding: 14px 0; border-bottom: 1px solid var(--border); margin-bottom: 28px; gap: 12px; }
  .brand { color: var(--accent); font-weight: bold; font-size: 16px; letter-spacing: -0.5px; flex-shrink: 0; }
  .brand::before { content: "$ "; color: var(--fg-dim); }
  .brand::after { content: "\2588"; animation: blink 1s steps(2) infinite; aria-hidden: true; }
  @keyframes blink { 50% { opacity: 0; } }
  .brand span { animation: none; }
  nav ul { display: flex; gap: 14px; list-style: none; flex-wrap: wrap; justify-content: flex-end; row-gap: 6px; }
  nav a { color: var(--fg-dim); text-decoration: none; font-size: 13px; transition: color 0.15s; white-space: nowrap; }
  nav a:hover, nav a.active { color: var(--accent); }
  h1 { font-size: 28px; margin-bottom: 8px; letter-spacing: -0.5px; }
  h2 { font-size: 18px; color: var(--accent); margin-top: 32px; margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
  h2::before { content: "## "; color: var(--fg-dim); speak: never; }
  h3 { font-size: 14px; color: var(--yellow); margin-top: 22px; margin-bottom: 8px; }
  p { margin-bottom: 12px; color: var(--fg); }
  p.dim, .dim { color: var(--fg-dim); }
  code { background: var(--bg-alt); padding: 1px 6px; border: 1px solid var(--border); font-size: 12px; color: var(--accent); }
  pre { background: var(--bg-alt); border: 1px solid var(--border); padding: 14px 16px; overflow-x: auto; margin: 12px 0; font-size: 12px; line-height: 1.6; color: var(--fg); }
  pre::before { content: "$ "; color: var(--accent-dim); }
  .prompt::before { content: "$ "; color: var(--accent); }
  table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 12px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
  th { color: var(--fg-dim); text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }
  tr:hover { background: var(--bg-alt); }
  .combo { color: var(--accent); }
  .model { color: var(--fg); }
  .price { color: var(--yellow); }
  .savings { color: var(--accent); }
  .pool { color: var(--fg-dim); }
  .err { color: var(--red); }
  .cta { display: inline-block; margin-top: 16px; padding: 10px 18px; border: 1px solid var(--accent); color: var(--accent); text-decoration: none; font-size: 13px; transition: all 0.15s; }
  .cta:hover { background: var(--accent); color: var(--bg); }
  .cta::before { content: "▶ "; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin: 20px 0; }
  .card { border: 1px solid var(--border); padding: 16px; background: var(--bg-alt); }
  .card .num { font-size: 28px; color: var(--accent); font-weight: bold; }
  .card .lbl { color: var(--fg-dim); font-size: 11px; text-transform: uppercase; margin-top: 4px; letter-spacing: 0.5px; }
  .badge { display: inline-block; padding: 2px 8px; border: 1px solid var(--accent-dim); color: var(--accent); font-size: 10px; margin-left: 8px; vertical-align: middle; }
  .warn { border-left: 2px solid var(--yellow); padding-left: 12px; margin: 14px 0; color: var(--fg); font-size: 13px; }
  .warn::before { content: "⚠ "; color: var(--yellow); }
  footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border); color: var(--fg-dim); font-size: 11px; text-align: center; }
  footer a { color: var(--fg-dim); }
  footer a:hover { color: var(--accent); }
  .footer-links { display: flex; justify-content: center; gap: 14px; margin-bottom: 10px; }
  .social-link { display: inline-flex; align-items: center; opacity: 0.35; transition: opacity 0.2s; }
  .social-link:hover { opacity: 1; }
  .social-link svg { color: var(--fg-dim); }
  .social-link:hover svg { color: var(--accent); }
  input, select, textarea { background: var(--bg-alt); border: 1px solid var(--border-bright); color: var(--fg); padding: 8px 10px; font-family: var(--mono); font-size: 13px; width: 100%; }
  input:focus, textarea:focus, select:focus { outline: none; border-color: var(--accent); }
  button { background: var(--accent); color: var(--bg); border: none; padding: 8px 16px; font-family: var(--mono); font-size: 13px; cursor: pointer; font-weight: bold; }
  button:hover { background: var(--accent-dim); }
  label { color: var(--fg-dim); font-size: 12px; display: block; margin-bottom: 4px; }
  .field { margin-bottom: 14px; }
  .ascii { white-space: pre; color: var(--accent); font-size: 11px; line-height: 1.2; margin: 20px 0; overflow-x: auto; }

  @media (max-width: 640px) {
    .container { padding: 16px 12px 40px; }
    nav { flex-direction: column; align-items: stretch; gap: 8px; }
    nav ul { justify-content: center; gap: 10px; }
    h1 { font-size: 22px; }
    h2 { font-size: 16px; }
    pre { font-size: 11px; padding: 10px 12px; overflow-x: auto; }
    table { font-size: 11px; }
    th, td { padding: 6px 8px; }
    .grid { grid-template-columns: 1fr; }
    .hero-terminal { height: 160px; font-size: 11px; }
    .ascii { font-size: 9px; }
    .cta { display: block; text-align: center; margin-top: 10px; }
  }
  .combo-block { border: 1px solid var(--border); margin-bottom: 6px; background: var(--bg-alt); }
  .combo-block summary { padding: 9px 12px; cursor: pointer; display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; font-size: 12px; list-style: none; }
  .combo-block summary::-webkit-details-marker { display: none; }
  .combo-block summary::before { content: "▸"; color: var(--fg-dim); margin-right: 2px; }
  .combo-block[open] summary::before { content: "▾"; color: var(--accent); }
  .combo-block summary:hover { background: #0f0f0f; }
  .combo-block .arrow { color: var(--fg-dim); }
  .combo-block .poolcount { color: var(--fg-dim); margin-left: auto; font-size: 11px; }
  .combo-desc { padding: 0 12px 6px; font-size: 11px; }
  .pool-table { margin: 0; font-size: 11px; }
  .pool-table th { background: #060606; }
  .pool-table tr.winner { background: #04180f; }
  .pool-table tr.winner .model { color: var(--accent); }
  .routed { color: var(--accent); font-size: 10px; }
  .eli5 { padding: 18px; }
  .eli5 .num { font-size: 32px; line-height: 1; margin-bottom: 8px; }
  .eli5 p { font-size: 13px; color: var(--fg); }
  .hero-terminal {
    border: 1px solid var(--border-bright);
    background: var(--bg-alt);
    padding: 16px 18px;
    margin: 20px 0;
    height: 200px;
    font-size: 12px;
    line-height: 1.6;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--accent-dim) transparent;
  }
  .hero-terminal::-webkit-scrollbar { width: 4px; }
  .hero-terminal::-webkit-scrollbar-track { background: transparent; }
  .hero-terminal::-webkit-scrollbar-thumb { background: var(--accent-dim); }
  .hero-line { white-space: pre-wrap; }
  .hero-line.prompt { color: var(--accent); }
  .hero-line.dim { color: var(--fg-dim); }
  .hero-line.yellow { color: var(--yellow); }
  .hero-line.accent { color: var(--accent); }
  .hero-line.fg { color: var(--fg); }
  .live-dot { display: inline-block; width: 8px; height: 8px; background: var(--accent); border-radius: 50%; animation: pulse 2s infinite; margin-right: 6px; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
  .feature-day { margin-bottom: 28px; padding-bottom: 16px; border-bottom: 1px solid #1a2a20; }
  .feature-day h2 { color: var(--accent); font-size: 18px; margin: 0 0 12px 0; }
  .feature-entry { margin-bottom: 16px; padding-left: 12px; border-left: 2px solid #1a2a20; }
  .feature-entry h3 { font-size: 13px; margin: 0 0 4px 0; color: var(--fg); }
  .feature-entry p { font-size: 12px; margin: 0; }
  .announce {
    display: flex; align-items: center; gap: 10px;
    background: linear-gradient(135deg, #0a1418, #0a1a14);
    border: 1px solid #1a3a3a; border-left: 3px solid #5ce1ff;
    padding: 10px 14px; margin: 8px 0 16px; font-size: 13px; line-height: 1.5;
    border-radius: 3px;
  }
  .announce .announce-pulse {
    display: inline-block; width: 9px; height: 9px; background: #5ce1ff;
    border-radius: 50%; animation: pulse 2s infinite; flex-shrink: 0;
  }
  .announce .announce-text { flex: 1; color: #b0d0e0; }
  .announce .announce-text a { color: #5ce1ff; }
  .announce .announce-text a:hover { text-decoration: underline; }
  .announce .announce-close {
    background: none; border: none; color: #666; font-size: 18px;
    cursor: pointer; padding: 0 4px; line-height: 1; flex-shrink: 0;
  }
  .announce .announce-close:hover { color: #e0e0e0; }
  .announce.hidden { display: none; }

  /* ── Universal Phosphor Terminal shell ─────────────────────────────── */
  .site-shell { min-height: 100vh; }
  .site-sidebar {
    position: fixed; inset: 0 auto 0 0; width: 240px; z-index: 60;
    /* Slight elevation makes the persistent nav visibly distinct from
       the page canvas — it should never look like it disappeared. */
    background: #060806; border-right: 1px solid var(--border-bright);
    box-shadow: 3px 0 20px rgba(0,0,0,.38);
    display: flex; flex-direction: column; overflow-y: auto;
  }
  .site-brand {
    padding: 20px; border-bottom: 1px solid var(--border); margin-bottom: 16px;
  }
  .site-brand strong {
    display: block; color: var(--accent); font-size: 20px; line-height: 1;
    text-shadow: 0 0 12px rgba(0,255,156,.35), 0 0 4px rgba(0,255,156,.6);
  }
  .site-brand small { display: block; color: #555; font-size: 10px; margin-top: 7px; }
  .site-menu {
    /* Override the global 'nav { display:flex }' rule — the sidebar menu
       must stack links vertically, one below the other. Without this the
       generic nav rule lays them out in a row and they overflow sideways. */
    display: flex; flex-direction: column; flex-wrap: nowrap;
    padding: 0 12px 16px;
  }
  .site-menu-label {
    color: #555; font-size: 9px; text-transform: uppercase; letter-spacing: 1.5px;
    margin: 18px 0 8px; padding-left: 12px;
  }
  .site-menu-label:first-child { margin-top: 4px; }
  .site-menu a {
    display: block; color: var(--fg-dim); border-left: 2px solid transparent;
    padding: 7px 12px; border-radius: 4px; font-size: 13px; text-decoration: none;
    transition: color .15s, background .15s, border-color .15s;
  }
  .site-menu a:hover {
    color: var(--accent); background: rgba(0,255,156,.06);
    border-left-color: var(--accent); text-decoration: none;
  }
  /* Selected page — phosphor glow so the active menu item "lights up". */
  .site-menu a.active {
    color: var(--accent);
    background: linear-gradient(90deg, rgba(0,255,156,.14), rgba(0,255,156,.03));
    border-left-color: var(--accent);
    font-weight: 700;
    box-shadow: inset 0 0 12px rgba(0,255,156,.12), 0 0 10px rgba(0,255,156,.18);
    text-shadow: 0 0 8px rgba(0,255,156,.55);
  }
  .site-menu a.docs-link {
    color: var(--accent); font-weight: 700; border-left-color: var(--accent);
  }
  .site-menu a.docs-link.active {
    background: linear-gradient(90deg, rgba(0,255,156,.16), rgba(0,255,156,.04));
    box-shadow: inset 0 0 14px rgba(0,255,156,.14), 0 0 12px rgba(0,255,156,.22);
    text-shadow: 0 0 8px rgba(0,255,156,.6);
  }
  .site-system {
    margin-top: auto; padding: 13px 20px; border-top: 1px solid var(--border);
    color: #555; font-size: 10px;
  }
  .site-system-dot {
    display: inline-block; width: 7px; height: 7px; margin-right: 7px;
    border-radius: 50%; background: var(--accent); vertical-align: middle;
    animation: pulse 1.5s ease-in-out infinite;
    box-shadow: 0 0 6px rgba(0,255,156,.7);
  }
  .site-main { margin-left: 240px; min-width: 0; }
  .market-ticker {
    height: 32px; display: flex; align-items: center; overflow: hidden;
    background: var(--bg-alt); border-bottom: 1px solid var(--border);
  }
  .market-live {
    height: 100%; display: flex; align-items: center; gap: 7px; flex-shrink: 0;
    padding: 0 12px; color: var(--accent); background: rgba(0,255,156,.08);
    border-right: 1px solid var(--border); font-size: 10px; font-weight: 700;
    letter-spacing: 1px;
  }
  .market-track {
    display: flex; gap: 32px; width: max-content; white-space: nowrap;
    padding-left: 14px; animation: market-scroll 42s linear infinite;
  }
  .market-track span { font-size: 11px; color: #555; }
  .market-track b { color: var(--accent); font-weight: 500; }
  .market-track i { color: var(--border-bright); font-style: normal; }
  @keyframes market-scroll { to { transform: translateX(-50%); } }
  .site-topbar {
    position: sticky; top: 0; z-index: 50; min-height: 52px;
    display: flex; justify-content: space-between; align-items: center; gap: 16px;
    padding: 10px 24px; background: rgba(0,0,0,.92);
    border-bottom: 1px solid var(--border); backdrop-filter: blur(8px);
  }
  .site-breadcrumb { color: #555; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
  .site-actions { display: flex; align-items: center; gap: 8px; }
  .site-actions a {
    display: inline-flex; align-items: center; min-height: 32px; padding: 6px 13px;
    border: 1px solid var(--border-bright); border-radius: 4px;
    color: var(--fg-dim); font-size: 12px; text-decoration: none;
  }
  .site-actions a:hover { color: var(--accent); border-color: var(--accent); text-decoration: none; }
  .site-actions .account-link {
    color: var(--accent); border-color: var(--accent); border-radius: 16px;
    text-shadow: 0 0 8px rgba(0,255,156,.45);
  }
  .site-content { max-width: 1200px; margin: 0 auto; padding: 22px 24px 60px; }
  /* Hide the legacy inline nav — the universal sidebar + mobile drawer
     handle navigation on all screen sizes. The old <nav> lives inside
     .container (a descendant), so use the descendant selector. */
  .site-content nav { display: none; }
  .site-content .announce { margin-top: 0; }
  .site-content h1 { color: var(--accent); text-shadow: 0 0 10px rgba(0,255,156,.22); }
  .site-content .card { border-radius: 6px; transition: border-color .2s, box-shadow .2s; }
  .site-content .card:hover { border-color: var(--border-bright); }

  /* ── Mobile: sidebar becomes an off-canvas drawer ─────────────────── */
  .site-hamburger {
    display: none; width: 36px; height: 36px; align-items: center; justify-content: center;
    background: transparent; border: 1px solid var(--border-bright); border-radius: 4px;
    color: var(--accent); cursor: pointer; padding: 0; font-size: 18px; line-height: 1;
  }
  .site-hamburger:hover { border-color: var(--accent); }
  .site-backdrop {
    display: none; position: fixed; inset: 0; z-index: 59;
    background: rgba(0,0,0,.7); opacity: 0; transition: opacity .2s;
  }
  .site-backdrop.open { display: block; opacity: 1; }

  @media (max-width: 900px) {
    .site-sidebar {
      transform: translateX(-100%); transition: transform .25s ease;
      box-shadow: 4px 0 24px rgba(0,0,0,.5);
    }
    .site-sidebar.open { transform: translateX(0); }
    .site-main { margin-left: 0; }
    .site-hamburger { display: inline-flex; }
    .site-topbar { padding: 9px 12px; }
    .site-breadcrumb { font-size: 10px; }
    .site-content { padding: 16px 12px 40px; }
    .site-actions .hide-mobile { display: none; }
    .market-track { animation-duration: 30s; }
  }
</style>
</head>
<body>
<div class="site-shell">
  <aside class="site-sidebar">
    <div class="site-brand">
      <a href="/" style="text-decoration:none;color:inherit;"><strong>surp</strong></a>
      <small>surplus intelligence router</small>
    </div>
    <nav class="site-menu" aria-label="primary">
      <div class="site-menu-label">▸ discover</div>
      <a href="/">home</a>
      <a href="/docs" class="docs-link">docs ★</a>
      <a href="/about">about</a>

      <div class="site-menu-label">▸ build</div>
      <a href="/connect">connect</a>
      <a href="/builder">builder</a>
      <a href="/playground">playground</a>
      <a href="/compare">compare</a>
      <a href="/find">find model</a>

      <div class="site-menu-label">▸ models &amp; pricing</div>
      <a href="/top">top models</a>
      <a href="/free-models">free models</a>
      <a href="/auction">cache auction</a>

      <div class="site-menu-label">▸ monitor</div>
      <a href="/status">status</a>
      <a href="/health">health board</a>
      <a href="/performance">verified tps</a>
      <a href="/svi">value index</a>
      <a href="/features">updates</a>
    </nav>
    <div class="site-system"><span class="site-system-dot"></span>all systems nominal</div>
  </aside>
  <div class="site-main">
    <div class="market-ticker" aria-hidden="true">
      <div class="market-live"><span class="live-dot"></span>LIVE</div>
      <div class="market-track">
        <span>surp/free <b>$0.00</b> free</span><i>│</i>
        <span>surp/best-chat <b>$0.012</b> ↓</span><i>│</i>
        <span>surp/best-coding <b>$0.034</b> ↑</span><i>│</i>
        <span>usdc/base <b>$1.00</b></span><i>│</i>
        <span>tps <b>847</b> ↑</span><i>│</i>
        <span>ttft <b>120ms</b> ↓</span><i>│</i>
        <span>cache hit <b>34%</b> ↑</span><i>│</i>
        <span>models live <b>1,204</b></span><i>│</i>
        <span>srp pool <b>2.4M</b> ↑</span><i>│</i>
        <span>surp/free <b>$0.00</b> free</span><i>│</i>
        <span>surp/best-chat <b>$0.012</b> ↓</span><i>│</i>
        <span>surp/best-coding <b>$0.034</b> ↑</span><i>│</i>
        <span>usdc/base <b>$1.00</b></span><i>│</i>
        <span>tps <b>847</b> ↑</span><i>│</i>
        <span>ttft <b>120ms</b> ↓</span><i>│</i>
        <span>cache hit <b>34%</b> ↑</span><i>│</i>
        <span>models live <b>1,204</b></span><i>│</i>
        <span>srp pool <b>2.4M</b> ↑</span><i>│</i>
      </div>
    </div>
    <div class="site-topbar">
      <span style="display:flex;align-items:center;gap:10px;">
        <button class="site-hamburger" onclick="toggleSidebar()" aria-label="toggle menu">≡</button>
        <span class="site-breadcrumb">▸ __BREADCRUMB__</span>
      </span>
      <span class="site-actions">
        <a href="/dashboard" class="hide-mobile">usage</a>
        <a href="/app" class="account-link">▶ account</a>
      </span>
    </div>
    <div class="site-backdrop" id="site-backdrop" onclick="closeSidebar()"></div>
    <div class="site-content">
<div class="container">
<nav>
  <a href="/" class="brand" style="text-decoration:none;">surp.ivc.lol</a>
  <ul>
    <li><a href="/">home</a></li>
    <li><a href="/docs">docs</a></li>
    <li><a href="/status">status</a></li>
    <li><a href="/connect">connect</a></li>
    <li><a href="/builder">builder</a></li>
    <li><a href="/free-models" style="color:#5ce1ff;">free</a></li>
    <li><a href="/health">health</a></li>
    <li><a href="/features">updates</a></li>
    <li><a href="/auction" style="color:#5ce1ff;">auction</a></li>
    <li><a href="/performance" style="color:#5ce1ff;">TPS</a></li>
    <li><a href="/app" style="color:#00ff9c;font-weight:bold;">login</a></li>
    <li><a href="/top">models</a></li>
    <li><a href="/find">find</a></li>
    <li><a href="/dashboard">usage</a></li>
    <li><a href="/playground">playground</a></li>
    <li><a href="/about">about</a></li>
    <li><a href="/api/health">api</a></li>
  </ul>
</nav>
<div id="announce-banner" class="announce">
  <span class="announce-pulse" aria-hidden="true"></span>
  <span class="announce-text">
    <b>new:</b> genuinely free AI models are live —
    <a href="/free-models">try surp/free + see live budgets</a> · <a href="/token-gating">token-gating prototype</a> · <a href="/proposal">vote on SRP</a>
  </span>
  <button class="announce-close" onclick="dismissAnnounce()" aria-label="dismiss">×</button>
</div>
__CONTENT__
<footer>
  <div class="footer-links">
    <a href="https://farcaster.xyz/ivc" target="_blank" rel="noopener" aria-label="Farcaster" class="social-link">
      <svg width="18" height="18" viewBox="0 0 1000 1000" fill="currentColor"><path d="M257.778 155.556H742.222V844.445H671.111V528.889H670.414C662.554 441.677 589.258 373.333 500 373.333C410.742 373.333 337.446 441.677 329.586 528.889H328.889V844.445H257.778V155.556Z"/><path d="M128.889 253.333L157.778 351.111H182.222V746.667C169.949 746.667 160 756.616 160 768.889V795.556H155.556C143.283 795.556 133.333 805.505 133.333 817.778V844.445H382.222V817.778C382.222 805.505 372.273 795.556 360 795.556H355.556V768.889C355.556 756.616 345.606 746.667 333.333 746.667H306.667V253.333H128.889Z"/><path d="M675.556 746.667C663.282 746.667 653.333 756.616 653.333 768.889V795.556H648.889C636.616 795.556 626.667 805.505 626.667 817.778V844.445H875.556V817.778C875.556 805.505 865.606 795.556 853.333 795.556H848.889V768.889C848.889 756.616 838.94 746.667 826.667 746.667V351.111H851.111L880 253.333H702.222V746.667H675.556Z"/></svg>
    </a>
    <a href="https://x.com/ivcained" target="_blank" rel="noopener" aria-label="X (Twitter)" class="social-link">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
    </a>
    <a href="https://github.com/ivcained/surp-router" target="_blank" rel="noopener" aria-label="GitHub" class="social-link" title="source on GitHub">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
    </a>
  </div>
  surp.ivc.lol &middot; aggregating the aggregator &middot; built for the community &middot; <a href="https://github.com/ivcained/surp-router">source on GitHub</a> &middot; <a href="https://github.com/x402-foundation/x402">x402 protocol</a> &middot; <a href="https://www.surplusintelligence.ai">surplus intelligence</a>
  <p class="dim" style="margin-top:8px;font-size:10px;">
    x402 LLM gateway · OpenAI-compatible API · pay per request in USDC on Base · cheapest AI models from the Surplus Intelligence marketplace · no account needed · no API key required
  </p>
  <p class="dim" style="margin-top:6px;font-size:10px;">
    <a href="/x402">what is x402</a> · <a href="/x402-llm-api">x402 LLM API</a> · <a href="/x402-gateway">x402 gateway</a> · <a href="/pay-per-request-llm-api">pay-per-request LLM API</a> · <a href="/cheapest-llm-api">cheapest LLM API</a> · <a href="/free-models">free AI models</a> · <a href="/health">health board</a> · <a href="/performance">verified TPS</a> · <a href="/app">login &amp; wallet</a> · <a href="/features">features &amp; updates</a> · <a href="/auction">cache auction</a> · <a href="/cache">cache-aware routing</a> · <a href="/proposal">reward proposal</a> · <a href="/token-gating">token-gating</a>
  </p>
</footer>
</div>
    </div>
  </div>
</div>
<script>
// Announcement banner: dismiss persists in localStorage so a user who
// has seen the update isn't nagged on every page load. Bump the version
// suffix when the announcement content changes so it resurfaces.
(function() {
  var v = "v2-free-models";
  try {
    if (localStorage.getItem("surp-announce-" + v) === "dismissed") {
      var b = document.getElementById("announce-banner");
      if (b) b.classList.add("hidden");
    }
  } catch (e) { /* localStorage may be blocked; banner just stays visible */ }
})();
function dismissAnnounce() {
  var b = document.getElementById("announce-banner");
  if (b) b.classList.add("hidden");
  try { localStorage.setItem("surp-announce-v2-free-models", "dismissed"); } catch (e) {}
}

// Mobile sidebar drawer — open/close with hamburger, click backdrop, or Escape.
function toggleSidebar() {
  var sb = document.querySelector(".site-sidebar");
  var bd = document.getElementById("site-backdrop");
  if (!sb || !bd) return;
  var open = sb.classList.toggle("open");
  bd.classList.toggle("open", open);
}
function closeSidebar() {
  var sb = document.querySelector(".site-sidebar");
  var bd = document.getElementById("site-backdrop");
  if (sb) sb.classList.remove("open");
  if (bd) bd.classList.remove("open");
}
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") closeSidebar();
});
// Close drawer when any menu link is clicked (mobile) AND persist the sidebar
// scroll position so it does not jump back to the top on the next page.
// We store it in sessionStorage keyed per-path so navigating back restores the
// exact scroll place the user was at, without caching stale positions forever.
var SB_SCROLL_KEY = "surp-sidebar-scroll";

// Restore the saved sidebar scroll position. Runs immediately (the script sits
// at the end of <body> so the sidebar DOM exists) with retries so font/layout
// settling that clamps scrollHeight never wins.
(function() {
  var sb = document.querySelector(".site-sidebar");
  if (!sb) return;
  var saved = null;
  try { saved = sessionStorage.getItem(SB_SCROLL_KEY); } catch (e) {}
  if (saved === null) return;
  var target = parseInt(saved, 10) || 0;
  var restore = function() {
    if (!sb.isConnected) return;
    var max = sb.scrollHeight - sb.clientHeight;
    // Clamp both bounds: target may be stale/negative if the menu shrank.
    sb.scrollTop = Math.min(Math.max(0, target), max);
  };
  restore();
  window.setTimeout(restore, 100);
  window.setTimeout(restore, 400);
  if (document.readyState !== "complete") {
    window.addEventListener("load", function() {
      window.setTimeout(restore, 100);
    });
  }
})();

document.addEventListener("DOMContentLoaded", function() {
  var sb = document.querySelector(".site-sidebar");
  var links = document.querySelectorAll(".site-menu a");
  links.forEach(function(a) { a.addEventListener("click", function() {
    closeSidebar();
    if (sb) {
      try { sessionStorage.setItem(SB_SCROLL_KEY, String(sb.scrollTop)); } catch (e) {}
    }
  }); });

  // Mark the current page's menu link as active so it lights up with a glow.
  var current = document.body.getAttribute("data-active-path")
                 || window.location.pathname;
  if (current === "" ) current = "/";
  links.forEach(function(a) {
    var href = a.getAttribute("href") || "/";
    if (href === current) {
      a.classList.add("active");
    }
  });
});
</script>
</body>
</html>
"""

_HOME_CONTENT = r"""
<h1>The cheapest LLM API on the internet.</h1>
<p class="dim prompt">cat surp.ivc.lol | grep -i "what is this"</p>
<p>surp.ivc.lol is an <b>x402 LLM gateway</b> — an <b>OpenAI-compatible API</b> that pays per request in <b>USDC on Base</b>. No account, no API key, no subscription. You pay per request in <b>USDC on Base</b> — no account, no API key, no subscription. Behind the scenes we aggregate <b>Surplus Intelligence</b> (itself a marketplace of competing sellers) and route every request to whichever model is <b>cheapest right now</b> for the class of work you asked for.</p>
<p class="dim">You ask for <code>surp/best-coding</code>. We fetch live Surplus market prices, find the cheapest coding-class model at this instant, forward your request there, and stream the answer back. The price you pay is the Surplus spot price + a small markup, settled on-chain in micropennies.</p>



<div id="hero-terminal" class="hero-terminal"></div>
<script>
(function() {
  var lines = [
    {t: "$ curl -X POST surp.ivc.lol/v1/chat/completions", c: "prompt", d: 40},
    {t: '  -d \'{"model":"surp/best-coding","messages":[{"role":"user","content":"write a fizzbuzz"}]}\'', c: "dim", d: 15},
    {t: "", d: 300},
    {t: "< HTTP 402 Payment Required", c: "yellow", d: 400},
    {t: "  amount: 10000 atomic USDC ($0.01)", c: "dim", d: 100},
    {t: "  payTo: 0x2f95...c2c8", c: "dim", d: 100},
    {t: "  signing EIP-3009 authorization...", c: "accent", d: 600},
    {t: "[OK] payment settled on Base", c: "accent", d: 400},
    {t: "-> routing surp/best-coding -> cheapest model...", c: "dim", d: 400},
    {t: "<- routed to: qwen3-coder-turbo ($0.46/1M)", c: "accent", d: 300},
    {t: "", d: 200},
    {t: "def fizzbuzz(n):", c: "fg", d: 80},
    {t: "    for i in range(1, n+1):", c: "fg", d: 60},
    {t: '        if i % 15 == 0: print("FizzBuzz")', c: "fg", d: 60},
    {t: '        elif i % 3 == 0: print("Fizz")', c: "fg", d: 60},
    {t: '        elif i % 5 == 0: print("Buzz")', c: "fg", d: 60},
    {t: "        else: print(i)", c: "fg", d: 200},
    {t: "", d: 500},
    {t: "[OK] 1c spent. model served: qwen3-coder-turbo. 95% cheaper than retail.", c: "accent", d: 0},
  ];
  var el = document.getElementById("hero-terminal");
  if (!el) return;
  var li = 0;
  function next() {
    if (li >= lines.length) {
      setTimeout(function() { el.innerHTML = ""; li = 0; next(); }, 5000);
      return;
    }
    var ln = lines[li++];
    var span = document.createElement("div");
    span.className = "hero-line " + (ln.c || "");
    if (ln.t && ln.d > 50 && ln.c !== "fg") {
      span.textContent = "";
      el.appendChild(span);
      var ci = 0;
      var txt = ln.t;
      var typer = setInterval(function() {
        if (ci >= txt.length) { clearInterval(typer); el.scrollTop = el.scrollHeight; setTimeout(next, ln.d || 200); return; }
        span.textContent += txt[ci++];
        el.scrollTop = el.scrollHeight;
      }, 20);
    } else {
      span.textContent = ln.t;
      el.appendChild(span);
      el.scrollTop = el.scrollHeight;
      setTimeout(next, ln.d || 200);
    }
  }
  next();
})();
</script>

<h2>explain it like i'm 5</h2>
<div class="grid">
  <div class="card eli5">
    <div class="num">🧠</div>
    <p><b>You want an AI to write code or answer questions.</b> There are dozens of AI models that can do it. Some cost $20 per million words. Some cost $0.03. They're all pretty good.</p>
  </div>
  <div class="card eli5">
    <div class="num">🛒</div>
    <p><b>surp.ivc.lol is a smart shopper.</b> Every time you ask a question, it checks a live marketplace where AI sellers compete on price, picks whichever one is cheapest right now for the type of work you need, and sends your question there.</p>
  </div>
  <div class="card eli5">
    <div class="num">💰</div>
    <p><b>You pay pennies per question.</b> Not a monthly subscription. Not a credit pack. Each question costs about 1&cent;, paid from your crypto wallet. No account, no signup, no credit card.</p>
  </div>
</div>
<p class="dim">That's it. You say "give me the best coding AI" and we hand you the cheapest one available at that exact second. The market moves &mdash; we follow it.</p>

<div class="ascii">
  client ──▶ surp.ivc.lol (x402 gateway) ──▶ Surplus Intelligence (seller market) ──▶ {cheapest model}
   ▲                ▲                          ▲
   │                │                          │
   │            verifies +               live price book
   │            settles USDC             (145+ models,
   │            on Base                  76 active listings)
   └─── response streams back ◀── response ◀──────
</div>

<h2>live ticker — what each combo routes to right now</h2>
<p class="dim"><span class="live-dot" role="presentation" aria-hidden="true"></span>Live &mdash; refreshed every 30s from <code>GET api.surplusintelligence.ai/api/markets</code>. Current snapshot: <b>__MC__</b> listings, of which <b>__TC__</b> are text/chat LLMs.</p>
<div class="combo-list">
__ROWS__
</div>
<p class="dim">Savings are vs a blended claude-sonnet-4.6 list price (~$9/1M). <b>Click any combo to expand it</b> and see every model in its pool, cheapest first &mdash; the top row is what your request routes to right now.</p>

<h2>how it works — 3 steps</h2>
<div class="grid">
  <div class="card"><div class="num">1</div><div class="lbl">you request</div><p>POST /v1/chat/completions with <code>model: "surp/best-chat"</code>. no auth header.</p></div>
  <div class="card"><div class="num">2</div><div class="lbl">we 402</div><p>we resolve the combo to the live cheapest model, compute the exact micropayment, and return HTTP 402 with payment requirements.</p></div>
  <div class="card"><div class="num">3</div><div class="lbl">you pay & go</div><p>your wallet signs an EIP-3009 USDC authorization. we verify + settle on Base. the completion streams back.</p></div>
</div>

<h2>why this is different</h2>
<p>Most "cheap LLM" services are <b>static</b>: they pick one model, hide it behind a flat price, and pocket the spread. surp.ivc.lol is <b>dynamic</b>: the model you get is whatever is cheapest on Surplus <i>at the second you asked</i>, and the price you pay is that spot price + a transparent markup. We're not a provider — we're a <b>price arbitrageur</b> sitting on top of a marketplace that itself sits on top of every other AI model provider. An <b>AI model marketplace router</b>. Aggregating the aggregator.</p>

<div class="warn">live: payments settle in <b>real USDC on Base mainnet</b> (eip155:8453) via the x402 protocol. each request is a single on-chain EIP-3009 transfer &mdash; no account, no API key, no subscription. your wallet pays, your model answers.</div>



<h2>quick start &mdash; try it right now</h2>
<p>Send this from any terminal. You'll get back a payment challenge &mdash; that's the x402 protocol asking for 1&cent; of USDC:</p>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"surp/best-chat",
       "messages":[{"role":"user","content":"what is 2+2?"}],
       "max_tokens":50}'</pre>
<p class="dim">The response tells you exactly how to pay: the amount, the USDC contract address, and where to send it. Use any x402-compatible wallet or client library to sign and retry. <a href="/connect">Hermes users &mdash; follow the 3-step connect guide &raquo;</a></p>

<a class="cta" href="/free-models" style="border-color: var(--accent); color: var(--accent);">try free — no wallet needed</a>
<a class="cta" href="/performance" style="border-color: var(--green); color: var(--green);">100 TPS @ $0.065/M — see verified benchmarks</a>
<a class="cta" href="/connect" style="border-color: var(--yellow); color: var(--yellow);">connect your hermes</a>
<a class="cta" href="/builder">build your own combo</a>

<h2>learn</h2>
<p>New to the stack? Start here:</p>
<div class="grid">
  <div class="card"><div class="num">1</div><div class="lbl">the protocol</div><p><a href="/x402">What is x402?</a> — the HTTP 402 payment protocol, explained simply.</p></div>
  <div class="card"><div class="num">2</div><div class="lbl">the api</div><p><a href="/x402-llm-api">x402 LLM API</a> — pay-per-request AI inference, OpenAI-compatible.</p></div>
  <div class="card"><div class="num">3</div><div class="lbl">the prices</div><p><a href="/cheapest-llm-api">Cheapest LLM API</a> — live pricing ranked, updated every minute.</p></div>
</div>
<a class="cta" href="/playground" style="border-color: var(--fg-dim); color: var(--fg-dim);">try the playground</a>
<p class="dim" style="margin-top:16px;font-size:12px;">
  compare <a href="/compare">ai models</a> · browse <a href="/models">150+ models</a> · <a href="/top">top 5 leaderboards</a> · <a href="/find">find the right model</a> · <a href="/builder">build a combo</a>
</p>
<a class="cta" href="/docs" style="border-color: var(--fg-dim); color: var(--fg-dim);">read the docs</a>
"""

_DOCS_CONTENT = r"""
<h1>docs</h1>
<p class="dim prompt">man surp.ivc.lol</p>

<h2>what is surp.ivc.lol?</h2>
<p>A per-request, x402-paywalled HTTP API for LLM inference. You send a chat completion request with a <b>combo</b> as the model name; we resolve that combo to the single cheapest concrete model currently listed on <a href="https://www.surplusintelligence.ai">Surplus Intelligence</a>, charge you that spot price plus a small markup, and forward the request. Settlement is on-chain USDC on Base via the <a href="https://docs.x402.org">x402 protocol</a>.</p>

<h2>the 15 combos</h2>
<p>Combos come in two tiers × five classes, plus three bare aliases and a free tier:</p>
<table>
<thead><tr><th>combo</th><th>tier</th><th>class</th><th>meaning</th></tr></thead>
<tbody>
  <tr><td>surp/best-coding</td><td>best</td><td>coding</td><td>cheapest model with "coder"/"codex"/"qwen3-coder" in the name</td></tr>
  <tr><td>surp/best-reasoning</td><td>best</td><td>reasoning</td><td>cheapest "thinking"/"r1"/"reasoning" model</td></tr>
  <tr><td>surp/best-fast</td><td>best</td><td>fast</td><td>cheapest small/mini/nano/lite model</td></tr>
  <tr><td>surp/best-vision</td><td>best</td><td>vision</td><td>cheapest multimodal vision model (-vl / vision / 5v)</td></tr>
  <tr><td>surp/best-chat</td><td>best</td><td>chat</td><td>cheapest text LLM not in a specialized class</td></tr>
  <tr><td>surp/best-coding-fast</td><td>best</td><td>coding∩fast</td><td>cheapest coding model (fast-coding cross, falls back to coding pool)</td></tr>
  <tr><td>surp/pro-coding</td><td>pro</td><td>coding</td><td>cheapest <i>frontier-tier</i> coding model (qwen3-coder-turbo, gpt-5.x-codex)</td></tr>
  <tr><td>surp/pro-reasoning</td><td>pro</td><td>reasoning</td><td>cheapest frontier reasoning model (deepseek-r1, qwen3-thinking)</td></tr>
  <tr><td>surp/pro-vision</td><td>pro</td><td>vision</td><td>cheapest frontier vision model (qwen3-vl-235b, etc.)</td></tr>
  <tr><td>surp/pro-chat</td><td>pro</td><td>chat</td><td>cheapest frontier chat model (gpt-5.6, claude-opus, gemini-pro)</td></tr>
  <tr><td>surp/pro-fast</td><td>pro</td><td>fast</td><td>cheapest frontier fast model (gemini-2.5-pro, etc.)</td></tr>
  <tr><td>surp/coding</td><td>—</td><td>—</td><td>alias for surp/best-coding</td></tr>
  <tr><td>surp/fast</td><td>—</td><td>—</td><td>alias for surp/best-fast</td></tr>
  <tr><td>surp/chat</td><td>—</td><td>—</td><td>alias for surp/best-chat</td></tr>
  <tr><td>surp/free</td><td>free</td><td>chat</td><td>treasury-sponsored free inference with live fallback, rate limits, and daily budgets</td></tr>
  <tr><td>surp/srup-free</td><td>free</td><td>alias</td><td>legacy alias of surp/free</td></tr>
</tbody>
</table>

<h2>build your own combo</h2>
<p>The 15 built-ins are opinionated. If you'd rather decide the candidate set yourself, use the <a href="/builder">builder</a>: pick any number of models (2&ndash;20) from the 152 text LLMs on Surplus, and we save that set as a combo with its own model id.</p>
<p>On every request we compare <b>only your chosen models</b> at their live prices and route to the cheapest one. You are never routed outside your set.</p>
<h3>why this saves money</h3>
<p>Frontier models are near-substitutes for most work, but their prices differ by more than an order of magnitude and move independently. Pick five you'd be happy with and you pay the price of whichever is cheapest at that second:</p>
<pre>$ 1.3930/1M  gpt-5.6-luna-pro   &lt;-- routed
$ 2.7621/1M  grok-4.3
$ 7.1928/1M  claude-sonnet-5
$10.4895/1M  kimi-k3
$17.9000/1M  claude-opus-5
              -&gt; 92% cheaper than the priciest pick in the same set</pre>
<h3>creating one from the API</h3>
<pre>curl -X POST https://surp.ivc.lol/api/combos/custom \
  -H "Content-Type: application/json" \
  -d '{"name":"my frontier five",
       "models":["claude-opus-5","gpt-5.6-sol","claude-opus-4.8","grok-4.5","gemini-3.1-pro"]}'</pre>
<p>Returns a <code>model_id</code> like <code>surp/my/d1e8eff1</code>. Use it exactly like a built-in combo:</p>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"surp/my/d1e8eff1","messages":[{"role":"user","content":"hi"}]}'</pre>
<p class="dim">Slugs are a content hash of the sorted model set, so the same picks always produce the same id &mdash; combos are shareable and de-duplicated. Inspect any combo (including its live pool ordering) at <code>GET /api/combos/custom/&lt;slug&gt;</code>, or browse what others built at <code>GET /api/combos/custom</code>.</p>

<h2>the request flow</h2>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"surp/best-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":100}'</pre>
<p>The first time, you get back HTTP <b>402 Payment Required</b> with an <code>PAYMENT-REQUIRED</code> header. That header is a base64-encoded JSON blob describing exactly what USDC authorization to sign: the pay-to address, the amount in atomic USDC units (6 decimals), the asset contract (USDC on Base), the network, and the max settlement window.</p>

<h3>the 402 response body</h3>
<pre>{
  "x402Version": 2,
  "error": "payment-required",
  "combo": "surp/best-chat",
  "routed_model": "glm-5.2",
  "surplus_price_per_1m": 30000,
  "expected_tokens": 100,
  "price_usd": "$0.01",
  "accepts": [{
    "scheme": "exact",
    "network": "eip155:8453",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "amount": "10000",
    "payTo": "0x...",
    "maxTimeoutSeconds": 600
  }]
}</pre>

<h3>paying and retrying</h3>
<p>Use any x402 client library to sign the EIP-3009 authorization and retry with the <code>X-Payment</code> header:</p>
<pre># Python (x402 client library)
from x402.http import x402HTTPClientSync
client = x402HTTPClientSync()
resp = client.post(
    "https://surp.ivc.lol/v1/chat/completions",
    json={"model":"surp/best-chat","messages":[{"role":"user","content":"hi"}]},
)
print(resp.json())  # the actual chat completion</pre>
<p>The client lib handles the 402 → sign → retry loop automatically. See <a href="https://docs.x402.org">docs.x402.org</a> for JS, Python, and TypeScript clients.</p>

<h2>pricing — how we compute the charge</h2>
<p>For a given request with <code>max_tokens = N</code>:</p>
<pre>price_usd = (surplus_best_price_per_1m / 1e6) * (N / 1_000_000) * (1 + markup_bps/10000)
price_usd = max(price_usd, floor_cents/100)
amount_atomic_usdc = ceil(price_usd * 100) * 10_000   # 6-decimal USDC</pre>
<p>Currently <code>markup_bps = 500</code> (5%), <code>floor_cents = 1</code> (one penny minimum). Surplus's <code>best_price_per_1m</code> is denominated so that <code>1e6 = $1.00 per 1M tokens</code> (calibrated against known retail prices). The markup covers our gateway/facilitator operating cost and a tiny margin; everything else passes through to the underlying Surplus seller at spot.</p>

<h2>API reference</h2>
<h3><code>GET /api/combos</code> — free</h3>
<p>Returns the live resolution for all 15 combos — the model each one currently routes to, its Surplus spot price, and the pool size. Useful for building dashboards.</p>
<h3><code>GET /api/models</code> — free</h3>
<p>The full catalog of Surplus text LLMs with live prices, class labels, and frontier-tier flags. This is what the builder reads.</p>
<h3><code>POST /api/combos/custom</code> — free</h3>
<p>Create a custom combo. Body: <code>{"name": str, "models": [str, ...]}</code> (2&ndash;20 models). Idempotent on the model set. Unknown or non-text model ids are rejected with a 400.</p>
<h3><code>GET /api/combos/custom</code> / <code>GET /api/combos/custom/&lt;slug&gt;</code> — free</h3>
<p>List community combos (most-used first), or inspect one including its live cheapest-first pool.</p>
<h3><code>GET /api/health</code> — free</h3>
<p>Gateway status: resolver URL, facilitator URL, network, pay-to address, markup, market cache size.</p>
<h3><code>POST /v1/chat/completions</code> — x402</h3>
<p>OpenAI-compatible. <code>model</code> must be <code>surp/&lt;combo&gt;</code>. Streaming (<code>"stream": true</code>) supported — we pipe SSE chunks straight through from the underlying seller.</p>
<h3><code>GET /v1/models</code> — free</h3>
<p>Returns the 15 combos as OpenAI-format model IDs.</p>

<h2>transparency</h2>
<p>Every paid response carries these headers so you can verify the routing on-chain:</p>
<ul>
  <li><code>X-Payment-Settled: true</code> — facilitator confirmed the USDC transfer</li>
  <li><code>X-Routed-Model: &lt;model_id&gt;</code> — which Surplus model actually served the request</li>
  <li><code>X-Surplus-Price-Per-1M: &lt;atomic&gt;</code> — the spot price we paid</li>
</ul>
<p>The difference between what you paid and <code>X-Surplus-Price-Per-1M × tokens / 1e6</code> is our markup. That's the entire business model, and it's fully auditable per-request.</p>
"""

_ABOUT_CONTENT = r"""
<h1>about</h1>
<p class="dim prompt">whoami && why</p>

<h2>we are aggregating the aggregator.</h2>
<p>Surplus Intelligence is a decentralized exchange for LLM inference — sellers list their OpenAI-compatible endpoints, buyers get routed to the cheapest seller at request time, settlement is on-chain USDC on Base. It's a marketplace sitting on top of every provider.</p>
<p>surp.ivc.lol sits one layer above: we don't host models, we don't run a seller, we don't even hold your money. We watch Surplus's live order book, classify every model into a small set of useful combos (best-coding, pro-reasoning, etc.), and route your request to whichever model is cheapest for the combo you asked for — for a transparent 5% markup on the spot price.</p>

<div class="grid">
  <div class="card"><div class="num">145+</div><div class="lbl">surplus models watched</div></div>
  <div class="card"><div class="num">15</div><div class="lbl">combos exposed</div></div>
  <div class="card"><div class="num">0</div><div class="lbl">accounts required</div></div>
  <div class="card"><div class="num">~$0.01</div><div class="lbl">floor per request</div></div>
</div>

<h2>why we built this</h2>
<p>The LLM API market is broken in a familiar way: providers charge what they think they can get away with, prices are opaque, and switching cost is high. Surplus Intelligence already solved the <i>supply</i> side — a real market where sellers compete on price. But on the <i>demand</i> side, you still have to know which of 145 models to call. That's not a product; that's homework.</p>
<p>Combos turn the homework into a one-word choice. <code>surp/best-coding</code> is "give me the cheapest model that's actually good at coding, whatever that is right now". The user doesn't need to track model releases, benchmark changes, or price moves — the gateway does that continuously, 24/7.</p>

<h2>why x402</h2>
<p>x402 — HTTP 402, the "payment required" status code that browsers ignored for 30 years — lets us charge <b>per request</b> with no account, no API key, no subscription, no KYC. You hold USDC in a wallet; you sign one EIP-3009 authorization per request; we settle on Base; the response streams back. That's the entire onboarding flow. It's the native payment rail for autonomous agents, and it's what makes a micropayment-priced service viable at all — no Stripe fees eating the margin, no minimum-topup, no metering infrastructure to maintain.</p>

<h2>this replaces questbase</h2>
<p>This project supersedes <code>qb.ivc.lol</code> (QuestBase). QuestBase was an AI scavenger-hunt protocol for crypto conferences — a fun idea, but a niche product. surp.ivc.lol is a tool we actually use ourselves, every day: the same Hermes agent that powers our infrastructure can point at <code>surp/best-coding</code> and get the cheapest coding LLM on the internet without thinking about it. If it's useful to us, it's probably useful to the broader community of agents, tinkerers, and builders who want cheap inference without the overhead.</p>

<h2>what's next</h2>
<ul style="margin-left: 20px; line-height: 1.8;">
  <li>expand to more facilitators and settlement schemes (upto, batch-settlement)</li>
  <li>add a public stats dashboard: total volume routed, savings vs retail, top combos by usage</li>
  <li>add a "savings vs OpenAI/Anthropic retail" calculator that takes your monthly token spend and shows the surp equivalent</li>
  <li>expose combo <i>history</i> — what best-coding routed to over the last week, so users can see the market move</li>
  <li>add agent SDK examples (every popular x402 client lib, with a surp base URL)</li>
  <li>self-host the facilitator so we control settlement end-to-end (today we use the x402.org shared facilitator)</li>
</ul>

<h2>open source / community</h2>
<p>The gateway code is small and readable. The routing logic — the combo resolver and the class taxonomy — is the valuable part, and it's all in one file. We'd rather the community fork it, improve the class definitions, add combos, and submit PRs than have us be the single source of truth. If you think <code>best-coding</code> should include a model we missed, or that we need a <code>best-agents</code> combo, open an issue.</p>
<p class="dim">this is a community project. we make it work for us first, and share it because the marginal cost of letting you use it is approximately zero.</p>
"""

_PLAYGROUND_CONTENT = r"""
<h1>playground</h1>
<p class="dim prompt">surp/best-chat --interactive</p>
<p>Pick a combo, send a message. The first request will return 402 with payment requirements — you'll sign with your wallet, and the completion will stream back. (Real USDC on Base mainnet — sign with your wallet.)</p>

<div class="field">
  <label for="combo">combo</label>
  <select id="combo">__COMBOS__</select>
</div>
<div class="field">
  <label for="prompt">prompt</label>
  <textarea id="prompt" rows="3">Say only the word PONG, nothing else.</textarea>
</div>
<div class="field">
  <label for="maxtok">max_tokens</label>
  <input id="maxtok" type="number" value="50" min="1" max="4000">
</div>
<button id="send">▶ send request</button>
<div id="status" style="margin-top: 14px; font-size: 12px; color: var(--fg-dim);"></div>
<pre id="out" style="margin-top: 14px; min-height: 60px; display: none;"></pre>

<h2>live resolutions</h2>
<table>
<thead><tr><th>combo</th><th>routes to</th><th>USD / 1M tok</th><th>vs $9/1M list</th><th>pool</th></tr></thead>
<tbody>__ROWS__</tbody>
</table>

<script>
const $ = (id) => document.getElementById(id);
$("send").onclick = async () => {
  const combo = $("combo").value;
  const prompt = $("prompt").value;
  const maxtok = parseInt($("maxtok").value, 10) || 50;
  $("status").textContent = "sending (expecting 402)...";
  $("out").style.display = "none";
  const body = JSON.stringify({model: combo, messages: [{role: "user", content: prompt}], max_tokens: maxtok, stream: false});
  try {
    const r = await fetch("/v1/chat/completions", {method: "POST", headers: {"Content-Type": "application/json"}, body});
    if (r.status === 402) {
      const j = await r.json();
      $("status").innerHTML = `payment required: <b>${j.price_usd}</b> for ${j.combo} → ${j.routed_model} (${j.surplus_price_per_1m} atomic/1M). use an x402 client lib to sign & retry — the browser can't sign EIP-3009 yet.`;
      $("out").style.display = "block";
      $("out").textContent = JSON.stringify(j, null, 2);
      return;
    }
    if (!r.ok) {
      $("status").textContent = "error " + r.status;
      $("out").style.display = "block";
      $("out").textContent = await r.text();
      return;
    }
    const j = await r.json();
    $("status").innerHTML = `ok — routed to <b>${r.headers.get("X-Routed-Model") || "?"}</b> · settled on Base`;
    $("out").style.display = "block";
    $("out").textContent = JSON.stringify(j, null, 2);
  } catch (e) {
    $("status").textContent = "network error: " + e.message;
  }
};
</script>
"""


_DASHBOARD_CONTENT = r"""
<h1>usage dashboard</h1>
<p class="dim prompt">surp --my-usage</p>
<p>Enter your wallet address to see every request you've made &mdash; which combos you called, which models served you, what you paid, and when.</p>
<div class="field">
  <label for="addr">your base wallet address</label>
  <input id="addr" placeholder="0x..." style="font-family:var(--mono);">
</div>
<button id="lookup">▶ look up usage</button>
<div id="result" style="margin-top:16px;"></div>

<h2>or create a prepaid API key</h2>
<p class="dim">No wallet? No problem. Prepay with a balance and use a standard API key instead of x402.</p>
<div class="field">
  <label for="keylabel">label (for your reference)</label>
  <input id="keylabel" placeholder="my project key" value="my project key">
</div>
<button id="createkey" style="border:1px solid var(--border-bright);background:transparent;color:var(--fg);">create key (0 balance)</button>
<div id="keyresult" style="margin-top:12px;"></div>

<script>
const $ = (id) => document.getElementById(id);
$("lookup").onclick = async () => {
  const addr = $("addr").value.trim();
  if (!addr.startsWith("0x") || addr.length !== 42) {
    $("result").innerHTML = "<p class=\"err\">enter a valid 0x address (42 chars)</p>"; return;
  }
  $("result").innerHTML = "<p class=\"dim\">loading...</p>";
  try {
    const r = await fetch("/api/dashboard?address=" + addr);
    const d = await r.json();
    if (d.error) { $("result").innerHTML = "<p class=\"err\">" + d.error + "</p>"; return; }
    if (!d.total_requests) {
      $("result").innerHTML = "<p class=\"dim\">no requests found for this address yet.</p>"; return;
    }
    let rows = d.recent.map(r =>
      "<tr><td class=\"dim\">" + new Date(r.ts*1000).toISOString().slice(0,19).replace("T"," ") +
      "</td><td class=\"combo\">" + r.combo + "</td><td class=\"model\">" + (r.model||"?") +
      "</td><td class=\"price\">" + (r.cents ? "$" + (r.cents/100).toFixed(2) : "-") +
      "</td><td class=\"pool\">" + (r.tx ? "<a href=\"https://basescan.org/tx/" + r.tx + "\" target=\"_blank\">tx</a>" : r.method) + "</td></tr>"
    ).join("");
    $("result").innerHTML = `
      <div class="grid">
        <div class="card"><div class="num">${d.total_requests}</div><div class="lbl">total requests</div></div>
        <div class="card"><div class="num">$${(d.total_spent_usd_cents/100).toFixed(2)}</div><div class="lbl">total spent</div></div>
      </div>
      <table><thead><tr><th>time</th><th>combo</th><th>model</th><th>cost</th><th>tx</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  } catch(e) { $("result").innerHTML = "<p class=\"err\">" + e.message + "</p>"; }
};
$("createkey").onclick = async () => {
  $("keyresult").innerHTML = "<p class=\"dim\">creating...</p>";
  try {
    const r = await fetch("/api/keys/create", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({label: $("keylabel").value, balance_cents: 0})
    });
    const d = await r.json();
    if (d.error) { $("keyresult").innerHTML = "<p class=\"err\">" + d.error + "</p>"; return; }
    $("keyresult").innerHTML = `
      <div class="okbox">
        <p><b>API key created</b> (balance: $0.00 &mdash; top up to use it)</p>
        <p>key: <code>${d.key}</code></p>
        <pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \
  -H "Authorization: Bearer ${d.key}" \
  -H "Content-Type: application/json" \
  -d '{"model":"surp/best-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'</pre>
        <p class="dim">check balance: <code>GET /api/keys/balance?key=${d.key}</code></p>
      </div>`;
  } catch(e) { $("keyresult").innerHTML = "<p class=\"err\">" + e.message + "</p>"; }
};
</script>
"""

_CONNECT_CONTENT = r"""
<h1>connect your hermes</h1>
<p class="dim prompt">surp.ivc.lol --connect-hermes</p>
<p>If you run <a href="https://hermes-agent.nousresearch.com">Hermes Agent</a>, you can point it at surp.ivc.lol in under a minute. Your agent gets the cheapest LLM on the internet per request, paying in USDC on Base &mdash; no API key, no account, no monthly bill.</p>

<div class="warn">You need <b>USDC on Base</b> in a wallet whose private key you control (not an exchange deposit address). A few cents covers hundreds of requests. Get test USDC first if you just want to try &mdash; the routing is identical.</p>

<h2>step 1 &mdash; install the x402 client</h2>
<p>Your Hermes runs on Python. The x402 library handles the sign-and-pay loop automatically.</p>
<pre>pip install "x402[evm]"</pre>
<p class="dim">This pulls in <code>eth-account</code> and <code>web3</code> for EIP-3009 signature signing. If your Hermes uses a virtualenv (it should), activate it first.</p>

<h2>step 2 &mdash; set your wallet key</h2>
<p>Export your wallet's private key as an environment variable. Hermes reads this on every request.</p>
<pre>export SURP_WALLET_KEY="0xabc123...your private key"</pre>
<div class="warn">Never commit this key or paste it in chat. Use a dedicated wallet with only the USDC you're willing to spend &mdash; a few dollars at a time.</p>

<h2>step 3 &mdash; add surp.ivc.lol as a custom provider</h2>
<p>Open <code>~/.hermes/config.yaml</code> and add this entry under <code>custom_providers:</code></p>
<pre>custom_providers:
  - name: surp-gateway
    base_url: https://surp.ivc.lol/v1
    model: surp/best-coding
    key_env: SURP_WALLET_KEY
    discover_models: false
    models:
      - surp/best-coding
      - surp/best-reasoning
      - surp/best-chat
      - surp/best-fast
      - surp/best-vision
      - surp/pro-coding
      - surp/pro-reasoning
      - surp/pro-chat
      - surp/best-coding-fast
      - surp/coding
      - surp/chat
      - surp/fast
      - surp/srup-free</pre>
<p class="dim">The <code>key_env</code> field tells Hermes to send your wallet key as the authorization. The gateway uses it to sign x402 payments on your behalf. <code>discover_models: false</code> makes the /model picker show exactly these combos instead of probing the endpoint.</p>

<h2>step 4 &mdash; switch your model</h2>
<p>Run <code>/model</code> in Hermes, pick <b>surp-gateway</b>, then pick a combo. Or set it directly:</p>
<pre>hermes config set model.default surp/best-coding
hermes config set model.provider surp-gateway</pre>

<h2>step 5 &mdash; test it</h2>
<p>Send any message. The first request triggers the x402 flow &mdash; Hermes signs a USDC authorization, the gateway verifies it on-chain via the facilitator, and the completion streams back. Check the response headers:</p>
<pre>curl -s -D - https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"surp/best-chat","messages":[{"role":"user","content":"say PONG"}],"max_tokens":10}' \\
  | head -5

# HTTP/2 402  <- payment required (expected on first hit)
# pay-to: 0xYOUR_WALLET_ADDRESS
# amount: 10000 atomic USDC ($0.01)</pre>
<p>With the x402 client installed, Hermes handles the 402 &rarr; sign &rarr; retry loop automatically. You'll see the settlement in your wallet within seconds.</p>

<h2>which combo should I pick?</h2>
<table>
<thead><tr><th>combo</th><th>use when</th><th>typical cost</th></tr></thead>
<tbody>
  <tr><td><code>surp/best-coding</code></td><td>everyday coding, PRs, debugging</td><td>~$0.005/1K tokens</td></tr>
  <tr><td><code>surp/pro-coding</code></td><td>hard architecture, complex refactors</td><td>~$0.01/1K tokens</td></tr>
  <tr><td><code>surp/best-chat</code></td><td>general questions, writing, analysis</td><td>~$0.0003/1K tokens</td></tr>
  <tr><td><code>surp/best-reasoning</code></td><td>math, logic, step-by-step problems</td><td>~$0.0005/1K tokens</td></tr>
  <tr><td><code>surp/best-fast</code></td><td>quick replies, simple lookups</td><td>~$0.0005/1K tokens</td></tr>
</tbody>
</table>
<p class="dim">Costs are live &mdash; they move with the Surplus market. Check <a href="/">the homepage ticker</a> for current rates.</p>

<h2>troubleshooting</h2>
<h3>"verification failed: insufficient_balance"</h3>
<p>Your wallet doesn't have enough USDC on Base. Fund it &mdash; even $1 covers thousands of requests at current prices.</p>
<h3>"verification failed: invalid signature"</h3>
<p>The private key in <code>SURP_WALLET_KEY</code> doesn't match the wallet the facilitator expects. Make sure you exported the key for the address that holds your USDC.</p>
<h3>the /model picker doesn't show surp-gateway</h3>
<p>Make sure the <code>custom_providers</code> entry is properly indented in YAML (2 spaces under the key). Run <code>hermes doctor</code> to validate.</p>
<h3>I want to build my own combo from specific models</h3>
<p>Use the <a href="/builder">combo builder</a> &mdash; pick any models, get a <code>surp/my/&lt;slug&gt;</code> id, add it to the <code>models:</code> list in step 3.</p>

<h2>how the payment works (under the hood)</h2>
<p>You don't need to understand this to use it, but if you're curious:</p>
<ol style="margin-left: 20px; line-height: 1.8;">
  <li>Hermes sends <code>POST /v1/chat/completions</code> with no payment header</li>
  <li>Gateway responds <code>402 Payment Required</code> with a <code>PAYMENT-REQUIRED</code> header describing the exact USDC amount, pay-to address, and token contract</li>
  <li>The x402 client library (running inside Hermes) signs an <b>EIP-3009 <code>transferWithAuthorization</code></b> message &mdash; an off-chain signature authorizing a single USDC transfer</li>
  <li>Hermes retries the request with a <code>PAYMENT-SIGNATURE</code> header containing the signed authorization</li>
  <li>The gateway forwards the signature to the <b>PayAI facilitator</b>, which verifies it and submits the on-chain transaction (gas is sponsored &mdash; you only pay USDC, no ETH needed)</li>
  <li>Once settled, the gateway resolves your combo to the cheapest live model and forwards the request to Surplus Intelligence</li>
</ol>
<p class="dim">The entire payment is a single EIP-3009 transfer &mdash; no approval transaction, no gas, no smart contract interaction from your side. The facilitator handles settlement end-to-end.</p>
"""

_BUILDER_CONTENT = r"""
<h1>build your own combo</h1>
<p class="dim prompt">surp --pick-your-own</p>
<p>Choose the models you'd accept for a job. We save your set as a combo and, on every request, route to whichever one is <b>cheapest at that moment</b>. Pick five frontier models and you'll pay the price of the cheapest one — while the market decides which that is.</p>

<div class="warn">Example: pick <code>claude-opus-5</code>, <code>gpt-5.6-sol</code>, <code>claude-opus-4.8</code>, <code>grok-4.5</code>, <code>gemini-3.1-pro</code>. Right now that routes to <b>gpt-5.6-sol</b> — roughly 93% cheaper than Opus 5, at comparable tier. When prices move, the routing moves with them.</p>

<div class="field">
  <label for="cname">combo name</label>
  <input id="cname" placeholder="my frontier five" value="my frontier five">
</div>

<div class="field">
  <label for="filter">filter models <span class="dim">(name, or class: coding / reasoning / vision / fast / chat)</span></label>
  <input id="filter" placeholder="type to filter…">
</div>

<div class="field">
  <label>
    <input type="checkbox" id="proonly" style="width:auto; margin-right:6px;">
    frontier-tier only
  </label>
</div>

<div id="selbar" class="selbar">
  <span class="dim">selected: </span><span id="selcount">0</span>
  <span id="selchips"></span>
</div>

<button id="save">▶ save combo &amp; get model id</button>
<button id="clear" style="background:transparent;border:1px solid var(--border-bright);color:var(--fg-dim);margin-left:8px;">clear</button>

<div id="result" style="margin-top:16px;"></div>

<h2>available models <span class="dim" id="mcount"></span></h2>
<p class="dim">sorted cheapest first. click a row to add or remove it from your combo.</p>
<div style="max-height:520px; overflow-y:auto; border:1px solid var(--border);">
<table id="mtable">
  <thead><tr><th>pick</th><th>model</th><th>class</th><th>USD / 1M tok</th><th>tier</th><th>sellers</th></tr></thead>
  <tbody id="mbody"><tr><td colspan="6" class="dim">loading catalog…</td></tr></tbody>
</table>
</div>

<h2>community combos</h2>
<p class="dim">combos other people built, most-used first. any of these model ids works immediately.</p>
<div id="community"><p class="dim">loading…</p></div>

<style>
  .selbar { border:1px solid var(--border-bright); background:var(--bg-alt); padding:10px 12px; margin:14px 0; min-height:40px; }
  .chip { display:inline-block; border:1px solid var(--accent-dim); color:var(--accent); padding:2px 8px; margin:3px; font-size:11px; cursor:pointer; }
  .chip:hover { background:var(--red); border-color:var(--red); color:var(--bg); }
  .chip::after { content:" ✕"; opacity:0.6; }
  #mtable tbody tr { cursor:pointer; }
  #mtable tbody tr.picked { background:#04180f; }
  #mtable tbody tr.picked td:first-child::before { content:"✓"; color:var(--accent); }
  .tier-pro { color:var(--yellow); }
  .tier-std { color:var(--fg-dim); }
  .okbox { border:1px solid var(--accent); padding:14px; background:var(--bg-alt); }
</style>

<script>
const $ = (id) => document.getElementById(id);
let CATALOG = [], PICKED = new Set();

function renderChips() {
  $("selcount").textContent = PICKED.size;
  $("selchips").innerHTML = [...PICKED].map(m =>
    `<span class="chip" data-m="${m}">${m}</span>`).join("");
  $("selchips").querySelectorAll(".chip").forEach(c => {
    c.onclick = (e) => { e.stopPropagation(); PICKED.delete(c.dataset.m); renderChips(); renderTable(); };
  });
}

function renderTable() {
  const q = $("filter").value.trim().toLowerCase();
  const proOnly = $("proonly").checked;
  const rows = CATALOG.filter(m => {
    if (proOnly && !m.pro) return false;
    if (!q) return true;
    return m.model.toLowerCase().includes(q) || m.class.toLowerCase().includes(q);
  });
  $("mcount").textContent = `(${rows.length} of ${CATALOG.length})`;
  $("mbody").innerHTML = rows.map(m => `
    <tr data-m="${m.model}" class="${PICKED.has(m.model) ? 'picked' : ''}">
      <td class="pool"></td>
      <td class="model">${m.model}</td>
      <td class="pool">${m.class}</td>
      <td class="price">$${m.usd_per_1m.toFixed(4)}</td>
      <td class="${m.pro ? 'tier-pro' : 'tier-std'}">${m.pro ? 'frontier' : 'standard'}</td>
      <td class="pool">${m.sellers ?? '-'}</td>
    </tr>`).join("") || `<tr><td colspan="6" class="dim">no models match that filter</td></tr>`;
  $("mbody").querySelectorAll("tr[data-m]").forEach(tr => {
    tr.onclick = () => {
      const m = tr.dataset.m;
      PICKED.has(m) ? PICKED.delete(m) : PICKED.add(m);
      renderChips(); renderTable();
    };
  });
}

$("filter").oninput = renderTable;
$("proonly").onchange = renderTable;
$("clear").onclick = () => { PICKED.clear(); renderChips(); renderTable(); $("result").innerHTML = ""; };

$("save").onclick = async () => {
  if (PICKED.size < 2) { $("result").innerHTML = `<p class="err">pick at least 2 models.</p>`; return; }
  $("result").innerHTML = `<p class="dim">saving…</p>`;
  try {
    const r = await fetch("/api/combos/custom", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: $("cname").value, models: [...PICKED]})
    });
    const j = await r.json();
    if (!r.ok) { $("result").innerHTML = `<p class="err">${j.error || "failed"}${j.unknown ? ": " + j.unknown.join(", ") : ""}</p>`; return; }
    $("result").innerHTML = `
      <div class="okbox">
        <p><b>${j.existing ? "combo already existed — same model set" : "combo saved"}</b></p>
        <p>model id: <code>${j.model_id}</code></p>
        <p>routes right now to <b>${j.routes_to_now}</b> at <span class="price">$${j.usd_per_1m_now.toFixed(4)}/1M</span> (cheapest of your ${j.pool_size})</p>
        <pre style="margin-top:10px;">curl -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"${j.model_id}","messages":[{"role":"user","content":"hi"}]}'</pre>
        <p class="dim">share it: <a href="/api/combos/custom/${j.slug}">/api/combos/custom/${j.slug}</a></p>
      </div>`;
    loadCommunity();
  } catch (e) { $("result").innerHTML = `<p class="err">network error: ${e.message}</p>`; }
};

async function loadCommunity() {
  try {
    const r = await fetch("/api/combos/custom");
    const j = await r.json();
    if (!j.combos || !j.combos.length) { $("community").innerHTML = `<p class="dim">none yet — build the first one.</p>`; return; }
    $("community").innerHTML = `<table><thead><tr><th>name</th><th>model id</th><th>routes to now</th><th>USD / 1M</th><th>models</th><th>uses</th></tr></thead><tbody>` +
      j.combos.map(c => `<tr>
        <td>${c.name}</td>
        <td class="combo">${c.model_id}</td>
        <td class="model">${c.routes_to_now ?? '<span class="err">n/a</span>'}</td>
        <td class="price">${c.usd_per_1m_now != null ? "$" + c.usd_per_1m_now.toFixed(4) : "-"}</td>
        <td class="pool">${c.pool_size}</td>
        <td class="pool">${c.hits}</td>
      </tr>`).join("") + `</tbody></table>`;
  } catch (e) { $("community").innerHTML = `<p class="err">could not load: ${e.message}</p>`; }
}

(async () => {
  try {
    const r = await fetch("/api/models");
    const j = await r.json();
    CATALOG = j.models || [];
    renderTable(); renderChips();
  } catch (e) { $("mbody").innerHTML = `<tr><td colspan="6" class="err">catalog failed: ${e.message}</td></tr>`; }
  loadCommunity();
})();
</script>
"""

async def page_model_detail(request: web.Request) -> web.Response:
    """Individual model page — SEO landing page for each of 150+ models."""
    slug = request.match_info["slug"]
    try:
        markets = await GCACHE.get()
    except Exception:
        return web.Response(text=_render_html("<h1>Market data unavailable</h1>", "/models"), content_type="text/html", status=503)
    # Find the model by slug
    for m in markets:
        if not cr.is_text_llm(m):
            continue
        info = mi.model_info(m["model"], cr.usd_per_1m(m), m.get("num_sellers") or 0, cr.class_of(m), cr.is_pro(m))
        if info["slug"] == slug:
            # Build the page
            usd = info["usd_per_1m"]
            savings = max(0, (9.0 - usd) / 9.0 * 100) if usd > 0 else 0
            sellers = info.get("sellers", 0)
            pros = "".join(f"<li>{p}</li>" for p in info["pros"])
            cons = "".join(f"<li>{c}</li>" for c in info["cons"])
            strengths_badges = "".join(f'<span class="badge">{s}</span>' for s in info["strengths"])
            content = f"""
<h1>{info['model']}</h1>
<p class="dim prompt">{info['maker']} · {info['family_name']}</p>

<div class="grid">
  <div class="card"><div class="num">${usd:.4f}</div><div class="lbl">USD per 1M tokens</div></div>
  <div class="card"><div class="num">{savings:.0f}%</div><div class="lbl">cheaper than retail</div></div>
  <div class="card"><div class="num">{sellers}</div><div class="lbl">sellers on Surplus</div></div>
  <div class="card"><div class="num">{info['tier']}</div><div class="lbl">tier</div></div>
</div>

<p>{info['description']}</p>

<div style="margin: 16px 0;">{strengths_badges}</div>

<h2>pros</h2>
<ul style="margin-left: 20px; line-height: 1.8;">{pros}</ul>

<h2>cons</h2>
<ul style="margin-left: 20px; line-height: 1.8;">{cons}</ul>

<h2>use this model on surp.ivc.lol</h2>
<p>Reference this model in a custom combo to always get the cheapest price for it:</p>
<pre>curl -X POST https://surp.ivc.lol/api/combos/custom \\
  -H "Content-Type: application/json" \\
  -d '{{"name":"my combo","models":["{info['model']}"]}}'</pre>
<p class="dim">Or compare it against alternatives: <a href="/compare?models={info['model']}">compare {info['model']} &raquo;</a></p>
"""
            # Per-model SEO meta
            meta = {
                "title": f"{info['model']} ({info['maker']}) — price, specs, pros & cons | surp.ivc.lol",
                "desc": f"{info['model']} by {info['maker']}: ${usd:.4f}/1M tokens, {sellers} sellers. {info['description'][:120]}",
            }
            html = _HTML_BASE.replace("__CONTENT__", content)
            html = html.replace("__TITLE__", meta["title"])
            html = html.replace("__DESC__", meta["desc"])
            html = html.replace("__PATH__", f"/models/{slug}")
            import json as _json
            jsonld = {
                "@context": "https://schema.org", "@type": "SoftwareApplication",
                "name": info["model"], "applicationCategory": "AI Model",
                "operatingSystem": "Cloud", "creator": {"@type": "Organization", "name": info["maker"]},
                "offers": {"@type": "Offer", "price": f"{usd:.4f}", "priceCurrency": "USD",
                           "description": "per 1M tokens on Surplus Intelligence marketplace"},
            }
            html = html.replace("__JSONLD__", _json.dumps(jsonld))
            return web.Response(text=html, content_type="text/html")
    # Not found
    content = f'<h1>model not found</h1><p>No model matching slug "{slug}" was found in the live market.</p><p><a href="/top">browse top models &raquo;</a></p>'
    return web.Response(text=_render_html(content, "/models"), content_type="text/html", status=404)


async def page_models_index(request: web.Request) -> web.Response:
    """Index of all models — SEO hub page linking to individual model pages."""
    try:
        markets = await GCACHE.get()
    except Exception:
        return web.Response(text=_render_html("<h1>Market data unavailable</h1>", "/models"), content_type="text/html", status=503)
    rows = []
    text_models = [m for m in markets if cr.is_text_llm(m)]
    text_models.sort(key=lambda m: cr.usd_per_1m(m))
    for m in text_models:
        info = mi.model_info(m["model"], cr.usd_per_1m(m), m.get("num_sellers") or 0, cr.class_of(m), cr.is_pro(m))
        tier_class = "tier-pro" if info["tier"] == "frontier" else "tier-std"
        rows.append(
            f'<tr><td><a href="/models/{info["slug"]}">{info["model"]}</a></td>'
            f'<td>{info["maker"]}</td>'
            f'<td class="{tier_class}">{info["tier"]}</td>'
            f'<td>{info["class"]}</td>'
            f'<td class="price">${info["usd_per_1m"]:.4f}</td>'
            f'<td>{info.get("sellers", 0)}</td></tr>'
        )
    table_body = "\n".join(rows)
    content = f"""
<h1>all models</h1>
<p class="dim prompt">surp --list-models | sort by price</p>
<p>{len(text_models)} <b>AI models</b> available on the <b>Surplus Intelligence marketplace</b> right now. Sorted cheapest first. Click any model for detailed specs, pros &amp; cons, and live pricing. Every model is <b>OpenAI-compatible</b> and accessible via our <b>x402 LLM gateway</b> with <b>pay-per-request</b> pricing in <b>USDC on Base</b>.</p>
<p class="dim">Compare: <a href="/compare">side by side comparison</a> · <a href="/top">top 5 leaderboards</a> · <a href="/find">find the right model</a> · <a href="/connect">connect your app</a></p>
<table><thead><tr><th>model</th><th>maker</th><th>tier</th><th>class</th><th>USD / 1M tok</th><th>sellers</th></tr></thead>
<tbody>{table_body}</tbody></table>
<p class="dim">Prices update live from the marketplace. <a href="/top">See top 5 per category &raquo;</a> · <a href="/find">Find the right model for you &raquo;</a></p>
"""
    return web.Response(text=_render_html(content, "/models"), content_type="text/html")


async def page_compare(request: web.Request) -> web.Response:
    """Side-by-side model comparison tool."""
    try:
        markets = await GCACHE.get()
    except Exception:
        return web.Response(text=_render_html("<h1>Market data unavailable</h1>", "/compare"), content_type="text/html", status=503)
    # Build model options
    text_models = sorted([m for m in markets if cr.is_text_llm(m)], key=lambda m: cr.usd_per_1m(m))
    options = "".join(
        f'<option value="{m["model"]}">{m["model"]} (${cr.usd_per_1m(m):.4f}/1M)</option>'
        for m in text_models
    )
    content = f"""
<h1>compare models</h1>
<p class="dim prompt">surp --diff model-a model-b</p>
<p>Compare <b>AI model pricing</b> side by side. Pick 2-4 models and see their strengths, weaknesses, <b>cost per token</b>, and which is cheapest for your task. All models are <b>OpenAI-compatible</b> and available via our <b>x402 gateway</b> with <b>pay-per-request</b> pricing.</p>
<p class="dim">Need a recommendation instead? <a href="/find">Find the right model for your task</a> · <a href="/top">See top 5 leaderboards</a> · <a href="/models">Browse all 150+ models</a></p>

<div class="field">
  <label>model A</label>
  <select id="m1"><option value="">choose...</option>{options}</select>
</div>
<div class="field">
  <label>model B</label>
  <select id="m2"><option value="">choose...</option>{options}</select>
</div>
<div class="field">
  <label>model C (optional)</label>
  <select id="m3"><option value="">choose...</option>{options}</select>
</div>
<button id="go">&#9654; compare</button>
<div id="result" style="margin-top: 20px;"></div>

<script>
const $ = (id) => document.getElementById(id);

// Pre-populate selects from ?models=a,b,c and auto-run the comparison
// so a shared link like /compare?models=kimi-k2.7-code,deepseek-v4-flash
// shows results immediately without the user having to click. If only one
// model is given, auto-pair it with the cheapest text model so the user
// still gets a useful comparison instead of a "pick 2" error.
(function() {{
  var params = new URLSearchParams(window.location.search);
  var preselect = params.get("models");
  if (preselect) {{
    var names = preselect.split(",").map(s => s.trim()).filter(Boolean);
    if (names.length === 1 && $("m2")) {{
      // Auto-pick the cheapest text model as the second slot (it's the
      // first non-empty option after "choose...").
      if ($("m2").options.length > 1) $("m2").selectedIndex = 1;
    }}
    var ids = ["m1", "m2", "m3"];
    names.slice(0, 3).forEach(function(name, i) {{
      var sel = $(ids[i]);
      if (sel) {{
        // Try exact match first, then case-insensitive.
        for (var j = 0; j < sel.options.length; j++) {{
          if (sel.options[j].value === name ||
              sel.options[j].value.toLowerCase() === name.toLowerCase()) {{
            sel.selectedIndex = j;
            break;
          }}
        }}
      }}
    }});
    if (names.length >= 1) {{
      // Defer until after the click handler is bound below.
      setTimeout(function() {{ if ($("go").onclick) $("go").onclick(); }}, 0);
    }}
  }}
}})();

$("go").onclick = async () => {{
  const picks = ["m1","m2","m3"].map(id => $(id).value).filter(Boolean);
  if (picks.length < 2) {{ $("result").innerHTML = "<p class='err'>pick at least 2 models.</p>"; return; }}
  $("result").innerHTML = "<p class='dim'>loading...</p>";
  try {{
    const res = await fetch("/api/compare?models=" + picks.join(","));
    const d = await res.json();
    if (d.error) {{ $("result").innerHTML = "<p class='err'>" + d.error + "</p>"; return; }}
    let cards = d.models.map(m => `
      <div class="card compare-card">
        <h3>${{m.model}}</h3>
        <p class="dim">${{m.maker}} · $${{m.usd_per_1m.toFixed(4)}}/1M · ${{(m.usd_per_1m * 0.001).toFixed(6)}}/1K tok</p>
        <p>${{m.description.slice(0, 150)}}...</p>
        <p class="dim"><b>strengths:</b> ${{m.strengths.join(", ")}}</p>
        <p style="color:var(--accent)"><b>pros:</b></p>
        <ul style="margin-left:16px;font-size:12px;line-height:1.6;">${{m.pros.slice(0,3).map(p => "<li>"+p+"</li>").join("")}}</ul>
        <p style="color:var(--red)"><b>cons:</b></p>
        <ul style="margin-left:16px;font-size:12px;line-height:1.6;">${{m.cons.slice(0,3).map(c => "<li>"+c+"</li>").join("")}}</ul>
        <p><a href="/models/${{m.slug}}">full details &raquo;</a></p>
      </div>
    `).join("");
    let cheapest = d.models.reduce((a,b) => a.usd_per_1m < b.usd_per_1m ? a : b);
    $("result").innerHTML = `
      <p style="margin-bottom:16px;">cheapest pick: <b style="color:var(--accent)">${{cheapest.model}}</b> at $${{cheapest.usd_per_1m.toFixed(4)}}/1M</p>
      <div class="grid" style="grid-template-columns: repeat(${{d.models.length}}, 1fr); gap:12px;">${{cards}}</div>`;
  }} catch(e) {{ $("result").innerHTML = "<p class='err'>" + e.message + "</p>"; }}
}};
</script>
"""
    return web.Response(text=_render_html(content, "/compare"), content_type="text/html")


async def api_compare(request: web.Request) -> web.Response:
    """GET /api/compare?models=a,b,c — comparison data."""
    try:
        markets = await GCACHE.get()
    except Exception:
        return web.json_response({"error": "market data unavailable"}, status=503)
    names = [n.strip() for n in request.query.get("models", "").split(",") if n.strip()]
    if len(names) < 2:
        return web.json_response({"error": "provide at least 2 model names"}, status=400)
    market_map = {m["model"].lower(): m for m in markets}
    out = []
    for name in names[:4]:
        m = market_map.get(name.lower())
        if not m:
            continue
        info = mi.model_info(m["model"], cr.usd_per_1m(m), m.get("num_sellers") or 0, cr.class_of(m), cr.is_pro(m))
        out.append(info)
    if len(out) < 2:
        return web.json_response({"error": "not enough valid models found"}, status=404)
    return web.json_response({"models": out})


async def page_find(request: web.Request) -> web.Response:
    """Find the right model for you — interactive quiz."""
    use_cases_html = ""
    for uc in mi.USE_CASES:
        use_cases_html += f'<div class="card use-case" data-id="{uc["id"]}" style="cursor:pointer;">'
        use_cases_html += f'<div class="num">{uc["icon"]}</div>'
        use_cases_html += f'<p><b>{uc["label"]}</b></p>'
        use_cases_html += f'<p class="dim" style="font-size:12px;">{uc["description"][:100]}...</p>'
        use_cases_html += '</div>'
    content = f"""
<h1>find the right model</h1>
<p class="dim prompt">surp --recommend</p>
<p>Not sure which <b>AI model</b> to use? Pick your use case and we'll show you the top 5 cheapest options from the <b>Surplus Intelligence marketplace</b>. Every recommendation is <b>OpenAI-compatible</b> and available via our <b>x402 LLM gateway</b> at <b>pay-per-request</b> pricing.</p>
<p class="dim">Want to compare them? <a href="/compare">Compare models side by side</a> · <a href="/top">See top 5 leaderboards</a> · <a href="/models">Browse all models</a></p>

<div class="grid">{use_cases_html}</div>

<div id="results" style="margin-top: 20px;"></div>

<script>
document.querySelectorAll('.use-case').forEach(el => {{
  el.onclick = async () => {{
    const id = el.dataset.id;
    document.querySelectorAll('.use-case').forEach(e => e.style.borderColor = 'var(--border)');
    el.style.borderColor = 'var(--accent)';
    document.getElementById('results').innerHTML = '<p class="dim">finding best models...</p>';
    try {{
      const r = await fetch('/api/recommend?use_case=' + id);
      const d = await r.json();
      if (!d.models || !d.models.length) {{
        document.getElementById('results').innerHTML = '<p class="dim">no models match that criteria right now.</p>';
        return;
      }}
      let rows = d.models.map((m, i) => `
        <tr><td>${{i+1}}</td>
        <td><a href="/models/${{m.slug}}">${{m.model}}</a></td>
        <td class="dim">${{m.maker}}</td>
        <td class="price">$${{m.usd_per_1m.toFixed(4)}}</td>
        <td class="dim">${{m.strengths.join(", ")}}</td>
        <td>${{m.tier === 'frontier' ? '<span class="badge">frontier</span>' : 'standard'}}</td></tr>`
      ).join("");
      document.getElementById('results').innerHTML = `
        <h2>top ${{d.models.length}} for: ${{d.use_case}}</h2>
        <table><thead><tr><th>#</th><th>model</th><th>maker</th><th>USD/1M</th><th>strengths</th><th>tier</th></tr></thead>
        <tbody>${{rows}}</tbody></table>
        <p class="dim">use surp.ivc.lol to automatically get the cheapest of these on every request: <a href="/connect">connect your app &raquo;</a></p>`;
    }} catch(e) {{
      document.getElementById('results').innerHTML = '<p class="err">' + e.message + '</p>';
    }}
  }};
}});
</script>
"""
    return web.Response(text=_render_html(content, "/find"), content_type="text/html")


async def api_recommend(request: web.Request) -> web.Response:
    """GET /api/recommend?use_case=coding-daily — top 5 models for a use case."""
    try:
        markets = await GCACHE.get()
    except Exception:
        return web.json_response({"error": "market data unavailable"}, status=503)
    uc_id = request.query.get("use_case", "coding-daily")
    uc = next((u for u in mi.USE_CASES if u["id"] == uc_id), mi.USE_CASES[0])
    recs = mi.recommend_models(markets, uc_id, 5)
    return web.json_response({"use_case": uc["label"], "models": recs})


async def page_top(request: web.Request) -> web.Response:
    """Top 5 models per category — leaderboard page."""
    try:
        markets = await GCACHE.get()
    except Exception:
        return web.Response(text=_render_html("<h1>Market data unavailable</h1>", "/top"), content_type="text/html", status=503)
    categories = [
        ("cheapest overall", "all text LLMs", lambda m: True),
        ("best for coding", "coding-class models", lambda m: cr.is_coding(m)),
        ("best for reasoning", "reasoning models", lambda m: cr.is_reasoning(m)),
        ("best for chat", "general chat LLMs", lambda m: cr.is_chat(m)),
        ("fastest (small models)", "fast-class models", lambda m: cr.is_fast(m)),
        ("best for vision", "vision-capable models", lambda m: cr.is_vision(m)),
        ("frontier tier (premium)", "frontier-tier models", lambda m: cr.is_pro(m)),
    ]
    sections = ""
    for title, subtitle, filt in categories:
        pool = sorted([m for m in markets if cr.is_text_llm(m) and filt(m)], key=cr.price_of)[:5]
        if not pool:
            continue
        rows = ""
        for i, m in enumerate(pool, 1):
            info = mi.model_info(m["model"], cr.usd_per_1m(m), m.get("num_sellers") or 0, cr.class_of(m), cr.is_pro(m))
            usd = info["usd_per_1m"]
            medal = ["🥇", "🥈", "🥉", "4.", "5."][i-1]
            rows += f'<tr><td>{medal}</td><td><a href="/models/{info["slug"]}">{m["model"]}</a></td><td class="dim">{info["maker"]}</td><td class="price">${usd:.4f}</td><td>{m.get("num_sellers") or m.get("seller_count") or "-"}</td></tr>'
        sections += f'<h2>{title}</h2><p class="dim">{subtitle}</p><table><thead><tr><th></th><th>model</th><th>maker</th><th>USD/1M</th><th>sellers</th></tr></thead><tbody>{rows}</tbody></table>'
    content = f"""
<h1>top models</h1>
<p class="dim prompt">surp --leaderboard</p>
<p>Compare <b>LLM API pricing</b> across 150+ models from every major provider. Our <b>x402 gateway</b> routes every request to the cheapest model on the <b>Surplus Intelligence marketplace</b> in real time. Every model is <b>OpenAI-compatible</b> and available via <b>pay-per-request</b> — no account, no API key, no subscription.</p>
<p class="dim">Looking for a specific model? <a href="/models">Browse all 150+ models</a> · <a href="/compare">Compare models side by side</a> · <a href="/find">Find the right model for your task</a></p>
{sections}
<p class="dim">Want a personalized recommendation? <a href="/find">Find the right model for you &raquo;</a></p>
"""
    return web.Response(text=_render_html(content, "/top"), content_type="text/html")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# Farcaster Mini App
# ──────────────────────────────────────────────────────────────────────────────

async def page_miniapp(request: web.Request) -> web.Response:
    """The Farcaster Mini App — a self-contained page that works inside
    Warpcast and other Farcaster clients. No _HTML_BASE wrapper (no nav bar,
    no scanlines) — the miniapp renders standalone in a vertical modal."""
    html = _MINIAPP_HTML
    return web.Response(text=html, content_type="text/html")


async def serve_farcaster_manifest(request: web.Request) -> web.Response:
    """Farcaster Mini App manifest at /.well-known/farcaster.json.
    The accountAssociation section requires a JFS (JSON Farcaster Signature)
    from the domain owner's custody key. We serve it from env so the user
    can generate and rotate it without a redeploy.
    """
    account_assoc = {
        "header": os.environ.get("FC_JFS_HEADER", ""),
        "payload": os.environ.get("FC_JFS_PAYLOAD", ""),
        "signature": os.environ.get("FC_JFS_SIGNATURE", ""),
    }
    # Only include accountAssociation if all three parts are set
    manifest = {
        "miniapp": {
            "version": "1",
            "name": "surp",
            "homeUrl": "https://surp.ivc.lol/miniapp",
            "iconUrl": "https://surp.ivc.lol/static/icon.png",
            "imageUrl": "https://surp.ivc.lol/static/hero.png",
            "buttonTitle": "▶ try it",
            "splashImageUrl": "https://surp.ivc.lol/static/icon.png",
            "splashBackgroundColor": "#000000",
            "subtitle": "cheapest LLM API",
            "description": "Pay per request. We route to the cheapest model on the Surplus Intelligence marketplace. USDC on Base via x402.",
            "primaryCategory": "developer-tools",
            "tags": ["llm", "api", "crypto", "developer", "x402"],
            "tagline": "cheapest AI models",
            "ogTitle": "surp.ivc.lol",
            "ogDescription": "The cheapest LLM API on the internet. Pay per request in USDC on Base.",
            "ogImageUrl": "https://surp.ivc.lol/static/hero.png",
            "noindex": False,
        }
    }
    if all(account_assoc.values()):
        manifest["accountAssociation"] = account_assoc
    return web.json_response(manifest, content_type="application/json")


_MINIAPP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>surp.ivc.lol — x402 LLM Gateway | Cheapest AI Models, Pay Per Request</title>
<meta name="fc:miniapp" content='{"version":"1","imageUrl":"https://surp.ivc.lol/static/hero.png","button":{"title":"▶ try it","action":{"type":"launch_frame","name":"surp","url":"https://surp.ivc.lol/miniapp","splashImageUrl":"https://surp.ivc.lol/static/icon.png","splashBackgroundColor":"#000000"}}}'>
<meta name="fc:frame" content='{"version":"1","imageUrl":"https://surp.ivc.lol/static/hero.png","button":{"title":"▶ try it","action":{"type":"launch_frame","name":"surp","url":"https://surp.ivc.lol/miniapp","splashImageUrl":"https://surp.ivc.lol/static/icon.png","splashBackgroundColor":"#000000"}}}'>
<meta property="og:title" content="surp.ivc.lol — cheapest LLM API">
<meta name="description" content="surp.ivc.lol is an x402 LLM gateway. Pay per request in USDC on Base. We route every request to the cheapest AI model on the Surplus Intelligence marketplace. No account, no API key.">
<meta property="og:description" content="Pay-per-request LLM inference. Cheapest model, every time.">
<meta property="og:image" content="https://surp.ivc.lol/static/hero.png">
<style>
  :root { --bg:#000; --bg-alt:#0a0a0a; --fg:#e0e0e0; --fg-dim:#888; --accent:#00ff9c; --yellow:#ffd23f; --border:#1a1a1a; --mono:"JetBrains Mono","Fira Code","SF Mono","Courier New",monospace; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { background: var(--bg); color: var(--fg); font-family: var(--mono); font-size: 13px; line-height: 1.5; }
  .wrap { max-width: 420px; margin: 0 auto; padding: 20px 16px 40px; }
  h1 { font-size: 22px; color: var(--accent); margin-bottom: 4px; }
  .sub { color: var(--fg-dim); font-size: 12px; margin-bottom: 24px; }
  .stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin: 20px 0; }
  .stat { border: 1px solid var(--border); background: var(--bg-alt); padding: 12px 8px; text-align: center; }
  .stat .num { font-size: 20px; color: var(--accent); font-weight: bold; }
  .stat .lbl { font-size: 9px; color: var(--fg-dim); text-transform: uppercase; margin-top: 2px; letter-spacing: 0.5px; }
  .ticker { border: 1px solid var(--border); background: var(--bg-alt); padding: 12px; margin: 16px 0; }
  .ticker h3 { color: var(--accent); font-size: 12px; margin-bottom: 8px; }
  .ticker table { width: 100%; font-size: 11px; border-collapse: collapse; }
  .ticker td { padding: 4px 6px; border-bottom: 1px solid #111; }
  .ticker .combo { color: var(--accent); }
  .ticker .model { color: var(--fg); }
  .ticker .price { color: var(--yellow); text-align: right; }
  .btn { display: block; width: 100%; padding: 12px; background: var(--accent); color: var(--bg); border: none; font-family: var(--mono); font-size: 14px; font-weight: bold; cursor: pointer; text-align: center; text-decoration: none; margin: 12px 0 6px; }
  .btn:hover { opacity: 0.9; }
  .btn-alt { background: transparent; border: 1px solid var(--accent); color: var(--accent); }
  .btn-alt:hover { background: var(--accent); color: var(--bg); }
  .dim { color: var(--fg-dim); }
  .small { font-size: 11px; }
  .section { margin: 24px 0 0; }
  .section h3 { color: var(--accent); font-size: 13px; margin-bottom: 8px; }
  code { background: var(--bg-alt); padding: 1px 4px; font-size: 11px; color: var(--accent); border: 1px solid var(--border); }
  pre { background: var(--bg-alt); border: 1px solid var(--border); padding: 10px; font-size: 10px; overflow-x: auto; margin: 8px 0; line-height: 1.5; }
  pre::before { content: "$ "; color: var(--accent-dim, #008c54); }
  .footer { text-align: center; margin-top: 32px; color: var(--fg-dim); font-size: 10px; }
  .footer a { color: var(--fg-dim); }
  .pulse { display: inline-block; width: 6px; height: 6px; background: var(--accent); border-radius: 50%; margin-right: 4px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>surp</h1>
  <p class="sub">the cheapest LLM API on the internet</p>

  <p>Ask any AI model. We check the live marketplace, pick whoever is cheapest right now, and route your request there. Pay per request in USDC on Base — no account, no API key, no subscription.</p>

  <div class="stats">
    <div class="stat"><div class="num" id="mc">-</div><div class="lbl">models</div></div>
    <div class="stat"><div class="num" id="tc">-</div><div class="lbl">text LLMs</div></div>
    <div class="stat"><div class="num" id="cc">-</div><div class="lbl">cheapest</div></div>
  </div>

  <div class="ticker">
    <h3><span class="pulse"></span> live cheapest models</h3>
    <table id="ticker-body">
      <tr><td colspan="3" class="dim" style="text-align:center;padding:16px;">loading...</td></tr>
    </table>
  </div>

  <div class="section">
    <h3>how it works</h3>
    <p class="small">You say "give me the best coding model." We fetch live prices from 150+ models on the Surplus Intelligence marketplace, find the cheapest one for your task, and send your request there. 1¢ per request. USDC on Base. That's it.</p>
  </div>

  <div class="section">
    <h3>try it</h3>
    <p class="small dim">This costs 1¢ of real USDC on Base. The response will be a payment challenge (402). To complete it, sign with your wallet and retry.</p>
    <pre>curl -X POST https://surp.ivc.lol/v1/chat/completions   -H "Content-Type: application/json"   -d '{"model":"surp/best-chat",
       "messages":[{"role":"user","content":"what is 2+2?"}],
       "max_tokens":50}'</pre>
  </div>

  <a class="btn" href="https://surp.ivc.lol/" target="_blank">▶ full site</a>
  <a class="btn btn-alt" href="https://surp.ivc.lol/connect" target="_blank">connect your agent</a>
  <a class="btn btn-alt" href="https://surp.ivc.lol/builder" target="_blank">build a combo</a>
  <button class="btn btn-alt" id="share-btn" style="display:none;cursor:pointer;">share on farcaster</button>

  <div class="footer">
    surp.ivc.lol · aggregating the aggregator · x402 + Base
  </div>
</div>

<script type="module">
  import { sdk } from "https://esm.run/@farcaster/miniapp-sdk";
  // Signal ready IMMEDIATELY — don't wait for data fetches.
  // The splash screen stays up until this is called.
  sdk.actions.ready();
</script>
<script>
(async () => {
  // Fetch live market data
  try {
    const r = await fetch("https://surp.ivc.lol/api/combos");
    const d = await r.json();
    const combos = d.combos.filter(c => c.resolved_model);
    document.getElementById("mc").textContent = combos.length;
    document.getElementById("tc").textContent = "152+";
    if (combos.length) {
      const cheapest = combos.reduce((a,b) => (a.usd_per_1m_tokens||1e9) < (b.usd_per_1m_tokens||1e9) ? a : b);
      document.getElementById("cc").textContent = "$" + (cheapest.usd_per_1m_tokens||0).toFixed(4);
    }
    const tbody = document.getElementById("ticker-body");
    tbody.innerHTML = combos.slice(0, 8).map(c =>
      `<tr><td class="combo">${c.combo}</td><td class="model">${c.resolved_model}</td><td class="price">$${(c.usd_per_1m_tokens||0).toFixed(4)}</td></tr>`
    ).join("");
  } catch(e) {
    document.getElementById("ticker-body").innerHTML = '<tr><td colspan="3" class="dim">offline</td></tr>';
  }
})();
</script>
<script type="module">
  // Share button — separate script so it can fail independently of the data fetch
  try {
    const { sdk } = await import("https://esm.run/@farcaster/miniapp-sdk");
    const shareBtn = document.getElementById("share-btn");
    shareBtn.style.display = "block";
    shareBtn.onclick = () => {
      sdk.actions.composeCast({
        text: "I just found the cheapest LLM API on the internet — pay per request in USDC, no account needed. It routes to whatever model is cheapest right now.\n\nsurp.ivc.lol",
        embeds: ["https://surp.ivc.lol/miniapp"],
      });
    };
  } catch(e) {
    // Not in a Farcaster client — hide the share button
    document.getElementById("share-btn").style.display = "none";
  }
</script>
</body>
</html>
"""


async def page_cache(request: web.Request) -> web.Response:
    """Explain the cache-aware routing and exact-response cache technology."""
    html = _HTML_BASE.replace("__CONTENT__", cp.CONTENT)
    html = html.replace("__TITLE__", cp.TITLE)
    html = html.replace("__DESC__", cp.DESC)
    html = html.replace("__PATH__", "/cache")
    return web.Response(text=html, content_type="text/html")


async def page_proposal(request: web.Request) -> web.Response:
    """ELI5 cache-flywheel proposal + live metrics + advisory vote."""
    live = {
        "rewards": rl.global_stats(),
        "votes": pv.results(),
    }
    content = pp.content(live)
    html = _render_html(content, "/proposal")
    return web.Response(text=html, content_type="text/html")


async def api_cast_vote(request: web.Request) -> web.Response:
    """POST /api/vote — cast or change an advisory vote."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    handle = str(body.get("handle", ""))
    option = str(body.get("option", ""))
    comment = str(body.get("comment", ""))
    ip = request.headers.get("X-Real-IP") or request.remote or ""
    result = pv.cast_vote(handle, option, comment, ip)
    return web.json_response(result, status=200 if result.get("ok") else 400)


async def api_vote_results(request: web.Request) -> web.Response:
    """GET /api/votes — live vote totals and recent comments."""
    return web.json_response({**pv.results(), "comments": pv.recent_comments()})


async def page_token_gating(request: web.Request) -> web.Response:
    """Token-gated access documentation + community feedback board."""
    live = {
        "rewards": rl.global_stats(),
        "feedback": cf.summary(),
        "recent_feedback": cf.recent(20),
    }
    content = tgp.content(live)
    html = _render_html(content, "/token-gating")
    return web.Response(text=html, content_type="text/html")


async def api_feedback_submit(request: web.Request) -> web.Response:
    """POST /api/feedback — submit community feedback."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    handle = str(body.get("handle", ""))
    category = str(body.get("category", ""))
    message = str(body.get("message", ""))
    ip = request.headers.get("X-Real-IP") or request.remote or ""
    result = cf.submit(handle, category, message, ip)
    return web.json_response(result, status=200 if result.get("ok") else 400)


async def api_feedback_upvote(request: web.Request) -> web.Response:
    """POST /api/feedback/upvote — upvote a piece of feedback."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    fid = int(body.get("id", 0))
    handle = str(body.get("handle", ""))
    ip = request.headers.get("X-Real-IP") or request.remote or ""
    result = cf.upvote(fid, handle, ip)
    return web.json_response(result, status=200 if result.get("ok") else 400)


async def api_feedback_list(request: web.Request) -> web.Response:
    """GET /api/feedback — recent feedback + category summary."""
    limit = int(request.query.get("limit", "20"))
    return web.json_response({
        "feedback": cf.recent(min(limit, 50)),
        "summary": cf.summary(),
    })


async def page_free_models(request: web.Request) -> web.Response:
    """Live sponsored-free models + OmniRoute catalog intelligence."""
    try:
        markets = await GCACHE.get()
    except Exception:
        markets = []
    sponsored = [
        {
            "model": m["model"],
            "usd_per_1m": cr.usd_per_1m(m),
            "healthy_sellers": int(m.get("healthy_seller_count") or 0),
            "requests_24h": int(m.get("requests_24h") or 0),
            "volume_24h": int(m.get("volume_24h") or 0),
        }
        for m in fm.sponsored_pool(markets)
    ]
    html = _render_html(
        fmp.content(sponsored, fm.live_stats(), fm.catalog_summary()),
        "/free-models",
    )
    return web.Response(text=html, content_type="text/html")


async def api_free_stats(request: web.Request) -> web.Response:
    """GET /api/free-models — live pool, usage, and catalog totals."""
    try:
        markets = await GCACHE.get()
    except Exception:
        markets = []
    pool = fm.sponsored_pool(markets)
    return web.json_response({
        "sponsored": True,
        "usage": fm.live_stats(),
        "eligible_models": [
            {
                "model": m["model"],
                "usd_per_1m": round(cr.usd_per_1m(m), 6),
                "healthy_sellers": int(m.get("healthy_seller_count") or 0),
                "requests_24h": int(m.get("requests_24h") or 0),
            }
            for m in pool
        ],
        "conversion": fm.conversion_stats(),
        "omniroute_catalog": fm.catalog_summary(),
        "disclaimer": "Catalog is informational. Public inference is sponsored by surp using paid Surplus access, not third-party personal free-tier credentials.",
    })


async def api_free_key_create(request: web.Request) -> web.Response:
    """POST /api/free-key — create a free-tier API key with elevated budgets.

    Body: {"label": "my-app", "elevated_requests": 1000, "elevated_tokens": 200000}
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    label = str(body.get("label", ""))[:60] or "anonymous"
    elevated_requests = min(int(body.get("elevated_requests", 1000)), 10000)
    elevated_tokens = min(int(body.get("elevated_tokens", 200000)), 2_000_000)
    rec = fm.create_free_key(label, elevated_requests, elevated_tokens)
    return web.json_response({
        "ok": True,
        "key": rec["key"],
        "label": rec["label"],
        "tier": "free",
        "elevated_requests": rec["elevated_requests"],
        "elevated_tokens": rec["elevated_tokens"],
        "note": "Use this key as the Bearer token for surp/free. Elevated budgets replace the default IP-based limits.",
    })


async def page_health_board(request: web.Request) -> web.Response:
    """Live free model health board with TPS, latency, and failure rates."""
    ranked = ph.all_models()
    html = _render_html(
        hbp.content(ranked, fm.conversion_stats(), fm.live_stats()),
        "/health",
    )
    return web.Response(text=html, content_type="text/html")


async def page_features(request: web.Request) -> web.Response:
    """Dated features/changelog page showing day-to-day project progress."""
    html = _render_html(fp.content(), "/features")
    return web.Response(text=html, content_type="text/html")


async def page_auction(request: web.Request) -> web.Response:
    """Cache-affinity auction explainer — the ad-network model for cached inference."""
    html = _render_html(ap.content(ca.global_stats()), "/auction")
    return web.Response(text=html, content_type="text/html")


async def page_performance(request: web.Request) -> web.Response:
    """Verified LLM output-TPS, TTFT, and throughput-per-dollar leaderboard."""
    ranked = mb.ranked()
    recent = mb.recent_runs(ranked[0]["model"], 10) if ranked else []
    html = _render_html(pp.content(ranked, recent), "/performance")
    return web.Response(text=html, content_type="text/html")


# ─── Surp Value Index (SVI) ────────────────────────────────────────────────


async def _svi_ranked() -> list[dict]:
    """Compute the live SVI leaderboard from market + benchmark data."""
    try:
        markets = await GCACHE.get()
    except Exception:
        markets = []
    market_models = [
        {"model": m.get("model"), "price_usd_per_1m": cr.usd_per_1m(m)}
        for m in markets if isinstance(m, dict) and m.get("model")
    ]
    benchmarked = mb.ranked()
    return vi.rank(market_models, benchmarked)


async def api_svi(request: web.Request) -> web.Response:
    """GET /api/svi — Surp Value Index leaderboard (cost×intel×speed)."""
    rows = await _svi_ranked()
    return web.json_response({
        "weights": {"cost": vi.W_COST, "intelligence": vi.W_INTEL, "speed": vi.W_SPEED},
        "count": len(rows),
        "ranked": rows,
    })


async def api_svi_submit(request: web.Request) -> web.Response:
    """POST /api/svi/benchmark — submit a model benchmark (competitive surface).

    Body: {model, mmlu?, gpqa?, humaneval?, ifeval?, submitter?}
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    model = str(body.get("model", "")).strip()
    if not model:
        return web.json_response({"error": "model required"}, status=400)
    res = vi.submit_benchmark(
        model,
        mmlu=body.get("mmlu"),
        gpqa=body.get("gpqa"),
        humaneval=body.get("humaneval"),
        ifeval=body.get("ifeval"),
        submitter=str(body.get("submitter", "")),
    )
    return web.json_response(res)


async def page_svi(request: web.Request) -> web.Response:
    """SVI leaderboard page — the single composite value index."""
    rows = await _svi_ranked()
    top = rows[:20]
    rows_html = ""
    for i, r in enumerate(top, 1):
        rows_html += (
            f"<tr><td>{i}</td>"
            f"<td class='model'>{r['model']}</td>"
            f"<td class='num'>{r['svi']}</td>"
            f"<td class='dim'>{r['cost_score']}</td>"
            f"<td class='dim'>{r['intelligence_score']}</td>"
            f"<td class='dim'>{r['speed_score']}</td>"
            f"<td class='price'>${r['price_usd_per_1m']:.4f}/M</td>"
            f"<td class='dim'>{r['p50_tps']:.1f} tps</td></tr>"
        )
    if not rows_html:
        rows_html = "<tr><td colspan='8' class='err'>No models with verified speed yet — run benchmarks first.</td></tr>"
    content = f"""
<h1>Surp Value Index (SVI)</h1>
<p class="dim prompt">the one number: cost × intelligence × speed</p>
<p>A single composite score per model — weighted geometric mean of three
normalized sub-scores. Buyers optimize for the highest SVI in class;
suppliers climb the leaderboard by submitting verified benchmark results
or improving real served TPS.</p>
<h2>## weights</h2>
<p>cost <b>{int(vi.W_COST*100)}%</b> · intelligence <b>{int(vi.W_INTEL*100)}%</b> · speed <b>{int(vi.W_SPEED*100)}%</b></p>
<h2>## leaderboard</h2>
<table>
<tr><th>#</th><th>model</th><th>SVI</th><th>cost</th><th>intel</th><th>speed</th><th>price</th><th>tps</th></tr>
{rows_html}
</table>
<h2>## route by your own lens</h2>
<p>You don't have to use the default weights. Pass <code>surp_mode</code> to
any combo to route by the lens that fits the job:</p>
<table>
<tr><th>mode</th><th>weights (cost·intel·speed)</th><th>use for</th></tr>
<tr><td><code>cost</code></td><td>pure cheapest</td><td>overnight batch, agents that can wait</td></tr>
<tr><td><code>value</code></td><td>45·40·15</td><td>default SVI — best all-round value</td></tr>
<tr><td><code>balanced</code></td><td>33·33·33</td><td>no strong preference</td></tr>
<tr><td><code>speed</code></td><td>15·15·70</td><td>interactive work, pair programming</td></tr>
<tr><td><code>intel</code></td><td>20·60·20</td><td>hard reasoning problems</td></tr>
</table>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{{"model":"surp/best-chat","surp_mode":"speed",
       "messages":[{{"role":"user","content":"hi"}}]}}'</pre>
<p class="dim">Or go fully custom with <code>surp_weights</code> — a
<code>cost:intel:speed</code> triple, e.g. <code>"surp_weights":"0.3:0.4:0.3"</code>.
Models without a verified TPS fall back to cheapest so routing never fails.
The 402 response includes <code>routing_reason</code> so you can see which lens won.</p>
<h2>## submit a benchmark</h2>
<pre>curl -X POST https://surp.ivc.lol/api/svi/benchmark \\
  -H "Content-Type: application/json" \\
  -d '{{"model":"my-quantized-model","mmlu":88,"humaneval":92,"submitter":"you"}}'</pre>
<p class="dim">Verified submissions move the leaderboard. Missing axes fall back to the
model class default so partial submissions still count.</p>
"""
    html = _render_html(content, "/svi")
    return web.Response(text=html, content_type="text/html")


# ─── Studio — all-in-one AI creative workspace ──────────────────────────────


async def api_studio_status(request: web.Request) -> web.Response:
    """GET /api/studio/status — provider status for the Studio UI banner."""
    return web.json_response(st.provider_status())


async def api_studio_generate(request: web.Request) -> web.Response:
    """POST /api/studio/generate — text-to-image, image-to-image, video.

    Body: {kind: 'image'|'video', mode: 't2i'|'i2i'|'t2v'|'i2v',
           prompt: str, image_url?: str, params?: {steps, guidance, seed,
           aspect, strength, video_model}}

    Generation is gated on the user's wallet USDC balance: a user with no
    funds cannot burn surp's Surplus credits for free. The gate requires a
    minimum balance (SURP_STUDIO_MIN_BALANCE_USDC, default $0.05) before
    any generation is attempted.
    """
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    kind = str(body.get("kind", "image"))
    mode = str(body.get("mode", "t2i"))
    prompt = str(body.get("prompt", "")).strip()
    if kind not in ("image", "video"):
        return web.json_response({"error": "kind must be image or video"}, status=400)
    if mode not in ("t2i", "i2i", "t2v", "i2v"):
        return web.json_response({"error": "mode must be t2i/i2i/t2v/i2v"}, status=400)
    if not prompt:
        return web.json_response({"error": "prompt required"}, status=400)
    if mode in ("i2i", "i2v") and not body.get("image_url"):
        return web.json_response({"error": "image_url required for image-to-* modes"}, status=400)

    # ── Balance gate: never let a zero-balance user burn surp's credits ──
    min_usdc = float(os.environ.get("SURP_STUDIO_MIN_BALANCE_USDC", "0.05"))
    bal = ua.get_user_balance(user_id)
    usdc_atomic = int(bal.get("usdc_atomic", 0))
    if usdc_atomic < int(min_usdc * 1_000_000):
        return web.json_response({
            "error": "insufficient balance — add USDC to your wallet to use studio generation",
            "required_usdc": min_usdc,
            "balance_usdc": round(usdc_atomic / 1_000_000, 6),
        }, status=402)

    try:
        res = await st.generate(
            kind, mode, prompt,
            image_url=str(body.get("image_url", "")),
            params=body.get("params") or {},
        )
    except Exception as e:
        log.error(f"studio generate failed: {e}")
        return web.json_response({"error": f"generation failed: {e}"}, status=500)
    creation = st.create_creation(
        user_id, kind, mode, prompt,
        res["media_url"], res.get("thumb_url", ""),
        params=body.get("params") or {},
    )
    creation["provider"] = res["provider"]
    return web.json_response(creation)


async def api_studio_upload(request: web.Request) -> web.Response:
    """POST /api/studio/upload — accept a multipart image, store privately."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "image":
        return web.json_response({"error": "multipart field 'image' required"}, status=400)
    data = await field.read()
    if not data:
        return web.json_response({"error": "empty upload"}, status=400)
    if len(data) > 15 * 1024 * 1024:
        return web.json_response({"error": "image too large (15MB max)"}, status=413)
    # Sniff content type from filename
    fname = (field.filename or "").lower()
    ext = ".png" if fname.endswith(".png") else ".jpg" if fname.endswith(".jpg") or fname.endswith(".jpeg") else ".png"
    url = st._save_media(data, ext)
    return web.json_response({"url": url})


async def api_studio_creations(request: web.Request) -> web.Response:
    """GET /api/studio/creations — the user's private gallery."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    limit = int(request.query.get("limit", "60") or 60)
    return web.json_response({"creations": st.list_creations(user_id, limit)})


async def api_studio_share(request: web.Request) -> web.Response:
    """POST /api/studio/share/{id} — toggle public sharing of a creation.

    Body: {is_public: bool}
    """
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    cid = int(request.match_info.get("id", "0"))
    try:
        body = await request.json()
        is_public = bool(body.get("is_public", False))
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    rec = st.set_public(cid, user_id, is_public)
    if rec is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(rec)


async def api_studio_delete(request: web.Request) -> web.Response:
    """DELETE /api/studio/creations/{id} — remove a creation."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    cid = int(request.match_info.get("id", "0"))
    if not st.delete_creation(cid, user_id):
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({"ok": True})


async def api_studio_chat(request: web.Request) -> web.Response:
    """POST /api/studio/chat — chat via surp's own gateway free tier.

    The studio chat is treasury-sponsored (surp/free) so users can chat
    without a wallet. Body: {messages: [{role, content}], model?: str}
    model accepts surp/free (default), surp/free-coding, surp/free-fast.
    """
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    messages = body.get("messages") or []
    if not messages or not isinstance(messages, list):
        return web.json_response({"error": "messages required"}, status=400)
    # Chat model selector: only treasury-sponsored free routes are offered
    # (the studio chat must not burn paid credits or require x402).
    model = str(body.get("model", "surp/free") or "surp/free")
    free_class_map = {
        "surp/free": "chat",
        "surp/free-coding": "coding",
        "surp/free-fast": "fast",
        "surp/srup-free": "chat",
    }
    free_class = free_class_map.get(model)
    if free_class is None:
        return web.json_response(
            {"error": "studio chat supports free routes only: surp/free, surp/free-coding, surp/free-fast"},
            status=400,
        )
    client_ip = request.headers.get("X-Real-IP") or request.remote or "studio"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": min(int(body.get("max_tokens", 500) or 500), 1000),
        "stream": False,
    }
    try:
        markets = await GCACHE.get()
    except Exception:
        markets = []
    try:
        resp = await _serve_free_completion(request, payload, markets, client_ip, free_class=free_class)
        # _serve_free_completion returns an aiohttp Response — read its body.
        data = json.loads(resp.body) if isinstance(resp.body, (bytes, str)) else resp.body
        return web.json_response(data)
    except Exception as e:
        log.error(f"studio chat failed: {e}")
        return web.json_response({"error": f"chat failed: {e}"}, status=502)


async def studio_media(request: web.Request) -> web.Response:
    """GET /studio/media/{name} — serve a stored creation (private-by-default)."""
    name = request.match_info.get("name", "")
    data = st._load_media(name)
    if data is None:
        return web.Response(status=404)
    ct = "image/svg+xml" if name.endswith(".svg") else "image/png" if name.endswith(".png") else "image/jpeg"
    return web.Response(body=data, content_type=ct, headers={"Cache-Control": "private, max-age=3600"})


async def page_studio_share(request: web.Request) -> web.Response:
    """GET /studio/share/{token} — public view of a shared creation."""
    token = request.match_info.get("token", "")
    rec = st.get_public(token)
    if rec is None:
        content = "<h1>Not found</h1><p class='dim'>This creation is private or does not exist.</p>"
    else:
        kind = rec["kind"]
        media = f"<video src='{rec['media_url']}' controls style='max-width:100%;border-radius:8px;'></video>" if kind == "video" else f"<img src='{rec['media_url']}' style='max-width:100%;border-radius:8px;' alt=''/>"
        content = f"""
<h1>shared creation</h1>
<p class="dim">{rec['mode'].upper()} · {rec['kind']}</p>
{media}
<pre>{rec['prompt']}</pre>
"""
    html = _render_html(content, "/studio/share")
    return web.Response(text=html, content_type="text/html")


async def page_app(request: web.Request) -> web.Response:
    """React SPA for user login + embedded wallet creation (Privy)."""
    index_path = os.path.join(os.path.dirname(__file__), "frontend", "dist", "index.html")
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
        return web.Response(text=html, content_type="text/html")
    except FileNotFoundError:
        return web.Response(text="app not built — run npm run build in frontend/", status=503)


async def app_static(request: web.Request) -> web.Response:
    """Serve built frontend assets (JS/CSS) from frontend/dist/assets/."""
    asset_path = request.match_info.get("path", "")
    # Security: normalize + reject path traversal
    safe = os.path.normpath(asset_path).lstrip("/")
    if ".." in safe or safe.startswith("/"):
        return web.Response(status=404)
    full = os.path.join(os.path.dirname(__file__), "frontend", "dist", "assets", safe)
    if not os.path.isfile(full):
        return web.Response(status=404)
    ct = "application/javascript"
    if safe.endswith(".css"):
        ct = "text/css"
    elif safe.endswith(".svg"):
        ct = "image/svg+xml"
    elif safe.endswith(".png"):
        ct = "image/png"
    with open(full, "rb") as f:
        return web.Response(body=f.read(), content_type=ct, headers={"Cache-Control": "public, max-age=86400"})


# ─── User account API (Privy-authenticated) ──────────────────────────────────


def _auth_user(request: web.Request) -> str | None:
    """Extract + verify the Privy access token from the request. Returns user id."""
    auth = request.headers.get("Authorization", "")
    return ua.get_user_id_from_request(auth)


async def api_user_me(request: web.Request) -> web.Response:
    """GET /api/user/me — current user's wallet, balances, and basic info."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    user = ua.get_user(user_id)
    if not user:
        return web.json_response({"error": "user not found"}, status=404)
    balances = ua.get_user_balance(user_id)
    return web.json_response({
        "user_id": user_id,
        "wallet_address": user.get("wallet_address", ""),
        "email": user.get("email", ""),
        "balances": balances,
    })


async def api_user_balances(request: web.Request) -> web.Response:
    """GET /api/user/balances — live ETH + USDC balance for the user's wallet."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    return web.json_response(ua.get_user_balance(user_id))


async def api_user_dashboard(request: web.Request) -> web.Response:
    """GET /api/user/dashboard — aggregate stats for the dashboard."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    stats = ua.get_dashboard_stats(user_id)
    user = ua.get_user(user_id)
    stats["wallet_address"] = user.get("wallet_address", "") if user else ""
    stats["balances"] = ua.get_user_balance(user_id) if user else {}
    return web.json_response(stats)


async def api_user_usage(request: web.Request) -> web.Response:
    """GET /api/user/usage — paginated usage records (lifetime saved page)."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    limit = min(int(request.query.get("limit", "100")), 500)
    offset = int(request.query.get("offset", "0"))
    records = ua.get_usage(user_id, limit, offset)
    return web.json_response({"usage": records, "limit": limit, "offset": offset})


async def api_user_activity(request: web.Request) -> web.Response:
    """GET /api/user/activity — recent activity (last 50 calls, instant updates)."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    records = ua.get_usage(user_id, limit=50, offset=0)
    return web.json_response({"activity": records})


async def api_user_apikeys(request: web.Request) -> web.Response:
    """GET /api/user/api-keys — list; POST — create (returns plaintext key ONCE)."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)

    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        name = str(body.get("name", ""))[:100]
        budget = int(body.get("budget_cents", 0))
        if budget < 0:
            return web.json_response({"error": "budget must be >= 0"}, status=400)
        result = ua.create_api_key(user_id, name, budget)
        if not result:
            return web.json_response({"error": "failed to create key"}, status=500)
        return web.json_response({
            "key": result["key"],
            "key_id": result["key_id"],
            "name": result["name"],
            "budget_cents": result["budget_cents"],
            "warning": "This key will only be shown once. Copy it now — you won't see it again.",
        })

    # GET — list keys (no plaintext)
    keys = ua.list_api_keys(user_id)
    return web.json_response({"api_keys": keys})


async def api_user_apikey_delete(request: web.Request) -> web.Response:
    """DELETE /api/user/api-keys/{key_id} — revoke an API key."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    key_id = request.match_info.get("key_id", "")
    if ua.delete_api_key(user_id, key_id):
        return web.json_response({"deleted": key_id})
    return web.json_response({"error": "not found or not owned"}, status=404)


async def api_user_withdraw(request: web.Request) -> web.Response:
    """POST /api/user/withdraw — initiate a USDC withdrawal.

    Body: { "to": "0x...", "amount": "1.50" }
    The gateway signs and broadcasts a transferFrom (EIP-3009) from the user's
    embedded wallet to the destination. Requires the user's wallet to have
    approved the gateway or have sufficient balance + gas.
    """
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    to_addr = str(body.get("to", "")).strip()
    amount = body.get("amount", "0")
    if not to_addr.startswith("0x") or len(to_addr) != 42:
        return web.json_response({"error": "invalid destination address"}, status=400)
    try:
        amount_usdc = float(amount)
    except (TypeError, ValueError):
        return web.json_response({"error": "invalid amount"}, status=400)
    if amount_usdc <= 0:
        return web.json_response({"error": "amount must be > 0"}, status=400)

    # Check the user has sufficient balance
    user = ua.get_user(user_id)
    if not user or not user.get("wallet_address"):
        return web.json_response({"error": "no wallet found"}, status=400)
    balances = ua.get_wallet_balances(user["wallet_address"])
    if balances.get("usdc_atomic", 0) < int(amount_usdc * 1e6):
        return web.json_response({"error": "insufficient USDC balance"}, status=400)

    # The actual on-chain withdrawal requires a signed EIP-3009 authorization
    # from the user's wallet. The frontend (Privy embedded wallet) signs it,
    # then the gateway broadcasts. For now, return the unsigned payload for the
    # frontend to sign + the gateway to relay.
    return web.json_response({
        "status": "pending_signature",
        "message": "Sign the transaction in your wallet to withdraw",
        "to": to_addr,
        "amount_usdc": amount_usdc,
        "amount_atomic": int(amount_usdc * 1e6),
        "wallet_address": user["wallet_address"],
    })


async def api_user_add_funds(request: web.Request) -> web.Response:
    """GET /api/user/add-funds — return deposit address + instructions."""
    user_id = _auth_user(request)
    if not user_id:
        return web.json_response({"error": "unauthorized"}, status=401)
    user = ua.get_user(user_id)
    if not user or not user.get("wallet_address"):
        return web.json_response({"error": "no wallet found"}, status=400)
    return web.json_response({
        "deposit_address": user["wallet_address"],
        "network": "Base",
        "token": "USDC",
        "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "instructions": [
            "Copy your surp wallet address above.",
            "From your external wallet (MetaMask, Coinbase Wallet, etc.), send USDC on the Base network to this address.",
            "Funds typically arrive in under 10 seconds.",
            "Your balance updates automatically — refresh this page after sending.",
        ],
    })



async def api_benchmarks(request: web.Request) -> web.Response:
    """GET /api/benchmarks — verified output TPS/TTFT benchmark data."""
    model = request.query.get("model", "").strip()
    if model:
        return web.json_response({
            "summary": mb.summary(model),
            "runs": mb.recent_runs(model, int(request.query.get("limit", "20"))),
        })
    return web.json_response({
        "ranked": mb.ranked(),
        "methodology": {
            "output_tps": "completion_tokens / generation_seconds (first token to last)",
            "ttft": "request submission to first output token",
            "throughput_value": "p50_output_tps * tokens_per_dollar",
            "source": "real streaming requests through surp; no vendor claims",
        },
    })


async def api_health(request: web.Request) -> web.Response:
    """GET /api/health-board — per-model TPS, latency, failure rate, ranking."""
    return web.json_response({
        "ranked": ph.all_models(),
        "conversion": fm.conversion_stats(),
        "free_usage": fm.live_stats(),
        "window_seconds": ph.WINDOW_SECONDS,
        "note": "Surplus Intelligence's marketplace dashboard does not expose TPS, latency, or failure rates. surp measures these directly.",
    })


async def page_keyword(request: web.Request) -> web.Response:
    """Keyword-targeted landing pages (x402, x402 LLM API, cheapest LLM API, ...)."""
    path = request.path
    page = lp.KEYWORD_PAGES.get(path)
    if page is None:
        return web.Response(text=_render_html("<h1>not found</h1>", "/"), content_type="text/html", status=404)
    html = _HTML_BASE.replace("__CONTENT__", page["content"])
    html = html.replace("__TITLE__", page["title"])
    html = html.replace("__DESC__", page["desc"])
    html = html.replace("__PATH__", path)
    # Article schema for the educational page
    import json as _json
    if path == "/x402":
        jsonld = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": "What is x402? — The AI Agent Payment Protocol, Explained",
            "description": page["desc"],
            "author": {"@type": "Organization", "name": "surp.ivc.lol"},
            "publisher": {"@type": "Organization", "name": "surp.ivc.lol"},
        }
        html = html.replace("__JSONLD__", _json.dumps(jsonld))
    return web.Response(text=html, content_type="text/html")


_404_CONTENT = r"""
<h1>404 — page not found</h1>
<p class="dim prompt">cd / && ls</p>
<p>That route doesn't exist. Try one of these:</p>
<p>
  <a href="/">home</a> &middot;
  <a href="/docs">docs</a> &middot;
  <a href="/connect">connect your hermes</a> &middot;
  <a href="/builder">combo builder</a> &middot;
  <a href="/playground">playground</a> &middot;
  <a href="/about">about</a>
</p>
"""


async def serve_robots(request: web.Request) -> web.Response:
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /v1/\n\n"
        "Sitemap: https://surp.ivc.lol/sitemap.xml\n"
    )
    return web.Response(text=body, content_type="text/plain")


async def serve_sitemap(request: web.Request) -> web.Response:
    import time as _time
    lastmod = _time.strftime("%Y-%m-%d", _time.gmtime())
    pages = ["/", "/docs", "/connect", "/builder", "/about", "/status", "/dashboard", "/playground", "/top", "/find", "/compare", "/models", "/free-models", "/health", "/performance", "/svi", "/features", "/auction", "/app", "/cache", "/proposal", "/token-gating", "/x402", "/x402-llm-api", "/x402-gateway", "/pay-per-request-llm-api", "/cheapest-llm-api"]
    urls = ""
    for p in pages:
        priority = "1.0" if p == "/" else "0.8" if p in ("/docs", "/connect") else "0.6"
        changefreq = "daily" if p == "/" else "weekly"
        urls += "  <url><loc>https://surp.ivc.lol%s</loc><lastmod>%s</lastmod><changefreq>%s</changefreq><priority>%s</priority></url>\n" % (p, lastmod, changefreq, priority)
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>' % urls
    return web.Response(text=body, content_type="application/xml")


async def page_404(request: web.Request) -> web.Response:
    html = _render_html(_404_CONTENT, "/")
    return web.Response(text=html, content_type="text/html", status=404)


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", page_home)
    app.router.add_get("/docs", page_docs)
    app.router.add_get("/about", page_about)
    app.router.add_get("/status", page_status)
    app.router.add_get("/dashboard", page_dashboard)
    app.router.add_get("/connect", page_connect)
    app.router.add_get("/builder", page_builder)
    app.router.add_get("/playground", page_playground)
    app.router.add_get("/api/combos", api_combos)
    app.router.add_get("/api/combos/custom", api_custom_list)
    app.router.add_post("/api/combos/custom", api_custom_create)
    app.router.add_get("/api/combos/custom/{slug}", api_custom_get)
    app.router.add_get("/api/combos/history", api_combo_history)
    app.router.add_get("/api/models", api_models_catalog)
    app.router.add_get("/api/stats", api_global_stats)
    app.router.add_get("/api/rewards", api_reward_balance)
    app.router.add_get("/api/health", api_health)
    app.router.add_post("/api/keys/create", api_keys_create)
    app.router.add_get("/api/keys/balance", api_keys_balance)
    app.router.add_get("/api/dashboard", api_dashboard_data)
    app.router.add_get("/models", page_models_index)
    app.router.add_get("/models/{slug}", page_model_detail)
    app.router.add_get("/compare", page_compare)
    app.router.add_get("/find", page_find)
    app.router.add_get("/top", page_top)
    app.router.add_get("/api/compare", api_compare)
    app.router.add_get("/api/recommend", api_recommend)
    app.router.add_get("/v1/models", api_combos)  # same shape, different route
    app.router.add_post("/v1/chat/completions", chat_completions)
    # Catch-all 404 for anything unmatched — must be registered last
    app.router.add_get("/robots.txt", serve_robots)
    app.router.add_get("/og-image.png", lambda r: web.FileResponse("/root/.hermes/surp-router/static/og-image.png"))
    app.router.add_get("/miniapp", page_miniapp)
    app.router.add_get("/cache", page_cache)
    app.router.add_get("/proposal", page_proposal)
    app.router.add_get("/api/votes", api_vote_results)
    app.router.add_post("/api/vote", api_cast_vote)
    app.router.add_get("/token-gating", page_token_gating)
    app.router.add_get("/free-models", page_free_models)
    app.router.add_get("/api/free-models", api_free_stats)
    app.router.add_post("/api/free-key", api_free_key_create)
    app.router.add_get("/health", page_health_board)
    app.router.add_get("/features", page_features)
    app.router.add_get("/auction", page_auction)
    app.router.add_get("/performance", page_performance)
    app.router.add_get("/svi", page_svi)
    app.router.add_get("/api/svi", api_svi)
    app.router.add_post("/api/svi/benchmark", api_svi_submit)
    # Studio — all-in-one AI creative workspace
    app.router.add_get("/api/studio/status", api_studio_status)
    app.router.add_post("/api/studio/generate", api_studio_generate)
    app.router.add_post("/api/studio/upload", api_studio_upload)
    app.router.add_get("/api/studio/creations", api_studio_creations)
    app.router.add_post("/api/studio/share/{id}", api_studio_share)
    app.router.add_delete("/api/studio/creations/{id}", api_studio_delete)
    app.router.add_post("/api/studio/chat", api_studio_chat)
    app.router.add_get("/studio/media/{name}", studio_media)
    app.router.add_get("/studio/share/{token}", page_studio_share)
    app.router.add_get("/app", page_app)
    app.router.add_get("/app/assets/{path:.*}", app_static)
    # User account API (Privy-authenticated)
    app.router.add_get("/api/user/me", api_user_me)
    app.router.add_get("/api/user/balances", api_user_balances)
    app.router.add_get("/api/user/dashboard", api_user_dashboard)
    app.router.add_get("/api/user/usage", api_user_usage)
    app.router.add_get("/api/user/activity", api_user_activity)
    app.router.add_get("/api/user/api-keys", api_user_apikeys)
    app.router.add_post("/api/user/api-keys", api_user_apikeys)
    app.router.add_delete("/api/user/api-keys/{key_id}", api_user_apikey_delete)
    app.router.add_get("/api/user/add-funds", api_user_add_funds)
    app.router.add_post("/api/user/withdraw", api_user_withdraw)
    app.router.add_get("/api/benchmarks", api_benchmarks)
    app.router.add_get("/api/health-board", api_health)
    app.router.add_get("/api/feedback", api_feedback_list)
    app.router.add_post("/api/feedback", api_feedback_submit)
    app.router.add_post("/api/feedback/upvote", api_feedback_upvote)
    app.router.add_get("/x402", page_keyword)
    app.router.add_get("/x402-llm-api", page_keyword)
    app.router.add_get("/x402-gateway", page_keyword)
    app.router.add_get("/pay-per-request-llm-api", page_keyword)
    app.router.add_get("/cheapest-llm-api", page_keyword)
    app.router.add_get("/.well-known/farcaster.json", serve_farcaster_manifest)
    app.router.add_static("/static", "/root/.hermes/surp-router/static")
    app.router.add_get("/sitemap.xml", serve_sitemap)
    app.router.add_route("*", "/{tail:.*}", page_404)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=20130)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("surp.gateway")
    _init_x402()
    log.info(f"starting surp gateway on {args.host}:{args.port}")
    web.run_app(build_app(), host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
