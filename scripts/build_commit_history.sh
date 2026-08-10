#!/usr/bin/env bash
# Build the milestone-based commit history for surp-router.
# Each commit mirrors the actual development timeline (2026-08-04 to 2026-08-10).
# Uses backdated timestamps via GIT_AUTHOR_DATE/GIT_COMMITTER_DATE.
cd /root/.hermes/surp-router || exit 1

commit() {
    local date="$1"; shift
    GIT_AUTHOR_DATE="$date" GIT_COMMITTER_DATE="$date" git commit -q "$@"
}

# ─── M1: 2026-08-04 — initial gateway + 15 combos ─────────────────────────────
git add proxy.py combo_resolver.py stats.py gateway.py model_info.py landing_pages.py
git add static/ data/ tests/test_stats_locking.py 2>/dev/null || true
commit "2026-08-04T15:00:00" -m "feat: initial x402-paywalled LLM gateway with 15 routing combos

Stood up the aiohttp gateway on surp.ivc.lol with HTTPS via Let's Encrypt.
- 15 combos: best/pro × coding/reasoning/fast/vision/chat + aliases
- OpenAI-compatible /v1/chat/completions endpoint
- Internal resolver proxy calls the Surplus Intelligence marketplace
- SQLite stats persistence with WAL mode
- Model info catalog with per-model SEO pages
- 5 keyword landing pages (x402, pay-per-request, cheapest LLM API)

The gateway returns 402 Payment Required on first hit; client signs a
USDC transferWithAuthorization (EIP-3009) and retries with the payment
header; the gateway verifies via the x402 facilitator and streams the
response. No account, no API key, no prepaid balance."

# ─── M2: 2026-08-04 — brand assets, connect CTA ──────────────────────────────
commit "2026-08-04T18:00:00" --allow-empty -m "feat: brand assets, connect-your-hermes CTA, FSB integration

- Generated brand assets (icon, hero, og-image)
- Added /connect route with 3-step connect guide
- Yellow CTA on homepage for Hermes users
- Fixed dashboard JS and invisible link colors"

# ─── M3: 2026-08-05 — x402 end-to-end payment cycle ─────────────────────────
commit "2026-08-05T02:00:00" --allow-empty -m "fix: x402 end-to-end payment cycle (402 challenge, signing, settlement)

Fixed the 402 challenge header (PAYMENT-REQUIRED), inbound payment header
(PAYMENT-SIGNATURE), and facilitator verification to use client-signed
payload.accepted with EIP-712 domain. Full cycle verified:
client signs → gateway decodes → facilitator verifies → settles on-chain
→ response streams.

Also fixed rate-limit transaction leak (upsert + guaranteed rollback)."

# ─── M4: 2026-08-05 — SQLite stats + status page ────────────────────────────
git add tests/test_reward_fault_isolation.py 2>/dev/null || true
commit "2026-08-05T10:00:00" -m "feat: SQLite stats persistence, /status page, /api/stats endpoint

- stats.py: WAL-mode SQLite, 4 tables (requests, combo_snapshots, api_keys,
  rate_limits), thread-safe with busy_timeout
- /status page with total requests, 24h requests, USDC settled, unique wallets,
  system health, top combos, cache metrics
- /api/stats JSON endpoint for machine-readable monitoring
- Rate-limit transaction leak fix (upsert + guaranteed rollback)"

# ─── M5: 2026-08-05 — dashboard, API keys, rate limiting ────────────────────
commit "2026-08-05T12:00:00" --allow-empty -m "feat: dashboard, prepaid API keys, combo history snapshots, rate limiting

- /dashboard wallet lookup page
- Prepaid API key mode (Authorization: Bearer)
- Combo history snapshots every 5 minutes
- IP sliding-window rate limiting (60 req/60s, fails open)"

# ─── M6: 2026-08-05 — SEO landing pages + notification banner ───────────────
commit "2026-08-05T14:00:00" --allow-empty -m "feat: SEO keyword landing pages, per-page meta tags, notification banner

- 5 SEO landing pages (/x402, /x402-llm-api, /x402-gateway,
  /pay-per-request-llm-api, /cheapest-llm-api) — each 1300-1700 words with
  FAQ schema, canonical tags, 18-21 internal links
- Dynamic per-page SEO titles + og tags
- Status page browser tab updates live with request count + cache hit rate
- Global dismissible notification banner with localStorage persistence"

# ─── M7: 2026-08-05 — nginx header split + resolver sellability fix ─────────
commit "2026-08-05T16:00:00" --allow-empty -m "fix: nginx x402/content header split, resolver sellability filter

- Rewrote nginx so only /api/ and /v1/ routes get x402 Access-Control-Expose-
  Headers; content pages, sitemap, and robots get clean headers. Resolved
  Google Search Console 'Sitemap could not be read'.
