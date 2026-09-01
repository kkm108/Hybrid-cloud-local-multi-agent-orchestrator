"""T03: Local LLM service tests (§5, §6)."""

import pytest
from fastapi.testclient import TestClient

from socialai.local_llm.backend import MockBackend
from socialai.local_llm.service import ack_ok, config_echo, create_app


@pytest.fixture
def backend() -> MockBackend:
    return MockBackend()


def test_status_ack_format(backend: MockBackend) -> None:
    app = create_app(backend, component_id="local_1")
    with TestClient(app) as c:
        r = c.get("/status")
        assert r.status_code == 200
        data = r.json()
        assert data["component_id"] == "local_1"
        assert "[local_1 GET_STATUS OK]" in data["ack"]
        assert "📊 Current Config: local_1 Config" in data["ack"]
        assert "(Model: mock | Device: cpu |" in data["ack"]
        assert "MaxTokens: 512 |" in data["ack"]


def test_status_defaults(backend: MockBackend) -> None:
    assert backend.config["temperature"] == 0.7
    assert backend.config["top_p"] == 0.9
    assert backend.config["top_k"] == 50
    assert backend.config["max_tokens"] == 512
    assert backend.config["repetition_penalty"] == 1.0


def test_config_mutation(backend: MockBackend) -> None:
    app = create_app(backend, component_id="local_1")
    with TestClient(app) as c:
        r = c.post("/config", json={"key": "TEMPERATURE", "value": 0.2})
        assert r.status_code == 200
        data = r.json()
        assert "[local_1 UPDATE_CONFIG OK]" in data["ack"]
        assert backend.config["temperature"] == 0.2
        assert "Temp: 0.2" in data["ack"]


def test_config_unknown_key_rejected(backend: MockBackend) -> None:
    with pytest.raises(KeyError):
        backend.update_config("NOPE", 1)
    # The config api returns an error rather than silently applying garbage.
    app = create_app(backend, component_id="local_1")
    with TestClient(app) as c:
        r = c.post("/config", json={"key": "NOPE", "value": 1})
        assert r.status_code == 422


def test_system_prompt_persists(backend: MockBackend) -> None:
    app = create_app(backend, component_id="local_1")
    with TestClient(app) as c:
        r = c.post("/system", json={"system_prompt": "answer as a poet"})
        assert r.status_code == 200
        data = r.json()
        assert "[local_1 SET_SYSTEM_INSTRUCTION OK]" in data["ack"]
        assert backend.config["system_prompt"] == "answer as a poet"


def test_generate_mock(backend: MockBackend) -> None:
    app = create_app(backend, component_id="local_1")
    with TestClient(app) as c:
        r = c.post("/generate", json={"prompt": "hello"})
        assert r.status_code == 200
        data = r.json()
        assert data["prompt"] == "hello"
        assert data["completion"] == "mock-reply:hello"


def test_generate_missing_prompt_422(backend: MockBackend) -> None:
    app = create_app(backend, component_id="local_1")
    with TestClient(app) as c:
        r = c.post("/generate", json={})
        assert r.status_code == 422


def test_ack_ok_and_echo_helpers(backend: MockBackend) -> None:
    ack = ack_ok("w", "GET_STATUS", backend.config)
    echo = config_echo("w", backend.config)
    assert ack.startswith("✅ [w GET_STATUS OK]")
    assert "📊 Current Config: w Config" in echo
