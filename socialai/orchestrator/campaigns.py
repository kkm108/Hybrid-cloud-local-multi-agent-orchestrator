"""Campaign lifecycle: launch / stop (§11).

A campaign is one running manifest instance. Launching reads a manifest from
``manifests/``, registers its components on the shared registry, and marks the
campaign RUNNING. Stopping is the kill switch: it unconditionally clears the
campaign, components and any running processes.

Manifests live in ``manifests/``; the layout is validated against the schema
in ``schemas/manifest.schema.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from ..state import set_campaign
from .components import Component, ComponentRegistry

MANIFEST_DIR = Path("manifests")
SCHEMA_DIR = Path("schemas") / "manifest.schema.json"


def set_manifest_dir(directory) -> None:
    """Redirect the manifest store directory (test isolation).

    The authoritative schema is always loaded from the repo ``schemas/``.
    """
    global MANIFEST_DIR
    MANIFEST_DIR = Path(directory)


class CampaignError(Exception):
    """Raised for invalid manifests or lifecycle misuse."""


class ManifestValidationError(CampaignError):
    """Raised when a manifest fails schema validation (→ HTTP 422)."""


def _load_schema() -> dict:
    if not SCHEMA_DIR.is_file():
        raise ManifestValidationError("manifest schema not found")
    return json.loads(SCHEMA_DIR.read_text(encoding="utf-8"))


def validate_manifest(data: dict) -> None:
    """Validate a manifest dict against the §8 schema. Raise on failure."""
    schema = _load_schema()
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        raise ManifestValidationError(f"schema violation: {exc.message}") from exc


def _load_manifest(name: str) -> dict:
    if name.endswith(".json"):
        path = MANIFEST_DIR / name
    else:
        path = (MANIFEST_DIR / name).with_suffix(".json")
    if not path.is_file():
        raise CampaignError(f"manifest not found: {name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CampaignError(f"invalid JSON in {name}") from exc
    validate_manifest(data)
    return data


def launch(name: str, registry: ComponentRegistry, scheduler=None) -> dict:
    """Launch a campaign from its manifest, registering its components.

    Timer components are also registered on the scheduler (if provided) so
    their trigger fires to ``assigned_ai`` every ``interval_s``.
    """
    manifest = _load_manifest(name)
    # Components are keyed by id; skip duplicate ids defensively.
    seen: set[str] = set()
    for comp in manifest["components"]:
        cid = comp["id"]
        if cid in seen:
            continue
        seen.add(cid)
        registry.add(
            Component(
                id=cid,
                kind=comp["kind"],
                config=comp.get("config", {}),
                assigned_ai=comp.get("assigned_ai"),
            )
        )
        if comp["kind"] == "timer" and scheduler is not None:
            scheduler.add(
                cid,
                interval_s=float(comp["interval_s"]),
                trigger=comp["trigger"],
                assigned_ai=comp.get("assigned_ai", manifest["target_recipient"]),
            )
    campaign = {
        "name": manifest["name"],
        "manifest": name,
        "description": manifest["description"],
        "target_recipient": manifest["target_recipient"],
        "status": "RUNNING",
    }
    set_campaign(campaign)
    return campaign


def stop(scheduler=None) -> dict:
    """Kill switch (§11): unconditionally clear everything."""
    if scheduler is not None:
        scheduler.stop()
    set_campaign(None)
    return {"campaign": None, "status": "STOPPED"}
