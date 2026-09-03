"""stackctl managed preparation 状态机：设备/runtime/lease/trust/binding/preflight/receipt。

一键托管 `flutter run`（launcher dispatcher -> `QWQ_MANAGED_FLUTTER_ENTRY=1 run.sh`）
在 Flutter build 前必须先证明整条链路：exact device -> 启动/复用 alpha full
mutable runtime -> 真实 consumer lease/transport -> 以同一 lease 安装并验证
device trust -> 服务端 active release readback -> exact Research readiness 绑定 ->
严格 preflight（readiness 发现从 warning 升级为 typed blocker）-> private
managed preparation receipt（receipt-first，含 sha256）。

状态机不重复实现任何一步的业务判定，复用 dev-session / device-trust /
app-preflight 家族的同一实现；dev-session 既有路径不经过本模块，行为不变。
测试经 ``mock.patch.object(stackctl, ...)`` patch 协作符号，因此本模块符号
一律经函数内延迟导入 ``_stackctl`` 属性访问（含本模块符号互调）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.managed_preparation_support import (  # noqa: F401
    _CONTENT_BINDING_FIELDS,
    _MANAGED_DIGEST_RE,
    _RECEIPT_FIELDS,
    MANAGED_CONTENT_BINDING_UNAVAILABLE,
    MANAGED_CONTENT_PREFLIGHT_SCHEMA,
    MANAGED_PREPARATION_SCHEMA,
    MANAGED_PREPARATION_TARGETS,
    MANAGED_RECEIPT_INVALID,
    MANAGED_RUNTIME_UNAVAILABLE,
    MANAGED_STRICT_PREFLIGHT_FAILED,
    ManagedPreparationBlocked,
    _managed_android_adb_reverse_ports,
    _managed_device_identity,
    _managed_file_digest,
    _managed_inspect_running_full_runtime,
    _managed_runtime_ready,
    _sanitize_blocked_receipt,
    _valid_content_binding,
    _valid_runtime_identity,
    _validate_prepared_receipt,
    _write_managed_preparation_receipt,
)

_MANAGED_RESEARCH_READBACK_FIELDS = frozenset(
    {
        "releaseId",
        "manifestDigest",
        "subjectHash",
        "attestationIdHash",
        "signatureVerified",
        "researchBadgeVisible",
        "postIds",
        "entityRefs",
        "mediaAssetIds",
        "publicCdnDetected",
        "anonymousMediaUrlDetected",
    }
)


def _managed_readback_closure(payload: Mapping[str, Any], field: str) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"active release readback {field} must be an array of strings")
    items = [item.strip() for item in value]
    if not items or any(not item for item in items) or len(items) != len(set(items)):
        raise ValueError(
            f"active release readback {field} must contain unique non-empty strings"
        )
    return items


def _managed_active_release_readback(
    *,
    environment: str,
    startup_attempt_id: str,
) -> dict[str, Any]:
    """服务端 active release readback：精确校验 Research DTO，不猜目录 latest。

    Research 内容保持匿名隔离：凭证是白名单研究账号的内存态 session，只用于
    readback，不注入业务账号也不绕过登录。
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    credential = _stackctl.issue_research_consumer_credential(
        environment=environment,
        release_id="managed-preparation",
        verify_run_id=str(startup_attempt_id or "managed-preparation"),
    )
    session = _stackctl.LocalAcceptanceSession(
        owner_id="managed-preparation-readback",
        persona_id="research-consumer",
        access_token=str(credential["bearerToken"]),
    )
    payload = _stackctl.request_local_environment_json(
        str(credential["apiBaseUrl"]),
        path="/content/research/readback",
        session=session,
        method="GET",
        headers={
            "X-Research-Identity-Attestation": str(credential["attestationToken"]),
        },
    )
    if not isinstance(payload, Mapping) or set(payload) != _MANAGED_RESEARCH_READBACK_FIELDS:
        observed = (
            sorted(str(field) for field in payload)
            if isinstance(payload, Mapping)
            else []
        )
        raise ValueError(
            "active release readback field set drifted; observed=" + ",".join(observed)
        )
    release_id = str(payload.get("releaseId") or "").strip()
    manifest_digest = str(payload.get("manifestDigest") or "").strip()
    if payload.get("releaseId") != release_id:
        raise ValueError("active release readback releaseId is not canonical")
    _stackctl._data_readiness_segment(release_id, label="releaseId")
    if (
        payload.get("manifestDigest") != manifest_digest
        or _MANAGED_DIGEST_RE.fullmatch(manifest_digest) is None
    ):
        raise ValueError("active release readback manifestDigest is not canonical")
    subject_hash = str(credential.get("subjectHash") or "").strip()
    attestation_token = str(credential.get("attestationToken") or "").strip()
    if (
        credential.get("subjectHash") != subject_hash
        or credential.get("attestationToken") != attestation_token
        or _MANAGED_DIGEST_RE.fullmatch(subject_hash) is None
        or not attestation_token
    ):
        raise ValueError("research consumer credential identity is not canonical")
    attestation_id_hash = "sha256:" + hashlib.sha256(
        attestation_token.encode("utf-8")
    ).hexdigest()
    if payload.get("subjectHash") != subject_hash:
        raise ValueError("active release readback subjectHash drifts from credential")
    if payload.get("attestationIdHash") != attestation_id_hash:
        raise ValueError(
            "active release readback attestationIdHash drifts from credential"
        )
    for field, expected in (
        ("signatureVerified", True),
        ("researchBadgeVisible", True),
        ("publicCdnDetected", False),
        ("anonymousMediaUrlDetected", False),
    ):
        if payload.get(field) is not expected:
            raise ValueError(f"active release readback {field} must be {expected!r}")
    return {
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "subjectHash": subject_hash,
        "attestationIdHash": attestation_id_hash,
        "signatureVerified": True,
        "researchBadgeVisible": True,
        "postIds": _managed_readback_closure(payload, "postIds"),
        "entityRefs": _managed_readback_closure(payload, "entityRefs"),
        "mediaAssetIds": _managed_readback_closure(payload, "mediaAssetIds"),
        "publicCdnDetected": False,
        "anonymousMediaUrlDetected": False,
    }


