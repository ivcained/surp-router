"""Focused homepage for Surp: value, proof, then connection."""

CONTENT = r'''
<style>
.home-focus { max-width: 980px; margin: 0 auto; }
.home-hero { min-height: calc(100vh - 150px); display:flex; flex-direction:column; justify-content:center; padding:56px 0 72px; }
.home-hero h1 { max-width:780px; font-size:clamp(40px,7vw,76px); line-height:.98; letter-spacing:-3px; margin:0 0 22px; }
.home-lede { max-width:720px; color:var(--fg-dim); font-size:clamp(16px,2vw,20px); line-height:1.6; margin:0 0 30px; }
.home-actions { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.home-primary-cta { display:inline-flex; padding:13px 22px; color:#00150d; background:var(--accent); border:1px solid var(--accent); border-radius:4px; font-weight:800; text-decoration:none; box-shadow:0 0 22px rgba(0,255,156,.24); }
.home-primary-cta:hover { color:#00150d; text-decoration:none; transform:translateY(-1px); }
.home-secondary { color:var(--fg-dim); font-size:13px; }
.home-proof { display:flex; gap:28px; flex-wrap:wrap; margin-top:42px; padding-top:22px; border-top:1px solid var(--border); }
.home-proof span { color:var(--fg-dim); font-size:12px; }
.home-proof b { display:block; color:var(--accent); font-size:18px; margin-bottom:3px; }
.cache-tip { position:relative; display:inline-flex; align-items:center; gap:6px; }
.cache-tip button { width:18px; height:18px; border:1px solid var(--border-bright); border-radius:50%; background:transparent; color:var(--accent); font:inherit; font-size:11px; line-height:1; cursor:pointer; padding:0; }
.cache-tip button:hover, .cache-tip button:focus-visible { border-color:var(--accent); }
.cache-tip .tip {
  display:none; position:absolute; left:0; top:calc(100% + 8px); z-index:5; width:min(320px,70vw);
  padding:12px 14px; background:#07140e; border:1px solid var(--border-bright); color:var(--fg); font-size:12px; line-height:1.5;
  box-shadow:0 8px 24px rgba(0,0,0,.45);
}
.cache-tip:hover .tip, .cache-tip:focus-within .tip { display:block; }
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
.demo-custom { display:none; margin-top:14px; }
.demo-custom.open { display:block; }
.demo-custom .sliders { display:grid; gap:8px; }
.demo-custom label { display:flex; justify-content:space-between; gap:12px; color:var(--fg-dim); font-size:12px; }
.demo-custom input[type=range] { width:100%; accent-color:var(--accent); }
.demo-result { padding:22px; display:flex; flex-direction:column; justify-content:center; }
.demo-result .route { color:var(--accent); font-size:18px; font-weight:700; margin:8px 0; }
.demo-result .saving { color:#5ce1ff; font-size:28px; font-weight:800; }
.demo-result p { color:var(--fg-dim); font-size:12px; line-height:1.5; }
.agent-box { margin-top:22px; padding:18px; border:1px dashed var(--border-bright); background:#030503; }
.agent-box h3 { margin:0 0 8px; font-size:14px; color:var(--accent); }
.agent-box p { color:var(--fg-dim); font-size:13px; line-height:1.5; margin:0 0 12px; }
.agent-box pre { white-space:pre-wrap; word-break:break-word; background:#000; border:1px solid var(--border); padding:12px; color:var(--fg); font-size:12px; line-height:1.5; }
.agent-box .row { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
.agent-box button, .agent-box a.btn {
  padding:8px 12px; border:1px solid var(--border-bright); border-radius:4px; background:transparent;
  color:var(--accent); font:inherit; cursor:pointer; text-decoration:none;
}
.connection-steps { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:28px; }
.connection-step { padding:20px; border:1px solid var(--border); background:var(--bg-alt); }
.connection-step b { color:var(--accent); }
.connection-step p { color:var(--fg-dim); font-size:13px; line-height:1.5; }
.funding-path { border:1px solid var(--border); margin-top:10px; background:var(--bg-alt); }
.funding-path summary { padding:16px 18px; cursor:pointer; color:var(--fg); font-weight:700; }
.funding-path summary:hover { color:var(--accent); }
.funding-path div { padding:0 18px 18px; color:var(--fg-dim); font-size:13px; line-height:1.6; }
.funding-path code { color:var(--accent); }
.warn-note { margin-top:10px; padding:12px 14px; border:1px solid var(--border-bright); color:var(--fg); font-size:13px; line-height:1.5; }
.home-docs { padding:30px; border:1px dashed var(--border-bright); text-align:center; color:var(--fg-dim); }
.home-docs a { color:var(--accent); }
.home-quiet-links { display:flex; justify-content:center; gap:18px; flex-wrap:wrap; margin-top:18px; font-size:12px; }
@media(max-width:760px) { .home-hero { min-height:auto; padding:44px 0 56px; } .home-hero h1 { letter-spacing:-1.5px; } .demo-shell { grid-template-columns:1fr; } .demo-prompt { border-right:0; border-bottom:1px solid var(--border); } .connection-steps { grid-template-columns:1fr; } .cache-tip .tip { left:auto; right:0; } }
</style>

<div class="home-focus">
  <section class="home-hero">
    <h1>Spend less on every AI call.</h1>
    <p class="home-lede">Surp uses live SurplusIntelligence.ai market prices, picks a model for the route you choose, and reuses identical answers for $0.001. Pay in USDC on Base. No subscription.</p>
    <div class="home-actions">
      <a href="#try" class="home-primary-cta">Try it free</a>
      <a href="#connect" class="home-secondary">Connect your agent →</a>
    </div>
    <div class="home-proof">
      <span><b>145+ models</b>one OpenAI-compatible endpoint</span>
      <span class="cache-tip">
        <b>$0.001</b>
        <button type="button" aria-describedby="cache-tip-text" aria-label="What a cache hit costs">?</button>
        <span class="tip" id="cache-tip-text" role="tooltip">The system remembers answers to identical questions. You pay a fraction of a penny to reuse an old answer. You do not pay full price to make it again.</span>
        exact-response cache hit
      </span>
      <span><b>No subscription</b>pay only for requests you make</span>
    </div>
  </section>

  <section class="home-section" id="try">
    <span class="home-section-kicker">01 · see it before setup</span>
    <h2>Give Surp a route.</h2>
    <p class="home-section-intro">No wallet. No account. No API key. Start on Free. See which live model Surp would pick, then copy a prompt into your agent.</p>
    <div class="demo-shell">
      <div class="demo-prompt">
        <label for="demo-text">Your prompt</label>
        <textarea id="demo-text">Say only the word PONG.</textarea>
        <div class="demo-buttons" role="group" aria-label="route">
          <button class="active" data-mode="free">Free</button>
          <button data-mode="value">Value</button>
          <button data-mode="frontier">Frontier</button>
          <button data-mode="fast">Fast</button>
          <button data-mode="vision">Vision</button>
          <button data-mode="custom">Custom</button>
        </div>
        <div class="demo-custom" id="demo-custom">
          <p class="dim">Set how much intelligence, speed, and discount matter. Cost here is Surplus % off the AA list price.</p>
          <div class="sliders">
            <label>Intelligence <input id="w-intel" type="range" min="0" max="5" value="4"></label>
            <label>Speed <input id="w-speed" type="range" min="0" max="5" value="1"></label>
            <label>Discount <input id="w-cost" type="range" min="0" max="5" value="1"></label>
          </div>
        </div>
      </div>
      <div class="demo-result" aria-live="polite">
        <span class="dim">Surp would route this to</span>
        <div class="route" id="demo-route">surp/free</div>
        <span class="dim" id="demo-model-label">live model</span>
        <div class="saving" id="demo-price">loading…</div>
        <p id="demo-saving">Free route. Treasury pays Surplus. You pay $0 within the daily cap.</p>
      </div>
    </div>

    <div class="agent-box" id="agent-box">
      <h3>Copy this into your agent</h3>
      <p>Create a Surp key, then paste the prompt. This is not a SurplusIntelligence.ai key. The base URL is different.</p>
      <pre id="agent-prompt">Use Surp as my OpenAI-compatible provider.

Base URL: https://surp.ivc.lol/v1
API key: YOUR_SURP_KEY
Model: surp/free

Do not use https://api.surplusintelligence.ai/min30/v1/chat/completions
Do not expect a SurplusIntelligence balance here. This key only works on this base URL.</pre>
      <div class="row">
        <button type="button" id="btn-copy-prompt">Copy prompt</button>
        <button type="button" id="btn-make-key">Create a free key</button>
        <a class="btn" href="/app">Open account →</a>
      </div>
      <p id="key-status" class="dim" style="margin-top:10px"></p>
    </div>
  </section>

  <section class="home-section" id="connect">
    <span class="home-section-kicker">02 · connect when ready</span>
    <h2>From zero to first paid call.</h2>
    <p class="home-section-intro">Pick the path that matches how your agent already works. Funding details stay closed until you need them.</p>
    <div class="connection-steps">
      <div class="connection-step"><b>1 · Choose</b><p>Pick a route: <code>surp/free</code>, <code>surp/value</code>, <code>surp/frontier</code>, <code>surp/fast</code>, <code>surp/vision</code>, or <code>surp/custom</code>.</p></div>
      <div class="connection-step"><b>2 · Fund</b><p>Add USDC on Base to a wallet, or use a Surp API key. Pay in USDC on Base — this page does not sell crypto.</p></div>
      <div class="connection-step"><b>3 · Call</b><p>Send an OpenAI-compatible request to <code>https://surp.ivc.lol/v1</code>.</p></div>
    </div>

    <div class="warn-note">This is not your SurplusIntelligence login. Same marketplace. Different address. Different key. Your Surplus balance does not show here.<br>Surplus example: <code>https://api.surplusintelligence.ai/min30/v1/chat/completions</code><br>This router: <code>https://surp.ivc.lol/v1</code></div>

    <details class="funding-path" open>
      <summary>Connect Hermes</summary>
      <div>Install the plugin with <code>hermes plugins install ivcained/surp-hermes-x402-llm</code>, enable it, then use the free discovery and quote tools. Set the base URL to <code>https://surp.ivc.lol/v1</code>. <a href="/connect">Open the Hermes connection guide →</a></div>
    </details>
    <details class="funding-path">
      <summary>Pay from a wallet</summary>
      <div>Use USDC on Base. Surp returns an x402 payment challenge with the exact amount before the request is retried. Your wallet signs an EIP-3009 authorization; Surp never needs your private key. <a href="/x402">See the wallet flow →</a></div>
    </details>
    <details class="funding-path">
      <summary>Use an API key</summary>
      <div>Create a Surp key on this site. It is tied to this router, not to SurplusIntelligence.ai. Put the key in your agent secret store and call <code>https://surp.ivc.lol/v1/chat/completions</code>. <a href="/app">Open account and funding →</a></div>
    </details>
  </section>

  <section class="home-section">
    <div class="home-docs">
      <b>Technical details belong in the docs.</b>
      <p>Read about x402 settlement, cache fingerprints, route pools, benchmarks, model catalogs, and the gateway design when you need them. Intelligence scores: Artificial Analysis.</p>
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
  var custom = document.getElementById('demo-custom');
  var promptBox = document.getElementById('agent-prompt');
  var keyStatus = document.getElementById('key-status');
  var currentMode = 'free';
  var currentKey = 'YOUR_SURP_KEY';

  function weights() {
    var c = document.getElementById('w-cost').value;
    var i = document.getElementById('w-intel').value;
    var s = document.getElementById('w-speed').value;
    return c + ':' + i + ':' + s;
  }

  function setPrompt(mode, key) {
    currentKey = key || currentKey;
    promptBox.textContent =
      'Use Surp as my OpenAI-compatible provider.\n\n' +
      'Base URL: https://surp.ivc.lol/v1\n' +
      'API key: ' + currentKey + '\n' +
      'Model: surp/' + mode + '\n\n' +
      'Do not use https://api.surplusintelligence.ai/min30/v1/chat/completions\n' +
      'Do not expect a SurplusIntelligence balance here. This key only works on this base URL.';
  }

  function loadPreview(mode) {
    currentMode = mode;
    route.textContent = 'surp/' + mode;
    custom.className = 'demo-custom' + (mode === 'custom' ? ' open' : '');
    price.textContent = 'loading…';
    var qs = '/api/routes/preview?mode=' + encodeURIComponent(mode);
    if (mode === 'custom') qs += '&weights=' + encodeURIComponent(weights());
    fetch(qs).then(function (r) { return r.json(); }).then(function (data) {
      if (!data || data.error) {
        price.textContent = '—';
        saving.textContent = data && data.error ? data.error : 'Live market is not available. Try again.';
        return;
      }
      route.textContent = data.combo || ('surp/' + mode);
      if (data.model) {
        price.textContent = data.model;
      } else {
        price.textContent = 'no model';
      }
      if (mode === 'free') {
        saving.textContent = 'Free route. You pay $0 within the daily cap. Live model: ' + (data.model || 'n/a') + '.';
      } else if (data.discount_pct != null) {
        saving.textContent = (data.surplus_usd_per_1m != null ? ('$' + data.surplus_usd_per_1m + '/M Surplus. ') : '') +
          data.discount_pct + '% below the Artificial Analysis list price. ' + (data.description || '');
      } else {
        saving.textContent = (data.surplus_usd_per_1m != null ? ('$' + data.surplus_usd_per_1m + '/M Surplus. ') : '') +
          (data.description || 'Final price is quoted before payment.');
      }
      setPrompt(mode, currentKey);
    }).catch(function () {
      price.textContent = '—';
      saving.textContent = 'Live market is not available. Try again.';
    });
  }

  buttons.forEach(function (button) {
    button.addEventListener('click', function () {
      buttons.forEach(function (item) { item.classList.remove('active'); });
      button.classList.add('active');
      loadPreview(button.getAttribute('data-mode'));
    });
  });
  ['w-intel', 'w-speed', 'w-cost'].forEach(function (id) {
    document.getElementById(id).addEventListener('input', function () {
      if (currentMode === 'custom') loadPreview('custom');
    });
  });
  document.getElementById('btn-copy-prompt').addEventListener('click', function () {
    var text = promptBox.textContent;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text);
    }
    keyStatus.textContent = 'Prompt copied.';
  });
  document.getElementById('btn-make-key').addEventListener('click', function () {
    keyStatus.textContent = 'Creating a free key…';
    fetch('/api/free-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: 'homepage' })
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (!data || !data.key) {
        keyStatus.textContent = (data && data.error) || 'Could not create a key. Open /app instead.';
        return;
      }
      setPrompt(currentMode, data.key);
      keyStatus.textContent = 'Key created. It is in the prompt. Store it now — this page will not show it again.';
    }).catch(function () {
      keyStatus.textContent = 'Could not create a key. Open /app instead.';
    });
  });
  loadPreview('free');
})();
</script>
'''
