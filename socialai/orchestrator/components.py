"""Component registry (§2, §4).

A ``Component`` is one routable endpoint. Kinds: ``local_llm | worker_tab |
timer | browser_bot | manual_input``. The ``manual_input`` component is always
registered (human override invariant, §11). Each registered component gets a
handler on the shared ``Router`` so incoming ``[SEND_TO]`` blocks dispatch to
it and every hop is appended to ``state/logs/routing.jsonl``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..protocol import Block, parse_blocks
from ..router import Router
from ..state import upsert_component

COMPONENT_KINDS = ("local_llm", "worker_tab", "timer", "browser_bot", "manual_input")

# Guard against infinite forwarding loops (each hop must terminate the chain).
MAX_CHAIN_DEPTH = 8

Runner = Callable[["Component", Block], str]


@dataclass
class Component:
    """A routable component endpoint."""

    id: str
    kind: str
    config: dict = field(default_factory=dict)
    assigned_ai: str | None = None
    status: str = "IDLE"
    used_by: str | None = None
    runner: Runner | None = None  # custom processor (tests / plugins)

    def register_msg(self) -> None:
        upsert_component(
            {
                "id": self.id,
                "kind": self.kind,
                "assigned_ai": self.assigned_ai,
                "config": self.config,
                "status": self.status,
                "used_by": self.used_by,
            }
        )


def default_runner(component: Component, block: Block) -> str:
    """Default per-kind processing. Worker/local_llm return an echo reply."""
    return f"reply-from-{component.id}:{block.body}"


class ComponentRegistry:
    """Manages components and wires each into the shared router."""

    def __init__(self, router: Router) -> None:
        self._router = router
        self._components: dict[str, Component] = {}
        # Always-on human override (§11).
        self._register_manual()

    def _register_manual(self) -> None:
        manual = Component(id="manual_input", kind="manual_input", config={})
        self.add(manual)

    def add(self, component: Component) -> None:
        self._components[component.id] = component
        component.register_msg()
        comp_c = component
        # Resolve the runner lazily at dispatch time so tests/plugins may swap
        # ``component.runner`` after registration (e.g. the E2E paper chain).
        self._router.register(
            comp_c.id,
            lambda block, from_id, _c=comp_c: self._dispatch(_c, block, from_id),
        )

    def _dispatch(self, component: Component, block: Block, from_id: str) -> str:
        runner = component.runner or default_runner
        self._set_status(component.id, "BUSY", used_by=from_id)
        try:
            return runner(component, block)
        finally:
            self._set_status(component.id, "IDLE", used_by=None)

    def _set_status(self, component_id: str, status: str, **extra) -> None:
        self._components[component_id].status = status
        upsert_component(
            {
                "id": self._components[component_id].id,
                "kind": self._components[component_id].kind,
                "assigned_ai": self._components[component_id].assigned_ai,
                "config": self._components[component_id].config,
                "status": status,
                "used_by": extra.get("used_by"),
            }
        )

    def all(self) -> list[Component]:
        return list(self._components.values())

    def get(self, component_id: str) -> Component | None:
        return self._components.get(component_id)

    def send(self, text: str, from_id: str = "operator") -> list[str]:
        """Route raw text through the router, cascading forwarded blocks.

        If a component's output contains further ``[SEND_TO]`` blocks, those
        hops are re-dispatched too (depth-capped), so worker chains like
        timer → deepseek → chatgpt → gemini → facebook run in one message.
        """
        return self._route(text, from_id=from_id, depth=0)

    def _route(self, text: str, from_id: str, depth: int) -> list[str]:
        replies: list[str] = []
        for block in parse_blocks(text):
            reply = self._router.dispatch_block(block, from_id)
            if reply is None:
                continue
            replies.append(reply)
            if depth >= MAX_CHAIN_DEPTH:
                continue
            # Re-dispatch any [SEND_TO] blocks the reply forwards onward.
            replies.extend(self._route(reply, from_id=block.target, depth=depth + 1))
        return replies
