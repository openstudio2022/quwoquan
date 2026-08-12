"""Single-track lock for Flutter/Patrol build-workspace consumers."""

from __future__ import annotations

import datetime as dt
import fcntl
import os
from pathlib import Path
from typing import TextIO


REPO_ROOT = Path(__file__).resolve().parents[3]
PATROL_EXECUTION_LOCK = (
    REPO_ROOT
    / ".qwq_output"
    / "env"
    / "repo"
    / "local"
    / "locks"
    / "environment-patrol-smoke.lock"
)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def acquire_patrol_execution_lock(
    *,
    env_name: str,
    target: str,
    lock_path: Path = PATROL_EXECUTION_LOCK,
) -> TextIO:
    """Serialize Flutter builds that share the App build workspace."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.seek(0)
        holder = handle.read().strip() or "unknown"
        handle.close()
        raise RuntimeError(
            f"Patrol build workspace is already in use: {holder}",
        ) from error
    handle.seek(0)
    handle.truncate()
    handle.write(
        f"pid={os.getpid()} env={env_name.strip()} "
        f"target={target.strip()} startedAt={_utc_now()}\n",
    )
    handle.flush()
    os.fsync(handle.fileno())
    return handle
