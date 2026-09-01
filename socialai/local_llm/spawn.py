"""Spawn local LLM service subprocesses + port allocation (§4).

Ports allocated from ``8100..8199`` are recorded in ``state/ports.json``.
Writes are atomic (tmp + rename) and guarded by a cross-platform lock file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


P_STATE = Path("state") / "ports.json"
P_LOCK = Path("state") / "ports.lock"
PORT_MIN, PORT_MAX = 8100, 8199


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _read_ports() -> dict:
    if not P_STATE.exists():
        return {}
    return json.loads(P_STATE.read_text(encoding="utf-8"))


def allocate_port(**meta) -> tuple[int, dict]:
    """Reserve and record an unused port in ``state/ports.json``."""
    P_STATE.parent.mkdir(parents=True, exist_ok=True)
    with P_LOCK.open("a", encoding="utf-8") as lockfh:
        _lock(lockfh)
        ports = _read_ports()
        used = set(int(p) for p in ports)
        free = next((p for p in range(PORT_MIN, PORT_MAX + 1) if p not in used), None)
        if free is None:
            raise RuntimeError("no free port in 8100..8199")
        ports[str(free)] = {**meta, "pid": os.getpid()}
        _atomic_write_json(P_STATE, ports)
        return free, ports


def release_port(port: int) -> None:
    """Remove a port from the allocation map."""
    with P_LOCK.open("a", encoding="utf-8") as lockfh:
        _lock(lockfh)
        ports = _read_ports()
        ports.pop(str(port), None)
        _atomic_write_json(P_STATE, ports)


def spawn_service(component_id: str = "local_1", mock: bool = True, model: str = "mock") -> int:
    """Launch a local LLM service as a subprocess; return its port."""
    port, _ = allocate_port(component_id=component_id)
    cmd = [
        sys.executable,
        "-m",
        "socialai.local_llm.service",
        "--port",
        str(port),
        "--id",
        component_id,
    ]
    if mock:
        cmd.append("--mock")
    else:
        cmd += ["--transformers", "--model", model]
    subprocess.Popen(cmd, close_fds=True)
    return port
