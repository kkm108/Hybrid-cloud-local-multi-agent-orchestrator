"""T13: Live GPU inference validation.

Spawns a real ``TransformersBackend`` against an HF model, asserts the device
choice (CUDA when available, else warn + CPU fallback §6), round-trips
``/status`` and ``/generate`` through the service app, and prints the §5
config echo verbatim plus timing numbers.
"""

from __future__ import annotations

import argparse
import sys
import time

from fastapi.testclient import TestClient

from socialai.local_llm.backend import TransformersBackend
from socialai.local_llm.service import config_echo, create_app

DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gpu_check")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="HF model id")
    args = parser.parse_args(argv)

    try:
        import torch  # noqa: F401
    except ImportError:
        print("torch not installed (install extra `gpu`); aborting", file=sys.stderr)
        return 2

    cuda = torch.cuda.is_available()
    if cuda:
        print(f"torch {torch.__version__} | CUDA available -> Device: CUDA")
    else:
        print(
            f"torch {torch.__version__} | CUDA NOT available -> warn + "
            "CPU fallback (§6)"
        )

    backend = TransformersBackend({"model": args.model})

    t0 = time.perf_counter()
    backend._ensure_loaded()
    load_s = time.perf_counter() - t0

    expected = "cuda" if cuda else "cpu"
    assert backend.config["device"] == expected, (
        f"device mismatch: {backend.config['device']} != {expected}"
    )
    print(f"Device: {backend.config['device']}")
    print(f"weight-load: {load_s:.2f} s")
    print("config-echo: " + config_echo("gpu_check", backend.config))

    app = create_app(backend, component_id="gpu_check")
    with TestClient(app) as c:
        r = c.get("/status")
        assert r.status_code == 200, r.text
        print("status ack:", r.json()["echo"])

        c.post("/config", json={"key": "MAX_TOKENS", "value": 32})
        t1 = time.perf_counter()
        g = c.post("/generate", json={"prompt": "Hello! "})
        gen_s = time.perf_counter() - t1
        assert g.status_code == 200, g.text
        completion = g.json()["completion"]
        print(f"generate ({len(completion.split())} tokens): {gen_s:.2f} s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
