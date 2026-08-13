"""SSE live metrics feed for surp-router (drop-in: metrics_feed.py).

Route: app.router.add_get("/api/metrics/stream", api_metrics_stream)
"""
from __future__ import annotations

import asyncio
import json
import time

from aiohttp import web


class MetricsBroadcaster:
    """Fan-out with one bounded queue per subscriber; publishers never block."""

    def __init__(self, maxlen: int = 100):
        self._subs: set[asyncio.Queue] = set()
        self._maxlen = maxlen
        self.latest: dict[str, dict] = {}

    def publish(self, sample) -> None:
        payload = {
            "provider": sample.provider,
            "model": sample.model,
            "ttft_ms": sample.ttft_ms,
            "tps": sample.tps,
            "f1000_h": sample.f1000_h,
            "total_ms": sample.total_ms,
            "source": sample.source,
            "estimated": sample.estimated,
            "ts": sample.ts or time.time(),
        }
        self.latest[f"{sample.provider}|{sample.model}"] = payload
        data = json.dumps(payload)
        for q in list(self._subs):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                self._subs.discard(q)

    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxlen)
        self._subs.add(q)
        try:
            yield q
        finally:
            self._subs.discard(q)


broadcaster = MetricsBroadcaster()


async def api_metrics_stream(request: web.Request) -> web.StreamResponse:
    resp = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
    await resp.prepare(request)
    for payload in broadcaster.latest.values():
        await resp.write(f"event: metric\ndata: {json.dumps(payload)}\n\n".encode())
    async for q in broadcaster.subscribe():
        try:
            while True:
                data = await asyncio.wait_for(q.get(), timeout=15)
                await resp.write(f"event: metric\ndata: {data}\n\n".encode())
        except asyncio.TimeoutError:
            try:
                await resp.write(b": keepalive\n\n")
            except (ConnectionResetError, asyncio.CancelledError):
                break
        except (ConnectionResetError, asyncio.CancelledError):
            break
    return resp
