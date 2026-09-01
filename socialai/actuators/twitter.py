"""Twitter/X posting actuator (§11).

Posting is modeled as pure state-machine steps: ``compose → type → attach →
post``. DRY-RUN (the default) writes the final payload to ``outbox/<ts>.json``
and performs **zero** network I/O — the dry-run code path never imports any
networking module. LIVE posting uses the shared §11 safety gate
(``socialai.actuators.safety.assert_live_authorized``): BOTH ``SOCIALAI_LIVE=1``
AND a per-call confirm token are required, else ``ActuatorError``.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path

from .safety import assert_live_authorized


class PostStep(str, Enum):
    COMPOSE = "compose"
    TYPE = "type"
    ATTACH = "attach"
    POST = "post"


class TwitterActuator:
    """Pure-step Twitter/X poster with a hard dry-run default."""

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
        LIVE requires ``SOCIALAI_LIVE=1`` AND a per-call ``confirm`` token
        (shared §11 gate in ``socialai.actuators.safety``).
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
            "platform": "twitter",
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
        assert_live_authorized(confirm)
        # Networking imports happen only here, lazily, never in dry-run.
        import httpx  # noqa: PLC0415

        client = httpx.Client()
        # Skeleton live publish — replace with the real X API call when LIVE=1.
        client.close()
        payload["posted"] = True
        return payload
