"""T07: Manifest studio & seeds tests (§8, validation, CRUD + 422)."""

import json

import pytest
from fastapi.testclient import TestClient

from socialai import state as state_mod
from socialai.orchestrator.app import build_app
from socialai.orchestrator.campaigns import set_manifest_dir, validate_manifest
from socialai.router import Router

_VALID = {
    "name": "test_camp",
    "description": "test",
    "agents": [
        {
            "id": "deepseek_1",
            "kind": "worker_tab",
            "vendor": "deepseek",
            "role": "r",
            "role_prompt": "p",
        }
    ],
    "components": [
        {"id": "deepseek_1", "kind": "worker_tab", "assigned_ai": "deepseek_1", "config": {}}
    ],
    "target_recipient": "deepseek_1",
}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point manifest store + state into tmp paths; return a TestClient."""
    import shutil

    state_mod.set_state_dir(tmp_path / "state")
    state_mod.reset_state()
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    set_manifest_dir(mdir)
    for fname in ("simpleagent.json", "poster_designer.json", "trading_dhan.json"):
        repo = __import__("pathlib").Path("manifests") / fname
        if repo.is_file():
            shutil.copy(repo, mdir / fname)
    log = tmp_path / "logs" / "routing.jsonl"
    app = build_app(router=Router(log_path=log))
    with TestClient(app) as c:
        yield c, mdir


class TestSchemaValidation:
    def test_valid_manifest_passes(self) -> None:
        validate_manifest(_VALID)

    def test_missing_required_field(self) -> None:
        bad = {k: v for k, v in _VALID.items() if k != "description"}
        with pytest.raises(Exception, match="required"):
            validate_manifest(bad)

    def test_bad_component_kind(self) -> None:
        bad = json.loads(json.dumps(_VALID))
        bad["components"][0]["kind"] = "teleporter"
        with pytest.raises(Exception, match="'teleporter'"):
            validate_manifest(bad)

    def test_missing_agent_field(self) -> None:
        bad = json.loads(json.dumps(_VALID))
        del bad["agents"][0]["role_prompt"]
        with pytest.raises(Exception, match="required"):
            validate_manifest(bad)

    def test_bad_name_pattern(self) -> None:
        bad = json.loads(json.dumps(_VALID))
        bad["name"] = "Bad Name!"
        with pytest.raises(Exception, match="'Bad Name!'"):
            validate_manifest(bad)

    def test_unknown_top_level_key_rejected(self) -> None:
        bad = json.loads(json.dumps(_VALID))
        bad["surprise"] = True
        with pytest.raises(Exception):
            validate_manifest(bad)


class TestCrud:
    def test_create_valid_manifest(self, isolated) -> None:
        c, mdir = isolated
        r = c.post("/api/manifests", json={"payload": _VALID})
        assert r.status_code == 200
        assert (mdir / "test_camp.json").is_file()

    def test_create_invalid_manifest_422(self, isolated) -> None:
        c, _ = isolated
        bad = json.loads(json.dumps(_VALID))
        bad["components"][0]["kind"] = "teleporter"
        r = c.post("/api/manifests", json={"payload": bad})
        assert r.status_code == 422

    def test_list_manifests(self, isolated) -> None:
        c, _ = isolated
        names = c.get("/api/manifests").json()
        for n in ("simpleagent", "poster_designer", "trading_dhan"):
            assert n in names

    def test_get_detail(self, isolated) -> None:
        c, _ = isolated
        r = c.get("/api/manifests/simpleagent")
        assert r.status_code == 200
        assert r.json()["name"] == "simpleagent"

    def test_get_missing_404(self, isolated) -> None:
        c, _ = isolated
        assert c.get("/api/manifests/ghost").status_code == 404

    def test_update_manifest(self, isolated) -> None:
        c, _ = isolated
        c.post("/api/manifests", json={"payload": _VALID})
        updated = json.loads(json.dumps(_VALID))
        updated["description"] = "updated desc"
        r = c.put("/api/manifests/test_camp", json={"payload": updated})
        assert r.status_code == 200
        assert c.get("/api/manifests/test_camp").json()["description"] == "updated desc"

    def test_update_invalid_422(self, isolated) -> None:
        c, _ = isolated
        c.post("/api/manifests", json={"payload": _VALID})
        bad = json.loads(json.dumps(_VALID))
        bad["name"] = "Bad"
        r = c.put("/api/manifests/test_camp", json={"payload": bad})
        assert r.status_code == 422

    def test_delete_manifest(self, isolated) -> None:
        c, _ = isolated
        c.post("/api/manifests", json={"payload": _VALID})
        r = c.delete("/api/manifests/test_camp")
        assert r.status_code == 200
        assert "test_camp" not in c.get("/api/manifests").json()

    def test_delete_missing_404(self, isolated) -> None:
        c, _ = isolated
        assert c.delete("/api/manifests/ghost").status_code == 404


class TestSeeds:
    @pytest.mark.parametrize(
        "name",
        [
            "simpleagent",
            "poster_designer",
            "trading_dhan",
        ],
    )
    def test_seed_manifests_validate(self, isolated, name) -> None:
        c, _ = isolated
        manifest = c.get(f"/api/manifests/{name}").json()
        validate_manifest(manifest)

    def test_poster_designer_shape(self, isolated) -> None:
        c, _ = isolated
        m = c.get("/api/manifests/poster_designer").json()
        assert len(m["agents"]) == 3
        kinds = {comp["kind"] for comp in m["components"]}
        assert "timer" in kinds
        assert "browser_bot" in kinds
        assert isinstance(m.get("style_rotation"), list)
        assert len(m.get("style_rotation", [])) > 0

    def test_trading_dhan_has_local_llm(self, isolated) -> None:
        c, _ = isolated
        m = c.get("/api/manifests/trading_dhan").json()
        kinds = {comp["kind"] for comp in m["components"]}
        assert "local_llm" in kinds
