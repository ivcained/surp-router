"""Tests for NFT/token eligibility gate and community feedback."""

import time

import pytest

import nft_gate as ng
import community_feedback as cf


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ng, "DB_PATH", str(tmp_path / "gate.db"))
    monkeypatch.setattr(ng, "_conn", None)
    monkeypatch.setattr(ng, "_rpc_url", "http://localhost:8545")
    monkeypatch.setattr(ng, "CONTRACT", "0x" + "a" * 40)
    monkeypatch.setattr(ng, "ELIGIBILITY_THRESHOLD", 1)
    monkeypatch.setattr(cf, "DB_PATH", str(tmp_path / "gate.db"))
    monkeypatch.setattr(cf, "_conn", None)
    monkeypatch.setattr(cf, "_SALT", "test-salt")
    yield


def test_holder_passes_gate(monkeypatch):
    calls = []

    def fake_rpc(url, to, data):
        calls.append((url, to, data))
        return "0x0000000000000000000000000000000000000000000000000000000000000001"

    monkeypatch.setattr(ng, "_eth_call", fake_rpc)
    assert ng.is_eligible("0x" + "b" * 40) is True
    assert ng.is_eligible("0x" + "b" * 40) is True  # second call is cached
    assert len(calls) == 1  # RPC hit only once


def test_non_holder_fails_gate(monkeypatch):
    monkeypatch.setattr(ng, "_eth_call", lambda url, to, data: "0x" + "0" * 64)
    assert ng.is_eligible("0x" + "c" * 40) is False


def test_rpc_failure_is_fail_closed(monkeypatch):
    def boom(url, to, data):
        raise ConnectionError("RPC down")
    monkeypatch.setattr(ng, "_eth_call", boom)
    assert ng.is_eligible("0x" + "d" * 40) is False


def test_cache_expiry_refetches(monkeypatch):
    call_count = {"n": 0}

    def fake_rpc(url, to, data):
        call_count["n"] += 1
        return "0x" + "0" * 63 + "1"
    monkeypatch.setattr(ng, "_eth_call", fake_rpc)

    ng.is_eligible("0x" + "e" * 40)
    ng.is_eligible("0x" + "e" * 40)
    assert call_count["n"] == 1
    # Force expiry by rewinding the cached timestamp.
    ng._conn.execute("UPDATE nft_eligibility SET checked_at=? WHERE wallet=?",
                     (int(time.time()) - 9999, "0x" + "e" * 40))
    ng._conn.commit()
    ng.is_eligible("0x" + "e" * 40)
    assert call_count["n"] == 2


def test_feedback_submission_stores_salt_hashed_identity():
    r = cf.submit("0x" + "f" * 40, "idea", "gate by NFT floor price", ip="")
    assert r["ok"] is True
    raw_db = open(cf.DB_PATH, "rb").read()
    assert b"0x" + b"f" * 40 not in raw_db  # raw wallet never persisted


def test_feedback_rejects_empty_category_and_message():
    assert cf.submit("0xabc", "", "msg")["ok"] is False
    assert cf.submit("0xabc", "idea", "   ")["ok"] is False


def test_feedback_clamps_long_message():
    cf.submit("0xabc", "idea", "x" * 500)
    recent = cf.recent(10)
    assert len(recent[0]["message"]) <= 280


def test_feedback_categories_track_counts():
    cf.submit("a1", "idea", "x")
    cf.submit("a2", "concern", "y")
    cf.submit("a3", "idea", "z")
    cats = cf.summary()
    assert cats["idea"] == 2
    assert cats["concern"] == 1


def test_feedback_can_be_upvoted_once_per_identity():
    cf.submit("author", "idea", "proposal text")
    item = cf.recent(1)[0]
    cf.upvote(item["id"], "voter1")
    cf.upvote(item["id"], "voter1")  # deduped
    cf.upvote(item["id"], "voter2")
    after = cf.recent(1)[0]
    assert after["upvotes"] == 2
