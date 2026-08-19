"""Public OpenRouter-vs-Surp comparison page."""

CONTENT = r"""
<style>
.price-hero { position:relative; overflow:hidden; border:1px solid var(--border-bright); padding:22px; margin-bottom:18px; background:#050806; }
.price-hero::after { content:""; position:absolute; width:220px; height:220px; right:-80px; top:-110px; border:1px solid rgba(0,255,156,.16); border-radius:50%; box-shadow:0 0 80px rgba(0,255,156,.06); }
.price-live { display:inline-flex; align-items:center; gap:7px; color:var(--accent); font-size:10px; letter-spacing:1px; text-transform:uppercase; }
.price-live::before { content:""; width:7px; height:7px; border-radius:50%; background:var(--accent); box-shadow:0 0 8px var(--accent); animation:pulse 1.5s infinite; }
.price-summary { display:grid; grid-template-columns:1.4fr 1fr 1fr; gap:10px; margin:16px 0; }
.price-stat { border:1px solid var(--border); padding:14px; background:#050505; }
.price-stat strong { display:block; color:var(--accent); font-size:28px; line-height:1.1; }
.price-stat span { color:var(--fg-dim); font-size:10px; text-transform:uppercase; letter-spacing:.7px; }
.price-controls { display:grid; grid-template-columns:minmax(220px,1fr) 180px 170px auto; gap:10px; margin:14px 0; align-items:end; }
.price-controls button { height:36px; }
.price-table-wrap { overflow-x:auto; border:1px solid var(--border); background:#030303; }
.price-table { margin:0; min-width:920px; }
.price-table th { position:sticky; top:0; z-index:2; background:#070907; }
.price-table td { vertical-align:middle; }
.price-model strong { display:block; color:var(--fg); font-size:13px; }
.price-model small { color:#555; }
.price-chip { display:inline-block; border:1px solid var(--border-bright); color:var(--fg-dim); padding:1px 5px; margin-left:5px; font-size:9px; }
.price-amount { font-variant-numeric:tabular-nums; white-space:nowrap; }
.price-amount.surp { color:var(--accent); }
.price-amount.router { color:#5ce1ff; }
.price-save { min-width:150px; }
.price-save b { display:block; color:var(--accent); }
.price-save.loss b { color:var(--yellow); }
.price-bar { height:3px; background:#171717; margin-top:5px; }
.price-bar i { display:block; height:100%; background:var(--accent); width:0; }
.price-save.loss .price-bar i { background:var(--yellow); }
.price-source { display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; color:#555; font-size:10px; margin:10px 0; }
.price-empty { padding:32px; text-align:center; color:var(--fg-dim); }
@media(max-width:800px) { .price-summary { grid-template-columns:1fr; } .price-controls { grid-template-columns:1fr 1fr; } }
@media(max-width:520px) { .price-controls { grid-template-columns:1fr; } .price-hero { padding:15px; } }
</style>

<section class="price-hero">
  <div class="price-live">live market spread</div>
  <h1 style="margin-top:7px;">OpenRouter vs Surp</h1>
  <p>Same model, two markets. Pick a workload mix and see the listed price difference now.</p>
  <p class="dim" style="font-size:11px;">Surp publishes one estimated blended rate; OpenRouter publishes separate input and output rates. The workload control makes that difference explicit instead of comparing unlike numbers.</p>
</section>

<div class="price-summary">
  <div class="price-stat"><strong id="avg-save">—</strong><span>average saving where Surp wins</span></div>
  <div class="price-stat"><strong id="surp-wins">—</strong><span>models cheaper on Surp</span></div>
  <div class="price-stat"><strong id="overlap">—</strong><span>matched live models</span></div>
</div>

<div class="price-controls">
  <div class="field"><label for="price-search">find a model</label><input id="price-search" type="search" placeholder="claude, gpt, gemini…" autocomplete="off"></div>
  <div class="field"><label for="price-class">class</label><select id="price-class"><option value="">all classes</option><option>chat</option><option>coding</option><option>reasoning</option><option>fast</option><option>vision</option></select></div>
  <div class="field"><label for="input-share">workload</label><select id="input-share"><option value="0.9">90% input / 10% output</option><option value="0.8" selected>80% input / 20% output</option><option value="0.5">50% input / 50% output</option><option value="0.2">20% input / 80% output</option></select></div>
  <button id="price-refresh" type="button">↻ refresh</button>
</div>

<div class="price-source"><span id="price-method">loading methodology…</span><span id="price-age">fetching live prices…</span></div>
<div class="price-table-wrap">
<table class="price-table">
<thead><tr><th>model</th><th>Surp blended</th><th>OpenRouter input</th><th>OpenRouter output</th><th>OpenRouter workload</th><th>difference</th></tr></thead>
<tbody id="price-rows"><tr><td colspan="6" class="price-empty">reading both markets…</td></tr></tbody>
</table>
</div>
<p class="dim" style="font-size:10px;margin-top:10px;">Prices are public listings, not a guarantee of final billed cost. Provider caching, request shape, minimum charges, routing choices, and market movement can change actual spend. OpenRouter batch/free variants are excluded. Surp exact-response cache hits are a separate $0.001 request tier and are not mixed into this table.</p>

<script>
(function(){
  var all=[];
  var tbody=document.getElementById('price-rows');
  var search=document.getElementById('price-search');
  var klass=document.getElementById('price-class');
  var mix=document.getElementById('input-share');
  function money(v){ if(v===null||v===undefined)return '—'; return '$'+Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:6})+'/M'; }
  function esc(s){ var d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML; }
  function render(){
    var q=search.value.trim().toLowerCase(), c=klass.value;
    var rows=all.filter(function(r){return (!q||(r.model+' '+r.name).toLowerCase().includes(q))&&(!c||r.class===c);});
    if(!rows.length){tbody.innerHTML='<tr><td colspan="6" class="price-empty">no matching models</td></tr>';return;}
    tbody.innerHTML=rows.map(function(r){
      var win=r.cheaper==='surp', width=Math.min(100,r.savings_pct);
      return '<tr><td class="price-model"><strong>'+esc(r.name)+'</strong><small>'+esc(r.model)+'</small>'+(r.pro?'<span class="price-chip">PRO</span>':'')+'</td>'+
        '<td class="price-amount surp">'+money(r.surp_usd_per_1m)+'</td><td class="price-amount router">'+money(r.openrouter_input_usd_per_1m)+'</td><td class="price-amount router">'+money(r.openrouter_output_usd_per_1m)+'</td><td>'+money(r.openrouter_blended_usd_per_1m)+'</td>'+
        '<td class="price-save '+(win?'':'loss')+'"><b>'+(win?'save ':'OpenRouter lower ')+r.savings_pct.toFixed(2)+'%</b><small>'+money(r.savings_usd_per_1m)+' difference</small><div class="price-bar"><i style="width:'+width+'%"></i></div></td></tr>';
    }).join('');
  }
  async function load(){
    var button=document.getElementById('price-refresh'); button.disabled=true; button.textContent='↻ loading';
    try{
      var res=await fetch('/api/price-compare?input_share='+encodeURIComponent(mix.value),{cache:'no-store'});
      var data=await res.json(); if(!res.ok) throw new Error(data.error||'price feed failed');
      all=data.models||[];
      document.getElementById('avg-save').textContent=data.summary.avg_savings_pct_when_surp_cheaper.toFixed(1)+'%';
      document.getElementById('surp-wins').textContent=data.summary.surp_cheaper_count;
      document.getElementById('overlap').textContent=data.summary.overlap_count;
      document.getElementById('price-method').textContent=Math.round(data.methodology.input_share*100)+'% input + '+Math.round(data.methodology.output_share*100)+'% output workload';
      document.getElementById('price-age').textContent='updated '+new Date(data.generated_at).toLocaleTimeString()+' · source age '+data.source_age_seconds+'s';
      render();
    }catch(e){tbody.innerHTML='<tr><td colspan="6" class="price-empty">'+esc(e.message)+'</td></tr>';}
    finally{button.disabled=false;button.textContent='↻ refresh';}
  }
  search.addEventListener('input',render); klass.addEventListener('change',render); mix.addEventListener('change',load); document.getElementById('price-refresh').addEventListener('click',load); load();
})();
</script>
"""
