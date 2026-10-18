#!/usr/bin/env python3
"""MCP (Model Context Protocol) server for Surp — Streamable HTTP transport.

Implements the 2025-03-26 and 2025-06-18 protocol revisions over a single
/mcp endpoint:

  POST   /mcp  — JSON-RPC requests and notifications
  GET    /mcp  — 405 (server-initiated streams not supported)
  DELETE /mcp  — 405 (stateless server: no sessions to terminate)
  OPTIONS /mcp — CORS preflight

The server is stateless (no Mcp-Session-Id) and response-mode JSON: it
returns `application/json` for requests and `202 Accepted` for
notifications, both permitted by the Streamable HTTP transport spec for
servers without server-initiated streams.

Tools and resources are served from the gateway itself over the loopback
base URL so MCP traffic sees exactly what public HTTP traffic sees.

Wire format reference: https://spec.modelcontextprotocol.io (JSON-RPC 2.0,
methods: initialize, notifications/initialized, ping, tools/list,
tools/call, resources/list, resources/read).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import aiohttp
from aiohttp import web

log = logging.getLogger("surp.mcp")

SERVER_NAME = "surp-router"
SERVER_VERSION = "1.1.0"
SUPPORTED_PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26"]
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

PUBLIC_BASE = "https://surp.ivc.lol"
INTERNAL_BASE = os.environ.get("SURP_INTERNAL_BASE", "http://127.0.0.1:20130")

_JSONRPC_PARSE_ERROR = -32700
_JSONRPC_INVALID_REQUEST = -32600
_JSONRPC_METHOD_NOT_FOUND = -32601
_JSONRPC_INVALID_PARAMS = -32602
_RESOURCE_NOT_FOUND = -32002


# ── HTTP transport helpers (monkeypatched in tests) ──────────────────────

async def _http_get(url: str, headers: dict | None = None) -> tuple[int, str, str]:
    """GET a gateway URL; returns (status, body, content_type)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                return resp.status, await resp.text(), resp.headers.get("Content-Type", "")
    except Exception as e:  # noqa: BLE001 — transport errors surface as tool errors
        log.warning(f"MCP loopback GET {url} failed: {e}")
        return 0, f"upstream request failed: {e}", ""


