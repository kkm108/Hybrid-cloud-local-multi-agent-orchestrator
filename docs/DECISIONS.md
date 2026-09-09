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

## T16 — Windows runner parity
- The box lacks make/curl, so `scripts/make.ps1` is the canonical Windows
  runner: it mirrors all §13 targets (test, lint, smoke, backup, consult,
  restore `BUNDLE=<zip>`) with faithful child exit codes and a `--dry-run`
  that prints the resolved command without executing. `make.cmd` is a thin
  shim forwarding all args. §13 semantics unchanged.
- `pyproject.toml` gains `[tool.ruff] extend-exclude = ["*.ps1", "*.cmd"]` so the
  runner sources are not parsed as Python by the `lint` target.

## T16 — Windows runner env
- PS execution policy must be at least `RemoteSigned` for the *current user*;
  a `Restricted` box refuses `powershell -NoProfile -File ...` outright
  (set once via `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`).
- `make.ps1` accepts the target plus option tokens as raw positional args:
  `--dry-run` / `--BUNDLE <zip>` / `BUNDLE=<zip>` are parsed manually because
  `-File` scripts do not bind named switches.
- `ruff` `extend-exclude` covers `*.ps1` / `*.cmd` (see "T16 — Windows runner
  parity").

## T22/afaa0ce — mixed commit: drill fidelity fix
- Commit `afaa0ce` ("T22: GitHub Actions CI workflow + drill fidelity fix")
  bundles two unrelated deliverables: the CI workflow file and a
  restore-drill regression fix. The drill fix deserved a separate commit
  but was folded in to unblock T22's verify block.
- **What the drill fix changed**: `scripts/drill.py` now calls
  `restore.py --no-smoke` (pure restore, no smoke), checks
  `_tree_matches_manifest` *before* running smoke, then runs smoke
  separately. This prevents a legitimate post-restore smoke timestamp
  stamp on `state/PROJECT_STATE.json` from being treated as a checksum
  mismatch. The report dropped `restore_smoke_ok`; tests removed the
  corresponding assertion.
- **Root cause**: when `state/PROJECT_STATE.json` didn't exist at the
  repo root (pre-T18), the bundle shipped no such file, so the `all()`
  check over expected keys passed trivially. Once the file was created
  by earlier root-level test runs and included in the bundle, the
  post-restore smoke's `set_campaign(None)` rewrote it with a fresh
  `updated` timestamp, producing a genuine byte mismatch against the
  bundled copy.
