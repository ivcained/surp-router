# -*- coding: utf-8 -*-
"""Single-writer, write-behind SQLite metrics store (drop-in: metrics_store.py).

This is a NEW, SEPARATE database from stats.py's requests table. It records
per-request latency/throughput samples for the TPS/live-metrics dashboards
without ever backpressuring user traffic.

Startup:
    import metrics_store
    asyncio.create_task(metrics_store.metric_writer.run())

Producers:
    metrics_store.metric_writer.enqueue(sample)  # non-blocking, drops on full

Design:
  * Single-writer asyncio queue; enqueue() never blocks, drops metrics when
    the queue is full rather than stalling a request.
  * Writes are flushed in batches (batch=50) every flush_s seconds inside a
    single transaction using WAL + synchronous=NORMAL.
  * Aggregates (avg/p95 TTFT, avg/p95 TPS, avg F1000/h, sample counts) are
    rolled up per provider/model into metric_rollups (ts bucket) on a ~30s
    cadence, for frontend history and /api/benchmarks.
  * Raw metric_samples older than RETENTION_S (14 days) are purged during
    flush; rollups are kept forever.

Read API (public, thread-safe, best-effort):
    get_rollups(bucket_seconds, limit)
    recent_samples(limit)
    best_f1000(model_class, min_samples, window_s)
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("surp.metrics")

DB_PATH = os.environ.get("SURP_METRICS_DB", str(Path(__file__).resolve().parent / "metrics.db"))

RETENTION_S = 14 * 86400  # raw samples kept 14 days
ROLLUP_BUCKET_SECONDS = 30  # rollup ts bucket size
ROLLUP_INTERVAL_S = 30.0  # rollup cadence (~30s)
MAX_BACKFILL_BUCKETS = 2880  # catch-up cap after downtime (24h of 30s buckets)

SCHEMA = """
CREATE TABLE IF NOT EXISTS metric_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'request',
  success INTEGER NOT NULL,
  ttft_ms REAL,
  gen_ms REAL,
  total_ms REAL,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  tps REAL,
  f1000_h REAL,
  estimated INTEGER DEFAULT 0,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_ms_model_ts ON metric_samples(model, ts);
CREATE INDEX IF NOT EXISTS idx_ms_provider_ts ON metric_samples(provider, ts);
CREATE TABLE IF NOT EXISTS metric_rollups (
  bucket_ts INTEGER NOT NULL,
  bucket_seconds INTEGER NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  success INTEGER NOT NULL DEFAULT 1,
  sample_count INTEGER NOT NULL,
  avg_ttft_ms REAL,
  p95_ttft_ms REAL,
  avg_tps REAL,
  p95_tps REAL,
  avg_f1000_h REAL,
  PRIMARY KEY (bucket_ts, bucket_seconds, provider, model, success)
);
"""

INSERT = """
INSERT INTO metric_samples
(ts, provider, model, source, success, ttft_ms, gen_ms, total_ms,
 prompt_tokens, completion_tokens, tps, f1000_h, estimated, error)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

