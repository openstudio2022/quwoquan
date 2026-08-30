"""Project Patrol page evidence and validate page-artifact ownership."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands.app_preflight_uat_projection_path import (
    canonical_source_projection_root,
    load_canonical_projection_evidence,
)
from quwoquan_ops.cli.commands.app_preflight_uat_raw_results import (
    emit_app_uat_raw_results as _emit_app_uat_raw_results,
)
from quwoquan_ops.cli.lib.app_launch_attempt import LAUNCH_BLOCKERS
from quwoquan_ops.cli.lib.local_controlled_edge_fault import (
    CONTROLLED_EDGE_SERVICES,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    APP_PAGE_ARTIFACT_BINDING_BLOCKER,
    CANONICAL_COMPARISON_KEYS,
    TESTED_APP_ARTIFACT_BINDING_SET_SCHEMA,
    TestedAppArtifactBindingError,
    validate_tested_app_artifact_binding,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.external_aut_driver import (
    PATROL_ANDROID_HOST_APPLICATION_ID,
    PATROL_IOS_HOST_APPLICATION_ID,
    ExternalAutDriverEvidenceError,
    validate_external_aut_driver_artifact_binding,
    validate_external_aut_homepage_journey,
)

_TYPED_BLOCKER_FIELDS = frozenset({"errorCode", "sourceOperationId", "httpStatus"})
_LOCAL_BLOCKER_FIELDS = frozenset({"errorCode"})
_RECEIPT_INVALID_BLOCKER = {"errorCode": "APP.LAUNCH.receipt_invalid"}


def emit_app_uat_raw_results(
    *,
    evidence_root: Path,
    target_binding: Mapping[str, Any],
    sample_plan: Mapping[str, Any],
    case_execution_reports: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Emit direct raw results at the page-evidence aggregation boundary."""

    return _emit_app_uat_raw_results(
        evidence_root=evidence_root,
        target_binding=target_binding,
        sample_plan=sample_plan,
        case_execution_reports=case_execution_reports,
    )



def _contained_relative_ref(root: Path, path_value: str, *, label: str) -> str:
    path = Path(path_value).expanduser()
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes the UAT evidence root") from exc


