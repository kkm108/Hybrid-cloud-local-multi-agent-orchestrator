# SocialAI — Hybrid Cloud-Local Multi-Agent Orchestrator

## 1. Title & The "Elevator Pitch"

**What is SocialAI?**
A small, self-hosted **multi-agent orchestrator** that runs on your own machine. It
coordinates two very different kinds of "minds":

- **Cloud LLM worker tabs** — real browser tabs logged into DeepSeek, ChatGPT, or
  Gemini (the chat UIs you already use), and
- **Local GPU inference services** — models like Qwen running on your own hardware.

**Why does it exist?**
Because the expensive "enterprise API tiers" of the big AI vendors are not the only
way to run multi-model pipelines. SocialAI treats each model as a **plain-text
mailbox**: a `Timer` component, a local model, or a cloud tab can all send each other
messages written in a tiny, human-readable protocol. You get collaboration between
"free" cloud tabs and your local GPUs without paying per-token enterprise rates.

A single **control plane** on `http://localhost:3005` routes those messages and gives
you a dashboard to watch it all happen.

## 2. Quick Start (Windows First)

### Prerequisites

- **Python 3.11+** (the codebase uses Python 3.11 type hints).
- **Brave Browser** — needed only for *live* worker-tab sessions (the attach doctor,
  real sends). Default mock and test runs need no browser at all.
- **Node.js** — *not required*. The dashboard is a static, no-build web page served
  by the orchestrator itself.

### Installation

From the project root, install the package in editable mode:

```powershell
pip install -e ".[dev]"
```

Optional extras (install alongside `dev` when you need them):

```powershell
pip install -e ".[dev,gpu]"   # + torch / transformers for local GPU inference
pip install -e ".[dev,live]"  # + Playwright for real browser worker tabs
```

### Running the system

Everything on Windows goes through our **Windows parity runner** (`scripts/make.ps1`).
First, sanity-check the whole install with the smoke target — it boots the control
plane with mock components, hits the health endpoint and the kill switch, then exits:

```powershell
powershell -NoProfile -File scripts/make.ps1 smoke
```

You should see:

```text
SocialAI smoke: OK (health + kill switch)
```

Then start the real dashboard (the control plane, fixed on port **3005**):

```powershell
python -m socialai.cli
```

If you prefer running uvicorn directly, the app is exported as a factory:

```powershell
python -m uvicorn socialai.orchestrator.app:build_app --factory --port 3005
```

### Accessing the Dashboard

Open <http://localhost:3005>. From here you can:

- see the current system state and all registered components,
- launch and stop campaigns,
- create or edit campaign manifests (see the "Creating a New Campaign" section),
- send a message through the relay to any component.

## 3. Core Concepts (The "Mental Model")

### Manifests — campaigns are just JSON files

A **campaign** is one running instance of a **manifest**: a plain JSON blueprint that
names the agents, the components, and who the default recipient is. Manifests live in
`manifests/*.json`. Three ship with the repo:

| Manifest | What it does |
|---|---|
| `simpleagent.json` | Minimal single-agent campaign (base example). |
| `poster_designer.json` | The creative poster loop (see Section 4). |
| `trading_dhan.json` | A local-analysis / cloud-quality-check loop. |

The file is plain data — no compilation, no build step. Change the JSON, save it, and
the system validates it against a strict schema (Section 6).

### The Router Protocol — `[SEND_TO: …] … [/SEND_TO]` in plain English

The glue of the whole system is a tiny "envelope" format. Any component can wrap text
in an envelope saying **who should receive it next**. The router parses every output,
finds these envelopes, and dispatches each body to the named target.

```text
[SEND_TO: chatgpt_1] apply the "bold retro" style to this brief [/SEND_TO]
```

- The **target** is a component id (e.g. `chatgpt_1`, `local_1`, `facebook_post`, or
  `manual_input`).
- The body can be ordinary free text or a **verb line** that issues a command, e.g.
  `ACTION: GET_STATUS` or `SYSTEM_PROMPT: You are a terse editor.`.
- Success replies look like `✅ [<component_id> <ACTION> OK]`; unknown actions get a
  clearly marked `❌ … UNKNOWN_ACTION …` reply.
- Every hop (source, target, verb, timestamp) is appended to the routing ledger at
  `state/logs/routing.jsonl`, so you can replay exactly what happened.

If a target doesn't exist, the message goes to the **dead-letter** log instead of
crashing the system.

### Components vs. Agents — the pointer and the brain

| Word | Meaning | Example in `poster_designer.json` |
|---|---|---|
| **Agent** | A *role* description for a cloud tab: its vendor (DeepSeek / ChatGPT / Gemini), a role name, and a role prompt. | `deepseek_1` with role `brief_writer` |
| **Component** | A *routable endpoint* — the thing messages are actually sent to. | the `worker_tab` component named `deepseek_1` |

