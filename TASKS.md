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