"""T14: Worker-tab attach doctor tests (never-send preflight, not live)."""

import os
from pathlib import Path

import pytest

from scripts.tab_doctor import (
    REQUIRED_SELECTORS,
    default_attach,
    dir_size,
    main,
    profile_lock_held,
)
from socialai.workers.playwright_adapter import PlaywrightAdapter


def _fake_profile(tmp_path: Path, locked: bool = False) -> Path:
    profile = tmp_path / "Default"
    profile.mkdir(parents=True)
    (profile / "Preferences").write_text("{}", encoding="utf-8")
    if locked:
        (profile / "SingletonLock").write_text("0000", encoding="utf-8")
    return profile


class TestLiveGate:
    def test_refuses_without_live(self, monkeypatch) -> None:
        monkeypatch.delenv("SOCIALAI_LIVE", raising=False)
        assert main(["--vendor", "deepseek"]) == 1

    def test_allows_with_live_flag(self, tmp_path) -> None:
        profile = _fake_profile(tmp_path)
        seen: list[str] = []

        def fake_attach(vendor: str, profile_dir: Path) -> int:
            seen.append(vendor)
            return 0

        assert main(
            ["--live", "--vendor", "deepseek", "--profile", str(profile)],
            attach_fn=fake_attach,
            running_probe=lambda _: False,
        ) == 0
        assert seen == ["deepseek"]

    def test_allows_with_env(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SOCIALAI_LIVE", "1")
        profile = _fake_profile(tmp_path)
        assert main(
            ["--vendor", "deepseek", "--profile", str(profile)],
            attach_fn=lambda _v, _p: 0,
            running_probe=lambda _: False,
        ) == 0


class TestLockPreflight:
    def test_exits_2_when_brave_running(self, tmp_path) -> None:
        profile = _fake_profile(tmp_path)
        assert main(
            ["--live", "--vendor", "deepseek", "--profile", str(profile)],
            running_probe=lambda _: True,
            lock_probe=lambda _: False,
        ) == 2

    def test_exits_2_when_lock_held(self, tmp_path, capsys) -> None:
        profile = _fake_profile(tmp_path, locked=True)
        assert main(
            ["--live", "--vendor", "deepseek", "--profile", str(profile)],
            running_probe=lambda _: False,
        ) == 2
        assert "Brave is running; close it or use --profile-copy" in capsys.readouterr().err

    def test_lock_held_detects_lock_files(self, tmp_path) -> None:
        locked = _fake_profile(tmp_path / "locked", locked=True)
        assert profile_lock_held(locked) is True
        free = _fake_profile(tmp_path / "free", locked=False)
        assert profile_lock_held(free) is False


class TestProfileCopy:
    def test_copies_strips_locks_and_attaches_to_copy(self, tmp_path) -> None:
        profile = _fake_profile(tmp_path, locked=True)
        attached_to: list[str] = []

        def fake_attach(vendor: str, profile_dir: Path) -> int:
            attached_to.append(str(profile_dir))
            return 0

        assert main(
            ["--live", "--vendor", "deepseek", "--profile", str(profile),
             "--profile-copy", "--yes"],
            attach_fn=fake_attach,
        ) == 0
        assert attached_to, "attach must be called on the copied profile"
        copy = Path(attached_to[0])
        assert copy != profile
        assert (copy / "Preferences").is_file(), "copy must carry profile files"
        assert not (copy / "SingletonLock").exists(), "locks must be stripped"
        assert profile_lock_held(copy) is False

    def test_requires_yes(self, tmp_path) -> None:
        profile = _fake_profile(tmp_path)
        assert main(
            ["--live", "--profile", str(profile), "--profile-copy"],
            attach_fn=lambda _v, _p: 0,
        ) == 3

    def test_reports_size_estimate(self, tmp_path, capsys) -> None:
        profile = _fake_profile(tmp_path)
        (profile / "blob").write_text("x" * 2048, encoding="utf-8")
        assert dir_size(profile) >= 2048
        main(
            ["--live", "--profile", str(profile), "--profile-copy", "--yes"],
            attach_fn=lambda _v, _p: 0,
        )
        assert "size estimate" in capsys.readouterr().out


class TestAttach:
    def test_all_selectors_load_for_every_vendor(self) -> None:
        for vendor in ("deepseek", "gemini", "chatgpt"):
            adapter = PlaywrightAdapter("doctor", vendor)
            for key in REQUIRED_SELECTORS:
                assert adapter.selectors.get(key), (vendor, key)

    def test_missing_selector_rejected(self, tmp_path) -> None:
        profile = _fake_profile(tmp_path)
        assert main(
            ["--live", "--vendor", "deepseek", "--profile", str(profile)],
            attach_fn=default_attach,
            running_probe=lambda _: False,
        ) == 0

    def test_reports_heartbeat_idle(self, tmp_path, capsys) -> None:
        profile = _fake_profile(tmp_path)
        assert main(
            ["--live", "--vendor", "chatgpt", "--profile", str(profile)],
            attach_fn=default_attach,
            running_probe=lambda _: False,
        ) == 0
        assert "heartbeat: IDLE" in capsys.readouterr().out


class TestNeverSend:
    def test_source_has_no_click_path(self) -> None:
        src = (Path(__file__).resolve().parent.parent / "scripts" / "tab_doctor.py")
        body = src.read_text(encoding="utf-8")
        assert ".click(" not in body, "doctor must never click"
        assert "_send_impl" not in body, "doctor must never send"


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("SOCIALAI_LIVE") != "1",
    reason="SOCIALAI_LIVE != 1 (real attach only under live env)",
)
def test_real_attach_live(tmp_path) -> None:
    """Real attach test — live-marked, skipped unless SOCIALAI_LIVE=1."""
    pytest.importorskip("playwright")
    profile = _fake_profile(tmp_path)
    assert main(
        ["--vendor", "deepseek", "--profile", str(profile)],
    ) == 0
