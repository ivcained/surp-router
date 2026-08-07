"""Cache-affinity auction explainer page — the ad-network model for cached inference."""

TITLE = "Cache-Affinity Auction — Why Orderbook Pricing Fails for Cached Inference | surp.ivc.lol"
DESC = ("Why cached inference is an ad-network Dutch auction, not an orderbook "
        "commodity. Prompt prefixes are cookies; providers with warm KV cache "
        "bid lower to win fills; latency verifies honesty. The market design "
        "surp is building.")


def content(affinity_stats: dict) -> str:
    return f"""
<h1>cache-affinity auction</h1>
<p class="dim prompt">why cached inference is an ad network, not an orderbook</p>

<p>The Surplus Intelligence marketplace uses an <b>orderbook</b>: providers list prices per million tokens, buyers pay the cheapest listing. That's the right model for <i>unused capacity</i> — GPU hours are a commodity. But it's the <b>wrong model for cached inference</b>, and here's why.</p>

<div class="warn"><b>the core problem:</b> An orderbook prices the <i>listing</i>, not the <i>fill</i>. Two providers listing at $0.01/M are indistinguishable on the orderbook — even if one is serving 10K fresh tokens (true cost ~$0.10) and the other is serving the same 10K tokens with 8K already in KV cache (true cost ~$0.02). The cached provider pockets 5x margin. The orderbook <i>cannot surface this difference</i> because it doesn't know which provider has which prefix cached.</p></div>

<h2>the ad-network mapping</h2>
<p>Cached inference behaves exactly like programmatic advertising. The mapping is precise:</p>
<table>
<thead><tr><th>ad network</th><th>surp cache auction</th></tr></thead>
<tbody>
<tr><td>cookie / user data</td><td>prompt prefix hash (SHA-256 of first N tokens)</td></tr>
<tr><td>DSP bid request</td><td>gateway broadcasts: "prefix hash X, Y output tokens, SLA Z"</td></tr>
<tr><td>DSP evaluates inventory + data match</td><td>provider checks KV cache for prefix X</td></tr>
<tr><td>DSP bids based on match rate</td><td>provider bids based on cached-token fraction</td></tr>
<tr><td>second-price (Vickrey) auction</td><td>lowest bid wins, pays second-lowest</td></tr>
<tr><td>win/loss + latency feedback</td><td>wall-clock latency reveals true cache state</td></tr>
<tr><td>cookie fraud</td><td>cache-state fraud (claiming cache hit when fresh)</td></tr>
</tbody>
</table>

<h2>why prompts are cookies, not secrets</h2>
<p>The critical insight: <b>the prompt prefix is a disclosed signal, not a secret.</b> The gateway hashes the prefix (system prompt + first chunk of user message) into a 16-character fingerprint. This is exactly like a cookie ID in ad tech:</p>
<ul style="margin-left:20px;line-height:1.8;">
<li><b>Deterministic:</b> same prompt → same hash (enables affinity tracking)</li>
<li><b>Private:</b> the hash cannot be reversed to recover the prompt (no plaintext leakage)</li>
<li><b>Disclosed:</b> the gateway publishes the hash in the bid request so providers can check their cache</li>
<li><b>Stable:</b> only the first 512 chars of user content are hashed, so tail variations don't break affinity</li>
</ul>
<p>Providers who have prefix X warm in their KV cache <i>should</i> bid lower to win the fill — and they <i>want</i> to, because their marginal cost is near-zero. The orderbook prevents this price discovery from happening.</p>

<h2>the verification layer (post-bid honesty)</h2>
<p>Providers would lie about cache state ("yes I have 80% cached" when they have 0%). But we can verify: <b>a cache hit is 5-10x faster than fresh compute</b> for the same token count. surp already measures wall-clock latency per model via the <a href="/health">health board</a>. So we <i>infer</i> true cache state from the latency/token ratio, and penalize providers whose bids implied cache but whose latency proved fresh compute.</p>
<p>This is the ad-network "post-bid verification" layer — the same mechanism DSPs use to detect cookie fraud. A provider that discounts its bid (claiming cache) but serves with fresh-compute latency loses its affinity score, and future bids won't discount. The system is self-correcting.</p>

<h2>live cache-affinity stats</h2>
<div class="grid">
  <div class="card"><div class="num">{affinity_stats.get('total_samples', 0)}</div><div class="lbl">prefix→model samples (24h)</div></div>
  <div class="card"><div class="num">{affinity_stats.get('distinct_prefixes', 0)}</div><div class="lbl">distinct prefix hashes</div></div>
  <div class="card"><div class="num">{affinity_stats.get('distinct_models', 0)}</div><div class="lbl">models tracked</div></div>
  <div class="card"><div class="num">{affinity_stats.get('cache_hit_rate', 0)*100:.1f}%</div><div class="lbl">inferred cache hit rate</div></div>
</div>
<p class="dim">methodology: {affinity_stats.get('methodology', '')}</p>

<h2>how the auction works (proposed)</h2>
<ol style="margin-left:20px;line-height:1.8;">
<li><b>Request arrives:</b> gateway hashes the prompt prefix → 16-char fingerprint.</li>
<li><b>Bid request broadcast:</b> gateway publishes "prefix X, Y output tokens, SLA Z" to eligible providers.</li>
<li><b>Provider self-assessment:</b> each provider checks its KV cache for prefix X. If 80% is cached, marginal cost is ~20% of list → bid 40% below list.</li>
<li><b>Vickrey auction:</b> lowest bid wins, pays second-lowest bid. This incentivizes truthful bidding (game-theoretic optimum).</li>
<li><b>Fill + measurement:</b> winner serves the request; gateway measures wall-clock latency.</li>
<li><b>Post-bid verification:</b> if latency implies cache hit but the bid was low, affinity score increases (honest). If latency implies fresh compute but bid was low, affinity score decreases (dishonest).</li>
<li><b>Feedback loop:</b> future bids for that prefix use the updated affinity score to propose discounts.</li>
</ol>

<h2>what we built (gateway-side)</h2>
<p>The full auction requires provider-side cooperation (they must check KV cache and bid). SI's static orderbook doesn't support that yet. But surp has built the gateway-side infrastructure that makes the auction possible:</p>
<ul style="margin-left:20px;line-height:1.8;">
<li><b>Prefix hashing:</b> <code>cache_affinity.prefix_hash()</code> — SHA-256 of normalized prefix, 16 chars, no plaintext leakage.</li>
<li><b>Sample recording:</b> every non-streaming paid request records (prefix, model, tokens, latency) to the affinity DB.</li>
<li><b>Cache-state inference:</b> latency/token ratio determines if a fill was cached (< 200ms/1K tokens = cache hit).</li>
<li><b>Affinity scoring:</b> per (prefix, model) pair: hit rate over a 24h rolling window.</li>
<li><b>Proposed bids:</b> <code>cache_affinity.proposed_bid()</code> discounts list price up to 50% for models with high affinity — the DSP bid based on match rate.</li>
<li><b>Dishonesty detection:</b> if latency doesn't support a cache claim, no discount is applied. The bid stays at list.</li>
<li><b>Public stats:</b> live at <code>/api/stats</code> under <code>cache_affinity</code>.</li>
</ul>

<h2>what we still need (provider-side)</h2>
<p>The missing piece is provider cooperation. To run a real auction, Surplus Intelligence providers would need to:</p>
<ol style="margin-left:20px;line-height:1.8;">
<li><b>Accept bid requests:</b> receive prefix hashes and respond with bids, not just static listings.</li>
<li><b>Check KV cache:</b> inspect their own prefix cache for the hashed prefix and report match rate.</li>
<li><b>Submit truthful bids:</b> bid below list price proportional to cached fraction.</li>
<li><b>Accept Vickrey settlement:</b> be paid the second-lowest bid, not their own.</li>
</ol>
<p>This is a protocol change, not a code change. surp's gateway is ready to participate the moment SI exposes a bid-request endpoint. Until then, the affinity data we collect is the public good that proves the mechanism works.</p>

<h2>why this matters</h2>
<p>Orderbook pricing for cached inference <b>overcharges buyers and under-rewards cache creators</b>. A buyer asking the same prefix twice pays list price both times, even though the second fill cost the provider ~5x less. An auction would let the cached provider bid lower, win the fill, and pass savings to the buyer — while still earning more than the commodity margin. The <a href="/cache">exact-response cache</a> and <a href="/proposal">SRP reward ledger</a> are surp's current approximation of this; the affinity auction is the full vision.</p>

<p class="dim">related: <a href="/cache">cache-aware routing</a> · <a href="/health">provider health board</a> · <a href="/proposal">reward proposal</a> · <a href="/free-models">free models</a> · <a href="/docs">API docs</a></p>
"""
