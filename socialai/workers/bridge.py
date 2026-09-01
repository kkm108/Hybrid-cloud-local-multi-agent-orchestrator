"""Worker-tab bridge interface (§2).

A worker tab is a cloud chat session attached as a worker (``deepseek_1``,
``gemini1_1``, ``chatgpt_1``). Bridges report BUSY while processing a message
and IDLE otherwise, and expose attach / send / read / heartbeat.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum


class WorkerStatus(str, Enum):
    IDLE = "IDLE"
    BUSY = "BUSY"


class WorkerBridge(ABC):
    """Interface for a single attached cloud chat worker tab."""

    def __init__(self, worker_id: str, vendor: str) -> None:
        self.worker_id = worker_id
        self.vendor = vendor
        self._status: WorkerStatus = WorkerStatus.IDLE
        self._last_heartbeat: float = 0.0

    @property
    def status(self) -> WorkerStatus:
        """Current BUSY/IDLE status."""
        return self._status

    def _set_busy(self) -> None:
        self._status = WorkerStatus.BUSY

    def _set_idle(self) -> None:
        self._status = WorkerStatus.IDLE

    @abstractmethod
    def attach(self) -> bool:
        """Connect to the worker tab. Returns True on success."""

    @abstractmethod
    def _send_impl(self, message: str) -> str:
        """Send a prompt and return the reply (assumes attached)."""

    def send(self, message: str, attach_if_needed: bool = True) -> str:
        """Send a prompt, marking BUSY while processing, then IDLE.

        This is the canonical entry point guaranteeing the BUSY/IDLE contract.
        """
        if attach_if_needed and not self.status == WorkerStatus.BUSY:
            self.attach()
        self._set_busy()
        try:
            return self._send_impl(message)
        finally:
            self._set_idle()
            self._last_heartbeat = time.time()

    @abstractmethod
    def read(self) -> str:
        """Read the current last response from the tab."""

    def heartbeat(self) -> dict:
        """Report liveness + status for dashboard/widget polling."""
        return {
            "worker_id": self.worker_id,
            "vendor": self.vendor,
            "status": self._status.value,
            "last_heartbeat": self._last_heartbeat,
        }