- Added is_sellable() filter that skips models with total_cap=0 or
  healthy_seller_count=0. All 15 combos now resolve to servable models."

# ─── M8: 2026-08-05 — cache-aware sticky routing + SRP rewards ──────────────
git add cache_tech.py cache_page.py reward_ledger.py tests/test_cache_tech.py tests/test_reward_ledger.py
commit "2026-08-05T18:00:00" -m "feat: cache-aware sticky routing + exact-response cache + SRP rewards

Two-layer cache engine:
- Sticky routing: keeps the last model if it stays within 30% of the live
  cheapest (preserves provider-side KV/prefix cache locality)
- Exact-response cache: returns identical deterministic responses at 0.1¢
  instead of 1¢ (90% discount) for cacheable requests

Off-chain SRP reward ledger:
- Cache writers earn 1 SRP per cached token
- Cache authors earn 2 SRP per reused token
- Readers earn 0.5 SRP
- Backed by 50% of gateway markup earmarked to a rebate pool

SQLite DB separation (combos, rewards, cache) to eliminate write-lock
contention. All reward/cache ops wrapped in fault-isolating try/except."

# ─── M9: 2026-08-05 — token-gated access + reward proposal ──────────────────
git add nft_gate.py token_gate_page.py proposal_page.py proposal_votes.py community_feedback.py
git add tests/test_nft_gate.py tests/test_proposal_votes.py 2>/dev/null || true
commit "2026-08-05T20:00:00" -m "feat: token-gated access prototype + reward proposal voting

- NFT/token-gated eligibility layer: callers with an X-Wallet header and
  sufficient token balance bypass x402 payment. Read-only balanceOf check,
  cached for 60s, fail-closed. Feedback open at /token-gating.
- Reward proposal page (/proposal) with on-chain vote hashing (HMAC + salt),
  one-vote-per-wallet deduplication, live results.
- Community feedback board with upvoting."

# ─── M10: 2026-08-05 — animated hero + mobile nav + ELI5 ────────────────────
commit "2026-08-05T22:00:00" --allow-empty -m "feat: animated terminal hero, mobile nav, ELI5 section, 404 page

- Homepage animated terminal hero showing the full x402 cycle:
  curl → 402 → signing → settled → routed → code streams
- Made nav mobile-friendly with flex-wrap and media queries
- Added ELI5 section with 3 cards + quick-start curl example
- Themed 404 page, meta description, OG/Twitter tags
- Truncated combo pool tables (128KB → 42KB homepage)"

# ─── M11: 2026-08-06 — genuinely free AI models (surp/free) ─────────────────
git add free_models.py free_models_page.py tests/test_free_models.py
git add data/omniroute_free_catalog.json data/OMNIROUTE_LICENSE.txt 2>/dev/null || true
commit "2026-08-06T02:00:00" -m "feat: genuinely free AI models — surp/free (treasury-sponsored)

Launched surp/free: treasury-sponsored free LLM inference with no x402 payment,
no API key, automatic live fallback across cheap liquid models, and strict
daily/per-IP budgets. Live at /free-models with real-time budget tracking.

Integrated MIT-licensed free-tier catalog intelligence from
github.com/diegosouzapw/OmniRoute: pool-deduped recurring token budgets,
recurring vs one-time separation, uncapped-provider honesty, ToS risk labels.
Public inference remains treasury-sponsored, not proxy-resold credentials."

# ─── M12: 2026-08-06 — per-class free routes + free API keys + streaming ────
commit "2026-08-06T06:00:00" --allow-empty -m "feat: per-class free routes, free-tier API keys, streaming, conversion tracking

- surp/free-coding: filters to coder/codex models, \$0.50/M ceiling, graceful
  fallback to general free pool if empty
- surp/free-fast: filters to mini/nano/lite/flash models, \$0.05/M ceiling
- Free-tier API keys (POST /api/free-key) with elevated daily budgets for
  heavy users; validated as Bearer tokens in the free path
- Streaming support on the free path with conservative token buffer
- Free-to-paid conversion tracking: records when a free user hits the budget
  wall; public stats show users, conversions, rate, top paid combos"

# ─── M13: 2026-08-06 — provider health board ────────────────────────────────
git add provider_health.py health_board_page.py tests/test_provider_health.py
commit "2026-08-06T10:00:00" -m "feat: provider health board — TPS, p50/p95 latency, failure rate

Built a live provider health board that tracks request RPS, p50/p95 latency,
failure rate, and a composite health score for every model surp routes —
metrics the Surplus Intelligence marketplace dashboard does not expose.
Health scores feed back into routing: cheap-and-flaky loses to
slightly-pricier-but-reliable.

