"""Focused homepage for Surp: value, proof, then connection."""

CONTENT = r'''
<style>
:root {
  --focus-ring: 0 0 0 2px #000, 0 0 0 4px var(--accent);
}
.home-focus { max-width: 980px; margin: 0 auto; }
.home-hero { min-height: calc(100vh - 160px); display:flex; flex-direction:column; justify-content:center; padding:56px 0 64px; }
.home-hero h1 { max-width:820px; font-size:clamp(38px,7vw,74px); line-height:1.02; letter-spacing:-2.5px; margin:0 0 20px; font-weight:800; color:var(--accent); text-shadow:0 0 16px rgba(0,255,156,.28); }
.home-lede { max-width:720px; color:var(--fg); font-size:clamp(15px,2vw,18px); line-height:1.65; margin:0 0 28px; font-weight:400; }
.home-actions { display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
.home-primary-cta { display:inline-flex; align-items:center; justify-content:center; min-height:44px; padding:12px 24px; color:#00150d; background:var(--accent); border:1px solid var(--accent); border-radius:4px; font-size:15px; font-weight:800; letter-spacing:0.2px; text-decoration:none; box-shadow:0 0 24px rgba(0,255,156,.28); transition:transform .15s, box-shadow .15s; }
.home-primary-cta:hover { color:#00150d; text-decoration:none; transform:translateY(-1px); box-shadow:0 0 32px rgba(0,255,156,.42); }
.home-primary-cta:focus-visible { outline:none; box-shadow:var(--focus-ring); }
.home-secondary { display:inline-flex; align-items:center; min-height:44px; color:var(--fg-dim); font-size:14px; text-decoration:none; transition:color .15s; padding:0 4px; }
.home-secondary:hover { color:var(--accent); text-decoration:underline; }
.home-secondary:focus-visible { outline:none; box-shadow:var(--focus-ring); border-radius:2px; }
.home-proof { display:flex; gap:32px; flex-wrap:wrap; margin-top:40px; padding-top:20px; border-top:1px solid var(--border); }
.home-proof-item { display:flex; flex-direction:column; gap:4px; }
.home-proof-item b { color:var(--accent); font-size:18px; font-weight:700; }
.home-proof-item span { color:var(--fg-dim); font-size:12px; line-height:1.4; }
.cache-tip { position:relative; display:inline-flex; align-items:center; gap:6px; cursor:help; }
.cache-tip button { min-width:24px; min-height:24px; border:1px solid var(--border-bright); border-radius:50%; background:transparent; color:var(--accent); font:inherit; font-size:12px; line-height:1; cursor:pointer; padding:0; display:inline-flex; align-items:center; justify-content:center; }
.cache-tip button:hover, .cache-tip button:focus-visible { border-color:var(--accent); outline:none; box-shadow:var(--focus-ring); }
.cache-tip .tip {
  display:none; position:absolute; left:0; top:calc(100% + 8px); z-index:20; width:min(340px,80vw);
  padding:12px 14px; background:#07140e; border:1px solid var(--accent-dim); border-radius:4px; color:var(--fg); font-size:12px; line-height:1.5;
  box-shadow:0 12px 32px rgba(0,0,0,.65); pointer-events:none;
}
.cache-tip:hover .tip, .cache-tip:focus-within .tip { display:block; }
.home-section { padding:64px 0; border-top:1px solid var(--border); }
.home-section h2 { font-size:clamp(26px,4.5vw,40px); line-height:1.15; letter-spacing:-1px; margin:0 0 10px; color:var(--accent); border-bottom:0; padding-bottom:0; }
.home-section-intro { max-width:680px; color:var(--fg-dim); font-size:15px; line-height:1.65; margin-bottom:24px; }
.demo-shell { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(280px,.85fr); border:1px solid var(--border-bright); background:var(--bg-alt); border-radius:4px; }
.demo-prompt { padding:20px; border-right:1px solid var(--border); }
.demo-prompt label { display:block; color:var(--fg-dim); font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; }
.demo-prompt textarea { width:100%; min-height:96px; resize:vertical; box-sizing:border-box; background:#030503; color:var(--fg); border:1px solid var(--border-bright); border-radius:4px; padding:12px 14px; font:inherit; font-size:13px; line-height:1.5; }
.demo-prompt textarea:focus-visible { outline:none; border-color:var(--accent); box-shadow:var(--focus-ring); }
.demo-buttons-label { display:block; color:var(--fg-dim); font-size:11px; text-transform:uppercase; letter-spacing:1px; margin:16px 0 8px; }
.demo-buttons { display:flex; gap:8px; flex-wrap:wrap; }
.demo-buttons button { min-height:40px; padding:8px 14px; border:1px solid var(--border-bright); border-radius:4px; background:transparent; color:var(--fg-dim); font:inherit; font-size:13px; cursor:pointer; transition:all .15s; }
.demo-buttons button:hover { border-color:var(--accent-dim); color:var(--fg); }
.demo-buttons button:focus-visible { outline:none; box-shadow:var(--focus-ring); border-color:var(--accent); }
.demo-buttons button.active { border-color:var(--accent); color:var(--accent); background:rgba(0,255,156,.06); font-weight:700; }
.demo-buttons button.active:focus-visible { outline:none; box-shadow:var(--focus-ring); }
.demo-custom { display:none; margin-top:16px; padding-top:14px; border-top:1px dashed var(--border); }
.demo-custom.open { display:block; }
.demo-custom p { margin-bottom:10px; font-size:12px; }
.demo-custom .sliders { display:grid; gap:10px; }
.demo-custom label { display:flex; justify-content:space-between; align-items:center; gap:14px; color:var(--fg); font-size:12px; min-height:36px; }
.demo-custom input[type=range] { flex:1; max-width:180px; min-height:32px; accent-color:var(--accent); cursor:pointer; }
.demo-custom input[type=range]:focus-visible { outline:none; box-shadow:var(--focus-ring); }
.demo-result { padding:20px; display:flex; flex-direction:column; justify-content:center; background:#030704; min-height:220px; }
.demo-result .route-label { color:var(--fg-dim); font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }
.demo-result .route { color:var(--accent); font-size:20px; font-weight:800; margin-bottom:12px; letter-spacing:-0.5px; word-break:break-word; }
.demo-result .model-label { color:var(--fg-dim); font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:2px; }
.demo-result .saving { color:#5ce1ff; font-size:22px; font-weight:800; line-height:1.2; margin-bottom:10px; word-break:break-word; }
.demo-result .detail { color:var(--fg-dim); font-size:12px; line-height:1.6; }
.demo-result .err-state { color:#ff8080; }
.demo-result .retry-btn { margin-top:10px; padding:6px 12px; border:1px solid #ff8080; border-radius:4px; background:transparent; color:#ff8080; font:inherit; font-size:12px; cursor:pointer; align-self:flex-start; }
.demo-result .retry-btn:hover { background:rgba(255,128,128,.1); }
.demo-result .retry-btn:focus-visible { outline:none; box-shadow:var(--focus-ring); }
.agent-box { margin-top:20px; padding:18px; border:1px dashed var(--border-bright); background:#030503; border-radius:4px; }
.agent-box h3 { margin:0 0 6px; font-size:14px; color:var(--accent); font-weight:700; }
.agent-box p { color:var(--fg-dim); font-size:13px; line-height:1.55; margin:0 0 10px; }
.agent-box pre { white-space:pre-wrap; word-break:break-word; background:#000; border:1px solid var(--border); border-radius:4px; padding:12px 14px; color:var(--fg); font-size:12px; line-height:1.6; }
.agent-box .row { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
.agent-box button, .agent-box a.btn {
  display:inline-flex; align-items:center; justify-content:center;
  min-height:40px; padding:8px 14px; border:1px solid var(--border-bright); border-radius:4px; background:transparent;
  color:var(--accent); font:inherit; font-size:12px; font-weight:700; cursor:pointer; text-decoration:none; transition:all .15s;
}
.agent-box button:hover, .agent-box a.btn:hover { border-color:var(--accent); background:rgba(0,255,156,.06); text-decoration:none; }
.agent-box button:focus-visible, .agent-box a.btn:focus-visible { outline:none; box-shadow:var(--focus-ring); border-color:var(--accent); }
.agent-box button:disabled { opacity:.5; cursor:not-allowed; }
.key-status-msg { margin-top:10px; font-size:12px; line-height:1.5; color:var(--fg-dim); }
.key-status-msg.ok { color:var(--accent); }
.key-status-msg.err { color:#ff8080; }
.connection-steps { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:16px; }
.connection-step { padding:20px; border:1px solid var(--border); background:var(--bg-alt); border-radius:4px; }
.connection-step b { display:block; color:var(--accent); font-size:14px; margin-bottom:6px; }
.connection-step p { color:var(--fg-dim); font-size:13px; line-height:1.55; margin:0; }
.warn-note { margin:16px 0; padding:14px 18px; border:1px solid var(--border-bright); background:rgba(255,210,63,.03); border-radius:4px; color:var(--fg); font-size:13px; line-height:1.6; }
.warn-note code { font-size:11px; }
.funding-path { border:1px solid var(--border); margin-top:10px; background:var(--bg-alt); border-radius:4px; }
.funding-path summary { padding:14px 18px; cursor:pointer; color:var(--fg); font-weight:700; font-size:13px; min-height:44px; display:flex; align-items:center; }
.funding-path summary:hover { color:var(--accent); }
.funding-path summary:focus-visible { outline:none; box-shadow:var(--focus-ring); border-radius:2px; }
.funding-path div { padding:0 18px 16px; color:var(--fg-dim); font-size:13px; line-height:1.6; }
.funding-path code { color:var(--accent); font-size:12px; }
.funding-path a { color:#5ce1ff; }
.funding-path a:focus-visible { outline:none; box-shadow:var(--focus-ring); }
.home-docs { padding:32px 20px; border:1px dashed var(--border-bright); text-align:center; color:var(--fg-dim); border-radius:4px; }
.home-docs b { display:block; color:var(--accent); font-size:16px; margin-bottom:8px; }
.home-docs p { max-width:620px; margin:0 auto 16px; font-size:13px; line-height:1.6; }
.home-docs a.docs-btn { display:inline-flex; align-items:center; justify-content:center; min-height:40px; padding:8px 18px; border:1px solid var(--accent); color:var(--accent); font-weight:700; border-radius:4px; text-decoration:none; margin-bottom:16px; }
.home-docs a.docs-btn:hover { background:var(--accent); color:#00150d; }
.home-docs a.docs-btn:focus-visible { outline:none; box-shadow:var(--focus-ring); }
.home-quiet-links { display:flex; justify-content:center; gap:20px; flex-wrap:wrap; font-size:12px; }
.home-quiet-links a { color:var(--fg-dim); display:inline-flex; align-items:center; min-height:36px; padding:0 4px; }
.home-quiet-links a:hover { color:var(--accent); }
.home-quiet-links a:focus-visible { outline:none; box-shadow:var(--focus-ring); border-radius:2px; }
@media(max-width:760px) {
  .home-hero { min-height:auto; padding:36px 0 44px; }
  .home-hero h1 { letter-spacing:-1.5px; }
  .demo-shell { grid-template-columns:1fr; }
  .demo-prompt { border-right:0; border-bottom:1px solid var(--border); }
  .connection-steps { grid-template-columns:1fr; }
  .cache-tip .tip { left:auto; right:0; }
  .home-proof { gap:18px; }
  .demo-custom label { flex-direction:column; align-items:flex-start; gap:6px; }
  .demo-custom input[type=range] { max-width:100%; width:100%; }
}
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
      <div class="home-proof-item">
        <b>145+ models</b>
        <span>one OpenAI-compatible endpoint</span>
      </div>
      <div class="home-proof-item">
        <span class="cache-tip">
          <b>$0.001</b>
          <button type="button" aria-describedby="cache-tip-text" aria-label="What a cache hit costs">?</button>
          <span class="tip" id="cache-tip-text" role="tooltip">The system remembers answers to identical questions. You pay a fraction of a penny to reuse an old answer. You do not pay full price to make it again.</span>
        </span>
        <span>exact-response cache hit</span>
      </div>
      <div class="home-proof-item">
        <b>No subscription</b>
        <span>pay only for requests you make</span>
      </div>
    </div>
  </section>

  <section class="home-section" id="try">
    <h2>Give Surp a route.</h2>
    <p class="home-section-intro">No wallet. No account. No API key. Start on Free. See which live model Surp would pick, then copy a prompt into your agent.</p>
    <div class="demo-shell">
      <div class="demo-prompt">
        <label for="demo-text">Your prompt</label>
        <textarea id="demo-text">Say only the word PONG.</textarea>
        <span class="demo-buttons-label">Choose a route</span>
        <div class="demo-buttons" role="group" aria-label="route">
          <button class="active" data-mode="free">Free</button>
          <button data-mode="value">Value</button>
          <button data-mode="frontier">Frontier</button>
        <button data-mode="speed">Speed</button>
        <button data-mode="fast" class="legacy-mode" hidden>Fast</button>
          <button data-mode="vision">Vision</button>
          <button data-mode="custom">Custom</button>
        </div>
        <div class="demo-custom" id="demo-custom">
          <p class="dim">Set how much intelligence, speed, and discount matter. Cost here is Surplus % off the AA list price.</p>
          <div class="sliders">
            <label>Intelligence <input id="w-intel" type="range" min="0" max="5" value="4" aria-label="Intelligence weight"></label>
            <label>Speed <input id="w-speed" type="range" min="0" max="5" value="1" aria-label="Speed weight"></label>
            <label>Discount <input id="w-cost" type="range" min="0" max="5" value="1" aria-label="Discount weight"></label>
          </div>
        </div>
      </div>
      <div class="demo-result" aria-live="polite">
        <span class="route-label">Surp routes this to</span>
        <div class="route" id="demo-route">surp/free</div>
        <span class="model-label">Live model pick</span>
        <div class="saving" id="demo-price">loading…</div>
        <p class="detail" id="demo-saving">Free route. Treasury pays Surplus. You pay $0 within the daily cap.</p>
        <p class="detail">Vision is ranked by Artificial Analysis general Intelligence Index, not a vision-specific benchmark.</p>
      </div>
    </div>

    <div class="agent-box" id="agent-box">
      <h3>Copy this into your agent</h3>
      <p>Create a Surp key, then paste the prompt. This is not a SurplusIntelligence.ai key. The base URL is different.</p>
      <pre id="agent-prompt" tabindex="0">Use Surp as my OpenAI-compatible provider.

Base URL: https://surp.ivc.lol/v1
API key: YOUR_SURP_KEY
Model: surp/free

Do not use https://api.surplusintelligence.ai/min30/v1/chat/completions
Do not expect a SurplusIntelligence balance here. This key only works on this base URL.</pre>
      <div class="row">
        <button type="button" id="btn-copy-prompt">Copy prompt</button>
        <a class="btn" href="/app">Open account →</a>
      </div>
      <p id="key-status" class="key-status-msg" aria-live="polite"></p>
    </div>
  </section>

  <section class="home-section" id="connect">
    <h2>From zero to first paid call.</h2>
    <p class="home-section-intro">Pick the path that matches how your agent already works. Funding details stay closed until you need them.</p>
    <div class="connection-steps">
      <div class="connection-step">
        <b>1 · Choose</b>
        <p>Pick a route: <code>surp/free</code>, <code>surp/value</code>, <code>surp/frontier</code>, <code>surp/fast</code>, <code>surp/vision</code>, or <code>surp/custom</code>.</p>
      </div>
      <div class="connection-step">
        <b>2 · Fund</b>
        <p>Add USDC on Base to a wallet, or use a Surp API key. Pay in USDC on Base — this page does not sell crypto.</p>
      </div>
      <div class="connection-step">
        <b>3 · Call</b>
        <p>Send an OpenAI-compatible request to <code>https://surp.ivc.lol/v1</code>.</p>
      </div>
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
      <a href="/docs" class="docs-btn">Read the documentation →</a>
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
  var copyPromptBtn = document.getElementById('btn-copy-prompt');
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

  function renderError(msg) {
    price.textContent = '—';
    saving.innerHTML = '<span class="err-state">' + msg + '</span><br><button type="button" class="retry-btn" id="btn-retry-preview">Retry</button>';
    var retryBtn = document.getElementById('btn-retry-preview');
    if (retryBtn) {
      retryBtn.addEventListener('click', function () {
        loadPreview(currentMode);
      });
    }
  }

  function loadPreview(mode) {
    currentMode = mode;
    route.textContent = 'surp/' + mode;
    custom.className = 'demo-custom' + (mode === 'custom' ? ' open' : '');
    price.textContent = 'loading…';
    saving.textContent = 'Checking live marketplace…';
    var qs = '/api/routes/preview?mode=' + encodeURIComponent(mode);
    if (mode === 'custom') qs += '&weights=' + encodeURIComponent(weights());
    fetch(qs).then(function (r) {
      if (!r.ok) {
        throw new Error('HTTP ' + r.status);
      }
      return r.json();
    }).then(function (data) {
      if (!data || data.error) {
        renderError((data && data.error) || 'Market feed is not available.');
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
    }).catch(function (err) {
      renderError('Live market is not available (' + (err.message || 'network') + ').');
    });
  }

  buttons.forEach(function (button) {
    button.addEventListener('click', function () {
      buttons.forEach(function (item) { item.classList.remove('active'); });
      button.classList.add('active');
      loadPreview(button.getAttribute('data-mode'));
    });
  });

  var debounceTimer = null;
  ['w-intel', 'w-speed', 'w-cost'].forEach(function (id) {
    document.getElementById(id).addEventListener('input', function () {
      if (currentMode === 'custom') {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () {
          loadPreview('custom');
        }, 150);
      }
    });
  });

  copyPromptBtn.addEventListener('click', function () {
    var text = promptBox.textContent;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        keyStatus.className = 'key-status-msg ok';
        keyStatus.textContent = 'Prompt copied to clipboard.';
      }).catch(function () {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }
  });

  function fallbackCopy(text) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      var ok = document.execCommand('copy');
      document.body.removeChild(ta);
      if (ok) {
        keyStatus.className = 'key-status-msg ok';
        keyStatus.textContent = 'Prompt copied to clipboard.';
        return;
      }
    } catch (e) {}
    keyStatus.className = 'key-status-msg';
    keyStatus.textContent = 'Select text above and press Ctrl+C (Cmd+C).';
  }

  loadPreview('free');
})();
</script>
'''
