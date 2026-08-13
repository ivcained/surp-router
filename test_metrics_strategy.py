"""Tests for the optional strategy="f1000" routing in combo_resolver.

Covers: empty/undersampled metrics DB -> cheapest fallback identical to the
default resolution; a metrics pick that outranks the cheapest pool member ->
that model is chosen; the min_samples threshold being respected (None ->
fallback); metrics failures never raising or breaking resolution; and a
metrics pick that is not part of the combo's pool being ignored.
"""

import pytest

import combo_resolver as cr

CHEAP = "acme/alpha-1"
PRICEY = "acme/beta-2"
OUTSIDE_POOL = "acme/not-in-pool"


def _market() -> list[dict]:
    return [
        {
            "model": CHEAP,
            "best_price_per_1m": 500_000,
            "best_input_per_1m": 100_000,
            "best_output_per_1m": 200_000,
            "total_cap": 1_000,
            "healthy_seller_count": 1,
        },
        {
            "model": PRICEY,
            "best_price_per_1m": 5_000_000,
            "best_input_per_1m": 300_000,
            "best_output_per_1m": 600_000,
            "total_cap": 1_000,
            "healthy_seller_count": 1,
        },
    ]


def _resolve(strategy=None):
    return cr.resolve("best-chat", _market(), strategy=strategy)


def test_f1000_empty_metrics_db_falls_back_to_cheapest(monkeypatch):
    """best_f1000 -> None (no data): f1000 == default cheapest selection."""
    monkeypatch.setattr(cr.metrics_store, "best_f1000", lambda **kw: None)

    default = _resolve()
    f1000 = _resolve("f1000")

    assert f1000 == default
    assert f1000[0] == CHEAP
    assert f1000[1] == default[1]  # byte-identical debug line (no strategy suffix)


def test_f1000_picks_best_metrics_model(monkeypatch):
    called = {}

    def fake_best_f1000(model_class, min_samples=50, window_s=86400):
        called["model_class"] = model_class
        called["min_samples"] = min_samples
        called["window_s"] = window_s
        return PRICEY  # outranks CHEAP despite costing more

    monkeypatch.setattr(cr.metrics_store, "best_f1000", fake_best_f1000)

    model, debug, price, pool_size = _resolve("f1000")

    assert model == PRICEY
    assert "strategy=f1000" in debug
    assert pool_size == 2
    # metric query contract: same class as the pool, ticket's thresholds
    assert called == {"model_class": "chat", "min_samples": 50, "window_s": 86400}


def test_f1000_undersampled_below_threshold_falls_back(monkeypatch):
    """best_f1000 -> None (COUNT < min_samples): fall back to cheapest."""
    monkeypatch.setattr(cr.metrics_store, "best_f1000", lambda **kw: None)

    f1000 = _resolve("f1000")

    assert f1000 == _resolve()
    assert f1000[0] == CHEAP


def test_f1000_never_raises_when_metrics_db_fails(monkeypatch):
    """best_f1000 raising must never break or change resolution."""

    def boom(**kw):
        raise RuntimeError("metrics db unreachable")

    monkeypatch.setattr(cr.metrics_store, "best_f1000", boom)

    f1000 = _resolve("f1000")

    assert f1000 == _resolve()
    assert f1000[0] == CHEAP


def test_f1000_metrics_pick_outside_pool_falls_back(monkeypatch):
    """Best-F1000 model not a candidate in this combo -> cheapest wins."""
    monkeypatch.setattr(
        cr.metrics_store, "best_f1000", lambda **kw: OUTSIDE_POOL
    )

    f1000 = _resolve("f1000")

    assert f1000 == _resolve()
    assert f1000[0] == CHEAP


def test_unknown_strategy_is_ignored():
    """Additive: a strategy value other than f1000 leaves behavior unchanged."""
    assert _resolve("mystery") == _resolve()
    assert _resolve("fast") == _resolve()
