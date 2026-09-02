# SocialAI — Task Prompts
Pick one task whose Deps are done. Run its Verify block; all commands must pass.
Contracts live in AGENTS.md (§refs). Keep commits scoped to the task.

## T01 Scaffold & toolchain
Deps: —
Create layout §3, pyproject (fastapi, uvicorn, pydantic, websockets, jsonschema,
httpx; dev: pytest, ruff; extra `gpu`: torch,transformers; extra `live`: playwright),
Makefile §13, `.env.example` (HF_TOKEN=, SOCIALAI_LIVE=0), empty packages,
`tests/test_scaffold.py` (imports ok, dirs exist, AGENTS/TASKS untouched).
Verify: `make lint` · `make test` · `python -c "import socialai"`

## T02 Protocol core & router
Deps: T01
`protocol.py` grammar §5 (multi-block, nested brackets, free text), `router.py`
dispatch registry + dead-letter §5. Tests: parse/serialize round-trip, unknown
target, malformed tag tolerance.
Verify: `pytest tests/test_protocol.py tests/test_router.py -q`

## T03 Local LLM service
Deps: T02
`backend.py` (MockBackend deterministic; TransformersBackend `gpu`), `service.py`
endpoints §6 with exact ack/config-echo strings §5, `spawn.py` subprocess + port
alloc §4. Tests via TestClient: /status format, /config mutation, /system persist,
/generate mock.
Verify: `pytest tests/test_local_llm.py -q` ·
`python -m socialai.local_llm.service --mock --port 8100 & curl -s localhost:8100/status | grep -E "Config \(Model:" ; kill %1`

## T04 Orchestrator & campaign lifecycle
Deps: T03
`components.py` registry (all kinds), `campaigns.py` launch/stop (kill switch §11),
`app.py` endpoints §7 (WS optional stub), routing log §5. Test: launch
`manifests/simpleagent.json` with mocks; inject benchmark; assert reply recorded,
state RUNNING, routing.jsonl rows.
Verify: `pytest tests/test_campaigns.py -q` · `make smoke`

## T05 Worker-tab bridge
Deps: T04
`bridge.py` interface (attach/send/read/heartbeat), `mock.py` scripted replies,
`playwright_adapter.py` skeleton + `workers/selectors/{deepseek,gemini,chatgpt}.yaml`
(input box, send btn, last-message). BUSY while processing, IDLE after. Real-tab
test marked `live`.
Verify: `pytest tests/test_workers.py -q -m "not live"`

## T06 Dashboard frontend
Deps: T04
Static `web/` panels: Active Campaign (+RUNNING badge, Stop OFF), Worker Tabs
(BUSY/IDLE + used-by), Components, Target Recipient select, Relay chat,
Quick Templates, top badges (Campaign ON, Connected & Registered). JS polls
`/api/state` + WS. Verify: `make smoke` ·
`curl -s localhost:3005/ | grep "SocialAI Control Center"`

## T07 Manifest studio & seeds
Deps: T04
`schemas/manifest.schema.json` §8; `/api/manifests` CRUD + 422 on invalid; seed
fixtures: `simpleagent.json`, `poster_designer.json` (3 agents, timer, facebook
dry_run, style_rotation), `trading_dhan.json`. Tests incl. schema rejection cases.
Verify: `pytest tests/test_manifests.py -q`

## T08 Timer component
Deps: T04
Scheduler with injectable clock; fires `trigger` to assigned AI every
`interval_s`; survives campaign stop (cancelled). Test with FakeClock.
Verify: `pytest tests/test_timer.py -q`

## T09 Facebook actuator (dry-run first)
Deps: T04
`actuators/facebook.py` posting state machine (compose→type→attach→post) as pure
steps; DRY-RUN writes `outbox/<ts>.json`; LIVE gate §11. Test: dry-run produces
payload, asserts zero network imports/calls; LIVE without token raises.
Verify: `pytest tests/test_facebook.py -q`

## T10 Relay & templates
Deps: T06
`relay.py`: operator messages, inline `[SEND_TO: x]` override §2, quick templates
seeded `state/templates.json` (Read PROJECT_STATE.json, Inspect Target Directory,
Run Syntax Error Audit). Verify: `pytest tests/test_relay.py -q`

## T11 Backup / restore / portability  ← resilience task
Deps: T04
Implement §12 exactly. `backup.py --mode restore` (full operational bundle) and
`--mode consult` (adds CONSULT.md + `git diff` patch + trimmed logs — for sending
the project as zip/diff to an external advisor). `restore.py`: checksum verify →
state recreate → `.env` from example → print next steps. Tests: seed state →
backup → restore into tmp → `make smoke` green inside restored tree → secret scan
(`! grep -RqE "HF_TOKEN=[A-Za-z0-9]|sk-|Bearer" <unzipped>`).
Verify: `pytest tests/test_backup_restore.py -q` ·
`python scripts/backup.py --mode consult --out /tmp/c.zip && unzip -l /tmp/c.zip | grep -E "CONSULT.md|patch|PROJECT_STATE"`

## T12 E2E poster-loop demo (mocks)
Deps: T05,T08,T09
Integration test `e2e`: launch `poster_designer.json`; timer fires → deepseek mock
emits brief `[SEND_TO: chatgpt_1]` → chatgpt mock forwards style → gemini mock
"generates" image placeholder → facebook dry-run outbox entry with text+image ref.
Assert chain in routing.jsonl and outbox payload.
Verify: `pytest tests/test_e2e_poster.py -q -m e2e`

