"""Payment gate on POST /api/keys/create and prepaid charge attribution.

Regression for the 2026-11-06 free-rider hole: anonymous callers minted
arbitrary prepaid balances ("artex" Go client drew ~100 paid requests/min on
keys funded for free). Balance grants must now be loopback-only, and the
"api-key charge" log line must attribute the key so nightly leech scans can
tie charges to keys.
"""

import asyncio
import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp.test_utils import make_mocked_request  # noqa: E402

import gateway  # noqa: E402


class FakePayload:
    def __init__(self, data: bytes):
        self._data = data
        self._served = False

    async def read(self, n: int = -1) -> bytes:
        if self._served:
            return b""
        self._served = True
        return self._data if n < 0 else self._data[:n]

    async def readany(self) -> bytes:
        if self._served:
            return b""
        self._served = True
        return self._data

    def at_eof(self) -> bool:
        return True

    def set_read_chunk_size(self, n: int) -> None:
        pass


def _peer_transport(peer):
    t = mock.Mock()
    t.get_extra_info = lambda name: peer if name == "peername" else None
    return t


def _post(body: dict, peer):
    return make_mocked_request(
        "POST", "/api/keys/create",
        headers={"Content-Type": "application/json"},
        payload=FakePayload(json.dumps(body).encode()),
        transport=_peer_transport(peer),
    )


def _create(rec):
    async def run():
        with mock.patch.object(gateway.st, "create_api_key", return_value=rec) as m:
            resp = await gateway.api_keys_create(_post(
                {"label": "t", "balance_cents": 5000}, ("203.0.113.9", 1111)))
            return resp, m
    return asyncio.run(run())


def test_remote_balance_request_is_rejected_402_and_mints_nothing():
    resp, minted = _create({"key": "sk-surp-x", "key_hash": "h", "label": "t",
                            "balance_microcents": 0})
    assert resp.status == 402
    assert "cannot be granted remotely" in resp.text
    minted.assert_not_called()


def test_loopback_balance_request_still_mints_funded_key_for_ops():
    req = _post({"label": "ops probe", "balance_cents": 20}, ("127.0.0.1", 0))
    rec = {"key": "sk-surp-x", "key_hash": "h", "label": "ops probe",
           "balance_microcents": 200000}
    async def run():
        with mock.patch.object(gateway.st, "create_api_key", return_value=rec) as m:
            resp = await gateway.api_keys_create(req)
            return resp, m
    resp, m = asyncio.run(run())
    assert resp.status == 200
    m.assert_called_once_with("ops probe", 200000)  # 20 cents -> 200k microcents


def test_ipv6_loopback_is_loopback():
    assert gateway._is_loopback_remote("::1") is True
    assert gateway._is_loopback_remote("127.0.0.1") is True
    assert gateway._is_loopback_remote("10.0.0.5") is False
    assert gateway._is_loopback_remote(None) is False
    assert gateway._is_loopback_remote("") is False


def test_remote_zero_balance_creation_still_works():
    req = _post({"label": "honest user", "balance_cents": 0}, ("198.51.100.7", 2222))
    rec = {"key": "sk-surp-x", "key_hash": "h", "label": "honest user",
           "balance_microcents": 0}
    async def run():
        with mock.patch.object(gateway.st, "create_api_key", return_value=rec) as m:
            resp = await gateway.api_keys_create(req)
            return resp, m
    resp, m = asyncio.run(run())
    assert resp.status == 200
    m.assert_called_once_with("honest user", 0)


def test_garbage_and_negative_balance_values_fail_closed():
    for bad in ("abc", [1], {"x": 1}):
        req = _post({"label": "t", "balance_cents": bad}, ("203.0.113.9", 1))
        resp = asyncio.run(gateway.api_keys_create(req))
        assert resp.status == 400, f"balance_cents={bad!r} should 400"
    req = _post({"label": "t", "balance_cents": -5}, ("203.0.113.9", 1))
    resp = asyncio.run(gateway.api_keys_create(req))
    assert resp.status == 400


def test_charge_log_line_attributes_key_and_label():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "gateway.py")).read()
    line = 'log.info(f"api-key charge: {required_microcents} mc key:'
    assert line in src, "charge log must carry key: attribution"
    assert "label:{str(key_rec.get('label')" in src, "charge log must carry the key label"
