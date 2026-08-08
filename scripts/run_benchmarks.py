#!/usr/bin/env python3
"""Scheduled benchmark runner: keeps the /performance leaderboard fresh.

Benchmarks the top cheap, high-throughput models on Surplus every run.
Designed to be called by a cron job every 6 hours.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import benchmark_runner as br

# Models to benchmark regularly — the cheap, high-throughput pool that
# matters for the "100 TPS at low cost" value proposition.
BENCH_MODELS = [
    "deepseek-v4-flash-0731",
    "deepseek-v4-flash",
    "glm-5.2",
    "deepseek-v4-pro",
    "gpt-5.6-luna",
    "llama-3.3-70b-instruct",
]


async def main() -> None:
    api_key = os.environ.get("SURP_BENCH_KEY", "")
    if not api_key:
        # Try to read from the persisted benchmark key file.
        try:
            with open("/tmp/bench_key") as f:
                api_key = f.read().strip()
        except FileNotFoundError:
            print("No API key available — skipping benchmark run.")
            return

    for model in BENCH_MODELS:
        try:
            await br.run_benchmark(model, runs=5, max_tokens=400, api_key=api_key)
        except Exception as e:
            print(f"Benchmark failed for {model}: {e}")
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
