"""Operator relay chat (§2, §7).

Operators send messages through the relay on the dashboard. A message may
carry an inline ``[SEND_TO: <component>]`` block (recipient override, §2);
otherwise it routes to the campaign's ``target_recipient``. Every operator
message is recorded in ``state/PROJECT_STATE.json``'s relay list, and the hop
is logged to the routing log.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..protocol import parse_message
from ..state import append_relay

TEMPLATES_FILE = Path("state") / "templates.json"

DEFAULT_TEMPLATES = [
    {
        "label": "Read PROJECT_STATE.json",
        "text": "Read PROJECT_STATE.json and summarize the current campaign state.",
    },
    {
        "label": "Inspect Target Directory",
        "text": "Inspect the target directory and report its structure.",
    },
    {
        "label": "Run Syntax Error Audit",
        "text": "Run a syntax error audit on the project and report findings.",
    },
]


class Relay:
    """Routes operator messages to components and records them."""

    def __init__(self, registry, default_recipient: str = "target_recipient") -> None:
        self._registry = registry
        self._default_recipient = default_recipient

    @property
    def default_recipient(self) -> str:
        return self._default_recipient

    def set_default_recipient(self, recipient: str | None) -> None:
        if recipient:
            self._default_recipient = recipient

    def handle(self, text: str, sender: str = "operator") -> dict:
        """Process one operator message and return the recorded entry."""
        result = parse_message(text)
        if result.blocks:
            # Inline [SEND_TO: <x>] override dictates the recipient (§2).
            target = result.blocks[0].target
            replies = self._registry.send(text, from_id=sender)
        else:
            # No override: route free text to the default target recipient.
            target = self._default_recipient
            wrapped = f"[SEND_TO: {target}] {text} [/SEND_TO]"
            replies = self._registry.send(wrapped, from_id=sender)

        entry = {
            "ts": time.time(),
            "from": sender,
            "to": target,
            "text": text,
            "replies": replies,
        }
        append_relay(entry)
        return entry


def load_templates(path: Path = TEMPLATES_FILE) -> list[dict]:
    """Load quick templates, seeding defaults into ``state/templates.json``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
        except json.JSONDecodeError:
            pass
    # Seed defaults and persist.
    path.write_text(json.dumps(DEFAULT_TEMPLATES, indent=2), encoding="utf-8")
    return [dict(t) for t in DEFAULT_TEMPLATES]