## T13 Live GPU inference validation
Deps: T03
`scripts/gpu_check.py --model <hf-id>` (default `Qwen/Qwen2.5-0.5B-Instruct`):
spawn TransformersBackend; assert Device CUDA when torch.cuda.is_available(),
else warn + CPU fallback; round-trip /status and /generate; print the §5 config
echo verbatim. Test `tests/test_gpu_live.py` marked `gpu`, skip gracefully when
torch absent. HF_TOKEN optional, never required.
Verify: `pytest -q -m gpu` · manual: `python scripts/gpu_check.py`

## T14 Worker-tab attach doctor
Deps: T05
`scripts/tab_doctor.py --vendor {deepseek,gemini,chatgpt}`: Playwright attach on
the existing Default profile; load `workers/selectors/<vendor>.yaml`; assert
input-box / send-button / last-message selectors present; report heartbeat IDLE.
NEVER sends a message. `live`-marked test wraps the doctor with skipif env.
Verify: manual `python scripts/tab_doctor.py --vendor deepseek` ·
`pytest -q -m "not live"`

## T15 Query Topology view
Deps: T02, T06
`GET /api/topology` aggregates `state/logs/routing.jsonl` into
`{nodes:[{id,count}], edges:[{from,to,count,last_ts}]}`; `/topology` renders a
no-build SVG graph (nodes = components, edge width = count); dashboard gains a
"Query Topology" button. Tests: fixture jsonl → exact node/edge counts; `ui`
test curls the page.
Verify: `pytest tests/test_topology.py -q` · `make smoke` ·
`curl -s localhost:3005/topology | grep "Query Topology"`

## T16 Windows runner parity
Deps: T01
`scripts/make.ps1` implementing the §13 targets (test, lint, smoke, backup,
consult, restore BUNDLE=...) with faithful exit codes, plus `--dry-run` that
prints the resolved command without executing; `make.cmd` shim forwarding args.
DECISIONS.md note: box lacks make/curl; make.ps1 is the canonical Windows runner,
§13 semantics unchanged. tests/test_runners.py: dry-run prints correct mapping
for all six targets; real subprocess run of `make.ps1 lint` exits 0.
Verify: `powershell -NoProfile -File scripts/make.ps1 --dry-run test` ·
`pytest tests/test_runners.py -q`

## T17 Manifest Edit UI wiring
Deps: T06, T07
Studio Edit/Create buttons open a no-build modal (JSON textarea + schema hint);
POST to /api/manifests (create or update); 422 body rendered inline verbatim;
Launch/Delete already wired stay unchanged. Extend tests/test_manifests.py:
update happy path + 422 on unknown key (§7/T07 strictness). `ui` test asserts
modal markup + wiring hooks present at /.
Verify: `pytest tests/test_manifests.py -q` · smoke equivalent ·
page grep "manifest-modal"

## T18 Restore drill + runbook
Deps: T11
docs/RESTORE_DRILL.md: real-second-machine checklist (copy bundle to laptop,
restore, smoke, then T14 doctor when Brave closed). scripts/drill.py automates
the local simulation: backup -> sandbox tmp "machine" (isolated cwd/HOME) ->
restore -> smoke-green inside restored tree -> bundle manifest equality assert.
tests/test_drill.py runs the simulation end-to-end.
Verify: `pytest tests/test_drill.py -q` · manual laptop checklist deferred.

## T19 Twitter/X actuator (dry-run first)

Deps: T04
`actuators/twitter.py` posting state machine (compose→type→attach→post) as pure
steps; DRY-RUN writes `outbox/<ts>.json`; LIVE gate §11. If the live-gate and
confirm-token logic from T09 is not already in a shared helper, extract it to
a shared module now so both actuators share the exact same safety gate.
Test: dry-run produces payload, asserts zero network imports/calls; LIVE
without token raises.
Verify: `pytest tests/test_twitter.py -q`

## T20 CLI-agent bridge (plan-mode first)

Deps: T04, T05, T07
Introduce a `cli_agent` component kind. Per §0 rule 2, do NOT modify AGENTS.md
text (§2/§8); instead, update `schemas/manifest.schema.json` to allow
`kind: "cli_agent"` (preventing T07 422s) and record the semantic addition and
§3 layout deviation (`socialai/cli_agents/`) in `docs/DECISIONS.md`.
Build a pluggable adapter mirroring `socialai/workers/`: `socialai/cli_agents/bridge.py`
(attach/send/read/heartbeat), `mock.py` (scripted replies), and
`selectors/claude.yaml` (binary, print/resume flags, JSON fields). Reference
impl: `claude -p <body> --output-format json --resume <id>`.
Safety (§11): defaults to `plan` permission mode (propose only). Switching to
`acceptEdits` or `--allowedTools` requires env `SOCIALAI_CLI_EXECUTE=1`; no
adapter may pass `bypassPermissions`.
Tests: mock adapter round-trips `[SEND_TO: cli_agent_1]`; plan-mode default
asserted; execute mode without env raises. Real-binary test marked `live`.
Verify: `pytest tests/test_cli_agent.py -q -m "not live"` · ruff clean ·
DECISIONS.md updated with schema/§3 deviations and a brief real-worker transcript.