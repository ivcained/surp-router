#!/usr/bin/env python3
"""
Keyword-targeted landing pages for surp.ivc.lol.

Each page targets a specific keyword cluster with real content (not thin
landing pages): x402, x402 LLM API, x402 gateway, cheapest LLM API, and
pay-per-request LLM API. Pages carry FAQPage / Article structured data and
deep internal links so Google can crawl the whole site from them.

Rendered by gateway.py via _render_html with per-page SEO meta.
"""

# ──────────────────────────────────────────────────────────────────────────────
# /x402 — "what is x402" educational page (targets: x402, x402 protocol,
# x402 explained, AI agent payments, HTTP 402 payment required)
# ──────────────────────────────────────────────────────────────────────────────

X402_PAGE_TITLE = "What is x402? — The AI Agent Payment Protocol, Explained | surp.ivc.lol"
X402_PAGE_DESC = ("x402 is the payment protocol that uses HTTP 402 to charge for API calls. "
                  "Learn how x402 works, how AI agents pay per request in USDC, and how to use "
                  "an x402 LLM gateway for pay-per-request inference.")

X402_PAGE = """
<h1>what is x402?</h1>
<p class="dim prompt">man x402 | head -50</p>

<p><b>x402</b> is a payment protocol built on the HTTP <code>402 Payment Required</code> status code. It lets any web API — including <b>LLM APIs</b> — charge per request using <b>USDC on Base</b>, with no account, no API key, and no subscription. The machine (or agent) pays as it goes.</p>

<h2>the problem x402 solves</h2>
<p>APIs today are gated by API keys, subscriptions, and credit-card billing. That breaks down for <b>AI agents</b>: an agent shouldn't need a human to sign up for a plan before making one request. x402 turns payment into a protocol handshake the agent can complete itself — the server responds <code>402</code>, the client signs a USDC transfer, retries, and gets the answer. One request, one penny, done.</p>

<h2>how x402 works — the handshake</h2>
<pre>POST /v1/chat/completions   ← no payment header
HTTP/2 402 Payment Required  ← server asks for USDC
  X-Payment-Requirements: &lt;base64 price + pay-to + token&gt;

POST /v1/chat/completions   ← retry with signed EIP-3009 auth
  X-Payment: &lt;base64 signed transfer&gt;
HTTP/2 200 OK               ← verified + settled, response streams back</pre>
<p>That's the whole protocol. <b>EIP-3009</b> (<code>transferWithAuthorization</code>) lets the client sign an off-chain transfer that a facilitator submits on-chain — the client doesn't even need gas for a transaction, just USDC.</p>

<h2>why x402 is built for AI</h2>
<ul style="margin-left:20px;line-height:1.8;">
  <li><b>Micropayments work</b> — a request costs cents or fractions of a cent; no billing minimums, no Stripe fee floor.</li>
  <li><b>Agents self-serve</b> — no KYC, no signup, no API key provisioning. The wallet is the identity.</li>
  <li><b>Settlement is transparent</b> — every payment is an on-chain USDC transfer on Base, auditable by anyone.</li>
  <li><b>No subscription lock-in</b> — you pay for exactly what you use, per request.</li>
</ul>

<h2>x402 vs API keys vs subscriptions</h2>
<table><thead><tr><th></th><th>x402</th><th>API key</th><th>Subscription</th></tr></thead>
<tbody>
  <tr><td class="dim">setup</td><td>none — just a wallet</td><td>create key, manage secrets</td><td>sign up, add payment method</td></tr>
  <tr><td class="dim">billing</td><td>per request, on-chain</td><td>metered, invoiced</td><td>flat monthly</td></tr>
  <tr><td class="dim">agent-friendly</td><td>yes — fully autonomous</td><td>key management needed</td><td>human needed</td></tr>
  <tr><td class="dim">privacy</td><td>wallet address only</td><td>account tied to you</td><td>full account</td></tr>
  <tr><td class="dim">settlement</td><td>USDC on Base, auditable</td><td>card/ACH, opaque</td><td>card, opaque</td></tr>
</tbody></table>

<h2>using x402 to pay for LLM inference</h2>
<p>surp.ivc.lol is a working <b>x402 LLM gateway</b>: an OpenAI-compatible API where every request is paid with x402. You send <code>surp/best-chat</code> as the model, get a 402 with the exact USDC price, sign it with your wallet, and the cheapest model on the marketplace answers. <a href="/x402-llm-api">Read more about the x402 LLM API &raquo;</a></p>

<h2>faq</h2>
<div itemscope itemtype="https://schema.org/FAQPage">
<div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
  <h3 itemprop="name">What does x402 stand for?</h3>
  <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <div itemprop="text">x402 refers to HTTP status code 402 (Payment Required). The "x" marks it as an extension of the code into a full payment protocol.</div>
  </div>
</div>
<div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
  <h3 itemprop="name">What network does x402 settle on?</h3>
  <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <div itemprop="text">Most x402 implementations settle USDC on Base (EIP-3009 transfers), with Solana, Polygon, and other chains supported by various facilitators.</div>
  </div>
</div>
<div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
  <h3 itemprop="name">Do I need a crypto wallet to use x402?</h3>
  <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <div itemprop="text">Yes — the wallet holds USDC and signs the per-request authorization. There's no account, KYC, or API key, just the wallet.</div>
  </div>
</div>
<div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
  <h3 itemprop="name">Can I use an x402 API with normal code?</h3>
  <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <div itemprop="text">Yes. x402 client libraries for Python, TypeScript, and JavaScript handle the 402 → sign → retry loop automatically, so your code just makes a normal HTTP request.</div>
  </div>
</div>
</div>

<p class="dim" style="margin-top:24px;">related: <a href="/x402-llm-api">x402 LLM API</a> · <a href="/x402-gateway">x402 gateway</a> · <a href="/pay-per-request-llm-api">pay-per-request LLM API</a> · <a href="/cheapest-llm-api">cheapest LLM API</a> · <a href="/docs">full docs</a></p>
"""

