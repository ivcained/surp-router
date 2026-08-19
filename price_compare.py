"""Live Surp vs OpenRouter price comparison.

Surp's public catalog currently exposes one estimated/blended USD-per-1M value.
OpenRouter exposes separate input and output token rates. For a fair single
number, callers choose an input-token share (default 80% input / 20% output).
The API always returns both raw OpenRouter rates and the methodology.
"""

from __future__ import annotations

import re
from typing import Any


_PROVIDER_PREFIXES = {
    "anthropic", "openai", "google", "deepseek", "meta-llama", "mistralai",
    "qwen", "x-ai", "z-ai", "moonshotai", "cohere", "amazon", "nvidia",
}


def model_key(value: str) -> str:
    value = str(value or "").strip().lower()
    if "/" in value and value.split("/", 1)[0] in _PROVIDER_PREFIXES:
        value = value.split("/", 1)[1]
    value = value.split(":", 1)[0]
    value = value.replace("_", "-")
    # Surp and OpenRouter sometimes disagree only on punctuation in version
    # suffixes (claude-opus-4-8 vs claude-opus-4.8).
    value = re.sub(r"-(\d+)-(\d+)(?=$|-)", r"-\1.\2", value)
    return value


def normalize_openrouter(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        model_id = str(row.get("id") or "")
        if not model_id or ":" in model_id:
            continue  # exclude :free, :batch, :exacto and other variants
        output_modalities = ((row.get("architecture") or {}).get("output_modalities") or ["text"])
        if "text" not in output_modalities:
            continue
        pricing = row.get("pricing") or {}
        try:
            prompt = float(pricing.get("prompt")) * 1_000_000
            completion = float(pricing.get("completion")) * 1_000_000
        except (TypeError, ValueError):
            continue
        if prompt < 0 or completion < 0:
            continue
        key = model_key(model_id)
        out[key] = {
            "openrouter_id": model_id,
            "name": row.get("name") or model_id,
            "input_usd_per_1m": round(prompt, 6),
            "output_usd_per_1m": round(completion, 6),
        }
    return out


def compare_prices(
    surp_rows: list[dict[str, Any]],
    openrouter: dict[str, dict[str, Any]],
    *,
    input_share: float = 0.8,
) -> list[dict[str, Any]]:
    if not 0 <= input_share <= 1:
        raise ValueError("input_share must be between 0 and 1")
    rows = []
    for surp in surp_rows:
        key = model_key(surp.get("model", ""))
        other = openrouter.get(key)
        if other is None:
            continue
        surp_price = float(surp.get("usd_per_1m") or 0)
        if surp_price < 0:
            continue
        blended = other["input_usd_per_1m"] * input_share + other["output_usd_per_1m"] * (1 - input_share)
        delta = blended - surp_price
        pct = (delta / blended * 100) if blended else 0.0
        rows.append({
            "model": surp.get("model"),
            "name": other["name"],
            "openrouter_id": other["openrouter_id"],
            "class": surp.get("class"),
            "pro": bool(surp.get("pro")),
            "sellers": surp.get("sellers"),
            "surp_usd_per_1m": round(surp_price, 6),
            "openrouter_input_usd_per_1m": other["input_usd_per_1m"],
            "openrouter_output_usd_per_1m": other["output_usd_per_1m"],
            "openrouter_blended_usd_per_1m": round(blended, 6),
            "savings_usd_per_1m": round(abs(delta), 6),
            "savings_pct": round(abs(pct), 2),
            "cheaper": "surp" if delta > 0 else "openrouter" if delta < 0 else "tie",
        })
    rows.sort(key=lambda row: (row["cheaper"] != "surp", -row["savings_pct"], row["model"] or ""))
    return rows


def build_payload(
    surp_rows: list[dict[str, Any]],
    openrouter: dict[str, dict[str, Any]],
    *,
    input_share: float = 0.8,
    generated_at: str | None = None,
    source_age_seconds: int = 0,
) -> dict[str, Any]:
    rows = compare_prices(surp_rows, openrouter, input_share=input_share)
    surp_cheaper = [row for row in rows if row["cheaper"] == "surp"]
    openrouter_cheaper = [row for row in rows if row["cheaper"] == "openrouter"]
    avg = round(sum(row["savings_pct"] for row in surp_cheaper) / len(surp_cheaper), 2) if surp_cheaper else 0.0
    return {
        "summary": {
            "overlap_count": len(rows),
            "surp_cheaper_count": len(surp_cheaper),
            "openrouter_cheaper_count": len(openrouter_cheaper),
            "ties": len(rows) - len(surp_cheaper) - len(openrouter_cheaper),
            "avg_savings_pct_when_surp_cheaper": avg,
        },
        "methodology": {
            "input_share": input_share,
            "output_share": round(1 - input_share, 4),
            "comparison_unit": "USD per 1M blended tokens",
            "surp_price_note": "Surp catalog's estimated/blended usd_per_1m value",
            "openrouter_price_note": "OpenRouter listed input/output rates blended by the selected workload",
            "excludes": "OpenRouter variants such as :free and :batch",
        },
        "generated_at": generated_at,
        "source_age_seconds": source_age_seconds,
        "models": rows,
    }
