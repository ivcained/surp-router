"""Public documentation page for NFT/token-gated access."""

TITLE = "Token-Gated API Access — NFT eligibility for surp.ivc.lol"
DESC = ("How surp.ivc.lol uses NFT/token holdings to gate API access. "
        "Prototype design, community feedback, and how to participate.")


def content(live: dict) -> str:
    rewards = (live or {}).get("rewards", {}) or {}
    feedback = (live or {}).get("feedback", {}) or {}
    recent = (live or {}).get("recent_feedback", []) or []
    pool = rewards.get("rebate_pool_usd", 0)
    srp = rewards.get("srp_outstanding", 0)
    total_fb = sum(feedback.values())

    fb_rows = ""
    for item in recent[:15]:
        ts = item.get("ts", 0)
        cat = item.get("category", "")
        msg = item.get("message", "").replace("<", "&lt;")
        up = item.get("upvotes", 0)
        fid = item.get("id", 0)
        fb_rows += f"<tr><td class='dim'>{cat}</td><td>{msg}</td><td>{up} <button onclick=\"upvote({fid})\" class='btn-sm'>↑</button></td></tr>\n"
    if not fb_rows:
        fb_rows = "<tr><td colspan='3' class='dim'>no feedback yet — be the first</td></tr>"

    return f"""<style>
    .choice {{ border:1px solid #333; padding:14px; margin:10px 0; cursor:pointer; }}
    .choice:hover {{ border-color:#5ce1ff; }}
    .choice.selected {{ border-color:#5ce1ff; background:#0a1418; }}
    label {{ display:block; font-size:13px; color:#888; margin:8px 0 2px; }}
    input, textarea {{ width:100%; background:#000; border:1px solid #333; color:#e0e0e0; padding:8px; font-family:monospace; font-size:13px; box-sizing:border-box; }}
    textarea {{ height:60px; resize:vertical; }}
    .btn {{ background:#5ce1ff; color:#000; border:none; padding:10px 20px; font-family:monospace; font-weight:bold; cursor:pointer; }}
    .btn:hover {{ background:#7ff0ff; }}
    .btn-sm {{ background:#333; color:#e0e0e0; border:none; padding:3px 8px; font-family:monospace; cursor:pointer; }}
    #feedback-result {{ margin-top:12px; font-family:monospace; font-size:13px; color:#5ce1ff; }}
    .warn {{ border-left:3px solid #f59e0b; padding:10px 14px; background:#1a1408; margin:16px 0; }}
    </style>

<h1>token-gated API access</h1>
<p class="dim prompt">hold an NFT, access the cheapest LLM API without per-request payment.</p>

<h2>the problem with per-request payment</h2>
<p>x402 is brilliant for cold-start agents: no account, no API key, just pay. But for repeat customers making hundreds or thousands of calls per day, it is wasteful — every request triggers a fresh signed transfer and an on-chain settlement, even though the agent's intent is the same every time: <i>"I want to use this service."</i></p>
<p>What if holding a token was the proof? Not a password, not an API key — an on-chain, verifiable, self-custodied signal that says: <i>I am a committed member of this network.</i></p>

<h2>how the prototype works</h2>
<p>A single <code>balanceOf</code> call against a configurable ERC-20 or ERC-721 contract on Base determines eligibility. The check is:</p>
<ul style="margin-left:20px;line-height:1.8;">
  <li><b>Read-only</b> — no gas, no signing, no state change. Just an <code>eth_call</code>.</li>
  <li><b>Cached</b> — a wallet's eligibility is cached for 60 seconds (configurable). Repeat callers incur near-zero RPC overhead.</li>
  <li><b>Fail-closed</b> — if the RPC is unreachable or returns garbage, the wallet is <i>denied</i>, never granted access for free.</li>
  <li><b>Composable</b> — works with any ERC-20 or ERC-721: a governance token, a membership NFT, a loyalty pass, a community badge.</li>
</ul>
<p>When eligibility is configured, callers include their wallet via the <code>X-Wallet</code> header. Holders skip x402 entirely; non-holders fall through to the normal payment flow.</p>

<h2>what a holder gets</h2>
<table><thead><tr><th>feature</th><th>x402 per-request</th><th>NFT holder</th></tr></thead><tbody>
<tr><td>per-request on-chain tx</td><td>yes (one per call)</td><td>no</td></tr>
<tr><td>signing overhead</td><td>every request</td><td>none</td></tr>
<tr><td>customer identity</td><td>anonymous</td><td>persistent (wallet = identity)</td></tr>
<tr><td>SRP reward accrual</td><td>wallet tracked</td><td>native (wallet = SRP account)</td></tr>
<tr><td>pricing</td><td>standard</td><td>configurable discount (0-100%)</td></tr>
<tr><td>rate limit</td><td>default</td><td>configurable higher tier</td></tr>
</tbody></table>

<h2>the closed loop: NFT + cache flywheel</h2>
<p>This is where it gets interesting. The NFT holder's wallet is simultaneously:</p>
<ul style="margin-left:20px;line-height:1.8;">
  <li><b>Their payment identity</b> (no API key, no account, just a wallet)</li>
  <li><b>Their SRP reward account</b> (cache writes and hits mint SRP directly to their wallet)</li>
  <li><b>Their eligibility proof</b> (holding = access, no per-request fee)</li>
  <li><b>A Sybil-resistant signal</b> (to farm SRP you must hold the token, which costs capital)</li>
</ul>
<p>And if the NFT sale revenue flows into the SRP rebate pool, every new member directly funds the flywheel for everyone:</p>
<pre>agent buys NFT → rebate pool grows → SRP value rises
agent uses gateway → creates/uses cache → earns SRP
agent's SRP appreciates → effective cost drops → uses gateway more
more usage → more cache hits → more savings → more SRP value</pre>

<h2>what we need from the community</h2>
<p>This is a prototype. We have not deployed a contract yet. Before we do, we need answers to real questions. That's what the feedback board below is for.</p>
<h3>open questions</h3>
<ol style="margin-left:20px;line-height:1.8;">
  <li>Should the token be an <b>ERC-721 membership NFT</b> (one per wallet, fixed price) or an <b>ERC-20 governance token</b> (variable balance, tradable)?</li>
  <li>Should holders pay <b>nothing at all</b> (pure gate), or should they get a <b>discount on per-request pricing</b> (gate + revenue)?</li>
  <li>Should there be <b>multiple tiers</b> (e.g. bronze/silver/gold NFTs with different rate limits and discounts)?</li>
  <li>Should NFT sale revenue go to the <b>SRP rebate pool</b>, to <b>operational costs</b>, or a <b>split</b>?</li>
  <li>Should there be a <b>stake-and-slash</b> mechanism (holding at risk, slashed for abuse) or is simple <b>holding</b> sufficient?</li>
  <li>What price point makes the NFT accessible to independent developers but expensive enough to deter Sybil farms?</li>
  <li>Should SRP become the on-chain token that grants eligibility, closing the loop completely?</li>
</ol>

<div class="warn"><b>prototype stage.</b> No contract has been deployed. No funds are accepted. The gate module is code-ready (see <a href="/status">status page</a>) but dormant until the community decides on the design. This page is the public specification. Your feedback here directly shapes what gets built.</div>

<h2>community feedback</h2>
<p class="dim">{total_fb} pieces of feedback so far. Your identity is a salted hash — raw handles/IPs are never stored.</p>

<div style="border:1px solid #333;padding:14px;margin:16px 0;">
  <legend style="padding:0 6px;color:#888;">submit feedback</legend>
  <label>handle (optional — your wallet address or name)</label>
  <input id="fb-handle" type="text" placeholder="0x... or your-name" />
  <label>category</label>
  <select id="fb-category" style="background:#000;border:1px solid #333;color:#e0e0e0;padding:8px;font-family:monospace;font-size:13px;width:100%;">
    <option value="idea">idea</option>
    <option value="concern">concern</option>
    <option value="question">question</option>
    <option value="support">support</option>
  </select>
  <label>message (max 280 chars)</label>
  <textarea id="fb-message" placeholder="your thoughts on the token-gating design..."></textarea>
  <div style="margin-top:10px;">
    <button class="btn" onclick="submitFeedback()">submit</button>
    <span id="feedback-result"></span>
  </div>
</div>

<h3>recent feedback</h3>
<table style="width:100%"><thead><tr><th style="width:80px;">type</th><th>message</th><th style="width:80px;">votes</th></tr></thead><tbody>
{fb_rows}
</tbody></table>

<p class="dim">related: <a href="/proposal">vote on SRP / RevNet direction</a> · <a href="/cache">how the cache engine works</a> · <a href="/status">live system status</a> · <a href="/docs">API docs</a> · <a href="/about">about surp</a></p>

<script>
async function submitFeedback() {{
  const handle = document.getElementById('fb-handle').value.trim();
  const category = document.getElementById('fb-category').value;
  const message = document.getElementById('fb-message').value.trim();
  const r = await fetch('/api/feedback', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{handle, category, message}})
  }});
  const d = await r.json();
  if (d.ok) {{
    document.getElementById('feedback-result').textContent = '✓ submitted — thank you';
    document.getElementById('fb-message').value = '';
    setTimeout(() => location.reload(), 1200);
  }} else {{
    document.getElementById('feedback-result').textContent = '✗ ' + d.error;
  }}
}}
async function upvote(id) {{
  const handle = document.getElementById('fb-handle').value.trim();
  const r = await fetch('/api/feedback/upvote', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{id, handle}})
  }});
  const d = await r.json();
  if (d.ok) location.reload();
}}
</script>
"""