# ──────────────────────────────────────────────────────────────────────────────
# /x402-llm-api — product page (targets: x402 LLM API, x402 api, pay per
# request llm api, USDC LLM inference)
# ──────────────────────────────────────────────────────────────────────────────

X402LLMAPI_PAGE_TITLE = "x402 LLM API — Pay-per-Request AI Inference in USDC | surp.ivc.lol"
X402LLMAPI_PAGE_DESC = ("The x402 LLM API: pay per request for AI inference in USDC on Base, no account, "
                        "no API key. OpenAI-compatible endpoint that routes to the cheapest model on the "
                        "Surplus Intelligence marketplace.")

X402LLMAPI_PAGE = """
<h1>x402 LLM API</h1>
<p class="dim prompt">POST /v1/chat/completions  # paid per request</p>

<p><b>surp.ivc.lol is an x402 LLM API</b> — a fully <b>OpenAI-compatible</b> inference endpoint where every request is paid with <b>x402</b> (USDC on Base, per request). No account, no API key, no subscription. Send a chat completion, get a 402 with the price, sign with your wallet, and the model answers.</p>

<h2>the cheapest model, every request</h2>
<p>Unlike a static API, surp.ivc.lol watches the live <b>Surplus Intelligence marketplace</b> (150+ models across Anthropic, OpenAI, Google, DeepSeek, Alibaba, xAI, and more) and routes each request to the <b>cheapest model for your task right now</b>. Ask for <code>surp/best-coding</code> and you get whatever coding model is cheapest at that second.</p>

<div class="grid">
  <div class="card"><div class="num">150+</div><div class="lbl">models on the marketplace</div></div>
  <div class="card"><div class="num">15</div><div class="lbl">built-in combos</div></div>
  <div class="card"><div class="num">~1¢</div><div class="lbl">typical request cost</div></div>
  <div class="card"><div class="num">0</div><div class="lbl">accounts required</div></div>
</div>

<h2>how to call the x402 LLM API</h2>
<p>Any HTTP client works. The first call returns <code>402</code> with payment requirements; an x402 client library completes the sign-and-retry automatically:</p>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"surp/best-chat",
       "messages":[{"role":"user","content":"explain x402 like I'm five"}],
       "max_tokens":100}'</pre>
<p class="dim">using an x402 client library (<a href="https://docs.x402.org">docs.x402.org</a>) handles the 402 → sign → retry loop so your code just works.</p>

<h2>what it costs</h2>
<p>You pay the <b>live market price</b> of the cheapest model in the combo, plus a transparent 5% gateway markup. Current examples (per 1M tokens):</p>
<table><thead><tr><th>combo</th><th>typical model</th><th>USD / 1M tokens</th></tr></thead>
<tbody>
  <tr><td class="combo">surp/best-chat</td><td class="model">deepseek-v4-flash</td><td class="price">~$0.04</td></tr>
  <tr><td class="combo">surp/best-coding</td><td class="model">kimi-k2.7-code</td><td class="price">~$0.42</td></tr>
  <tr><td class="combo">surp/pro-chat</td><td class="model">gpt-5.6-terra</td><td class="price">~$0.18</td></tr>
  <tr><td class="combo">surp/best-reasoning</td><td class="model">qwen3-thinking</td><td class="price">~$0.05</td></tr>
</tbody></table>
<p class="dim">live prices: <a href="/">homepage ticker</a></p>

<h2>why agents love an x402 LLM API</h2>
<ul style="margin-left:20px;line-height:1.8;">
  <li><b>Autonomous</b> — an agent pays per request with its own wallet; no human provisioning.</li>
  <li><b>No lock-in</b> — pay only for what you use, stop anytime.</li>
  <li><b>Auditable</b> — every request is an on-chain USDC transfer on Base.</li>
  <li><b>Cheap</b> — dynamic routing means you never overpay for a model you didn't need.</li>
</ul>

<h2>faq</h2>
<div itemscope itemtype="https://schema.org/FAQPage">
<div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
  <h3 itemprop="name">Is the x402 LLM API OpenAI-compatible?</h3>
  <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <div itemprop="text">Yes — it uses the standard /v1/chat/completions shape, so it works with Cursor, Aider, OpenCode, Hermes, and any OpenAI-compatible client.</div>
  </div>
</div>
<div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
  <h3 itemprop="name">What wallet do I need?</h3>
  <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <div itemprop="text">Any wallet holding USDC on Base. The request signs an EIP-3009 authorization; a facilitator submits the transfer (gas sponsored).</div>
  </div>
</div>
<div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
  <h3 itemprop="name">How cheap is it compared to OpenAI or Anthropic?</h3>
  <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <div itemprop="text">Typically 70–99% cheaper than retail list prices, because we route to the cheapest marketplace seller rather than a fixed provider price.</div>
  </div>
</div>
<div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">
  <h3 itemprop="name">Can I use it without a crypto wallet?</h3>
  <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">
    <div itemprop="text">Yes — we also offer prepaid API keys. Create one on the <a href="/dashboard">usage dashboard</a> and use a standard Authorization header.</div>
  </div>
</div>
</div>

<p class="dim" style="margin-top:24px;">related: <a href="/x402">what is x402?</a> · <a href="/x402-gateway">x402 gateway</a> · <a href="/pay-per-request-llm-api">pay-per-request LLM API</a> · <a href="/connect">connect your agent</a> · <a href="/docs">docs</a></p>
"""

