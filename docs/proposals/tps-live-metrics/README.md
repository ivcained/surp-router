# Real-Time TPS Feed & Advanced Benchmarking for `surp-router`

Implementation plan for TTFT / TPS / F1000 metrics, a live metrics feed, and a
React dashboard. Grounded against the actual repos (HEAD, 2026-08-10):

- `surp-router`: aiohttp monolith (`gateway.py`, ~3300 lines, routes via
  `app.router.add_get`), storage in `provider_health.py` / `model_benchmarks.py`
  (both: `sqlite3`, `check_same_thread=False`, `threading.RLock`, WAL,
  `busy_timeout=5000`), standalone CLI `benchmark_runner.py`, Vite+React+TS
  frontend in `frontend/` (`vite.config.ts` already proxies `/api` and `/ws`
  to `localhost:8000`).
- `Ai-speedometer`: the metric definitions to mirror —
  `f1000 = (1000 * (ttft_s + 300 / tps)) / 3600` (hours), token estimation
  fallback `len(text)/4` when `usage` is absent.

**Current state gap:** `benchmark_runner.py` already measures TTFT/TPS, but only
as a CLI through the public gateway, one sample per model. `gateway.py` does
**not** time real production streams. Nothing pushes metrics live; the frontend
polls `/api/benchmarks`. This plan closes those three gaps.

---

## 1. Backend metric calculation

### 1.1 Shared sample shape

Add a single dataclass both the gateway tap and the benchmark runner produce
(new file `metrics_core.py` in surp-router):

```python
@dataclass
class StreamSample:
    provider: str
    model: str
    source: str            # "request" (real traffic) | "benchmark"
    success: bool
    ttft_ms: float | None  # request start -> first *content* token
    gen_ms: float | None   # first token -> stream end
    total_ms: float
    completion_tokens: int # from usage, else ceil(chars/4) (flag estimated)
    prompt_tokens: int
    estimated: bool        # True if token counts were estimated
    error: str | None = None

    @property
    def tps(self) -> float | None:
        if self.gen_ms and self.completion_tokens and self.gen_ms > 0:
            return self.completion_tokens / (self.gen_ms / 1000)
        return None

    @property
    def f1000_h(self) -> float | None:
        """Ai-speedometer parity: hours for 1000 agentic requests of ~300 tok."""
        tps = self.tps
        if not tps or self.ttft_ms is None or tps <= 0:
            return None
        return (1000 * (self.ttft_ms / 1000 + 300 / tps)) / 3600
```

### 1.2 Timing tap inside `gateway.py` (real traffic)

The gateway streams upstream SSE straight to the client. Wrap that loop — do
**not** buffer — and parse each `data:` line only enough to detect the first
content token and the trailing `usage` object. Request
`stream_options={"include_usage": True}` upstream so token counts are exact
(the gateway already injects `max_tokens`; adding `stream_options` for
OpenAI-compatible upstreams is one line — strip it before sending to Anthropic-
shaped upstreams, same as Ai-speedometer does).

```python
# gateway.py — inside the streaming proxy path
import time, json
from metrics_core import StreamSample
from metrics_feed import broadcaster          # §2
from metrics_store import metric_writer       # §4

async def stream_with_metrics(upstream_resp, client_resp, *, provider, model):
    t0 = time.perf_counter()
    ttft_ms = None
    usage = {}
    text_chars = 0
    buf = b""
    try:
        async for chunk in upstream_resp.content.iter_any():
            await client_resp.write(chunk)          # zero-latency passthrough
            buf += chunk
            # SSE frame boundary scan; keep tail
            *lines, buf = buf.split(b"\n")
            for raw in lines:
                line = raw.strip()
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except ValueError:
                    continue
                if obj.get("usage"):
                    usage = obj["usage"]
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                content = delta.get("content") or delta.get("reasoning_content") or ""
                if content:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - t0) * 1000
                    text_chars += len(content)
    finally:
        total_ms = (time.perf_counter() - t0) * 1000
        comp = usage.get("completion_tokens") or max(1, round(text_chars / 4))
        sample = StreamSample(
            provider=provider, model=model, source="request", success=True,
            ttft_ms=ttft_ms,
            gen_ms=(total_ms - ttft_ms) if ttft_ms is not None else None,
            total_ms=total_ms,
            completion_tokens=comp,
            prompt_tokens=usage.get("prompt_tokens", 0),
            estimated="completion_tokens" not in usage,
        )
        broadcaster.publish(sample)      # non-blocking, §2
        metric_writer.enqueue(sample)    # non-blocking, §4
```

