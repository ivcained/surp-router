import asyncio
import json
from aiohttp.test_utils import make_mocked_request

import gateway


def test_ucp_profile_has_reachable_custom_content_capability():
    response = asyncio.run(gateway.serve_ucp_profile(make_mocked_request("GET", "/.well-known/ucp")))
    profile = json.loads(response.text)
    ucp = profile["ucp"]

    assert response.status == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert ucp["version"] == "2026-08-25"
    assert ucp["services"]
    assert ucp["capabilities"]
    assert ucp["payment_handlers"] == {}

    service = ucp["services"]["lol.ivc.surp.content"][0]
    assert service["transport"] == "rest"
    assert service["endpoint"] == "https://surp.ivc.lol/v1"
    assert service["schema"] == "https://surp.ivc.lol/openapi.json"

    capability = ucp["capabilities"]["lol.ivc.surp.content.inference"][0]
    assert capability["spec"].startswith("https://surp.ivc.lol/")
    assert capability["schema"].startswith("https://surp.ivc.lol/")


def test_ucp_capability_schema_and_spec_are_served():
    schema_response = asyncio.run(gateway.serve_ucp_inference_schema(make_mocked_request("GET", "/ucp/schemas/content-inference.json")))
    schema = json.loads(schema_response.text)
    assert schema_response.status == 200
    assert schema["name"] == "lol.ivc.surp.content.inference"
    assert schema["version"] == "2026-08-25"

    spec_response = asyncio.run(gateway.serve_ucp_inference_spec(make_mocked_request("GET", "/ucp/spec/content-inference")))
    assert spec_response.status == 200
    assert "Surp Content Inference" in spec_response.text
