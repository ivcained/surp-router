import asyncio
import json
from aiohttp.test_utils import make_mocked_request

import gateway


def test_mcp_server_card_has_sep2127_identity_and_cors():
    request = make_mocked_request("GET", "/.well-known/mcp/server-card.json")
    response = asyncio.run(gateway.serve_mcp_server_card(request))
    body = json.loads(response.text)

    assert response.status == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert body["name"]
    assert body["description"]
    assert body["version"] == "1.0.0"
    assert body["name"] == "lol.ivc.surp/router"
    assert body["remotes"][0]["type"] == "streamable-http"
    assert body["remotes"][0]["url"].startswith("https://")
