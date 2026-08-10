"""Single-writer, write-behind SQLite store (drop-in: metrics_store.py).

Startup: asyncio.create_task(metric_writer.run())
Producers: metric_writer.enqueue(sample)  -- non-blocking, drops on full.
"""
from __future__ import annotations

import asyncio
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'request',
    success INTEGER NOT NULL,
    ttft_ms REAL, gen_ms REAL, total_ms REAL,
    prompt_tokens INTEGER, completion_tokens INTEGER,
    tps REAL, f1000_h REAL,
    estimated INTEGER DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_ms_model_ts ON metric_samples(model, ts);
CREATE INDEX IF NOT EXISTS idx_ms_provider_ts ON metric_samples(provider, ts);
"""

INSERT = """
INSERT INTO metric_samples
(ts, provider, model, source, success, ttft_ms, gen_ms, total_ms,
 prompt_tokens, completion_tokens, tps, f1000_h, estimated, error)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


class MetricWriter:
    def __init__(self, db_path: str, batch: int = 50, flush_s: float = 2.0):
        self.q: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self.db_path, self.batch, self.flush_s = db_path, batch, flush_s

    def enqueue(self, sample) -> None:
        try:
            self.q.put_nowait(sample)
        except asyncio.QueueFull:
            pass  # drop metrics before backpressuring user traffic

    async def run(self) -> None:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA wal_autocheckpoint=2000")
        conn.executescript(SCHEMA)
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
                with conn:  # one transaction per batch
                    conn.executemany(
                        INSERT,
                        [
                            (
                                s.ts, s.provider, s.model, s.source, s.success,
                                s.ttft_ms, s.gen_ms, s.total_ms,
                                s.prompt_tokens, s.completion_tokens,
                                s.tps, s.f1000_h, s.estimated, s.error,
                            )
                            for s in buf
                        ],
                    )
                buf.clear()


metric_writer = MetricWriter("metrics.db")
