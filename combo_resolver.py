#!/usr/bin/env python3
"""
Shared combo resolution logic for surp.ivc.lol.

Imported by BOTH proxy.py (the :20129 resolver) and gateway.py (the :20130
x402 gateway) so the two can never disagree about what a combo means.

Contains:
  * the model class taxonomy (coding / reasoning / vision / fast / chat)
  * the 15 built-in combos
  * user-defined custom combos, persisted in SQLite
  * resolve() — the single entry point: combo name -> cheapest concrete model
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from typing import Any, Optional

import metrics_store

# ──────────────────────────────────────────────────────────────────────────────
# Price units
#
# Surplus `best_price_per_1m` is denominated so that 1e6 == $1.00 per 1M tokens.
# Calibrated against known retail: gemini-2.5-pro 1687500 -> $1.69/1M (real
# ~$1.70), gpt-4o 3125000 -> $3.13/1M, glm-5.2 30000 -> $0.03/1M.
# ──────────────────────────────────────────────────────────────────────────────
PRICE_DIVISOR = 1e6

# Baseline for "you save X%" comparisons: blended claude-sonnet-4.6 list price.
RETAIL_BASELINE_USD_PER_1M = 9.0

DB_PATH = os.environ.get("SURP_DB", "/root/.hermes/surp-router/combos.db")

# ──────────────────────────────────────────────────────────────────────────────
# Class taxonomy
# ──────────────────────────────────────────────────────────────────────────────

CODING_TOKENS = ("coder", "codex", "kimi-k2.7-code", "qwen3-coder", "gpt-5.2-codex", "gpt-5.3-codex")
REASONING_TOKENS = ("deepseek-r1", "-r1", "thinking", "reasoning")
# Genuine multimodal vision LLMs. Deliberately excludes "-image" suffixes —
# those are image-GEN models that merely carry text pricing.
VISION_TOKENS = ("-vl", "vision", "multimodal", "palmyra-vision", "phi-4-multimodal", "glm-5v", "5v-turbo")
FAST_TOKENS = ("mini", "nano", "air", "3b-instruct", "4b-it", "8b", "9b", "12b-it", "small", "flash-lite", "-lite", "e2b", "ministral-3")
PRO_TOKENS = (
    "claude-opus", "claude-sonnet-5", "claude-sonnet-4.6", "claude-sonnet-4.5",
    "claude-fable", "claude-opus-5", "claude-opus-4",
    "gpt-5.5", "gpt-5.4-pro", "gpt-5.5-pro",
    "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
    "gpt-5.3-codex", "gpt-5.2-codex",
    "gemini-3.1-pro", "gemini-2.5-pro",
    "grok-4", "grok-4.3", "grok-4.5", "grok-build",
    "kimi-k3", "deepseek-r1", "qwen3-coder", "qwen3.5-397b",
    "qwen3-vl", "glm-5v", "palmyra-vision", "phi-4-multimodal",
)

BUILTIN_COMBOS: list[str] = [
    "best-coding", "best-reasoning", "best-fast", "best-vision", "best-chat",
    "best-coding-fast",
    "pro-coding", "pro-reasoning", "pro-vision", "pro-chat", "pro-fast",
    "coding", "fast", "chat",
    "free", "srup-free",
    "free-coding", "free-fast",
]

# Human-readable descriptions, shown on the site.
COMBO_DESCRIPTIONS: dict[str, str] = {
    "best-coding": "cheapest coding-class model (coder / codex / qwen3-coder)",
    "best-reasoning": "cheapest reasoning model (thinking / r1)",
    "best-fast": "cheapest small/fast model (mini / nano / lite / small)",
    "best-vision": "cheapest multimodal vision model (-vl / vision / 5v)",
    "best-chat": "cheapest general text LLM (no specialization)",
    "best-coding-fast": "cheapest coding model, biased to small/fast variants",
    "pro-coding": "cheapest FRONTIER-tier coding model",
    "pro-reasoning": "cheapest FRONTIER-tier reasoning model",
    "pro-vision": "cheapest FRONTIER-tier vision model",
    "pro-chat": "cheapest FRONTIER-tier chat model",
    "pro-fast": "cheapest FRONTIER-tier fast model",
    "coding": "alias of best-coding",
    "fast": "alias of best-fast",
    "chat": "alias of best-chat",
    "free": "treasury-sponsored free inference with live fallback and daily limits",
    "free-coding": "treasury-sponsored free coding models with live fallback",
    "free-fast": "treasury-sponsored free fast/small models with live fallback",
    "srup-free": "legacy alias of surp/free (treasury-sponsored)",
}


def _name_matches(name: str, tokens: tuple[str, ...]) -> bool:
    n = name.lower()
    return any(tok in n for tok in tokens)


def is_text_llm(m: dict) -> bool:
    """A text/chat LLM — has per-token pricing and no media-unit pricing."""
    inp = m.get("best_input_per_1m") or 0
    out = m.get("best_output_per_1m") or 0
    media = m.get("best_media_unit_price")
    try:
        return (float(inp) > 0 or float(out) > 0) and not media
    except (TypeError, ValueError):
        return False


def price_of(m: dict) -> float:
    v = m.get("best_price_per_1m")
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def usd_per_1m(m: dict) -> float:
    return price_of(m) / PRICE_DIVISOR


def is_coding(m: dict) -> bool:
    return _name_matches(m["model"], CODING_TOKENS)


def is_vision(m: dict) -> bool:
    return _name_matches(m["model"], VISION_TOKENS)


def is_reasoning(m: dict) -> bool:
    return _name_matches(m["model"], REASONING_TOKENS) and not is_vision(m)


def is_fast(m: dict) -> bool:
    return _name_matches(m["model"], FAST_TOKENS)


def is_pro(m: dict) -> bool:
    return _name_matches(m["model"], PRO_TOKENS)


def is_chat(m: dict) -> bool:
    return is_text_llm(m) and not (is_coding(m) or is_reasoning(m) or is_vision(m))


def class_of(m: dict) -> str:
    """Primary class label for display."""
    if is_coding(m):
        return "coding"
    if is_reasoning(m):
        return "reasoning"
    if is_vision(m):
        return "vision"
    if is_fast(m):
        return "fast"
    return "chat"


def _filter_class(markets: list[dict], cls: str) -> list[dict]:
    if cls == "coding":
        return [m for m in markets if is_coding(m)]
    if cls == "reasoning":
        return [m for m in markets if is_reasoning(m)]
    if cls == "vision":
        return [m for m in markets if is_vision(m)]
    if cls == "fast":
        return [m for m in markets if is_fast(m)]
    if cls == "chat":
        return [m for m in markets if is_chat(m)]
    return []


def is_sellable(m: dict) -> bool:
    """A model is routable only if someone can actually serve it.

    The market book lists models that may have zero available liquidity:
      - total_cap == 0  → no seller has funded capacity (Surplus caps liquidity)
      - healthy_seller_count == 0 → listed but no healthy seller attached

    Routing to such a model makes Surplus return `no_healthy_sellers` (HTTP 503).
    """
    try:
        cap = float(m.get("total_cap") or 0)
        healthy = int(m.get("healthy_seller_count") or 0)
        return healthy > 0 and cap > 0
    except (TypeError, ValueError):
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Pool computation — which models a combo considers, cheapest first.
# This is what powers the "what's in this combo" disclosure on the site.
# ──────────────────────────────────────────────────────────────────────────────

def pool_for(combo: str, markets: list[dict]) -> list[dict]:
    """Return the candidate models a combo compares, cheapest-first.

    Only sellable models (positive liquidity + healthy seller) are considered,
    so we never route to a model no seller can actually serve.
    """
    all_text = [m for m in markets if is_text_llm(m) and is_sellable(m)]

    # Direct model passthrough: surp/direct/<model-id> pins one specific model.
    # Useful for benchmarks, pinned deployments, and model-specific SLAs.
    if combo.startswith("direct/"):
        wanted = combo[7:]
        pool = [m for m in all_text if m["model"].lower() == wanted.lower()]
        return pool
    if combo in ("free", "srup-free"):
        zero = [m for m in all_text if price_of(m) == 0]
        pool = zero if zero else all_text
    elif combo.startswith("my/"):
        wanted = get_custom_models(combo[3:])
        if wanted is None:
            return []
        want = {w.lower() for w in wanted}
        pool = [m for m in all_text if m["model"].lower() in want]
    else:
        if combo in ("coding", "fast", "chat"):
            tier, cls = "best", combo
        elif combo.startswith("best-"):
            tier, cls = "best", combo[5:]
        elif combo.startswith("pro-"):
            tier, cls = "pro", combo[4:]
        else:
            return []
        if cls == "coding-fast":
            pool = [m for m in all_text if is_coding(m) and is_fast(m)]
            if not pool:
                pool = _filter_class(all_text, "coding")
        else:
            pool = _filter_class(all_text, cls)
        if tier == "pro":
            pool = [m for m in pool if is_pro(m)]

    return sorted(pool, key=price_of)


def _f1000_winner(pool: list[dict]) -> Optional[dict]:
    """Pick the pool member with the best (lowest) F1000 in the metrics store.

    Best-effort and never raising: on missing data, an empty DB, samples
    below the min_samples threshold, or a metrics pick that is not part of
    this pool, returns None and the caller keeps the default cheapest pick.
    """
    try:
        best = metrics_store.best_f1000(
            model_class=class_of(pool[0]), min_samples=50, window_s=86400
        )
    except Exception:
        return None
    if not best:
        return None
    want = str(best).lower()
    for m in pool:
        name = str(m.get("model", "")).lower()
        if name == want or name.startswith(want + "/"):
            return m
    return None


def resolve(
    combo: str, markets: list[dict], strategy: Optional[str] = None
) -> tuple[Optional[str], str, float, int]:
    """Resolve a combo to the cheapest concrete model.

    Returns (model_id, debug_line, price_per_1m_atomic, pool_size).
    On failure model_id is None and debug_line explains why.
    """
    pool = pool_for(combo, markets)
    if not pool:
        if combo.startswith("my/") and get_custom_models(combo[3:]) is None:
            return None, f"unknown custom combo: {combo}", 0.0, 0
        return None, f"no models match {combo}", 0.0, 0
    winner = pool[0]
    suffix = ""
    if strategy == "f1000":
        pick = _f1000_winner(pool)
        if pick is not None and pick is not pool[0]:
            winner = pick
            suffix = " (strategy=f1000: best F1000)"
    p = price_of(winner)
    return (
        winner["model"],
        f"{combo} -> {winner['model']} (${p / PRICE_DIVISOR:.4f}/1M, pool={len(pool)}){suffix}",
        p,
        len(pool),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Custom combos — SQLite persistence
#
# Keyed by a deterministic content hash of the sorted model set, so submitting
# the same set twice is idempotent and yields a shareable, stable slug.
# ──────────────────────────────────────────────────────────────────────────────

_SLUG_RE = re.compile(r"^[0-9a-f]{8}$")
MAX_CUSTOM_MODELS = 20
MIN_CUSTOM_MODELS = 2


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS custom_combos (
               slug       TEXT PRIMARY KEY,
               name       TEXT NOT NULL,
               models     TEXT NOT NULL,
               created_at INTEGER NOT NULL,
               hits       INTEGER NOT NULL DEFAULT 0
           )"""
    )
    return conn


