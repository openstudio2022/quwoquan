"""Machine-readable lifecycle receipt for one App compile/install/launch attempt."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA = "app-launch-attempt"
FORWARD_STATES = (
    "prepared",
    "compiling",
    "compiled",
    "installing",
    "installed",
    "launching",
    "launched",
)
TERMINAL_STATES = frozenset({"launched", "runtime_degraded", "failed", "stopped"})
_ALL_STATES = frozenset((*FORWARD_STATES, "runtime_degraded", "failed", "stopped"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def read_app_launch_attempt(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_app_launch_attempt(value)


def validate_app_launch_attempt(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("App launch attempt schema mismatch")
    required = {
        "schema",
        "attemptId",
        "environment",
        "target",
        "platform",
        "buildMode",
        "runMode",
        "artifactDigest",
        "launchDigest",
        "status",
        "transitions",
        "warnings",
        "firstBlocker",
        "deviceId",
        "logRefs",
        "updatedAt",
        "nonPromotable",
    }
    if set(value) != required:
        raise ValueError("App launch attempt fields mismatch")
    environment = str(value.get("environment") or "")
    target = str(value.get("target") or "")
    if environment not in {"alpha", "beta", "gamma", "prod"}:
        raise ValueError("App launch attempt environment is invalid")
    expected_target = f"{environment}-local" if environment != "prod" else target
    if target != expected_target or target not in {
        "alpha-local",
        "beta-local",
        "gamma-local",
        "prod-sim",
        "prod-hosted",
    }:
        raise ValueError("App launch attempt target is invalid")
    if value.get("platform") not in {"android", "ios"}:
        raise ValueError("App launch attempt platform is invalid")
    if value.get("buildMode") not in {"debug", "profile", "release"}:
        raise ValueError("App launch attempt build mode is invalid")
    if value.get("runMode") not in {"content-live", "ui-only", "release-artifact"}:
        raise ValueError("App launch attempt run mode is invalid")
    status = str(value.get("status") or "")
    if status not in _ALL_STATES:
        raise ValueError("App launch attempt status is invalid")
    transitions = value.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        raise ValueError("App launch attempt transitions are invalid")
    observed = [str(item.get("status") or "") for item in transitions if isinstance(item, dict)]
    if not observed or observed[-1] != status or observed[0] != "prepared":
        raise ValueError("App launch attempt transition tail mismatch")
    forward_positions = [FORWARD_STATES.index(item) for item in observed if item in FORWARD_STATES]
    if forward_positions != sorted(set(forward_positions)):
        raise ValueError("App launch attempt transition order is invalid")
    for field in ("warnings", "logRefs"):
        if not isinstance(value.get(field), list) or not all(
            isinstance(item, str) for item in value[field]
        ):
            raise ValueError(f"App launch attempt {field} is invalid")
    if not isinstance(value.get("nonPromotable"), bool):
        raise TypeError("App launch attempt promotability is invalid")
    return dict(value)


def create_app_launch_attempt(
    path: str | Path,
    *,
    environment: str,
    target: str,
    platform: str,
    build_mode: str,
    run_mode: str,
    device_id: str,
    artifact_digest: str = "",
    launch_digest: str = "",
    warnings: Iterable[str] = (),
    log_refs: Iterable[str] = (),
    attempt_id: str = "",
    non_promotable: bool | None = None,
) -> dict[str, Any]:
    now = utc_now()
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "attemptId": attempt_id or str(uuid4()),
        "environment": environment,
        "target": target,
        "platform": platform,
        "buildMode": build_mode,
        "runMode": run_mode,
        "artifactDigest": artifact_digest,
        "launchDigest": launch_digest,
        "status": "prepared",
        "transitions": [{"status": "prepared", "at": now}],
        "warnings": list(dict.fromkeys(str(item) for item in warnings if str(item))),
        "firstBlocker": "",
        "deviceId": device_id,
        "logRefs": list(dict.fromkeys(str(item) for item in log_refs if str(item))),
        "updatedAt": now,
        "nonPromotable": (
            run_mode != "release-artifact"
            if non_promotable is None
            else non_promotable
        ),
    }
    validated = validate_app_launch_attempt(payload)
    _atomic_write(Path(path), validated)
    return validated


def transition_app_launch_attempt(
    path: str | Path,
    status: str,
    *,
    first_blocker: str = "",
    warning: str = "",
    artifact_digest: str | None = None,
    launch_digest: str | None = None,
) -> dict[str, Any]:
    receipt_path = Path(path)
    payload = read_app_launch_attempt(receipt_path)
    current = str(payload["status"])
    if status not in _ALL_STATES:
        raise ValueError(f"App launch attempt status is invalid: {status}")
    if current in {"failed", "runtime_degraded", "stopped"}:
        raise ValueError(f"App launch attempt is already terminal: {current}")
    if status in FORWARD_STATES:
        if current not in FORWARD_STATES:
            raise ValueError(f"App launch attempt cannot advance from {current}")
        if FORWARD_STATES.index(status) != FORWARD_STATES.index(current) + 1:
            raise ValueError(f"App launch attempt transition {current} -> {status} is invalid")
    elif status == "runtime_degraded" and current != "launched":
        raise ValueError("runtime_degraded requires launched")
    elif status == "stopped" and current not in FORWARD_STATES:
        raise ValueError("stopped requires an active App launch attempt")
    if first_blocker and not payload["firstBlocker"]:
        payload["firstBlocker"] = first_blocker
    if warning and warning not in payload["warnings"]:
        payload["warnings"].append(warning)
    if artifact_digest is not None:
        payload["artifactDigest"] = artifact_digest
    if launch_digest is not None:
        payload["launchDigest"] = launch_digest
    now = utc_now()
    payload["status"] = status
    payload["updatedAt"] = now
    payload["transitions"].append({"status": status, "at": now})
    validated = validate_app_launch_attempt(payload)
    _atomic_write(receipt_path, validated)
    return validated


def record_app_launch_attempt_warning(
    path: str | Path,
    warning: str,
) -> dict[str, Any]:
    """Append runtime evidence without inventing a lifecycle transition."""

    receipt_path = Path(path)
    payload = read_app_launch_attempt(receipt_path)
    normalized = str(warning).strip()
    if normalized and normalized not in payload["warnings"]:
        payload["warnings"].append(normalized)
        payload["updatedAt"] = utc_now()
        validated = validate_app_launch_attempt(payload)
        _atomic_write(receipt_path, validated)
        return validated
    return payload


def wait_for_app_launch_attempt(
    path: str | Path,
    *,
    timeout_seconds: float = 900,
    poll_seconds: float = 0.2,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    receipt_path = Path(path)
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last = read_app_launch_attempt(receipt_path)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            time.sleep(poll_seconds)
            continue
        if last["status"] in TERMINAL_STATES:
            return last
        time.sleep(poll_seconds)
    status = str((last or {}).get("status") or "missing")
    raise TimeoutError(
        f"APP.LAUNCH.receipt_timeout: status={status} path={receipt_path}"
    )
