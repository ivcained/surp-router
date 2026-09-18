from home_page import CONTENT


def test_free_key_card_precedes_prompt_card():
    create_heading = CONTENT.index('<h3>Create a free key</h3>')
    prompt_heading = CONTENT.index('<h3>Copy this into your agent</h3>')
    assert create_heading < prompt_heading
    prompt_card = CONTENT[prompt_heading:CONTENT.index('</div>\n  </section>', prompt_heading)]
    assert 'id="btn-make-key"' not in prompt_card


def test_mobile_agent_card_content_is_constrained():
    assert '.agent-box { width:100%; min-width:0' in CONTENT
    assert 'overflow-wrap:anywhere' in CONTENT
    assert '.agent-box button, .agent-box a.btn { max-width:100%' in CONTENT