INSERT_ROLLUP = """
INSERT OR IGNORE INTO metric_rollups
(bucket_ts, bucket_seconds, provider, model, success, sample_count,
 avg_ttft_ms, p95_ttft_ms, avg_tps, p95_tps, avg_f1000_h)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

ROLLUP_SELECT = """
SELECT provider, model, ttft_ms, tps, f1000_h
FROM metric_samples
WHERE ts >= ? AND ts < ? AND success = 1
"""


def _p95(values: List[float]) -> Optional[float]:
    """Nearest-rank 95th percentile; None for empty input, stable for n==1."""
    if not values:
        return None
    values = sorted(values)
    return values[max(0, int(math.ceil(0.95 * len(values))) - 1)]


class MetricWriter:
    """Single-writer, write-behind async metrics sink (never blocks callers)."""

    def __init__(
        self,
        db_path: str,
        batch: int = 50,
        flush_s: float = 2.0,
        max_queue: int = 5000,
        rollup_interval_s: float = ROLLUP_INTERVAL_S,
        rollup_bucket_seconds: int = ROLLUP_BUCKET_SECONDS,
        retention_s: int = RETENTION_S,
    ) -> None:
        self.db_path = db_path
        self.batch = batch
        self.flush_s = flush_s
        self.q: "asyncio.Queue[Any]" = asyncio.Queue(maxsize=max_queue)
        self.rollup_interval_s = rollup_interval_s
        self.rollup_bucket_seconds = rollup_bucket_seconds
        self.retention_s = retention_s
        self._conn: Optional[sqlite3.Connection] = None

    def enqueue(self, sample: Any) -> None:
        """Non-blocking: drop the sample before ever stalling a request."""
        try:
            self.q.put_nowait(sample)
        except asyncio.QueueFull:
            pass  # drop metrics rather than backpressure user traffic

    def _open(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA wal_autocheckpoint=2000")
        conn.executescript(SCHEMA)
        return conn

    def _insert_batch(self, conn: sqlite3.Connection, buf: List[Any]) -> None:
        if not buf:
            return
        with conn:  # one transaction per batch
            conn.executemany(
                INSERT,
                [
                    (
                        s.ts,
                        s.provider,
                        s.model,
                        s.source,
                        int(bool(s.success)),
                        s.ttft_ms,
                        s.gen_ms,
                        s.total_ms,
                        s.prompt_tokens,
                        s.completion_tokens,
                        s.tps,
                        s.f1000_h,
                        int(bool(s.estimated)),
                        s.error,
                    )
                    for s in buf
                ],
            )

    def _purge_old(self, conn: sqlite3.Connection, now: Optional[float] = None) -> int:
        now = time.time() if now is None else now
        with conn:
            cur = conn.execute(
                "DELETE FROM metric_samples WHERE ts < ?",
                (now - self.retention_s,),
            )
            return cur.rowcount

    def _roll_bucket(self, conn: sqlite3.Connection, bucket_ts: int, bucket_s: int) -> None:
        """Compute one finished ts bucket into metric_rollups (idempotent)."""
        start, end = bucket_ts, bucket_ts + bucket_s
        groups: dict = {}
        for provider, model, ttft_ms, tps, f1000_h in conn.execute(ROLLUP_SELECT, (start, end)):
            key = (provider, model)
            g = groups.setdefault(
                key,
                {"n": 0, "ttfts": [], "tpss": [], "f1000s": []},
            )
            g["n"] += 1
            if ttft_ms is not None:
                g["ttfts"].append(ttft_ms)
            if tps is not None:
                g["tpss"].append(tps)
            if f1000_h is not None:
                g["f1000s"].append(f1000_h)
        for (provider, model), g in groups.items():
            conn.execute(
                INSERT_ROLLUP,
                (
                    bucket_ts,
                    bucket_s,
                    provider,
                    model,
                    1,  # success
                    g["n"],
                    (sum(g["ttfts"]) / len(g["ttfts"])) if g["ttfts"] else None,
                    _p95(g["ttfts"]),
                    (sum(g["tpss"]) / len(g["tpss"])) if g["tpss"] else None,
                    _p95(g["tpss"]),
                    (sum(g["f1000s"]) / len(g["f1000s"])) if g["f1000s"] else None,
                ),
            )

    def _rollup(self, conn: sqlite3.Connection, now: Optional[float] = None) -> None:
        """Roll up finished buckets since the marker, capped backfill."""
        now = time.time() if now is None else now
        bs = self.rollup_bucket_seconds
        newest = (int(now) // bs) * bs - bs  # last fully elapsed bucket
        row = conn.execute(
            "SELECT MAX(bucket_ts) FROM metric_rollups WHERE bucket_seconds = ?",
            (bs,),
        ).fetchone()
        start_bucket = newest - bs if row[0] is None else row[0] + bs
        done = 0
        b = start_bucket
        while b <= newest and done < MAX_BACKFILL_BUCKETS:
            self._roll_bucket(conn, b, bs)
            done += 1
            b += bs
        conn.commit()

    async def run(self) -> None:
        self._conn = self._open()
        buf: List[Any] = []
        last_rollup = 0.0
        while True:
            try:
                item = await asyncio.wait_for(self.q.get(), timeout=self.flush_s)
                buf.append(item)
                while len(buf) < self.batch:
                    buf.append(self.q.get_nowait())
            except (asyncio.TimeoutError, asyncio.QueueEmpty):
                pass
            if buf:
                try:
                    self._insert_batch(self._conn, buf)
                    self._purge_old(self._conn)
                    now = time.time()
                    if now - last_rollup >= self.rollup_interval_s:
                        self._rollup(self._conn, now)
                        last_rollup = now
                except sqlite3.Error:
                    # Never let a bad row kill the writer task — drop the batch
                    # and keep draining the queue (metrics are best-effort).
                    log.debug("metrics_store: batch dropped (sqlite error)", exc_info=True)
                buf.clear()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None


metric_writer = MetricWriter(DB_PATH)

_read_conn: Optional[sqlite3.Connection] = None
_read_conn_path: Optional[str] = None


def _get_read_conn() -> Optional[sqlite3.Connection]:
    """Lazy, path-keyed read connection (WAL allows concurrent readers)."""
    global _read_conn, _read_conn_path
    path = metric_writer.db_path
    if _read_conn is None or _read_conn_path != path:
        if _read_conn is not None:
            try:
                _read_conn.close()
            except sqlite3.Error:
                pass
        try:
            _read_conn = sqlite3.connect(path, check_same_thread=False)
            _read_conn.row_factory = sqlite3.Row
            _read_conn.execute("PRAGMA busy_timeout=8000")
            _read_conn_path = path
        except sqlite3.Error:
            _read_conn = None
    return _read_conn


def get_rollups(
    bucket_seconds: int = ROLLUP_BUCKET_SECONDS,
    limit: int = 500,
) -> List[dict]:
    """Rollup rows (newest bucket first) for dashboard history/benchmarks."""
    try:
        conn = _get_read_conn()
        if conn is None:
            return []
        rows = conn.execute(
            "SELECT bucket_ts, provider, model, success, sample_count, "
            "avg_ttft_ms, p95_ttft_ms, avg_tps, p95_tps, avg_f1000_h "
            "FROM metric_rollups WHERE bucket_seconds = ? "
            "ORDER BY bucket_ts DESC, provider, model LIMIT ?",
            (bucket_seconds, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        log.debug("metrics_store.get_rollups failed", exc_info=True)
        return []


def recent_samples(limit: int = 100) -> List[dict]:
    """Most recent raw samples, newest first."""
    try:
        conn = _get_read_conn()
        if conn is None:
            return []
        rows = conn.execute(
            "SELECT ts, provider, model, source, success, ttft_ms, gen_ms, "
            "total_ms, tps, f1000_h, estimated "
            "FROM metric_samples ORDER BY ts DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        log.debug("metrics_store.recent_samples failed", exc_info=True)
        return []


def best_f1000(
    model_class: str,
    min_samples: int = 50,
    window_s: int = 86400,
) -> Optional[str]:
    """Provider/model with the best observed F1000/h within the window, or None.

    ``model_class`` matches model names exactly or by prefix; only combos with
    at least ``min_samples`` successful observations are candidates. F1000 is
    HOURS-per-1000-tasks (lower = faster), so the winner is the MIN aggregate.
    """
    try:
        conn = _get_read_conn()
        if conn is None:
            return None
        row = conn.execute(
            "SELECT provider, model, AVG(f1000_h) AS avg_f1000, COUNT(*) AS n "
            "FROM metric_samples "
            "WHERE success = 1 AND f1000_h IS NOT NULL AND ts >= ? "
            "AND (model = ? OR model LIKE ?) "
            "GROUP BY provider, model HAVING COUNT(*) >= ? "
            "ORDER BY avg_f1000 ASC LIMIT 1",
            (time.time() - window_s, model_class, model_class + "%", min_samples),
        ).fetchone()
        if row is None:
            return None
        return f"{row['provider']}/{row['model']}"
    except sqlite3.Error:
        log.debug("metrics_store.best_f1000 failed", exc_info=True)
        return None
