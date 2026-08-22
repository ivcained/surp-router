"""AA-backed route picker.

Routes:
  value     — AA score within 20% of the best, then max Surplus % discount
  frontier  — highest AA Intelligence Index, discount breaks a tie
  fast      — same quality band, then highest AA median TPS
  vision    — vision pool (caller filters), then the value rule
  free      — highest AA score in the sponsored pool, then cheapest
  custom    — weighted mix of intelligence, speed, and discount

Cost in custom weights is Surplus discount vs AA list price, not AA index cost.
A request never fails because AA is missing: unmatched models fall back to
cheapest in the remaining set.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

import combo_resolver as cr
import aa_catalog

QUALITY_BAND = float(os.environ.get("AA_QUALITY_BAND", "0.20"))
LENS_COMBOS = ("value", "frontier", "speed", "vision", "custom", "free", "fast")
LEGACY_LENS_ALIASES = {"fast": "speed"}


@dataclass
class Pick:
    model: str
    reason: str
    intelligence: Optional[float]
    tps: Optional[float]
    surplus_usd: float
    list_usd: Optional[float]
    discount_pct: Optional[float]
    band_size: int
    pool_size: int


@dataclass
class Candidate:
    model: str
    surplus_usd: float
    intelligence: Optional[float]
    tps: Optional[float]
    list_usd: Optional[float]
    discount: float
    raw: dict[str, Any]


def discount_frac(surplus_usd: float, list_usd: Optional[float]) -> float:
    if list_usd is None or list_usd <= 0:
        return 0.0
    return max(0.0, (list_usd - surplus_usd) / list_usd)


def annotate(pool: list[dict[str, Any]], catalog: Optional[aa_catalog.Catalog] = None) -> list[Candidate]:
    cat = catalog if catalog is not None else aa_catalog.get_catalog()
    out: list[Candidate] = []
    for m in pool:
        name = str(m.get("model") or "")
        if not name:
            continue
        usd = cr.usd_per_1m(m)
        aa = aa_catalog.match_model(name, cat)
        intel = aa.intelligence if aa else None
        tps = aa.tps if aa else None
        list_usd = aa.list_usd if aa else None
        out.append(Candidate(
            model=name,
            surplus_usd=usd,
            intelligence=intel,
            tps=tps,
            list_usd=list_usd,
            discount=discount_frac(usd, list_usd),
            raw=m,
        ))
    return out


def _band(cands: list[Candidate], key: Callable[[Candidate], Optional[float]]) -> tuple[list[Candidate], str]:
    scores = [key(c) for c in cands if key(c) is not None]
    if not scores:
        return cands, "no-aa-fallback"
    best = max(scores)
    floor = best * (1.0 - QUALITY_BAND)
    band = [c for c in cands if (key(c) or 0.0) >= floor]
    return (band or cands), "aa-band"


def _cheapest(cands: list[Candidate]) -> Candidate:
    return min(cands, key=lambda c: (c.surplus_usd, c.model))


def _to_pick(c: Candidate, reason: str, band_size: int, pool_size: int) -> Pick:
    pct = round(c.discount * 100.0, 1) if c.list_usd else None
    return Pick(
        model=c.model,
        reason=reason,
        intelligence=c.intelligence,
        tps=c.tps,
        surplus_usd=c.surplus_usd,
        list_usd=c.list_usd,
        discount_pct=pct,
        band_size=band_size,
        pool_size=pool_size,
    )


def _custom_score(c: Candidate, intel_max: float, tps_max: float,
                  weights: tuple[float, float, float]) -> float:
    """weights = (cost/discount, intelligence, speed). Intelligence is doubled."""
    wc, wi, ws = weights
    wsum = wc + (2.0 * wi) + ws
    if wsum <= 0:
        return 0.0
    d = c.discount * 100.0
    i = 0.0 if c.intelligence is None or intel_max <= 0 else 100.0 * c.intelligence / intel_max
    s = 0.0 if c.tps is None or tps_max <= 0 else 100.0 * c.tps / tps_max
    return (d * wc + i * (2.0 * wi) + s * ws) / wsum


def pick(mode: str, pool: list[dict[str, Any]],
         catalog: Optional[aa_catalog.Catalog] = None,
         weights: Optional[tuple[float, float, float]] = None) -> Optional[Pick]:
    """Pick a Surplus model for an AA lens. pool is already class-filtered."""
    mode = LEGACY_LENS_ALIASES.get(mode.lower().strip(), mode.lower().strip())
    if mode == "speed":
        mode = "fast"
    if not pool:
        return None
    cands = annotate(pool, catalog)
    if not cands:
        return None
    n = len(cands)
    mode = (mode or "value").lower()

    if mode == "frontier":
        scored = [c for c in cands if c.intelligence is not None]
        if not scored:
            w = _cheapest(cands)
            return _to_pick(w, "frontier-cost-fallback", n, n)
        best_i = max(c.intelligence or 0 for c in scored)
        top = [c for c in scored if (c.intelligence or 0) == best_i]
        top.sort(key=lambda c: (-c.discount, c.surplus_usd, c.model))
        return _to_pick(top[0], "frontier", len(top), n)

    if mode == "free":
        scored = [c for c in cands if c.intelligence is not None]
        if not scored:
            w = _cheapest(cands)
            return _to_pick(w, "free-cost-fallback", n, n)
        scored.sort(key=lambda c: (-(c.intelligence or 0), c.surplus_usd, c.model))
        return _to_pick(scored[0], "free", n, n)

    if mode == "custom" or weights is not None:
        wts = weights or (0.45, 0.40, 0.15)
        intel_max = max((c.intelligence or 0) for c in cands) or 1.0
        tps_max = max((c.tps or 0) for c in cands) or 1.0
        ranked = sorted(
            cands,
            key=lambda c: (-_custom_score(c, intel_max, tps_max, wts), c.surplus_usd, c.model),
        )
        return _to_pick(ranked[0], "custom", n, n)

    band, tag = _band(cands, lambda c: c.intelligence)
    if mode == "fast":
        with_tps = [c for c in band if c.tps is not None]
        if not with_tps:
            w = _cheapest(band)
            return _to_pick(w, f"fast-{tag}-cost-fallback", len(band), n)
        with_tps.sort(key=lambda c: (-(c.tps or 0), -c.discount, c.surplus_usd, c.model))
        return _to_pick(with_tps[0], f"fast-{tag}", len(band), n)

    band.sort(key=lambda c: (-c.discount, c.surplus_usd, c.model))
    reason = "vision" if mode == "vision" else "value"
    if tag == "no-aa-fallback":
        reason = f"{reason}-cost-fallback"
    else:
        reason = f"{reason}-{tag}"
    return _to_pick(band[0], reason, len(band), n)


def preview_dict(p: Optional[Pick], combo: str) -> dict[str, Any]:
    if p is None:
        return {"combo": f"surp/{combo}", "model": None, "reason": "empty-pool"}
    return {
        "combo": f"surp/{combo}",
        "model": p.model,
        "reason": p.reason,
        "intelligence": p.intelligence,
        "tps": p.tps,
        "surplus_usd_per_1m": round(p.surplus_usd, 4),
        "list_usd_per_1m": None if p.list_usd is None else round(p.list_usd, 4),
        "discount_pct": p.discount_pct,
        "band_size": p.band_size,
        "pool_size": p.pool_size,
        "attribution": "https://artificialanalysis.ai/",
    }
