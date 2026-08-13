"""Public dated features/changelog page for surp.ivc.lol."""

TITLE = "Features & Updates — surp.ivc.lol Changelog"
DESC = ("Day-by-day progress on surp.ivc.lol: x402 LLM gateway, cache flywheel "
        "rewards, token-gated access, free AI models, provider health board, "
        "and SEO landing pages. See what shipped and when.")


# Milestones grouped by date (newest first). Each entry: (date, title, blurb).
# Drawn from the actual development history of this project.
MILESTONES: list[tuple[str, str, str]] = [
    ("2026-08-13", "investor pitch deck live at /pitch",
     "Apple-style 10-slide pitch deck for the Base Ecosystem Fund application, "
     "served at https://surp.ivc.lol/pitch. One idea per slide, no bullets, "
     "huge type on black with phosphor accents. Scrolls horizontally with "
     "snap, arrow keys, and nav dots; one wheel notch glides one slide with "
     "an eased animation; fixed 'back to surp' link. Print CSS exports a "
     "clean one-slide-per-page PDF."),
    ("2026-08-13", "merged community PR #1 — live TTFT/TPS/F1000 metrics feed",
     "Merged and deployed the first community contribution, authored by "
     "armchairfuturist-code (github.com/armchairfuturist-code), who asked "
     "ivcained to merge it. Lands metrics_core.py (StreamSample + "
     "compute_tps/compute_f1000_h with ai-speedometer parity), a write-behind "
     "SQLite metrics store in its own metrics.db (drop-on-full, WAL, 14-day "
     "raw retention), a stream tap that measures wall-clock TTFT to the first "
     "token, a token-gated SSE feed at /api/metrics/stream (Bearer + "
     "hmac.compare_digest), a live section on /dashboard (TTFT / TPS / F1000 "
     "cards, per-model table, canvas sparkline, SSE-over-fetch client), and "
     "optional strategy=f1000 routing that picks the best F1000 model from "
     "live samples with fallback to cheapest. Author credited in the README "
     "contributors section."),
    ("2026-08-12", "import-collision fixes — chat path restored",
     "Found and fixed two module-alias collisions that shadowed imports: "
     "'import studio as st' overrode stats (breaking every chat completion "
     "with AttributeError), and 'import performance_page as pp' overrode "
     "proposal_page (breaking /proposal). Studio re-aliased to stdo, "
     "performance_page to pfp, and a static scan now guards against any "
     "handler using a logger it never defined."),
    ("2026-08-11", "Surp Studio — all-in-one AI creative workspace",
     "Launched a full creative suite at /app/studio with chat, text-to-image, "
     "image-to-image, text-to-video, and a private gallery. Chat defaults to "
     "surp's treasury-sponsored free tier with a pick-your-model dropdown "
     "(surp/free, surp/free-coding, surp/free-fast); clicking the "
     "'ask anything' placeholder focuses the input. Image pane ships 8 "
     "one-click presets (photoreal, anime, pixel art, cyberpunk, watercolor, "
     "3D render, line art, oil painting) plus a comfy-style advanced panel "
     "(steps, guidance, seed, strength, aspect). Creations are private by "
     "default with opt-in sharing via unguessable token URLs."),
    ("2026-08-11", "studio generation on Surplus Intelligence (no FAL key needed)",
     "Rewired the studio's image/video generation to the Surplus Intelligence "
     "OpenAI-compatible API using the same key the resolver already uses — "
     "verified live that venice-flux-1.1-pro and 111 other image/video models "
     "generate real media. FAL stays as an optional fallback, mock last."),
    ("2026-08-11", "studio generation is x402-paywalled with 5% router markup",
     "Hard per-generation charging: studio image/video generation now runs the "
     "same two-phase x402 flow as chat. First call returns 402 with the exact "
     "USDC price (Surplus media-unit price + 5% router markup, floored at "
     "1¢), the wallet signs an EIP-3009 transfer, and the gateway verifies "
     "and settles on Base before generating. Zero-balance accounts can no "
     "longer generate for free — the quote includes live balance and the UI "
     "warns before signing. Creation records store paid_usdc and tx_hash."),
    ("2026-08-11", "Surplus SettlementV2-inspired fee transparency + retry",
     "Studied Surplus's on-chain settlement contract (0x0770...e6cc137, UUPS "
     "proxy with feeMultiplier/flatFee) and adopted the useful parts without "
     "copying the risky standing-allowance design: a public "
     "GET /api/studio/quote endpoint exposes the full fee breakdown (seller "
     "amount, markup bps, markup USD, flat fee, total) like their "
     "calculateFee view call, and settlement now retries with exponential "
     "backoff (5 attempts) instead of failing on the first transient error. "
     "Kept per-request signatures, which their own docs call the safer "
     "pattern."),
    ("2026-08-11", "SRP token contract proposal page + deploy vote",
     "Community proposal at /proposal/srp: should surp deploy SurpRewardToken "
     "(SRP) as a real ERC-20 on Base? Lists the contract design (OZ ERC20 + "
     "Permit + AccessControl + Pausable, 1B cap, immutable), benefits, risks, "
     "and the gas-fee analysis of standing approvals vs per-request "
     "signatures. Advisory vote with 4 options (deploy mainnet now / testnet "
     "first / wait / don't deploy), isolated from the existing flywheel "
     "proposal via multi-proposal voting with automatic DB migration."),
    ("2026-08-11", "Surp Value Index (SVI) — one score per model + your own routing lens",
     "Built a composite score (weighted geometric mean, 0-100) combining "
     "price, verified speed, and intelligence into a single SVI per model. "
     "Leaderboard at /svi with benchmark submission. Then added routing "
     "modes: send surp_mode=cost|value|speed|intel|balanced or custom "
     "surp_weights='0.3:0.4:0.3' and the gateway routes by your lens instead "
     "of the default — verified live across all modes, with the winning "
     "reason included in the 402 body."),
    ("2026-08-11", "'Phosphor Terminal' redesign — one UI language for the whole site",
     "Unified every page into a distinctive phosphor-terminal design "
     "language: pure-black background, phosphor-green accents, JetBrains "
     "Mono, CRT scanlines. The React dashboard got a sectioned left sidebar "
     "(account: overview/wallet/api keys/activity/usage; explore: all site "
     "pages with docs highlighted), active-page phosphor glow, mobile "
     "off-canvas drawer, and a top bar with wallet widget and logout."),
    ("2026-08-10", "Privy login + embedded wallets + full user dashboard",
     "Added real accounts: login with email/passkeys/Farcaster via Privy, an "
     "embedded wallet per user, and a full dashboard at /app — wallet page "
     "with QR code and add/withdraw USDC, API keys with per-key budgets and "
     "one-time-show secrets, live activity feed, lifetime usage table with "
     "Basescan tx links, and recharts graphs (total spend, marketplace "
     "savings, requests, token volume, top models, top API keys). Auth "
     "verifies Privy JWTs locally via JWKS with a fallback REST path; user "
     "API keys (surp_ prefix, SHA-256 hashed) authenticate Bearer requests."),
    ("2026-08-08", "verified LLM throughput benchmarks — real output TPS",
     "Built a live benchmark runner that streams real requests through surp and "
     "measures generation throughput (output tokens/second), TTFT, and "
     "throughput-per-dollar. Verified deepseek-v4-flash-0731 at p50 90.6 TPS "
     "(mean 100.2, max 122.3) at $0.0648/M, and deepseek-v4-flash at p50 94 TPS "
     "@ $0.0162/M. Public leaderboard at /performance, API at /api/benchmarks. "
     "Corrected the health board terminology: RPS (requests/second) is different "
     "from output TPS (generated tokens/second) — both are now measured."),
    ("2026-08-07", "cache-affinity auction — ad-network model for cached inference",
     "Identified the core market-design flaw: orderbooks price the listing, not "
     "the fill, so they can't surface cache-state differences between providers. "
     "Built the gateway-side infrastructure for an ad-network-style auction: "
     "privacy-preserving prefix hashing (like cookie IDs), latency-based cache "
     "inference (post-bid verification), Vickrey-style proposed bids that "
     "discount below list price for models with demonstrated cache affinity, and "
     "dishonesty detection via latency. Live explainer at /auction, data in "
     "/api/stats under cache_affinity."),
    ("2026-08-06", "free model health board + provider TPS/latency tracker",
     "Built a live provider health board that tracks TPS, p50/p95 latency, "
     "failure rate, and a composite health score for every model surp routes — "
     "metrics the Surplus Intelligence marketplace dashboard does not expose. "
     "Health scores feed back into routing: cheap-and-flaky loses to "
     "slightly-pricier-but-reliable."),
    ("2026-08-06", "per-class free routes: surp/free-coding + surp/free-fast",
     "Added two new treasury-sponsored free routes with their own price "
     "ceilings: surp/free-coding (filters to coder/codex models, $0.50/M cap) "
     "and surp/free-fast (filters to mini/nano/lite/flash, $0.05/M cap). Both "
     "gracefully fall back to the general free pool if no models qualify."),
    ("2026-08-06", "free-tier API keys with elevated budgets",
     "Heavy free users can now create a free-tier API key (POST /api/free-key) "
     "with elevated daily request and token budgets, replacing the default "
     "IP-based limits. Keys are validated in the free request path."),
    ("2026-08-06", "streaming support on the free path",
     "The free tier now accepts streaming requests with a conservative token "
     "buffer (200 tokens above the max output cap) so concurrent streams "
     "don't starve the global budget."),
    ("2026-08-06", "free-to-paid conversion tracking",
     "When a free user hits the budget wall, the gateway records a conversion "
     "event. Public stats show distinct free users, conversion count, rate, "
     "and which paid combos they upgraded to."),
    ("2026-08-06", "OmniRoute-inspired free-tier intelligence integration",
     "Integrated MIT-licensed free-tier catalog intelligence from "
     "github.com/diegosouzapw/OmniRoute: pool-deduped recurring token budgets, "
     "recurring vs one-time separation, uncapped-provider honesty, and ToS "
     "risk labels. Public inference remains treasury-sponsored, not "
     "proxy-resold third-party credentials."),
    ("2026-08-06", "genuinely free AI models — surp/free",
     "Launched surp/free: treasury-sponsored free LLM inference with no x402 "
     "payment, no API key, automatic live fallback across cheap liquid models, "
     "and strict daily/per-IP budgets. Live at /free-models with real-time "
     "budget tracking."),
    ("2026-08-05", "token-gated API access prototype",
     "Built an NFT/token-gated eligibility layer: callers with an X-Wallet "
     "header and sufficient token balance bypass x402 payment. Read-only "
     "balanceOf check, cached for 60s, fail-closed. Community feedback open "
     "at /token-gating."),
    ("2026-08-05", "cache flywheel reward ledger (SRP)",
     "Implemented off-chain SRP reward tokens: cache writers earn 1 SRP per "
     "cached token, cache authors earn 2 SRP per reused token, readers earn "
     "0.5 SRP. Backed by 50% of gateway markup earmarked to a rebate pool. "
     "Public vote on Juicebox/RevNet direction at /proposal."),
    ("2026-08-05", "cache-aware sticky routing + exact-response cache",
     "Two-layer cache engine: sticky routing keeps the last model if it stays "
     "within 30% of the live cheapest (preserves provider prefix cache), and "
     "exact-response cache returns identical deterministic responses at 0.1¢ "
     "instead of 1¢ (90% discount). Live at /cache."),
    ("2026-08-05", "SQLite database separation + fault isolation",
     "Split the monolithic combos.db into three separate files (combos, "
     "rewards, cache) to eliminate write-lock contention. All reward and "
     "cache operations are now wrapped in fault-isolating try/except so a "
     "locked DB never breaks a paid request."),
    ("2026-08-05", "dynamic per-page SEO titles + og tags",
     "Every page now has a unique, keyword-targeted <title> and matching "
     "og:title/og:description. The status page browser tab updates live with "
     "request count and cache hit rate."),
    ("2026-08-05", "5 SEO keyword landing pages",
     "Created /x402, /x402-llm-api, /x402-gateway, /pay-per-request-llm-api, "
     "and /cheapest-llm-api — each 1300-1700 words with FAQ schema, canonical "
     "tags, and 18-21 internal links. Sitemap grew to 17 URLs."),
    ("2026-08-05", "global notification banner",
     "Added a site-wide dismissible announcement banner that appears on every "
     "page, with localStorage persistence. Version-keyed so new announcements "
     "resurface for users who dismissed the previous one."),
    ("2026-08-05", "Farcaster mini app + JFS signing",
     "Built a Farcaster mini app at /miniapp with fc:miniapp meta tags, live "
     "ticker, and composeCast share button. Manifest signed with the user's "
     "FID 191554 JFS signature."),
    ("2026-08-05", "resolver sellability fix",
     "Fixed best-reasoning and best-fast returning model '?' by adding an "
     "is_sellable() filter that skips models with total_cap=0 or "
     "healthy_seller_count=0. All 15 combos now resolve to servable models."),
    ("2026-08-05", "nginx header split for x402 vs content",
     "Rewrote nginx config so only /api/ and /v1/ routes get x402 "
     "Access-Control-Expose-Headers; content pages, sitemap, and robots get "
     "clean headers. Resolved Google Search Console 'Sitemap could not be read'."),
    ("2026-08-05", "dashboard, API keys, combo history, rate limiting",
     "Added /dashboard wallet lookup, prepaid API key mode (Authorization: "
     "Bearer), combo history snapshots every 5 minutes, and IP sliding-window "
     "rate limiting (60 req/60s, fails open)."),
    ("2026-08-05", "animated terminal hero + mobile nav",
     "Homepage now has an animated terminal hero showing the full x402 cycle: "
     "curl → 402 → signing → settled → routed → code streams. Made nav "
     "mobile-friendly with flex-wrap and media queries."),
    ("2026-08-05", "ELI5, quick-start, 404 page, SEO meta",
     "Added an ELI5 section with 3 cards, a quick-start curl example, a themed "
     "404 page, meta description + OG/Twitter tags, and truncated the combo "
     "pool tables (128KB → 42KB homepage)."),
    ("2026-08-05", "x402 end-to-end payment cycle working",
     "Fixed 402 challenge header (PAYMENT-REQUIRED), inbound payment header "
     "(PAYMENT-SIGNATURE), and facilitator verification to use client-signed "
     "payload.accepted with EIP-712 domain. Full cycle verified: client signs "
     "→ gateway decodes → facilitator verifies → settles."),
    ("2026-08-05", "status page + /api/stats",
     "Added /status page and /api/stats JSON with total requests, 24h "
     "requests, USDC settled, unique wallets, system health, top combos, and "
     "cache metrics."),
    ("2026-08-05", "SQLite stats persistence",
     "Created stats.py with WAL-mode SQLite, 4 tables (requests, "
     "combo_snapshots, api_keys, rate_limits), thread-safe with busy_timeout. "
     "Also added rate-limit transaction leak fix (upsert + guaranteed rollback)."),
    ("2026-08-04", "Farcaster mini app + brand assets",
     "Generated brand assets (icon.png, hero.png, og-image.png), built the "
     "/miniapp page (424x695 modal, no nav/scanlines), and added "
     ".well-known/farcaster.json manifest."),
    ("2026-08-04", "FSB (Full Self Browsing) integration",
     "Installed fsb-mcp-server globally, added to Hermes config under "
     "mcp_servers, saved the FSB workflow skill, and verified the bridge on "
     "localhost:7225 (WS) + 127.0.0.1:7226 (HTTP)."),
    ("2026-08-04", "connect your Hermes button + dashboard JS fixes",
     "Added /connect route with a 3-step connect guide and yellow CTA on the "
     "homepage. Fixed dashboard JS ($ is not defined) and global link colors "
     "(was invisible dark blue)."),
    ("2026-08-04", "initial gateway + 15 combos live",
     "Stood up the x402-paywalled LLM gateway on aiohttp with 15 routing "
     "combos (best/pro × coding/reasoning/fast/vision/chat + aliases), served "
     "at https://surp.ivc.lol/ with HTTPS via Let's Encrypt."),
]


