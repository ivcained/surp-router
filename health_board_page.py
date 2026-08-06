"""Live free model health board with auto-ranking."""

TITLE = "Free Model Health Board — Live TPS, Latency & Reliability | surp.ivc.lol"
DESC = ("Live provider health board: TPS, p50/p95 latency, failure rate, and "
        "composite health score for every model surp has routed. Fills the gap "
        "left by the Surplus Intelligence marketplace dashboard.")


def _fmt(n: float | int) -> str:
    if isinstance(n, float) and n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if isinstance(n, (int, float)) and n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if isinstance(n, (int, float)) and n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def content(ranked: list[dict], conversion: dict, free_stats: dict) -> str:
    rows = ""
    for i, m in enumerate(ranked[:60], 1):
        score = m.get("health_score", 0)
        color = "#5ce1ff" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
        rows += (
            f"<tr>"
            f"<td>{i}</td>"
            f"<td class='model'>{m['model']}</td>"
            f"<td><span style='color:{color};font-weight:bold;'>{score:.1f}</span></td>"
            f"<td>{m['requests']}</td>"
            f"<td>{m['failures']}</td>"
            f"<td>{m['failure_rate']*100:.1f}%</td>"
            f"<td>{m['p50_latency_ms']}ms</td>"
            f"<td>{m['p95_latency_ms']}ms</td>"
            f"<td>{m['mean_latency_ms']:.0f}ms</td>"
            f"<td>{m['tps']:.2f}</td>"
            f"<td>{_fmt(m['tokens'])}</td>"
            f"</tr>"
        )
    if not rows:
        rows = '<tr><td colspan="11" class="dim">No routing samples yet. Health scores populate as requests flow through the gateway.</td></tr>'

    top_conv = "".join(
        f"<tr><td class='model'>surp/{x['to_combo']}</td><td>{x['n']}</td></tr>"
        for x in conversion.get("top_paid_combos", [])
    ) or '<tr><td colspan="2" class="dim">No conversions recorded yet.</td></tr>'

    return f"""
<h1>free model health board</h1>
<p class="dim prompt">live TPS, latency, and failure rate — the metrics the SI dashboard doesn't show.</p>

<p>The <a href="https://www.surplusintelligence.ai/markets">Surplus Intelligence marketplace</a> exposes pricing, liquidity, and 24h volume for each model — but not <b>TPS</b>, <b>wall-clock latency</b>, or <b>per-provider failure rates</b>. So we measure them ourselves. Every request routed through surp feeds this board, and the resulting health scores feed back into routing: cheap-and-flaky loses to slightly-pricier-but-reliable.</p>

<div class="warn"><b>why this matters:</b> A model listed at $0.01/M with 50 active offers might still be the wrong choice if it 500s half the time or takes 8 seconds to respond. Price is one signal; reliability is another. This board makes both visible.</div>

<h2>composite health ranking</h2>
<p>Models are ranked by a composite 0-100 score: <b>reliability (60%)</b> × <b>speed (30%)</b> × <b>throughput (10%)</b>. Green ≥ 70, amber 40-69, red &lt; 40.</p>
<div style="overflow-x:auto;">
<table><thead><tr>
<th>#</th><th>model</th><th>health</th><th>requests</th><th>failures</th><th>failure rate</th>
<th>p50 latency</th><th>p95 latency</th><th>mean latency</th><th>TPS</th><th>tokens</th>
</tr></thead><tbody>{rows}</tbody></table>
</div>

<h2>methodology</h2>
<ul style="margin-left:20px;line-height:1.8;">
<li><b>Window:</b> rolling 1 hour (configurable via <code>SURP_HEALTH_WINDOW</code>).</li>
<li><b>TPS:</b> requests / elapsed window seconds.</li>
<li><b>p50/p95:</b> percentile of successful-request latencies (interpolated).</li>
<li><b>Failure rate:</b> non-ok responses / total responses.</li>
<li><b>Health score:</b> <code>(1 - failure_rate) × 60 + speed_norm × 30 + min(1, TPS) × 10</code>, where <code>speed_norm = (2000 - p50) / 1950</code> clamped to [0,1].</li>
<li><b>Pruning:</b> samples older than 24h are deleted automatically.</li>
</ul>

<h2>free-to-paid conversion</h2>
<p>How many free-tier users have upgraded to a paid combo, and which one they chose. This is the metric that tells us whether the free tier is doing its job — bootstrapping usage — without permanently subsidizing freeloaders.</p>
<div class="grid">
  <div class="card"><div class="num">{conversion.get('free_users', 0)}</div><div class="lbl">distinct free users</div></div>
  <div class="card"><div class="num">{conversion.get('conversions', 0)}</div><div class="lbl">upgraded to paid</div></div>
  <div class="card"><div class="num">{conversion.get('conversion_rate_pct', 0)}%</div><div class="lbl">conversion rate</div></div>
  <div class="card"><div class="num">{free_stats.get('requests_today', 0)}</div><div class="lbl">free requests today</div></div>
</div>
<h3>top paid combos chosen by free users</h3>
<table><thead><tr><th>paid combo</th><th>conversions</th></tr></thead><tbody>{top_conv}</tbody></table>

<h2>what this enables</h2>
<ul style="margin-left:20px;line-height:1.8;">
<li><b>Smarter free routing:</b> the free pool can prefer reliable models, not just the absolute cheapest.</li>
<li><b>Provider accountability:</b> sellers who degrade get visible — not hidden behind a static offer count.</li>
<li><b>Capacity planning:</b> TPS trends reveal which providers are scaling and which are stagnating.</li>
<li><b>Community good:</b> this data doesn't exist anywhere else. We can publish it as a public good.</li>
</ul>

<p class="dim">related: <a href="/free-models">free models &amp; live budget</a> · <a href="/status">system status</a> · <a href="/cache">cache-aware routing</a> · <a href="/proposal">reward proposal</a></p>
"""
