# SocialAI — Standing Contract (canonical)

## 0. Operating rules for agents
1. Read §1–§4 before writing code. Then open TASKS.md and pick exactly ONE task
   whose deps are satisfied. Complete it, run its Verify block, commit
   (`T<nn>: <summary>`), stop.
2. Never widen scope. If a contract here is wrong/blocking, record it in
   `docs/DECISIONS.md` and work around it minimally — do not rewrite contracts.
3. Every behavior ships with tests. Untested behavior = not done.
4. No GPU, no network, no browser in default test runs. Real-inference tests are
   marked `gpu`, real vendor tabs `live`, UI checks `ui`. CI runs unmarked only.

## 1. Purpose
SocialAI is a hybrid cloud–local multi-agent orchestrator. A control plane
(localhost:3005) routes plain-text RPC messages between heterogeneous components:
cloud LLM worker tabs (DeepSeek/Gemini/ChatGPT), local GPU inference services
(transformers), schedulers (timer), and browser actuators (social posting).
Campaigns = JSON manifests declaring agents, components, and routing.

## 2. Glossary
- **Campaign**: one running manifest instance. **Manifest**: JSON blueprint in `manifests/`.
- **Component**: routable endpoint. Kinds: `local_llm | worker_tab | timer |
  browser_bot | manual_input`.
- **Worker tab**: cloud chat session attached as a worker (`deepseek_1`, `gemini1_1`,
  `chatgpt_1`), reports BUSY/IDLE.
- **Router**: parses `[SEND_TO]` blocks from any component output, dispatches bodies.
- **Relay**: operator chat on the dashboard; supports inline recipient override.
- **Target AI recipient**: default route for free text.

## 3. Repo layout (exact)

    AGENTS.md CLAUDE.md TASKS.md Makefile pyproject.toml .env.example
    schemas/manifest.schema.json
    manifests/*.json
    socialai/
      protocol.py router.py state.py cli.py
      orchestrator/{app,campaigns,components,relay}.py
      local_llm/{backend,service,spawn}.py
      workers/{bridge,mock,playwright_adapter}.py
      actuators/facebook.py
      web/{index.html,app.js,styles.css}   # no-build static frontend
    scripts/{backup.py,restore.py}
    state/   (gitignored runtime: PROJECT_STATE.json ports.json logs/routing.jsonl)
    tests/

## 4. Ports & processes
- `3005` control center (fixed).
- Local LLM instances: allocated from `8100..8199`, recorded in `state/ports.json`.
- One writer per state file; atomic writes (tmp+rename) + `fcntl` lock.

## 5. Protocol contract (grammar)

    block    = "[SEND_TO:" SP target "]" SP body SP "[/SEND_TO]"
    target   = component_id | "manual_input"
    body     = verb_line | free_text (mixed allowed)
    verb_line= "ACTION:" (GET_STATUS|UPDATE_CONFIG|SET_SYSTEM_INSTRUCTION|START_WORK)
             | (TEMPERATURE|TOP_P|TOP_K|MAX_TOKENS|REPETITION_PENALTY|SYSTEM_PROMPT) ":" value

- Unknown ACTION → `❌ [<component_id> UNKNOWN_ACTION: <name>]`.
- Unknown target → dead-letter entry in `state/logs/routing.jsonl`, no crash.
- Success acks: `✅ [<component_id> <ACTION> OK]` followed by `📊 Current Config: `
  `<id> Config (Model: <m> | Device: <cuda|cpu> | Temp: <t> | MaxTokens: <n> |`
  ` TopP: <p> | TopK: <k> | RepetitionPenalty: <r>)`.
- All routing appended to `state/logs/routing.jsonl` (ts, from, to, verb, hash).

## 6. Local LLM service contract (`socialai/local_llm/service.py`, port 81xx)
`GET /status` → ack config echo. `POST /config` → UPDATE_CONFIG semantics.
`POST /system` → SET_SYSTEM_INSTRUCTION. `POST /generate {prompt}` → completion.
Backend interface `LLMBackend`: `MockBackend` (deterministic, default) and
`TransformersBackend` (torch/CUDA, CPU fallback; HF model id configurable;
sampling kwargs map 1:1 to `generate()`). Defaults: temp .7, top_p .9, top_k 50,
max_tokens 512, rep_penalty 1.0.

## 7. Control-center API contract (`:3005`)
`GET /api/health` · `GET /api/state` · `GET /api/manifests` ·
`POST /api/manifests` (schema-validated, 422 on bad) ·
`POST /api/campaigns/{name}/launch` · `POST /api/campaigns/stop` (kill switch,
must always work) · `GET /api/components` · `POST /api/components/{id}/message` ·
`POST /api/relay` · `WS /ws/dashboard` (state push). Frontend: static, served at `/`.

## 8. Manifest schema (see schemas/manifest.schema.json)
Required: `name, description, agents[], components[], target_recipient`.
Agent: `{id, kind:"worker_tab", vendor, role, role_prompt}`.
Component: `{id, kind, assigned_ai, config{...}}`; timer adds `interval_s, trigger`;
browser_bot adds `mode: "dry_run"|"live"`. Optional `style_rotation[]` for creative
campaigns (novelty enforcement: prompts must include DO-NOT-copy-previous rules).

## 9. Coding conventions
Python 3.11+, type hints, ruff clean. FastAPI+pydantic v2. No wildcard imports,
no new deps without adding to pyproject + DECISIONS.md. Frontend: vanilla JS/HTMX,
no build step. IDs snake_case with `_1` instance suffix.

## 10. Testing contract
pytest. Markers: `gpu`, `live`, `ui`, `e2e`. `make test` = `pytest -q -m "not gpu
and not live and not ui"`. `make lint`, `make smoke` (mock boot + curl health +
stop). Fixtures live in `tests/fixtures/`.

## 11. Safety & values
- Human override is invariant: `manual_input` component always registered;
  kill switch unconditionally stops spawns/timers/actuators.
- Actuators default DRY-RUN (write `outbox/<ts>.json`); LIVE requires env
  `SOCIALAI_LIVE=1` AND per-call confirm token. No actuator may import networking
  in dry-run code path.
- Secrets only via `.env` (HF_TOKEN etc.). `.env` never committed, never in bundles.
- Local-first: prefer local inference for cheap hops; cloud for quality hops.
- Observability over cleverness: log first, then act.

## 12. Backup / portability contract
`scripts/backup.py --mode restore|consult` → `socialai-backup-<UTC>.zip` containing
exactly: `BUNDLE.json` (mode, schema ver, git rev, ts, sha256 manifest), AGENTS.md,
TASKS.md, CLAUDE.md, `manifests/`, `schemas/`, `state/PROJECT_STATE.json`,
`state/ports.json`, sanitized `routing.jsonl` tail (≤2000 lines, secrets redacted),
`.env.example`, `SNAPSHOT.md` (running campaign, component statuses, versions).
Consult mode adds: `CONSULT.md`, `git diff <last-tag>...HEAD.patch` (or
`git bundle` fallback note), trimmed chat logs. **Never** `.env`, never `outbox/`.
`scripts/restore.py` verifies checksums, recreates state, prompts tokens from
`.env.example`, then `make smoke` green ⇒ machine operational.

## 13. Commands (standing)
`make test | lint | smoke | backup | consult | restore BUNDLE=<zip>`

## 14. Definition of done (any task)
Verify block green · ruff clean · tests added/updated · DECISIONS.md entry if any
deviation · single commit.