"""Environment Patrol 独占执行与本地 runtime 使用锁。"""
from __future__ import annotations

import atexit
import sys
from typing import Any

from quwoquan_ops.cli.lib.local_runtime_reservation import (
    acquire_local_runtime_use_lock,
)
from quwoquan_ops.cli.lib.patrol_execution_lock import (
    acquire_patrol_execution_lock as _acquire_patrol_execution_lock,
)

from .session import _is_local_target, _local_target_for_environment_alias


def acquire_patrol_runtime_locks(*, env_name: str, target: str) -> bool:
    """获取本轮 Patrol 需要的锁；失败时保持原入口的 typed gate 行为。"""
    execution_lock: Any | None = None
    runtime_use_lock: Any | None = None
    try:
        execution_lock = _acquire_patrol_execution_lock(
            env_name=env_name,
            target=target,
        )
        atexit.register(execution_lock.close)
        if _is_local_target(env_name):
            runtime_use_lock = acquire_local_runtime_use_lock(
                target=_local_target_for_environment_alias(env_name),
                purpose="environment-patrol-smoke",
            )
            atexit.register(runtime_use_lock.close)
    except RuntimeError as exc:
        if runtime_use_lock is not None:
            runtime_use_lock.close()
        if execution_lock is not None:
            execution_lock.close()
        print(f"GATE_BLOCK: {exc}", file=sys.stderr)
        return False
    return True
