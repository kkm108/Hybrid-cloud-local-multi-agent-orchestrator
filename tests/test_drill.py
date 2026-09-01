"""T18: Restore drill simulation test (end-to-end, sandbox machine)."""

import json
import zipfile
from pathlib import Path

from scripts.drill import ROOT, _tree_matches_manifest, run_drill


def test_drill_end_to_end(tmp_path) -> None:
    report = run_drill(root=ROOT, tmp_base=tmp_path / "drill")
    bundle = Path(report["bundle"])
    machine = Path(report["machine"])

    assert bundle.is_file() and bundle.name.startswith("socialai-backup-")
    assert machine.is_dir(), "sandbox machine must exist"
    assert report["restore_smoke_ok"] is True
    assert report["smoke_ok"] is True, report.get("restore_log")
    assert report["checksums_equal"] is True

    # Restored tree carries the bundle payload byte-for-byte.
    assert (machine / "manifests" / "simpleagent.json").is_file()
    assert (machine / "schemas" / "manifest.schema.json").is_file()
    assert (machine / "state" / "logs" / "routing.jsonl").is_file()
    assert (machine / ".env.example").is_file()
    assert (machine / ".env").is_file(), ".env recreated from .env.example"
    with zipfile.ZipFile(bundle) as zf:
        manifest = json.loads(zf.read("BUNDLE.json").decode("utf-8"))
    assert manifest["mode"] == "restore"
    assert "sha256_manifest" in manifest


def test_drill_isolates_cwd_and_home(tmp_path) -> None:
    report = run_drill(root=ROOT, tmp_base=tmp_path / "iso")
    machine = Path(report["machine"])
    home = Path(report["home"])
    assert home == machine / "home"
    assert home.is_dir()
    # The developer's real HOME must not leak into the sandbox.
    assert home != Path.home()
    assert str(home).startswith(str(tmp_path)), "HOME must live inside the sandbox"


def test_matches_manifest_detects_drift(tmp_path) -> None:
    report = run_drill(root=ROOT, tmp_base=tmp_path / "drift")
    bundle = Path(report["bundle"])
    machine = Path(report["machine"])
    assert report["checksums_equal"] is True

    with zipfile.ZipFile(bundle) as zf:
        manifest = json.loads(zf.read("BUNDLE.json").decode("utf-8"))
    target = next(
        a for a in manifest["sha256_manifest"] if a.startswith("manifests/")
    )
    path = machine / target
    path.write_text("drift", encoding="utf-8")
    assert _tree_matches_manifest(bundle, machine) is False, "tamper must be detected"
