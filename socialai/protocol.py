"""Protocol grammar core (§5).

Parses and serializes ``[SEND_TO:<target>] ... [/SEND_TO]`` blocks from any
component output. Blocks may appear multiple times, may be nested, and may be
mixed with free text. Free text outside any block routes to the default
target recipient.

Grammar (AGENTS.md §5)::

    block    = "[SEND_TO:" SP target "]" SP body SP "[/SEND_TO]"
    target   = component_id | "manual_input"
    body     = verb_line | free_text (mixed allowed)
    verb_line= "ACTION:" (GET_STATUS|UPDATE_CONFIG|SET_SYSTEM_INSTRUCTION|START_WORK)
             | (TEMPERATURE|TOP_P|TOP_K|MAX_TOKENS|REPETITION_PENALTY|SYSTEM_PROMPT) ":" value
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Named config verbs (missing values default to the key name lowercased).
VERBS = ("GET_STATUS", "UPDATE_CONFIG", "SET_SYSTEM_INSTRUCTION", "START_WORK")
CONFIG_KEYS = (
    "TEMPERATURE",
    "TOP_P",
    "TOP_K",
    "MAX_TOKENS",
    "REPETITION_PENALTY",
    "SYSTEM_PROMPT",
)

_OPEN_RE = r"\[SEND_TO:\s*([A-Za-z0-9_]+)\s*\]"  # m.group(1) = target
_CLOSE_RE = r"\[/SEND_TO\]"


@dataclass
class Block:
    """One parsed ``[SEND_TO:<target>] ... [/SEND_TO]`` block."""

    target: str
    body: str
    verb: str | None = None
    value: str | None = None
    raw: str = ""

    @property
    def is_action(self) -> bool:
        return self.verb == "ACTION"

    @property
    def is_config(self) -> bool:
        return self.verb in CONFIG_KEYS


@dataclass
class ParseResult:
    """Result of parsing a message: blocks plus trailing/free text."""

    blocks: list[Block] = field(default_factory=list)
    free_text: str = ""


def _find_open(match: re.Match[str]) -> tuple[str, int]:
    """Return (target, index just past the opening tag)."""
    target = match.group(1)
    return target, match.end()


def parse_blocks(message: str) -> list[Block]:
    """Extract all top-level ``[SEND_TO:...]...[/SEND_TO]`` blocks.

    Handles multiple blocks and nested brackets inside a body. Malformed
    opening tags without a matching closer are ignored (tolerance), and
    malformed closer tags without an opener are treated as free text.
    """
    blocks: list[Block] = []
    open_re = re.compile(_OPEN_RE)
    close_re = re.compile(_CLOSE_RE, re.IGNORECASE)

    i = 0
    n = len(message)
    while i < n:
        m = open_re.search(message, i)
        if m is None:
            break
        target, after_open = _find_open(m)

        # Scan forward tracking nesting depth for the matching closer.
        depth = 1
        j = after_open
        closed = False
        depth_open = re.compile(_OPEN_RE)
        while j < n:
            nxt_open = depth_open.search(message, j)
            nxt_close = close_re.search(message, j)
            if nxt_close is None:
                # No closer: tolerate as malformed, stop scanning this block.
                break
            if nxt_open is not None and nxt_open.start() < nxt_close.start():
                depth += 1
                j = nxt_open.end()
                continue
            depth -= 1
            j = nxt_close.end()
            if depth == 0:
                closed = True
                break

        if not closed:
            # Malformed (no matching closer): ignore the block.
            i = after_open
            continue

        raw_body = message[after_open : j - len("[/SEND_TO]")].strip()
        block = _make_block(target, raw_body, message[m.start() : j])
        blocks.append(block)
        i = j

    return blocks


def _make_block(target: str, body: str, raw: str) -> Block:
    """Build a Block, extracting the leading verb_line if present."""
    block = Block(target=target, body=body, raw=raw)
    first_line = body.splitlines()[0].strip() if body.splitlines() else ""
    if first_line.startswith("ACTION:"):
        block.verb = "ACTION"
        block.value = first_line[len("ACTION:") :].strip()
        return block
    for key in CONFIG_KEYS:
        if first_line.upper().startswith(key + ":"):
            block.verb = key
            block.value = first_line[len(key) + 1 :].strip()
            return block
    return block


def parse_message(message: str) -> ParseResult:
    """Parse a full message into blocks plus residual free text."""
    result = ParseResult()
    blocks = parse_blocks(message)
    result.blocks = blocks
    # Strip all recognized blocks out of the text; whatever's left is free text.
    stripped = message
    for b in blocks:
        stripped = stripped.replace(b.raw, "", 1)
    result.free_text = " ".join(stripped.split())
    return result


def valid_target(target: str, known_ids: set[str]) -> bool:
    """Check whether the target is routable (known component or manual_input)."""
    return target == "manual_input" or target in known_ids


def unknown_action_reply(component_id: str, name: str) -> str:
    """Produce the canonical unknown-action ack (§5)."""
    return f"❌ [{component_id} UNKNOWN_ACTION: {name}]"


def serialize_block(target: str, body: str) -> str:
    """Serialize a single block back to canonical protocol text."""
    return f"[SEND_TO:{target}] {body} [/SEND_TO]"