def _read_regular_bytes(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is missing") from exc
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise ValueError(f"{label} changed during exact-byte read")
    return b"".join(chunks)


def collect_app_uat_case_execution_reports(
    *,
    evidence_root: Path,
    report_ref: str,
    expected_target_uat_binding_digest: str,
) -> list[dict[str, str]]:
    """Collect only explicit create-once case receipts from one Patrol report."""

    root = evidence_root.expanduser().resolve(strict=True)
    report_relative = _contained_relative_ref(root, report_ref, label="Patrol report")
    report_path = root / report_relative
    report_bytes = _read_regular_bytes(report_path, label="Patrol report")
    try:
        report = json.loads(report_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError("Patrol report is not JSON") from exc
    if not isinstance(report, Mapping):
        raise ValueError("Patrol report must be an object")
    raw_sources = report.get("appUatCaseExecutionReports")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError(
            "Patrol report lacks required quwoquan_ops.app_uat_case_execution.v1 receipts"
        )
    collected: list[dict[str, str]] = []
    seen_refs: set[str] = set()
    for index, source in enumerate(raw_sources):
        if not isinstance(source, Mapping) or set(source) != {
            "receiptRef",
            "receiptSha256",
        }:
            raise ValueError(f"Patrol case receipt source {index} is invalid")
        ref = _contained_relative_ref(
            root,
            str(source.get("receiptRef") or ""),
            label=f"Patrol case receipt {index}",
        )
        digest = str(source.get("receiptSha256") or "")
        if ref in seen_refs or not digest.startswith("sha256:") or len(digest) != 71:
            raise ValueError(f"Patrol case receipt source {index} identity is invalid")
        encoded = _read_regular_bytes(root / ref, label=f"Patrol case receipt {index}")
        if "sha256:" + hashlib.sha256(encoded).hexdigest() != digest:
            raise ValueError(f"Patrol case receipt {index} exact bytes drifted")
        try:
            receipt = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Patrol case receipt {index} is not JSON") from exc
        if (
            not isinstance(receipt, Mapping)
            or receipt.get("schema")
            != "quwoquan_ops.app_uat_case_execution.v1"
            or receipt.get("targetUatBindingDigest")
            != expected_target_uat_binding_digest
        ):
            raise ValueError(f"Patrol case receipt {index} authority identity drifted")
        seen_refs.add(ref)
        collected.append({"receiptRef": ref, "receiptSha256": digest})
    return collected

def _safe_child_string(value: Any) -> str:
    return value if isinstance(value, str) and value == value.strip() else ""


def _candidate_operation_failures(
    binding: Mapping[str, Any],
) -> tuple[str, dict[str, frozenset[str]]]:
    raw_digest = binding.get("contractGraphDigest")
    raw_ref = binding.get("contractGraphRef")
    if (
        not isinstance(raw_digest, str)
        or len(raw_digest) != 71
        or not raw_digest.startswith("sha256:")
        or not isinstance(raw_ref, str)
        or not raw_ref
        or raw_ref != raw_ref.strip()
    ):
        raise ValueError("candidate ContractGraph binding is invalid")
    try:
        bytes.fromhex(raw_digest.removeprefix("sha256:"))
        projection_root = canonical_source_projection_root(
            binding.get("sourceProjectionRoot")
        )
        graph_ref, encoded = load_canonical_projection_evidence(
            raw_ref,
            projection_root=projection_root,
            output_root=projection_root,
            label="candidate ContractGraph projection",
            loader=lambda path, content, _mode: (path, content),
        )
        if str(graph_ref) != raw_ref:
            raise ValueError("candidate ContractGraph reference drifted")
        observed_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        if observed_digest != raw_digest:
            raise ValueError("candidate ContractGraph digest drifted")
        graph = json.loads(encoded)
        operations = graph["operations"]
    except (
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError(
            "candidate operation failure registry is unavailable"
        ) from error
    if not isinstance(operations, list):
        raise TypeError("canonical operation failure registry is invalid")
    registry: dict[str, frozenset[str]] = {}
    for item in operations:
        if not isinstance(item, Mapping):
            raise TypeError("canonical operation failure registry is invalid")
        operation_id = item.get("id")
        error_codes = item.get("errorCodes")
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or operation_id != operation_id.strip()
            or not isinstance(error_codes, list)
            or any(
                not isinstance(code, str) or not code or code != code.strip()
                for code in error_codes
            )
            or operation_id in registry
        ):
            raise ValueError("canonical operation failure registry is invalid")
        registry[operation_id] = frozenset(error_codes)
    if len(registry) != binding.get("contractGraphOperationCount"):
        raise ValueError("candidate operation failure registry identity drifted")
    return raw_digest, registry


def _safe_typed_blocker(
    value: Any,
    *,
    operation_failures: Mapping[str, frozenset[str]],
) -> dict[str, Any]:
    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("Patrol child typed blocker schema is invalid")
    fields = set(value)
    error_code = value.get("errorCode")
    if fields == _LOCAL_BLOCKER_FIELDS:
        if not isinstance(error_code, str) or error_code not in LAUNCH_BLOCKERS:
            raise ValueError("Patrol child typed blocker value is invalid")
        return dict(value)
    if fields != _TYPED_BLOCKER_FIELDS:
        raise ValueError("Patrol child typed blocker schema is invalid")
    operation = value.get("sourceOperationId")
    status = value.get("httpStatus")
    if (
        not isinstance(error_code, str)
        or not error_code
        or error_code != error_code.strip()
        or not isinstance(operation, str)
        or not operation
        or operation != operation.strip()
        or operation not in operation_failures
        or error_code not in operation_failures[operation]
        or (
            status is not None
            and (
                not isinstance(status, int)
                or isinstance(status, bool)
                or not 100 <= status <= 599
            )
        )
    ):
        raise ValueError("Patrol child typed blocker value is invalid")
    return dict(value)


def _closed_receipt_blocker(*records: Any) -> dict[str, Any]:
    codes: list[str] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        for field in ("firstBlocker", "errorCode"):
            if field not in record or record[field] in (None, ""):
                continue
            value = record[field]
            if not isinstance(value, str) or value not in LAUNCH_BLOCKERS:
                raise ValueError("Patrol child receipt blocker is invalid")
            codes.append(value)
    if not codes:
        return {}
    if any(code != codes[0] for code in codes[1:]):
        raise ValueError("Patrol child receipt blockers conflict")
    return {"errorCode": codes[0]}


def _ordered_child_runs(
    value: Any,
    *,
    operation_failures: Mapping[str, frozenset[str]],
) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise TypeError("Patrol child runs schema is invalid")
    runs: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError("Patrol child run schema is invalid")
        exit_code = item.get("exitCode")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise TypeError("Patrol child run exitCode is invalid")
        evidence = item.get("evidence", {})
        if not isinstance(evidence, Mapping):
            raise TypeError("Patrol child run evidence is invalid")
        blockers = _validated_child_run_blockers(
            item,
            evidence=evidence,
            operation_failures=operation_failures,
        )
        if exit_code != 0 and not any(blockers):
            raise ValueError("failed Patrol child run lacks a typed blocker")
        runs.append(item)
    return runs


def _validated_child_run_blockers(
    run: Mapping[str, Any],
    *,
    evidence: Mapping[str, Any],
    operation_failures: Mapping[str, frozenset[str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Validate every blocker surface before caller selects the first failure."""

    receipt = _closed_receipt_blocker(run, evidence)
    run_typed = _safe_typed_blocker(
        run.get("typedBlocker"),
        operation_failures=operation_failures,
    )
    evidence_typed = _safe_typed_blocker(
        evidence.get("typedBlocker"),
        operation_failures=operation_failures,
    )
    run_artifact = _safe_typed_blocker(
        run.get("artifactBindingBlocker"),
        operation_failures=operation_failures,
    )
    evidence_artifact = _safe_typed_blocker(
        evidence.get("artifactBindingBlocker"),
        operation_failures=operation_failures,
    )
    if run_typed and evidence_typed and run_typed != evidence_typed:
        raise ValueError("Patrol child typed blocker surfaces conflict")
    if run_artifact and evidence_artifact and run_artifact != evidence_artifact:
        raise ValueError("Patrol child artifact blocker surfaces conflict")
    return (
        receipt,
        run_typed or evidence_typed,
        run_artifact or evidence_artifact,
    )


def _first_child_blocker(
    runs: list[Mapping[str, Any]],
    *receipts: Any,
    operation_failures: Mapping[str, frozenset[str]],
) -> dict[str, Any]:
    receipt_blocker = _closed_receipt_blocker(*receipts)
    validated: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for run in runs:
        evidence = run.get("evidence", {})
        assert isinstance(evidence, Mapping)
        validated.append(
            _validated_child_run_blockers(
                run,
                evidence=evidence,
                operation_failures=operation_failures,
            )
        )
    for blockers in validated:
        for candidate in blockers:
            if candidate:
                return candidate
    return receipt_blocker


def _app_content_patrol_evidence(
    report_ref: str,
    *,
    contract_graph_binding: Mapping[str, Any],
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report_path = Path(report_ref)
    if not report_path.is_absolute():
        report_path = _stackctl.ROOT / report_path
    report = _stackctl._read_json_object(str(report_path))
    malformed = False
    try:
        graph_digest, operation_failures = _candidate_operation_failures(
            contract_graph_binding
        )
        report_runs = _ordered_child_runs(
            report.get("runs"),
            operation_failures=operation_failures,
        )
    except (TypeError, ValueError):
        graph_digest = ""
        operation_failures = {}
        report_runs = []
        malformed = True
    first_run = report_runs[0] if report_runs else {}
    selected = next(
        (item for item in report_runs if item["exitCode"] == 0),
        first_run,
    )
    evidence = selected.get("evidence", {})
    evidence = evidence if isinstance(evidence, Mapping) else {}
    screenshot = evidence.get("afterScreenshot")
    screenshot = screenshot if isinstance(screenshot, dict) else {}
    screenshot_marker = screenshot.get("marker")
    screenshot_marker = screenshot_marker if isinstance(screenshot_marker, dict) else {}
    screenshot_is_live_page = (
        screenshot.get("status") == "captured"
        and screenshot.get("capturedDuringPatrol") is True
        and all(
            _safe_child_string(screenshot_marker.get(field))
            for field in ("environment", "suite", "route", "terminalKey")
        )
    )
    screenshot_ref = _safe_child_string(screenshot.get("path"))
    screenshot_path = Path(screenshot_ref)
    if screenshot_ref and not screenshot_path.is_absolute():
        screenshot_path = _stackctl.ROOT / screenshot_path
    screenshot_digest = (
        "sha256:" + hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
        if screenshot_is_live_page and screenshot_ref and screenshot_path.is_file()
        else ""
    )
    tested_app_artifact_binding = report.get("testedAppArtifactBinding")
    if not isinstance(tested_app_artifact_binding, dict):
        tested_app_artifact_binding = {}
    external_aut_journeys = report.get("externalProductionAutJourneys")
    if not isinstance(external_aut_journeys, dict):
        external_aut_journeys = {}
    external_aut_driver_artifact = report.get("externalProductionAutDriverArtifact")
    if not isinstance(external_aut_driver_artifact, dict):
        external_aut_driver_artifact = {}
    activation_receipt = report.get("hostRuntimeConfigActivation")
    try:
        if malformed:
            raise ValueError("Patrol child receipt is malformed")
        first_evidence = first_run.get("evidence", {})
        assert isinstance(first_evidence, Mapping)
        typed_blocker = _safe_typed_blocker(
            first_evidence.get("typedBlocker"),
            operation_failures=operation_failures,
        )
        artifact_blocker = _safe_typed_blocker(
            first_evidence.get("artifactBindingBlocker"),
            operation_failures=operation_failures,
        )
        receipt_blocker = _first_child_blocker(
            report_runs,
            activation_receipt,
            report,
            operation_failures=operation_failures,
        )
    except (TypeError, ValueError):
        typed_blocker = dict(_RECEIPT_INVALID_BLOCKER)
        artifact_blocker = {}
        receipt_blocker = {}
    return {
        "status": _safe_child_string(report.get("status")),
        "patrolTarget": _safe_child_string(report.get("target")),
        "environmentAlias": _safe_child_string(report.get("environmentAlias")),
        "platform": _safe_child_string(report.get("platform")),
        "deviceId": _safe_child_string(
            first_run.get("device", {}).get("id")
            if isinstance(first_run.get("device"), dict)
            else None
        ),
        "device": selected.get("device", {}) if isinstance(selected, dict) else {},
        "testExecution": (
            selected.get("testExecution", {}) if isinstance(selected, dict) else {}
        ),
        "consumerLease": evidence.get("consumerLease", {}),
        "feedContent": evidence.get("feedContent", {}),
        "controlledEdgeFault": evidence.get("controlledEdgeFault", {}),
        "controlledEdgeFaultReceipt": evidence.get("controlledEdgeFaultReceipt", {}),
        "screenshotRef": screenshot_ref,
        "screenshotDigest": screenshot_digest,
        "screenshotMarker": screenshot_marker if screenshot_is_live_page else {},
        "testedAppArtifactBinding": tested_app_artifact_binding,
        "externalProductionAutJourneys": external_aut_journeys,
        "externalProductionAutDriverArtifact": external_aut_driver_artifact,
        "typedBlocker": receipt_blocker or typed_blocker,
        "artifactBindingBlocker": artifact_blocker,
        "remoteApi": report.get("remoteApiEvidence", {}),
        "contractGraphDigest": graph_digest,
    }


def _app_content_page_artifact_binding(
    *,
    page_evidence: Mapping[str, Any],
    launch_binding: Mapping[str, Any],
    expected_patrol_target: str,
    expected_environment_alias: str,
    expected_platform: str,
    expected_device_id: str,
) -> dict[str, Any]:
    """Bind one page run to the exact canonical launcher AppArtifact."""

    external_collection = page_evidence.get("externalProductionAutJourneys")
    if (
        isinstance(external_collection, Mapping)
        and external_collection.get("required") is True
    ):
        journeys = external_collection.get("journeys")
        if (
            external_collection.get("schema")
            != "environment-page-smoke.external-production-aut-journey-set.v1"
            or external_collection.get("status") != "passed"
            or not isinstance(journeys, list)
            or len(journeys) != 1
            or not isinstance(journeys[0], Mapping)
        ):
            raise ValueError(
                f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
                "external production AUT journey is missing or not passed"
            )
        test_host_collection = page_evidence.get("testedAppArtifactBinding")
        if (
            not isinstance(test_host_collection, Mapping)
            or test_host_collection.get("schema")
            != TESTED_APP_ARTIFACT_BINDING_SET_SCHEMA
            or test_host_collection.get("status") != "passed"
        ):
            raise ValueError(
                f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
                "external production AUT Patrol test-host artifact is unbound"
            )
        test_host_bindings = test_host_collection.get("bindings")
        test_host_projections = test_host_collection.get("comparisonProjections")
        if (
            not isinstance(test_host_bindings, list)
            or len(test_host_bindings) != 1
            or not isinstance(test_host_bindings[0], dict)
            or not isinstance(test_host_projections, list)
            or len(test_host_projections) != 1
            or not isinstance(test_host_projections[0], dict)
        ):
            raise ValueError(
                f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
                "external production AUT requires one exact Patrol test-host artifact"
            )
        try:
            test_host_comparison = validate_tested_app_artifact_binding(
                test_host_bindings[0]
            )
        except TestedAppArtifactBindingError as error:
            raise ValueError(
                f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: {error.detail}"
            ) from error
        expected_test_host_application_id = (
            PATROL_IOS_HOST_APPLICATION_ID
            if expected_platform == "ios"
            else PATROL_ANDROID_HOST_APPLICATION_ID
        )
        if (
            test_host_bindings[0].get("platform") != expected_platform
            or test_host_bindings[0].get("deviceId") != expected_device_id
            or test_host_comparison.get("applicationId")
            != expected_test_host_application_id
            or test_host_projections[0] != test_host_comparison
            or test_host_comparison.get("applicationId")
            == launch_binding.get("applicationId")
        ):
            raise ValueError(
                f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
                "external production AUT Patrol test-host identity drifted"
            )
        native_driver_raw = page_evidence.get("externalProductionAutDriverArtifact")
        try:
            if not isinstance(native_driver_raw, Mapping):
                raise ExternalAutDriverEvidenceError(
                    "external AUT native driver artifact is missing"
                )
            native_driver = validate_external_aut_driver_artifact_binding(
                native_driver_raw,
                expected_platform=expected_platform,
                expected_device_id=expected_device_id,
            )
            if native_driver.get(
                "testHostApplicationId"
            ) != expected_test_host_application_id or native_driver.get(
                "driverApplicationId"
            ) in {
                expected_test_host_application_id,
                launch_binding.get("applicationId"),
            }:
                raise ExternalAutDriverEvidenceError(
                    "external AUT native driver/test-host separation drifted"
                )
            page_binding = validate_external_aut_homepage_journey(
                journeys[0],
                launch_binding=launch_binding,
                native_driver_artifact_binding=native_driver,
                expected_patrol_target=expected_patrol_target,
                expected_environment_alias=expected_environment_alias,
                expected_platform=expected_platform,
                expected_device_id=expected_device_id,
            )
        except ExternalAutDriverEvidenceError as error:
            raise ValueError(
                f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: {error.detail}"
            ) from error
        page_binding["testHost"] = {
            "applicationId": test_host_comparison["applicationId"],
            "artifactDigest": test_host_comparison["artifactDigest"],
            "deviceId": expected_device_id,
        }
        page_binding["nativeDriver"] = {
            "applicationId": native_driver["driverApplicationId"],
            "artifactDigest": native_driver["artifactDigest"],
            "artifactBindingDigest": journeys[0]["nativeDriverArtifactBindingDigest"],
            "deviceId": expected_device_id,
        }
        return page_binding

    collection = page_evidence.get("testedAppArtifactBinding")
    if not isinstance(collection, Mapping) or collection.get("status") != "passed":
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "page report has no passed tested App artifact binding"
        )
    bindings = collection.get("bindings")
    projections = collection.get("comparisonProjections")
    if (
        not isinstance(bindings, list)
        or len(bindings) != 1
        or not isinstance(projections, list)
        or len(projections) != 1
    ):
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "page report must contain exactly one tested App comparison"
        )
    raw_binding = bindings[0]
    raw_projection = projections[0]
    if not isinstance(raw_binding, dict) or not isinstance(raw_projection, dict):
        raise TypeError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "page tested App comparison is malformed"
        )
    try:
        tested = validate_tested_app_artifact_binding(raw_binding)
    except TestedAppArtifactBindingError as error:
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: {error.detail}"
        ) from error
    expected_page_identity = {
        "patrolTarget": expected_patrol_target,
        "environmentAlias": expected_environment_alias,
        "platform": expected_platform,
        "deviceId": expected_device_id,
    }
    mismatched_page_identity = [
        field
        for field, expected in expected_page_identity.items()
        if not expected or page_evidence.get(field) != expected
    ]
    if mismatched_page_identity:
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "page report identity differs from its canonical launch on "
            + ",".join(mismatched_page_identity)
        )
    if raw_binding.get("platform") != expected_platform:
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "page tested App platform differs from its canonical launch"
        )
    if raw_binding.get("deviceId") != expected_device_id:
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "page tested App device differs from its canonical launch"
        )
    if raw_projection != tested:
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "page comparison projection drifted from its tested App binding"
        )
    canonical = {
        "applicationId": str(launch_binding.get("applicationId") or ""),
        "artifactDigest": str(launch_binding.get("artifactDigest") or ""),
        "sourceProjectionDigest": str(
            launch_binding.get("sourceProjectionDigest") or ""
        ),
        "runtimeConfigPackageDigest": str(
            launch_binding.get("runtimeConfigPackageDigest") or ""
        ),
        "trustDigest": str(
            launch_binding.get("runtimeConfigTrustEnvelopeDigest") or ""
        ),
        "launchAttemptId": str(launch_binding.get("launchAttemptId") or ""),
    }
    missing = [key for key in CANONICAL_COMPARISON_KEYS if not tested.get(key)]
    if missing:
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "page tested App comparison is missing " + ",".join(missing)
        )
    canonical_missing = [
        key for key in CANONICAL_COMPARISON_KEYS if not canonical.get(key)
    ]
    if canonical_missing:
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "canonical launch comparison is missing " + ",".join(canonical_missing)
        )
    mismatched = [
        key
        for key in CANONICAL_COMPARISON_KEYS
        if tested.get(key) != canonical.get(key)
    ]
    if mismatched:
        raise ValueError(
            f"{APP_PAGE_ARTIFACT_BINDING_BLOCKER}: "
            "page tested App differs from canonical launch on " + ",".join(mismatched)
        )
    return {
        "status": "passed",
        "comparisonKeys": list(CANONICAL_COMPARISON_KEYS),
        "tested": tested,
        "canonical": canonical,
    }


def _controlled_edge_recovery_evidence_issue(
    evidence: Mapping[str, Any],
    *,
    target: str,
    environment: str,
    runtime_binding: Mapping[str, Any],
    expected_health_url: str,
) -> str:
    """Validate child recovery evidence against the immutable startup receipt."""

    fault = evidence.get("controlledEdgeFault")
    receipt = evidence.get("controlledEdgeFaultReceipt")
    startup_identity = runtime_binding.get("startupIdentity")
    if (
        evidence.get("status") != "passed"
        or runtime_binding.get("launchPolicy") != "immutable_candidate"
        or not isinstance(fault, Mapping)
        or not isinstance(receipt, Mapping)
        or not isinstance(startup_identity, Mapping)
        or runtime_binding.get("candidateDigest")
        != startup_identity.get("candidateDigest")
    ):
        return "controlled edge recovery Patrol evidence is incomplete"

    recovered_count = fault.get("recoveredVisibleCardCount")
    expected_fault = {
        "environment": environment,
        "singlePrimaryAction": True,
        "forbiddenBrandAbsent": True,
        "technicalDetailsAbsent": True,
        "blockedRetryCount": 5,
        "blockingErrorRetained": True,
        "sameInstallRecovery": True,
    }
    if (
        any(fault.get(field) != value for field, value in expected_fault.items())
        or not str(fault.get("copyKey") or "").strip()
        or isinstance(recovered_count, bool)
        or not isinstance(recovered_count, int)
        or recovered_count <= 0
    ):
        return "controlled edge recovery same-install evidence is incomplete"

    expected_receipt = {
        "schema": "quwoquan_ops.controlled_edge_fault",
        "status": "restored",
        "target": target,
        "environment": environment,
        "composeProject": runtime_binding.get("composeProject"),
        "configurationDigest": startup_identity.get("configurationDigest"),
        "healthUrl": expected_health_url,
    }
    if (
        any(receipt.get(field) != value for field, value in expected_receipt.items())
        or not str(receipt.get("restoredAt") or "").strip()
    ):
        return "controlled edge recovery receipt does not match current runtime binding"

    raw_services = receipt.get("services")
    if not isinstance(raw_services, list) or any(
        not isinstance(item, Mapping) for item in raw_services
    ):
        return "controlled edge recovery receipt lacks restored API Edge containers"
    services = {str(item.get("service") or ""): item for item in raw_services}
    if set(services) != set(CONTROLLED_EDGE_SERVICES):
        return "controlled edge recovery receipt lacks restored API Edge containers"
    for service in CONTROLLED_EDGE_SERVICES:
        container = services[service]
        if (
            container.get("statusBefore") != "running"
            or container.get("statusAfter") != "running"
            or not str(container.get("containerId") or "").strip()
            or not str(container.get("imageRef") or "").strip()
            or not str(container.get("runtimeImageId") or "").strip()
        ):
            return "controlled edge recovery receipt lacks restored API Edge containers"
    return ""


__all__ = [
    "collect_app_uat_case_execution_reports",
    "emit_app_uat_raw_results",
]
