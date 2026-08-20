"""Homepage onboarding and hierarchy regression tests."""

from home_page import CONTENT as _HOME_CONTENT


def test_homepage_starts_with_one_value_proposition_and_primary_cta():
    assert 'Spend less on every AI call.' in _HOME_CONTENT
    assert 'href="#try" class="home-primary-cta"' in _HOME_CONTENT
    assert 'Try it free' in _HOME_CONTENT
    assert _HOME_CONTENT.index('Spend less on every AI call.') < _HOME_CONTENT.index('id="try"')
    assert 'crypto onramp' not in _HOME_CONTENT.lower()


def test_homepage_explains_cache_hit_price():
    assert '$0.001' in _HOME_CONTENT
    assert 'identical questions' in _HOME_CONTENT
    assert 'id="cache-tip-text"' in _HOME_CONTENT


def test_homepage_demo_uses_aa_routes_and_defaults_to_free():
    assert 'data-mode="free"' in _HOME_CONTENT
    assert 'data-mode="value"' in _HOME_CONTENT
    assert 'data-mode="frontier"' in _HOME_CONTENT
    assert 'data-mode="fast"' in _HOME_CONTENT
    assert 'data-mode="vision"' in _HOME_CONTENT
    assert 'data-mode="custom"' in _HOME_CONTENT
    assert _HOME_CONTENT.index('data-mode="free"') < _HOME_CONTENT.index('data-mode="value"')
    assert 'data-route="surp/best-coding"' not in _HOME_CONTENT


def test_homepage_separates_surp_and_surplus_keys():
    assert 'https://surp.ivc.lol/v1' in _HOME_CONTENT
    assert 'https://api.surplusintelligence.ai/min30/v1/chat/completions' in _HOME_CONTENT
    assert 'Your Surplus balance does not show here' in _HOME_CONTENT
    assert 'Copy this into your agent' in _HOME_CONTENT


def test_homepage_demo_precedes_funding_and_requires_no_auth():
    assert 'id="try"' in _HOME_CONTENT
    assert 'No wallet. No account. No API key.' in _HOME_CONTENT
    assert 'id="connect"' in _HOME_CONTENT
    assert _HOME_CONTENT.index('id="try"') < _HOME_CONTENT.index('id="connect"')


def test_homepage_progressively_discloses_funding_paths():
    assert '<details class="funding-path"' in _HOME_CONTENT
    assert 'Connect Hermes' in _HOME_CONTENT
    assert 'Pay from a wallet' in _HOME_CONTENT
    assert 'Use an API key' in _HOME_CONTENT


def test_homepage_buries_implementation_details_behind_docs_link():
    assert 'Technical details belong in the docs' in _HOME_CONTENT
    assert 'href="/docs"' in _HOME_CONTENT
    assert 'explain it like i\'m 5' not in _HOME_CONTENT.lower()