def _group_by_date() -> list[tuple[str, list[tuple[str, str]]]]:
    """Group milestones by date, newest first, preserving order within a date."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for date, title, blurb in MILESTONES:
        groups.setdefault(date, []).append((title, blurb))
    return sorted(groups.items(), key=lambda x: x[0], reverse=True)


def content() -> str:
    sections = []
    for date, items in _group_by_date():
        entries = ""
        for title, blurb in items:
            entries += (
                f"<div class='feature-entry'>"
                f"<h3>{title}</h3>"
                f"<p class='dim'>{blurb}</p>"
                f"</div>"
            )
        sections.append(f"<div class='feature-day'><h2>{date}</h2>{entries}</div>")

    return f"""
<h1>features &amp; updates</h1>
<p class="dim prompt">surp.ivc.lol changelog — what shipped and when.</p>

<p>This page tracks day-to-day progress on surp.ivc.lol: the x402-paywalled LLM gateway, cache flywheel rewards, token-gated access, free AI models, and the provider health board. Updates are newest first.</p>

<div class="warn"><b>this is a living project.</b> Features ship as they're ready, not on a fixed release schedule. If something breaks, it gets fixed the same day. Check <a href="/status">/status</a> for live system health, or <a href="/health">/health</a> for per-model TPS and latency.</p></div>

{''.join(sections)}

<h2>how to follow along</h2>
<ul style="margin-left:20px;line-height:1.8;">
<li><a href="/status">/status</a> — live request counts, cache hit rate, USDC settled, reward pool</li>
<li><a href="/health">/health</a> — per-model TPS, p50/p95 latency, failure rate, composite health score</li>
<li><a href="/free-models">/free-models</a> — live free-tier budget, eligible models, served models today</li>
<li><a href="/api/stats">/api/stats</a> — machine-readable version of everything above</li>
<li><a href="/proposal">/proposal</a> — vote on the cache flywheel reward direction</li>
<li><a href="/token-gating">/token-gating</a> — feedback on the NFT-gated access prototype</li>
</ul>

<p class="dim">related: <a href="/docs">API docs</a> · <a href="/cache">cache-aware routing</a> · <a href="/about">about</a></p>
"""
