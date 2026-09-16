import gateway

def test_agent_discovery_routes_exist():
    app = gateway.build_app()
    paths = {r.canonical for r in app.router.resources()}
    assert "/.well-known/agent-card.json" in paths
    assert "/.well-known/api-catalog" in paths
    assert "/.well-known/ai-plugin.json" in paths
    assert "/llms.txt" in paths
    assert "/openapi.json" in paths
    assert "/auth.md" in paths
    assert "/mcp.json" in paths
