import asyncio
import json
from aiohttp.test_utils import make_mocked_request

import gateway


def test_acp_discovery_document_has_required_fields_and_cache_headers():
    response = asyncio.run(gateway.serve_acp_discovery(make_mocked_request("GET", "/.well-known/acp.json")))
    document = json.loads(response.text)

    assert response.status == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["Cache-Control"] == "public, max-age=3600"
    assert document["protocol"]["name"] == "acp"
    assert document["protocol"]["version"] == "2026-04-17"
    assert document["protocol"]["supported_versions"] == ["2026-04-17"]
    assert document["protocol"]["documentation_url"].startswith("https://")
    assert document["api_base_url"] == "https://surp.ivc.lol/acp"
    assert document["transports"] == ["rest"]
    assert document["capabilities"]["services"] == ["checkout"]
    assert document["capabilities"]["supported_currencies"] == ["USD"]
    assert document["capabilities"]["supported_locales"] == ["en-US"]
