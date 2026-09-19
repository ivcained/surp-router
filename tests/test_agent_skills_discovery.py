import asyncio
import hashlib
import json
from pathlib import Path
from aiohttp.test_utils import make_mocked_request

import gateway


def test_agent_skills_index_matches_published_skill_artifact():
    response = asyncio.run(gateway.serve_agent_skills_index(make_mocked_request("GET", "/.well-known/agent-skills/index.json")))
    index = json.loads(response.text)
    skill = index["skills"][0]
    artifact = Path(gateway._STATIC_DIR) / "agent-skills" / "surp-api" / "SKILL.md"
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

    assert index["$schema"] == "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
    assert skill["name"] == "surp-api"
    assert skill["type"] == "skill-md"
    assert skill["description"]
    assert skill["url"] == "https://surp.ivc.lol/static/agent-skills/surp-api/SKILL.md"
    assert skill["digest"] == f"sha256:{digest}"
    assert len(digest) == 64
