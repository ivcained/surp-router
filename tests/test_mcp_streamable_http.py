"""MCP Streamable HTTP server tests — transport contract, handshake, tools, resources."""

import asyncio
import json
import sys
import types

sys.path.insert(0, ".")

import mcp_server  # noqa: E402
from aiohttp.test_utils import make_mocked_request  # noqa: E402


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


def post(body, auth=None):
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if auth:
        headers["Authorization"] = auth
    return make_mocked_request("POST", "/mcp", headers=headers,
                               payload=FakePayload(json.dumps(body).encode()))


def result_of(response):
    assert response.status == 200, response.text
    assert response.content_type == "application/json"
    doc = json.loads(response.text)
    assert doc["jsonrpc"] == "2.0"
    return doc["result"]


def error_of(response):
    doc = json.loads(response.text)
    return doc["error"]


def test_initialize_handshake_returns_capabilities_and_echoes_protocol():
    response = asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t"}},
    })))
    result = result_of(response)
    assert result["protocolVersion"] == "2025-03-26"
    assert "tools" in result["capabilities"]
    assert "resources" in result["capabilities"]
    assert result["serverInfo"]["name"] == "surp-router"
    assert response.headers["MCP-Protocol-Version"] == "2025-06-18"


def test_initialize_unknown_version_falls_back_to_latest():
    result = result_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 2, "method": "initialize",
        "params": {"protocolVersion": "1999-01-01"},
    }))))
    assert result["protocolVersion"] == mcp_server.LATEST_PROTOCOL_VERSION


def test_initialized_notification_returns_202_without_body():
    response = asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "method": "notifications/initialized",
    })))
    assert response.status == 202
    assert response.body in (None, b"")  # body renders empty on prepare()


def test_ping_returns_empty_result():
    result = result_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 3, "method": "ping",
    }))))
    assert result == {}


def test_parse_error_uses_32700():
    req = make_mocked_request("POST", "/mcp",
                              headers={"Content-Type": "application/json"},
                              payload=FakePayload(b"{not json"))
    response = asyncio.run(mcp_server.handle_mcp_post(req))
    assert response.status == 200
    assert error_of(response)["code"] == -32700


def test_unknown_method_uses_32601():
    response = asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 4, "method": "resources/subscribe",
    })))
    assert error_of(response)["code"] == -32601


def test_get_and_delete_are_405_per_streamable_http_spec():
    assert asyncio.run(mcp_server.handle_mcp_get(make_mocked_request("GET", "/mcp"))).status == 405
    assert asyncio.run(mcp_server.handle_mcp_delete(make_mocked_request("DELETE", "/mcp"))).status == 405


def test_tools_list_has_typed_schemas():
    result = result_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 5, "method": "tools/list",
    }))))
    tools = {t["name"]: t for t in result["tools"]}
    assert set(tools) == {"list_models", "compare_prices", "get_status", "chat_completion"}
    for tool in result["tools"]:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"
    chat = tools["chat_completion"]
    items = chat["inputSchema"]["properties"]["messages"]["items"]
    assert items["required"] == ["role", "content"]
    assert "Bearer" in chat["description"] or "Authorization" in chat["description"] or "402" in chat["description"]


def _fake_fetch(status_by_path):
    async def fake_get(url, headers=None):
        for path, (status, body) in status_by_path.items():
            if url.endswith(path):
                return status, body, "application/json"
        return 404, "{}", "application/json"
    return fake_get


def test_tools_call_list_models(monkeypatch):
    monkeypatch.setattr(mcp_server, "_http_get", _fake_fetch({"/v1/models": (200, '{"data":[]}')}))
    result = result_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 6, "method": "tools/call",
        "params": {"name": "list_models", "arguments": {}},
    }))))
    assert result["isError"] is False
    assert result["content"][0]["type"] == "text"
    assert "data" in result["content"][0]["text"]


def test_tools_call_unknown_tool_is_32602():
    err = error_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": "nope", "arguments": {}},
    }))))
    assert err["code"] == -32602


def test_resources_list_has_readable_resources():
    result = result_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 8, "method": "resources/list",
    }))))
    uris = {r["uri"] for r in result["resources"]}
    assert uris == {"surp://docs/llms.txt", "surp://openapi.json", "surp://routes", "surp://prices", "surp://auth"}
    for r in result["resources"]:
        assert r["mimeType"]
        assert r["name"]
        assert r["description"]


def test_resources_read_returns_content_with_mimetype(monkeypatch):
    monkeypatch.setattr(mcp_server, "_http_get", _fake_fetch({"/llms.txt": (200, "# Surp\nagent instructions")}))

    async def fake_read(params, request):
        return await mcp_server._handle_resources_read(params, request)
    result = result_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 9, "method": "resources/read",
        "params": {"uri": "surp://docs/llms.txt"},
    }))))
    content = result["contents"][0]
    assert content["uri"] == "surp://docs/llms.txt"
    assert content["mimeType"] == "text/markdown"
    assert "# Surp" in content["text"]


def test_resources_read_unknown_uri_is_32002():
    err = error_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 10, "method": "resources/read",
        "params": {"uri": "surp://nope"},
    }))))
    assert err["code"] == -32002


def test_resources_read_empty_body_is_32002(monkeypatch):
    monkeypatch.setattr(mcp_server, "_http_get", _fake_fetch({"/llms.txt": (200, "   ")}))
    err = error_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 11, "method": "resources/read",
        "params": {"uri": "surp://docs/llms.txt"},
    }))))
    assert err["code"] == -32002


def test_chat_tool_forwards_authorization_and_maps_402(monkeypatch):
    captured = {}

    async def fake_post(url, payload, headers=None):
        captured["url"], captured["payload"], captured["headers"] = url, payload, headers
        return 402, '{"error": "payment required"}', "application/json"

    monkeypatch.setattr(mcp_server, "_http_post", fake_post)
    result = result_of(asyncio.run(mcp_server.handle_mcp_post(post({
        "jsonrpc": "2.0", "id": 12, "method": "tools/call",
        "params": {"name": "chat_completion",
                   "arguments": {"model": "surp/value", "messages": [{"role": "user", "content": "hi"}]}},
    }, auth="Bearer sk-1"))))
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["payload"]["model"] == "surp/value"
    assert captured["headers"]["Authorization"] == "Bearer sk-1"
    assert result["isError"] is False  # 402 is a valid outcome, not a tool failure
    assert "402" in result["content"][0]["text"]
    assert "x402" in result["content"][0]["text"]


def test_register_adds_mcp_routes():
    app = types.SimpleNamespace(router=types.SimpleNamespace(
        add_options=lambda *a: None, add_get=lambda *a: None,
        add_delete=lambda *a: None, add_post=lambda *a: None,
        calls=[]))
    calls = []
    for name in ("add_options", "add_get", "add_delete", "add_post"):
        def mk(n):
            return lambda *a: calls.append((n, a[0]))
        setattr(app.router, name, mk(name))
    mcp_server.register(app, internal_base="http://127.0.0.1:9/")
    assert mcp_server.INTERNAL_BASE == "http://127.0.0.1:9"
    assert ("add_post", "/mcp") in calls
    assert ("add_get", "/mcp") in calls
    assert ("add_delete", "/mcp") in calls
    assert ("add_options", "/mcp") in calls