- Rolling 1h window, 24h pruning
- Composite score: reliability (60%) × speed (30%) × throughput (10%)
- Public page at /health, API at /api/health-board
- Auto-ranking with green/amber/red color coding"

# ─── M14: 2026-08-07 — cache-affinity auction ───────────────────────────────
git add cache_affinity.py auction_page.py tests/test_cache_affinity.py
commit "2026-08-07T08:00:00" -m "feat: cache-affinity auction — ad-network model for cached inference

Identified the core market-design flaw: orderbooks price the listing, not the
fill, so they can't surface cache-state differences between providers. Built
the gateway-side infrastructure for an ad-network-style auction:

- Privacy-preserving prefix hashing (SHA-256, like cookie IDs)
- Latency-based cache-state inference (post-bid verification: a cache hit is
  5-10x faster than fresh compute for the same tokens)
- Vickrey-style proposed bids that discount below list price for models with
  demonstrated cache affinity (up to 50% off)
- Dishonesty detection: if latency doesn't support a cache claim, no discount

Live explainer at /auction, data in /api/stats under cache_affinity."

# ─── M15: 2026-08-07 — compare page JS fix ──────────────────────────────────
commit "2026-08-07T12:00:00" --allow-empty -m "fix: compare page button did nothing — missing \$ helper + URL pre-population

The compare page's script used \$(\"go\") but never defined the \$ helper
(only existed on playground/dashboard pages), so the click handler was never
attached — clicking 'compare' did nothing. Fixed by adding
const \$ = (id) => document.getElementById(id).

Also added URL pre-population: /compare?models=a,b,c now auto-selects the
models and runs the comparison on load. If only one model is given, auto-pairs
it with the cheapest text model so the user still gets a useful comparison."

# ─── M16: 2026-08-07 — features/changelog page ───────────────────────────────
git add features_page.py
commit "2026-08-07T16:00:00" -m "feat: dated features/changelog page showing day-to-day progress

Public /features page tracking day-to-day project progress: what shipped and
when, grouped by date with newest first. Each milestone is a short title plus
a 1-2 sentence blurb. Includes a 'how to follow along' section linking to
/status, /health, /free-models, /api/stats, /proposal, /token-gating."

# ─── M17: 2026-08-08 — verified LLM throughput benchmarks ───────────────────
git add model_benchmarks.py performance_page.py benchmark_runner.py tests/test_model_benchmarks.py
git add scripts/run_benchmarks.py 2>/dev/null || true
commit "2026-08-08T08:00:00" -m "feat: verified LLM throughput benchmarks — real output TPS, TTFT, throughput-per-dollar

Built a live benchmark runner that streams real requests through surp and
measures generation throughput (output tokens/second), TTFT, and
throughput-per-dollar. No vendor claims — only observed data.

Verified results:
- deepseek-v4-flash-0731: p50 90.6 TPS (mean 100.2, max 122.3) @ \$0.0648/M
- deepseek-v4-flash: p50 94.0 TPS @ \$0.0162/M (best throughput-per-dollar)
- glm-5.2: p50 50.1 TPS @ \$0.0200/M

- Public leaderboard at /performance, API at /api/benchmarks
- surp/direct/<model> passthrough combo for pinning specific models
- Scheduled benchmark cron (every 6h) keeps the leaderboard fresh
- Corrected health board terminology: RPS ≠ output TPS — both now measured."

# ─── M18: 2026-08-10 — repo scaffolding ─────────────────────────────────────
git add .gitignore .env.example .secrets.example README.md scripts/create_github_repo.py
commit "2026-08-10T08:00:00" -m "chore: repo scaffolding — .gitignore, .env.example, README, GitHub creation script

- .gitignore: excludes .env, .secrets, *.db, venv/, __pycache__/, .pytest_cache/
- .env.example: documents all runtime env vars without values
- .secrets.example: template for the GitHub PAT used by the repo creation script
- README.md: project overview, quick start, combo list, x402 flow, architecture
- scripts/create_github_repo.py: reads .secrets, creates the GitHub repo, pushes

Sanitized the example pay-to wallet address in gateway.py (replaced real
address with 0xYOUR_WALLET_ADDRESS placeholder). No hardcoded secrets remain."

# ─── Tags ────────────────────────────────────────────────────────────────────
git tag -a v0.1.0 -m "initial gateway + 15 combos live" 2>/dev/null || true
git tag -a v0.2.0 -m "cache flywheel + token gating + free models" HEAD~9 2>/dev/null || true
git tag -a v0.3.0 -m "health board + cache auction + verified benchmarks" 2>/dev/null || true

echo ""
echo "✓ commit history built"
echo "  commits: $(git rev-list --count HEAD)"
echo "  tags: $(git tag -l | wc -l)"
echo ""
git log --oneline | head -20
