"""Shared actuator safety gate (§11).

Every actuator (Facebook, Twitter/X, …) authorizes a LIVE post through this one
function so the human-hold rule is byte-for-byte identical across actuators:
``SOCIALAI_LIVE=1`` in the environment **AND** a per-call ``confirm`` token.
Either missing → ``ActuatorError``. Dry-run code paths must never call this and
must never import networking.
"""

from __future__ import annotations

import os


class ActuatorError(Exception):
    """Raised when a live post is attempted without full authorization."""


def assert_live_authorized(confirm: str | None) -> None:
    """Raise unless BOTH SOCIALAI_LIVE=1 and a confirm token are present."""
    if os.environ.get("SOCIALAI_LIVE", "0") != "1":
        raise ActuatorError("SOCIALAI_LIVE is not 1; refusing live post")
    if not confirm:
        raise ActuatorError("per-call confirm token required for live post")
