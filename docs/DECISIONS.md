# SocialAI — Decisions Log

Deviations, module additions, and rationale recorded per AGENTS.md §9/§14.
Never rewrite contracts; note and work around minimally.

## T08 — Timer scheduler module
- Added `socialai/orchestrator/timer.py` (not in §3's fixed layout) to host the
  `TimerScheduler`. The fixed layout lists only `app/campaigns/components/relay`
  under `orchestrator/`, but T08 requires a dedicated injectable-clock
  scheduler. Timers declared in manifests register on this scheduler; the kill
  switch (`stop`) calls `scheduler.stop()`, which clears timers and rejoins the
  loop — a campaign stop always survives cleanly.

## T07 — Manifest schema strictness
- `schemas/manifest.schema.json` uses `additionalProperties: false` at the top
  level (unknown keys rejected). Schema violations surface as HTTP 422.
- The manifest store directory is configurable (`set_manifest_dir`) for test
  isolation; the authoritative schema always loads from the repo `schemas/`.

## T12 — Cascade routing + two T12-discovered fixes
- `ComponentRegistry.send` now cascades: any `[SEND_TO]` block returned by a
  component's runner is re-dispatched (depth-capped at 8) so paper-chain worker
  loops (timer → deepseek → chatgpt → gemini → facebook) run in one message.
- Runner dispatch became lazy: `component.runner` is resolved at dispatch time
  instead of being captured at registration, so tests/plugins may swap a runner
  after launch. The E2E chain depends on this.
- Fixed `FacebookActuator._dry_run`: the on-disk outbox payload now includes
  `posted: false` and the `outbox` path (previously written before those keys
  were set, so the file lacked them).

## T15 — Query Topology module
- Added `socialai/orchestrator/topology.py` (not in §3's fixed layout) to host
  `build_topology()`. It aggregates `state/logs/routing.jsonl` into a
  `{nodes, edges}` graph; the app exposes `GET /api/topology` (JSON) and a
  no-build SVG page at `/topology`, plus a dashboard "Query Topology" button.

## T13 — GPU inference environment
- Validation box runs `torch 2.13.0+cpu` with `torch.cuda.is_available()=False`:
  CUDA is unavailable here, so the §6 CPU-fallback path was exercised and
  validated instead of CUDA.
- Baselines (CPU, `Qwen/Qwen2.5-0.5B-Instruct`): weight-load **124.17 s**,
  generate **5.05 s / 27 tokens** (max_tokens 32).
- transformers 5.x emits deprecation warnings (generation_config merge,
  BPE clean-up) — non-blocking, output correct; no code fix warranted.
- The CUDA path is untested on this machine; validating it requires an
  operational (non-`+cpu`) torch reinstall.
