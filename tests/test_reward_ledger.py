"""Tests for the surp reward ledger / cache flywheel."""

import pytest

import reward_ledger as rl


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(rl, "DB_PATH", str(tmp_path / "rewards.db"))
    monkeypatch.setattr(rl, "_conn", None)
    yield


def test_mint_on_cache_write_credits_author_balance():
    srp = rl.mint("0xalice", "cache_write", "best-chat", "key1", 100,
                  rl.WRITE_REWARD_PER_TOKEN, "cache write")
    assert srp == 100
    bal = rl.balance("0xalice")
    assert bal["balance_srp"] == 100
    assert bal["lifetime_earned"] == 100


def test_mint_on_cache_hit_credits_both_author_and_reader():
    rl.mint("0xauthor", "cache_write", "best-chat", "key2", 100,
            rl.WRITE_REWARD_PER_TOKEN, "write")
    author_srp = rl.mint("0xauthor", "cache_hit_author", "best-chat", "key2", 50,
                          rl.HIT_AUTHOR_REWARD_PER_TOKEN, "hit author")
    reader_srp = rl.mint("0xreader", "cache_hit_reader", "best-chat", "key2", 50,
                         rl.HIT_READER_REWARD_PER_TOKEN, "hit reader")
    assert author_srp == 100
    assert reader_srp == 25
    assert rl.balance("0xauthor")["balance_srp"] == 200
    assert rl.balance("0xreader")["balance_srp"] == 25


def test_dedup_prevents_farming_same_cache_key_same_role():
    first = rl.mint("0xsibyl", "cache_write", "best-chat", "key3", 100,
                    rl.WRITE_REWARD_PER_TOKEN, "write")
    second = rl.mint("0xsibyl", "cache_write", "best-chat", "key3", 100,
                     rl.WRITE_REWARD_PER_TOKEN, "write again")
    assert first == 100
    assert second == 0
    assert rl.balance("0xsibyl")["balance_srp"] == 100


def test_funding_pool_increases_token_value():
    rl.mint("0xalice", "cache_write", "best-chat", "key4", 100,
            rl.WRITE_REWARD_PER_TOKEN, "write")
    rl.fund_pool(50_000)  # 5 cents = 50,000 microcents
    stats = rl.global_stats()
    assert stats["rebate_pool_usd"] == 0.05
    assert stats["srp_outstanding"] == 100
    # 50000 microcents / 100 SRP = 500 microcents/SRP = 0.05 cents/SRP
    assert stats["value_per_srp_cents"] == pytest.approx(0.05, rel=1e-3)


def test_burn_redeems_at_current_token_value():
    rl.mint("0xalice", "cache_write", "best-chat", "key5", 100,
            rl.WRITE_REWARD_PER_TOKEN, "write")
    rl.fund_pool(50_000)
    claim = rl.burn("0xalice", 50)
    assert claim["burned_srp"] == 50
    # 50 SRP × 500 microcents = 25,000 microcents = 2.5 cents
    assert claim["claim_usd_cents"] == pytest.approx(2.5, rel=1e-3)
    assert claim["remaining_balance"] == 50


def test_burn_more_than_balance_fails():
    rl.mint("0xalice", "cache_write", "best-chat", "key6", 10,
            rl.WRITE_REWARD_PER_TOKEN, "write")
    claim = rl.burn("0xalice", 1000)
    assert "error" in claim


def test_more_revenue_makes_existing_tokens_appreciate():
    rl.mint("0xalice", "cache_write", "best-chat", "key7", 100,
            rl.WRITE_REWARD_PER_TOKEN, "write")
    rl.fund_pool(50_000)
    before = rl.balance("0xalice")["pending_claim_usd"]
    rl.fund_pool(50_000)  # more revenue flows in
    after = rl.balance("0xalice")["pending_claim_usd"]
    assert after > before
