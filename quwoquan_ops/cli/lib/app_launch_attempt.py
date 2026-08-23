"""Machine-readable lifecycle receipt for one App compile/install/launch attempt."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable, Mapping
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
    "configuring",
    "configured",
    "launching",
    "launched",
)
TERMINAL_STATES = frozenset({"launched", "runtime_degraded", "failed", "stopped"})
_ALL_STATES = frozenset((*FORWARD_STATES, "runtime_degraded", "failed", "stopped"))

# 与 app_launch_manifest.yaml 的 launch_blockers 同源；launcher 侧 typed blocker
# 不经过服务端请求，因此不进任何服务 errors.yaml。
LAUNCH_BLOCKERS = frozenset(
    {
        "APP.LAUNCH.compile_failed",
        "APP.LAUNCH.install_failed",
        "APP.LAUNCH.launch_failed",
        "APP.LAUNCH.prod_debug_forbidden",
        "APP.LAUNCH.prod_artifact_required",
        "APP.LAUNCH.prod_artifact_invalid",
        "APP.LAUNCH.prod_hosted_flutter_forbidden",
        "APP.LAUNCH.ios_release_simulator_unsupported",
        "APP.LAUNCH.device_unavailable",
        "APP.LAUNCH.platform_unsupported",
        "APP.LAUNCH.receipt_invalid",
        "APP.LAUNCH.receipt_timeout",
        "APP.LAUNCH.runtime_dependency_unavailable",
        "APP.LAUNCH.runtime_config_missing",
        "APP.LAUNCH.runtime_config_activation_failed",
        "APP.WEB.recovery_unavailable",
    }
)
CONFIGURATION_STATES = ("unobserved", "pending_native", "complete", "invalid")
RUNTIME_HEALTH_STATUSES = ("unobserved", "healthy", "degraded", "unavailable")
RECOVERY_WEB_STATUSES = ("not_applicable", "unobserved", "available", "unavailable")


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
        "configurationState",
        "runtimeHealthStatus",
        "recoveryWebStatus",
        "recoveryWebEvidenceRef",
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
    first_blocker = str(value.get("firstBlocker") or "")
    if first_blocker and first_blocker not in LAUNCH_BLOCKERS:
        raise ValueError(f"App launch attempt firstBlocker is invalid: {first_blocker}")
    for field, allowed in (
        ("configurationState", CONFIGURATION_STATES),
        ("runtimeHealthStatus", RUNTIME_HEALTH_STATUSES),
        ("recoveryWebStatus", RECOVERY_WEB_STATUSES),
    ):
        if value.get(field) not in allowed:
            raise ValueError(f"App launch attempt {field} is invalid")
    if not isinstance(value.get("recoveryWebEvidenceRef"), str):
        raise TypeError("App launch attempt recoveryWebEvidenceRef is invalid")
    # 运行时健康只有真的启动过才可观测；否则 unobserved 是唯一诚实的取值。
    if value["runtimeHealthStatus"] != "unobserved" and "launched" not in observed:
        raise ValueError("App launch attempt runtime health requires launched")
    if value["recoveryWebStatus"] in {"available", "unavailable"} and not str(
        value["recoveryWebEvidenceRef"]
    ):
        raise ValueError("App launch attempt recovery web evidence is missing")
    if value["recoveryWebStatus"] not in {"available", "unavailable"} and str(
        value["recoveryWebEvidenceRef"]
    ):
        raise ValueError("App launch attempt recovery web evidence is unexpected")
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
        "configurationState": "unobserved",
        "runtimeHealthStatus": "unobserved",
        "recoveryWebStatus": "unobserved",
        "recoveryWebEvidenceRef": "",
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


def record_app_launch_attempt_observation(
    path: str | Path,
    *,
    configuration_state: str | None = None,
    runtime_health_status: str | None = None,
    recovery_web_status: str | None = None,
    recovery_web_evidence_ref: str | None = None,
    warning: str = "",
    first_blocker: str = "",
) -> dict[str, Any]:
    """Record configuration、runtime health 与恢复面观测，不发明生命周期跃迁。"""

    receipt_path = Path(path)
    payload = read_app_launch_attempt(receipt_path)
    for field, incoming in (
        ("configurationState", configuration_state),
        ("runtimeHealthStatus", runtime_health_status),
        ("recoveryWebStatus", recovery_web_status),
        ("recoveryWebEvidenceRef", recovery_web_evidence_ref),
    ):
        if incoming is not None:
            payload[field] = incoming
    if warning and warning not in payload["warnings"]:
        payload["warnings"].append(warning)
    if first_blocker and not payload["firstBlocker"]:
        payload["firstBlocker"] = first_blocker
    payload["updatedAt"] = utc_now()
    validated = validate_app_launch_attempt(payload)
    _atomic_write(receipt_path, validated)
    return validated


def wait_for_app_launch_attempt(
    path: str | Path,
    *,
    timeout_seconds: float = 900,
    poll_seconds: float = 0.2,
    watchdog: Callable[[], None] | None = None,
    watchdog_interval_seconds: float = 30,
) -> dict[str, Any]:
    """等待启动回执进入终态。

    编译、安装与启动可以占用十几分钟，运行时依赖在这段窗口里退出不会回写
    任何 receipt。`watchdog` 让调用方在等待期间按间隔复验运行期健康，从而
    把降级在窗口内就报出来，而不是等窗口结束后由用户从界面上发现。
    """
    deadline = time.monotonic() + timeout_seconds
    receipt_path = Path(path)
    last: dict[str, Any] | None = None
    next_watch = time.monotonic() + watchdog_interval_seconds
    while time.monotonic() < deadline:
        if watchdog is not None and time.monotonic() >= next_watch:
            watchdog()
            next_watch = time.monotonic() + watchdog_interval_seconds
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
