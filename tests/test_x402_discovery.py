import asyncio
from aiohttp.test_utils import make_mocked_request

import gateway


def test_x402_discovery_probe_returns_402():
    response = asyncio.run(gateway.api_x402_discovery(make_mocked_request("GET", "/api/v1")))
    assert response.status == 402
    assert response.headers.get("PAYMENT-REQUIRED")
    assert "x402Version" in response.text