def _managed_research_readiness_candidates(
    *,
    environment: str,
    release_id: str,
    manifest_digest: str,
) -> list[dict[str, Any]]:
    """遍历本机 readiness 记录，只收集严格校验通过的 research readiness。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    release_root = (
        _stackctl.env_runs_root(environment)
        / "data-release"
        / _stackctl._data_readiness_segment(release_id, label="releaseId")
    )
    candidates: list[dict[str, Any]] = []
    if not release_root.is_dir() or release_root.is_symlink():
        return candidates
    for entry in sorted(release_root.iterdir()):
        if not entry.is_dir() or entry.is_symlink():
            continue
        verify_run_id = entry.name
        try:
            readiness, receipt_path = _stackctl._load_data_release_readiness(
                environment=environment,
                release_id=release_id,
                verify_run_id=verify_run_id,
                manifest_digest=manifest_digest,
                readiness_phase=_stackctl.ReadinessPhase.RESEARCH,
            )
        except (OSError, TypeError, ValueError):
            continue
        candidates.append(
            {
                "verifyRunId": verify_run_id,
                "readiness": readiness,
                "receiptPath": str(receipt_path),
            }
        )
    return candidates


def _managed_content_binding(
    *,
    environment: str,
    target: str,
    startup_attempt_id: str,
) -> dict[str, Any]:
    """readback -> exact readiness -> create-once binding；零/多候选均阻断。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        readback = _stackctl._managed_active_release_readback(
            environment=environment,
            startup_attempt_id=startup_attempt_id,
        )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        _stackctl.ResearchConsumerCredentialError,
        _stackctl.LocalEnvironmentHTTPError,
    ) as exc:
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            [f"active release readback failed: {exc}"],
        ) from exc
    candidates = _stackctl._managed_research_readiness_candidates(
        environment=environment,
        release_id=readback["releaseId"],
        manifest_digest=readback["manifestDigest"],
    )
    if len(candidates) != 1:
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            [
                "exactly one valid research readiness is required for "
                f"releaseId={readback['releaseId']} "
                f"manifestDigest={readback['manifestDigest']}; "
                f"found {len(candidates)} candidates: "
                + ", ".join(
                    str(candidate["verifyRunId"]) for candidate in candidates
                )
            ],
        )
    candidate = candidates[0]
    readiness = candidate.get("readiness")
    if not isinstance(readiness, Mapping):
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            ["research readiness candidate has no validated readiness projection"],
        )
    drift: list[str] = []
    if readiness.get("internalSubjectHash") != readback["subjectHash"]:
        drift.append("internalSubjectHash drifts from fresh research readback")
    for readiness_field, readback_field in (
        ("postIds", "postIds"),
        ("researchReadbackEntityRefs", "entityRefs"),
        ("researchReadbackMediaAssetIds", "mediaAssetIds"),
    ):
        expected = readiness.get(readiness_field)
        normalized = (
            [item.strip() for item in expected]
            if isinstance(expected, list)
            and all(isinstance(item, str) for item in expected)
            else []
        )
        if (
            not normalized
            or any(not item for item in normalized)
            or len(normalized) != len(set(normalized))
            or set(normalized) != set(readback[readback_field])
        ):
            drift.append(f"{readiness_field} drifts from fresh research readback")
    if drift:
        raise ManagedPreparationBlocked(MANAGED_CONTENT_BINDING_UNAVAILABLE, drift)
    verify_run_id = str(candidate["verifyRunId"])
    try:
        binding = _stackctl.create_test_live_content_binding(
            environment=environment,
            target=target,
            startup_attempt_id=startup_attempt_id,
            release_id=readback["releaseId"],
            verify_run_id=verify_run_id,
            manifest_digest=readback["manifestDigest"],
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            [f"test-live content binding failed: {exc}"],
        ) from exc
    if binding.get("readinessPhase") != _stackctl.ReadinessPhase.RESEARCH.value:
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            [
                "managed preparation only binds research readiness; got "
                + str(binding.get("readinessPhase") or "<missing>")
            ],
        )
    return binding


