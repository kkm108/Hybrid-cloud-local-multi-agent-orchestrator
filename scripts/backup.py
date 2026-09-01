"""SocialAI backup bundle builder (§12).

Produces ``socialai-backup-<UTC>.zip`` in two modes:

* ``restore``  – operational bundle for restoring a working machine.
* ``consult``  – advisory bundle: adds CONSULT.md, a git diff patch (or a
  ``git bundle`` fallback note), and trimmed chat logs.

The bundle never contains ``.env`` or ``outbox/``. Routing logs are sanitized
(secrets redacted, tail ≤ 2000 lines).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0.0"
LOG_TAIL_LINES = 2000

# Secret-ish patterns redacted from any text placed in a bundle.
SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{8,})", re.I),
    re.compile(r"(Bearer\s+[A-Za-z0-9._\-]{8,})", re.I),
    re.compile(r"(HF_TOKEN[=:]\s*\S+)", re.I),
    re.compile(r"(api[_-]?key[=:]\s*\S+)", re.I),
    re.compile(r"(token[=:]\s*[A-Za-z0-9._\-]{12,})", re.I),
]

NEVER_BUNDLED = {".env", "outbox", ".git"}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def bundle_name(mode: str) -> str:
    return f"socialai-backup-{utc_stamp()}.zip"


def redact_secrets(text: str) -> str:
    for pat in SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_routing(path: Path) -> bytes:
    """Return ≤ LOG_TAIL_LINES sanitized lines of the routing log."""
    if not path.is_file():
        return b""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-LOG_TAIL_LINES:]
    redacted = [redact_secrets(line) for line in tail]
    return ("\n".join(redacted) + "\n").encode("utf-8")


def make_snapshot(root: Path) -> str:
    """SNAPSHOT.md: running campaign, component statuses, versions."""
    snap = ["# SocialAI Snapshot", "", f"Generated: {utc_stamp()} (UTC)", ""]
    state_file = root / "state" / "PROJECT_STATE.json"
    campaign = "none"
    components = []
    if state_file.is_file():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            campaign = data.get("campaign", {}).get("name", "none")
            components = list(data.get("components", {}).keys())
        except (json.JSONDecodeError, AttributeError):
            pass
    snap.append(f"Running campaign: {campaign}")
    snap.append("Components: " + (", ".join(sorted(components)) if components else "none"))
    snap.append("")
    snap.append("Versions:")
    for name in ("python",):
        try:
            ver = subprocess.run(
                [name, "--version"], capture_output=True, text=True, timeout=10
            ).stdout.strip()
            snap.append(f"- {ver}")
        except Exception:  # noqa: BLE001
            pass
    snap.append("")
    return "\n".join(snap)


def _git_rev(root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def make_bundle_json(root: Path, mode: str, sha_map: dict[str, str]) -> str:
    payload = {
        "mode": mode,
        "schema_version": SCHEMA_VERSION,
        "git_rev": _git_rev(root),
        "ts": utc_stamp(),
        "sha256_manifest": sha_map,
    }
    return json.dumps(payload, indent=2) + "\n"


def _gather_entries(root: Path, mode: str) -> list[tuple[str, bytes]]:
    """Return [(arcname, content_bytes), ...] for every bundled file."""
    entries: list[tuple[str, bytes]] = []

    def add(text_path: Path, arcname: str) -> None:
        if text_path.is_file():
            entries.append((arcname, text_path.read_bytes()))

    add(root / "AGENTS.md", "AGENTS.md")
    add(root / "TASKS.md", "TASKS.md")
    add(root / "CLAUDE.md", "CLAUDE.md")
    add(root / ".env.example", ".env.example")

    for sub in ("manifests", "schemas"):
        base = root / sub
        if base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    entries.append((f"{sub}/{p.relative_to(base).as_posix()}", p.read_bytes()))

    for fname in ("PROJECT_STATE.json", "ports.json"):
        add(root / "state" / fname, f"state/{fname}")

    routing = sanitize_routing(root / "state" / "logs" / "routing.jsonl")
    entries.append(("state/logs/routing.jsonl", routing))

    if mode == "consult":
        consult = _make_consult(root)
        entries.append(("CONSULT.md", consult[0].encode("utf-8")))
        for arcname, data in consult[1]:
            entries.append((arcname, data))

    entries.append(("SNAPSHOT.md", make_snapshot(root).encode("utf-8")))

    # BUNDLE.json manifest covers everything except itself.
    sha_map = {a: _sha256(b) for a, b in entries}
    entries.append(("BUNDLE.json", make_bundle_json(root, mode, sha_map).encode("utf-8")))
    return entries

    if mode == "consult":
        consult = _make_consult(root)
        entries.append(("CONSULT.md", consult[0].encode("utf-8")))
        for arcname, data in consult[1]:
            entries.append((arcname, data))

    return entries


def _make_consult(root: Path) -> tuple[str, list[tuple[str, bytes]]]:
    """CONSULT.md plus git diff patch (or bundle fallback note) + chat logs."""
    extras: list[tuple[str, bytes]] = []
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "log", "--oneline", "-1", "--format=%H"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            diff = subprocess.run(
                ["git", "-C", str(root), "diff", "HEAD"],
                capture_output=True, text=True, timeout=30,
            ).stdout
            if diff.strip():
                extras.append(("diff.patch", diff.encode("utf-8")))
            body = (
                "# Consult\n\n"
                "Includes CONSULT.md, git diff patch, sanitized routing log tail.\n"
            )
            return body, extras
    except Exception:  # noqa: BLE001
        pass
    extras.append(
        ("GIT_BUNDLE_NOTE.txt", b"Not a git repository; git diff unavailable.\n")
    )
    return "# Consult\n\nGit not available; see GIT_BUNDLE_NOTE.txt.\n", extras


def build_bundle(root: Path, out_dir: Path, mode: str = "restore") -> Path:
    if mode not in ("restore", "consult"):
        raise ValueError(f"mode must be 'restore' or 'consult', got {mode!r}")
    root = root.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / bundle_name(mode)
    entries = _gather_entries(root, mode)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in entries:
            zf.writestr(arcname, data)
    return out_path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = "restore"
    out_dir = Path(".")
    if "--mode" in argv:
        i = argv.index("--mode")
        mode = argv[i + 1] if i + 1 < len(argv) else "restore"
    if "--out" in argv:
        i = argv.index("--out")
        out_dir = Path(argv[i + 1]) if i + 1 < len(argv) else Path(".")
    root = Path(os.getcwd())
    path = build_bundle(root, out_dir, mode)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
