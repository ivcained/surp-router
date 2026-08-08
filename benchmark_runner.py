#!/usr/bin/env python3
"""Live benchmark runner: streams real requests through surp and records
verified generation throughput (output tokens/second), TTFT, and wall time.

Usage:
    python3 benchmark_runner.py --model deepseek-v4-flash-0731 --runs 10
    python3 benchmark_runner.py --free  # benchmark the surp/free pool
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any, Optional

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import combo_resolver as cr
import model_benchmarks as mb

GATEWAY = os.environ.get("SURP_GATEWAY", "https://surp.ivc.lol")
BENCH_PROMPTS = [
    "Write a 200-word explanation of how HTTP/2 multiplexing improves web performance.",
    "Explain the difference between TCP and UDP with 3 examples each.",
    "Write a Python function that reverses a linked list and explain its O(n) complexity.",
    "Describe the CAP theorem and give a real-world example of each tradeoff.",
    "Write a 150-word product description for a wireless mechanical keyboard.",
]


async def _stream_benchmark(session: aiohttp.ClientSession, model: str,
                             prompt: str, max_tokens: int = 512,
                             api_key: str = "", is_free: bool = False) -> dict[str, Any]:
    """Stream one request, measuring TTFT and generation throughput precisely."""
    headers = {"Content-Type": "application/json"}
    # Use direct passthrough to pin a specific model for benchmarking.
    full_model = "surp/free" if is_free else f"surp/direct/{model}"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": full_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
    }

    t0 = time.monotonic()
    ttft_ms = 0
    first_chunk_time = None
    last_chunk_time = None
    output_text = ""
    usage = {}
    status = "ok"
    error = ""

    try:
        async with session.post(
            f"{GATEWAY}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120, sock_read=120),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                status = "failed"
                error = f"HTTP {resp.status}: {body[:200]}"
                mb.record(model if not is_free else "surp/free", 0, int((time.monotonic() - t0) * 1000),
                          0, 0, 0.0, status, error)
                return {"status": status, "error": error}

            async for line in resp.content:
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str or not line_str.startswith("data:"):
                    continue
                data_str = line_str[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except Exception:
                    continue
                if first_chunk_time is None:
                    first_chunk_time = time.monotonic()
                    ttft_ms = int((first_chunk_time - t0) * 1000)
                last_chunk_time = time.monotonic()
                # Extract token text
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    output_text += delta.get("content", "") or ""
                if chunk.get("usage"):
                    usage = chunk["usage"]

    except Exception as e:
        status = "failed"
        error = str(e)[:200]
        wall = int((time.monotonic() - t0) * 1000)
        mb.record(model if not is_free else "surp/free", ttft_ms, wall, 0, 0, 0.0, status, error)
        return {"status": status, "error": error}

    wall_ms = int((time.monotonic() - t0) * 1000)
    # Generation time = wall - TTFT (time spent generating after first token)
    generation_ms = max(0, wall_ms - ttft_ms)
    # Prefer usage-reported tokens; fall back to rough char/4 estimate
    output_tokens = int(usage.get("completion_tokens") or 0)
    if output_tokens == 0 and output_text:
        output_tokens = max(1, len(output_text) // 4)
    prompt_tokens = int(usage.get("prompt_tokens") or 0)

    # Get the actual routed model from headers/usage if available
    recorded_model = "surp/free" if is_free else model

    # Look up price from the live market data.
    price = 0.0
    try:
        import aiohttp as _aio
        async with _aio.ClientSession() as _s:
            async with _s.get(f"{GATEWAY}/api/models", timeout=_aio.ClientTimeout(total=10)) as _r:
                _cat = (await _r.json()).get("models", [])
                for _m in _cat:
                    if _m.get("model") == model:
                        price = float(_m.get("usd_per_1m", 0))
                        break
    except Exception:
        pass

    tps = mb.output_tps(output_tokens, generation_ms / 1000)
    mb.record(recorded_model, ttft_ms, wall_ms, output_tokens, generation_ms, price, "ok")

    return {
        "status": "ok",
        "model": recorded_model,
        "ttft_ms": ttft_ms,
        "wall_ms": wall_ms,
        "generation_ms": generation_ms,
        "output_tokens": output_tokens,
        "output_tps": tps,
        "price_usd_per_1m": price,
        "prompt_tokens": prompt_tokens,
    }


async def run_benchmark(model: str, runs: int = 10, max_tokens: int = 512,
                         api_key: str = "", is_free: bool = False) -> None:
    """Run multiple benchmark iterations and print a summary."""
    print(f"\n{'='*60}")
    print(f"  benchmarking: {model} ({runs} runs, max_tokens={max_tokens})")
    print(f"{'='*60}")

    results = []
    async with aiohttp.ClientSession() as session:
        for i in range(runs):
            prompt = BENCH_PROMPTS[i % len(BENCH_PROMPTS)]
            r = await _stream_benchmark(session, model, prompt, max_tokens, api_key, is_free)
            if r["status"] == "ok":
                results.append(r)
                print(f"  run {i+1:2d}: TPS={r['output_tps']:6.1f}  TTFT={r['ttft_ms']:5d}ms  "
                      f"wall={r['wall_ms']:5d}ms  tokens={r['output_tokens']:4d}  "
                      f"price=${r['price_usd_per_1m']:.4f}/M")
            else:
                print(f"  run {i+1:2d}: FAILED - {r.get('error','')[:80]}")
            await asyncio.sleep(0.5)

    if results:
        tps_vals = [r["output_tps"] for r in results]
        ttft_vals = [r["ttft_ms"] for r in results]
        import statistics
        print(f"\n{'='*60}")
        print(f"  SUMMARY: {model}")
        print(f"{'='*60}")
        print(f"  successful runs:   {len(results)}/{runs}")
        print(f"  p50 output TPS:    {statistics.median(tps_vals):.1f}")
        print(f"  mean output TPS:   {statistics.mean(tps_vals):.1f}")
        print(f"  min/max TPS:       {min(tps_vals):.1f} / {max(tps_vals):.1f}")
        print(f"  p50 TTFT:          {statistics.median(ttft_vals):.0f}ms")
        if results[0]["price_usd_per_1m"] > 0:
            tpd = mb.throughput_per_dollar(statistics.median(tps_vals), results[0]["price_usd_per_1m"])
            print(f"  price:             ${results[0]['price_usd_per_1m']:.4f}/M")
            print(f"  throughput/$:      {tpd:,}")
        print(f"\n  data recorded to health board + /api/benchmarks")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live LLM throughput benchmark")
    parser.add_argument("--model", default="deepseek-v4-flash-0731",
                        help="model to benchmark")
    parser.add_argument("--runs", type=int, default=10, help="number of runs")
    parser.add_argument("--max-tokens", type=int, default=512, help="max output tokens per run")
    parser.add_argument("--api-key", default="", help="paid API key")
    parser.add_argument("--free", action="store_true", help="benchmark surp/free pool")
    args = parser.parse_args()

    asyncio.run(run_benchmark(args.model, args.runs, args.max_tokens, args.api_key, args.free))


if __name__ == "__main__":
    main()