def _managed_content_binding_projection(
    binding: Mapping[str, Any],
    *,
    output_root: Path,
) -> dict[str, str]:
    """Project and independently read back the exact research readiness receipt."""

    projection = {
        field: str(binding.get(field) or "") for field in _CONTENT_BINDING_FIELDS
    }
    if not _valid_content_binding(projection):
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            ["test-live content binding does not carry exact readiness identity"],
        )
    raw_ref = Path(projection["readinessReceiptRef"])
    readiness_path = raw_ref if raw_ref.is_absolute() else output_root / raw_ref
    readiness_path = readiness_path.absolute()
    if readiness_path.is_symlink() or not readiness_path.is_file():
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            ["test-live content binding readiness receipt is not a regular file"],
        )
    observed_digest = _managed_file_digest(readiness_path)
    if observed_digest != projection["readinessReceiptDigest"]:
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            ["test-live content binding readiness exact-byte digest drifted"],
        )
    try:
        readiness = json.loads(readiness_path.read_bytes())
    except (OSError, UnicodeError, ValueError) as exc:
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            [f"test-live content readiness receipt is unreadable: {exc}"],
        ) from exc
    expected = {
        "releaseId": projection["releaseId"],
        "verifyRunId": projection["verifyRunId"],
        "manifestDigest": projection["manifestDigest"],
        "readinessPhase": "research",
        "passed": True,
    }
    if not isinstance(readiness, Mapping) or any(
        readiness.get(field) != value for field, value in expected.items()
    ):
        raise ManagedPreparationBlocked(
            MANAGED_CONTENT_BINDING_UNAVAILABLE,
            ["test-live content readiness receipt identity drifted"],
        )
    projection["readinessReceiptRef"] = str(readiness_path)
    return projection


