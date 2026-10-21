"""Operator identity and Terms of Service pages.

Hermes plugin catalog reviewers require a verifiable named operator and a
real terms page before listing the Surp plugin. Covers /terms, /operator,
JSON-LD operator naming, and cross-links (about, developers, llms.txt, sitemap).
"""

import asyncio
import json
import os
import sys

from aiohttp.test_utils import make_mocked_request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gateway as gw


def test_terms_and_operator_routes_registered():
    app = gw.build_app()
    paths = {r.resource.canonical for r in app.router.routes()}
    assert "/terms" in paths
    assert "/operator" in paths


def _get(path, handler):
    resp = asyncio.run(handler(make_mocked_request("GET", path)))
    assert resp.status == 200
    return resp.text


def test_terms_page_content():
    body = _get("/terms", gw.page_terms).lower()
    for needle in (
        "terms of service",
        "surp.ivc.lol",
        "pay-per-request",
        "surplus intelligence",
        "prepaid",
        "usdc",
        "x402",
        "acceptable use",
        "no warranty",
        "as-is",
        "liability",
        "prepaid balance",
        "termination",
        "refund",
        "unused balance",
        "changes to these terms",
        "hi@surp.ivc.lol",
    ):
        assert needle in body, needle


def test_operator_page_content():
    body = _get("/operator", gw.page_operator)
    for needle in (
        "ivcained",
        "https://github.com/ivcained",
        "hi@surp.ivc.lol",
        "independent",
        "api.surplusintelligence.ai",
        "/terms",
    ):
        assert needle in body, needle


def test_terms_and_operator_have_seo_meta():
    for path in ("/terms", "/operator"):
        meta = gw.PAGE_META[path]
        assert 10 <= len(meta["title"]) <= 70, (path, len(meta["title"]))
        assert 100 <= len(meta["desc"]) <= 170, (path, len(meta["desc"]))


def test_sitemap_lists_terms_and_operator():
    resp = asyncio.run(gw.serve_sitemap(make_mocked_request("GET", "/sitemap.xml")))
    assert resp.status == 200
    assert "https://surp.ivc.lol/terms" in resp.text
    assert "https://surp.ivc.lol/operator" in resp.text


def test_llms_txt_lists_terms_and_operator():
    body = asyncio.run(gw.serve_llms_txt(make_mocked_request("GET", "/llms.txt"))).text
    assert "https://surp.ivc.lol/terms" in body
    assert "https://surp.ivc.lol/operator" in body


def test_about_page_links_terms_and_operator():
    assert 'href="/terms"' in gw._ABOUT_CONTENT
    assert 'href="/operator"' in gw._ABOUT_CONTENT


def test_jsonld_names_the_operator():
    creator = gw.JSONLD_ORG["creator"]
    assert creator.get("name") == "surp.ivc.lol"
    person = creator.get("founder") or creator.get("employee") or creator
    blob = json.dumps(person)
    assert "ivcained" in blob
    assert "https://github.com/ivcained" in blob


def test_developers_page_links_terms_and_operator():
    html = _get("/developers", gw.page_developers)
    assert 'href=\'/terms\'' in html or 'href="/terms"' in html
    assert 'href=\'/operator\'' in html or 'href="/operator"' in html