def _slug_for(models: list[str]) -> str:
    canon = "\n".join(sorted(m.strip().lower() for m in models))
    return hashlib.sha256(canon.encode()).hexdigest()[:8]


def create_custom(name: str, models: list[str]) -> dict:
    """Persist a custom combo. Idempotent on the model set.

    Raises ValueError on bad input.
    """
    cleaned: list[str] = []
    seen = set()
    for m in models:
        m = str(m).strip()
        if not m or m.lower() in seen:
            continue
        seen.add(m.lower())
        cleaned.append(m)

    if len(cleaned) < MIN_CUSTOM_MODELS:
        raise ValueError(f"pick at least {MIN_CUSTOM_MODELS} models (got {len(cleaned)})")
    if len(cleaned) > MAX_CUSTOM_MODELS:
        raise ValueError(f"at most {MAX_CUSTOM_MODELS} models allowed (got {len(cleaned)})")

    name = (str(name or "").strip() or "untitled")[:60]
    slug = _slug_for(cleaned)

    conn = _db()
    try:
        row = conn.execute("SELECT slug, name, models, created_at FROM custom_combos WHERE slug=?", (slug,)).fetchone()
        if row:
            return {
                "slug": row[0], "name": row[1], "models": json.loads(row[2]),
                "created_at": row[3], "existing": True,
            }
        now = int(time.time())
        conn.execute(
            "INSERT INTO custom_combos (slug, name, models, created_at) VALUES (?,?,?,?)",
            (slug, name, json.dumps(cleaned), now),
        )
        conn.commit()
        return {"slug": slug, "name": name, "models": cleaned, "created_at": now, "existing": False}
    finally:
        conn.close()


