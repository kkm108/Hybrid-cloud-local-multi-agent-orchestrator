"""Playwright adapter for real browser worker tabs (``live`` marker).

A skeleton native bridge that drives a real vendor chat tab via Playwright.
Selectors for each vendor live in ``workers/selectors/<vendor>.yaml``
(input box, send button, last-message). Playwright is imported lazily so
importing this module never requires the ``live`` extra.

Real browser automation is exercised only by ``live``-marked tests.
"""

from __future__ import annotations

from pathlib import Path

from .bridge import WorkerBridge

SELECTORS_DIR = Path(__file__).resolve().parent / "selectors"


def _load_selectors(vendor: str) -> dict:
    """Parse a flat ``key: value`` selector YAML file without pyyaml."""
    path = SELECTORS_DIR / f"{vendor}.yaml"
    selectors: dict[str, str] = {}
    if not path.is_file():
        return selectors
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        selectors[key.strip()] = value.strip()
    return selectors


class PlaywrightAdapter(WorkerBridge):
    """Drives a real cloud chat tab (deepseek/gemini/chatgpt) via Playwright."""

    def __init__(self, worker_id: str, vendor: str, **_) -> None:
        super().__init__(worker_id, vendor)
        self._selectors = _load_selectors(vendor)
        self._page = None
        self._attached = False

    @property
    def selectors(self) -> dict:
        return dict(self._selectors)

    def attach(self) -> bool:
        import importlib.util

        if importlib.util.find_spec("playwright") is None:
            raise RuntimeError("playwright not installed (extra `live`)")
        # Skeleton: a real adapter would launch a browser and open the vendor tab.
        self._attached = True
        return True

    def _send_impl(self, message: str) -> str:
        # Skeleton: real typing/sending goes here when driven live.
        return f"live:{self.worker_id}:{message}"

    def read(self) -> str:
        return f"live:{self.worker_id}:last-message"

    @property
    def attached(self) -> bool:
        return self._attached