def _write_managed_exact_payload(path: Path, payload: Mapping[str, Any]) -> str:
    """Write private exact command payload bytes with atomic 0600/no-follow semantics."""

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


def _managed_device_trust(
    *,
    target: str,
    trust_platform: str,
    device_id: str,
    lease_id: str,
) -> dict[str, str]:
    """有效 trust 直接复用；否则以真实 consumer lease 安装并复验。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    if not trust_platform:
        return {"deviceTrustReceiptRef": "", "deviceTrustReceiptDigest": ""}
    try:
        verified = _stackctl.verify_device_trust(
            target=target,
            platform_name=trust_platform,
            device=device_id,
        )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        _stackctl.LocalDeviceTrustError,
        _stackctl.PublicDomainTlsError,
    ):
        verified = None
    # verify-first 只能证明设备当前受信；还必须证明本次真实 consumer lease
    # 已写入 receipt.leases，否则必须 install 一次完成 lease binding 后再复验。
    if verified is None or lease_id not in {
        str(value) for value in verified.get("leases") or []
    }:
        try:
            installed = _stackctl.install_device_trust(
                target=target,
                platform_name=trust_platform,
                device=device_id,
                lease_id=lease_id,
                endpoint_probe=True,
            )
            if installed.get("systemTrustStore") is not True:
                raise _stackctl.LocalDeviceTrustError(
                    "managed preparation requires a provisioned system trust store"
                )
            verified = _stackctl.verify_device_trust(
                target=target,
                platform_name=trust_platform,
                device=device_id,
            )
            if lease_id not in {
                str(value) for value in verified.get("leases") or []
            }:
                raise _stackctl.LocalDeviceTrustError(
                    "device trust receipt does not bind the active consumer lease"
                )
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            _stackctl.LocalDeviceTrustError,
            _stackctl.PublicDomainTlsError,
        ) as exc:
            raise ManagedPreparationBlocked(
                MANAGED_STRICT_PREFLIGHT_FAILED,
                [f"device trust install/verify failed: {exc}"],
            ) from exc
    receipt_ref = str(verified.get("receipt") or "")
    if not receipt_ref:
        raise ManagedPreparationBlocked(
            MANAGED_STRICT_PREFLIGHT_FAILED,
            ["device trust verification returned no receipt reference"],
        )
    receipt_path = Path(receipt_ref)
    _validate_managed_trust_receipt(
        path=receipt_path,
        target=target,
        trust_platform=trust_platform,
        device_id=device_id,
        lease_id=lease_id,
    )
    return {
        "deviceTrustReceiptRef": receipt_ref,
        "deviceTrustReceiptDigest": _managed_file_digest(receipt_path),
    }


def _validate_managed_trust_receipt(
    *,
    path: Path,
    target: str,
    trust_platform: str,
    device_id: str,
    lease_id: str,
) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManagedPreparationBlocked(
            MANAGED_STRICT_PREFLIGHT_FAILED,
            [f"device trust receipt is unreadable: {exc}"],
        ) from exc
    if (
        not isinstance(payload, Mapping)
        or payload.get("target") != target
        or payload.get("platform") != trust_platform
        or payload.get("device") != device_id
        or payload.get("status") != "installed"
        or payload.get("systemTrustStore") is not True
        or lease_id not in {str(value) for value in payload.get("leases") or []}
    ):
        raise ManagedPreparationBlocked(
            MANAGED_STRICT_PREFLIGHT_FAILED,
            ["device trust receipt is not installed for the active consumer lease"],
        )


def _release_managed_preparation_resources(
    *,
    target: str,
    identity: Mapping[str, str],
    consumer_id: str,
    lease_id: str,
    owned_ports: str,
    trust_bound: bool,
) -> list[str]:
    """Best-effort compensation before the prepared receipt is handed off."""
    import quwoquan_ops.cli.stackctl as _stackctl

    warnings: list[str] = []
    if trust_bound and identity.get("trustPlatform") and lease_id:
        try:
            _stackctl.release_device_trust(
                target=target,
                platform_name=str(identity["trustPlatform"]),
                device=str(identity["deviceId"]),
                lease_id=lease_id,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            warnings.append(f"failed to release preparation device trust: {exc}")
    if identity.get("platform") == "android" and owned_ports:
        adb = shutil.which("adb")
        if not adb:
            warnings.append("failed to remove preparation-owned Android reverse: adb unavailable")
        else:
            for raw_port in owned_ports.split(","):
                port = raw_port.strip()
                if not port:
                    continue
                completed = subprocess.run(
                    [adb, "-s", str(identity["deviceId"]), "reverse", "--remove", f"tcp:{port}"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode != 0:
                    warnings.append(
                        f"failed to remove preparation-owned Android reverse tcp:{port}"
                    )
    if consumer_id:
        try:
            _stackctl.release_consumer_lease(
                target=target,
                device=str(identity.get("deviceId") or ""),
                consumer=consumer_id,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            warnings.append(f"failed to release preparation consumer lease: {exc}")
    return warnings


def _managed_strict_preflight(
    *,
    environment: str,
    target: str,
    content_binding: Mapping[str, Any],
    report_dir: Path,
) -> dict[str, Any]:
    """严格 preflight：readiness 发现从 warning 升级为 typed 阻断。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    del environment
    debug_payload = _stackctl.command_app_debug_preflight(
        argparse.Namespace(
            command="app-debug-preflight",
            target=target,
            purpose="content_live",
            runtime_mode="test_live",
            report_dir=str(report_dir / "app-debug-preflight"),
        )
    )
    debug_findings = [
        *(str(item) for item in debug_payload.get("details") or []),
        *(str(item) for item in debug_payload.get("warnings") or []),
    ]
    debug_binding = debug_payload.get("contentBinding")
    debug_binding = debug_binding if isinstance(debug_binding, Mapping) else {}
    if (
        int(debug_payload.get("exitCode", 2)) != 0
        or debug_payload.get("status") != "passed"
        or str(debug_payload.get("firstBlocker") or "")
        or str(debug_payload.get("releaseId") or "")
        != str(content_binding.get("releaseId") or "")
        or str(debug_payload.get("manifestDigest") or "")
        != str(content_binding.get("manifestDigest") or "")
        or str(debug_payload.get("readinessReceiptRef") or "")
        != str(content_binding.get("readinessReceiptRef") or "")
        or str(debug_payload.get("readinessReceiptDigest") or "")
        != str(content_binding.get("readinessReceiptDigest") or "")
        or str(debug_binding.get("verifyRunId") or "")
        != str(content_binding.get("verifyRunId") or "")
        or str(debug_binding.get("readinessPhase") or "") != "research"
    ):
        raise ManagedPreparationBlocked(
            MANAGED_STRICT_PREFLIGHT_FAILED,
            [
                "app-debug-preflight is not strictly green: status="
                + str(debug_payload.get("status") or "<missing>"),
                *debug_findings,
            ],
        )
    content_payload = _stackctl.command_app_content_preflight(
        argparse.Namespace(
            command="app-content-preflight",
            target=target,
            purpose="content_live",
            runtime_mode="test_live",
            content_binding=dict(content_binding),
            report_dir=str(report_dir / "app-content-preflight"),
        )
    )
    release_probe = content_payload.get("releaseProbe")
    release_probe = release_probe if isinstance(release_probe, Mapping) else {}
    media_checks = release_probe.get("mediaChecks")
    media_checks = media_checks if isinstance(media_checks, Mapping) else {}
    if (
        int(content_payload.get("exitCode", 2)) != 0
        or content_payload.get("schema") != "quwoquan_ops.app_content_preflight"
        or content_payload.get("target") != target
        or content_payload.get("status") != "passed"
        or str(content_payload.get("releaseId") or "")
        != str(content_binding.get("releaseId") or "")
        or str(content_payload.get("manifestDigest") or "")
        != str(content_binding.get("manifestDigest") or "")
        or str(content_payload.get("readinessReceiptRef") or "")
        != str(content_binding.get("readinessReceiptRef") or "")
        or str(content_payload.get("readinessReceiptDigest") or "")
        != str(content_binding.get("readinessReceiptDigest") or "")
        or release_probe.get("exitCode") != 0
        or type(release_probe.get("executedSampleCount")) is not int
        or int(release_probe["executedSampleCount"]) <= 0
        or media_checks.get("automatic") is not True
    ):
        raise ManagedPreparationBlocked(
            MANAGED_STRICT_PREFLIGHT_FAILED,
            [
                "strict content preflight exact payload is not green: status="
                + str(content_payload.get("status") or "<missing>"),
                *(str(item) for item in content_payload.get("details") or []),
            ],
        )
    return {"debugPayload": debug_payload, "contentPayload": content_payload}


