"""Surp Studio — all-in-one AI creative workspace.

Backend for the Studio SPA: chat (via surp's own gateway free tier),
image generation (text-to-image / image-to-image), video generation
(image-to-video / text-to-video), and a private per-user gallery with
optional public sharing.

Provider abstraction:
  - FAL.ai when SURP_FAL_KEY is set (flux t2i/i2i, kling/minimax/veo i2v/t2v)
  - mock provider otherwise — returns deterministic SVG placeholders so the
    full pipeline (upload → generate → gallery → share) is testable without
    a key. The UI shows a clear banner when the real provider is unconfigured.

All creations are private to the owning user by default. Sharing is opt-in
and generates an unguessable token URL.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("surp.studio")

DB_PATH = os.environ.get("SURP_STUDIO_DB", str(Path(__file__).resolve().parent / "studio.db"))
MEDIA_DIR = os.environ.get("SURP_STUDIO_MEDIA", str(Path(__file__).resolve().parent / "studio_media"))
# Generation provider: Surplus Intelligence (the same key the resolver uses
# for inference). OpenAI-compatible /v1/images/generations + /v1/videos/
# endpoints expose 112+ image/video models (Flux, Wan 2.7, Kling, Veo3,
# Seedance, Runway, Pixverse, ...).
SURPLUS_BASE = os.environ.get("SURPLUS_BASE", "https://api.surplusintelligence.ai")
SURPLUS_KEY = os.environ.get("SURPLUS_INTELLIGENCE_API_KEY", "")
FAL_KEY = os.environ.get("SURP_FAL_KEY", "")  # optional fallback provider
FAL_API = "https://fal.run"

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _db()
        _conn.executescript("""
        CREATE TABLE IF NOT EXISTS creations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,            -- 'image' | 'video'
            mode TEXT NOT NULL,            -- 't2i' | 'i2i' | 't2v' | 'i2v'
            prompt TEXT NOT NULL DEFAULT '',
            params_json TEXT NOT NULL DEFAULT '{}',
            media_url TEXT NOT NULL DEFAULT '',
            thumb_url TEXT NOT NULL DEFAULT '',
            is_public INTEGER NOT NULL DEFAULT 0,
            share_token TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_creations_user ON creations(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_creations_token ON creations(share_token);
        """)
        _conn.commit()
    return _conn


# ── media storage (private by default) ─────────────────────────────────────

def _save_media(data: bytes, ext: str) -> str:
    """Persist a media blob under MEDIA_DIR and return its public URL path."""
    Path(MEDIA_DIR).mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(8)}{ext}"
    (Path(MEDIA_DIR) / name).write_bytes(data)
    return f"/studio/media/{name}"


def _load_media(name: str) -> Optional[bytes]:
    """Read a media blob by filename (path-traversal safe)."""
    safe = Path(name).name
    if safe != name:
        return None
    p = Path(MEDIA_DIR) / safe
    if not p.is_file():
        return None
    return p.read_bytes()


# ── providers ────────────────────────────────────────────────────────────────

def provider_status() -> dict[str, Any]:
    return {
        "configured": bool(SURPLUS_KEY),
        "provider": "surplus" if SURPLUS_KEY else ("fal" if FAL_KEY else "mock"),
    }


async def _surplus_generate_image(prompt: str, mode: str, image_url: str = "",
                                  params: Optional[dict] = None) -> str:
    """Generate an image via Surplus OpenAI-compatible images endpoint.

    Returns a data URL (b64) or a URL to the generated image.
    """
    import aiohttp
    params = params or {}
    body: dict[str, Any] = {
        "model": params.get("image_model", "venice-flux-1.1-pro"),
        "prompt": prompt,
        "size": params.get("size", "1024x1024"),
    }
    if mode == "i2i" and image_url:
        # OpenAI images/edit accepts an image; Surplus supports image input.
        body["image"] = image_url
        body["strength"] = float(params.get("strength", 0.6))
    headers = {
        "Authorization": f"Bearer {SURPLUS_KEY}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{SURPLUS_BASE}/v1/images/generations", json=body,
                          headers=headers, timeout=aiohttp.ClientTimeout(total=180)) as r:
            res = await r.json()
            if r.status != 200:
                raise RuntimeError(f"surplus images: HTTP {r.status}: {res}")
    data = res.get("data") or []
    if not data:
        raise RuntimeError("surplus images: empty data")
    item = data[0]
    if item.get("b64_json"):
        return f"data:image/png;base64,{item['b64_json']}"
    if item.get("url"):
        return item["url"]
    raise RuntimeError("surplus images: no b64_json or url in response")


async def _surplus_generate_video(prompt: str, mode: str, image_url: str = "",
                                  params: Optional[dict] = None) -> str:
    """Generate a video via Surplus. Returns a URL to the video."""
    import aiohttp
    params = params or {}
    # Video models come in text-to-video and image-to-video variants.
    model = params.get("video_model", "venice-wan-2.7")
    if mode == "i2v":
        # Prefer an image-to-video model when the user supplied an image.
        i2v_models = [
            "wan-2-1-pro-image-to-video",
            "wan-2-6-flash-image-to-video",
            "veo3-1-full-image-to-video",
            "kling-2-6-pro-image-to-video",
            "ovi-image-to-video",
        ]
        if model in i2v_models or "image-to-video" in model:
            pass
        else:
            model = i2v_models[0]
    body: dict[str, Any] = {"model": model, "prompt": prompt}
    if mode == "i2v" and image_url:
        body["image"] = image_url
    headers = {
        "Authorization": f"Bearer {SURPLUS_KEY}",
        "Content-Type": "application/json",
    }
    # Try the OpenAI-compatible videos endpoint first, then the chat fallback.
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{SURPLUS_BASE}/v1/videos/generations", json=body,
                          headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as r:
            res = await r.json()
            if r.status == 200:
                data = res.get("data") or []
                if data:
                    item = data[0]
                    url = item.get("url") or item.get("video_url") or ""
                    if url:
                        return url
    raise RuntimeError(f"surplus videos: no URL returned for {model}")


async def _fal_generate(model_id: str, input_: dict[str, Any]) -> dict[str, Any]:
    """Call a FAL.ai model endpoint and return its JSON result."""
    import aiohttp
    url = f"{FAL_API}/{model_id}"
    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=input_, headers=headers,
                          timeout=aiohttp.ClientTimeout(total=180)) as r:
            body = await r.json()
            if r.status != 200:
                raise RuntimeError(f"fal {model_id}: HTTP {r.status}: {body}")
            return body


def _mock_image(prompt: str, seed: int) -> bytes:
    """Deterministic SVG placeholder so the pipeline is testable without a key."""
    h = seed % 360
    safe = urllib.parse.quote(prompt[:60])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="768" height="768">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="hsl({h},70%,12%)"/>
      <stop offset="1" stop-color="hsl({(h+60)%360},70%,20%)"/>
    </linearGradient>
  </defs>
  <rect width="768" height="768" fill="url(#g)"/>
  <rect x="24" y="24" width="720" height="720" fill="none" stroke="#00ff9c" stroke-opacity="0.35" stroke-width="2" rx="12"/>
  <text x="384" y="360" text-anchor="middle" fill="#00ff9c" font-family="monospace" font-size="26" opacity="0.9">surp studio · mock</text>
  <text x="384" y="404" text-anchor="middle" fill="#5ce1ff" font-family="monospace" font-size="14" opacity="0.7">seed {seed}</text>
  <text x="384" y="436" text-anchor="middle" fill="#ffffff" font-family="monospace" font-size="12" opacity="0.6">{safe}</text>
</svg>"""
    return svg.encode("utf-8")


async def generate(kind: str, mode: str, prompt: str,
                   image_url: str = "", params: Optional[dict] = None) -> dict[str, Any]:
    """Generate an image or video. Returns {media_url, thumb_url, provider}."""
    params = params or {}
    seed = int(params.get("seed", 0)) or int(time.time() * 1000) % 2_000_000_000
    # Primary provider: Surplus Intelligence (user's existing key).
    if SURPLUS_KEY:
        try:
            if kind == "image":
                url = await _surplus_generate_image(prompt, mode, image_url, params)
                # b64 data URLs are persisted locally (private); remote URLs kept as-is.
                if url.startswith("data:image"):
                    _, b64 = url.split(",", 1)
                    try:
                        data = base64.b64decode(b64)
                        # Sniff real format: Surplus returns JPEG for flux.
                        ext = ".png" if data[:4] == b"\x89PNG" else ".jpg" if data[:3] == b"\xff\xd8\xff" else ".png"
                        media_url = _save_media(data, ext)
                    except Exception:
                        media_url = url
                else:
                    media_url = url
                return {"media_url": media_url, "thumb_url": media_url, "provider": "surplus"}
            else:
                url = await _surplus_generate_video(prompt, mode, image_url, params)
                return {"media_url": url, "thumb_url": url, "provider": "surplus"}
        except Exception as e:
            log.warning(f"surplus generation failed, falling back to mock: {e}")
            # fall through to mock so the UI never hard-fails

    # Optional FAL fallback.
    if FAL_KEY:
        try:
            if kind == "image":
                if mode == "i2i":
                    res = await _fal_generate("fal-ai/flux/dev/image-to-image", {
                        "prompt": prompt,
                        "image_url": image_url,
                        "strength": float(params.get("strength", 0.6)),
                        "num_inference_steps": int(params.get("steps", 28)),
                        "guidance_scale": float(params.get("guidance", 3.5)),
                        "seed": seed,
                    })
                else:
                    res = await _fal_generate("fal-ai/flux/dev", {
                        "prompt": prompt,
                        "num_inference_steps": int(params.get("steps", 28)),
                        "guidance_scale": float(params.get("guidance", 3.5)),
                        "seed": seed,
                        "image_size": params.get("aspect", "square_hd"),
                    })
                url = res.get("images", [{}])[0].get("url", "")
                return {"media_url": url, "thumb_url": url, "provider": "fal"}
            else:  # video
                model = params.get("video_model", "fal-ai/minimax/video-01-live")
                inp: dict[str, Any] = {"prompt": prompt}
                if mode == "i2v" and image_url:
                    inp["image_url"] = image_url
                res = await _fal_generate(model, inp)
                url = res.get("video", {}).get("url", "")
                return {"media_url": url, "thumb_url": url, "provider": "fal"}
        except Exception as e:
            log.warning(f"fal generation failed, falling back to mock: {e}")

    # mock provider
    svg = _mock_image(prompt, seed)
    url = _save_media(svg, ".svg")
    return {"media_url": url, "thumb_url": url, "provider": "mock"}


# ── creations CRUD ──────────────────────────────────────────────────────────

def create_creation(user_id: str, kind: str, mode: str, prompt: str,
                    media_url: str, thumb_url: str = "",
                    params: Optional[dict] = None) -> dict[str, Any]:
    now = int(time.time())
    with _lock:
        c = conn()
        cur = c.execute(
            "INSERT INTO creations(user_id,kind,mode,prompt,params_json,media_url,thumb_url,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (user_id, kind, mode, prompt, json.dumps(params or {}), media_url, thumb_url or media_url, now),
        )
        c.commit()
        return get_creation(cur.lastrowid, user_id)


def get_creation(cid: int, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    row = conn().execute("SELECT * FROM creations WHERE id=?", (cid,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["params"] = json.loads(d.pop("params_json") or "{}")
    d["is_public"] = bool(d["is_public"])
    return d


def list_creations(user_id: str, limit: int = 60) -> list[dict[str, Any]]:
    rows = conn().execute(
        "SELECT * FROM creations WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, min(max(1, limit), 200)),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["params"] = json.loads(d.pop("params_json") or "{}")
        d["is_public"] = bool(d["is_public"])
        out.append(d)
    return out


def set_public(cid: int, user_id: str, is_public: bool) -> Optional[dict[str, Any]]:
    with _lock:
        c = conn()
        rec = get_creation(cid, user_id)
        if rec is None or rec["user_id"] != user_id:
            return None
        token = rec["share_token"]
        if is_public and not token:
            token = secrets.token_urlsafe(16)
        c.execute("UPDATE creations SET is_public=?, share_token=? WHERE id=?",
                  (1 if is_public else 0, token, cid))
        c.commit()
        return get_creation(cid, user_id)


def get_public(token: str) -> Optional[dict[str, Any]]:
    row = conn().execute(
        "SELECT * FROM creations WHERE share_token=? AND is_public=1", (token,)
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["params"] = json.loads(d.pop("params_json") or "{}")
    return d


def delete_creation(cid: int, user_id: str) -> bool:
    with _lock:
        c = conn()
        rec = get_creation(cid, user_id)
        if rec is None or rec["user_id"] != user_id:
            return False
        c.execute("DELETE FROM creations WHERE id=?", (cid,))
        c.commit()
        return True
