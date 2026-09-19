from pathlib import Path


SOURCE = Path("frontend/src/components/ApiKeys.tsx").read_text()


def test_api_keys_declares_keys_state_before_loading_and_rendering():
    declaration = "const [keys, setKeys] = useState<ApiKey[]>([])"
    assert declaration in SOURCE
    assert SOURCE.index(declaration) < SOURCE.index("const loadKeys")
    assert SOURCE.index(declaration) < SOURCE.index("keys.length")
