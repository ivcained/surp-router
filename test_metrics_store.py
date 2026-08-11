# -*- coding: utf-8 -*-
"""Unit tests for metrics_store.py (tmp dirs only, no real I/O leaks)."""
from __future__ import annotations

import asyncio
import sqlite3
import time

import pytest

import metrics_store as ms
from metrics_core import StreamSample


def _writer(tmp_path, **kw) -> ms.MetricWriter:
    return ms.MetricWriter(str(tmp_path / "metrics.db"), **kw)


def _sample(**kw) -> StreamSample:
    base = dict(ts=time.time(), provider="p1", model="m1", success=1, tps=10.0)
    base.update(kw)
    return StreamSample(**base)


def _count(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM metric_samples"
        ).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def test_batching_insert(tmp_path):
    """run() drains the queue into batches and persists every sample."""
    w = _writer(tmp_path, batch=4, flush_s=0.05)

    async def scenario():
        task = asyncio.create_task(w.run())
        for i in range(10):
            w.enqueue(_sample(ts=time.time(), tps=float(i)))
        deadline = time.time() + 5
        while w._conn is None or _count(w.db_path) != 10:
            assert time.time() < deadline, "timed out waiting for flush"
            await asyncio.sleep(0.02)
        assert _count(w.db_path) == 10
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    w.close()


def test_drop_on_full(tmp_path):
    """Queue is capped; enqueue beyond max drops instead of blocking."""
    w = _writer(tmp_path, max_queue=5)
    for _ in range(20):
        w.enqueue(_sample())
    assert w.q.qsize() == 5
    w.close()


def test_rollup_correctness_p95(tmp_path, monkeypatch):
    """Rollup aggregates per provider/model: counts, avg and p95."""
    w = _writer(tmp_path)
    conn = w._open()
    monkeypatch.setattr(ms, "metric_writer", w)

    # bucket [990, 1020)
    rows = [
        StreamSample(ts=990 + i, provider="p1", model="m1", success=1,
                        ttft_ms=t, tps=tps, f1000_h=f)
        for i, (t, tps, f) in enumerate(
            [(100, 10, 1), (200, 20, 2), (300, 30, 3), (400, 40, 4)]
        )
    ]
    rows.append(StreamSample(ts=995, provider="p2", model="m1", success=1,
                                ttft_ms=500, tps=5, f1000_h=9))
    w._insert_batch(conn, rows)

    w._rollup(conn, now=1020)

    rollups = {r["provider"]: r for r in ms.get_rollups(bucket_seconds=30)}
    assert set(rollups) == {"p1", "p2"}

    p1 = rollups["p1"]
    assert p1["sample_count"] == 4
    assert p1["avg_ttft_ms"] == 250.0
    assert p1["p95_ttft_ms"] == 400.0  # n=4 -> nearest-rank idx 3
    assert p1["avg_tps"] == 25.0
    assert p1["p95_tps"] == 40.0
    assert p1["avg_f1000_h"] == 2.5

    p2 = rollups["p2"]
    assert p2["sample_count"] == 1
    assert p2["avg_ttft_ms"] == 500.0
    assert p2["p95_ttft_ms"] == 500.0  # stable for n == 1

    # idempotent: re-rolling the same bucket must not duplicate rows
    w._rollup(conn, now=1020)
    assert len(ms.get_rollups(bucket_seconds=30)) == 2
    w.close()


def test_purge_old_rows(tmp_path, monkeypatch):
    """Raw samples older than retention are purged; rollups survive."""
    w = _writer(tmp_path)
    conn = w._open()
    monkeypatch.setattr(ms, "metric_writer", w)

    now = time.time()
    w._insert_batch(conn, [
        StreamSample(ts=now - 15 * 86400, provider="old", model="m1", success=1),
        StreamSample(ts=now - 100, provider="new", model="m1", success=1),
    ])
    conn.execute(
        ms.INSERT_ROLLUP,
        (990, 30, "old", "m1", 1, 1, 1.0, 1.0, 1.0, 1.0, 1.0),
    )
    conn.commit()

    deleted = w._purge_old(conn, now=now)
    assert deleted == 1
    assert _count(w.db_path) == 1  # fresh row kept

    kept = conn.execute(
        "SELECT COUNT(*) FROM metric_rollups WHERE bucket_ts = 990"
    ).fetchone()[0]
    assert kept == 1  # rollups kept forever
    w.close()


def test_best_f1000_threshold(tmp_path, monkeypatch):
    """best_f1000 returns best provider/model above min_samples within window."""
    w = _writer(tmp_path)
    conn = w._open()
    monkeypatch.setattr(ms, "metric_writer", w)

    now = time.time()
    rows = []
    # a: 50 samples @ f1000=5.0h ; b: 60 @ 9.0h (slower) ; c: prefix match @ 7.0h
    # f1000 is HOURS: lower = faster/better, so "a" must win on ASC ordering.
    rows += [StreamSample(ts=now - 100, provider="a", model="gpt-x",
                             success=1, f1000_h=5.0) for _ in range(50)]
    rows += [StreamSample(ts=now - 100, provider="b", model="gpt-x",
                             success=1, f1000_h=9.0) for _ in range(60)]
    rows += [StreamSample(ts=now - 100, provider="c", model="gpt-x-extra",
                             success=1, f1000_h=7.0) for _ in range(50)]
    # d: below threshold, must never win despite the high value
    rows += [StreamSample(ts=now - 100, provider="d", model="gpt-x",
                             success=1, f1000_h=100.0) for _ in range(10)]
    # e: outside window, must be excluded
    rows += [StreamSample(ts=now - 2 * 86400, provider="e", model="gpt-x",
                             success=1, f1000_h=99.0) for _ in range(50)]
    w._insert_batch(conn, rows)

    assert ms.best_f1000("gpt-x") == "a/gpt-x"  # lowest f1000_h wins
    assert ms.best_f1000("gpt-x", min_samples=100) is None  # threshold too high
    assert ms.best_f1000("does-not-exist") is None
    w.close()


def test_recent_samples(tmp_path, monkeypatch):
    """recent_samples returns newest-first raw rows."""
    w = _writer(tmp_path)
    conn = w._open()
    monkeypatch.setattr(ms, "metric_writer", w)

    now = time.time()
    w._insert_batch(conn, [
        StreamSample(ts=now - 5, provider="p", model="m1", success=1, tps=1.0),
        StreamSample(ts=now - 1, provider="p", model="m2", success=1, tps=2.0),
    ])
    samples = ms.recent_samples(limit=10)
    assert len(samples) == 2
    assert samples[0]["model"] == "m2"  # newest first
    assert samples[1]["model"] == "m1"
    w.close()
