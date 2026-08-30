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

from .app_launch_manifest_schema import validate_schema_document
from .generated.app_launch_contract import (
    APP_LAUNCH_ATTEMPT_FORWARD_STATES,
    APP_LAUNCH_ATTEMPT_REQUIRED_FIELDS,
    APP_LAUNCH_ATTEMPT_STATUSES,
    APP_LAUNCH_ATTEMPT_TERMINAL_STATES,
    APP_LAUNCH_MANIFEST,
    BUILD_PROFILE_ENVIRONMENTS,
    LAUNCH_PROVENANCES,
    RUNTIME_CONFIG_SUPPLY_MODES,
    SCHEMA_VALUES,
    TARGET_ENVIRONMENT,
)
from .generated.app_launch_contract import (
    LAUNCH_BLOCKERS as GENERATED_LAUNCH_BLOCKERS,
)

SCHEMA = SCHEMA_VALUES["app_launch_attempt"]
FORWARD_STATES = tuple(APP_LAUNCH_ATTEMPT_FORWARD_STATES)
TERMINAL_STATES = frozenset(("launched", *APP_LAUNCH_ATTEMPT_TERMINAL_STATES))
_ALL_STATES = frozenset(APP_LAUNCH_ATTEMPT_STATUSES)
LAUNCH_BLOCKERS = frozenset(GENERATED_LAUNCH_BLOCKERS)
_ATTEMPT_FIELDS = APP_LAUNCH_MANIFEST["schemas"]["app_launch_attempt"]["fields"]
CONFIGURATION_STATES = tuple(_ATTEMPT_FIELDS["configurationState"]["allowed_values"])
RUNTIME_HEALTH_STATUSES = tuple(_ATTEMPT_FIELDS["runtimeHealthStatus"]["allowed_values"])
RECOVERY_WEB_STATUSES = tuple(_ATTEMPT_FIELDS["recoveryWebStatus"]["allowed_values"])


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
    required = set(APP_LAUNCH_ATTEMPT_REQUIRED_FIELDS)
    if set(value) != required:
        raise ValueError("App launch attempt fields mismatch")
    schema_issues = validate_schema_document(
        value,
        "app_launch_attempt",
        contract=APP_LAUNCH_MANIFEST,
        field_path="appLaunchAttempt",
    )
    if schema_issues:
        raise ValueError("App launch attempt schema invalid: " + "; ".join(schema_issues))
    environment = str(value.get("environment") or "")
    target = str(value.get("target") or "")
    if TARGET_ENVIRONMENT.get(target) != environment:
        raise ValueError("App launch attempt target is invalid")
    expected_profile = next(
        (
            profile
            for profile, environments in BUILD_PROFILE_ENVIRONMENTS.items()
            if environment in environments
        ),
        "",
    )
    if value.get("buildProfile") != expected_profile:
        raise ValueError("App launch attempt build profile is invalid")
    if value.get("launchProvenance") not in LAUNCH_PROVENANCES:
        raise ValueError("App launch attempt launch provenance is invalid")
    if value.get("runtimeConfigSupplyMode") not in RUNTIME_CONFIG_SUPPLY_MODES:
        raise ValueError("App launch attempt runtime config supply mode is invalid")
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
    if "compiled" in observed and not str(value.get("artifactDigest") or ""):
        raise ValueError(
            "App launch attempt compiled transition requires artifactDigest"
        )
    terminal_identity = tuple(
        str(value.get(field) or "")
        for field in (
            "startupTerminalAttemptId",
            "startupTerminalEvidenceDigest",
            "startupTerminalEvidenceRef",
        )
    )
    if any(terminal_identity) and not all(terminal_identity):
        raise ValueError("App launch attempt startup terminal identity is partial")
    if all(terminal_identity) and "launching" not in observed:
        raise ValueError("App launch attempt startup terminal requires launching")
    for field in ("warnings", "logRefs"):
        if not isinstance(value.get(field), list) or not all(
            isinstance(item, str) for item in value[field]
        ):
            raise ValueError(f"App launch attempt {field} is invalid")
    first_blocker = str(value.get("firstBlocker") or "")
    if first_blocker and first_blocker not in LAUNCH_BLOCKERS:
        raise ValueError(f"App launch attempt firstBlocker is invalid: {first_blocker}")
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
    candidate_identity = tuple(
        str(value.get(field) or "")
        for field in (
            "candidateDigest",
            "artifactManifestDigest",
            "launcherHandoffDigest",
        )
    )
    if value["runMode"] == "release-artifact":
        if not all(candidate_identity):
            raise ValueError("Release App launch attempt candidate identity is incomplete")
    elif any(candidate_identity):
        raise ValueError("Non-release App launch attempt candidate identity is unexpected")
    if value["runMode"] in {"content-live", "ui-only"} and not value["nonPromotable"]:
        raise ValueError("test_live App launch attempt must be nonPromotable")
    return dict(value)


def create_app_launch_attempt(
    path: str | Path,
    *,
    environment: str,
    target: str,
    platform: str,
    build_profile: str,
    build_mode: str,
    run_mode: str,
    launch_provenance: str,
    runtime_config_supply_mode: str,
    runtime_config_trust_envelope_digest: str,
    runtime_config_package_digest: str,
    application_id: str,
    flutter_version: str,
    command_resolution_digest: str,
    device_id: str,
    artifact_digest: str = "",
    candidate_digest: str = "",
    artifact_manifest_digest: str = "",
    launcher_handoff_digest: str = "",
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
        "buildProfile": build_profile,
        "buildMode": build_mode,
        "runMode": run_mode,
        "launchProvenance": launch_provenance,
        "runtimeConfigSupplyMode": runtime_config_supply_mode,
        "artifactDigest": artifact_digest,
        "candidateDigest": candidate_digest,
        "artifactManifestDigest": artifact_manifest_digest,
        "launcherHandoffDigest": launcher_handoff_digest,
        "runtimeConfigTrustEnvelopeDigest": runtime_config_trust_envelope_digest,
        "runtimeConfigPackageDigest": runtime_config_package_digest,
        "applicationId": application_id,
        "flutterVersion": flutter_version,
        "commandResolutionDigest": command_resolution_digest,
        "launchDigest": launch_digest,
        "startupTerminalAttemptId": "",
        "startupTerminalEvidenceDigest": "",
        "startupTerminalEvidenceRef": "",
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
        incoming_artifact_digest = str(artifact_digest).strip()
        current_artifact_digest = str(payload.get("artifactDigest") or "")
        if (
            current_artifact_digest
            and incoming_artifact_digest != current_artifact_digest
        ):
            raise ValueError("App launch attempt artifactDigest is immutable")
        payload["artifactDigest"] = incoming_artifact_digest
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
    startup_terminal_attempt_id: str | None = None,
    startup_terminal_evidence_digest: str | None = None,
    startup_terminal_evidence_ref: str | None = None,
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
        ("startupTerminalAttemptId", startup_terminal_attempt_id),
        ("startupTerminalEvidenceDigest", startup_terminal_evidence_digest),
        ("startupTerminalEvidenceRef", startup_terminal_evidence_ref),
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
