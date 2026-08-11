"""Live TPS metrics dashboard section — SSE-fed headline cards, per-model table, sparkline.

Sibling of the other *_page builders. Merge the return value of
``tps_dashboard_html`` into the existing /dashboard page in gateway.py. The
feed contract is frozen: GET /api/metrics/stream (SSE, event name "metric",
``Authorization: Bearer <token>``). Data fields per event:
{"ts": <unix ms>, "model": str, "provider": str, "ttft_ms": float|null,
 "wall_ms": float, "completion_tokens": int, "tps": float|null,
 "f1000": float|null, "source": "live"|"benchmark", "estimated": 0|1}

The returned fragment is server-rendered + plain browser JS (no framework),
reusing the dashboard's existing CSS classes (card/num/lbl, grid, badge,
dim, model) so it drops into the page with zero new global styles.
"""

import json

__all__ = ["tps_dashboard_html"]

_TOKEN_PLACEHOLDER = "__SURP_METRICS_TOKEN__"

_DISABLED_CARD = (
    '<div class="card dim" id="tps-metrics">'
    "<p><b>metrics feed disabled.</b> set SURP_METRICS_TOKEN on the gateway "
    "to enable live TPS metrics.</p>"
    "</div>"
)

_TPS_METRICS_HTML = r"""
<div id="tps-metrics">
  <h2>live tps metrics</h2>
  <p class="dim" id="m-status">connecting to metrics feed&hellip;</p>

  <div class="grid">
    <div class="card">
      <div class="num" id="m-ttft">&mdash;</div>
      <div class="lbl">ttft (ms)</div>
    </div>
    <div class="card">
      <div class="num" id="m-tps">&mdash;</div>
      <div class="lbl">generation tps</div>
    </div>
    <div class="card">
      <div class="num" id="m-f1000">&mdash;</div>
      <div class="lbl">f1000 score</div>
    </div>
  </div>

  <div class="field">
    <label>session tps sparkline</label>
    <canvas id="m-spark" style="width:100%;height:48px;display:block;background:var(--bg-alt);border:1px solid var(--border);"></canvas>
  </div>

  <table>
    <thead><tr>
      <th>model</th><th>provider</th><th>ttft ms</th><th>tps</th>
      <th>f1000</th><th>flags</th><th>samples</th>
    </tr></thead>
    <tbody id="m-tbody">
      <tr><td colspan="7" class="dim">waiting for the first metric event&hellip;</td></tr>
    </tbody>
  </table>
</div>
<script>
(function () {
  var TOKEN = __SURP_METRICS_TOKEN__;
  var $ = function (id) { return document.getElementById(id); };

  var SAMPLES = [];   // rolling window of all events -> headline cards
  var MAX_SAMPLES = 100;
  var MODELS = new Map();  // model + provider -> per-model summary
  var SPARK = [];     // live-only tps samples -> sparkline
  var MAX_SPARK = 48;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function mean(vals) {
    var xs = [];
    for (var i = 0; i < vals.length; i++) {
      if (vals[i] != null && !isNaN(vals[i])) xs.push(Number(vals[i]));
    }
    if (!xs.length) return null;
    var sum = 0;
    for (var j = 0; j < xs.length; j++) sum += xs[j];
    return sum / xs.length;
  }

  function fmtF(v, dec) {
    if (v == null) return '&mdash;';
    return v.toFixed(dec);
  }

  function fmtShort(v, dec) {
    if (v == null) return '&mdash;';
    if (v >= 1000) return (v / 1000).toFixed(1) + 'k';
    return v.toFixed(dec);
  }

  function meanSamples(field) {
    var vals = [];
    for (var i = 0; i < SAMPLES.length; i++) vals.push(SAMPLES[i][field]);
    return mean(vals);
  }

  function agg(model, provider) {
    var key = model + '\u0000' + provider;
    var a = MODELS.get(key);
    if (!a) {
      a = {
        model: model, provider: provider,
        samples: [], count: 0,
        lastSource: 'live', lastEst: 0
      };
      MODELS.set(key, a);
    }
    return a;
  }

  function refreshHeadline() {
    $('m-ttft').innerHTML = fmtF(meanSamples('ttft_ms'), 1);
    $('m-tps').innerHTML = fmtShort(meanSamples('tps'), 1);
    $('m-f1000').innerHTML = fmtF(meanSamples('f1000'), 0);
  }

  function rowFor(a) {
    var ttft = [], tps = [], f1000 = [];
    for (var i = 0; i < a.samples.length; i++) {
      var s = a.samples[i];
      ttft.push(s.ttft_ms); tps.push(s.tps); f1000.push(s.f1000);
    }
    var flags = a.lastEst
      ? '<span class="badge">est</span>'
      : '<span class="badge">live</span>';
    if (a.lastSource === 'benchmark') flags += ' <span class="badge">bench</span>';
    var html = '<tr>'
      + '<td class="model">' + esc(a.model) + '</td>'
      + '<td class="dim">' + esc(a.provider) + '</td>'
      + '<td>' + fmtF(mean(ttft), 1) + '</td>'
      + '<td>' + fmtShort(mean(tps), 1) + '</td>'
      + '<td>' + fmtF(mean(f1000), 0) + '</td>'
      + '<td>' + flags + '</td>'
      + '<td>' + a.samples.length + '</td>'
      + '</tr>';
    return { n: a.samples.length, html: html };
  }

  function refreshTable() {
    var rows = [];
    MODELS.forEach(function (a) {
      if (a.samples.length) rows.push(rowFor(a));
    });
    rows.sort(function (x, y) { return y.n - x.n; });
    var html;
    if (!rows.length) {
      html = '<tr><td colspan="7" class="dim">waiting for the first metric event&hellip;</td></tr>';
    } else {
      html = rows.map(function (r) { return r.html; }).join('');
    }
    $('m-tbody').innerHTML = html;
  }

  function drawSpark() {
    var cv = $('m-spark');
    if (!cv) return;
    var css = window.getComputedStyle(document.documentElement);
    var accent = (css.getPropertyValue('--accent') || '#00ff9c').trim();
    var dim = (css.getPropertyValue('--fg-dim') || '#888888').trim();
    var dpr = window.devicePixelRatio || 1;
    var w = cv.clientWidth || 600;
    var h = 48;
    cv.width = Math.floor(w * dpr);
    cv.height = Math.floor(h * dpr);
    var ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    var pts = [];
    for (var i = 0; i < SPARK.length; i++) {
      var t = SPARK[i];
      if (t.tps != null && t.tps > 0) pts.push(t.tps);
    }
    if (!pts.length) {
      ctx.fillStyle = dim;
      ctx.font = '12px monospace';
      ctx.fillText('no live tps yet...', 6, 28);
      return;
    }
    var lo = Math.min.apply(null, pts);
    var hi = Math.max.apply(null, pts);
    var span = (hi - lo) || 1;
    var pad = 6, bw = w - pad, bh = h - 12;
    ctx.strokeStyle = accent;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (var j = 0; j < pts.length; j++) {
      var x = pad + (pts.length === 1 ? 0 : (j * bw) / (pts.length - 1));
      var y = 6 + bh - ((pts[j] - lo) / span) * bh;
      if (j === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.fillStyle = dim;
    ctx.font = '11px monospace';
    ctx.fillText(hi.toFixed(1) + ' tps', 6, 12);
  }

  // Native EventSource cannot send an Authorization header, so we stream the
  // SSE feed over fetch (same wire format) and keep an EventSource-like API.
  function TpsEventSource(url, token) {
    this.url = url;
    this.token = token;
    this.closed = false;
    this.reader = null;
    this.handlers = {};
  }
  TpsEventSource.prototype.addEventListener = function (name, fn) {
    this.handlers[name] = fn;
  };
  TpsEventSource.prototype.dispatch = function (name, data) {
    var fn = this.handlers[name];
    if (fn) fn(data);
  };
  TpsEventSource.prototype.parseFrame = function (frame) {
    var event = 'message';
    var data = [];
    var lines = frame.split('\n');
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (!line || line.charAt(0) === ':') continue;
      var idx = line.indexOf(':');
      if (idx < 0) continue;
      var field = line.slice(0, idx);
      var value = line.slice(idx + 1).replace(/^ +/, '');
      if (field === 'event') event = value;
      else if (field === 'data') data.push(value);
    }
    if (!data.length) return;
    var payload = data.join('\n');
    try { payload = JSON.parse(payload); } catch (e) { /* keep raw text */ }
    this.dispatch(event, payload);
  };
  TpsEventSource.prototype.reconnect = function (why) {
    var self = this;
    var st = $('m-status');
    if (st) st.textContent = 'feed disconnected (' + why + ') - retrying...';
    setTimeout(function () { if (!self.closed) self.connect(); }, 2000);
  };
  TpsEventSource.prototype.connect = function () {
    var self = this;
    fetch(this.url, {
      headers: { 'Authorization': 'Bearer ' + this.token, 'Accept': 'text/event-stream' }
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      if (!r.body) throw new Error('no stream body');
      var decoder = new TextDecoder();
      var buf = '';
      var reader = r.body.getReader();
      self.reader = reader;
      function pump() {
        return reader.read().then(function (res) {
          if (res.done) {
            if (!self.closed) self.reconnect('stream ended');
            return;
          }
          buf += decoder.decode(res.value, { stream: true });
          buf = buf.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
          var frames = buf.split('\n\n');
          buf = frames.pop();
          for (var i = 0; i < frames.length; i++) self.parseFrame(frames[i]);
          return pump();
        }).catch(function (e) {
          if (!self.closed) self.reconnect(String((e && e.message) || 'stream error'));
        });
      }
      return pump();
    }).catch(function (e) {
      if (!self.closed) self.reconnect(String((e && e.message) || 'connection failed'));
    });
  };
  TpsEventSource.prototype.close = function () {
    this.closed = true;
    if (this.reader) this.reader.cancel();
    var st = $('m-status');
    if (st) st.textContent = 'metrics feed stopped';
  };

  function onMetric(d) {
    if (!d || typeof d !== 'object') return;
    var model = (d.model != null ? d.model : '?').toString();
    var provider = (d.provider != null ? d.provider : '?').toString();

    SAMPLES.push(d);
    if (SAMPLES.length > MAX_SAMPLES) SAMPLES.shift();

    var a = agg(model, provider);
    a.samples.push(d);
    if (a.samples.length > 200) a.samples.shift();
    a.count++;
    if (d.source === 'live' || d.source === 'benchmark') a.lastSource = d.source;
    a.lastEst = Number(d.estimated) ? 1 : 0;

    if (d.tps != null && Number(d.tps) > 0 && a.lastSource !== 'benchmark') {
      SPARK.push({ t: Number(d.ts) || 0, tps: Number(d.tps) });
      if (SPARK.length > MAX_SPARK) SPARK.shift();
    }

    refreshHeadline();
    refreshTable();
    drawSpark();
    var st = $('m-status');
    if (st) st.textContent = 'live - ' + SAMPLES.length + ' sample window';
  }

  var es = new TpsEventSource('/api/metrics/stream', TOKEN);
  es.addEventListener('metric', onMetric);
  es.connect();
})();
</script>
"""


def tps_dashboard_html(metrics_token: str) -> str:
    """Return a self-contained dashboard section (div + inline script) for live TPS metrics.

    Merge the result into the existing /dashboard page. If ``metrics_token``
    is empty/None, render a muted "metrics feed disabled" card instead.
    """
    if not metrics_token:
        return _DISABLED_CARD
    token_literal = json.dumps(metrics_token)
    return _TPS_METRICS_HTML.replace(_TOKEN_PLACEHOLDER, token_literal)
