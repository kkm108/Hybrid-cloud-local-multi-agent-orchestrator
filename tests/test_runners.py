"""T16: Windows runner (make.ps1) parity tests — §13 target mapping."""

import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
MAKE_PS1 = SCRIPTS / "make.ps1"
PWSH = "powershell"

EXPECTED = {
    "test": 'python -m pytest -q -m "not gpu and not live and not ui"',
    "lint": "python -m ruff check .",
    "smoke": "python -m socialai.cli --smoke",
    "backup": "python scripts/backup.py --mode restore",
    "consult": "python scripts/backup.py --mode consult",
    "restore": "python scripts/restore.py --bundle sample-backup.zip",
}


def _dry_run(*args: str) -> str:
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(MAKE_PS1), "--dry-run", *args],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_runner_files_exist() -> None:
    assert MAKE_PS1.is_file()
    assert (SCRIPTS / "make.cmd").is_file()


@pytest.mark.parametrize("target", list(EXPECTED))
def test_dry_run_maps_target(target: str) -> None:
    args: tuple[str, ...] = ("--BUNDLE", "sample-backup.zip") if target == "restore" else ()
    out = _dry_run(target, *args)
    assert EXPECTED[target] in out, out


def test_dry_run_accepts_make_style_bundle() -> None:
    out = _dry_run("restore", "BUNDLE=sample-backup.zip")
    assert EXPECTED["restore"] in out, out


def test_unknown_target_exits_2() -> None:
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(MAKE_PS1), "--dry-run", "bogus"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_restore_without_bundle_exits_2() -> None:
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(MAKE_PS1), "--dry-run", "restore"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "BUNDLE" in proc.stdout


def test_real_lint_run_exits_zero() -> None:
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(MAKE_PS1), "lint"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "> python -m ruff check ." in proc.stdout
