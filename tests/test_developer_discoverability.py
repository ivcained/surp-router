import asyncio
from aiohttp.test_utils import make_mocked_request

import gateway


def test_developer_portal_links_machine_resources():
    response = asyncio.run(gateway.page_developers(make_mocked_request("GET", "/developers")))
    assert response.status == 200
    assert "Surp Developer Portal" in response.text
    for path in ["/docs", "/openapi.json", "/auth.md", "/mcp.json", "/llms.txt"]:
        assert path in response.text


def test_llms_and_sitemap_list_developer_resources():
    llms = asyncio.run(gateway.serve_llms_txt(make_mocked_request("GET", "/llms.txt")))
    for url in ["https://surp.ivc.lol/developers", "https://surp.ivc.lol/openapi.json", "https://surp.ivc.lol/auth.md", "https://surp.ivc.lol/mcp.json"]:
        assert url in llms.text

    sitemap = asyncio.run(gateway.serve_sitemap(make_mocked_request("GET", "/sitemap.xml")))
    for path in ["/developers", "/openapi.json", "/auth.md", "/mcp.json", "/llms.txt"]:
        assert f"https://surp.ivc.lol{path}" in sitemap.text
