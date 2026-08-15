"""surp system-design primer — architecture, trade-offs, and the v2 proposal.

Inspired by donnemartin/system-design-primer: we document how surp is
actually built (not a hypothetical), the load-bearing design decisions,
the numbers that matter, and a concrete next-version proposal with its
own trade-offs. Public page at /system-design.
"""

TITLE = "surp system design — how the cheapest LLM API works | architecture & v2 proposal"
DESC = ("How surp.ivc.lol is built: the x402 payment path, cache flywheel, "
        "routing engine, settlement, and fault isolation. Design decisions, "
        "back-of-envelope numbers, and a proposed v2 with batched settlement.")


def content(live: dict) -> str:
    stats = live.get("stats", {})
    total_req = stats.get("total_requests", 0)
    settled_usdc = stats.get("total_usdc_cents", 0) / 100
    reqs_24h = stats.get("requests_24h", 0)
    unique_wallets = stats.get("unique_payers", 0)

    return f"""<style>
.ds-cmp {{ border:1px solid var(--border-bright); border-left:3px solid var(--accent); padding:10px 14px; margin:8px 0; font-size:13px; }}
.ds-cmp b {{ color:var(--accent); }}
.ds-arrow {{ color:var(--fg-dim); font-family:var(--mono); font-size:12px; padding:2px 0 2px 18px; }}
.ds-num {{ color:var(--yellow); font-family:var(--mono); font-weight:700; }}
.ds-good {{ color:var(--accent); }} .ds-bad {{ color:var(--red); }} .ds-meh {{ color:var(--yellow); }}
table.ds {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
table.ds td, table.ds th {{ padding:6px 8px; border-bottom:1px solid var(--border); vertical-align:top; }}
</style>

<h1>system design</h1>
<p class="dim prompt">how surp.ivc.lol is built · what we chose · what we'd change · v2 proposal</p>

<div class="card" style="margin:14px 0;">
<h2>## tl;dr</h2>
<p>surp is an <b>x402-paywalled LLM gateway</b>: an OpenAI-compatible HTTP API where every request is a
USDC micro-payment settled on Base, and the model behind each request is chosen from the
live cheapest listing on the Surplus Intelligence marketplace. This page documents the real
architecture, the design decisions that make it cheap and honest, the numbers, and a proposed
<b>v2</b> that batches settlements so heavy users pay gas once, not per request.</p>
</div>

<h2>## the system at a glance</h2>
<div class="ds-cmp"><b>client</b> — curl / SDK / agent. Sends <code>POST /v1/chat/completions</code> with a combo like <code>surp/best-chat</code>.</div>
<div class="ds-arrow">│ x402: 402 → wallet signs EIP-3009 → retry with PAYMENT-SIGNATURE</div>
<div class="ds-cmp"><b>nginx :443</b> — TLS termination, rate limiting, CORS headers, static SPA.</div>
<div class="ds-arrow">▼</div>
<div class="ds-cmp"><b>gateway :20130</b> (aiohttp, single process) — the whole product lives here: auth,
routing, cache, payment verification, settlement, stats, health, SVI, Studio, metrics.</div>
<div class="ds-arrow">▼ resolve combo → cheapest live model</div>
<div class="ds-cmp"><b>resolver :20129</b> — proxies to <b>Surplus Intelligence</b> marketplace with our API key;
returns the live price and picks the cheapest model per combo.</div>
<div class="ds-arrow">▼</div>
<div class="ds-cmp"><b>sqlite stores</b> — combos.db (market snapshot), stats.db (usage), rewards.db (SRP ledger),
cache.db (exact responses), metrics.db (TTFT/TPS/F1000), user_accounts.db (Privy users, API keys), free_models.db.</div>

<h2>## the request lifecycle</h2>
<table class="ds">
<thead><tr><th>step</th><th>what happens</th><th>why it matters</th></tr></thead>
<tbody>
<tr><td>1</td><td>Client calls with <code>model: surp/best-chat</code>. Gateway checks the exact-response cache first.</td>
<td>Cache hits are <span class="ds-num">0.1¢</span> instead of 1¢ — the flywheel.</td></tr>
<tr><td>2</td><td>No payment header → gateway returns <b>402 + PAYMENT-REQUIRED</b> with the exact USDC amount
(spot price + 5% markup, floored at 1¢) and the EIP-712 domain.</td>
<td>Price is disclosed before the wallet signs. No surprise billing.</td></tr>
<tr><td>3</td><td>Client signs a <code>TransferWithAuthorization</code> (EIP-3009) with their wallet and retries with PAYMENT-SIGNATURE.</td>
<td>Per-request signature — no standing allowance, no unlimited-spend risk.</td></tr>
<tr><td>4</td><td>Gateway decodes the payload, verifies it, settles on Base via the PayAI facilitator (retry ×5 backoff), then streams the response.</td>
<td>Settle-then-serve: generation never runs unpaid.</td></tr>
<tr><td>5</td><td>Post-response: stats logged, health sample recorded, affinity hash recorded, metrics sample enqueued.</td>
<td>Every layer records to its own store, fault-isolated.</td></tr>
</tbody></table>

<h2>## load-bearing design decisions</h2>
<table class="ds">
<thead><tr><th>decision</th><th>choice</th><th>trade-off</th></tr></thead>
<tbody>
<tr><td>Payments</td><td class="ds-good">per-request EIP-3009 signatures, no approve-and-pull</td>
<td>safer (Surplus's own docs call this the better pattern) but every request needs a wallet sign; standing approvals save gas at unlimited-spend risk.</td></tr>
<tr><td>Routing</td><td class="ds-good">resolve combo → live cheapest on the marketplace + 5% fixed markup</td>
<td>we're a router, not a provider: no inventory risk, but margin is thin and depends on market liquidity.</td></tr>
<tr><td>Cache</td><td class="ds-good">exact-response cache at 0.1¢ + sticky routing (30% tolerance) preserving KV-prefix cache</td>
<td>massive cost savings on repeated prompts; cache only works for deterministic responses.</td></tr>
<tr><td>Data stores</td><td class="ds-meh">one sqlite file per concern, WAL mode</td>
<td>zero ops, perfect for this scale; single-writer contention becomes a ceiling at higher QPS (v2 addresses this).</td></tr>
<tr><td>Fault isolation</td><td class="ds-good">every side-effect wrapped: a locked DB or dead metrics writer never breaks a paid stream</td>
<td>metrics are best-effort by design; a crash in telemetry is invisible to the money path.</td></tr>
<tr><td>Deployment</td><td class="ds-meh">single Hetzner VPS, systemd, nginx</td>
<td>cheap and simple; single point of failure, single region (v2: multi-region or at least a standby).</td></tr>
<tr><td>Free tier</td><td class="ds-good">treasury-sponsored pool with per-class price ceilings and daily budgets</td>
<td>acquires users without a wallet; costs us real money, capped by budgets and conversion tracking.</td></tr>
</tbody></table>

<h2>## back-of-the-envelope</h2>
<table class="ds">
<thead><tr><th>number</th><th>value</th></tr></thead>
<tbody>
<tr><td>requests served (lifetime)</td><td class="ds-num">{total_req:,}</td></tr>
<tr><td>requests (24h)</td><td class="ds-num">{reqs_24h:,}</td></tr>
<tr><td>USDC settled</td><td class="ds-num">${settled_usdc:,.4f}</td></tr>
<tr><td>unique wallets</td><td class="ds-num">{unique_wallets:,}</td></tr>
<tr><td>cache hits</td><td class="ds-num">see /status (live cache metrics)</td></tr>
<tr><td>typical p50 output TPS</td><td class="ds-num">~100 (deepseek-v4-flash-0731, verified)</td></tr>
<tr><td>markup</td><td class="ds-num">500 bps (5%) over spot, 1¢ floor</td></tr>
<tr><td>cache-hit price</td><td class="ds-num">0.1¢ (90% off the floor)</td></tr>
</tbody></table>
<p class="dim" style="font-size:12px;">Numbers come from the live /api/stats feed; latency and TPS from the verified benchmark runner and the metrics feed.</p>

<h2>## what we'd NOT change</h2>
<ul style="margin-left:20px;line-height:1.8;">
<li><b>Per-request signatures.</b> The whole trust story is "your wallet signs exactly this amount, once." Standing allowances are a downgrade.</li>
<li><b>Fault isolation.</b> Telemetry must never gate money. Any v2 keeps metrics drop-on-full.</li>
<li><b>Price honesty.</b> The 402 discloses the price before signing; the quote endpoint shows the fee breakdown. This is the brand.</li>
<li><b>Separate stores.</b> One DB per concern has saved us from lock contention repeatedly; v2 replaces the mechanism (Redis), not the principle.</li>
</ul>

<h2>## v2 proposal — batched settlement</h2>
<div class="card" style="margin:14px 0;">
<h3>the problem</h3>
<p>Every request = one on-chain EIP-3009 transfer. At Base's current ~0.01 gwei that's
fractions of a cent, so it's fine today. But the moment a real agent makes thousands of
calls an hour, gas + wallet-sign latency become the bottleneck, and per-request signing
stops being "safer" and starts being "annoying." The fix is not a standing allowance — it's
<b>batching with a per-user credit ledger.</b></p>
</div>
<div class="card" style="margin:14px 0;">
<h3>the design</h3>
<ul style="margin-left:20px;line-height:1.8;">
<li><b>Credit ledger (v2):</b> each user has an off-chain USDC balance backed by on-chain collateral.
Requests deduct from the ledger instantly; the user tops up once (one tx, one signature) and
the gateway settles the net delta to/from their wallet in a single batched transfer.</li>
<li><b>Batched settlement queue:</b> instead of N transfers, the gateway accumulates credits and
settles when (a) 100 tx-worth accumulated, (b) 60s elapsed, or (c) the user requests a withdraw.
Settler signs one transfer for the whole batch.</li>
<li><b>Collateral floor:</b> the ledger can go negative up to a small floor (e.g. $5) so bursts
never block; the floor is enforced at withdraw time, not request time.</li>
<li><b>Opt-in:</b> per-request x402 stays the default for casual users; the ledger is a setting
for agents and heavy users. Both use the same EIP-3009 rails, so nothing about the security
model changes — the signature just moves from per-request to per-settlement.</li>
</ul>
</div>
<div class="card" style="margin:14px 0;">
<h3>why this beats the alternatives</h3>
<table class="ds">
<thead><tr><th>option</th><th>verdict</th></tr></thead>
<tbody>
<tr><td>standing allowance (Surplus SettlementV2 style)</td><td class="ds-bad">rejected — unlimited-spend risk, and their own docs want to move away from it</td></tr>
<tr><td>per-request x402 forever</td><td class="ds-meh">safe but doesn't scale to agent workloads; wallet-sign latency per call</td></tr>
<tr><td><b>credit ledger + batched settlement</b></td><td class="ds-good">one signature per batch, collateral-backed, opt-in, same EIP-3009 rails, no unlimited spend</td></tr>
</tbody></table>
</div>
<div class="card" style="margin:14px 0;">
<h3>v2 trade-offs, honestly</h3>
<ul style="margin-left:20px;line-height:1.8;">
<li class="ds-bad"><b>New trust surface:</b> the gateway now holds off-chain balances. Mitigation: balances are capped at the user's on-chain collateral, the ledger is auditable (every deduction maps to a settled tx), and withdraws are always possible.</li>
<li class="ds-meh"><b>Complexity:</b> a settlement queue, a ledger table, and a top-up flow. Real work, but contained — it reuses the existing payment verification path.</li>
<li class="ds-good"><b>What we keep:</b> price honesty (402 still quotes the exact per-request price), fault isolation (ledger writes never block requests), and per-request signing for everyone who wants it.</li>
</ul>
<p style="margin-top:10px;"><b>Status:</b> proposal only. Community vote at <a href="/proposal/srp">/proposal/srp</a> is about the SRP token; this v2 is the next design conversation after that. Want it sooner? Say so.</p>
</div>

<h2>## source & credits</h2>
<p class="dim" style="font-size:12px;">Structure inspired by
<a href="https://github.com/donnemartin/system-design-primer">donnemartin/system-design-primer</a>
(CC BY 4.0). The architecture documented here is the live system — read the code at
<a href="https://github.com/ivcained/surp-router">github.com/ivcained/surp-router</a>.</p>
"""
