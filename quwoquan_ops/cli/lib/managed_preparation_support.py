"""managed preparation 的 receipt、设备与 runtime 准备支撑职责。

本模块是 ``managed_preparation`` 的内部职责拆分；稳定 public import 仍由原模块
re-export。所有 stackctl 协作符号继续经函数内延迟导入访问，以保持既有 patch 面。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

MANAGED_PREPARATION_SCHEMA = "quwoquan_ops.app_managed_preparation.v1"

# 四个码已在 canonical metadata 注册；代码内按注册字面量使用。
MANAGED_RUNTIME_UNAVAILABLE = "APP.PREPARATION.runtime_unavailable"
MANAGED_CONTENT_BINDING_UNAVAILABLE = "APP.PREPARATION.content_binding_unavailable"
MANAGED_STRICT_PREFLIGHT_FAILED = "APP.PREPARATION.strict_preflight_failed"
MANAGED_RECEIPT_INVALID = "APP.PREPARATION.receipt_invalid"

MANAGED_PREPARATION_TARGETS = ("alpha-local",)

_MANAGED_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "target",
        "environment",
        "platform",
        "deviceId",
        "runtimeIdentity",
        "consumerId",
        "consumerLeaseId",
        "androidReversePorts",
        "androidReverseOwnedPorts",
        "deviceTrustReceiptRef",
        "deviceTrustReceiptDigest",
        "contentBinding",
        "strictPreflightReceiptRef",
        "strictPreflightReceiptDigest",
        "strictContentPreflightReceiptRef",
        "strictContentPreflightReceiptDigest",
        "createdAt",
        "status",
        "firstBlocker",
    }
)

_CONTENT_BINDING_FIELDS = frozenset(
    {
        "releaseId",
        "verifyRunId",
        "manifestDigest",
        "readinessPhase",
        "readinessReceiptRef",
        "readinessReceiptDigest",
    }
)


class ManagedPreparationBlocked(RuntimeError):
    """typed 阻断：携带 canonical blocker 码与诊断明细。"""

    def __init__(self, blocker: str, details: list[str]) -> None:
        super().__init__(blocker + ": " + "; ".join(details))
        self.blocker = blocker
        self.details = list(details)


def _managed_file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _managed_android_adb_reverse_ports(device_id: str) -> set[int]:
    """读取准备前 same-port reverse 集合，用于精确交接 cleanup 所有权。"""

    adb = shutil.which("adb")
    if not adb:
        raise RuntimeError("adb not found in PATH")
    completed = subprocess.run(
        [adb, "-s", str(device_id), "reverse", "--list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "cannot inspect existing adb reverse mappings: "
            + (detail or "unknown adb failure")
        )
    ports: set[int] = set()
    for line in completed.stdout.splitlines():
        endpoints = [part for part in line.split() if part.startswith("tcp:")]
        if len(endpoints) < 2 or endpoints[-2] != endpoints[-1]:
            continue
        try:
            ports.add(int(endpoints[-1].removeprefix("tcp:")))
        except ValueError:
            continue
    return ports


def _valid_runtime_identity(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "startupAttemptId",
        "composeProject",
        "composeDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "reused",
        "replaced",
    }:
        return False
    if not all(
        isinstance(value.get(field), str) and str(value[field]).strip()
        for field in ("startupAttemptId", "composeProject")
    ):
        return False
    if not all(
        isinstance(value.get(field), str)
        and _MANAGED_DIGEST_RE.fullmatch(str(value[field])) is not None
        for field in ("composeDigest", "configurationDigest", "providerRuntimeDigest")
    ):
        return False
    return all(type(value.get(field)) is bool for field in ("reused", "replaced"))


def _valid_content_binding(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != _CONTENT_BINDING_FIELDS:
        return False
    return (
        all(
            isinstance(value.get(field), str) and str(value[field]).strip()
            for field in ("releaseId", "verifyRunId")
        )
        and _MANAGED_DIGEST_RE.fullmatch(str(value.get("manifestDigest") or ""))
        is not None
        and value.get("readinessPhase") == "research"
        and isinstance(value.get("readinessReceiptRef"), str)
        and bool(str(value["readinessReceiptRef"]).strip())
        and _MANAGED_DIGEST_RE.fullmatch(
            str(value.get("readinessReceiptDigest") or "")
        )
        is not None
    )


def _sanitize_blocked_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("target") != "alpha-local":
        receipt["target"] = ""
    if receipt.get("environment") != "alpha":
        receipt["environment"] = ""
    if receipt.get("platform") not in {"android", "ios"}:
        receipt["platform"] = ""
    for field in ("deviceId", "consumerId"):
        if not isinstance(receipt.get(field), str):
            receipt[field] = ""
    if not _valid_runtime_identity(receipt.get("runtimeIdentity")):
        receipt["runtimeIdentity"] = {}
    if not _valid_content_binding(receipt.get("contentBinding")):
        receipt["contentBinding"] = {}
    for field in (
        "consumerLeaseId",
        "deviceTrustReceiptDigest",
        "strictPreflightReceiptDigest",
        "strictContentPreflightReceiptDigest",
    ):
        value = str(receipt.get(field) or "")
        if value and _MANAGED_DIGEST_RE.fullmatch(value) is None:
            receipt[field] = ""
    for field in (
        "androidReversePorts",
        "androidReverseOwnedPorts",
        "deviceTrustReceiptRef",
        "strictPreflightReceiptRef",
        "strictContentPreflightReceiptRef",
    ):
        if not isinstance(receipt.get(field), str):
            receipt[field] = ""
    trust_ref = str(receipt.get("deviceTrustReceiptRef") or "")
    trust_digest = str(receipt.get("deviceTrustReceiptDigest") or "")
    if bool(trust_ref) != bool(trust_digest):
        receipt["deviceTrustReceiptRef"] = ""
        receipt["deviceTrustReceiptDigest"] = ""


def _validate_prepared_receipt(payload: Mapping[str, Any]) -> None:
    if payload.get("target") != "alpha-local" or payload.get("environment") != "alpha":
        raise ValueError("prepared managed preparation target/environment is invalid")
    if payload.get("platform") not in {"android", "ios"}:
        raise ValueError("prepared managed preparation platform is invalid")
    if not all(
        isinstance(payload.get(field), str) and str(payload[field]).strip()
        for field in ("deviceId", "consumerId")
    ):
        raise ValueError("prepared managed preparation string identity is incomplete")
    if not _valid_runtime_identity(payload.get("runtimeIdentity")):
        raise ValueError("prepared managed preparation runtimeIdentity is invalid")
    if _MANAGED_DIGEST_RE.fullmatch(str(payload.get("consumerLeaseId") or "")) is None:
        raise ValueError("prepared managed preparation consumerLeaseId is invalid")
    reverse_ports = str(payload.get("androidReversePorts") or "")
    owned_ports = str(payload.get("androidReverseOwnedPorts") or "")
    port_pattern = r"[1-9][0-9]*(?:,[1-9][0-9]*)*"
    if payload.get("platform") == "android":
        if re.fullmatch(port_pattern, reverse_ports) is None:
            raise ValueError("prepared Android managed preparation transport is invalid")
        canonical_reverse = ",".join(
            str(value)
            for value in sorted({int(value) for value in reverse_ports.split(",")})
        )
        if reverse_ports != canonical_reverse:
            raise ValueError("prepared Android managed preparation transport is not canonical")
    elif reverse_ports or owned_ports:
        raise ValueError("prepared non-Android managed preparation cannot own reverse ports")
    if owned_ports and re.fullmatch(port_pattern, owned_ports) is None:
        raise ValueError("prepared managed preparation reverse ownership is invalid")
    canonical_owned = (
        ",".join(
            str(value)
            for value in sorted({int(value) for value in owned_ports.split(",")})
        )
        if owned_ports
        else ""
    )
    if owned_ports != canonical_owned:
        raise ValueError("prepared managed preparation reverse ownership is not canonical")
    if owned_ports and not set(owned_ports.split(",")) <= set(reverse_ports.split(",")):
        raise ValueError("managed preparation reverse ownership exceeds transport ports")
    trust_ref = str(payload.get("deviceTrustReceiptRef") or "")
    trust_digest = str(payload.get("deviceTrustReceiptDigest") or "")
    if bool(trust_ref) != bool(trust_digest) or (
        trust_digest and _MANAGED_DIGEST_RE.fullmatch(trust_digest) is None
    ):
        raise ValueError("prepared managed preparation trust identity is invalid")
    if not _valid_content_binding(payload.get("contentBinding")):
        raise ValueError("prepared managed preparation contentBinding is invalid")
    for ref_field, digest_field, label in (
        (
            "strictPreflightReceiptRef",
            "strictPreflightReceiptDigest",
            "strict debug preflight",
        ),
        (
            "strictContentPreflightReceiptRef",
            "strictContentPreflightReceiptDigest",
            "strict content preflight",
        ),
    ):
        if not str(payload.get(ref_field) or "") or (
            _MANAGED_DIGEST_RE.fullmatch(str(payload.get(digest_field) or ""))
            is None
        ):
            raise ValueError(
                f"prepared managed preparation {label} identity is invalid"
            )


def _write_managed_preparation_receipt(
    path: Path,
    payload: Mapping[str, Any],
) -> str:
    """receipt-first 私有落盘（0600），返回文件字节 sha256。"""

    if set(payload) != _RECEIPT_FIELDS:
        raise ValueError("managed preparation receipt fields mismatch")
    if payload["status"] not in {"prepared", "blocked"}:
        raise ValueError("managed preparation receipt status is invalid")
    if payload["status"] == "blocked" and not str(payload["firstBlocker"] or ""):
        raise ValueError("blocked managed preparation receipt requires firstBlocker")
    if payload["status"] == "prepared" and str(payload["firstBlocker"] or ""):
        raise ValueError("prepared managed preparation receipt cannot carry a blocker")
    if payload["status"] == "prepared":
        _validate_prepared_receipt(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, path)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _managed_device_identity(*, device_id: str, platform: str) -> dict[str, str]:
    """exact device 解析：必须是当前已连接的 iOS/Android 设备。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    normalized_device = str(device_id or "").strip()
    if not normalized_device:
        raise ManagedPreparationBlocked(
            MANAGED_RUNTIME_UNAVAILABLE,
            ["managed preparation requires an explicit device id"],
        )
    device = _stackctl.find_device(normalized_device, include_desktop=False)
    if device is None:
        raise ManagedPreparationBlocked(
            MANAGED_RUNTIME_UNAVAILABLE,
            [f"Flutter device {normalized_device!r} is not currently connected"],
        )
    device_kind = _stackctl.detect_device_kind(
        normalized_device,
        target_platform=str(device.get("targetPlatform", "")),
        emulator=bool(device.get("emulator", False)),
    )
    if device_kind.startswith("ios-"):
        base_platform = "ios"
        lease_platform = device_kind
        trust_platform = "ios-simulator" if device_kind == "ios-simulator" else ""
    elif device_kind.startswith("android"):
        base_platform = "android"
        lease_platform = "android"
        trust_platform = (
            "android-emulator" if device_kind == "android_emulator" else ""
        )
    else:
        raise ManagedPreparationBlocked(
            MANAGED_RUNTIME_UNAVAILABLE,
            [
                f"Flutter device {normalized_device!r} has unsupported kind "
                f"{device_kind!r}; managed preparation supports iOS/Android only"
            ],
        )
    requested_platform = str(platform or "").strip().lower()
    if requested_platform and requested_platform != base_platform:
        raise ManagedPreparationBlocked(
            MANAGED_RUNTIME_UNAVAILABLE,
            [
                f"requested platform {requested_platform!r} conflicts with the "
                f"connected device platform {base_platform!r}"
            ],
        )
    return {
        "deviceId": normalized_device,
        "deviceKind": device_kind,
        "platform": base_platform,
        "leasePlatform": lease_platform,
        "trustPlatform": trust_platform,
    }


