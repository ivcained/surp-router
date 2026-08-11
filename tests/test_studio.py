"""Tests for the Surp Studio backend."""

import asyncio
import json

import pytest

import studio as st


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "DB_PATH", str(tmp_path / "studio.db"))
    monkeypatch.setattr(st, "MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(st, "SURPLUS_KEY", "")
    monkeypatch.setattr(st, "FAL_KEY", "")
    st._conn = None  # reset the cached connection
    st.conn()  # create schema
    yield


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_create_and_get_creation():
    c = st.create_creation("user-1", "image", "t2i", "a cat", "/studio/media/x.svg")
    assert c["user_id"] == "user-1"
    assert c["kind"] == "image"
    assert c["is_public"] is False
    got = st.get_creation(c["id"], "user-1")
    assert got["prompt"] == "a cat"


def test_creations_private_by_default():
    st.create_creation("user-1", "image", "t2i", "a", "/m/a")
    st.create_creation("user-1", "video", "t2v", "b", "/m/b")
    st.create_creation("user-2", "image", "t2i", "c", "/m/c")
    assert len(st.list_creations("user-1")) == 2
    assert len(st.list_creations("user-2")) == 1


def test_set_public_generates_token():
    c = st.create_creation("user-1", "image", "t2i", "a", "/m/a")
    pub = st.set_public(c["id"], "user-1", True)
    assert pub["is_public"] is True
    assert pub["share_token"]
    # fetchable by token
    got = st.get_public(pub["share_token"])
    assert got["id"] == c["id"]


def test_set_public_requires_owner():
    c = st.create_creation("user-1", "image", "t2i", "a", "/m/a")
    assert st.set_public(c["id"], "user-2", True) is None


def test_delete_requires_owner():
    c = st.create_creation("user-1", "image", "t2i", "a", "/m/a")
    assert st.delete_creation(c["id"], "user-2") is False
    assert st.delete_creation(c["id"], "user-1") is True
    assert st.get_creation(c["id"], "user-1") is None


def test_mock_generate_produces_media(tmp_path):
    res = _run(st.generate("image", "t2i", "hello world"))
    assert res["provider"] == "mock"
    assert res["media_url"].startswith("/studio/media/")
    # the blob is saved and loadable
    name = res["media_url"].rsplit("/", 1)[-1]
    data = st._load_media(name)
    assert data and b"surp studio" in data


def test_mock_generate_deterministic_seed(tmp_path):
    r1 = _run(st.generate("image", "t2i", "x", params={"seed": 42}))
    r2 = _run(st.generate("image", "t2i", "x", params={"seed": 42}))
    # URLs differ (random filenames) but the rendered content must match.
    n1 = r1["media_url"].rsplit("/", 1)[-1]
    n2 = r2["media_url"].rsplit("/", 1)[-1]
    assert st._load_media(n1) == st._load_media(n2)


def test_media_path_traversal_blocked():
    assert st._load_media("../../etc/passwd") is None


def test_provider_status():
    s = st.provider_status()
    assert s["provider"] == "mock"
    assert s["configured"] is False


def test_provider_status_surplus():
    st.SURPLUS_KEY = "test-key"
    s = st.provider_status()
    assert s["provider"] == "surplus"
    assert s["configured"] is True
    st.SURPLUS_KEY = ""


# ── pricing (x402 quote) ────────────────────────────────────────────────────

def test_quote_price_usd_applies_markup():
    markets = [{"model": "venice-flux-1.1-pro", "best_media_unit_price": 11700}]
    # 11700 atomic = $0.0117, +5% = $0.012285, ceil to $0.02 (floor $0.01... wait)
    # marked cents = 1.2285 → ceil = 2 cents → $0.02
    price = st.quote_price_usd("venice-flux-1.1-pro", markets)
    assert price == 0.02


def test_quote_price_usd_floor():
    markets = [{"model": "tiny", "best_media_unit_price": 100}]
    # $0.0001 * 1.05 = $0.000105 → 0.0105 cents → floored to 1 cent
    assert st.quote_price_usd("tiny", markets) == 0.01


def test_quote_price_usd_missing_model():
    assert st.quote_price_usd("nope", [{"model": "other", "best_media_unit_price": 100}]) is None


def test_quote_price_usd_no_markets():
    assert st.quote_price_usd("x", None) is None
