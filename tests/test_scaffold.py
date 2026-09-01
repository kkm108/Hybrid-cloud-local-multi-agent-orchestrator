"""T01: Scaffold & toolchain checks.

Verifies repo layout (§3), package importability, and that the
standing contracts (AGENTS.md, TASKS.md, CLAUDE.md is absent for now)
are left untouched.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_package_importable() -> None:
    import socialai  # noqa: F401


def test_scaffold_modules_importable() -> None:
    import socialai.actuators.facebook  # noqa: F401
    import socialai.cli  # noqa: F401
    import socialai.local_llm.backend  # noqa: F401
    import socialai.local_llm.service  # noqa: F401
    import socialai.local_llm.spawn  # noqa: F401
    import socialai.orchestrator.app  # noqa: F401
    import socialai.orchestrator.campaigns  # noqa: F401
    import socialai.orchestrator.components  # noqa: F401
    import socialai.orchestrator.relay  # noqa: F401
    import socialai.protocol  # noqa: F401
    import socialai.router  # noqa: F401
    import socialai.state  # noqa: F401
    import socialai.workers.bridge  # noqa: F401
    import socialai.workers.mock  # noqa: F401
    import socialai.workers.playwright_adapter  # noqa: F401


REQUIRED_DIRS = [
    "schemas",
    "manifests",
    "socialai/orchestrator",
    "socialai/local_llm",
    "socialai/workers",
    "socialai/actuators",
    "socialai/web",
    "scripts",
    "state",
    "tests",
    "tests/fixtures",
]


@pytest.mark.parametrize("rel", REQUIRED_DIRS)
def test_directory_exists(rel: str) -> None:
    assert (ROOT / rel).is_dir(), f"missing directory: {rel}"


REQUIRED_FILES = [
    "AGENTS.md",
    "TASKS.md",
    "Makefile",
    "pyproject.toml",
    ".env.example",
    "schemas/manifest.schema.json",
    "socialai/protocol.py",
    "socialai/router.py",
    "socialai/state.py",
    "socialai/cli.py",
    "socialai/web/index.html",
    "socialai/web/app.js",
    "socialai/web/styles.css",
]


@pytest.mark.parametrize("rel", REQUIRED_FILES)
def test_file_exists(rel: str) -> None:
    assert (ROOT / rel).is_file(), f"missing file: {rel}"


def test_contracts_untouched() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    tasks = (ROOT / "TASKS.md").read_text(encoding="utf-8")
    assert "Purpose" in agents
    assert "## 1. Purpose" in agents
    assert "T01 Scaffold & toolchain" in tasks
    assert "Deps: —" in tasks


def test_env_example_secrets() -> None:
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "HF_TOKEN=" in env
    assert "SOCIALAI_LIVE=0" in env
    # No real secrets ever allowed in the example.
    assert "sk-" not in env
    assert "Bearer" not in env


def test_sofiscan_schema_present() -> None:
    schema = (ROOT / "schemas" / "manifest.schema.json").read_text(encoding="utf-8")
    assert "name" in schema