In practice each cloud agent gets a matching `worker_tab` component that fronts it, but
components are a broader idea. The full menu of component kinds:

- `worker_tab` — a cloud chat session attached as a worker (reports BUSY/IDLE).
- `local_llm` — a local model served by its own process on a port in `8100..8199`
  (`mock` backend by default, deterministic).
- `timer` — fires on a fixed interval and pushes a trigger text at a target.
- `browser_bot` — an actuator, e.g. the Facebook poster (dry-run by default).
- `manual_input` — an operator chat channel; **always registered**, so a human can
  always step in. (Human override is invariant.)

The short mental model: **agents are roles, components are mailboxes, and the router
moves envelopes between mailboxes.**

## 4. Primary Use Cases (What can I build?)

### The Autonomous Poster Agency — `poster_designer.json`

The shipped creative campaign is a **cascade** of cloud tabs plus a dry-run actuator.
Open the manifest and you will see four moving parts:

```text
poster_timer (every 30s)
   └─▶ deepseek_1   — brief_writer:   writes a concise creative brief
        └─▶ chatgpt_1 — style_director: applies a visual style (with a
             |                        DO-NOT-copy-previous rule for novelty)
             └─▶ gemini1_1 — image_generator: describes the poster image
                  └─▶ facebook_post — browser_bot in dry_run mode
                                   (writes the post to the outbox, posts nothing)
```

The `style_rotation` list (`minimalist`, `bold retro`, `glassmorphism`, `brutalist`)
is the novelty knob: each pass uses a different style so the campaign never copies its
previous output. Everything is data-driven — remove any one hop and the cascade simply
re-routes around it.

### The Local-Cloud Evaluator — `trading_dhan.json`

The "cheap hops stay local, quality hops go cloud" pattern:

```text
trading_timer (every 60s)
   └─▶ local_1     — local_llm: does the cheap, first-pass analysis
        └─▶ gemini1_1 — cloud analyst: quality-checks and summarises
```

The local model's output is routed to a cloud model for the final judgment, exactly
the pattern you would re-use to have a cloud model *benchmark* any local model
(e.g. Qwen). Default manifests use the deterministic `mock` backend on CPU; point
`local_1` at a real model (Section 5) to make the evaluation meaningful.

### Dry-Run vs. Live — safety first, always

Everything defaults to **watch-only**:

- `browser_bot` actuators (Facebook) default to `mode: "dry_run"` — the composed post
  is written to `outbox/<ts>.json` with **zero network I/O**.
- The local LLM defaults to a `mock` backend so nothing expensive happens until you
  opt in to a real model.

Going **live** is deliberately two conscious acts (Section 5): set `SOCIALAI_LIVE=1`
*and* confirm per call. You cannot post by accident.

## 5. User-Specific Tweaks & Customization

### How to add a new Cloud Vendor

Worker-tab attachments are driven by tiny CSS-selector files in
`socialai/workers/selectors/`. Each vendor is one YAML file naming three elements:

```yaml
# socialai/workers/selectors/<vendor>.yaml
vendor:
  input_box: "textarea#chat-input"
  send_btn: "button[type='submit']"
  last_message: ".ds-chat-message:last-child"
```

