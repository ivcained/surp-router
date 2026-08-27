from home_page import CONTENT as _HOME_CONTENT


def test_homepage_starts_with_one_value_proposition_and_primary_cta():
    assert 'Spend less on every AI call.' in _HOME_CONTENT
    assert 'pay in USDC on Base' in _HOME_CONTENT
    assert 'crypto onramp' not in _HOME_CONTENT.lower()
    assert 'Try it free' in _HOME_CONTENT


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


def test_homepage_explains_cache_hit_price():
    assert '$0.001' in _HOME_CONTENT
    assert 'identical questions' in _HOME_CONTENT


def test_homepage_has_current_onboarding_copy():
    assert 'Connect once' in _HOME_CONTENT
