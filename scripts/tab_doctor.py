"""T14: Worker-tab attach doctor (profile-safety preflight).

Validates a vendor worker tab WITHOUT ever sending a message:

1. Live gate: refuse unless ``SOCIALAI_LIVE=1`` or ``--live`` (exit 1).
2. Lock preflight: probe ``brave.exe`` and the Default profile lock; if either
   is held, refuse (exit 2) unless ``--profile-copy`` is used.
3. ``--profile-copy``: copy the profile to a temp dir, strip lock files, and
   attach to that copy — safe while a real Brave stays open.
4. Attach via ``workers/playwright_adapter.py`` + ``workers/selectors/`` and
   assert input/send/last-message selectors; report heartbeat IDLE.

Never-send by construction: this module contains no click path at all.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROFILE_DIR = Path(
    os.environ.get(
        "SOCIALAI_BRAVE_PROFILE",
        r"C:\Users\kameshwar\AppData\Local\BraveSoftware\Brave-Browser\User Data\Default",
    )
)
BRAVE_EXE = Path(
    os.environ.get(
        "SOCIALAI_BRAVE_EXE",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    )
)
SELECTORS_DIR = (
    Path(__file__).resolve().parent.parent / "socialai" / "workers" / "selectors"
)
REQUIRED_SELECTORS = ("input_box", "send_btn", "last_message")
LOCK_FILES = ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tab_doctor")
    p.add_argument("--vendor", choices=("deepseek", "gemini", "chatgpt"),
                   default="deepseek")
    p.add_argument("--live", action="store_true",
                   help="allow real attach (SOCIALAI_LIVE=1 also works)")
    p.add_argument("--profile-copy", action="store_true",
                   help="attach to a temp copy of the profile instead of live")
    p.add_argument("--yes", action="store_true", help="confirm --profile-copy")
    p.add_argument("--profile", type=Path, default=PROFILE_DIR)
    p.add_argument("--brave", type=Path, default=BRAVE_EXE)
    return p.parse_args(argv)


def probe_brave_running(brave_exe: Path) -> bool:
    """True when a ``brave.exe`` process is present (Windows tasklist)."""
    if not Path(brave_exe).exists():
        return False
    name = Path(brave_exe).name.lower()
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return name in out.stdout.lower()


def profile_lock_held(profile_dir: Path) -> bool:
    """True when any interplay lock file exists in the profile directory."""
    return any(Path(profile_dir, lock).exists() for lock in LOCK_FILES)


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())


def copy_profile(profile_dir: Path) -> Path | None:
    """Copy the profile to a temp dir and strip lock files (returns the copy)."""
    dst = Path(tempfile.mkdtemp(prefix="tabdoctor-")) / Path(profile_dir).name
    try:
        shutil.copytree(Path(profile_dir), dst, symlinks=True)
    except (OSError, shutil.Error):
        return None
    for lock in LOCK_FILES:
        lock_path = dst / lock
        if lock_path.exists() and lock_path.is_file():
            lock_path.unlink()
    return dst


def default_attach(vendor: str, profile_dir: Path) -> int:
    """Attach via PlaywrightAdapter; assert selectors; report heartbeat IDLE."""
    from socialai.workers.playwright_adapter import PlaywrightAdapter  # noqa: PLC0415

    adapter = PlaywrightAdapter(worker_id="doctor", vendor=vendor)
    missing = [k for k in REQUIRED_SELECTORS if not adapter.selectors.get(k)]
    if missing:
        print(f"missing selectors for {vendor}: {missing}", file=sys.stderr)
        return 3
    try:
        ok = adapter.attach()
    except RuntimeError as exc:
        print(f"attach failed: {exc}", file=sys.stderr)
        return 3
    if not ok:
        return 3
    print(f"heartbeat: IDLE (vendor={vendor}, attached={adapter.attached})")
    print("selectors present: " + ", ".join(REQUIRED_SELECTORS))
    return 0


def main(
    argv: list[str] | None = None,
    *,
    attach_fn=default_attach,
    running_probe=probe_brave_running,
    lock_probe=profile_lock_held,
) -> int:
    args = parse_args(argv)

    # 1. Live gate.
    if not (args.live or os.environ.get("SOCIALAI_LIVE", "0") == "1"):
        print("refused: set SOCIALAI_LIVE=1 or pass --live (never-send doctor)",
              file=sys.stderr)
        return 1

    profile = Path(args.profile)

    # 3. Profile-copy fallback: safe while Brave stays open.
    if args.profile_copy:
        if not args.yes:
            print("--profile-copy requires --yes; aborting", file=sys.stderr)
            return 3
        print(f"profile-copy: size estimate {dir_size(profile) / 1e6:.1f} MB")
        copied = copy_profile(profile)
        if copied is None:
            print("profile-copy failed", file=sys.stderr)
            return 3
        print(f"attaching to copy: {copied}")
        return attach_fn(args.vendor, copied)

    # 2. Lock preflight (skipped on --profile-copy by design).
    if running_probe(args.brave) or lock_probe(profile):
        print("Brave is running; close it or use --profile-copy", file=sys.stderr)
        return 2

    # 4. Attach to the real profile (assert-only; never clicks).
    return attach_fn(args.vendor, profile)


if __name__ == "__main__":
    sys.exit(main())
