# SocialAI — Restore Drill & Runbook (T18)

Real-second-machine checklist for bringing a laptop (or any fresh box) back to
operational after this machine is gone or unreachable.

## 1. The checklist (real second machine)

1. **Ship the bundle.** Copy `socialai-backup-<UTC>.zip` (from
   `python scripts/backup.py --mode restore`) to the target machine — USB,
   drive share, or encrypted transfer. Never ship `.env` separately; tokens
   are re-entered from `.env.example` below.
2. **Place the code.** Clone/checkout the SocialAI repo on the laptop and
   `pip install -e ".[dev]"` (the bundle carries docs/manifests/schemas/state,
   not the `socialai/` package — restore + smoke need the package importable).
3. **Restore.** From the repo root: `python scripts/restore.py --bundle
   socialai-backup-<UTC>.zip` (or `restore.py`'s no-arg form picks the newest
   bundle in the folder). It verifies the sha256 manifest, recreates `state/`,
   and writes `.env` from `.env.example`.
4. **Tokens.** Open `.env` and put real values in (HF_TOKEN etc.) — the
   placeholder stays otherwise.
5. **Smoke.** `make smoke` (or `make.ps1 smoke`) must print
   `SocialAI smoke: OK (health + kill switch)`. Exit code 0 = machine
   operational.
6. **Worker-tab attach doctor (only once Brave is closed).** Close Brave, then
   run `python scripts/tab_doctor.py --live --vendor deepseek`. Expect: no
   preflight refusal (exit 2 only when Brave is running), selectors present,
   `heartbeat: IDLE`. If Brave must stay open, use
   `python scripts/tab_doctor.py --live --vendor deepseek --profile-copy --yes`,
   which attaches to a lock-free temp copy of the profile.
7. **Verify portability** (optional but cheap): the same zip restores byte-for-
   byte under `scripts/drill.py`'s sandbox simulation (below).

## 2. What `drill.py` automates (local simulation)

`python scripts/drill.py [--out <dir>]` runs the full drill without a second
machine:

- builds a **fresh restore bundle** from this repo (`--mode restore`);
- creates a sandbox tmp "machine" with **isolated cwd and HOME**;
- runs `restore.py` **inside the sandbox** (isolated env);
- runs the **smoke equivalent inside the restored tree**; and
- asserts **bundle manifest equality**: every `BUNDLE.json` sha256 must match
  the restored file bytes.

Iterates through the same restore path the laptop would take. Pass `--out` to
inspect the sandbox afterwards; the state/checksum outputs are printed.

## 3. Failure triage

| Symptom | Fix |
|---|---|
| `checksum mismatch for <arc>` | Bundle corrupted in transit — re-ship it; never run a partial restore. |
| `smoke: FAILED` | Package not importable on laptop (`pip install -e ".[dev]"`) or `state/` not recreated — rerun restore with the same bundle. |
| doctor exit 2 | Brave is running — close it (or pass `--profile-copy --yes`). |
| doctor exit 1 | Forgot `--live` / `SOCIALAI_LIVE=1` — add it. |