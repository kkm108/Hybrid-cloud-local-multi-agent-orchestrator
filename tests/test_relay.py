"""T10: Relay & templates tests (§2, §7, seeded quick templates)."""

import json

import pytest
from fastapi.testclient import TestClient

from socialai import state as state_mod
from socialai.orchestrator.app import build_app
from socialai.orchestrator.relay import DEFAULT_TEMPLATES, load_templates
from socialai.router import Router


@pytest.fixture
def client(tmp_path, monkeypatch):
    state_mod.set_state_dir(tmp_path / "state")
    state_mod.reset_state()
    log = tmp_path / "logs" / "routing.jsonl"
    app = build_app(router=Router(log_path=log))
    with TestClient(app) as c:
        yield c


class TestRelayRouting:
    def test_free_text_routes_to_default_recipient(self, client) -> None:
        c = client
        c.post("/api/campaigns/simpleagent/launch")  # target = deepseek_1
        r = c.post("/api/relay", json={"text": "give me a status", "sender": "op"})
        assert r.status_code == 200
        entry = r.json()
        assert entry["from"] == "op"
        assert entry["to"] == "deepseek_1"
        assert entry["replies"]

    def test_inline_send_to_override(self, client) -> None:
        c = client
        c.post("/api/campaigns/simpleagent/launch")
        r = c.post(
            "/api/relay",
            json={"text": "[SEND_TO: local_1] do a local check [/SEND_TO]", "sender": "op"},
        )
        assert r.status_code == 200
        entry = r.json()
        assert entry["to"] == "local_1"
        # Reply came from the overridden local_1 handler.
        assert any(res.startswith("reply-from-local_1:") for res in entry["replies"])

    def test_message_recorded_in_state_relay(self, client, tmp_path) -> None:
        c = client
        c.post("/api/campaigns/simpleagent/launch")
        c.post("/api/relay", json={"text": "hello", "sender": "op"})
        state = c.get("/api/state").json()
        assert len(state["relay"]) == 1
        assert state["relay"][0]["text"] == "hello"


class TestTemplates:
    def test_templates_seeded_and_served(self, client) -> None:
        c = client
        r = c.get("/api/templates")
        assert r.status_code == 200
        labels = [t["label"] for t in r.json()]
        for expected in (
            "Read PROJECT_STATE.json",
            "Inspect Target Directory",
            "Run Syntax Error Audit",
        ):
            assert expected in labels

    def test_load_templates_writes_state_file(self, tmp_path) -> None:
        tfile = tmp_path / "templates.json"
        tlist = load_templates(tfile)
        assert tlist == DEFAULT_TEMPLATES
        assert tfile.is_file()
        saved = json.loads(tfile.read_text(encoding="utf-8"))
        # Fresh template file must seed exactly the canonical template set.
        assert saved == DEFAULT_TEMPLATES

    def test_default_templates_have_label_and_text(self) -> None:
        for t in DEFAULT_TEMPLATES:
            assert t["label"]
            assert t["text"]
