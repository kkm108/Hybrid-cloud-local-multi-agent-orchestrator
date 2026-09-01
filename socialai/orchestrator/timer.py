"""Timer component scheduler (T08).

A campaign may declare a ``timer`` component with ``interval_s`` and a
``trigger`` sent to its ``assigned_ai`` on every interval. The scheduler uses
an injectable clock so behaviour is deterministic under test (FakeClock), and
exposes ``start()``/``stop()`` for lifecycle. ``stop()`` is the kill-switch
path and always leaves the scheduler in a clean cancelled state (it survives
a campaign stop without raising).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

FireHandler = Callable[[str, str], None]  # (assigned_ai, trigger)


class TimerScheduler:
    """Fires registered timers on a repeating interval."""

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        on_fire: FireHandler | None = None,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._on_fire = on_fire
        self._timers: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._cancelled = False
        self._thread: threading.Thread | None = None

    def add(self, timer_id: str, interval_s: float, trigger: str, assigned_ai: str) -> None:
        with self._lock:
            self._timers[timer_id] = {
                "interval_s": interval_s,
                "trigger": trigger,
                "assigned_ai": assigned_ai,
                "next_fire": self._clock() + interval_s,
            }

    def remove(self, timer_id: str) -> None:
        with self._lock:
            self._timers.pop(timer_id, None)

    def clear(self) -> None:
        """Drop all timers (used by the kill switch)."""
        with self._lock:
            self._timers.clear()

    @property
    def timers(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self._timers.items()}

    def tick(self, now: float | None = None) -> list[tuple[str, str, str]]:
        """Fire any due timers now. Returns [(timer_id, assigned_ai, trigger)].

        Pure and clock-driven, so tests can advance a FakeClock and call tick().
        """
        now = now if now is not None else self._clock()
        fired: list[tuple[str, str, str]] = []
        with self._lock:
            due = [
                (tid, t)
                for tid, t in self._timers.items()
                if now >= t["next_fire"]
            ]
            for tid, t in due:
                # Reschedule to the next interval boundary (catch-up once).
                while t["next_fire"] <= now:
                    t["next_fire"] += t["interval_s"]
                fired.append((tid, t["assigned_ai"], t["trigger"]))
        for tid, ai, trigger in fired:
            if self._on_fire is not None:
                self._on_fire(ai, trigger)
        return fired

    def start(self) -> None:
        """Begin the background firing loop (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._cancelled = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._cancelled:
            try:
                self.tick()
                self._sleep(0.5)
            except Exception:
                # Never let a callback failure kill the scheduler loop.
                self._sleep(0.5)

    def stop(self) -> None:
        """Cancel all timers and join the loop. Always safe to call."""
        self._cancelled = True
        self.clear()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
