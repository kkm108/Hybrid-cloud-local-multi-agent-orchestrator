"""T12: End-to-end poster-loop demo (mocks) — marked ``e2e``.

Launches ``poster_designer.json``, fires the timer, and verifies the full
worker chain in a single message cascade:

    timer → deepseek_1 (brief) → chatgpt_1 (style) → gemini1_1 (image)
          → facebook_post (dry-run outbox entry)

Assertions: the routing log records every hop, and the dry-run outbox payload
carries the composed text plus an image placeholder reference.
"""

import json

import pytest
from fastapi.testclient import TestClient

from socialai import state as state_mod
from socialai.actuators.facebook import FacebookActuator
from socialai.orchestrator.app import build_app
from socialai.orchestrator.campaigns import set_manifest_dir
from socialai.orchestrator.components import ComponentRegistry
from socialai.router import Router

pytestmark = pytest.mark.e2e


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    state_mod.set_state_dir(tmp_path / "state")
    state_mod.reset_state()
    set_manifest_dir(tmp_path / "manifests")
    (tmp_path / "manifests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifests" / "poster_designer.json").write_text(
        json.dumps(_poster_manifest()), encoding="utf-8"
    )
    outbox = tmp_path / "outbox"
    log = tmp_path / "logs" / "routing.jsonl"

    router = Router(log_path=log)
    registry = ComponentRegistry(router)
    app = build_app(router=router, registry=registry)
    return {
        "client": TestClient(app),
        "registry": registry,
        "router": router,
        "outbox": outbox,
        "log": log,
    }


class TestPosterLoop:
    def test_full_chain_routes_and_posts(self, ctx) -> None:
        c, registry, outbox, log = (
            ctx["client"], ctx["registry"], ctx["outbox"], ctx["log"],
        )
        # Launch, then wire the paper-chain worker runners + dry-run actuator.
        assert c.post("/api/campaigns/poster_designer/launch").status_code == 200
        _wire_runners(registry, outbox)

        # Fire the poster_timer trigger once (assigned_ai = deepseek_1).
        manifest = _poster_manifest()
        timer = next(x for x in manifest["components"] if x["kind"] == "timer")
        registry.send(
            f"[SEND_TO: {timer['assigned_ai']}] {timer['trigger']} [/SEND_TO]",
            from_id="timer",
        )

        # 1. Routing log shows deepseek → chatgpt → gemini → facebook, in order.
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        chain = [json.loads(ln)["to"] for ln in lines]
        for hop in ("deepseek_1", "chatgpt_1", "gemini1_1", "facebook_post"):
            assert hop in chain
        assert chain.index("deepseek_1") < chain.index("chatgpt_1") < chain.index(
            "gemini1_1"
        ) < chain.index("facebook_post")

        # 2. Dry-run outbox entry exists with text + image reference.
        out_files = list(outbox.glob("*.json"))
        assert out_files, "no outbox payload written"
        payload = json.loads(out_files[0].read_text(encoding="utf-8"))
        assert payload["mode"] == "dry_run"
        assert payload["posted"] is False
        assert "PLACEHOLDER" in payload["image_ref"].upper()
        assert payload["text"]

    def test_kill_switch_after_loop(self, ctx) -> None:
        c = ctx["client"]
        c.post("/api/campaigns/poster_designer/launch")
        _wire_runners(ctx["registry"], ctx["outbox"])
        stop = c.post("/api/campaigns/stop")
        assert stop.status_code == 200
        assert stop.json()["status"] == "STOPPED"


def _wire_runners(registry: ComponentRegistry, outbox) -> None:
    def make_forward(next_id: str, prefix: str):
        return lambda comp, block: f"[SEND_TO: {next_id}] {prefix}: {block.body} [/SEND_TO]"

    registry.get("deepseek_1").runner = make_forward(
        "chatgpt_1", "brief"
    )
    registry.get("chatgpt_1").runner = make_forward(
        "gemini1_1", "styled (DO-NOT-copy-previous)"
    )

    def gemini(comp, block):
        return (
            f"[SEND_TO: facebook_post] {block.body} | "
            f"image: IMG_PLACEHOLDER_001 [/SEND_TO]"
        )

    registry.get("gemini1_1").runner = gemini

    def facebook(comp, block):
        act = FacebookActuator(mode="dry_run", outbox_dir=str(outbox))
        act.compose(block.body, image_ref="IMG_PLACEHOLDER_001")
        act.type(block.body)
        act.attach(media_ref="IMG_PLACEHOLDER_001")
        payload = act.post()
        return f"facebook-posted into {payload['outbox']}"

    registry.get("facebook_post").runner = facebook


def _poster_manifest() -> dict:
    return {
        "name": "poster_designer",
        "description": "Creative poster-loop demo (mocks).",
        "agents": [
            {"id": "deepseek_1", "kind": "worker_tab", "vendor": "deepseek",
             "role": "brief_writer", "role_prompt": "brief"},
            {"id": "chatgpt_1", "kind": "worker_tab", "vendor": "chatgpt",
             "role": "style_director", "role_prompt": "style"},
            {"id": "gemini1_1", "kind": "worker_tab", "vendor": "gemini",
             "role": "image_generator", "role_prompt": "image"},
        ],
        "components": [
            {"id": "deepseek_1", "kind": "worker_tab", "assigned_ai": "deepseek_1", "config": {}},
            {"id": "chatgpt_1", "kind": "worker_tab", "assigned_ai": "chatgpt_1", "config": {}},
            {"id": "gemini1_1", "kind": "worker_tab", "assigned_ai": "gemini1_1", "config": {}},
            {"id": "poster_timer", "kind": "timer", "assigned_ai": "deepseek_1",
             "config": {}, "interval_s": 30, "trigger": "Start a new poster design brief."},
            {"id": "facebook_post", "kind": "browser_bot", "assigned_ai": "gemini1_1",
             "config": {}, "mode": "dry_run"},
        ],
        "target_recipient": "deepseek_1",
        "style_rotation": ["minimalist", "bold retro"],
    }
