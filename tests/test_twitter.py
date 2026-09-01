"""T19: Twitter/X actuator tests (§11, dry-run first, shared safety gate)."""

import json
import pathlib

import pytest

from socialai.actuators.facebook import (
    assert_live_authorized as facebook_assert_live_authorized,
)
from socialai.actuators.safety import ActuatorError, assert_live_authorized
from socialai.actuators.twitter import TwitterActuator


@pytest.fixture
def outbox(tmp_path) -> pathlib.Path:
    return tmp_path / "outbox"


class TestSharedGate:
    def test_both_actuators_share_the_exact_same_gate(self) -> None:
        assert assert_live_authorized is facebook_assert_live_authorized
        source = pathlib.Path(
            __import__("socialai.actuators.twitter", fromlist=["twitter"]).__file__
        ).read_text(encoding="utf-8")
        assert "assert_live_authorized(confirm)" in source


class TestDryRun:
    def test_dry_run_writes_payload(self, outbox) -> None:
        a = TwitterActuator(mode="dry_run", outbox_dir=outbox)
        a.compose("Posting from SocialAI", image_ref="img/x_poster.png")
        a.type("Posting from SocialAI")
        a.attach("img/x_poster.png")
        result = a.post()
        assert result["platform"] == "twitter"
        assert result["mode"] == "dry_run"
        assert result["posted"] is False
        assert result["text"] == "Posting from SocialAI"
        assert result["image_ref"] == "img/x_poster.png"
        files = list(outbox.glob("*.json"))
        assert len(files) == 1
        saved = json.loads(files[0].read_text(encoding="utf-8"))
        assert saved["text"] == "Posting from SocialAI"
        assert saved["posted"] is False

    def test_dry_run_records_steps(self, outbox) -> None:
        a = TwitterActuator(mode="dry_run", outbox_dir=outbox)
        a.compose("x")
        a.type("x")
        a.attach()
        a.post()
        step_names = [s["step"].value for s in a.steps]
        assert step_names == ["compose", "type", "attach", "post"]

    def test_invalid_mode_rejected(self, outbox) -> None:
        with pytest.raises(ValueError):
            TwitterActuator(mode="teleport", outbox_dir=outbox)


class TestNoNetworkInDryRun:
    def test_network_import_only_inside_live_method(self) -> None:
        source = pathlib.Path(
            __import__("socialai.actuators.twitter", fromlist=["twitter"]).__file__
        ).read_text(encoding="utf-8")
        # Socket/HTTP imports may only appear inside the live method (indented),
        # never at module scope (column 0), per §11's network-free dry-run path.
        top_level = [
            line for line in source.splitlines()
            if line and not line[0].isspace() and not line.startswith(("from ", "import "))
        ]
        joined_top = "\n".join(top_level)
        for banned in ("import httpx", "import requests", "import urllib", "import socket"):
            assert banned not in joined_top
        # And wherever a network import does exist, it must be indented (in a method).
        for line in source.splitlines():
            if "import httpx" in line:
                assert line[0].isspace()

    def test_dry_run_makes_no_imports(self, monkeypatch, outbox) -> None:
        def trap(*args, **kwargs):
            raise AssertionError("dry-run must not import networking")

        monkeypatch.setattr("builtins.__import__", trap)
        a = TwitterActuator(mode="dry_run", outbox_dir=outbox)
        a.compose("no network here")
        a.post()
        files = list(outbox.glob("*.json"))
        assert len(files) == 1


class TestLiveGate:
    def test_live_without_env_raises(self, monkeypatch, outbox) -> None:
        monkeypatch.delenv("SOCIALAI_LIVE", raising=False)
        a = TwitterActuator(mode="live", outbox_dir=outbox)
        a.compose("x")
        with pytest.raises(ActuatorError, match="SOCIALAI_LIVE"):
            a.post(confirm="tok")

    def test_live_without_confirm_raises(self, monkeypatch, outbox) -> None:
        monkeypatch.setenv("SOCIALAI_LIVE", "1")
        a = TwitterActuator(mode="live", outbox_dir=outbox)
        a.compose("x")
        with pytest.raises(ActuatorError, match="confirm token"):
            a.post(confirm=None)

    def test_live_with_env_and_confirm_posts(self, monkeypatch, outbox) -> None:
        monkeypatch.setenv("SOCIALAI_LIVE", "1")
        a = TwitterActuator(mode="live", outbox_dir=outbox)
        a.compose("x")
        result = a.post(confirm="tok")
        assert result["posted"] is True
        # Live must not write an outbox file (real post path).
        assert list(outbox.glob("*.json")) == []
