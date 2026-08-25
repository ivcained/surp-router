from pathlib import Path

ROOT = Path(__file__).parents[1]
NAV = (ROOT / "frontend/src/components/Nav.tsx").read_text()
INDEX = (ROOT / "frontend/index.html").read_text()
KEYS = (ROOT / "frontend/src/components/ApiKeys.tsx").read_text()


def test_mobile_drawer_has_accessible_close_paths_and_scroll_lock():
    assert "aria-label=\"open menu\"" in NAV
    assert "aria-hidden=\"true\"" in NAV
    assert "e.key === 'Escape'" in NAV
    assert "document.body.style.overflow" in NAV
    assert "setDrawerOpen(false)" in NAV


def test_mobile_drawer_uses_transform_and_reduced_motion():
    assert "aside.sidebar-open" in INDEX
    assert "translateX(-100%) !important" in INDEX
    assert "prefers-reduced-motion: reduce" in INDEX


def test_key_flow_does_not_call_legacy_free_key_endpoint():
    assert "amount_usdc" in KEYS
    assert "/api/free-key" not in KEYS