# ──────────────────────────────────────────────────────────────────────────────
# /x402-gateway — keyword page (targets: x402 gateway, x402 llm gateway,
# x402 payment gateway, monetization gateway)
# ──────────────────────────────────────────────────────────────────────────────

X402GATEWAY_PAGE_TITLE = "x402 Gateway — Pay-per-Request LLM Gateway | surp.ivc.lol"
X402GATEWAY_PAGE_DESC = ("An x402 gateway is a server that verifies and settles HTTP 402 payments for APIs. "
                         "surp.ivc.lol is a live x402 LLM gateway: pay per request in USDC, get the cheapest model.")

X402GATEWAY_PAGE = """
<h1>x402 gateway</h1>
<p class="dim prompt">402 — payment required. this gateway handles the rest.</p>

<p>An <b>x402 gateway</b> sits between a client and an API, verifying <code>402</code> payments and settling them on-chain. <b>surp.ivc.lol</b> is a production <b>x402 LLM gateway</b>: it paywalls AI inference per request in <b>USDC on Base</b>, so anyone with a wallet can call frontier models without an account.</p>

<h2>what a gateway does</h2>
<p>In the x402 flow, three parties cooperate:</p>
<ul style="margin-left:20px;line-height:1.8;">
  <li><b>Client</b> — your app or agent. Sends the request, signs the USDC authorization.</li>
  <li><b>Gateway</b> — surp.ivc.lol. Presents the price (402), verifies the signature via a facilitator, forwards the request to the model.</li>
  <li><b>Facilitator</b> — submits the EIP-3009 transfer on-chain, sponsoring gas so the client only pays USDC.</li>
</ul>

<h2>our gateway adds dynamic pricing</h2>
<p>Most x402 gateways charge a fixed price for a fixed resource. Ours is a <b>marketplace router</b>: the price and the model both come from the live <b>Surplus Intelligence</b> order book. The gateway picks the cheapest model in your requested class at that second, quotes that price, and on payment routes the request there. You never pay frontier prices for a model that's cheap on the open market.</p>

<h2>why pay-per-request beats subscriptions for LLMs</h2>
<ul style="margin-left:20px;line-height:1.8;">
  <li>No unused quota — you pay for exactly the tokens you use.</li>
  <li>No credit card, no KYC — a wallet is enough.</li>
  <li>No vendor lock-in — switch models per request, or let the gateway pick the cheapest.</li>
  <li>Fully automated for agents — the handshake is protocol-level, not human-level.</li>
</ul>

<h2>the gateway as a product</h2>
<p>If you build AI products, an x402 gateway can be your monetization layer: charge per request, settle in USDC, no billing infrastructure. The <a href="https://github.com/x402-foundation/x402">x402 reference implementation</a> and our own <a href="/docs">docs</a> cover the server side; <a href="/connect">connect your agent</a> shows the client side.</p>

<p class="dim" style="margin-top:24px;">related: <a href="/x402">what is x402?</a> · <a href="/x402-llm-api">x402 LLM API</a> · <a href="/pay-per-request-llm-api">pay-per-request LLM API</a> · <a href="/cheapest-llm-api">cheapest LLM API</a> · <a href="/docs">docs</a></p>
"""

