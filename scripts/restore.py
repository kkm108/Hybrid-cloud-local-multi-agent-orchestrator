"""SocialAI restore / portability (§12).

Verifies the bundle's sha256 manifest, recreates ``state/``, prompts load of
``.env`` from ``.env.example``, then runs the smoke test to confirm the machine
is operational.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path


def verify_manifest(bundle: Path) -> dict:
    """Re-raise CorruptBundle if any bundled file's checksum mismatches."""
    with zipfile.ZipFile(bundle) as zf:
        names = set(zf.namelist())
        if "BUNDLE.json" not in names:
            raise ValueError("bundle missing BUNDLE.json")
        manifest = json.loads(zf.read("BUNDLE.json").decode("utf-8"))["sha256_manifest"]
        for arcname, expected in manifest.items():
            if arcname not in names:
                raise ValueError(f"bundle missing {arcname} referenced by manifest")
            actual = _sha256(zf.read(arcname))
            if actual != expected:
                raise ValueError(f"checksum mismatch for {arcname}")
    return manifest


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def restore_bundle(bundle: Path, target: Path, run_smoke: bool = True) -> dict:
    bundle = Path(bundle).resolve()
    target = Path(target).resolve()
    manifest = verify_manifest(bundle)

    # Recreate state layout from bundled files, keeping secrets/none else out.
    with zipfile.ZipFile(bundle) as zf:
        for arcname in sorted(zf.namelist()):
            if arcname == "BUNDLE.json":
                continue
            if arcname == ".env" or "outbox/" in arcname or "outbox" in arcname.split("/"):
                continue
            dest = target / arcname
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(arcname))

    env_example = target / ".env.example"
    env_file = target / ".env"
    if env_example.is_file() and not env_file.is_file():
        env_file.write_bytes(env_example.read_bytes())

    result = {"manifest": manifest, "restored": target}
    if run_smoke:
        smoke = subprocess.run(
            [sys.executable, "-m", "socialai.cli", "--smoke"],
            cwd=str(target), capture_output=True, text=True, timeout=60,
        )
        result["smoke"] = {"ok": smoke.returncode == 0, "output": smoke.stdout + smoke.stderr}
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    bundle = None
    target = Path(".")
    if "--bundle" in argv:
        bundle = argv[argv.index("--bundle") + 1]
    elif "BUNDLE" in os.environ:
        bundle = os.environ["BUNDLE"]
    if "--target" in argv:
        target = Path(argv[argv.index("--target") + 1])
    if "--no-smoke" in argv:
        run_smoke = False
    else:
        run_smoke = True
    if not bundle:
        bundle = _latest_bundle()
    if not bundle:
        print("no bundle specified (use --bundle <zip> or BUNDLE=<zip>)", file=sys.stderr)
        return 1
    try:
        result = restore_bundle(Path(bundle), target, run_smoke=run_smoke)
    except ValueError as exc:
        print(f"restore failed: {exc}", file=sys.stderr)
        return 1
    print(f"restored into {result['restored']}")
    if "smoke" in result:
        ok = result["smoke"]["ok"]
        print(f"smoke: {'OK' if ok else 'FAILED'}")
        return 0 if ok else 1
    print("next: run `make smoke` to confirm the machine is operational")
    return 0


def _latest_bundle() -> str | None:
    try:
        zips = sorted(Path(".").glob("socialai-backup-*.zip"), key=lambda p: p.stat().st_mtime)
    except OSError:
        zips = []
    return str(zips[-1]) if zips else None


if __name__ == "__main__":
    sys.exit(main())
