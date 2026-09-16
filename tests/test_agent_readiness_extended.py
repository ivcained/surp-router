import asyncio
import json
from aiohttp.test_utils import make_mocked_request

import gateway


def test_extended_agent_routes_exist():
    paths = {resource.canonical for resource in gateway.build_app().router.resources()}
    expected = {
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-protected-resource",
        "/.well-known/mcp/server-card.json",
        "/.well-known/agent-skills/index.json",
        "/.well-known/ai-catalog.json",
        "/.well-known/dns-aid.json",
    }
    assert expected <= paths


def test_api_catalog_has_linkset():
    response = asyncio.run(gateway.serve_api_catalog(make_mocked_request("GET", "/.well-known/api-catalog")))
    payload = json.loads(response.text)
    assert isinstance(payload["linkset"], list)
    assert payload["linkset"][0]["anchor"] == "https://surp.ivc.lol/v1"


def test_auth_md_has_heading():
    response = asyncio.run(gateway.serve_auth_md(make_mocked_request("GET", "/auth.md")))
    assert "# Auth.md" in response.text


def test_markdown_negotiation_converts_html():
    request = make_mocked_request("GET", "/", headers={"Accept": "text/markdown"})
    response = asyncio.run(gateway.page_home(request))
    assert response.content_type == "text/markdown"
    assert "<html" not in response.text.lower()
    assert "#" in response.text
