"""Public performance/benchmark page — verified generation throughput."""

TITLE = "Verified LLM Performance — Real Output TPS, TTFT & Throughput per Dollar | surp.ivc.lol"
DESC = ("Independently verified LLM generation throughput: output tokens/second, "
        "time-to-first-token, and throughput-per-dollar for every model on surp. "
        "No vendor claims — only measured data from real streaming requests.")


def _fmt_score(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def content(ranked: list[dict], recent: dict) -> str:
    rows = ""
    for i, m in enumerate(ranked[:30], 1):
        tps = m.get("p50_output_tps", 0)
        color = "#5ce1ff" if tps >= 80 else "#f59e0b" if tps >= 40 else "#ef4444"
        rows += (
            f"<tr>"
            f"<td>{i}</td>"
            f"<td class='model'>{m['model']}</td>"
            f"<td><span style='color:{color};font-weight:bold;'>{tps:.1f}</span></td>"
            f"<td>{m.get('p95_output_tps',0):.1f}</td>"
            f"<td>{m.get('min_output_tps',0):.1f}-{m.get('max_output_tps',0):.1f}</td>"
            f"<td>{m.get('p50_ttft_ms',0)}ms</td>"
            f"<td>${m.get('median_price_usd_per_1m',0):.4f}</td>"
            f"<td>{_fmt_score(m.get('throughput_value_score',0))}</td>"
            f"<td>{m.get('successful_runs',0)}/{m.get('runs',0)}</td>"
            f"</tr>"
        )
    if not rows:
        rows = '<tr><td colspan="9" class="dim">No benchmarks recorded yet. Run <code>python3 benchmark_runner.py</code> to generate verified data.</td></tr>'

    # Recent raw observations for the top model (auditability)
    audit_rows = ""
    top_model = ranked[0]["model"] if ranked else None
    if top_model and recent:
        for r in recent[:10]:
            audit_rows += (
                f"<tr>"
                f"<td>{r.get('output_tps',0):.1f}</td>"
                f"<td>{r.get('ttft_ms',0)}ms</td>"
                f"<td>{r.get('wall_ms',0)}ms</td>"
                f"<td>{r.get('output_tokens',0)}</td>"
                f"<td>${r.get('price_usd_per_1m',0):.4f}</td>"
                f"<td>{r.get('status','')}</td>"
                f"</tr>"
            )

    return f"""
<h1>verified llm performance</h1>
<p class="dim prompt">real output TPS, TTFT, and throughput-per-dollar — measured, not claimed.</p>

<p>Every number on this page comes from a <b>real streaming request</b> sent through surp to the Surplus Intelligence marketplace. No vendor spec sheets, no extrapolated benchmarks — only observed generation throughput. This is the data the Surplus dashboard doesn't show.</p>

<div class="warn"><b>why this matters:</b> A model listing at $0.01/M might sound cheap, but if it generates at 20 tokens/second, a 1000-token response takes 50 seconds. A model at $0.06/M generating at 100 TPS delivers the same response in 10 seconds. <b>Throughput-per-dollar</b> is the metric that actually determines your cost-per-task. We measure it directly.</p></div>

<h2>throughput leaderboard</h2>
<p>Models ranked by <b>throughput-value score</b> (p50 output TPS × tokens-per-dollar). Green ≥ 80 TPS, amber 40-79, red &lt; 40.</p>
<div style="overflow-x:auto;">
<table><thead><tr>
<th>#</th><th>model</th><th>p50 TPS</th><th>p95 TPS</th><th>range</th>
<th>p50 TTFT</th><th>price /1M</th><th>throughput/$</th><th>runs</th>
</tr></thead><tbody>{rows}</tbody></table>
</div>

<h2>what "output TPS" means</h2>
<p><b>Output TPS</b> = generated completion tokens ÷ generation seconds (time from first token to last token). This is the metric LLM buyers care about: how fast the model produces text.</p>
<p>This is <b>different from request RPS</b> (requests per second), which measures how many separate requests the gateway handles. The <a href="/health">health board</a> tracks RPS; this page tracks output TPS.</p>

<h2>methodology</h2>
<ul style="margin-left:20px;line-height:1.8;">
<li><b>Real requests:</b> each run sends a streaming <code>POST /v1/chat/completions</code> through surp with <code>max_tokens=400</code>.</li>
<li><b>TTFT:</b> time from request submission to first output token (time-to-first-token).</li>
<li><b>Generation time:</b> wall time − TTFT (time spent generating, excluding queue/TTFT).</li>
<li><b>Output TPS:</b> <code>completion_tokens / generation_seconds</code>.</li>
<li><b>Throughput-value score:</b> <code>p50_output_tps × (1,000,000 / price_per_1m)</code> — higher is better.</li>
<li><b>p50/p95:</b> percentile across all successful runs in the window.</li>
<li><b>Token counting:</b> prefers <code>usage.completion_tokens</code> from the API; falls back to <code>len(text)/4</code> estimate if usage is absent.</li>
<li><b>No cherry-picking:</b> all runs (including slow ones) are recorded. Failed runs count against the failure rate.</li>
</ul>

{"<h2>recent observations: " + top_model + "</h2><p class='dim'>Last 10 raw runs — verify the numbers yourself.</p><table><thead><tr><th>output TPS</th><th>TTFT</th><th>wall</th><th>tokens</th><th>price/1M</th><th>status</th></tr></thead><tbody>" + audit_rows + "</tbody></table>" if top_model else ""}

<h2>try it yourself</h2>
<p>The benchmark runner is open source. Clone the repo and run:</p>
<pre>python3 benchmark_runner.py --model deepseek-v4-flash-0731 --runs 10 --api-key sk-sur-...</pre>
<p>You'll get the same kind of numbers we publish here. Or just make a streaming request and time it:</p>
<pre>curl -N -X POST https://surp.ivc.lol/v1/chat/completions \\
  -H "Authorization: Bearer sk-sur-..." \\
  -H "Content-Type: application/json" \\
  -d '{{"model":"surp/direct/deepseek-v4-flash-0731",
       "messages":[{{"role":"user","content":"Write 200 words about HTTP/2"}}],
       "max_tokens":400,
       "stream":true}}'</pre>

<p class="dim">related: <a href="/health">provider health board (RPS, latency)</a> · <a href="/free-models">free models</a> · <a href="/auction">cache-affinity auction</a> · <a href="/api/benchmarks">benchmark API</a></p>
"""
