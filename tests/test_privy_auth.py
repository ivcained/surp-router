"""Tests for Privy JWT verification and user extraction."""

import io
import json
import os
from unittest.mock import MagicMock

import pytest

import user_accounts as ua


@pytest.fixture(autouse=True)
def privy_env(monkeypatch):
    """Configure test Privy credentials."""
    monkeypatch.setenv("PRIVY_APP_ID", "test-app-id")
    monkeypatch.setenv("PRIVY_APP_SECRET", "test-app-secret")


def test_verify_privy_token_rejects_empty_token():
    """Empty access tokens are rejected without a network call."""
    assert ua.verify_privy_token("") is None


def test_verify_privy_token_uses_jwks_and_verified_sub(monkeypatch):
    """A verified JWT sub is used to fetch the user; client identity is ignored."""
    signing_key = MagicMock()
    signing_key.key = object()
    jwks_client = MagicMock()
    jwks_client.get_signing_key_from_jwt.return_value = signing_key
    monkeypatch.setattr("jwt.PyJWKClient", MagicMock(return_value=jwks_client))

    decode = MagicMock(return_value={
        "sub": "did:privy:verified-user",
        "aud": "test-app-id",
        "iss": "privy.io",
        "exp": 2_000_000_000,
    })
    monkeypatch.setattr("jwt.decode", decode)

    user = {
        "id": "did:privy:verified-user",
        "linked_accounts": [
            {"type": "wallet", "address": "0x1111111111111111111111111111111111111111"},
            {"type": "email", "address": "user@example.com"},
        ],
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(user).encode()

    captured = {}

    def fake_urlopen(request, timeout=10):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = ua.verify_privy_token("header.payload.signature")

    assert result is not None
    assert result["id"] == "did:privy:verified-user"
    assert result["linkedAccounts"] == result["linked_accounts"]
    assert captured["url"].endswith("/v1/users/did%3Aprivy%3Averified-user")
    assert "privy-app-id" in {key.lower() for key in captured["headers"]}
    jwks_client.get_signing_key_from_jwt.assert_called_once_with("header.payload.signature")
    decode.assert_called_once()
    assert decode.call_args.kwargs["audience"] == "test-app-id"
    assert decode.call_args.kwargs["issuer"] == "privy.io"
    assert decode.call_args.kwargs["algorithms"] == ["ES256"]


def test_verify_privy_token_does_not_post_token_to_users(monkeypatch):
    """Regression: never POST {access_token} to the Privy users endpoint."""
    jwks_client = MagicMock()
    jwks_client.get_signing_key_from_jwt.side_effect = ValueError("invalid token")
    monkeypatch.setattr("jwt.PyJWKClient", MagicMock(return_value=jwks_client))

    urlopen = MagicMock()
    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    assert ua.verify_privy_token("invalid.jwt.token") is None
    urlopen.assert_not_called()


def test_get_user_id_extracts_snake_case_linked_accounts(monkeypatch, tmp_path):
    """Verified Privy users are persisted with their embedded wallet and email."""
    user = {
        "id": "did:privy:user-1",
        "linkedAccounts": [
            {"type": "wallet", "address": "0x2222222222222222222222222222222222222222"},
            {"type": "email", "address": "wallet@example.com"},
        ],
    }
    monkeypatch.setattr(ua, "verify_privy_token", lambda _: user)

    captured = {}
    monkeypatch.setattr(
        ua,
        "upsert_user",
        lambda user_id, wallet, email="": captured.update(
            user_id=user_id, wallet=wallet, email=email
        ),
    )

    result = ua.get_user_id_from_request("Bearer valid-token")

    assert result == "did:privy:user-1"
    assert captured == {
        "user_id": "did:privy:user-1",
        "wallet": "0x2222222222222222222222222222222222222222",
        "email": "wallet@example.com",
    }