# ──────────────────────────────────────────────────────────────────────────────
# /pay-per-request-llm-api — intent page (targets: pay per request llm api,
# pay as you go LLM, micropayment LLM API)
# ──────────────────────────────────────────────────────────────────────────────

PAYPERREQUEST_PAGE_TITLE = "Pay-Per-Request LLM API — No Subscription, No Account | surp.ivc.lol"
PAYPERREQUEST_PAGE_DESC = ("A pay-per-request LLM API: pay only for the tokens you use, in USDC on Base. "
                           "No subscription, no account, no API key. Dynamic routing to the cheapest model.")

PAYPERREQUEST_PAGE = """
<h1>pay-per-request LLM API</h1>
<p class="dim prompt">pay as you go. literally.</p>

<p>Most LLM APIs are subscriptions: a monthly bill whether you use it or not. <b>surp.ivc.lol is a pay-per-request LLM API</b> — you pay only for the requests you make, in <b>USDC on Base</b>, via <b>x402</b>. No subscription, no credit card, no account, no API key.</p>

<h2>how pay-per-request pricing works here</h2>
<p>Every request is priced at the <b>live market rate</b> of the model that serves it. You choose a <b>combo</b> (e.g. <code>surp/best-coding</code>), and the gateway routes to the cheapest model in that class at that second. The price is quoted in the 402 response, you sign the USDC transfer, and the model answers.</p>

<div class="grid">
  <div class="card"><div class="num">~1¢</div><div class="lbl">per request</div></div>
  <div class="card"><div class="num">0</div><div class="lbl">monthly fees</div></div>
  <div class="card"><div class="num">0</div><div class="lbl">accounts</div></div>
  <div class="card"><div class="num">150+</div><div class="lbl">models, dynamically priced</div></div>
</div>

<h2>when pay-per-request makes sense</h2>
<ul style="margin-left:20px;line-height:1.8;">
  <li><b>Agents and bots</b> — autonomous workloads that shouldn't carry a subscription.</li>
  <li><b>Sporadic use</b> — you call an LLM occasionally; a monthly plan is wasted money.</li>
  <li><b>Cost-sensitive products</b> — every cent counts; pay only for real usage.</li>
  <li><b>Experiments and demos</b> — spin up, try, tear down, no billing baggage.</li>
</ul>

<h2>no wallet? use a prepaid key</h2>
<p>If you'd rather not hold crypto, we also offer <b>prepaid API keys</b> — top up a balance and use a standard <code>Authorization: Bearer</code> header. Same per-request pricing, same dynamic routing. <a href="/dashboard">Create a key &raquo;</a></p>

<h2>try it</h2>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"surp/best-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":50}'</pre>
<p class="dim">First response is a 402 with the price. Sign with an x402 client and the completion streams back. See <a href="/connect">connect your agent</a> for full setup.</p>

<p class="dim" style="margin-top:24px;">related: <a href="/x402">what is x402?</a> · <a href="/x402-llm-api">x402 LLM API</a> · <a href="/x402-gateway">x402 gateway</a> · <a href="/cheapest-llm-api">cheapest LLM API</a> · <a href="/docs">docs</a></p>
"""

# ──────────────────────────────────────────────────────────────────────────────
# /cheapest-llm-api — comparison/price page (targets: cheapest LLM API, LLM API
# pricing, cheap AI API, compare LLM prices)
# ──────────────────────────────────────────────────────────────────────────────

