"""Public cache-technology page for surp.ivc.lol."""

TITLE = "Cache-Aware LLM Routing — Cut AI Costs with Prefix and Response Caching | surp.ivc.lol"
DESC = ("How surp.ivc.lol combines provider prefix caching, sticky model routing, and privacy-preserving exact response caching to reduce LLM API cost and latency.")

CONTENT = r"""
<h1>cache-aware LLM routing</h1>
<p class="dim prompt">compute once. reuse safely. pay less.</p>

<p>LLM APIs waste money when they recompute the same context over and over. Agent tool definitions, system prompts, codebases, policies, and long conversation prefixes are often identical between requests. surp.ivc.lol now uses a <b>two-layer cache engine</b> to avoid that waste while preserving live marketplace pricing.</p>

<div class="grid">
  <div class="card"><div class="num">4-10x</div><div class="lbl">cheaper provider cache reads</div></div>
  <div class="card"><div class="num">90%</div><div class="lbl">discount on exact cache hits</div></div>
  <div class="card"><div class="num">15 min</div><div class="lbl">default exact-cache TTL</div></div>
  <div class="card"><div class="num">0</div><div class="lbl">raw prompts stored</div></div>
</div>

<h2>layer 1 — cache-aware sticky routing</h2>
<p>Provider-side prefix caching stores the model's computed state for the beginning of a prompt. Reusing a cached prefix cuts input cost by <b>-75% to -90%</b> and can drop time-to-first-token dramatically compared to processing fresh input.</p>

<p>But normal cheapest-price routing can destroy those savings: request one goes to model A, request two goes to model B, so model A's warm cache is useless. Our router now keeps a recently selected model when it remains within <b>30% of the current cheapest eligible model</b>. If the price gap grows beyond that, it switches back to the live cheapest option.</p>

<pre>request 1 → cheapest model A → provider writes prefix cache
request 2 → A is still within tolerance → reuse A → cache read
request 3 → model B becomes 40% cheaper → switch to B</pre>

<p>This balances two things that normally conflict: <b>marketplace arbitrage</b> and <b>cache locality</b>.</p>

<h2>layer 2 — exact response caching</h2>
<p>Some requests are completely repeatable: temperature zero, no tools, one response, and no streaming. For those requests, surp.ivc.lol stores the completed JSON response under a SHA-256 fingerprint of the full request.</p>

<p>When the exact request arrives again within the cache window:</p>
<ul style="margin-left:20px;line-height:1.8;">
  <li>The model is not called again.</li>
  <li>The response returns immediately.</li>
  <li>The request costs <b>$0.001</b> by default instead of the normal 1¢ floor.</li>
  <li>The response carries <code>X-Surp-Cache: HIT</code> and cache metadata.</li>
</ul>

<h2>privacy and safety boundaries</h2>
<p>We deliberately do <b>not</b> cache every request.</p>
<table><thead><tr><th>request type</th><th>exact response cache</th><th>sticky/provider cache</th></tr></thead><tbody>
<tr><td>temperature 0, no tools, non-streaming</td><td class="ok">eligible</td><td class="ok">eligible</td></tr>
<tr><td>streaming response</td><td>bypass</td><td class="ok">eligible</td></tr>
<tr><td>tool or agent call</td><td>bypass</td><td class="ok">eligible</td></tr>
<tr><td>creative/nonzero temperature</td><td>bypass</td><td class="ok">eligible</td></tr>
<tr><td>multiple candidates (<code>n &gt; 1</code>)</td><td>bypass</td><td class="ok">eligible</td></tr>
</tbody></table>

<p><b>Raw prompts are never persisted in the exact cache.</b> The database contains only a SHA-256 request fingerprint and the completed response. Responses expire automatically and the cache is size-bounded.</p>

<h2>how to get more cache hits</h2>
<ol style="margin-left:20px;line-height:1.8;">
  <li>Keep tool definitions and system instructions stable.</li>
  <li>Put static content first and changing user input last.</li>
  <li>Do not inject timestamps or random IDs into the reusable prefix.</li>
  <li>Use <code>temperature: 0</code> for deterministic tasks that may repeat.</li>
  <li>Use non-streaming mode when you want exact-response caching.</li>
</ol>

<h2>observe it yourself</h2>
<p>Every response reports its cache path:</p>
<pre>X-Surp-Cache: HIT | MISS | BYPASS
X-Surp-Cache-Type: exact-response
X-Surp-Routing: sticky-within-tolerance | live-cheapest</pre>

<p>The public <a href="/status">status page</a> shows exact-cache hit rate, tokens not recomputed, live cached answers, and sticky-route reuse. The same metrics are available as JSON at <code>GET /api/stats</code>.</p>

<h2>why this is different</h2>
<p>Most gateways optimize either price or caching. Pure cheapest-price routing jumps between models and loses warm prefixes. Pure session pinning ignores cheaper market offers. Our approach treats cached computation as an economic asset: keep it while its savings beat the price gap, then move when the market moves enough to justify losing it.</p>

<h2>the cache flywheel — rewards for creating shared value</h2>
<p>Cache hits create measurable economic value: the network avoids an upstream model call and keeps the difference. Instead of capturing all of that value, surp runs an experimental off-chain reward ledger called <b>SRP</b>:</p>
<ul style="margin-left:20px;line-height:1.8;">
  <li><b>Cache writer:</b> the payer who funds a deterministic MISS earns 1 SRP per token cached.</li>
  <li><b>Cache author:</b> when another agent reuses that entry, the original writer earns 2 SRP per token saved.</li>
  <li><b>Cache reader:</b> the agent that cooperatively reuses the cache earns 0.5 SRP per token saved.</li>
  <li><b>Revenue backing:</b> 50% of estimated gateway markup — and 50% of cache-hit revenue — is earmarked to a rebate pool.</li>
</ul>

<pre>more usage → more shared cache → lower network costs
     ↑                              ↓
SRP claim on revenue ← more rebates ← more margin</pre>

<p>SRP's estimated redemption value is <code>rebate pool ÷ outstanding SRP</code>. As protocol revenue enters the pool, existing SRP gains claim value. Heavy users who create useful cache entries can push their effective marginal cost toward zero over time.</p>

<div class="warn"><b>experimental, off-chain only.</b> SRP is currently a transparent accounting simulation, not an ERC-20, security, promise of profit, or transferable token. No automatic redemption or on-chain claim exists yet. The ledger is designed to produce real data before committing to a RevNet/Juicebox configuration.</div>

<h3>anti-farming guardrails</h3>
<ul style="margin-left:20px;line-height:1.8;">
  <li>Rewards are deduplicated per cache entry, role, and payer for one hour.</li>
  <li>Tool calls, streaming, creative sampling, and nondeterministic requests never enter the exact cache.</li>
  <li>Raw prompts are never stored — only SHA-256 fingerprints and completed responses.</li>
  <li>Cache readers still pay the discounted $0.001 micropayment, preventing free probing.</li>
  <li>Most author rewards only appear when somebody actually reuses the entry — write spam has little value.</li>
</ul>

<p>Live pool backing, SRP outstanding, holders, and implied value per SRP are visible on the <a href="/status">status page</a>. An agent can query its own balance with <code>GET /api/rewards?payer=0x...</code>.</p>

<h2>BYO guardrails — user-controlled routing</h2>
<p>You don't have to trust the default routing. Every request can carry its own constraints without changing the combo:</p>

<table><thead><tr><th>parameter</th><th>type</th><th>effect</th></tr></thead><tbody>
<tr><td><code>max_price_per_1m</code></td><td>float</td><td>Reject any model above this USD/1M-token ceiling. Returns 404 if nothing qualifies.</td></tr>
<tr><td><code>provider</code></td><td>string or array</td><td>Pin routing to one or more providers (allow-list). Cheapest within the set wins.</td></tr>
<tr><td><code>surp_bypass_cache</code></td><td>bool</td><td>Skip the exact-response cache entirely. Always calls the model, never returns a cached answer.</td></tr>
<tr><td><code>surp/strict/&lt;combo&gt;</code></td><td>model prefix</td><td>Disable sticky routing for this request. Always picks the live cheapest, never reuses a model for cache locality.</td></tr>
</tbody></table>

<p>Example: cheapest coder, but never above $0.50/1M and never from the cache:</p>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"surp/best-coding",
       "max_price_per_1m": 0.50,
       "surp_bypass_cache": true,
       "messages":[{"role":"user","content":"write a binary search"}],
       "max_tokens":100}'</pre>

<p>Example: cheapest chat, but only from a specific provider:</p>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"surp/best-chat",
       "provider": "deepseek",
       "messages":[{"role":"user","content":"hi"}],
       "max_tokens":50}'</pre>

<p>These guardrails compose. A request can pin a provider, cap the price, and bypass the cache at the same time. The <code>surp/strict/</code> prefix layers on top of any combo, including custom ones (<code>surp/strict/my/your-slug</code>).</p>

<p class="dim">related: <a href="/x402-llm-api">x402 LLM API</a> · <a href="/cheapest-llm-api">cheapest LLM API</a> · <a href="/x402-gateway">x402 gateway</a> · <a href="/docs">API docs</a> · <a href="/status">live cache metrics</a></p>
"""
