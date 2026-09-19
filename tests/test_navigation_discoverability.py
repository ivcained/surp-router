import asyncio
from aiohttp.test_utils import make_mocked_request
import gateway


def test_pricing_alias_is_available():
    response = asyncio.run(gateway.page_pricing(make_mocked_request("GET", "/pricing")))
    assert response.status == 200
    assert "price" in response.text.lower()


def test_homepage_links_key_resources():
    response = asyncio.run(gateway.page_home(make_mocked_request("GET", "/")))
    for path in ["/docs", "/pricing", "/models", "/about", "/contact", "/privacy"]:
        assert path in response.text
