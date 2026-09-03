"""Bounded launcher handoff and VM-service observation helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .activation import CanonicalExecutorError, bounded_payload
from .vm_service_info_file import (
    VmServiceInfoSecurityError,
    validate_private_vm_service_info_file,
)


def validated_vm_service_info_file(path: Path, *, allowed_root: Path) -> Path:
    try:
        return validate_private_vm_service_info_file(
            path,
            allowed_root=allowed_root,
        )
    except VmServiceInfoSecurityError as error:
        raise CanonicalExecutorError(str(error)) from error


def load_handoff(path: Path | None) -> dict[str, object]:
    try:
        if path is not None:
            payload = path.read_bytes()
        else:
            raw = os.environ.get("QWQ_LAUNCH_HANDOFF_JSON", "")
            if not raw:
                raise CanonicalExecutorError("canonical launcher handoff is missing")
            payload = raw.encode("utf-8")
        decoded = json.loads(
            bounded_payload(payload, "launcher handoff").decode("utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CanonicalExecutorError(
            f"launcher handoff is unreadable: {error}"
        ) from error
    if not isinstance(decoded, dict):
        raise CanonicalExecutorError("launcher handoff must be an object")
    return decoded


def flutter_daemon_app_id(line: str) -> str:
    """从 flutter daemon 事件行提取 appId；非 daemon 事件行返回空串。"""
    try:
        messages = json.loads(line)
    except json.JSONDecodeError:
        return ""
    if not isinstance(messages, list) or len(messages) != 1:
        return ""
    message = messages[0]
    if not isinstance(message, dict):
        return ""
    params = message.get("params")
    if not isinstance(params, dict):
        return ""
    app_id = params.get("appId")
    return app_id if isinstance(app_id, str) else ""


def is_flutter_app_started_event(line: str) -> bool:
    try:
        messages = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(messages, list) or len(messages) != 1:
        return False
    message = messages[0]
    if not isinstance(message, dict):
        return False
    params = message.get("params")
    if (
        not isinstance(params, dict)
        or not isinstance(params.get("appId"), str)
        or not params["appId"]
    ):
        return False
    if message.get("event") == "app.started":
        return True
    # Flutter 3.47 emits app.start before app.debugPort. Only the latter proves
    # that an attachable VM-service session exists.
    return (
        message.get("event") == "app.debugPort"
        and isinstance(params.get("wsUri"), str)
        and bool(params["wsUri"])
    )
