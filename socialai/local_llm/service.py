"""Local LLM service endpoints (§6, port 81xx).

    GET  /status                          -> ack config echo (§5)
    POST /config  {key, value}            -> UPDATE_CONFIG semantics
    POST /system  {system_prompt}         -> SET_SYSTEM_INSTRUCTION
    POST /generate {prompt}               -> completion

Runnable standalone::

    python -m socialai.local_llm.service --mock --port 8100
"""

from __future__ import annotations

import argparse
import sys

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .backend import VERB_TO_KEY, LLMBackend, MockBackend, TransformersBackend

DEFAULT_ID = "local_1"


class ConfigIn(BaseModel):
    key: str
    value: str | int | float


class SystemIn(BaseModel):
    system_prompt: str


class GenerateIn(BaseModel):
    prompt: str


def config_echo(component_id: str, config: dict) -> str:
    """Build the canonical §5 config-echo string."""
    return (
        f"📊 Current Config: {component_id} Config "
        f"(Model: {config['model']} | Device: {config['device']} | "
        f"Temp: {config['temperature']} | MaxTokens: {config['max_tokens']} | "
        f"TopP: {config['top_p']} | TopK: {config['top_k']} | "
        f"RepetitionPenalty: {config['repetition_penalty']})"
    )


def ack_ok(component_id: str, action: str, config: dict) -> str:
    """Full success ack: ``✅ [...] OK`` followed by the config echo (§5)."""
    return f"✅ [{component_id} {action} OK]" + "\n" + config_echo(component_id, config)


def create_app(backend: LLMBackend, component_id: str = DEFAULT_ID) -> FastAPI:
    app = FastAPI(title="SocialAI Local LLM", version="0.1.0")

    @app.get("/status")
    def status() -> dict:
        return {
            "component_id": component_id,
            "ack": ack_ok(component_id, "GET_STATUS", backend.config),
            "echo": config_echo(component_id, backend.config),
            "config": backend.config,
        }

    @app.post("/config")
    def set_config(body: ConfigIn) -> dict:
        key = VERB_TO_KEY.get(body.key.upper(), body.key)
        try:
            backend.update_config(key, body.value)
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"unknown config key: {body.key}") from exc
        return {
            "component_id": component_id,
            "ack": ack_ok(component_id, "UPDATE_CONFIG", backend.config),
            "config": backend.config,
        }

    @app.post("/system")
    def set_system(body: SystemIn) -> dict:
        backend.update_config("system_prompt", body.system_prompt)
        return {
            "component_id": component_id,
            "ack": ack_ok(component_id, "SET_SYSTEM_INSTRUCTION", backend.config),
            "config": backend.config,
        }

    @app.post("/generate")
    def generate(body: GenerateIn) -> dict:
        try:
            completion = backend.generate(body.prompt)
        except Exception as exc:  # noqa: BLE001 - surface as 500
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"prompt": body.prompt, "completion": completion}

    return app


def make_backend(kind: str, model: str) -> LLMBackend:
    if kind == "transformers":
        return TransformersBackend({"model": model})
    return MockBackend({"model": model})


def main() -> None:
    parser = argparse.ArgumentParser(prog="local_llm.service")
    parser.add_argument("--mock", action="store_true", help="use MockBackend")
    parser.add_argument("--transformers", action="store_true", help="use TransformersBackend")
    parser.add_argument("--model", default="mock", help="HF model id (transformers)")
    parser.add_argument("--id", default=DEFAULT_ID, help="component id")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    kind = "transformers" if args.transformers and not args.mock else "mock"
    backend = make_backend(kind, args.model)

    import uvicorn  # noqa: PLC0415

    app = create_app(backend, args.id)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    sys.exit(main())
