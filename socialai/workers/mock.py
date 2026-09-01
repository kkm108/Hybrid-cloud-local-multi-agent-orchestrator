"""Mock worker tab with scripted, deterministic replies."""

from __future__ import annotations

from .bridge import WorkerBridge


class MockWorker(WorkerBridge):
    """Worker that returns replies from a script, in order.

    When the script is exhausted, it defaults to an echo-style reply so the
    bridge always answers without real vendor tabs.
    """

    def __init__(self, worker_id: str, vendor: str = "mock",
                 script: list[str] | None = None) -> None:
        super().__init__(worker_id, vendor)
        self._script = list(script) if script else []
        self._attached = False
        self._last_message: str | None = None
        self._last_reply: str | None = None

    def attach(self) -> bool:
        self._attached = True
        return True

    def _send_impl(self, message: str) -> str:
        self._last_message = message
        if self._script:
            self._last_reply = self._script.pop(0)
        else:
            self._last_reply = f"mock:{self.worker_id}:{message}"
        return self._last_reply

    def read(self) -> str:
        return self._last_reply or ""

    @property
    def attached(self) -> bool:
        return self._attached

    @property
    def last_message(self) -> str | None:
        return self._last_message

    @property
    def last_reply(self) -> str | None:
        return self._last_reply
