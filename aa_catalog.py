"""Artificial Analysis catalog sync for Surp routing.

Pulls the free language-model feed occasionally (default 6 hours), stores a
local snapshot, and matches Surplus model ids to AA intelligence / speed /
list price. A user request never waits on the network: stale snapshot wins.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
SNAPSHOT_PATH = Path(os.environ.get(
    "AA_SNAPSHOT_PATH", str(ROOT / "data" / "aa_models.json")
))
AA_FREE_URL = os.environ.get(
    "AA_FREE_URL", "https://artificialanalysis.ai/api/v2/language/models/free"
)
TTL_SECONDS = int(os.environ.get("AA_SYNC_SECONDS", "21600"))
MAX_PAGES = int(os.environ.get("AA_MAX_PAGES", "10"))
REQUEST_TIMEOUT = float(os.environ.get("AA_HTTP_TIMEOUT", "25"))

_lock = threading.RLock()
_cache: Optional["Catalog"] = None
_refreshing = False


def _load_env_file() -> None:
    """Load .env keys that are not already in the process environment."""
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


_load_env_file()


def _norm(s: str) -> str:
    """Collapse a model name/slug to a comparable token string."""
    s = (s or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = s.replace(".", "-")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


def blended_list_usd(price_in: Optional[float], price_out: Optional[float]) -> Optional[float]:
    """3:1 input:output blend, matching common AA display practice."""
    inn = float(price_in or 0)
    out = float(price_out or 0)
    if inn <= 0 and out <= 0:
        return None
    if inn <= 0:
        return out
    if out <= 0:
        return inn
    return (3.0 * inn + out) / 4.0


@dataclass
class AAModel:
    slug: str
    name: str
    intelligence: Optional[float]
    coding: Optional[float]
    agentic: Optional[float]
    tps: Optional[float]
    price_in: Optional[float]
    price_out: Optional[float]
    list_usd: Optional[float]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Catalog:
    fetched_at: float
    intelligence_index_version: Optional[float]
    models: list[AAModel]
    source: str = "snapshot"

    def by_slug(self) -> dict[str, AAModel]:
        return {_norm(m.slug): m for m in self.models if m.slug}


def _parse_row(row: dict[str, Any]) -> AAModel:
    ev = row.get("evaluations") or {}
    pricing = row.get("pricing") or {}
    perf = row.get("performance") or {}
    pin = pricing.get("price_1m_input_tokens")
    pout = pricing.get("price_1m_output_tokens")
    tps = perf.get("median_output_tokens_per_second")
    intel = ev.get("artificial_analysis_intelligence_index")
    coding = ev.get("artificial_analysis_coding_index")
    agentic = ev.get("artificial_analysis_agentic_index")
    return AAModel(
        slug=str(row.get("slug") or ""),
        name=str(row.get("name") or ""),
        intelligence=float(intel) if intel is not None else None,
        coding=float(coding) if coding is not None else None,
        agentic=float(agentic) if agentic is not None else None,
        tps=float(tps) if tps is not None else None,
        price_in=float(pin) if pin is not None else None,
        price_out=float(pout) if pout is not None else None,
        list_usd=blended_list_usd(pin, pout),
    )


def catalog_from_payload(payload: dict[str, Any], fetched_at: float, source: str) -> Catalog:
    rows = payload.get("models") or payload.get("data") or []
    models = []
    for row in rows:
        if not isinstance(row, dict) or not (row.get("slug") or row.get("name")):
            continue
        if "intelligence" in row and "evaluations" not in row:
            models.append(AAModel(
                slug=str(row.get("slug") or ""),
                name=str(row.get("name") or ""),
                intelligence=row.get("intelligence"),
                coding=row.get("coding"),
                agentic=row.get("agentic"),
                tps=row.get("tps"),
                price_in=row.get("price_in"),
                price_out=row.get("price_out"),
                list_usd=row.get("list_usd") if row.get("list_usd") is not None
                else blended_list_usd(row.get("price_in"), row.get("price_out")),
            ))
        else:
            models.append(_parse_row(row))
    version = payload.get("intelligence_index_version")
    return Catalog(
        fetched_at=float(payload.get("fetched_at") or fetched_at),
        intelligence_index_version=float(version) if version is not None else None,
        models=models,
        source=source,
    )


def load_snapshot(path: Optional[Path] = None) -> Catalog:
    p = path or SNAPSHOT_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return Catalog(fetched_at=0.0, intelligence_index_version=None, models=[], source="empty")
    return catalog_from_payload(raw, fetched_at=0.0, source="snapshot")


def save_snapshot(cat: Catalog, path: Optional[Path] = None) -> None:
    p = path or SNAPSHOT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": cat.fetched_at,
        "intelligence_index_version": cat.intelligence_index_version,
        "attribution": "https://artificialanalysis.ai/",
        "models": [m.as_dict() for m in cat.models],
    }
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(p)


def match_model(surplus_id: str, catalog: Catalog) -> Optional[AAModel]:
    """Best-effort Surplus id to AA row."""
    if not surplus_id or not catalog.models:
        return None
    tail = surplus_id.split("/")[-1]
    want = _norm(tail)
    full = _norm(surplus_id)
    by = catalog.by_slug()
    if want in by:
        return by[want]
    if full in by:
        return by[full]
    name_map = {_norm(m.name): m for m in catalog.models}
    if want in name_map:
        return name_map[want]
    best: Optional[AAModel] = None
    best_len = 0
    for m in catalog.models:
        ns = _norm(m.slug)
        if not ns:
            continue
        if ns == want or ns in want or want in ns or ns in full:
            if len(ns) > best_len:
                best = m
                best_len = len(ns)
    return best


def _http_get(url: str, api_key: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "x-api-key": api_key,
            "User-Agent": "surp-router/aa-sync",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_remote(api_key: Optional[str] = None) -> Catalog:
    key = api_key or os.environ.get("AA_API_KEY", "")
    if not key:
        raise RuntimeError("AA_API_KEY is not set")
    rows: list[dict[str, Any]] = []
    page = 1
    version = None
    while page <= MAX_PAGES:
        url = f"{AA_FREE_URL}?page={page}"
        payload = _http_get(url, key)
        version = payload.get("intelligence_index_version", version)
        chunk = payload.get("data") or []
        rows.extend(chunk)
        pag = payload.get("pagination") or {}
        if not pag.get("has_more"):
            break
        page += 1
    return Catalog(
        fetched_at=time.time(),
        intelligence_index_version=float(version) if version is not None else None,
        models=[_parse_row(r) for r in rows if isinstance(r, dict)],
        source="live",
    )


def get_catalog(force_refresh: bool = False) -> Catalog:
    """Return the in-memory catalog. Refresh in a thread if stale."""
    global _cache, _refreshing
    with _lock:
        if _cache is None:
            _cache = load_snapshot()
        cat = _cache
        stale = (time.time() - cat.fetched_at) > TTL_SECONDS or force_refresh
        if stale and not _refreshing and os.environ.get("AA_API_KEY"):
            _refreshing = True
            t = threading.Thread(target=_refresh_worker, daemon=True)
            t.start()
        return cat


def _refresh_worker() -> None:
    global _cache, _refreshing
    try:
        cat = fetch_remote()
        save_snapshot(cat)
        with _lock:
            _cache = cat
    except Exception:
        pass
    finally:
        with _lock:
            _refreshing = False


def refresh_now() -> Catalog:
    """Blocking refresh. Falls back to snapshot on failure."""
    global _cache
    try:
        cat = fetch_remote()
        save_snapshot(cat)
        with _lock:
            _cache = cat
        return cat
    except Exception:
        cat = load_snapshot()
        with _lock:
            if _cache is None:
                _cache = cat
        return _cache or cat


if __name__ == "__main__":
    cat = refresh_now()
    print(f"models={len(cat.models)} source={cat.source} version={cat.intelligence_index_version}")
