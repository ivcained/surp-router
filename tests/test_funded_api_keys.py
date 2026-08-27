"""Tests for prepaid API-key accounting."""

import importlib.util


def setup_db(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("ua_funded_test", "user_accounts.py")
    ua = importlib.util.module_from_spec(spec)
    ua._DB_PATH = str(tmp_path / "users.db")
    spec.loader.exec_module(ua)
    ua._init_db()
    ua.upsert_user("u1", "0x" + "1" * 40)
    return ua


def test_paid_key_requires_payment_path(tmp_path, monkeypatch):
    ua = setup_db(tmp_path, monkeypatch)
    key = ua.create_api_key("u1", "paid", 2_500_000)
    assert key is not None
    assert ua.check_budget(key["key_id"], 2_500_001) is False


def test_budget_is_not_reusable_after_spend(tmp_path, monkeypatch):
    ua = setup_db(tmp_path, monkeypatch)
    key = ua.create_api_key("u1", "one", 1_000_000)
    assert ua.check_budget(key["key_id"], 600_000) is True
    assert ua.check_budget(key["key_id"], 400_001) is False


def test_zero_budget_denies_paid_usage(tmp_path, monkeypatch):
    ua = setup_db(tmp_path, monkeypatch)
    key = ua.create_api_key("u1", "zero", 0)
    assert ua.check_budget(key["key_id"], 1) is False