def run_managed_preparation(
    *,
    target: str,
    device_id: str,
    platform: str = "",
    consumer_id: str,
    report_dir: Path,
) -> dict[str, Any]:
    """执行固定顺序的 managed preparation，并以 receipt-first 写私有回执。"""
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.app_debug_preflight_handoff import (
        write_app_debug_preflight_receipt,
    )

    receipt_path = report_dir / "managed-preparation.json"
    receipt: dict[str, Any] = {
        "schema": MANAGED_PREPARATION_SCHEMA,
        "target": str(target) if str(target) in MANAGED_PREPARATION_TARGETS else "",
        "environment": "",
        "platform": str(platform or "") if str(platform or "") in {"ios", "android"} else "",
        "deviceId": str(device_id or "").strip(),
        "runtimeIdentity": {},
        "consumerId": "",
        "consumerLeaseId": "",
        "androidReversePorts": "",
        "androidReverseOwnedPorts": "",
        "deviceTrustReceiptRef": "",
        "deviceTrustReceiptDigest": "",
        "contentBinding": {},
        "strictPreflightReceiptRef": "",
        "strictPreflightReceiptDigest": "",
        "strictContentPreflightReceiptRef": "",
        "strictContentPreflightReceiptDigest": "",
        "createdAt": "",
        "status": "blocked",
        "firstBlocker": "",
    }
    details: list[str] = []
    warnings: list[str] = []
    identity: dict[str, str] = {}
    lease_acquired = False
    lease_id = ""
    trust_bound = False
    handed_off = False

    def compensate_unhanded() -> None:
        nonlocal lease_acquired, trust_bound
        if not lease_acquired or handed_off or not identity:
            return
        warnings.extend(
            _release_managed_preparation_resources(
                target=target,
                identity=identity,
                consumer_id=str(receipt.get("consumerId") or ""),
                lease_id=lease_id,
                owned_ports=str(receipt.get("androidReverseOwnedPorts") or ""),
                trust_bound=trust_bound,
            )
        )
        lease_acquired = False
        trust_bound = False

    def finish(status: str, blocker: str, blocker_details: list[str]) -> dict[str, Any]:
        receipt["status"] = status
        receipt["firstBlocker"] = blocker
        receipt["createdAt"] = _stackctl.utc_now()
        if status == "blocked":
            _sanitize_blocked_receipt(receipt)
        digest = _stackctl._write_managed_preparation_receipt(receipt_path, receipt)
        return {
            "exitCode": 0 if status == "prepared" else 2,
            "status": status,
            "firstBlocker": blocker,
            "receiptPath": str(receipt_path),
            "receiptDigest": digest,
            "details": [*blocker_details, *details],
            "warnings": warnings,
        }

    try:
        if target not in MANAGED_PREPARATION_TARGETS:
            raise ManagedPreparationBlocked(
                MANAGED_RUNTIME_UNAVAILABLE,
                [f"managed preparation does not support target {target!r}"],
            )
        normalized_consumer = str(consumer_id or "").strip()
        if not normalized_consumer:
            raise ManagedPreparationBlocked(
                MANAGED_RECEIPT_INVALID,
                ["managed preparation requires a stable run consumer id"],
            )
        receipt["consumerId"] = normalized_consumer
        environment = str(
            _stackctl.get_target(_stackctl.load_environment_topology(), target)["env"]
        )
        receipt["environment"] = environment

        # 1. exact device。
        identity = _stackctl._managed_device_identity(
            device_id=device_id,
            platform=platform,
        )
        receipt["deviceId"] = identity["deviceId"]
        receipt["platform"] = identity["platform"]

        # 2. 启动/复用 exact full mutable runtime（identity 漂移仅一次有界替换）。
        runtime = _stackctl._managed_runtime_ready(
            environment=environment,
            target=target,
            report_dir=report_dir,
        )
        warnings.extend(str(item) for item in runtime.get("warnings") or [])
        startup_attempt = dict(runtime.get("startupAttempt") or {})
        startup_attempt_id = str(startup_attempt.get("attemptId") or "")
        receipt["runtimeIdentity"] = {
            "startupAttemptId": startup_attempt_id,
            "composeProject": str(startup_attempt.get("composeProject") or ""),
            "composeDigest": str(startup_attempt.get("composeDigest") or ""),
            "configurationDigest": str(
                startup_attempt.get("configurationDigest") or ""
            ),
            "providerRuntimeDigest": str(
                startup_attempt.get("providerRuntimeDigest") or ""
            ),
            "reused": bool(runtime.get("reused")),
            "replaced": bool(runtime.get("replaced")),
        }

        # 3. 以 run.sh 预先确定的稳定 consumer 获取真实 lease/transport。
        try:
            application_id = _stackctl.application_id_for(
                identity["platform"], environment, "debug"
            )
            ports: list[int] = []
            if identity["leasePlatform"] == "android":
                preexisting_ports = _stackctl._managed_android_adb_reverse_ports(
                    identity["deviceId"]
                )
                from quwoquan_ops.cli.lib.dev_up import local_target_ports

                ports = sorted(
                    {
                        int(port)
                        for port in local_target_ports(target)
                        if int(port) > 0
                    }
                )
                adb = shutil.which("adb")
                if not adb:
                    raise RuntimeError("adb not found in PATH")
                created_ports: list[int] = []
                try:
                    for port in ports:
                        if port in preexisting_ports:
                            continue
                        completed = subprocess.run(
                            [
                                adb,
                                "-s",
                                identity["deviceId"],
                                "reverse",
                                f"tcp:{port}",
                                f"tcp:{port}",
                            ],
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        if completed.returncode != 0:
                            detail = (completed.stderr or completed.stdout or "").strip()
                            raise RuntimeError(
                                f"adb reverse tcp:{port} failed: {detail or 'unknown adb failure'}"
                            )
                        created_ports.append(port)
                except BaseException:
                    for port in created_ports:
                        subprocess.run(
                            [
                                adb,
                                "-s",
                                identity["deviceId"],
                                "reverse",
                                "--remove",
                                f"tcp:{port}",
                            ],
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                    raise
                receipt["androidReversePorts"] = ",".join(str(port) for port in ports)
                receipt["androidReverseOwnedPorts"] = ",".join(
                    str(port) for port in created_ports
                )
            lease = _stackctl.acquire_consumer_lease(
                target=target,
                device=identity["deviceId"],
                consumer=normalized_consumer,
                package_name=application_id,
                ports=ports,
                platform=identity["leasePlatform"],
            )
            lease_acquired = True
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            if identity.get("platform") == "android" and receipt["androidReverseOwnedPorts"]:
                warnings.extend(
                    _release_managed_preparation_resources(
                        target=target,
                        identity=identity,
                        consumer_id="",
                        lease_id="",
                        owned_ports=str(receipt["androidReverseOwnedPorts"]),
                        trust_bound=False,
                    )
                )
                receipt["androidReverseOwnedPorts"] = ""
            raise ManagedPreparationBlocked(
                MANAGED_RUNTIME_UNAVAILABLE,
                [f"real consumer lease/transport preparation failed: {exc}"],
            ) from exc
        lease_id = str(lease.get("leaseId") or "")
        if _MANAGED_DIGEST_RE.fullmatch(lease_id) is None:
            raise ManagedPreparationBlocked(
                MANAGED_RECEIPT_INVALID,
                ["real consumer lease readback returned an invalid leaseId"],
            )
        receipt["consumerLeaseId"] = lease_id

        # 4. 以同一真实 lease 安装并验证 device trust。
        trust_bound = bool(identity["trustPlatform"])
        trust = _stackctl._managed_device_trust(
            target=target,
            trust_platform=identity["trustPlatform"],
            device_id=identity["deviceId"],
            lease_id=lease_id,
        )
        receipt["deviceTrustReceiptRef"] = trust["deviceTrustReceiptRef"]
        receipt["deviceTrustReceiptDigest"] = trust["deviceTrustReceiptDigest"]
        trust_bound = bool(trust["deviceTrustReceiptRef"])

        # 5-6. 服务端 active release readback + exact Research readiness 绑定。
        binding = _stackctl._managed_content_binding(
            environment=environment,
            target=target,
            startup_attempt_id=startup_attempt_id,
        )
        receipt["contentBinding"] = _managed_content_binding_projection(
            binding,
            output_root=_stackctl.output_root(),
        )

        # 7. 严格 preflight（含严格 content preflight），零 warning 才算通过。
        strict_payloads = _stackctl._managed_strict_preflight(
            environment=environment,
            target=target,
            content_binding=binding,
            report_dir=report_dir,
        )
        preflight_receipt = write_app_debug_preflight_receipt(
            report_dir / "preflight" / "app-debug-preflight.json",
            strict_payloads["debugPayload"],
            purpose="content_live",
            target=target,
        )
        receipt["strictPreflightReceiptRef"] = str(preflight_receipt.absolute())
        receipt["strictPreflightReceiptDigest"] = _managed_file_digest(
            preflight_receipt
        )
        content_receipt = (
            report_dir / "preflight" / "app-content-preflight.exact.json"
        ).absolute()
        exact_content_payload = strict_payloads["contentPayload"]
        content_envelope = {
            "schema": MANAGED_CONTENT_PREFLIGHT_SCHEMA,
            "target": target,
            "status": "passed",
            "releaseId": receipt["contentBinding"]["releaseId"],
            "manifestDigest": receipt["contentBinding"]["manifestDigest"],
            "readinessReceiptRef": receipt["contentBinding"][
                "readinessReceiptRef"
            ],
            "readinessReceiptDigest": receipt["contentBinding"][
                "readinessReceiptDigest"
            ],
            "releaseProbe": dict(exact_content_payload["releaseProbe"]),
            "payload": dict(exact_content_payload),
        }
        receipt["strictContentPreflightReceiptDigest"] = (
            _write_managed_exact_payload(content_receipt, content_envelope)
        )
        receipt["strictContentPreflightReceiptRef"] = str(content_receipt)
    except ManagedPreparationBlocked as exc:
        compensate_unhanded()
        try:
            return finish("blocked", exc.blocker, exc.details)
        except (OSError, ValueError):
            return {
                "exitCode": 2,
                "status": "blocked",
                "firstBlocker": exc.blocker,
                "receiptPath": "",
                "receiptDigest": "",
                "details": [*exc.details, *details],
                "warnings": warnings,
            }
    except BaseException:
        compensate_unhanded()
        raise

    try:
        prepared = finish("prepared", "", [])
    except (OSError, ValueError) as exc:
        compensate_unhanded()
        try:
            return finish("blocked", MANAGED_RECEIPT_INVALID, [str(exc)])
        except (OSError, ValueError):
            return {
                "exitCode": 2,
                "status": "blocked",
                "firstBlocker": MANAGED_RECEIPT_INVALID,
                "receiptPath": "",
                "receiptDigest": "",
                "details": [str(exc), *details],
                "warnings": warnings,
            }
    handed_off = True
    return prepared
