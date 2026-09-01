"""Control-center FastAPI app (§7, port 3005).

    GET  /api/health
    GET  /api/state
    GET  /api/manifests
    GET  /api/manifests/{name}
    POST /api/manifests            (schema-validated, 422 on bad)
    PUT  /api/manifests/{name}
    DELETE /api/manifests/{name}
    POST /api/campaigns/{name}/launch
    POST /api/campaigns/stop                (kill switch, must always work)
    GET  /api/components
    POST /api/components/{id}/message
    POST /api/relay
    WS   /ws/dashboard             (state push; stub)
    /                             (static frontend)

Frontend: static files served from ``socialai/web``.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..router import Router
from ..state import (
    append_relay,
    get_components,
    get_state,
)
from . import campaigns as campaigns_mod
from .campaigns import (
    CampaignError,
    ManifestValidationError,
    launch,
    validate_manifest,
)
from .campaigns import stop as stop_campaign
from .components import ComponentRegistry
from .relay import Relay, load_templates

DEFAULT_LOG = Path("state") / "logs" / "routing.jsonl"


class ManifestIn(BaseModel):
    payload: dict


class MessageIn(BaseModel):
    text: str
    from_id: str = "operator"


class RelayIn(BaseModel):
    text: str
    sender: str = "operator"
    recipient: str | None = None


def _manifest_names() -> list[str]:
    if not campaigns_mod.MANIFEST_DIR.is_dir():
        return []
    return sorted(p.stem for p in campaigns_mod.MANIFEST_DIR.glob("*.json"))


def build_app(router: Router | None = None, registry: ComponentRegistry | None = None,
              scheduler=None, reload_state: bool = True) -> FastAPI:
    """Construct the control-center app, sharing a router + component registry.

    A ``TimerScheduler`` is created unless one is supplied; its timer triggers
    are routed to the assigned AI through the registry.
    """
    router = router or Router(log_path=DEFAULT_LOG)
    registry = registry or ComponentRegistry(router)

    from .timer import TimerScheduler  # noqa: PLC0415

    scheduler = scheduler or TimerScheduler(
        on_fire=lambda ai, trigger: registry.send(
            f"[SEND_TO: {ai}] {trigger} [/SEND_TO]", from_id="timer"
        )
    )

    relay_svc = Relay(registry)

    app = FastAPI(title="SocialAI Control Center", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/state")
    def state() -> dict:
        return get_state()

    @app.get("/api/manifests")
    def manifests() -> list[str]:
        return _manifest_names()

    @app.get("/api/manifests/{name}")
    def manifest_detail(name: str) -> dict:
        path = campaigns_mod.MANIFEST_DIR / f"{name}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"manifest not found: {name}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="invalid JSON on disk") from exc

    @app.post("/api/manifests")
    def create_manifest(body: ManifestIn) -> dict:
        try:
            validate_manifest(body.payload)
        except ManifestValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        path = campaigns_mod.MANIFEST_DIR / f"{body.payload['name']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body.payload, indent=2), encoding="utf-8")
        return {"saved": path.name}

    @app.put("/api/manifests/{name}")
    def update_manifest(name: str, body: ManifestIn) -> dict:
        path = campaigns_mod.MANIFEST_DIR / f"{name}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"manifest not found: {name}")
        try:
            validate_manifest(body.payload)
        except ManifestValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        path.write_text(json.dumps(body.payload, indent=2), encoding="utf-8")
        return {"saved": path.name}

    @app.delete("/api/manifests/{name}")
    def delete_manifest(name: str) -> dict:
        path = campaigns_mod.MANIFEST_DIR / f"{name}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"manifest not found: {name}")
        path.unlink()
        return {"deleted": name}

    @app.post("/api/campaigns/{name}/launch")
    def campaign_launch(name: str) -> dict:
        try:
            launched = launch(name, registry, scheduler=scheduler)
            relay_svc.set_default_recipient(launched["target_recipient"])
            return launched
        except CampaignError as exc:
            raise HTTPException(status_code=400, detail=f"launch failed: {exc}") from exc

    @app.post("/api/campaigns/stop")
    def campaign_stop() -> dict:
        return stop_campaign(scheduler=scheduler)

    @app.get("/api/components")
    def components() -> dict:
        return get_components()

    @app.post("/api/components/{component_id}/message")
    def component_message(component_id: str, body: MessageIn) -> dict:
        comp = registry.get(component_id)
        if comp is None:
            # Unknown target: dead-letter via router, still a 404 for the caller.
            raise HTTPException(status_code=404, detail=f"unknown component: {component_id}")
        replies = registry.send(body.text, from_id=body.from_id)
        record = {
            "from": body.from_id,
            "to": component_id,
            "text": body.text,
            "replies": replies,
        }
        append_relay(record)
        return {"component": component_id, "replies": replies}

    @app.get("/api/templates")
    def templates() -> list[dict]:
        return load_templates()

    @app.post("/api/relay")
    def relay(body: RelayIn) -> dict:
        if body.recipient is not None:
            relay_svc.set_default_recipient(body.recipient)
        return relay_svc.handle(body.text, sender=body.sender)

    @app.websocket("/ws/dashboard")
    async def ws_dashboard(websocket: WebSocket) -> None:
        """State-push stub: sends the current snapshot on connect, then stays open."""
        await websocket.accept()
        try:
            await websocket.send_json(get_state())
            while True:
                # Keep-alive: push refreshed state periodically (polled elsewhere).
                await websocket.receive_text()
                await websocket.send_json(get_state())
        except WebSocketDisconnect:
            return

    # --- static frontend (mounted last so it never shadows API routes) ---
    from fastapi.staticfiles import StaticFiles  # noqa: PLC0415

    web_dir = Path(__file__).resolve().parent.parent / "web"
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app
