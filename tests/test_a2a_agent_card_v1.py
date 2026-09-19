import asyncio
import json
from aiohttp.test_utils import make_mocked_request

import gateway


def test_a2a_agent_card_v1_required_fields_and_skill_tags():
    request = make_mocked_request("GET", "/.well-known/agent-card.json")
    response = asyncio.run(gateway.serve_agent_card(request))
    card = json.loads(response.text)

    assert response.status == 200
    assert card["capabilities"] == {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionHistory": False,
    }
    assert card["defaultInputModes"] == ["application/json", "text/plain"]
    assert card["defaultOutputModes"] == ["application/json", "text/plain"]
    assert card["supportedInterfaces"][0]["protocolBinding"] == "HTTP+JSON"
    assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
    assert card["skills"]
    assert card["skills"][0]["tags"]
    assert all(isinstance(tag, str) and tag for tag in card["skills"][0]["tags"])