def get_custom_models(slug: str) -> Optional[list[str]]:
    """Return the model list for a custom combo slug, or None if unknown."""
    slug = str(slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        return None
    conn = _db()
    try:
        row = conn.execute("SELECT models FROM custom_combos WHERE slug=?", (slug,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def get_custom(slug: str) -> Optional[dict]:
    slug = str(slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        return None
    conn = _db()
    try:
        row = conn.execute(
            "SELECT slug, name, models, created_at, hits FROM custom_combos WHERE slug=?", (slug,)
        ).fetchone()
        if not row:
            return None
        return {
            "slug": row[0], "name": row[1], "models": json.loads(row[2]),
            "created_at": row[3], "hits": row[4],
        }
    finally:
        conn.close()


def bump_hits(slug: str) -> None:
    slug = str(slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        return
    try:
        conn = _db()
        conn.execute("UPDATE custom_combos SET hits = hits + 1 WHERE slug=?", (slug,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def list_custom(limit: int = 50) -> list[dict]:
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT slug, name, models, created_at, hits FROM custom_combos "
            "ORDER BY hits DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"slug": r[0], "name": r[1], "models": json.loads(r[2]), "created_at": r[3], "hits": r[4]}
            for r in rows
        ]
    finally:
        conn.close()


def all_combo_names() -> list[str]:
    """Built-ins plus every saved custom combo, as routable model suffixes."""
    return BUILTIN_COMBOS + [f"my/{c['slug']}" for c in list_custom(500)]
