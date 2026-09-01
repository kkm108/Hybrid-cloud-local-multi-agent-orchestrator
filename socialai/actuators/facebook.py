"""Facebook posting actuator (§11).

Posting is modeled as pure state-machine steps: ``compose → type → attach →
post``. DRY-RUN (the default) writes the final payload to ``outbox/<ts>.json``
and performs **zero** network I/O — the dry-run code path never imports any
networking module. LIVE posting requires BOTH ``SOCIALAI_LIVE=1`` in the
environment AND a per-call confirm token; either is missing and the actuator
raises (human hold, §11).
"""

from __future__ import annotations

import json
import os
import time
from enum import Enum
from pathlib import Path


class PostStep(str, Enum):
    COMPOSE = "compose"
    TYPE = "type"
    ATTACH = "attach"
    POST = "post"


class ActuatorError(Exception):
    """Raised when a live post is attempted without full authorization."""


class FacebookActuator:
    """Pure-step Facebook poster with a hard dry-run default."""

    def __init__(self, mode: str = "dry_run", outbox_dir: str = "outbox") -> None:
        if mode not in ("dry_run", "live"):
            raise ValueError(f"mode must be dry_run or live, got {mode}")
        self.mode = mode
        self.outbox_dir = Path(outbox_dir)
        self.steps: list[dict] = []

    # --- pure state machine steps -----------------------------------------
    def compose(self, text: str, image_ref: str | None = None) -> dict:
        """Step 1: capture the copy to be posted."""
        entry = {"step": PostStep.COMPOSE, "text": text, "image_ref": image_ref}
        self.steps.append(entry)
        return entry

    def type(self, message: str) -> dict:
        """Step 2: record the typed message body."""
        entry = {"step": PostStep.TYPE, "message": message}
        self.steps.append(entry)
        return entry

    def attach(self, media_ref: str | None = None) -> dict:
        """Step 3: attach media (image reference) to the post."""
        entry = {"step": PostStep.ATTACH, "media_ref": media_ref}
        self.steps.append(entry)
        return entry

    def post(self, confirm: str | None = None) -> dict:
        """Step 4: finalize the post.

        DRY-RUN writes ``outbox/<ts>.json`` with zero network I/O.
        LIVE requires ``SOCIALAI_LIVE=1`` AND a per-call ``confirm`` token.
        """
        self.steps.append({"step": PostStep.POST})
        payload = self._build_payload()
        if self.mode == "dry_run":
            return self._dry_run(payload)
        return self._live(payload, confirm)

    # --- payload assembly -------------------------------------------------
    def _build_payload(self) -> dict:
        text = ""
        image_ref = None
        media_ref = None
        for s in self.steps:
            if s["step"] == PostStep.COMPOSE:
                text = s.get("text", "")
                image_ref = s.get("image_ref")
            elif s["step"] == PostStep.TYPE:
                text = s.get("message", text)
            elif s["step"] == PostStep.ATTACH:
                media_ref = s.get("media_ref")
        return {
            "text": text,
            "image_ref": image_ref,
            "media_ref": media_ref,
            "mode": self.mode,
            "ts": time.time(),
        }

    # --- dry run ----------------------------------------------------------
    def _dry_run(self, payload: dict) -> dict:
        # No networking imports live on this code path (§11). This writes a
        # timestamped payload only.
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        ts = payload["ts"]
        path = self.outbox_dir / f"{int(ts)}.json"
        payload["outbox"] = str(path)
        payload["posted"] = False
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload

    # --- live post --------------------------------------------------------
    def _live(self, payload: dict, confirm: str | None) -> dict:
        if os.environ.get("SOCIALAI_LIVE", "0") != "1":
            raise ActuatorError("SOCIALAI_LIVE is not 1; refusing live post")
        if not confirm:
            raise ActuatorError("per-call confirm token required for live post")
        # Networking imports happen only here, lazily, never in dry-run.
        import httpx  # noqa: PLC0415

        client = httpx.Client()
        # Skeleton live publish — replace with the real FB API call when LIVE=1.
        client.close()
        payload["posted"] = True
        return payload
