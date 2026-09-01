"""State file access (§4): ``state/PROJECT_STATE.json``.

One writer per state file; writes are atomic (tmp + rename) and guarded by
a cross-platform lock file. Components, campaigns and the control-center app
all read/write through this module.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

try:  # pragma: no cover - platform split
    import fcntl  # type: ignore

    def _lock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)

except ImportError:  # Windows
    import msvcrt  # type: ignore

    def _lock(fh) -> None:
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)


P_STATE = Path("state") / "PROJECT_STATE.json"
P_LOCK = Path("state") / "PROJECT_STATE.lock"

_EMPTY: dict = {
    "campaign": None,
    "components": {},
    "relay": [],
}


def set_state_dir(directory) -> None:
    """Redirect state file writes to ``directory`` (test isolation)."""
    global P_STATE, P_LOCK
    P_STATE = Path(directory) / "PROJECT_STATE.json"
    P_LOCK = Path(directory) / "PROJECT_STATE.lock"


def reset_state() -> None:
    """Reset the on-disk state to empty (used by tests)."""
    _write(_copy(_EMPTY))


def _copy(data: dict) -> dict:
    return json.loads(json.dumps(data))


def _read() -> dict:
    if not P_STATE.exists():
        return _copy(_EMPTY)
    return json.loads(P_STATE.read_text(encoding="utf-8"))


def _write(data: dict) -> None:
    P_STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(P_STATE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, P_STATE)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _locked_write(mutator) -> dict:
    """Run ``mutator(state) -> dict`` under the file lock, persisting result."""
    P_STATE.parent.mkdir(parents=True, exist_ok=True)
    with P_LOCK.open("a", encoding="utf-8") as lockfh:
        _lock(lockfh)
        state = _read()
        result = mutator(state)
        _write(state)
        return result


def get_state() -> dict:
    return _copy(_read())


def set_campaign(campaign: dict | None) -> None:
    def mut(st: dict) -> None:
        st["campaign"] = campaign
    _locked_write(mut)


def get_campaign() -> dict | None:
    return _read().get("campaign")


def upsert_component(comp: dict) -> None:
    def mut(st: dict) -> None:
        st.setdefault("components", {})[comp["id"]] = comp
    _locked_write(mut)


def get_components() -> dict:
    return dict(_read().get("components", {}))


def set_component_status(component_id: str, status: str, **extra) -> None:
    def mut(st: dict) -> None:
        comp = st.setdefault("components", {}).setdefault(component_id, {"id": component_id})
        comp["status"] = status
        comp.update(extra)
    _locked_write(mut)


def append_relay(entry: dict) -> None:
    def mut(st: dict) -> None:
        st.setdefault("relay", []).append(entry)
    _locked_write(mut)


def get_relay() -> list:
    return list(_read().get("relay", []))
