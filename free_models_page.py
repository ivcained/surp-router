"""Public live dashboard for free models and sponsored inference."""

TITLE = "Free AI Models — Live Sponsored LLM API | surp.ivc.lol"
DESC = ("Use surp/free for genuinely free, treasury-sponsored AI inference. "
        "See live eligible models, daily budgets, fallback health, and OmniRoute-inspired free-tier intelligence.")


def _fmt(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def content(sponsored: list[dict], stats: dict, catalog: dict) -> str:
    rows = ""
    for i, m in enumerate(sponsored[:50], 1):
        rows += (
            f"<tr><td>{i}</td><td class='model'>{m['model']}</td>"
            f"<td class='price'>${m['usd_per_1m']:.4f}</td>"
            f"<td>{m['healthy_sellers']}</td><td>{m['requests_24h']:,}</td>"
            f"<td>{m['volume_24h']:,}</td></tr>"
        )
    if not rows:
        rows = '<tr><td colspan="6" class="dim">No live model currently meets the sponsored-free guardrails. The paid gateway remains available.</td></tr>'

    allc = catalog["all"]
    safe = catalog["excluding_tos_avoid"]
    tos = allc["tos_counts"]
    top_rows = "".join(
        f"<tr><td class='model'>{x['model']}</td><td>{x['requests']}</td><td>{x['tokens']:,}</td></tr>"
        for x in stats.get("top_models", [])
    ) or '<tr><td colspan="3" class="dim">No free requests served today yet.</td></tr>'

    return f"""
<h1>free AI models</h1>
<p class="dim prompt">surp/free — real responses, zero payment, treasury-sponsored.</p>

<p><b>surp/free</b> gives users genuinely free LLM inference through the same OpenAI-compatible endpoint. There is no x402 payment challenge and no API key. The surp treasury pays the upstream model cost, with strict daily budgets, per-IP limits, cheap-model guardrails, and automatic fallback.</p>

<div class="warn"><b>important:</b> We do not resell or proxy personal free-tier credentials from OmniRoute's catalog. Many provider free tiers prohibit proxying or third-party access. OmniRoute's MIT-licensed methodology powers our catalog intelligence; actual public inference is purchased through our normal Surplus account and sponsored by surp.</div>

<h2>try it now</h2>
<pre>curl -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{{"model":"surp/free",
       "messages":[{{"role":"user","content":"Explain x402 in one sentence"}}],
       "max_tokens":64,
       "stream":false}}'</pre>
<p class="dim">Limits: {stats['per_ip_daily_requests']} requests/IP/day · {stats['max_output_tokens']} max output tokens · non-streaming · no tool calls · availability is best-effort.</p>

<h2>live sponsored budget (UTC)</h2>
<div class="grid">
  <div class="card"><div class="num">{stats['requests_remaining']}</div><div class="lbl">requests remaining today</div></div>
  <div class="card"><div class="num">{_fmt(stats['tokens_remaining'])}</div><div class="lbl">tokens remaining today</div></div>
  <div class="card"><div class="num">{len(sponsored)}</div><div class="lbl">eligible live models</div></div>
  <div class="card"><div class="num">{stats['avg_latency_ms']:.0f}ms</div><div class="lbl">average free latency</div></div>
</div>
<table><tbody>
<tr><td class="dim">requests served today</td><td>{stats['requests_today']} / {stats['request_budget']}</td></tr>
<tr><td class="dim">tokens served today</td><td>{stats['tokens_today']:,} / {stats['token_budget']:,}</td></tr>
<tr><td class="dim">failed upstream attempts</td><td>{stats['failures_today']}</td></tr>
<tr><td class="dim">maximum sponsored model price</td><td>${stats['max_model_usd_per_1m']:.4f} / 1M tokens</td></tr>
<tr><td class="dim">fallback attempts per request</td><td>up to 3 live models</td></tr>
</tbody></table>

<h2>live models we may sponsor</h2>
<p>These are real, liquid Surplus marketplace models currently below the configured treasury ceiling. The router tries the cheapest first and falls back when a seller is unavailable.</p>
<table><thead><tr><th>#</th><th>model</th><th>USD/1M</th><th>healthy sellers</th><th>requests 24h</th><th>volume 24h</th></tr></thead><tbody>{rows}</tbody></table>

<h2>models actually served today</h2>
<table><thead><tr><th>model</th><th>free requests</th><th>tokens</th></tr></thead><tbody>{top_rows}</tbody></table>

<h2>what we adopted from OmniRoute</h2>
<p><a href="https://github.com/diegosouzapw/OmniRoute">OmniRoute</a> is an MIT-licensed AI gateway with an unusually careful free-tier catalog. We incorporated the parts that improve honesty and transparency:</p>
<ul style="margin-left:20px;line-height:1.8;">
<li><b>Pool deduplication:</b> if ten models share one provider quota, count the pool once using its maximum—not ten times.</li>
<li><b>Recurring vs one-time separation:</b> signup credits never inflate the steady monthly headline.</li>
<li><b>Uncapped-provider honesty:</b> permanently free providers with no published token cap are listed but never multiplied by RPM × 24/7.</li>
<li><b>ToS risk labels:</b> each catalog entry is classified as ok, ambiguous, caution, avoid, or unknown.</li>
<li><b>Quota visibility:</b> used, remaining, reset/budget limits and actual served models are public.</li>
<li><b>Automatic fallback:</b> failed free models are skipped and the next live candidate is tried.</li>
</ul>

<h2>OmniRoute free-tier catalog snapshot</h2>
<p class="dim">Source: OmniRoute <code>{catalog['branch']}</code>, curated {catalog['curated_at']}, MIT License. Snapshot stored with license attribution in this repository.</p>
<div class="grid">
  <div class="card"><div class="num">{_fmt(allc['steady_recurring_tokens'])}</div><div class="lbl">documented recurring tokens/month</div></div>
  <div class="card"><div class="num">{_fmt(allc['first_month_realistic_tokens'])}</div><div class="lbl">realistic first month + credits</div></div>
  <div class="card"><div class="num">{allc['pool_count']}</div><div class="lbl">deduped recurring pools</div></div>
  <div class="card"><div class="num">{allc['model_count']}</div><div class="lbl">catalog model entries</div></div>
</div>
<table><tbody>
<tr><td class="dim">providers represented</td><td>{allc['provider_count']}</td></tr>
<tr><td class="dim">permanently free, uncapped providers</td><td>{len(allc['uncapped_providers'])} (listed, never summed)</td></tr>
<tr><td class="dim">ToS generally ok</td><td>{tos.get('ok',0)}</td></tr>
<tr><td class="dim">ToS ambiguous</td><td>{tos.get('ambiguous',0)}</td></tr>
<tr><td class="dim">ToS caution</td><td>{tos.get('caution',0)}</td></tr>
<tr><td class="dim">ToS avoid</td><td>{tos.get('avoid',0)}</td></tr>
<tr><td class="dim">catalog entries after excluding avoid</td><td>{safe['model_count']}</td></tr>
</tbody></table>

<h2>why not directly pool all those free tiers?</h2>
<p>Because "free" often means free for one developer's account—not free to resell through a public proxy. OmniRoute itself surfaces these ToS risks. surp will only integrate a third-party free provider into public routing when its terms explicitly allow proxying/resale or we have written permission. Until then, the catalog is informational and our public free requests are treasury-sponsored.</p>

<h2>failure behavior</h2>
<ul style="margin-left:20px;line-height:1.8;">
<li>If a model has no healthy sellers, it is excluded before routing.</li>
<li>If the first model returns an error, the router tries up to two more candidates.</li>
<li>If the daily global budget is exhausted, the API returns HTTP 429 with a paid x402 alternative.</li>
<li>If one IP reaches its daily allowance, only that client is throttled.</li>
<li>If every sponsored model fails, the API returns structured JSON—never a paid settlement followed by an HTML 500.</li>
</ul>

<p class="dim">related: <a href="/status">live system status</a> · <a href="/cache">cache-aware routing</a> · <a href="/proposal">reward proposal</a> · <a href="/token-gating">token-gated access</a> · <a href="/docs">API docs</a></p>
"""
