"""Focused homepage for Surp: value, proof, then connection."""

CONTENT = r'''
<style>
.home-focus { max-width: 980px; margin: 0 auto; }
.home-hero { min-height: calc(100vh - 150px); display:flex; flex-direction:column; justify-content:center; padding:56px 0 72px; }
.home-eyebrow { color:var(--accent); font-size:11px; letter-spacing:1.6px; text-transform:uppercase; margin-bottom:18px; }
.home-hero h1 { max-width:780px; font-size:clamp(40px,7vw,76px); line-height:.98; letter-spacing:-3px; margin:0 0 22px; }
.home-lede { max-width:720px; color:var(--fg-dim); font-size:clamp(16px,2vw,20px); line-height:1.6; margin:0 0 30px; }
.home-actions { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.home-primary-cta { display:inline-flex; padding:13px 22px; color:#00150d; background:var(--accent); border:1px solid var(--accent); border-radius:4px; font-weight:800; text-decoration:none; box-shadow:0 0 22px rgba(0,255,156,.24); }
.home-primary-cta:hover { color:#00150d; text-decoration:none; transform:translateY(-1px); }
.home-secondary { color:var(--fg-dim); font-size:13px; }
.home-proof { display:flex; gap:28px; flex-wrap:wrap; margin-top:42px; padding-top:22px; border-top:1px solid var(--border); }
.home-proof span { color:var(--fg-dim); font-size:12px; }
.home-proof b { display:block; color:var(--accent); font-size:18px; margin-bottom:3px; }
.home-section { padding:72px 0; border-top:1px solid var(--border); }
.home-section-kicker { color:var(--accent); font-size:10px; letter-spacing:1.5px; text-transform:uppercase; }
.home-section h2 { font-size:clamp(26px,4vw,42px); margin:10px 0 12px; }
.home-section-intro { max-width:680px; color:var(--fg-dim); font-size:16px; line-height:1.6; }
.demo-shell { margin-top:26px; display:grid; grid-template-columns:minmax(0,1.3fr) minmax(260px,.7fr); border:1px solid var(--border-bright); background:var(--bg-alt); }
.demo-prompt { padding:22px; border-right:1px solid var(--border); }
.demo-prompt label { display:block; color:var(--fg-dim); font-size:11px; margin-bottom:9px; }
.demo-prompt textarea { width:100%; min-height:96px; resize:vertical; box-sizing:border-box; background:#030503; color:var(--fg); border:1px solid var(--border-bright); border-radius:4px; padding:13px; font:inherit; }
.demo-buttons { display:flex; gap:9px; margin-top:12px; flex-wrap:wrap; }
.demo-buttons button { padding:9px 13px; border:1px solid var(--border-bright); border-radius:4px; background:transparent; color:var(--fg-dim); font:inherit; cursor:pointer; }
.demo-buttons button.active,.demo-buttons button:hover { border-color:var(--accent); color:var(--accent); }
.demo-result { padding:22px; display:flex; flex-direction:column; justify-content:center; }
.demo-result .route { color:var(--accent); font-size:18px; font-weight:700; margin:8px 0; }
.demo-result .saving { color:#5ce1ff; font-size:28px; font-weight:800; }
.demo-result p { color:var(--fg-dim); font-size:12px; line-height:1.5; }
.connection-steps { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:28px; }
.connection-step { padding:20px; border:1px solid var(--border); background:var(--bg-alt); }
.connection-step b { color:var(--accent); }
.connection-step p { color:var(--fg-dim); font-size:13px; line-height:1.5; }
.funding-path { border:1px solid var(--border); margin-top:10px; background:var(--bg-alt); }
.funding-path summary { padding:16px 18px; cursor:pointer; color:var(--fg); font-weight:700; }
.funding-path summary:hover { color:var(--accent); }
.funding-path div { padding:0 18px 18px; color:var(--fg-dim); font-size:13px; line-height:1.6; }
.funding-path code { color:var(--accent); }
.home-docs { padding:30px; border:1px dashed var(--border-bright); text-align:center; color:var(--fg-dim); }
.home-docs a { color:var(--accent); }
.home-quiet-links { display:flex; justify-content:center; gap:18px; flex-wrap:wrap; margin-top:18px; font-size:12px; }
@media(max-width:760px) { .home-hero { min-height:auto; padding:44px 0 56px; } .home-hero h1 { letter-spacing:-1.5px; } .demo-shell { grid-template-columns:1fr; } .demo-prompt { border-right:0; border-bottom:1px solid var(--border); } .connection-steps { grid-template-columns:1fr; } }
</style>

<div class="home-focus">
  <section class="home-hero">
    <div class="home-eyebrow">Surplus prices + smart routing + a 10× cheaper repeat cache</div>
    <h1>Spend less on every AI call.</h1>
    <p class="home-lede">Surp checks the live Surplus marketplace, routes each job to the lowest-cost suitable model, and serves exact repeated answers from cache for $0.001. Connect once; your agent keeps shopping.</p>
    <div class="home-actions">
      <a href="#try" class="home-primary-cta">Try it free</a>
      <a href="#connect" class="home-secondary">Already convinced? Connect your agent →</a>
    </div>
    <div class="home-proof">
      <span><b>145+ models</b>one OpenAI-compatible endpoint</span>
      <span><b>$0.001</b>exact-response cache hit</span>
      <span><b>No subscription</b>pay only for requests you make</span>
    </div>
  </section>

  <section class="home-section" id="try">
    <span class="home-section-kicker">01 · see it before setup</span>
    <h2>Give Surp a job.</h2>
    <p class="home-section-intro">No wallet. No account. No API key. Choose the kind of work and see which route Surp would use at the current market price.</p>
    <div class="demo-shell">
      <div class="demo-prompt">
        <label for="demo-text">Your prompt</label>
        <textarea id="demo-text">Write a Python function that deduplicates a list while preserving order.</textarea>
        <div class="demo-buttons" role="group" aria-label="work class">
          <button class="active" data-route="surp/best-coding" data-price="$0.33/M" data-saving="96%">coding</button>
          <button data-route="surp/best-chat" data-price="$0.03/M" data-saving="99%">chat</button>
          <button data-route="surp/best-fast" data-price="$0.04/M" data-saving="99%">fast</button>
          <button data-route="surp/free" data-price="$0.00" data-saving="free">free</button>
        </div>
      </div>
      <div class="demo-result" aria-live="polite">
        <span class="dim">Surp would route this to</span>
        <div class="route" id="demo-route">surp/best-coding</div>
        <span class="dim">current estimated rate</span>
        <div class="saving" id="demo-price">$0.33/M</div>
        <p id="demo-saving">about 96% below the reference frontier price. Final price is quoted before payment.</p>
        <a href="/playground">Run a real free request →</a>
      </div>
    </div>
  </section>

  <section class="home-section" id="connect">
    <span class="home-section-kicker">02 · connect when ready</span>
    <h2>From zero to first paid call.</h2>
    <p class="home-section-intro">Pick the path that matches how your agent already works. Funding details stay closed until you need them.</p>
    <div class="connection-steps">
      <div class="connection-step"><b>1 · Choose</b><p>Use a smart route such as <code>surp/best-chat</code>, or choose an exact model.</p></div>
      <div class="connection-step"><b>2 · Fund</b><p>Add USDC on Base to a wallet, or use a Surp API key for simpler billing.</p></div>
      <div class="connection-step"><b>3 · Call</b><p>Your agent receives a quote, confirms spend, and sends the OpenAI-compatible request.</p></div>
    </div>

    <details class="funding-path" open>
      <summary>Connect Hermes</summary>
      <div>Install the plugin with <code>hermes plugins install ivcained/surp-hermes-x402-llm</code>, enable it, then use the free discovery and quote tools. <a href="/connect">Open the Hermes connection guide →</a></div>
    </details>
    <details class="funding-path">
      <summary>Pay from a wallet</summary>
      <div>Use USDC on Base. Surp returns an x402 payment challenge with the exact amount before the request is retried. Your wallet signs an EIP-3009 authorization; Surp never needs your private key. <a href="/x402">See the wallet flow →</a></div>
    </details>
    <details class="funding-path">
      <summary>Use an API key</summary>
      <div>Create or connect an account, fund a balance, and put the API key in your agent's secret store. This avoids signing each request manually. <a href="/app">Open account and funding →</a></div>
    </details>
  </section>

  <section class="home-section">
    <div class="home-docs">
      <b>Technical details belong in the docs.</b>
      <p>Read about x402 settlement, cache fingerprints, route pools, benchmarks, model catalogs, and the gateway design when you need them.</p>
      <a href="/docs">Read the documentation →</a>
      <div class="home-quiet-links"><a href="/prices">compare prices</a><a href="/status">system status</a><a href="/builder">build a route</a><a href="/system-design">system design</a></div>
    </div>
  </section>
</div>

<script>
(function () {
  var buttons = document.querySelectorAll('.demo-buttons button');
  var route = document.getElementById('demo-route');
  var price = document.getElementById('demo-price');
  var saving = document.getElementById('demo-saving');
  buttons.forEach(function (button) {
    button.addEventListener('click', function () {
      buttons.forEach(function (item) { item.classList.remove('active'); });
      button.classList.add('active');
      route.textContent = button.getAttribute('data-route');
      price.textContent = button.getAttribute('data-price');
      var amount = button.getAttribute('data-saving');
      saving.textContent = amount === 'free' ? 'Treasury-sponsored route with live limits.' : 'about ' + amount + ' below the reference frontier price. Final price is quoted before payment.';
    });
  });
})();
</script>
'''
