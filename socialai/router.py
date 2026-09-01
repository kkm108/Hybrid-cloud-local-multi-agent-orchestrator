"""Router dispatch registry (§2, §5).

Dispatches parsed ``[SEND_TO]`` blocks to registered components. Unknown
targets are written to the routing dead-letter log
(``state/logs/routing.jsonl``) without crashing.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import Block, parse_blocks

DEFAULT_LOG = Path("state") / "logs" / "routing.jsonl"

DispatchHandler = Callable[[Block, str], str | None]


@dataclass
class Router:
    """Holds registered handlers and routes blocks to them."""

    _handlers: dict[str, DispatchHandler] = field(default_factory=dict)
    log_path: Path = DEFAULT_LOG
    source: str = "router"

    def register(self, component_id: str, handler: DispatchHandler) -> None:
        """Register a handler for a routable component id."""
        self._handlers[component_id] = handler

    def unregister(self, component_id: str) -> None:
        self._handlers.pop(component_id, None)

    def handles(self, component_id: str) -> bool:
        return component_id in self._handlers

    def dispatch_text(self, text: str, from_id: str = "unknown") -> list[str]:
        """Run a raw message through the router, returning handler replies."""
        replies: list[str] = []
        blocks = parse_blocks(text)
        for block in blocks:
            reply = self.dispatch_block(block, from_id)
            if reply is not None:
                replies.append(reply)
        return replies

    def dispatch_block(self, block: Block, from_id: str) -> str | None:
        """Route a single block to its handler, logging every hop.

        Unknown target -> dead-letter log entry; returns None and does not
        raise.
        """
        self._log(from_id, block.target, block.verb, block.body)
        handler = self._handlers.get(block.target)
        if handler is None:
            self._dead_letter(block, from_id)
            return None
        return handler(block, from_id)

    def _log(
        self,
        from_id: str,
        to: str,
        verb: str | None,
        body: str,
    ) -> None:
        record = {
            "ts": time.time(),
            "from": from_id,
            "to": to,
            "verb": verb or "free_text",
            "hash": hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
        }
        self._append(record)

    def _dead_letter(self, block: Block, from_id: str) -> None:
        record = {
            "ts": time.time(),
            "event": "dead_letter",
            "from": from_id,
            "to": block.target,
            "verb": block.verb or "free_text",
            "hash": hashlib.sha256(block.body.encode("utf-8")).hexdigest()[:16],
        }
        self._append(record)

    def _append(self, record: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record)
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
