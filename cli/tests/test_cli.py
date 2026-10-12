"""Offline tests for surp-cli — no network: urllib is monkeypatched."""

import io
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")

from surp_cli import cli  # noqa: E402


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Recorder:
    def __init__(self, status=200, body="{}"):
        self.status = status
        self.body = body
        self.calls = []

    def __call__(self, req, timeout=None):
        self.calls.append(req)
        return FakeResponse(self.status, self.body)


def _patch(monkeypatch, recorder):
    monkeypatch.setattr(urllib.request, "urlopen", recorder)


def test_models_hits_v1_models_and_passes_key(monkeypatch, capsys):
    rec = Recorder(200, json.dumps({"data": [{"id": "surp/free"}]}))
    _patch(monkeypatch, rec)
    assert cli.main(["--base-url", "https://x.test", "models", "--json"]) == 0
    req = rec.calls[0]
    assert req.full_url == "https://x.test/v1/models"
    assert req.get_method() == "GET"
    assert json.loads(capsys.readouterr().out)["data"][0]["id"] == "surp/free"


def test_chat_builds_openai_payload_and_extracts_content(monkeypatch, capsys):
    body = json.dumps({"choices": [{"message": {"content": "hi there"}}]})
    rec = Recorder(200, body)
    _patch(monkeypatch, rec)
    assert cli.main(["chat", "-m", "surp/value", "-p", "hello", "--key", "sk-1",
                      "--system", "be brief"]) == 0
    req = rec.calls[0]
    assert req.full_url == "https://surp.ivc.lol/v1/chat/completions"
    assert req.get_header("Authorization") == "Bearer sk-1"
    payload = json.loads(req.data)
    assert payload["model"] == "surp/value"
    assert payload["messages"][0] == {"role": "system", "content": "be brief"}
    assert payload["messages"][1] == {"role": "user", "content": "hello"}
    assert capsys.readouterr().out.strip() == "hi there"


def test_chat_error_status_returns_nonzero_and_prints_body(monkeypatch, capsys):
    rec = Recorder(402, json.dumps({"error": "payment required"}))
    _patch(monkeypatch, rec)
    assert cli.main(["chat", "-p", "hello"]) == 1
    assert "payment required" in capsys.readouterr().err


def test_free_key_posts_budgets(monkeypatch):
    rec = Recorder(200, json.dumps({"ok": True, "key": "sk-free"}))
    _patch(monkeypatch, rec)
    assert cli.main(["key", "free", "--label", "ci", "--requests", "5"]) == 0
    req = rec.calls[0]
    assert req.full_url == "https://surp.ivc.lol/api/free-key"
    payload = json.loads(req.data)
    assert payload == {"label": "ci", "elevated_requests": 5, "elevated_tokens": 200000}


def test_balance_encodes_key_query(monkeypatch):
    rec = Recorder(200, json.dumps({"balance_cents": 1}))
    _patch(monkeypatch, rec)
    assert cli.main(["balance", "--key", "sk x&y"]) == 0
    assert "key=sk+x%26y" in rec.calls[0].full_url


def test_transport_error_is_clean(monkeypatch, capsys):
    def boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert cli.main(["models"]) == 1
    assert "error: cannot reach" in capsys.readouterr().err


def test_stdin_prompt(monkeypatch, capsys, monkeypatch_stdin=None):
    body = json.dumps({"choices": [{"message": {"content": "ok"}}]})
    rec = Recorder(200, body)
    _patch(monkeypatch, rec)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "read", lambda: "piped prompt")
    assert cli.main(["chat", "-m", "surp/free"]) == 0
    payload = json.loads(rec.calls[0].data)
    assert payload["messages"][-1]["content"] == "piped prompt"