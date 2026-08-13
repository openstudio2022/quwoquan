"""Provider Patrol 报告证据：断言矩阵、敏感值防泄漏与运行时身份绑定。"""
from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from quwoquan_ops.ci.provider_conformance.protected_otp_broker import (
    ProtectedOTPBrokerBinding,
)
from quwoquan_ops.ci.provider_conformance.provider_patrol_lib.runtime_identity import (
    ROOT,
    _UNKNOWN_IDENTITIES,
    ProviderPatrolRuntimeIdentity,
    _require_digest,
    _sha256_bytes,
)

_SMS_CAPABILITY_ID = "identity.sms.otp"
_SMS_ASSERTION_COUNT = 12


def _validated_broker_port(binding: ProtectedOTPBrokerBinding) -> int:
    parsed = urlparse(binding.url)
    try:
        port = int(parsed.port or 0)
    except ValueError as exc:
        raise ValueError("protected OTP broker URL has an invalid port") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/v1/otp"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or port <= 0
    ):
        raise ValueError("protected OTP broker must use the exact HTTPS loopback URL")
    _require_digest(binding.ca_digest, label="protected OTP broker CA")
    _require_digest(
        binding.certificate_digest,
        label="protected OTP broker certificate",
    )
    try:
        ca_bytes = base64.b64decode(
            binding.ca_certificate_base64,
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("protected OTP broker CA certificate is invalid") from exc
    if _sha256_bytes(ca_bytes) != binding.ca_digest:
        raise ValueError("protected OTP broker CA certificate digest mismatch")
    return port


def _runtime_evidence(
    identity: ProviderPatrolRuntimeIdentity,
    binding: ProtectedOTPBrokerBinding | None,
) -> dict[str, Any]:
    if identity.launch_policy == "test_live":
        evidence: dict[str, Any] = {
            "environment": identity.environment,
            "target": identity.target,
            "launchPolicy": "test_live",
            "nonPromotable": True,
            "sourceRevision": identity.source_revision,
            "composeDigest": identity.compose_digest,
            "configurationDigest": identity.runtime_config_digest,
            "resolverHandoffDigest": identity.resolver_handoff_digest,
            "workspaceStatusDigest": identity.workspace_status_digest,
            "mutableStateDigest": identity.mutable_state_digest,
            "providerRuntime": {
                "bindingDigest": identity.provider_binding_digest,
                "runtimeCompositionDigest": identity.provider_runtime_digest,
                "workloads": list(identity.provider_workloads),
            },
            "smsProvider": {
                "adapterId": "ext.sms.local_capture",
                "endpointRef": "local_topology:sms-provider-substitute",
                "publishedPort": identity.sms_published_port,
            },
            "startup": {"workload": "full", "attemptId": identity.attempt_id},
        }
    else:
        evidence = {
            "environment": identity.environment,
            "target": identity.target,
            "baselineId": identity.baseline_id,
            "sourceRevision": identity.source_revision,
            "packageDigest": identity.package_digest,
            "imageDigest": identity.image_digest,
            "runtimeConfigDigest": identity.runtime_config_digest,
            "environmentRuntimeDigest": identity.environment_runtime_digest,
            "providerRuntimeDigest": identity.provider_runtime_digest,
            "elasticsearch": {
                "adapterId": "ext.obs.elasticsearch",
                "bindingDigest": identity.elasticsearch_binding_digest,
                "imageDigest": identity.elasticsearch_image_digest,
                "composeDigest": identity.elasticsearch_compose_digest,
                "clusterRef": identity.elasticsearch_cluster_ref,
            },
            "release": {
                "releaseId": identity.release_id,
                "releaseDigest": identity.release_digest,
            },
            "startup": {"workload": "full", "attemptId": identity.attempt_id},
        }
    if binding is not None:
        evidence["protectedOtpBrokerTls"] = {
            "scheme": "https",
            "minimumTlsVersion": "TLSv1.3",
            "caDigest": binding.ca_digest,
            "certificateDigest": binding.certificate_digest,
        }
    return evidence


def _declared_provider_assertion_ids() -> tuple[str, ...]:
    raw = _required_environment("QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS must be a JSON list"
        ) from exc
    if (
        not isinstance(payload, list)
        or not payload
        or any(
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or not item.startswith("provider.")
            for item in payload
        )
        or len(set(payload)) != len(payload)
    ):
        raise ValueError(
            "Provider Patrol assertion IDs must be a unique provider.* string list"
        )
    capability_id = _required_environment(
        "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID"
    )
    if capability_id == _SMS_CAPABILITY_ID and len(payload) != _SMS_ASSERTION_COUNT:
        raise ValueError(
            "identity.sms.otp Provider Patrol requires exactly 12 source assertions"
        )
    return tuple(payload)


def _validated_test_execution(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "framework",
        "executed",
        "failed",
        "skipped",
    }:
        raise ValueError(f"{label} testExecution shape is invalid")
    executed = value.get("executed")
    failed = value.get("failed")
    skipped = value.get("skipped")
    if (
        value.get("framework") not in {"patrol", "xctest"}
        or isinstance(executed, bool)
        or not isinstance(executed, int)
        or executed <= 0
        or isinstance(failed, bool)
        or not isinstance(failed, int)
        or failed != 0
        or isinstance(skipped, bool)
        or not isinstance(skipped, int)
        or skipped != 0
    ):
        raise ValueError(
            f"{label} must bind non-zero executed tests with zero failures/skips"
        )
    return dict(value)


def _safe_patrol_log(
    report: dict[str, Any],
    *,
    run_evidence: dict[str, Any],
    case_evidence: dict[str, Any],
) -> tuple[str, bytes]:
    raw_evidence_root = str(report.get("evidenceRoot") or "").strip()
    raw_run_directory = str(run_evidence.get("runDirectory") or "").strip()
    raw_log_ref = str(run_evidence.get("rawLogPath") or "").strip()
    if case_evidence.get("patrolLogPath") != raw_log_ref:
        raise ValueError("Provider Patrol case/run log evidence is inconsistent")
    relative_values = tuple(
        Path(value)
        for value in (raw_evidence_root, raw_run_directory, raw_log_ref)
    )
    if any(
        not str(value)
        or value.is_absolute()
        or value == Path(".")
        or any(part in {"", ".", ".."} for part in value.parts)
        for value in relative_values
    ):
        raise ValueError("Provider Patrol evidence paths are unsafe")
    evidence_root = (ROOT / relative_values[0]).resolve()
    run_directory = (ROOT / relative_values[1]).resolve()
    log_path = (ROOT / relative_values[2]).resolve()
    if (
        not evidence_root.is_relative_to(ROOT.resolve())
        or not run_directory.is_relative_to(evidence_root)
        or log_path != run_directory / "patrol.log"
    ):
        raise ValueError("Provider Patrol log does not belong to its run evidence")
    current = ROOT
    for part in relative_values[2].parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Provider Patrol log path contains a symlink")
    try:
        before = log_path.lstat()
        raw = log_path.read_bytes()
        after = log_path.lstat()
    except OSError as exc:
        raise ValueError("Provider Patrol log evidence is unavailable") from exc
    if (
        not log_path.is_file()
        or log_path.is_symlink()
        or not raw
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError("Provider Patrol log evidence is not a stable regular file")
    return raw_log_ref, raw


def _patrol_assertion_evidence(
    report: dict[str, Any],
    *,
    assertion_ids: tuple[str, ...],
    sensitive_values: tuple[str, ...],
) -> list[dict[str, Any]]:
    if (
        not assertion_ids
        or len(set(assertion_ids)) != len(assertion_ids)
        or any(
            not assertion_id
            or assertion_id != assertion_id.strip()
            or not assertion_id.startswith("provider.")
            for assertion_id in assertion_ids
        )
    ):
        raise ValueError("Provider Patrol source assertions are invalid")
    if report.get("status") != "passed" or "assertions" in report:
        raise ValueError(
            "Provider Patrol assertions require a fresh passed source report"
        )
    runs = report.get("runs")
    cases = report.get("caseResults")
    if (
        not isinstance(runs, list)
        or not runs
        or not isinstance(cases, list)
        or len(cases) != len(runs)
    ):
        raise ValueError(
            "Provider Patrol assertions require one real case for every device run"
        )
    normalized_sensitive_values = _sensitive_representations(sensitive_values)
    cases_by_device: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Provider Patrol run/case evidence must be objects")
        device_id = str(case.get("deviceId") or "").strip()
        if (
            device_id.lower() in _UNKNOWN_IDENTITIES
            or device_id in cases_by_device
        ):
            raise ValueError("Provider Patrol run/case identity is invalid")
        cases_by_device[device_id] = case

    matrix: list[dict[str, str]] = []
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("Provider Patrol run/case evidence must be objects")
        device = run.get("device")
        run_evidence = run.get("evidence")
        if not isinstance(device, dict) or not isinstance(run_evidence, dict):
            raise ValueError("Provider Patrol run/case evidence must be objects")
        device_id = str(device.get("id") or "").strip()
        case = cases_by_device.pop(device_id, None)
        case_evidence = case.get("evidence") if isinstance(case, dict) else None
        case_id = str((case or {}).get("caseId") or "").strip()
        if (
            device_id.lower() in _UNKNOWN_IDENTITIES
            or case_id.lower() in _UNKNOWN_IDENTITIES
            or not isinstance(case_evidence, dict)
            or run.get("exitCode") != 0
            or run.get("timedOut") is not False
            or (case or {}).get("status") != "passed"
        ):
            raise ValueError("Provider Patrol run/case is not a passed real execution")
        run_execution = _validated_test_execution(
            run.get("testExecution"),
            label=f"Provider Patrol run {device_id}",
        )
        case_execution = _validated_test_execution(
            (case or {}).get("testExecution"),
            label=f"Provider Patrol case {device_id}",
        )
        if run_execution != case_execution:
            raise ValueError("Provider Patrol run/case testExecution is inconsistent")
        raw_log_ref, log_raw = _safe_patrol_log(
            report,
            run_evidence=run_evidence,
            case_evidence=case_evidence,
        )
        if any(
            value in log_raw
            for value in normalized_sensitive_values
        ):
            raise ValueError("Provider Patrol log exposed a protected UAT value")
        execution_digest = _sha256_bytes(
            json.dumps(
                run_execution,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        matrix.append(
            {
                "caseId": case_id,
                "deviceId": device_id,
                "targetPlatform": str(device.get("targetPlatform") or ""),
                "logDigest": _sha256_bytes(log_raw),
                "logRef": raw_log_ref,
                "testExecutionDigest": execution_digest,
            }
        )
    if cases_by_device:
        raise ValueError("Provider Patrol case/run device matrix is inconsistent")
    matrix.sort(key=lambda item: (item["targetPlatform"], item["deviceId"]))
    matrix_digest = _sha256_bytes(
        json.dumps(
            matrix,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    execution_digest = _sha256_bytes(
        "\n".join(item["testExecutionDigest"] for item in matrix).encode("utf-8")
    )
    anchor_case_id = matrix[0]["caseId"]
    assertions: list[dict[str, Any]] = []
    for assertion_id in assertion_ids:
        assertion_digest = _sha256_bytes(
            f"{matrix_digest}\n{assertion_id}".encode("utf-8")
        )
        assertions.append(
            {
                "assertionId": assertion_id,
                "caseId": anchor_case_id,
                "status": "passed",
                "logRef": f"log:patrol-matrix:{matrix_digest}",
                "traceRef": (
                    f"trace:patrol-matrix:{matrix_digest}:{assertion_digest}"
                ),
                "metricRefs": [
                    "metric:patrol-matrix-test-execution:"
                    f"{execution_digest}:{assertion_digest}"
                ],
            }
        )
    return assertions


def _sensitive_representations(
    sensitive_values: tuple[str, ...],
) -> tuple[bytes, ...]:
    representations: list[bytes] = []
    for value in dict.fromkeys(item for item in sensitive_values if item):
        raw = value.encode("utf-8")
        standard = base64.b64encode(raw)
        urlsafe = base64.urlsafe_b64encode(raw)
        representations.extend(
            (raw, standard, standard.rstrip(b"="), urlsafe, urlsafe.rstrip(b"="))
        )
    return tuple(dict.fromkeys(item for item in representations if item))


def _bind_runtime_evidence_to_patrol_report(
    report_path: Path,
    *,
    identity: ProviderPatrolRuntimeIdentity,
    binding: ProtectedOTPBrokerBinding | None,
    assertion_ids: tuple[str, ...] = (),
    sensitive_values: tuple[str, ...] = (),
) -> None:
    if not report_path.is_file() or report_path.is_symlink():
        raise ValueError("Provider Patrol did not produce a safe report")
    try:
        report_raw = report_path.read_bytes()
        report = json.loads(report_raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Provider Patrol report is unreadable") from exc
    if not isinstance(report, dict):
        raise ValueError("Provider Patrol report root must be an object")
    if (
        report.get("suiteId") != "environment_page_smoke"
        or report.get("runtimeEnv") != identity.environment
        or report.get("apiContractEnv") != identity.environment
        or report.get("candidateDigest") != identity.baseline_id
        or "runtimeIdentityEvidence" in report
    ):
        raise ValueError("Provider Patrol report runtime identity mismatch")
    if binding is not None and binding.token.encode("utf-8") in report_raw:
        raise ValueError("Provider Patrol report exposed the protected broker token")
    if any(
        value in report_raw
        for value in _sensitive_representations(sensitive_values)
    ):
        raise ValueError("Provider Patrol report exposed a protected UAT value")
    if assertion_ids:
        report["assertions"] = _patrol_assertion_evidence(
            report,
            assertion_ids=assertion_ids,
            sensitive_values=sensitive_values,
        )
    report["runtimeIdentityEvidence"] = _runtime_evidence(identity, binding)
    rendered = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    if binding is not None and binding.token.encode("utf-8") in rendered:
        raise ValueError("Provider Patrol TLS evidence exposed the broker token")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{report_path.name}.",
        suffix=".tmp",
        dir=report_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, report_path.stat().st_mode & 0o777)
        temporary.replace(report_path)
    finally:
        temporary.unlink(missing_ok=True)


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _required_url(public_bases: dict[str, Any], name: str) -> str:
    value = str(public_bases.get(name) or "").strip()
    if not value:
        raise ValueError(f"environment topology publicBases.{name} is required")
    return value