CHEAPEST_PAGE_TITLE = "Cheapest LLM API — Live LLM API Pricing, Ranked | surp.ivc.lol"
CHEAPEST_PAGE_DESC = ("The cheapest LLM API, ranked with live prices. Compare 150+ AI models across "
                      "providers, see who's cheapest right now, and pay per request in USDC — no subscription.")

CHEAPEST_PAGE = """
<h1>cheapest LLM API</h1>
<p class="dim prompt">price check: 150+ models, live.</p>

<p>Looking for the <b>cheapest LLM API</b>? Here's the thing: the cheapest model changes <i>constantly</i>. Sellers on the <b>Surplus Intelligence marketplace</b> reprice in real time, and new models launch all the time. A static comparison is stale the moment it's published.</p>

<p>surp.ivc.lol solves this differently: it's an <b>LLM API that routes to whatever is cheapest at request time</b>. You don't pick a provider — you pick a class of work ("coding", "chat", "reasoning") and the gateway picks the cheapest model serving that class right now. You pay the live market price plus a 5% gateway fee.</p>

<h2>live pricing vs retail</h2>
<p class="dim">examples from the live marketplace (per 1M tokens):</p>
<table><thead><tr><th>model</th><th>retail list price</th><th>via surp.ivc.lol</th><th>savings</th></tr></thead>
<tbody>
  <tr><td class="model">deepseek-v4-flash</td><td>~$0.20</td><td class="price">~$0.04</td><td>~80%</td></tr>
  <tr><td class="model">qwen3-coder-turbo</td><td>~$1.00</td><td class="price">~$0.42</td><td>~58%</td></tr>
  <tr><td class="model">gpt-5.6-terra</td><td>~$1.75</td><td class="price">~$0.18</td><td>~90%</td></tr>
  <tr><td class="model">glm-5.2</td><td>~$0.60</td><td class="price">~$0.03</td><td>~95%</td></tr>
</tbody></table>
<p class="dim">these move every minute — see <a href="/">the live ticker</a>, <a href="/top">top-5 leaderboards</a>, or <a href="/models">browse all models</a>.</p>

<h2>why we're cheaper than retail</h2>
<ul style="margin-left:20px;line-height:1.8;">
  <li><b>Marketplace pricing</b> — sellers compete on price; you get the best offer, not a fixed list price.</li>
  <li><b>Dynamic routing</b> — no overpaying for a "premium" model when a cheaper one is just as good for your task.</li>
  <li><b>No subscription overhead</b> — no unused quota to subsidize, no billing minimums.</li>
  <li><b>Open models included</b> — DeepSeek, Qwen, GLM and other open-weight models cost a fraction of closed frontier models for most tasks.</li>
</ul>

<h2>how to get the cheapest LLM API right now</h2>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"surp/chat","messages":[{"role":"user","content":"hello"}],"max_tokens":50}'</pre>
<p class="dim"><code>surp/chat</code> = cheapest general chat model at this second. <code>surp/best-coding</code> = cheapest coder. <a href="/find">Find the right model for your task &raquo;</a></p>

<p class="dim" style="margin-top:24px;">related: <a href="/x402">what is x402?</a> · <a href="/x402-llm-api">x402 LLM API</a> · <a href="/pay-per-request-llm-api">pay-per-request LLM API</a> · <a href="/compare">compare models</a> · <a href="/top">top 5 leaderboards</a></p>
"""

# ──────────────────────────────────────────────────────────────────────────────
# Registry — page → (title, desc, content)
# ──────────────────────────────────────────────────────────────────────────────

KEYWORD_PAGES = {
    "/x402": {
        "title": X402_PAGE_TITLE,
        "desc": X402_PAGE_DESC,
        "content": X402_PAGE,
    },
    "/x402-llm-api": {
        "title": X402LLMAPI_PAGE_TITLE,
        "desc": X402LLMAPI_PAGE_DESC,
        "content": X402LLMAPI_PAGE,
    },
    "/x402-gateway": {
        "title": X402GATEWAY_PAGE_TITLE,
        "desc": X402GATEWAY_PAGE_DESC,
        "content": X402GATEWAY_PAGE,
    },
    "/pay-per-request-llm-api": {
        "title": PAYPERREQUEST_PAGE_TITLE,
        "desc": PAYPERREQUEST_PAGE_DESC,
        "content": PAYPERREQUEST_PAGE,
    },
    "/cheapest-llm-api": {
        "title": CHEAPEST_PAGE_TITLE,
        "desc": CHEAPEST_PAGE_DESC,
        "content": CHEAPEST_PAGE,
    },
}
