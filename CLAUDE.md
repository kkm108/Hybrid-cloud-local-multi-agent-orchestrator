# SocialAI — Operations Guide (Claude / any agent)

Concise companion to AGENTS.md. For the full contract see AGENTS.md (canonical).
TASKS.md is the task board; work one task at a time and run its Verify block.

## Quick commands
- `make test`        → pytest, unmarked only
- `make lint`        → ruff check .
- `make smoke`       → mock boot + `/api/health` + kill switch
- `make backup`      → `socialai-backup-<UTC>.zip` (operational bundle)
- `make consult`     → bundle + CONSULT.md + git diff patch (advisory zip)
- `make restore BUNDLE=<zip>` → verify checksums, recreate state, `.env` from example

## Minimum operational facts
- Control center: `localhost:3005` (fixed). Static dashboard served at `/`.
- Local LLM instances: ports `8100..8199`, recorded in `state/ports.json`.
- State: `state/PROJECT_STATE.json` (campaign, components, relay). Atomic writes + lock.
- Routable kinds: `local_llm | worker_tab | timer | browser_bot | manual_input`.
- `manual_input` is always registered; the kill switch (`POST /api/campaigns/stop`)
  must always work.
- Actuators default DRY-RUN (`outbox/<ts>.json`); LIVE needs `SOCIALAI_LIVE=1` +
  per-call confirm token. Never ship `.env` or `outbox/` in bundles.

## Guarantees
- No GPU / no network / no browser in default test runs.
- Tests: `gpu`, `live`, `ui`, `e2e` markers are excluded by `make test`.
- Code: Python 3.11+, type hints, ruff clean, FastAPI + pydantic v2.
