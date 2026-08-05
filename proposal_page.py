"""Public ELI5 proposal page for the surp cache flywheel + reward token."""

TITLE = "Proposal: Cache Flywheel Rewards — surp.ivc.lol"
DESC = ("Should surp.ivc.lol keep cache rewards off-chain, deploy a Juicebox treasury, "
        "launch a RevNet revenue-backed token, or go hybrid? Read the ELI5 proposal and vote.")


def content(live: dict) -> str:
    """Render the proposal page, interpolating live reward + vote metrics."""
    rewards = (live or {}).get("rewards", {}) or {}
    votes = (live or {}).get("votes", {}) or {}
    pool = rewards.get("rebate_pool_usd", 0)
    srp = rewards.get("srp_outstanding", 0)
    holders = rewards.get("holders", 0)
    vps = rewards.get("value_per_srp_cents", 0)
    total_votes = votes.get("total_votes", 0)
    changed = votes.get("changed_votes", 0)
    opts = votes.get("options", {})

    def bar(opt: str) -> str:
        o = opts.get(opt, {})
        pct = o.get("pct", 0)
        n = o.get("votes", 0)
        return f'<div class="vote-row"><div class="vote-bar"><span style="width:{pct}%"></span></div><div class="vote-num">{n} ({pct}%)</div></div>'

    return f"""<style>
.vote-row {{ display:flex; align-items:center; gap:12px; margin:6px 0; }}
.vote-bar {{ flex:1; height:18px; background:#111; border:1px solid #333; overflow:hidden; }}
.vote-bar span {{ display:block; height:100%; background:#5ce1ff; }}
.vote-num {{ font-family:monospace; font-size:12px; min-width:90px; }}
.fieldset {{ border:1px solid #333; padding:12px; margin:16px 0; }}
.fieldset legend {{ padding:0 6px; color:#888; }}
.warn {{ border-left:3px solid #f59e0b; padding:10px 14px; background:#1a1408; margin:16px 0; }}
.choice {{ border:1px solid #333; padding:14px; margin:10px 0; cursor:pointer; }}
.choice:hover {{ border-color:#5ce1ff; }}
.choice.selected {{ border-color:#5ce1ff; background:#0a1418; }}
label {{ display:block; font-size:13px; color:#888; margin:8px 0 2px; }}
input, textarea {{ width:100%; background:#000; border:1px solid #333; color:#e0e0e0; padding:8px; font-family:monospace; font-size:13px; box-sizing:border-box; }}
textarea {{ height:60px; resize:vertical; }}
.btn {{ background:#5ce1ff; color:#000; border:none; padding:10px 20px; font-family:monospace; font-weight:bold; cursor:pointer; }}
.btn:hover {{ background:#7ff0ff; }}
#vote-result {{ margin-top:12px; font-family:monospace; font-size:13px; color:#5ce1ff; }}
</style>

<h1>proposal: cache flywheel rewards</h1>
<p class="dim prompt">vote on how surp.ivc.lol should handle rewards for agents that create shared cache value.</p>

<div class="warn"><b>this is an advisory vote.</b> Nothing here commits funds, mints a token, or promises profit. It is a transparent signal to the maintainers about what the community wants. Read the full proposal below before voting.</div>

<h2>the idea, in plain English (ELI5)</h2>
<p>Every time an AI agent asks surp.ivc.lol a question, it pays a tiny amount of USDC. If the question is one the network has already answered, the network can return a <b>cached copy</b> instead of calling the model again. That saves real money and time.</p>
<p>Right now surp keeps all of that savings. But what if the agents that <i>created</i> the cached answer, and the agents that <i>reused</i> it, got a small reward? Then:</p>
<ul style="margin-left:20px;line-height:1.8;">
  <li>Agents would want to reuse the cache (more rewards) instead of bypassing it.</li>
  <li>Agents would ask useful, reusable questions (their cache gets reused → they earn more).</li>
  <li>The network's costs would drop as the shared cache grows.</li>
  <li>Loyal heavy users would accumulate a claim on the savings they helped create.</li>
</ul>
<p>The more the network is used, the cheaper it gets for the people using it — a <b>positive feedback loop</b>. That is the core idea behind a "revenue network" or <b>RevNet</b>.</p>

<h2>what's running right now (off-chain prototype)</h2>
<p>To prove the loop works before touching real money, surp runs an <b>off-chain accounting ledger</b> called <b>SRP</b> (surp reward points). No token contract, no blockchain settlement — just a database that records who created how much cache value.</p>
<div class="grid">
  <div class="card"><div class="num">${pool:.4f}</div><div class="lbl">rebate pool backing</div></div>
  <div class="card"><div class="num">{srp}</div><div class="lbl">SRP outstanding</div></div>
  <div class="card"><div class="num">{holders}</div><div class="lbl">reward holders</div></div>
  <div class="card"><div class="num">{vps:.6f}¢</div><div class="lbl">implied value per SRP</div></div>
</div>
<p class="dim">live data from <code>GET /api/stats</code>. these are tiny numbers because the experiment just started — the point is the accounting loop works.</p>

<h3>how SRP is earned</h3>
<table><thead><tr><th>event</th><th>who earns</th><th>rate</th></tr></thead><tbody>
<tr><td>cache write (a reusable answer is created)</td><td>the payer who funded it</td><td>1 SRP per token cached</td></tr>
<tr><td>cache hit (the answer is reused)</td><td>the original author</td><td>2 SRP per token saved</td></tr>
<tr><td>cache hit</td><td>the agent that reused it</td><td>0.5 SRP per token saved</td></tr>
</tbody></table>

<h3>how SRP is backed</h3>
<p>A share of estimated gateway revenue is earmarked to a rebate pool. SRP's implied value = <code>pool ÷ outstanding SRP</code>. As revenue flows in, existing SRP appreciates. That's the RevNet redemption mechanism, done off-chain.</p>

<h2>the question for the community</h2>
<p>SRP works as accounting. But should it stay an internal ledger, or should we move the backing on-chain so rewards become real, verifiable claims? Here are the options as we see them. Vote below.</p>

<div class="choice" onclick="selectChoice('offchain')">
  <h3>option A — keep it off-chain (safest)</h3>
  <p>SRP stays a transparent accounting simulation. No token, no contract, no legal exposure. We keep measuring and publish metrics. Downside: rewards are not portable or independently verifiable; agents have to trust the ledger.</p>
</div>

<div class="choice" onclick="selectChoice('juicebox')">
  <h3>option B — Juicebox treasury + Merkle claims</h3>
  <p>A portion of gateway revenue flows into a Juicebox project with public splits (inference costs, operations, rebate reserve, community). We publish periodic Merkle roots of off-chain SRP balances; agents claim USDC rebates on-chain. Medium setup cost, high transparency, no new speculative token.</p>
</div>

<div class="choice" onclick="selectChoice('revnet')">
  <h3>option C — RevNet revenue-backed token</h3>
  <p>Gateway revenue backs a redemption pool for a network token. Token holders can redeem against the pool. This is the strongest loyalty flywheel — use the network, earn a claim on its future revenue — but it requires the most legal/engineering care and carries the most token-risk.</p>
</div>

<div class="choice" onclick="selectChoice('hybrid')">
  <h3>option D — hybrid (recommended by maintainers)</h3>
  <p>Keep SRP off-chain for 30–90 days to gather real farming/Sybil data. Then move backing to a Juicebox treasury and publish Merkle claims. Only transition to a full RevNet if the economics prove out. Slower to ship, but avoids permanently encoding bad reward weights.</p>
</div>

<h2>cast your advisory vote</h2>
<p>One vote per person. You can change it later. Your handle (or IP if you leave it blank) is salted and hashed — we never store the raw value.</p>
<div class="fieldset">
  <legend>vote</legend>
  <label>handle (optional — leave blank to vote anonymously by IP)</label>
  <input id="vote-handle" type="text" placeholder="your-name or 0xaddress" />
  <label>your choice</label>
  <div id="choice-display" style="font-family:monospace;font-size:13px;padding:8px;border:1px dashed #333;">pick an option above</div>
  <input id="vote-option" type="hidden" />
  <label>comment (optional, max 280 chars)</label>
  <textarea id="vote-comment" placeholder="why this choice?"></textarea>
  <div style="margin-top:10px;">
    <button class="btn" onclick="castVote()">cast vote</button>
    <span id="vote-result"></span>
  </div>
</div>

<h2>live results</h2>
<p class="dim">{total_votes} votes cast ({changed} changed their mind)</p>
{bar('offchain')}
<p class="dim" style="margin:-2px 0 6px;">keep it off-chain</p>
{bar('juicebox')}
<p class="dim" style="margin:-2px 0 6px;">Juicebox treasury + Merkle claims</p>
{bar('revnet')}
<p class="dim" style="margin:-2px 0 6px;">RevNet revenue-backed token</p>
{bar('hybrid')}
<p class="dim" style="margin:-2px 0 6px;">hybrid: off-chain now, RevNet later</p>

<h2>anti-farming guardrails</h2>
<ul style="margin-left:20px;line-height:1.8;">
  <li>Rewards are deduplicated per cache entry, role, and payer for one hour.</li>
  <li>Only deterministic, non-streaming, tool-free requests enter the exact cache.</li>
  <li>Raw prompts are never stored — only SHA-256 fingerprints and completed responses.</li>
  <li>Cache readers still pay a discounted $0.001 micropayment, preventing free probing.</li>
  <li>Most author rewards only mint when an independent agent reuses an entry — write-spam has little value.</li>
  <li>One salted hash per voter; votes can be changed, not multiplied.</li>
</ul>

<h2>risks and honest caveats</h2>
<ul style="margin-left:20px;line-height:1.8;">
  <li><b>Sybil attacks:</b> a determined attacker could spin up many wallets. Off-chain first lets us measure this before going on-chain.</li>
  <li><b>Reward weight tuning:</b> 1/2/0.5 SRP rates are guesses. Real traffic data will tell us if authors or readers are over/under-rewarded.</li>
  <li><b>Legal:</b> any on-chain token with revenue backing may be a security in some jurisdictions. The hybrid path delays this risk until the model is proven.</li>
  <li><b>Centralization:</b> until on-chain settlement exists, the maintainer holds the earmarked pool. Juicebox/RevNet removes this trust assumption.</li>
  <li><b>Cache poisoning:</b> a malicious agent could try to fill the cache with wrong answers to farm rewards — but readers still pay, answers are deterministic, and the dedup window limits farming.</li>
</ul>

<div class="warn"><b>not financial advice, not a security.</b> SRP is currently an internal accounting unit with no on-chain existence, no transferability, no guaranteed redemption, and no expectation of profit. Voting here signals preference only.</div>

<p class="dim">related: <a href="/cache">how the cache engine works</a> · <a href="/status">live system status</a> · <a href="/x402-llm-api">x402 LLM API</a> · <a href="/about">about surp</a></p>

<script>
let selected = null;
function selectChoice(opt) {{
  selected = opt;
  document.querySelectorAll('.choice').forEach(c => c.classList.remove('selected'));
  event.currentTarget.classList.add('selected');
  document.getElementById('vote-option').value = opt;
  const labels = {{offchain:'keep off-chain',juicebox:'Juicebox treasury',revnet:'RevNet token',hybrid:'hybrid path'}};
  document.getElementById('choice-display').textContent = labels[opt] || opt;
}}
async function castVote() {{
  if (!selected) {{ document.getElementById('vote-result').textContent = 'pick an option first'; return; }}
  const handle = document.getElementById('vote-handle').value.trim();
  const comment = document.getElementById('vote-comment').value.trim();
  const r = await fetch('/api/vote', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{handle, option: selected, comment}})
  }});
  const d = await r.json();
  if (d.ok) {{
    document.getElementById('vote-result').textContent = '✓ vote recorded — ' + d.label + (d.changed_vote ? ' (vote changed)' : '');
    setTimeout(() => location.reload(), 1200);
  }} else {{
    document.getElementById('vote-result').textContent = '✗ ' + d.error;
  }}
}}
</script>
"""