To add a new vendor: ship a new file in that folder naming its input box, send button,
and last-message selector, then use that vendor id in a manifest (and in the attach
doctor's `--vendor` choice). No other wiring is required — the doctor validates that
each of the three selectors resolves before it reports a heartbeat.

### Upgrading to Real GPU (CUDA)

The repo installs CPU-friendly torch by default. To swap in the CUDA build:

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Then point the `local_llm` component's `config` at a Hugging Face model id and
`device: "cuda"` in your manifest, and the `TransformersBackend` will use it (with
automatic CPU fallback). If you have no CUDA-capable GPU this machine will use the CPU
path — which is exactly what our validation runs exercised.

### Making the Facebook Actuator LIVE

The actuator's dry-run path is fully wired (writes `outbox/<ts>.json`). Opening the
live path requires **both** of the following:

1. `SOCIALAI_LIVE=1` in the environment (its default in `.env.example` is `0`), and
2. a **per-call confirm token** passed at post time.

If either is missing, the actuator refuses with a clear error and nothing is sent.
Note: the live gate and confirm-token checks are implemented; the final HTTP call to
Facebook's API is a deliberately guarded skeleton — fill that one method in when you
wire real credentials.

### Creating a New Campaign

Prefer the **Manifest Edit UI** on the dashboard: use *Create / Edit* to open a JSON
editor with an inline schema hint, type your manifest, and Save. If the JSON violates
the strict schema you get the violation message shown inline (Section 6) instead of a
silent save.

Two ground rules from the schema (`schemas/manifest.schema.json`):

- The fields are strict: `name`, `description`, `agents`, `components`, and
  `target_recipient` are required; **no unknown keys are allowed**
  (`additionalProperties: false`).
- Ids are lowercase `snake_case` (e.g. `deepseek_1`), and component kinds must be one
  of `local_llm | worker_tab | timer | browser_bot | manual_input`.

## 6. Troubleshooting & FAQ

### "Brave is running; close it or use --profile-copy" (Exit Code 2)

The attach doctor (`scripts/tab_doctor.py`) opens a real Brave profile, and Chromium
locks a profile while the browser is open. When it detects the running browser or the
profile lock, it refuses (exit code 2) rather than corrupting your session.

- Simplest fix: close Brave, then re-run `python scripts/tab_doctor.py --live
  --vendor deepseek`.
- Can't close Brave? Use the fallback, which attaches to a lock-free temp copy of the
  profile:
  `python scripts/tab_doctor.py --live --vendor deepseek --profile-copy --yes`.

(The doctor is *never-send by construction* — it only validates selectors and reports
`heartbeat: IDLE`. Exit code 1 means you forgot `--live` / the live gate; exit code 2
is the browser/profile lock guard.)

### 422 Schema Violation Errors

The manifest schema is deliberately strict — an extra key is an error, not a cosmetic
difference. When you Save an invalid manifest from the dashboard, the exact reason is
shown inline in the editor, e.g.:

```json
{"detail": "schema violation: Additional properties are not allowed ('surprise' was unexpected)"}
```

Read the message, fix the offending key, and Save again. The same validation protects
the `POST /api/manifests` endpoint: no invalid manifest ever lands on disk.

### Where are my backups?

Every restore-mode backup is a zip named `socialai-backup-<UTC>.zip` containing the
manifests, schemas, project state, port map, sanitized routing log tail, and a
`BUNDLE.json` checksum manifest. Backups are **gitignored** (`socialai-backup-*.zip`
in `.gitignore`) so they never get committed to the repo.

To move to a new laptop, follow the step-by-step copy-and-restore checklist in
`docs/RESTORE_DRILL.md`. You can rehearse the entire procedure locally in an isolated
sandbox with `python scripts/drill.py`.

### Port Conflicts

- The control plane is **fixed** on `3005` — that's the dashboard.
- Local LLM services are allocated dynamically from `8100..8199` and recorded in
  `state/ports.json` (with pid + component id). If the dashboard or a local model
  won't start, check nothing else is squatting on those ranges; the local-LLM spawner
  picks the first free port and books it atomically.

## 7. Architecture & For Developers

### Tech stack

- **FastAPI** + **uvicorn** — control-plane API and serving (`:3005`).
- **Pydantic v2** — request validation (plus `jsonschema` for manifest validation).
- **WebSockets** — dashboard state push (`/ws/dashboard`).
- **Playwright** (live extra) — real browser attach for worker tabs / the actuator.
- **Transformers + torch** (gpu extra) — local inference with CPU fallback.
- **Vanilla JS / static HTML** — the dashboard (`socialai/web/`), no build step.

### Layout in one glance

```text
manifests/            JSON campaign blueprints (validated against schemas/)
socialai/
  protocol.py         the [SEND_TO: …] envelope grammar + acks
  router.py           envelope parsing, dispatch, dead-letter log
  orchestrator/       control-plane app, campaigns, components, relay, timer
  local_llm/          local service + backends (mock / transformers)
  workers/            bridge, Playwright adapter, vendor selector YAMLs
  actuators/          Facebook actuator (dry-run default)
  web/                static dashboard (index.html, app.js, styles.css)
scripts/              backup / restore / drill / tab doctor / make.ps1
state/                runtime state, port map, routing ledger (gitignored)
tests/                pytest suite (markers: gpu, live, ui, e2e)
```

### Where the rules of the road live

- **`AGENTS.md`** is the standing contract: the protocol grammar, port assignments,
  the JSON schema, the safety values, and the definition of done. Read it before
  touching code.
- **`TASKS.md`** is the full build history — every feature from T01 (scaffold &
  toolchain) through T18 (restore drill + runbook), each with its verify block.
- **`docs/DECISIONS.md`** records every environment and contract deviation taken
  along the way (Windows runner parity, GPU environment facts, schema strictness).

### Testing on Windows

```powershell
powershell -NoProfile -File scripts/make.ps1 test    # default-filter pytest run
powershell -NoProfile -File scripts/make.ps1 lint    # ruff
powershell -NoProfile -File scripts/make.ps1 smoke   # mock boot + health + stop
```

GPU, live-browser, and UI tests are opt-in via pytest markers (`gpu`, `live`, `ui`);
the default `test` target skips all three so CI and a fresh laptop both stay green
without special hardware.