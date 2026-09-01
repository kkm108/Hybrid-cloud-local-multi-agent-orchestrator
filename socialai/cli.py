"""SocialAI CLI entry point.

``socialai --smoke`` performs a mock boot of the control-center app, hits
``/api/health`` and the kill switch, then exits (powers ``make smoke``).
Running ``socialai`` boots the real control plane on ``:3005``.
"""

from __future__ import annotations

import argparse
import sys


def _run_smoke() -> int:
    from fastapi.testclient import TestClient

    from socialai.orchestrator.app import build_app

    app = build_app()
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200, health.text
        assert health.json()["status"] == "ok"
        stop = client.post("/api/campaigns/stop")
        assert stop.status_code == 200, stop.text
    print("SocialAI smoke: OK (health + kill switch)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="socialai")
    parser.add_argument("--smoke", action="store_true", help="mock boot + health + stop")
    parser.add_argument("--port", type=int, default=3005)
    args = parser.parse_args()

    if args.smoke:
        return _run_smoke()

    import uvicorn  # noqa: PLC0415

    from socialai.orchestrator.app import build_app

    uvicorn.run(build_app(), host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
