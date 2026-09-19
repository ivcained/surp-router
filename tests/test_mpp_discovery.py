import asyncio
import json
from aiohttp.test_utils import make_mocked_request

import gateway


def test_openapi_advertises_mpp_payment_offer():
    response = asyncio.run(gateway.serve_openapi(make_mocked_request("GET", "/openapi.json")))
    doc = json.loads(response.text)
    service = doc["x-service-info"]
    operation = doc["paths"]["/chat/completions"]["post"]
    offers = operation["x-payment-info"]["offers"]

    assert service["categories"] == ["ai", "developer-tools", "payments"]
    assert service["docs"]["apiReference"] == "https://surp.ivc.lol/docs"
    assert operation["responses"]["402"]
    assert offers
    offer = offers[0]
    assert offer["intent"] == "charge"
    assert offer["method"] == "evm"
    assert offer["amount"] is None
    assert offer["currency"]
    assert offer["description"]


def test_openapi_discovery_response_is_publicly_cacheable():
    response = asyncio.run(gateway.serve_openapi(make_mocked_request("GET", "/openapi.json")))
    assert response.headers["Cache-Control"] == "public, max-age=300"
    assert response.headers["Access-Control-Allow-Origin"] == "*"
