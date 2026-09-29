"""Jev decision-model routing for Surp.

Jev (TypeSafe System One) picks a model from a Surp-supplied candidate list.
Bounded by design:

- Jev only sees request *metadata* (token estimate, modality flags, class) —
  never prompt content.
- Jev only picks from candidates we annotate and pass in.
- Every failure mode (missing SDK, missing key, timeout, low confidence,
  invalid choice, exception) falls open to the AA pick the caller already
  computed. Availability never depends on Jev.

Config (all optional, safe defaults keep everything off):

  JEV_SHADOW=1          log what Jev would have picked, serve the AA pick
  JEV_LIVE=1            honor Jev picks for the surp/jev preset
  JEV_TIMEOUT_MS=600    decision budget
  JEV_MIN_CONFIDENCE=0.55
  JEV_MAX_CANDIDATES=12
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("surp.jev")

LOG_PATH = Path(__file__).parent / "logs" / "jev-routing.jsonl"


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def shadow_enabled() -> bool:
    return _env_bool("JEV_SHADOW")


def live_enabled() -> bool:
    return _env_bool("JEV_LIVE")


@dataclass
class JevDecision:
    ok: bool
    choice: Optional[str] = None
    confidence: float = 0.0
    latency_ms: float = 0.0
    fallback_reason: Optional[str] = None
    probabilities: Optional[dict] = None


def build_state(
    payload: dict[str, Any],
    pool_size: int,
    model_class: str,
    cache_eligible: bool,
) -> dict[str, Any]:
    """Request metadata for Jev. MUST NOT include message content."""
    messages = payload.get("messages") or []
    has_images = False
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in ("image_url", "input_image", "image"):
                    has_images = True
                    break
    est_tokens = payload.get("max_tokens") or payload.get("max_completion_tokens") or 1500
    try:
        est_tokens = int(est_tokens)
    except (TypeError, ValueError):
        est_tokens = 1500
    return {
        "model_class": model_class,
        "est_tokens": est_tokens,
        "has_images": has_images,
        "has_tools": bool(payload.get("tools")),
        "cache_eligible": bool(cache_eligible),
        "pool_size": pool_size,
    }


def _criteria_for(candidates: list[Any], max_candidates: int) -> dict[str, str]:
    """One criterion per candidate model, with a short pricing/quality descriptor."""
    out: dict[str, str] = {}
    for c in candidates[:max_candidates]:
        parts = [c.model, f"${c.surplus_usd:.4f}/1M"]
        if c.intelligence is not None:
            parts.append(f"intel {c.intelligence:.1f}")
        if c.tps is not None:
            parts.append(f"~{c.tps:.0f} tps")
        if c.list_usd:
            parts.append(f"{c.discount * 100:.0f}% off list")
        out[c.model] = " | ".join(parts)
    return out


class JevRouter:
    def __init__(
        self,
        client_factory: Optional[Callable[[], Any]] = None,
        timeout_s: float = 0.6,
        min_confidence: float = 0.55,
        max_candidates: int = 12,
        enabled: bool = True,
    ):
        self._client_factory = client_factory
        self.timeout_s = timeout_s
        self.min_confidence = min_confidence
        self.max_candidates = max_candidates
        self.enabled = enabled
        self._client: Any = None

    @classmethod
    def from_env(cls) -> "JevRouter":
        key = (os.environ.get("TYPESAFE_API_KEY") or "").strip()
        if not key:
            return cls(enabled=False)
        try:
            from typesafe_sdk import AsyncTypeSafeClient  # noqa: F401
        except ImportError:
            log.warning("typesafe-sdk not installed; Jev routing disabled")
            return cls(enabled=False)

        def factory():
            from typesafe_sdk import AsyncTypeSafeClient
            return AsyncTypeSafeClient()

        return cls(
            client_factory=factory,
            timeout_s=_env_int("JEV_TIMEOUT_MS", 600) / 1000.0,
            min_confidence=_env_float("JEV_MIN_CONFIDENCE", 0.55),
            max_candidates=_env_int("JEV_MAX_CANDIDATES", 12),
            enabled=True,
        )

    async def decide(self, candidates: list[Any], state: dict[str, Any]) -> JevDecision:
        if not self.enabled or self._client_factory is None:
            return JevDecision(ok=False, fallback_reason="disabled")
        if not candidates:
            return JevDecision(ok=False, fallback_reason="no_candidates")

        t0 = time.monotonic()
        try:
            from typesafe_sdk import Choice
        except ImportError:
            Choice = None

        criteria = _criteria_for(candidates, self.max_candidates)
        try:
            if Choice is not None:
                questions = {
                    "route": Choice(
                        instructions=(
                            "Pick the best model for this request, balancing quality, "
                            "speed, and price for the request's class. Cheaper is better "
                            "when quality is comparable."
                        ),
                        criteria=criteria,
                    )
                }
                coro = self._call(questions, state)
            else:
                coro = self._call_raw(criteria, state)
            resp = await asyncio.wait_for(coro, timeout=self.timeout_s)
        except asyncio.TimeoutError:
            return JevDecision(ok=False, latency_ms=(time.monotonic() - t0) * 1000,
                               fallback_reason="timeout")
        except Exception as e:
            log.warning("jev decision failed: %s", e)
            return JevDecision(ok=False, latency_ms=(time.monotonic() - t0) * 1000,
                               fallback_reason="error")

        latency_ms = (time.monotonic() - t0) * 1000
        choice = resp.choices["route"].choice
        confidence = float(resp.choices["route"].confidence or 0.0)
        probs = getattr(resp.choices["route"], "probabilities", None)

        if choice not in criteria:
            return JevDecision(ok=False, choice=choice, confidence=confidence,
                               latency_ms=latency_ms, fallback_reason="invalid_choice",
                               probabilities=probs)
        if confidence < self.min_confidence:
            return JevDecision(ok=False, choice=choice, confidence=confidence,
                               latency_ms=latency_ms, fallback_reason="low_confidence",
                               probabilities=probs)
        return JevDecision(ok=True, choice=choice, confidence=confidence,
                           latency_ms=latency_ms, probabilities=probs)

    async def _call(self, questions: Any, state: dict[str, Any]) -> Any:
        # Hold one client across decisions: opening an HTTP/2 session per
        # request wastes most of the 600ms budget on handshake.
        if self._client is None:
            factory = self._client_factory
            assert factory is not None
            self._client = factory()
            await self._client.__aenter__()
        return await self._client.system_one(state=state, questions=questions)

    async def _call_raw(self, criteria: dict[str, str], state: dict[str, Any]) -> Any:
        """Fallback when the SDK's Choice symbol isn't importable in tests."""
        raise RuntimeError("typesafe-sdk unavailable")


def log_decision(
    mode: str,
    combo: str,
    aa_pick: str,
    decision: JevDecision,
    pool_size: int,
) -> None:
    """Append one decision record. Never raises; logging must not break serving."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": int(time.time()),
            "mode": mode,
            "combo": combo,
            "aa_pick": aa_pick,
            "jev_pick": decision.choice,
            "ok": decision.ok,
            "confidence": decision.confidence,
            "latency_ms": round(decision.latency_ms, 1),
            "fallback_reason": decision.fallback_reason,
            "agree": decision.ok and decision.choice == aa_pick,
            "pool_size": pool_size,
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    except Exception as e:
        log.warning("jev decision log failed: %s", e)


def read_stats() -> dict[str, Any]:
    """Aggregate the decision log for /api/jev/stats. Read-only, tolerant."""
    total = fallbacks = agree = 0
    latencies: list[float] = []
    try:
        if LOG_PATH.exists():
            with open(LOG_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    total += 1
                    if not r.get("ok"):
                        fallbacks += 1
                    if r.get("mode") == "shadow" and r.get("agree"):
                        agree += 1
                    if r.get("latency_ms"):
                        latencies.append(float(r["latency_ms"]))
    except Exception as e:
        log.warning("jev stats read failed: %s", e)
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else None
    return {
        "jev_decisions_total": total,
        "jev_fallbacks_total": fallbacks,
        "jev_fallback_rate": round(fallbacks / total, 4) if total else None,
        "jev_shadow_agreement_rate": round(agree / total, 4) if total else None,
        "jev_latency_ms_p50": p50,
        "jev_shadow_enabled": _env_bool("JEV_SHADOW"),
        "jev_live_enabled": _env_bool("JEV_LIVE"),
        "units": {"jev_latency_ms_p50": "milliseconds", "jev_fallback_rate": "ratio", "jev_shadow_agreement_rate": "ratio"},
    }