Precision notes:

- TTFT must be stamped on the **first content/reasoning token**, not the first
  HTTP byte — role-announce chunks (`delta: {"role":"assistant"}`) would
  otherwise understate TTFT.
- TPS = `completion_tokens / (t_end − t_first_token)`; excluding TTFT from the
  denominator is what makes TTFT and TPS independently meaningful.
- Fall back to `ceil(chars/4)` only when `usage` is missing, and mark
  `estimated=True` so rollups can exclude/flag it (Ai-speedometer does the same).

### 1.3 Upgrade `benchmark_runner.py`

It currently computes `tps = output_tokens / total_s` (TTFT-inclusive) —
fix to match §1.2 semantics, reuse `StreamSample`, and record the returned
sample instead of only printing:

```python
# benchmark_runner.py (patch inside benchmark_model)
gen_s = (time.perf_counter() * 1000 - result.ttft_ms) / 1000 if result.ttft_ms else result.total_s
result.tps = round(result.output_tokens / gen_s, 1) if gen_s and gen_s > 0 else 0
```

### 1.4 F1000 conceptually

F1000 is a **derived** metric — you do not run 1000 requests. For one sample
with `ttft_s` and steady-state `tps`, time for 1000 agentic turns of ~300
output tokens each is `1000 * (ttft_s + 300/tps)` seconds → divide by 3600 for
hours. It deliberately weights TTFT heavily (agentic workloads are many small
requests), which is why it's a better router signal than raw TPS for agent use
cases.

Where it lives in routing:

1. Compute per sample (property above), store in the DB row.
2. Roll up per provider/model: keep a rolling window (existing
   `window_sampler` pattern in `provider_health.py`) and persist
   `ttft_p50`, `tps_p50`, `f1000_p50` in the rollup/bucket tables.
3. Router score: extend the existing `score = tps*0.6 - p95*0.4` style
   composite in `get_healthy()` with an F1000 term, e.g.
   `score = w1*tps_p50 − w2*ttft_p50 − w3*f1000_p50`, or expose
   `strategy=f1000` alongside the existing routing strategies so clients can
   opt in per request.

---

## 2. Real-time data feed: SSE, not WebSockets

**Decision: Server-Sent Events.** Rationale:

- Traffic is strictly server→client. WS buys nothing here.
- aiohttp-native (`web.StreamResponse` + chunked writes), no `aiohttp` WS
  handshake/frame machinery, no heartbeat protocol to design.
