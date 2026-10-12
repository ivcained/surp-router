"""Agent-readiness fixes: OpenAPI typing, MCP manifests, versioning policy page."""

import asyncio
import json
from aiohttp.test_utils import make_mocked_request

import gateway


def run(handler, path, accept="application/json"):
    req = make_mocked_request("GET", path, headers={"Accept": accept})
    return asyncio.run(handler(req))


def test_openapi_request_and_response_schemas_are_fully_typed():
    doc = json.loads(run(gateway.serve_openapi, "/openapi.json").text)
    schemas = doc["components"]["schemas"]
    chat = doc["paths"]["/chat/completions"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert "$ref" in chat and chat["$ref"] == "#/components/schemas/ChatRequest"
    messages = schemas["ChatRequest"]["properties"]["messages"]
    assert messages["items"]["$ref"] == "#/components/schemas/ChatMessage"
    msg = schemas["ChatMessage"]
    assert msg["required"] == ["role", "content"]
    assert msg["properties"]["role"]["enum"] == ["system", "user", "assistant", "tool"]
    assert msg["properties"]["content"]["type"] == "string"
    # response side: no bare {"type": "object"} items left in chat schemas
    assert schemas["ChatResponse"]["properties"]["choices"]["items"]["$ref"] == "#/components/schemas/ChatChoice"
    flat = json.dumps([schemas[k] for k in ("ChatRequest", "ChatResponse", "ChatChoice", "ChatMessage")])
    assert '"items": {"type": "object"}' not in flat


def test_openapi_documents_deprecation_and_sunset_policy():
    doc = json.loads(run(gateway.serve_openapi, "/openapi.json").text)
    policy = doc["x-deprecation-policy"] + doc.get("x-sunset-policy", "")
    assert "Sunset" in policy and "Deprecation" in policy
    assert "https://surp.ivc.lol/versioning" in policy


def test_mcp_manifest_points_at_streamable_http_mcp_endpoint():
    body = json.loads(run(gateway.serve_mcp_card, "/mcp.json").text)
    assert body["transport"] == "streamable-http"
    assert body["url"] == "https://surp.ivc.lol/mcp"
    assert body["protocolVersion"] == "2025-06-18"


def test_mcp_server_card_lists_supported_protocol_versions():
    card = json.loads(run(gateway.serve_mcp_server_card, "/.well-known/mcp/server-card.json").text)
    remote = card["remotes"][0]
    assert remote["url"] == "https://surp.ivc.lol/mcp"
    assert "2025-06-18" in remote["supportedProtocolVersions"]
    assert "2025-03-26" in remote["supportedProtocolVersions"]


def test_versioning_page_html_and_markdown():
    html = run(gateway.page_versioning, "/versioning", "text/html")
    assert html.status == 200
    assert "Sunset" in html.text and "Deprecation" in html.text
    assert "90 days" in html.text
    md = run(gateway.page_versioning, "/versioning", "text/markdown")
    assert md.status == 200
    assert md.content_type == "text/markdown"
    assert "## Deprecation & sunset process" in md.text


def test_llms_txt_links_mcp_endpoint_and_versioning_policy():
    text = run(gateway.serve_llms_txt, "/llms.txt", "text/plain").text
    assert "https://surp.ivc.lol/mcp" in text
    assert "https://surp.ivc.lol/versioning" in text


def test_sitemap_includes_versioning_and_mcp():
    body = run(gateway.serve_sitemap, "/sitemap.xml").text
    assert "/versioning" in body


def test_developers_page_names_scp_server_sandbox_and_versioning():
    html = run(gateway.page_developers, "/developers", "text/html").text
    assert "href='/mcp'" in html
    assert "href='/versioning'" in html
    assert "api/free-key" in html  # live, copy-pasteable sandbox step