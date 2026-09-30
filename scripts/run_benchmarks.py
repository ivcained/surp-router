#!/usr/bin/env python3
"""Scheduled benchmark runner: keeps the /performance leaderboard fresh.

Benchmarks the top cheap, high-throughput models on Surplus every run.
Designed to be called by a cron job every 6 hours.
"""

import asyncio
import os
import sys

# Make the repo root importable when invoked as `python3 scripts/run_benchmarks.py`
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
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
            pass
    if not api_key:
        # Fall back to the server env file (survives /tmp cleanup on reboot).
        try:
            with open("/etc/surp/surp.env") as f:
                for line in f:
                    if line.startswith("SURP_BENCH_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except FileNotFoundError:
            pass
    if not api_key:
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
