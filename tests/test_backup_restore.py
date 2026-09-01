"""T11: Backup / restore / portability tests (§12)."""

import json
import zipfile
from pathlib import Path

import pytest

from scripts.backup import build_bundle, redact_secrets, sanitize_routing
from scripts.restore import restore_bundle, verify_manifest


def _seed_project(root: Path) -> None:
    (root / "manifests").mkdir(parents=True, exist_ok=True)
    (root / "schemas").mkdir(parents=True, exist_ok=True)
    (root / "state" / "logs").mkdir(parents=True, exist_ok=True)
    (root / "outbox").mkdir(parents=True, exist_ok=True)

    (root / "AGENTS.md").write_text("# AGENTS\nstanding contract", encoding="utf-8")
    (root / "TASKS.md").write_text("# TASKS\none at a time", encoding="utf-8")
    (root / "CLAUDE.md").write_text("# CLAUDE\nguide", encoding="utf-8")
    (root / ".env.example").write_text("HF_TOKEN=sk-REPLACE_ME\n", encoding="utf-8")
    (root / ".env").write_text("HF_TOKEN=sk-SUPERSECRET123\n", encoding="utf-8")
    (root / "manifests" / "simpleagent.json").write_text(
        json.dumps({"name": "simpleagent"}), encoding="utf-8"
    )
    (root / "schemas" / "manifest.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    (root / "state" / "PROJECT_STATE.json").write_text(
        json.dumps({"campaign": {"name": "simpleagent"}, "components": {"deepseek_1": "IDLE"}}),
        encoding="utf-8",
    )
    (root / "state" / "ports.json").write_text("{}", encoding="utf-8")
    secret_log = (
        '{"ts":1,"to":"x","reply":"sk-AABBCCDDEEFF001122334455"}\n'
        '{"ts":2,"to":"y","text":"Bearer abcdef1234567890xyz"}\n'
    )
    (root / "state" / "logs" / "routing.jsonl").write_text(secret_log, encoding="utf-8")
    (root / "outbox" / "should_not_appear.json").write_text("{}", encoding="utf-8")


class TestBackupBundle:
    def test_bundle_excludes_env_and_outbox(self, tmp_path) -> None:
        src = tmp_path / "src"
        _seed_project(src)
        zip_path = build_bundle(src, tmp_path / "out", mode="restore")
        assert zip_path.is_file() and zip_path.name.startswith("socialai-backup-")
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        assert ".env" not in names and not any(n == ".env" or n.startswith(".env/") for n in names)
        assert not any("outbox" in n for n in names)
        assert "state/PROJECT_STATE.json" in names
        assert "state/ports.json" in names
        assert "BUNDLE.json" in names
        assert "SNAPSHOT.md" in names

    def test_bundle_distinguishes_consult(self, tmp_path) -> None:
        src = tmp_path / "src"
        _seed_project(src)
        zip_path = build_bundle(src, tmp_path / "out", mode="consult")
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        assert "CONSULT.md" in names
        # Non-git environment => bundle fallback note present instead of patch.
        assert "GIT_BUNDLE_NOTE.txt" in names or "diff.patch" in names
        assert "state/PROJECT_STATE.json" in names


class TestRedaction:
    def test_redact_secrets(self) -> None:
        text = "key=sk-AABBCCDDEEFF001122334455 and Bearer tok1234567890x"
        out = redact_secrets(text)
        assert "sk-AABBCCDDEEFF" not in out
        assert "[REDACTED]" in out

    def test_routing_log_sanitized(self, tmp_path) -> None:
        src = tmp_path / "src"
        _seed_project(src)
        data = sanitize_routing(src / "state" / "logs" / "routing.jsonl")
        assert b"sk-AABBCCDDEEFF" not in data
        assert b"[REDACTED]" in data

    def test_routing_tail_capped(self, tmp_path) -> None:
        log = tmp_path / "routing.jsonl"
        log.write_text("\n".join(f"line{i}" for i in range(2050)) + "\n", encoding="utf-8")
        data = sanitize_routing(log).decode("utf-8")
        lines = data.strip().splitlines()
        assert len(lines) == 2000
        assert lines[0] == "line50"  # the most recent 2000 lines retained


class TestRestore:
    def test_roundtrip_restore_and_smoke(self, tmp_path) -> None:
        src = tmp_path / "src"
        _seed_project(src)
        zip_path = build_bundle(src, tmp_path / "out", mode="restore")
        assert verify_manifest(zip_path)

        target = tmp_path / "target"
        result = restore_bundle(zip_path, target, run_smoke=True)
        assert (target / "state" / "PROJECT_STATE.json").is_file()
        assert (target / "manifests" / "simpleagent.json").is_file()
        # .env recreated from .env.example (canonical placeholder, not the secret).
        env = (target / ".env").read_text(encoding="utf-8")
        assert "sk-SUPERSECRET123" not in env
        assert "REPLACE_ME" in env
        # outbox never restored.
        assert not (target / "outbox").exists()
        assert result["smoke"]["ok"] is True

    def test_restore_detects_tamper(self, tmp_path) -> None:
        src = tmp_path / "src"
        _seed_project(src)
        zip_path = build_bundle(src, tmp_path / "out", mode="restore")
        # Rewrite the whole zip with one bundled file tampered (manifest intact).
        tampered = tmp_path / "tampered.zip"
        with zipfile.ZipFile(zip_path) as zfin, zipfile.ZipFile(tampered, "w") as zfout:
            for info in zfin.infolist():
                data = zfin.read(info.filename)
                if info.filename == "manifests/simpleagent.json":
                    data = b'{"name":"tampered"}'
                zfout.writestr(info, data)
        with pytest.raises(ValueError, match="checksum mismatch"):
            verify_manifest(tampered)
