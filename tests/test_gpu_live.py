"""T13: Live GPU inference validation test (``gpu`` marker, manual only).

Skips gracefully when torch/transformers are absent so default CI stays green.
Exercises the real TransformersBackend: device resolution (CUDA or CPU
fallback §6) and a /generate round-trip. Uses the HF cache (the model is
downloaded once by ``scripts/gpu_check.py``).
"""

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")  # noqa: F401

pytestmark = pytest.mark.gpu

from fastapi.testclient import TestClient  # noqa: E402

from socialai.local_llm.backend import TransformersBackend  # noqa: E402
from socialai.local_llm.service import config_echo, create_app  # noqa: E402


def test_backend_resolves_device_and_generates() -> None:
    cuda = torch.cuda.is_available()
    backend = TransformersBackend({"model": "Qwen/Qwen2.5-0.5B-Instruct"})
    backend._ensure_loaded()
    expected = "cuda" if cuda else "cpu"
    assert backend.config["device"] == expected

    app = create_app(backend, component_id="gpu_check")
    with TestClient(app) as c:
        status = c.get("/status")
        assert status.status_code == 200
        assert config_echo("gpu_check", backend.config) in status.json()["ack"]

        gen = c.post("/generate", json={"prompt": "Hello! "})
        assert gen.status_code == 200
        assert gen.json()["completion"]
