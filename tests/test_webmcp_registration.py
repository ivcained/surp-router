from pathlib import Path

import gateway


def test_server_rendered_pages_use_batch_webmcp_registration():
    html = gateway._render_html("<h1>Test</h1>", "/")
    assert "context.provideContext({tools: tools})" in html
    assert "new AbortController()" in html
    assert "surp_list_models" in html
    assert "surp_get_status" in html
    assert "inputSchema" in html
    assert "execute:" in html


def test_spa_uses_same_webmcp_context_on_page_load():
    html = Path("frontend/index.html").read_text()
    assert "navigator.modelContext.provideContext({ tools })" in html
    assert "new AbortController()" in html
    assert "surp_list_models" in html
    assert "surp_get_status" in html