- `EventSource` auto-reconnects with `Last-Event-ID`; through the existing
  Vite `/api` proxy it needs zero config (the `/ws` proxy entry exists but
  isn't backed by any aiohttp route today — SSE avoids needing it).
- SSE survives HTTP/1.1 keep-alive and is trivially cache-busted; a `metrics`
  event per second per subscriber is negligible.

Use WS later only if you need client→server control (pause feed, per-model
subscribe filters negotiated at runtime).

### 2.1 Broadcaster + route (`metrics_feed.py`)

```python
import asyncio, json, time
from aiohttp import web

class MetricsBroadcaster:
    """Fan-out: one asyncio.Queue per subscriber; publishers never block."""
    def __init__(self, maxlen: int = 100):
        self._subs: set[asyncio.Queue] = set()
        self._maxlen = maxlen
        self.latest: dict[str, dict] = {}   # provider|model -> last payload

    def publish(self, sample) -> None:
        key = f"{sample.provider}|{sample.model}"
        payload = {
            "provider": sample.provider, "model": sample.model,
            "ttft_ms": sample.ttft_ms, "tps": sample.tps,
            "f1000_h": sample.f1000_h, "total_ms": sample.total_ms,
            "source": sample.source, "estimated": sample.estimated,
            "ts": time.time(),
        }
        self.latest[key] = payload
        data = json.dumps(payload)
        for q in list(self._subs):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                self._subs.discard(q)   # drop slow consumers, never block the proxy path

    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxlen)
        self._subs.add(q)
        try:
            yield q
        finally:
            self._subs.discard(q)

broadcaster = MetricsBroadcaster()

async def api_metrics_stream(request: web.Request) -> web.StreamResponse:
    resp = web.StreamResponse(headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",          # disable nginx buffering if present
    })
    await resp.prepare(request)
    # Replay snapshot so a fresh client sees current state immediately
    for payload in broadcaster.latest.values():
        await resp.write(f"event: metric\ndata: {json.dumps(payload)}\n\n".encode())
    async for q in broadcaster.subscribe():
        try:
            while True:
                data = await asyncio.wait_for(q.get(), timeout=15)
                await resp.write(f"event: metric\ndata: {data}\n\n".encode())
        except asyncio.TimeoutError:
            await resp.write(b": keepalive\n\n")   # comment frame keeps proxies open
        except (ConnectionResetError, asyncio.CancelledError):
            break
    return resp

# gateway.py route table, next to the other add_get calls:
app.router.add_get("/api/metrics/stream", api_metrics_stream)
```

**Throttling:** real traffic can spike per-model. Coalesce inside `publish` is
optional; a simpler guard is per-subscriber `maxlen=100` + drop-slow (above).
If you chart at 1 Hz, also aggregate: keep `latest[key]` (instant) and let the
frontend render at animation-frame cadence.

---

## 3. Frontend dashboard (React + TS)

Deps: `npm i recharts` in `frontend/`. Two files (also in `snippets/`).

### 3.1 `src/hooks/useMetricsFeed.ts`

```ts
import { useEffect, useRef, useState } from "react";

export interface MetricEvent {
  provider: string; model: string;
  ttft_ms: number | null; tps: number | null; f1000_h: number | null;
  total_ms: number; source: "request" | "benchmark";
  estimated: boolean; ts: number;
}

export function useMetricsFeed(windowSize = 60) {
  const [samples, setSamples] = useState<MetricEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const buf = useRef<MetricEvent[]>([]);
  const raf = useRef(0);

  useEffect(() => {
    const es = new EventSource("/api/metrics/stream");
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);   // EventSource auto-reconnects
    es.addEventListener("metric", (e) => {
      buf.current.push(JSON.parse((e as MessageEvent).data));
      if (!raf.current) {
        raf.current = requestAnimationFrame(() => {   // render at ~60fps max
          setSamples((prev) => [...prev, ...buf.current].slice(-windowSize * 4));
          buf.current = [];
          raf.current = 0;
        });
      }
    });
    return () => { es.close(); if (raf.current) cancelAnimationFrame(raf.current); };
  }, [windowSize]);

  return { samples, connected };
}
```

### 3.2 `src/components/LiveTpsDashboard.tsx`

Cards show the latest sample per metric; the chart plots the rolling window,
one series per `provider|model` (top 5 by recency shown for brevity):

```tsx
import { useMemo } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { useMetricsFeed, MetricEvent } from "../hooks/useMetricsFeed";

const fmt = (v: number | null | undefined, d = 1) => (v == null ? "—" : v.toFixed(d));

export default function LiveTpsDashboard() {
  const { samples, connected } = useMetricsFeed(60);

  const latest: MetricEvent | undefined = samples[samples.length - 1];
  const keys = useMemo(
    () => [...new Set(samples.map((s) => `${s.provider}|${s.model}`))].slice(-5),
    [samples]
  );
  const chartData = useMemo(
    () =>
      samples.map((s) => ({
        t: new Date(s.ts * 1000).toLocaleTimeString(),
        [`${s.provider}|${s.model}`]: s.tps ?? undefined,
      })),
    [samples]
  );

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-red-500"}`} />
        <h2 className="text-lg font-semibold">Live Throughput</h2>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card label="TTFT" value={`${fmt(latest?.ttft_ms, 0)} ms`} sub={latest?.model} />
        <Card label="TPS" value={fmt(latest?.tps)} sub={latest?.provider} />
        <Card label="F1000" value={`${fmt(latest?.f1000_h, 2)} h`} sub="1000 × ~300 tok" />
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          <XAxis dataKey="t" hide />
          <YAxis label={{ value: "tok/s", angle: -90, position: "insideLeft" }} />
          <Tooltip /><Legend />
          {keys.map((k, i) => (
            <Line key={k} dataKey={k} dot={false} isAnimationActive={false}
                  stroke={["#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#a855f7"][i % 5]}
                  connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Card({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border p-4">
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs text-gray-400 truncate">{sub}</div>}
    </div>
  );
}
```

Wire `<LiveTpsDashboard />` into the existing `/app` route or the
`/performance` page. The Vite proxy already forwards `/api/*` to
`localhost:8000`, so `EventSource("/api/metrics/stream")` works in dev with
no config change.

---

## 4. SQLite integration without WAL/lock bottlenecks

Existing pattern in `provider_health.py`/`model_benchmarks.py`:
`check_same_thread=False` + `threading.RLock` + WAL + `busy_timeout=5000`.
That is safe but **synchronous per call** — under a live tap, every streamed
request would take a global write lock and fsync-adjacent WAL work. At
bursty load this serializes the event loop.

**Architecture: single-writer, write-behind queue.**

1. **Producers never touch SQLite.** `metric_writer.enqueue(sample)` is a
   `queue.put_nowait` (bounded, drop-oldest on full — metrics are lossy by
   nature; drop policy beats backpressuring user traffic).
2. **One asyncio task owns the connection** (`metrics_store.py`). The gateway
   is single-process aiohttp, so one writer task + WAL readers is sufficient —
   no threads needed on the write path at all:

```python
import asyncio, sqlite3, time

class MetricWriter:
    def __init__(self, db_path: str, batch: int = 50, flush_s: float = 2.0):
        self.q: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self.db_path, self.batch, self.flush_s = db_path, batch, flush_s

    def enqueue(self, sample) -> None:
        try:
            self.q.put_nowait(sample)
        except asyncio.QueueFull:
            pass  # drop metrics before dropping user requests

    async def run(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")     # safe with WAL; big win
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA wal_autocheckpoint=2000") # cap WAL growth (~8MB)
        buf = []
        while True:
            try:
                item = await asyncio.wait_for(self.q.get(), timeout=self.flush_s)
                buf.append(item)
                while len(buf) < self.batch:
                    buf.append(self.q.get_nowait())
            except (asyncio.TimeoutError, asyncio.QueueEmpty):
                pass
            if buf:
                with conn:  # single transaction per batch
                    conn.executemany(
                        """INSERT INTO requests
                           (ts, provider, model, source, success, ttft_ms,
                            gen_ms, total_ms, prompt_tokens, completion_tokens,
                            tps, f1000_h, estimated, error)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        [(time.time(), s.provider, s.model, s.source, s.success,
                          s.ttft_ms, s.gen_ms, s.total_ms, s.prompt_tokens,
                          s.completion_tokens, s.tps, s.f1000_h,
                          s.estimated, s.error) for s in buf],
                    )
                buf.clear()

metric_writer = MetricWriter("metrics.db")
# gateway.py startup: asyncio.create_task(metric_writer.run())
```

3. **Schema:** extend the existing `requests` table (`ALTER TABLE ... ADD COLUMN
   gen_ms REAL, source TEXT DEFAULT 'request', estimated INTEGER DEFAULT 0,
   f1000_h REAL`) — `ttft_ms`/`tps` columns already exist. Keep
   `provider_health` per-request samples as-is for failure/latency; the tap's
   DB write goes to this one hot table only.
4. **Rollups, not reads of raw rows:** on the same flush cadence, update the
   existing bucket/rollup tables (15-min and 5-min windows already exist) with
   incremental aggregates, so `/api/benchmarks` and the dashboard cards read
   small rollup rows instead of scanning the hot table. TTL pruning
   (`delete_old`) moves into the writer task's idle time to avoid lock
   contention with flushes.
5. **Why this avoids the bottlenecks:** WAL allows concurrent readers while
   the single writer batches; batching turns N fsyncs into 1 per ≤2 s;
   `synchronous=NORMAL` is corruption-safe under WAL (only durability-on-power-
   loss of the last checkpoint is relaxed — acceptable for metrics);
   readers elsewhere in the codebase keep their existing `RLock` connections
   untouched.

---

## Build order

1. `metrics_core.py` (StreamSample + F1000) → unit-test the math against
   Ai-speedometer's `benchmark.ts` formula.
2. `metrics_store.py` writer + schema migration → soak test with synthetic
   samples at 100/s.
3. Gateway tap (`stream_with_metrics`) behind a config flag → verify TTFT/TPS
   against `benchmark_runner.py` output for the same model.
4. `metrics_feed.py` SSE route → `curl -N localhost:8000/api/metrics/stream`.
5. Frontend hook + dashboard → verify reconnect by bouncing the gateway.
6. Router integration: expose `strategy=f1000` once ≥50 samples/provider exist.
