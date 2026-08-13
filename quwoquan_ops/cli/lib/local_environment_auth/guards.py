"""local_environment_auth 包输入校验与小工具（原单文件底部辅助函数逐字搬移）。"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

from .constants import _LOCAL_TARGETS


def _require_local_environment(environment: str, target_name: str) -> None:
    expected_target = _LOCAL_TARGETS.get(environment)
    if expected_target != target_name:
        raise ValueError(
            f"unsupported local environment target: environment={environment} target={target_name}"
        )


def _require_nonprod_target(environment: str, target_name: str) -> None:
    _require_local_environment(environment, target_name)
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError("nonprod acceptance identity is forbidden for Prod")


def _canonical_test_data_instance_id(value: str) -> str:
    instance_id = value.strip()
    if len(instance_id) != 64 or any(
        character not in "0123456789abcdef" for character in instance_id
    ):
        raise ValueError(
            "testDataInstanceId transport scope must be a lowercase SHA-256 hex digest"
        )
    return instance_id


def _canonical_actor_role(value: str) -> str:
    role = value.strip()
    allowed = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_")
    if not role or len(role) > 64 or any(character not in allowed for character in role):
        raise ValueError("local acceptance actor role is invalid")
    return role


def _required_string(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{context} missing required {field}")
    return value.strip()


def _require_mode(path: Path, expected: int) -> None:
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        raise RuntimeError(f"local environment auth secret file must use mode {expected:04o}: {path}")
