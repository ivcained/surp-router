"""Tests for live Surp vs OpenRouter price comparison."""

import price_compare as pc


def test_normalize_openrouter_filters_variants_and_converts_per_token_prices():
    rows = pc.normalize_openrouter([
        {"id": "anthropic/claude-opus-5", "name": "Anthropic: Claude Opus 5",
         "pricing": {"prompt": "0.000005", "completion": "0.000025"}},
        {"id": "anthropic/claude-opus-5:batch", "name": "Claude Opus 5 batch",
         "pricing": {"prompt": "0.0000025", "completion": "0.0000125"}},
        {"id": "vendor/image", "architecture": {"output_modalities": ["image"]},
         "pricing": {"prompt": "0.1", "completion": "0.1"}},
    ])
    assert rows == {"claude-opus-5": {
        "openrouter_id": "anthropic/claude-opus-5",
        "name": "Anthropic: Claude Opus 5",
        "input_usd_per_1m": 5.0,
        "output_usd_per_1m": 25.0,
    }}


def test_compare_uses_blended_workload_and_reports_direction():
    surp = [{"model": "claude-opus-5", "usd_per_1m": 3.27, "sellers": 60}]
    openrouter = {"claude-opus-5": {
        "openrouter_id": "anthropic/claude-opus-5", "name": "Anthropic: Claude Opus 5",
        "input_usd_per_1m": 5.0, "output_usd_per_1m": 25.0,
    }}
    row = pc.compare_prices(surp, openrouter, input_share=0.8)[0]
    assert row["openrouter_blended_usd_per_1m"] == 9.0
    assert row["surp_usd_per_1m"] == 3.27
    assert row["savings_usd_per_1m"] == 5.73
    assert row["savings_pct"] == 63.67
    assert row["cheaper"] == "surp"


def test_compare_handles_openrouter_cheaper_and_summary():
    surp = [{"model": "model-a", "usd_per_1m": 3.0, "sellers": 2}]
    openrouter = {"model-a": {
        "openrouter_id": "org/model-a", "name": "Model A",
        "input_usd_per_1m": 1.0, "output_usd_per_1m": 2.0,
    }}
    payload = pc.build_payload(surp, openrouter, input_share=0.5)
    assert payload["models"][0]["cheaper"] == "openrouter"
    assert payload["summary"]["surp_cheaper_count"] == 0
    assert payload["summary"]["openrouter_cheaper_count"] == 1
    assert payload["methodology"]["input_share"] == 0.5


def test_model_key_aliases_known_separator_differences():
    assert pc.model_key("openai/gpt-5.6-sol") == "gpt-5.6-sol"
    assert pc.model_key("anthropic/claude-opus-4-8") == pc.model_key("claude-opus-4.8")