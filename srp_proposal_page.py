"""SRP token contract proposal page — deploy-vote with benefits/risks review.

Proposal: should surp deploy SurpRewardToken (SRP) as a real ERC-20 on Base?

The vote is advisory (community signal). The current off-chain accounting
ledger (reward_ledger.py) would become the mint authority for the on-chain
token, so every earned SRP maps to a claimable mint.
"""

TITLE = "Proposal: Deploy the SRP Token Contract on Base — surp.ivc.lol"
DESC = ("Vote on whether surp should deploy SurpRewardToken (SRP) as an ERC-20 on "
        "Base, list the benefits and risks, and review the contract design before "
        "any mainnet deploy.")

GAS_NOTES = (
    "Gas note: with x402 the payment signature is off-chain and free — the user "
    "only pays submit gas when a transaction actually lands on Base. A standing "
    "approval (Surplus's SettlementV2 model) saves the per-request submit gas, "
    "but introduces an unlimited-spend risk on your wallet. At current Base gas "
    "(~0.01 gwei), one EIP-3009 transfer costs well under $0.001 — an unlimited "
    "approval saves fractions of a cent per request at the cost of handing the "
    "contract unlimited access to your balance. We recommend against it."
)


def content(live: dict) -> str:
    rewards = (live or {}).get("rewards", {}) or {}
    votes = (live or {}).get("votes", {}) or {}
    pool = rewards.get("rebate_pool_usd", 0)
    srp = rewards.get("srp_outstanding", 0)
    holders = rewards.get("holders", 0)
    vps = rewards.get("value_per_srp_cents", 0)
    total_votes = votes.get("total_votes", 0)
    opts = votes.get("options", {})

    def bar(opt: str) -> str:
        o = opts.get(opt, {})
        pct = o.get("pct", 0)
        n = o.get("votes", 0)
        return (f'<div class="vote-row"><div class="vote-bar">'
                f'<span style="width:{pct}%"></span></div>'
                f'<div class="vote-num">{n} ({pct}%)</div>'
                f'<div class="dim" style="font-size:11px">{o.get("label", "")}</div></div>')

    vote_buttons = ""
    for opt, o in opts.items():
        vote_buttons += (f'<button class="btn btn-outline vote-btn" data-opt="{opt}" '
                         f'style="margin:4px 6px 4px 0;">{o.get("label", opt)}</button>')

    return f"""<style>
.vote-row {{ display:flex; align-items:center; gap:12px; margin:6px 0; }}
.vote-bar {{ flex:1; height:18px; background:#111; border:1px solid #333; overflow:hidden; }}
.vote-bar span {{ display:block; height:100%; background:#5ce1ff; }}
.vote-num {{ font-family:monospace; font-size:12px; min-width:90px; }}
.vote-btn.selected {{ background:rgba(0,255,156,.15) !important; border-color:var(--accent) !important; }}
</style>

<h1>Proposal: Deploy the SRP Token on Base</h1>
<p class="dim prompt">surp reward token · contract review · advisory vote</p>

<div class="card" style="margin:14px 0;">
<h2>## tl;dr</h2>
<p>surp's reward ledger (SRP) is currently <b>off-chain accounting</b>. This proposal
asks the community whether we should deploy it as a real ERC-20 on Base —
<code>SurpRewardToken</code> — with the existing ledger as the mint authority.
The vote is advisory; nothing deploys without this reaching a community-supported
threshold and a security review.</p>
</div>

<h2>## current state (live)</h2>
<table>
<tr><th>metric</th><th>value</th></tr>
<tr><td>rebate pool (USDC)</td><td>${pool}</td></tr>
<tr><td>SRP outstanding (off-chain)</td><td>{srp}</td></tr>
<tr><td>holders</td><td>{holders}</td></tr>
<tr><td>value per SRP (est)</td><td>{vps}¢</td></tr>
<tr><td>votes cast</td><td>{total_votes}</td></tr>
</table>

<h2>## what we'd deploy</h2>
<ul>
<li><b>Standard:</b> OpenZeppelin ERC20 + Permit (EIP-2612) + AccessControl + Pausable</li>
<li><b>Supply:</b> 1,000,000,000 SRP cap, mintable only by MINTER_ROLE (the gateway ledger)</li>
<li><b>Upgradeable?</b> No — immutable implementation. The ledger remains the mint
authority; the token itself is a simple, auditable ERC-20.</li>
<li><b>Burn:</b> burnable by holders (or via a future burn-bridge)</li>
<li><b>Draft source:</b> <code>docs/BASE_LAUNCH_READINESS.md</code> (SurpRewardToken.sol)</li>
</ul>

<h2>## benefits</h2>
<ul>
<li><b>Real ownership</b> — SRP becomes a claimable, transferable asset instead of a
database row. Holders can verify their balance on-chain (basescan).</li>
<li><b>Liquidity path</b> — a listed ERC-20 can later get a Base swap pool
(Aerodrome/Uniswap), giving cache writers/authors a real exit.</li>
<li><b>Marketplace engagement</b> — suppliers and buyers both earn SRP for
participation; an on-chain token makes the flywheel tangible.</li>
<li><b>Composability</b> — wallets, dapps, and future governance can hold/use SRP.</li>
<li><b>Same economics</b> — reward rates unchanged (1 write / 2 author / 0.5 read
per token), just moved from ledger rows to mint claims.</li>
</ul>

<h2>## risks</h2>
<ul>
<li><b>Irreversibility</b> — once deployed, the supply cap and mint rules are
immutable. A bug in the ledger integration would need a new contract.</li>
<li><b>Launch cost</b> — deployer wallet needs ~0.005 ETH for gas (currently
0.000457). A Base Sepolia testnet deploy is the low-cost rehearsal.</li>
<li><b>No implied value</b> — SRP is a reward token, not an investment contract.
Value depends on the platform's real revenue, not on token mechanics.</li>
<li><b>Regulatory ambiguity</b> — a transferable token can attract scrutiny;
we'd include a transfer-restriction switch if the community wants it.</li>
<li><b>Ledger↔contract coupling</b> — the gateway's reward ledger becomes the
mint authority; a ledger bug could mint incorrectly (mitigated by the cap +
audit logging + pausable minting).</li>
</ul>

<h2>## gas-fee question (standing approval vs per-request)</h2>
<p>{GAS_NOTES}</p>
<p class="dim">If we ever want to offer an approve-and-pull settlement for users who
explicitly prefer it, the safe version is a <b>capped one-time allowance</b>
(spend limit), not an infinite approval — same gas savings, no unlimited-spend
risk. The studio already settles per-request via EIP-3009 signatures.</p>

<h2>## vote — should we deploy SRP on Base?</h2>
<div id="vote-box">
  <div>{vote_buttons}</div>
  <div style="display:flex; gap:8px; margin:10px 0;">
    <input id="vote-handle" placeholder="your handle (e.g. @you)" style="flex:1; background:#000; border:1px solid var(--border); color:var(--fg); padding:8px; border-radius:4px; font-family:monospace;"/>
  </div>
  <textarea id="vote-comment" placeholder="optional comment (max 280)" rows="2" style="width:100%; background:#000; border:1px solid var(--border); color:var(--fg); padding:8px; border-radius:4px; font-family:monospace;"></textarea>
  <div style="margin-top:8px;"><button class="btn" id="vote-submit">cast vote</button>
  <span id="vote-msg" class="dim" style="margin-left:10px;"></span></div>
</div>
<div id="vote-results" style="margin-top:14px;">
{''.join(bar(o) for o in opts)}
</div>

<script>
(function() {{
  var selected = null;
  document.querySelectorAll('.vote-btn').forEach(function(b) {{
    b.addEventListener('click', function() {{
      document.querySelectorAll('.vote-btn').forEach(function(x) {{ x.classList.remove('selected'); }});
      b.classList.add('selected');
      selected = b.getAttribute('data-opt');
    }});
  }});
  document.getElementById('vote-submit').addEventListener('click', async function() {{
    if (!selected) {{ document.getElementById('vote-msg').textContent = 'pick an option first'; return; }}
    var body = {{
      handle: document.getElementById('vote-handle').value || '',
      option: selected,
      comment: document.getElementById('vote-comment').value || '',
      proposal: 'srp-contract'
    }};
    var r = await fetch('/api/vote', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(body) }});
    var d = await r.json();
    document.getElementById('vote-msg').textContent = d.ok ? ('voted: ' + d.label) : (d.error || 'error');
    if (d.ok) setTimeout(function(){{ location.reload(); }}, 600);
  }});
}})();
</script>
"""
