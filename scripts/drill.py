"""T18: Restore drill — local simulation of a second-machine restore.

Automates: fresh restore bundle -> sandbox tmp "machine" (isolated cwd/HOME)
-> restore.py inside the sandbox -> smoke inside the restored tree -> bundle
manifest equality assert (BUNDLE.json checksums match the restored files).

This mirrors docs/RESTORE_DRILL.md without needing a real second machine.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tree_matches_manifest(bundle: Path, machine: Path) -> bool:
    """True when every BUNDLE.json checksum matches the restored files.

    The manifest lives inside the bundle (restore.py consumes BUNDLE.json and
    never writes it into the tree). Runtime files smoke may create in the
    sandbox (e.g. ``state/templates.json``) are not shipped, so only the
    bundled keys are asserted.
    """
    import zipfile

    with zipfile.ZipFile(bundle) as zf:
        expected = json.loads(zf.read("BUNDLE.json").decode("utf-8"))["sha256_manifest"]
    actual = {
        p.relative_to(machine).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in machine.rglob("*")
        if p.is_file()
    }
    return all(actual.get(arc) == sha for arc, sha in expected.items())


def run_drill(root: Path | None = None, tmp_base: Path | None = None) -> dict:
    """Execute the full drill; raise ``RuntimeError`` on any failed checkpoint."""
    root = Path(root).resolve() if root else ROOT
    tmp = (
        Path(tmp_base).resolve()
        if tmp_base
        else Path(tempfile.mkdtemp(prefix="socialai-drill-"))
    )
    bundle_dir = tmp / "bundle_out"
    machine = tmp / "machine"
    home_dir = machine / "home"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    machine.mkdir(parents=True, exist_ok=True)
    home_dir.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    scripts_dir = root / "scripts"

    # 1. Fresh restore bundle, built on the source machine (cwd = repo root).
    backup = subprocess.run(
        [py, str(scripts_dir / "backup.py"), "--mode", "restore", "--out", str(bundle_dir)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if backup.returncode != 0:
        raise RuntimeError(f"backup step failed: {backup.stdout}{backup.stderr}")
    bundles = sorted(bundle_dir.glob("socialai-backup-*.zip"))
    if not bundles:
        raise RuntimeError("backup produced no bundle")
    bundle = bundles[-1]

    # 2. Sandbox machine env: isolated cwd + HOME.
    sandbox_env = dict(os.environ)
    sandbox_env["HOME"] = str(home_dir)

    # 3. restore.py runs inside the sandbox (cwd = machine, isolated HOME).
    restore = subprocess.run(
        [py, str(scripts_dir / "restore.py"), "--bundle", str(bundle), "--target", str(machine)],
        cwd=str(machine),
        env=sandbox_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    restore_log = restore.stdout + restore.stderr
    if restore.returncode != 0:
        raise RuntimeError(f"restore step failed:\n{restore_log}")
    restore_smoke_ok = "smoke: OK" in restore.stdout

    # 4. Smoke equivalent inside the restored tree (isolated cwd/HOME).
    smoke = subprocess.run(
        [py, "-m", "socialai.cli", "--smoke"],
        cwd=str(machine),
        env=sandbox_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    smoke_ok = smoke.returncode == 0

    # 5. Bundle manifest equality: BUNDLE.json checksums vs restored files.
    checksums_equal = _tree_matches_manifest(bundle, machine)

    return {
        "bundle": bundle,
        "machine": machine,
        "home": home_dir,
        "restore_smoke_ok": restore_smoke_ok,
        "smoke_ok": smoke_ok,
        "checksums_equal": checksums_equal,
        "restore_log": restore_log,
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = None
    if "--out" in argv:
        i = argv.index("--out")
        out = Path(argv[i + 1]) if i + 1 < len(argv) else None
    try:
        report = run_drill(tmp_base=out)
    except Exception as exc:  # noqa: BLE001
        print(f"drill failed: {exc}", file=sys.stderr)
        return 1
    print(f"bundle:      {report['bundle']}")
    print(f"machine:     {report['machine']}")
    print(f"home:        {report['home']}")
    print(f"restore:     {'smoke OK' if report['restore_smoke_ok'] else 'smoke FAILED'}")
    print(f"smoke:       {'OK' if report['smoke_ok'] else 'FAILED'}")
    print(f"checksums:   {'MATCH' if report['checksums_equal'] else 'MISMATCH'}")
    ok = report["restore_smoke_ok"] and report["smoke_ok"] and report["checksums_equal"]
    print(f"drill:       {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
