"""T04: Orchestrator & campaign lifecycle tests (§4, §5, §7, §11)."""

import json

import pytest
from fastapi.testclient import TestClient

from socialai import state as state_mod
from socialai.orchestrator.app import build_app
from socialai.router import Router


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Control-center app isolated to tmp state + routing log."""
    state_mod.set_state_dir(tmp_path / "state")
    state_mod.reset_state()
    log_path = tmp_path / "logs" / "routing.jsonl"
    router = Router(log_path=log_path)
    app = build_app(router=router)
    with TestClient(app) as c:
        yield c, log_path


class TestLifecycle:
    def test_launch_simpleagent_sets_running(self, client) -> None:
        c, _ = client
        r = c.post("/api/campaigns/simpleagent/launch")
        assert r.status_code == 200
        st = c.get("/api/state").json()
        assert st["campaign"] is not None
        assert st["campaign"]["status"] == "RUNNING"
        assert st["campaign"]["name"] == "simpleagent"

    def test_launch_registers_components(self, client) -> None:
        c, _ = client
        c.post("/api/campaigns/simpleagent/launch")
        comps = c.get("/api/components").json()
        # manual_input is always registered (§11).
        assert "manual_input" in comps
        assert "deepseek_1" in comps
        assert "local_1" in comps

    def test_launch_unknown_manifest_400(self, client) -> None:
        c, _ = client
        r = c.post("/api/campaigns/nope/launch")
        assert r.status_code == 400

    def test_stop_is_kill_switch(self, client) -> None:
        c, _ = client
        c.post("/api/campaigns/simpleagent/launch")
        r = c.post("/api/campaigns/stop")
        assert r.status_code == 200
        assert r.json()["status"] == "STOPPED"
        st = c.get("/api/state").json()
        assert st["campaign"] is None


class TestBenchmark:
    def test_inject_benchmark_reply_recorded(self, client) -> None:
        c, _ = client
        c.post("/api/campaigns/simpleagent/launch")
        body = {
            "text": "write a product benchmark line",
            "from_id": "benchmarker",
        }
        # Route to the worker tab via an explicit SEND_TO block.
        payload = self._send_to("deepseek_1", body["text"])
        r = c.post(
            "/api/components/deepseek_1/message",
            json={"text": payload, "from_id": body["from_id"]},
        )
        assert r.status_code == 200
        replies = r.json()["replies"]
        assert replies, "expected at least one routed reply"
        assert replies[0].startswith("reply-from-deepseek_1:")

    def test_routing_log_rows_written(self, client) -> None:
        c, log_path = client
        c.post("/api/campaigns/simpleagent/launch")
        c.post(
            "/api/components/deepseek_1/message",
            json={"text": self._send_to("deepseek_1", "hello"), "from_id": "bench"},
        )
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert lines, "expected routing log rows"
        last = json.loads(lines[-1])
        assert last["to"] == "deepseek_1"
        assert last["from"] == "bench"

    def test_unknown_component_message_404(self, client) -> None:
        c, _ = client
        r = c.post(
            "/api/components/ghost_9/message",
            json={"text": "hi", "from_id": "op"},
        )
        assert r.status_code == 404

    @staticmethod
    def _send_to(target: str, body: str) -> str:
        return f"[SEND_TO: {target}] {body} [/SEND_TO]"


class TestApiSurface:
    def test_health(self, client) -> None:
        c, _ = client
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_manifests_listed(self, client) -> None:
        c, _ = client
        r = c.get("/api/manifests")
        names = r.json()
        assert "simpleagent" in names

    def test_relay(self, client) -> None:
        c, _ = client
        r = c.post("/api/relay", json={"text": "status?", "sender": "op"})
        assert r.status_code == 200
        assert r.json()["from"] == "op"
        assert r.json()["text"] == "status?"