async def _http_post(url: str, payload: dict, headers: dict | None = None) -> tuple[int, str, str]:
    """POST JSON to a gateway URL; returns (status, body, content_type)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                return resp.status, await resp.text(), resp.headers.get("Content-Type", "")
    except Exception as e:  # noqa: BLE001
        log.warning(f"MCP loopback POST {url} failed: {e}")
        return 0, f"upstream request failed: {e}", ""


# ── Tool and resource definitions ────────────────────────────────────────

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_models",
        "title": "List Surp models",
        "description": "List the Surp routes and models currently available at GET /v1/models, including live cheapest-model resolutions per surp/<combo> route.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "compare_prices",
        "title": "Compare Surp prices",
        "description": "Compare live Surp routing prices against other providers. Optional `query` filters results by model or route name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional model or route search text"},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "get_status",
        "title": "Get Surp status",
        "description": "Read current Surp gateway and upstream service health from GET /api/health.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "chat_completion",
        "title": "Chat completion",
        "description": "OpenAI-compatible chat completion against POST /v1/chat/completions with model 'surp/<route>' (e.g. 'surp/value' for cost-aware routing, 'surp/frontier' for quality, 'surp/jev' for decision-model routing). Requires the MCP client to send a prepaid Bearer key in the Authorization header, or returns the x402 USDC-on-Base payment requirements from the 402 challenge.",
        "inputSchema": {
            "type": "object",
            "required": ["model", "messages"],
            "properties": {
                "model": {"type": "string", "description": "Route to call, e.g. surp/value, surp/frontier, surp/jev"},
                "messages": {
                    "type": "array",
                    "description": "OpenAI-style messages",
                    "items": {
                        "type": "object",
                        "required": ["role", "content"],
                        "properties": {
                            "role": {"type": "string", "enum": ["system", "user", "assistant", "tool"]},
                            "content": {"type": "string"},
                        },
                    },
                },
                "max_tokens": {"type": "integer", "description": "Optional maximum output tokens"},
            },
            "additionalProperties": False,
        },
        "annotations": {"openWorldHint": False},
    },
]

_RESOURCES: list[dict[str, Any]] = [
    {
        "uri": "surp://docs/llms.txt",
        "name": "Surp llms.txt",
        "description": "Concise agent instructions for the Surp API: endpoints, auth, routes, and payments.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "surp://openapi.json",
        "name": "Surp OpenAPI 3.1 specification",
        "description": "Typed OpenAPI 3.1 contract for the public /v1 API.",
        "mimeType": "application/json",
    },
    {
        "uri": "surp://routes",
        "name": "Live Surp routes",
        "description": "Live model catalog: every surp/<combo> route with its resolved model and price.",
        "mimeType": "application/json",
    },
    {
        "uri": "surp://prices",
        "name": "Live Surp price comparison",
        "description": "Live Surp pricing compared against other providers.",
        "mimeType": "application/json",
    },
    {
        "uri": "surp://auth",
        "name": "Surp authentication guide",
        "description": "How agents authenticate: prepaid Bearer API keys and per-request x402 USDC payment signatures.",
        "mimeType": "text/markdown",
    },
]


# ── JSON-RPC method handlers ──────────────────────────────────────────────

async def _handle_initialize(params: dict, request: web.Request) -> dict:
    requested = str(params.get("protocolVersion", ""))
    protocol_version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
    return {
        "protocolVersion": protocol_version,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "logging": {},
        },
        "serverInfo": {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "title": "Surp Router",
        },
        "instructions": (
            "Surp routes OpenAI-compatible chat completions to the live cheapest model on the "
            "Surplus Intelligence marketplace. Call list_models first; use chat_completion with "
            "'surp/frontier' for production. Paid calls need a prepaid Bearer key in the "
            "Authorization header or an x402 USDC-on-Base payment."
        ),
    }


async def _handle_tools_list(_params: dict, _request: web.Request) -> dict:
    return {"tools": _TOOLS}


async def _handle_tools_call(params: dict, request: web.Request) -> dict:
    name = str(params.get("name", ""))
    arguments = params.get("arguments") or {}
    if name == "list_models":
        status, body, _ = await _http_get(f"{INTERNAL_BASE}/v1/models")
        return _tool_text_result(status, body, "list models")
    if name == "compare_prices":
        query = str(arguments.get("query", "") or "")
        url = f"{INTERNAL_BASE}/api/price-compare" + (f"?search={query}" if query else "")
        status, body, _ = await _http_get(url)
        return _tool_text_result(status, body, "compare prices")
    if name == "get_status":
        status, body, _ = await _http_get(f"{INTERNAL_BASE}/api/health")
        return _tool_text_result(status, body, "get status")
    if name == "chat_completion":
        payload = {k: arguments[k] for k in ("model", "messages", "max_tokens") if k in arguments}
        headers = {}
        auth = request.headers.get("Authorization")
        if auth:
            headers["Authorization"] = auth
        status, body, _ = await _http_post(f"{INTERNAL_BASE}/v1/chat/completions", payload, headers)
        if status == 0:
            return {"content": [{"type": "text", "text": body}], "isError": True}
        if status == 402:
            # Valid, well-formed outcome: tell the agent how to pay.
            return {
                "content": [{"type": "text", "text": f"Payment required (HTTP 402). Challenge details:\n{body}\n\nCreate a self-serve prepaid key at https://surp.ivc.lol/app or fulfill the x402 USDC-on-Base challenge. Retry with the Authorization header set."}],
                "isError": False,
            }
        return _tool_text_result(status, body, "chat completion")
    raise _JsonRpcError(_JSONRPC_INVALID_PARAMS, f"unknown tool: {name}")


async def _handle_resources_list(_params: dict, _request: web.Request) -> dict:
    return {"resources": _RESOURCES}


async def _handle_resources_read(params: dict, _request: web.Request) -> dict:
    uri = str(params.get("uri", ""))
    mapping = {
        "surp://docs/llms.txt": ("/llms.txt", "text/markdown"),
        "surp://openapi.json": ("/openapi.json", "application/json"),
        "surp://routes": ("/v1/models", "application/json"),
        "surp://prices": ("/api/price-compare", "application/json"),
        "surp://auth": ("/auth.md", "text/markdown"),
    }
    if uri not in mapping:
        raise _JsonRpcError(_RESOURCE_NOT_FOUND, f"resource not found: {uri}")
    path, mime = mapping[uri]
    status, body, _ = await _http_get(f"{INTERNAL_BASE}{path}")
    if status != 200 or not body.strip():
        raise _JsonRpcError(_RESOURCE_NOT_FOUND, f"resource unavailable (HTTP {status}): {uri}")
    return {"contents": [{"uri": uri, "mimeType": mime, "text": body}]}


_METHODS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
    "resources/list": _handle_resources_list,
    "resources/read": _handle_resources_read,
}


def _tool_text_result(status: int, body: str, what: str) -> dict:
    if status == 0:
        return {"content": [{"type": "text", "text": body}], "isError": True}
    if status != 200:
        return {"content": [{"type": "text", "text": f"Surp {what} request failed (HTTP {status}):\n{body}"}], "isError": True}
    return {"content": [{"type": "text", "text": body}], "isError": False}


class _JsonRpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ── aiohttp handlers ──────────────────────────────────────────────────────

_MCP_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Mcp-Session-Id, MCP-Protocol-Version, X-Inter-Session-Id, Last-Event-ID",
    "Access-Control-Expose-Headers": "MCP-Protocol-Version",
    "Access-Control-Max-Age": "86400",
}


async def handle_mcp_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_MCP_HEADERS)


async def handle_mcp_get(request: web.Request) -> web.Response:
    """Streamable HTTP GET: no server-initiated streams, so 405 per spec."""
    return web.Response(status=405, headers={**_MCP_HEADERS, "Allow": "POST, OPTIONS"})


async def handle_mcp_delete(request: web.Request) -> web.Response:
    """Stateless server (no Mcp-Session-Id issued): nothing to terminate."""
    return web.Response(status=405, headers={**_MCP_HEADERS, "Allow": "POST, OPTIONS"})


async def handle_mcp_post(request: web.Request) -> web.Response:
    """Single JSON-RPC message per POST (the common MCP client pattern)."""
    raw = await request.read()
    headers = {**_MCP_HEADERS, "MCP-Protocol-Version": LATEST_PROTOCOL_VERSION}
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return _jsonrpc_error(None, _JSONRPC_PARSE_ERROR, f"parse error: {e}", headers)
    if not isinstance(message, dict):
        return _jsonrpc_error(None, _JSONRPC_INVALID_REQUEST, "invalid request: expected a JSON-RPC object", headers)

    msg_id = message.get("id")
    method = message.get("method")
    if method is None:
        # A response envelope routed back to us — nothing to do.
        return web.Response(status=202, headers=headers)

    if msg_id is None:
        # Notification (e.g. notifications/initialized): 202 Accepted, no body.
        return web.Response(status=202, headers=headers)

    handler = _METHODS.get(method)
    if handler is None:
        if method == "ping":
            return _jsonrpc_result(msg_id, {}, headers)
        return _jsonrpc_error(msg_id, _JSONRPC_METHOD_NOT_FOUND, f"method not found: {method}", headers)
    try:
        result = await handler(message.get("params") or {}, request)
    except _JsonRpcError as e:
        return _jsonrpc_error(msg_id, e.code, e.message, headers)
    except Exception as e:  # noqa: BLE001 — never leak a stack trace to the client
        log.exception("MCP internal error")
        return _jsonrpc_error(msg_id, -32603, f"internal error: {e}", headers)
    return _jsonrpc_result(msg_id, result, headers)


def _jsonrpc_result(msg_id: Any, result: dict, headers: dict) -> web.Response:
    return web.json_response({"jsonrpc": "2.0", "id": msg_id, "result": result}, headers=headers)


def _jsonrpc_error(msg_id: Any, code: int, message: str, headers: dict) -> web.Response:
    return web.json_response({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}, headers=headers)


def register(app: web.Application, internal_base: str | None = None) -> None:
    """Attach the MCP routes to the gateway's aiohttp app."""
    global INTERNAL_BASE
    if internal_base:
        INTERNAL_BASE = internal_base.rstrip("/")
    app.router.add_options("/mcp", handle_mcp_options)
    app.router.add_get("/mcp", handle_mcp_get)
    app.router.add_delete("/mcp", handle_mcp_delete)
    app.router.add_post("/mcp", handle_mcp_post)
