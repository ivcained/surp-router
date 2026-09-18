import asyncio
import json
from aiohttp.test_utils import make_mocked_request

import gateway


def run(handler, path, accept="application/json"):
    req = make_mocked_request("GET", path, headers={"Accept": accept})
    return asyncio.run(handler(req))


def test_homepage_negotiation_varies_on_accept():
    response = run(gateway.page_home, "/", "text/markdown")
    assert response.status == 200
    assert response.content_type == "text/markdown"
    assert response.headers["Vary"] == "Accept"
    assert "# Surp" in response.text


def test_404_markdown_and_api_json():
    markdown = run(gateway.page_404, "/missing", "text/markdown")
    assert markdown.status == 404
    assert markdown.content_type == "text/markdown"
    assert "https://surp.ivc.lol/docs" in markdown.text
    assert markdown.headers["Vary"] == "Accept"

    api = run(gateway.page_404, "/api/missing", "application/json")
    body = json.loads(api.text)
    assert api.status == 404
    assert api.content_type == "application/problem+json"
    assert body["code"] == "not_found"
    assert body["message"]
    assert body["resolution"]


def test_openapi_has_operation_ids_and_typed_responses():
    response = run(gateway.serve_openapi, "/openapi.json")
    doc = json.loads(response.text)
    assert "Problem" in doc["components"]["schemas"]
    for path in doc["paths"].values():
        for operation in path.values():
            assert operation["operationId"]
            assert operation["description"]
            for spec in operation["responses"].values():
                assert "content" in spec


def test_llms_has_when_to_use_guidance():
    response = run(gateway.serve_llms_txt, "/llms.txt", "text/plain")
    assert "## When to use Surp" in response.text
    assert "/v1/chat/completions" in response.text
