import asyncio
from aiohttp.test_utils import make_mocked_request

import gateway


def test_llms_full_is_expanded_markdown_context():
    response = asyncio.run(gateway.serve_llms_full(make_mocked_request("GET", "/llms-full.txt")))
    assert response.status == 200
    assert response.content_type == "text/plain"
    assert len(response.text) >= 3000
    for heading in [
        "# Surp — full agent context",
        "## When to use Surp",
        "## Authentication and payment",
        "## API reference",
        "## Error handling",
        "## Discovery documents",
    ]:
        assert heading in response.text
    assert "https://surp.ivc.lol/openapi.json" in response.text
    assert "POST /v1/chat/completions" in response.text


def test_llms_txt_links_full_context():
    response = asyncio.run(gateway.serve_llms_txt(make_mocked_request("GET", "/llms.txt")))
    assert "https://surp.ivc.lol/llms-full.txt" in response.text