def _managed_runtime_result(
    *,
    reused: bool,
    startup_attempt: Mapping[str, Any],
    runtime: Mapping[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "reused": reused,
        "replaced": False,
        "warnings": list(warnings),
        "startupAttempt": dict(startup_attempt),
        "runtime": dict(runtime),
    }


def _managed_inspect_running_full_runtime(
    *,
    environment: str,
    target: str,
    immutable_attempt: Mapping[str, Any] | None,
    workspace_snapshot: Mapping[str, Any],
    report_dir: Path | None = None,
) -> dict[str, Any] | None:
    """复用 exact healthy full runtime；immutable 与 mutable 共用 canonical readback。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    if immutable_attempt is None:
        resumed, warnings = _stackctl._dev_session_resume_running_mutable_runtime(
            environment=environment,
            target=target,
            workspace_snapshot=workspace_snapshot,
            required_running_services=frozenset(),
        )
        if resumed is not None:
            return _managed_runtime_result(
                reused=True,
                startup_attempt=dict(resumed.get("startupAttempt") or {}),
                runtime=dict(resumed.get("runtime") or {}),
                warnings=list(warnings),
            )
    else:
        try:
            mutable = _stackctl.load_test_live_startup_attempt(target)
        except (OSError, RuntimeError, TypeError, ValueError):
            mutable = None
        if isinstance(mutable, Mapping) and mutable.get("status") == "running":
            resumed, warnings = _stackctl._dev_session_resume_running_mutable_runtime(
                environment=environment,
                target=target,
                workspace_snapshot=workspace_snapshot,
                required_running_services=frozenset(),
            )
            if resumed is None:
                raise RuntimeError("running mutable full runtime could not be inspected")
            return _managed_runtime_result(
                reused=True,
                startup_attempt=dict(resumed.get("startupAttempt") or {}),
                runtime=dict(resumed.get("runtime") or {}),
                warnings=list(warnings),
            )

    if not (
        isinstance(immutable_attempt, Mapping)
        and immutable_attempt.get("status") == "running"
        and immutable_attempt.get("workload") == "full"
    ):
        return None
    snapshot = _stackctl.active_deployment_candidate_snapshot(target)
    if snapshot is None:
        raise RuntimeError(
            "running immutable full runtime has no active candidate snapshot"
        )
    expected_identity = _stackctl._fixed_candidate_runtime_identity(
        snapshot,
        environment_name=environment,
        target_name=target,
    )
    mismatches = _stackctl._runtime_identity_mismatches(
        immutable_attempt,
        expected_identity,
    )
    if mismatches:
        raise RuntimeError(
            "running immutable full runtime differs from the active candidate: "
            + ", ".join(mismatches)
        )
    _stackctl.assert_active_deployment_candidate_snapshot(dict(snapshot))
    image_composition = expected_identity.get("imageComposition")
    expected_descriptors = (
        image_composition.get("images")
        if isinstance(image_composition, Mapping)
        else None
    )
    if not isinstance(expected_descriptors, Mapping) or not expected_descriptors:
        raise RuntimeError("running immutable full runtime image identity is incomplete")
    canonical_services = set(_stackctl.runtime_image_owner_names(_stackctl.ROOT))
    if set(str(service) for service in expected_descriptors) != canonical_services:
        raise RuntimeError(
            "running immutable full runtime first-party image closure drifted"
        )
    expected_images: dict[str, str] = {}
    for raw_service, raw_descriptor in sorted(expected_descriptors.items()):
        service = str(raw_service or "").strip()
        descriptor = raw_descriptor if isinstance(raw_descriptor, Mapping) else {}
        image_id = str(descriptor.get("ref") or "").strip()
        if (
            not service
            or _MANAGED_DIGEST_RE.fullmatch(image_id) is None
            or raw_service != service
            or descriptor.get("ref") != image_id
        ):
            raise RuntimeError(
                "running immutable full runtime image identity is incomplete"
            )
        expected_images[service] = image_id

    compose_project = str(immutable_attempt.get("composeProject") or "").strip()
    if not compose_project or immutable_attempt.get("composeProject") != compose_project:
        raise RuntimeError("running immutable full runtime Compose project is missing")
    lookup = _stackctl.run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={compose_project}",
            "--filter",
            "status=running",
            "--format",
            "{{.ID}}",
        ],
        timeout_seconds=30,
    )
    if lookup.returncode != 0:
        detail = (lookup.stderr or lookup.stdout or "").strip()
        raise RuntimeError(
            "running immutable full runtime Docker inventory failed: "
            + (detail or f"exit={lookup.returncode}")
        )
    container_ids = [line.strip() for line in lookup.stdout.splitlines() if line.strip()]
    if not container_ids or len(container_ids) != len(set(container_ids)):
        raise RuntimeError(
            "running immutable full runtime Docker inventory is empty or ambiguous"
        )
    inspected = _stackctl.run(
        ["docker", "inspect", *container_ids],
        timeout_seconds=30,
    )
    if inspected.returncode != 0:
        detail = (inspected.stderr or inspected.stdout or "").strip()
        raise RuntimeError(
            "running immutable full runtime Docker inspect failed: "
            + (detail or f"exit={inspected.returncode}")
        )
    try:
        inspection = json.loads(inspected.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(
            "running immutable full runtime Docker inspect is not valid JSON"
        ) from exc
    if not isinstance(inspection, list) or len(inspection) != len(container_ids):
        raise RuntimeError(
            "running immutable full runtime Docker inspect closure drifted"
        )
    actual_images: dict[str, set[str]] = {}
    observed_ids: set[str] = set()
    for item in inspection:
        if not isinstance(item, Mapping):
            raise RuntimeError(
                "running immutable full runtime Docker inspect entry is invalid"
            )
        container_id = str(item.get("Id") or "").strip()
        config = item.get("Config")
        labels = config.get("Labels") if isinstance(config, Mapping) else None
        if (
            not container_id
            or not any(container_id.startswith(expected) for expected in container_ids)
            or container_id in observed_ids
            or not isinstance(labels, Mapping)
            or labels.get("com.docker.compose.project") != compose_project
        ):
            raise RuntimeError(
                "running immutable full runtime Docker project label drifted"
            )
        observed_ids.add(container_id)
        service = str(labels.get("com.docker.compose.service") or "").strip()
        image_id = str(item.get("Image") or "").strip()
        if not service or _MANAGED_DIGEST_RE.fullmatch(image_id) is None:
            raise RuntimeError(
                "running immutable full runtime Docker service/image identity is invalid"
            )
        actual_images.setdefault(service, set()).add(image_id)
    if len(observed_ids) != len(container_ids):
        raise RuntimeError(
            "running immutable full runtime Docker inspect identity drifted"
        )

    runtime_images: dict[str, dict[str, str]] = {}
    for service, expected_image_id in sorted(expected_images.items()):
        replicas = actual_images.get(service, set())
        if not replicas:
            raise RuntimeError(
                f"running immutable full runtime is missing service: {service}"
            )
        if len(replicas) != 1:
            raise RuntimeError(
                f"running immutable full runtime replicas drifted: {service}"
            )
        actual_image_id = next(iter(replicas))
        if actual_image_id != expected_image_id:
            raise RuntimeError(
                f"running immutable full runtime image drifted: {service}"
            )
        runtime_images[service] = {"runtimeImageId": actual_image_id}
    health = _stackctl.command_health(
        __import__("argparse").Namespace(
            command="health",
            target=target,
            scope="full",
            workload="full",
            read_only=True,
            output_format="json",
            report_dir=str((report_dir or Path(".")).resolve()),
        )
    )
    if int(health.get("exitCode", 2)) != 0:
        raise RuntimeError(
            "running immutable full runtime failed canonical full health readback: "
            + "; ".join(str(item) for item in health.get("details") or [])
        )
    return _managed_runtime_result(
        reused=True,
        startup_attempt=immutable_attempt,
        runtime={"images": runtime_images, "health": dict(health)},
        warnings=[],
    )


def _managed_runtime_ready(
    *,
    environment: str,
    target: str,
    report_dir: Path,
) -> dict[str, Any]:
    """启动或复用 exact healthy full runtime；只修复专用旧 receipt 类型。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    replacement_happened = False
    try:
        with _stackctl._local_stack_operation_lock(target):
            try:
                active_attempt, conflict = _stackctl._dev_session_runtime_preflight(
                    topology=_stackctl.load_environment_topology(),
                    target=target,
                )
            except _stackctl.InadmissibleCurrentTestLiveReceipt as exc:
                try:
                    stale_receipt = _stackctl._bounded_replace_stale_managed_receipt(
                        target=target
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as replacement_exc:
                    raise ManagedPreparationBlocked(
                        MANAGED_RUNTIME_UNAVAILABLE,
                        [str(exc), str(replacement_exc)],
                    ) from replacement_exc
                if not str(stale_receipt.get("attemptId") or "").strip():
                    raise ManagedPreparationBlocked(
                        MANAGED_RUNTIME_UNAVAILABLE,
                        ["bounded-replaced stale receipt has no attempt identity"],
                    )
                replacement_happened = True
                try:
                    active_attempt, conflict = _stackctl._dev_session_runtime_preflight(
                        topology=_stackctl.load_environment_topology(),
                        target=target,
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as retry_exc:
                    raise ManagedPreparationBlocked(
                        MANAGED_RUNTIME_UNAVAILABLE,
                        [str(retry_exc)],
                    ) from retry_exc
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise ManagedPreparationBlocked(
                    MANAGED_RUNTIME_UNAVAILABLE,
                    [str(exc)],
                ) from exc
            if conflict is not None:
                raise ManagedPreparationBlocked(
                    MANAGED_RUNTIME_UNAVAILABLE,
                    [
                        "another runtime workload occupies the target: "
                        f"target={conflict.get('target')} "
                        f"workload={conflict.get('workload')} "
                        f"attemptId={conflict.get('attemptId')}"
                    ],
                )
            try:
                workspace_snapshot = _stackctl._mutable_workspace_snapshot()
            except (OSError, RuntimeError, ValueError):
                workspace_snapshot = {}
            try:
                reused = _stackctl._managed_inspect_running_full_runtime(
                    environment=environment,
                    target=target,
                    immutable_attempt=active_attempt,
                    workspace_snapshot=workspace_snapshot,
                    report_dir=report_dir / "runtime-reuse-health",
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise ManagedPreparationBlocked(
                    MANAGED_RUNTIME_UNAVAILABLE,
                    [str(exc)],
                ) from exc
            if reused is not None:
                return {**reused, "replaced": replacement_happened}

            started = _stackctl._start_mutable_test_live_runtime(
                environment=environment,
                target=target,
                report_dir=report_dir / "runtime-start",
                workspace_snapshot=workspace_snapshot,
            )
            if int(started.get("exitCode", 2)) != 0:
                raise ManagedPreparationBlocked(
                    MANAGED_RUNTIME_UNAVAILABLE,
                    [
                        "mutable full runtime start failed: "
                        + str(started.get("blockerKind") or "unknown"),
                        *(str(item) for item in started.get("details") or []),
                    ],
                )
            try:
                validated = _stackctl._managed_inspect_running_full_runtime(
                    environment=environment,
                    target=target,
                    immutable_attempt=None,
                    workspace_snapshot=workspace_snapshot,
                    report_dir=report_dir / "runtime-start-health",
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                validated = None
                validation_detail = str(exc)
            else:
                validation_detail = ""
            started_attempt = dict(started.get("startupAttempt") or {})
            validated_attempt = dict((validated or {}).get("startupAttempt") or {})
            if (
                validated is None
                or validated_attempt.get("attemptId")
                != started_attempt.get("attemptId")
            ):
                raise ManagedPreparationBlocked(
                    MANAGED_RUNTIME_UNAVAILABLE,
                    [
                        "started runtime identity could not be re-verified: "
                        + (validation_detail or "attempt identity changed after start")
                    ],
                )
            return {
                **validated,
                "reused": False,
                "replaced": replacement_happened,
            }
    except _stackctl.LocalOperationLockBusyError as exc:
        raise ManagedPreparationBlocked(
            MANAGED_RUNTIME_UNAVAILABLE,
            [f"target runtime operation lock is busy: {exc}"],
        ) from exc
