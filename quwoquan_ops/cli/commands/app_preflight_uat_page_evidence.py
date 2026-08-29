"""Project Patrol page evidence and validate page-artifact ownership."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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

_TYPED_CODE_RE = re.compile(r"[A-Z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*){2,}")
_SOURCE_OPERATION_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.]{0,159}")
_TYPED_BLOCKER_FIELDS = frozenset({"errorCode", "sourceOperationId", "httpStatus"})


def _safe_typed_blocker(value: Any) -> dict[str, Any]:
    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping) or set(value) != _TYPED_BLOCKER_FIELDS:
        raise ValueError("Patrol child typed blocker schema is invalid")
    error_code = value.get("errorCode")
    operation = value.get("sourceOperationId")
    status = value.get("httpStatus")
    if (
        not isinstance(error_code, str)
        or len(error_code) > 160
        or _TYPED_CODE_RE.fullmatch(error_code) is None
        or not isinstance(operation, str)
        or _SOURCE_OPERATION_RE.fullmatch(operation) is None
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
    return {
        "errorCode": codes[0],
        "sourceOperationId": "environment_page_smoke.child_receipt",
        "httpStatus": None,
    }


def _app_content_patrol_evidence(report_ref: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report_path = Path(report_ref)
    if not report_path.is_absolute():
        report_path = _stackctl.ROOT / report_path
    report = _stackctl._read_json_object(str(report_path))
    report_runs = report.get("runs")
    if not isinstance(report_runs, list):
        report_runs = []
    first_run = next(
        (item for item in report_runs if isinstance(item, dict)),
        {},
    )
    first_evidence = first_run.get("evidence") if isinstance(first_run, dict) else {}
    first_evidence = first_evidence if isinstance(first_evidence, dict) else {}
    selected = next(
        (
            item
            for item in report_runs
            if isinstance(item, dict) and int(item.get("exitCode", 1)) == 0
        ),
        first_run,
    )
    evidence = selected.get("evidence") if isinstance(selected, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    screenshot = evidence.get("afterScreenshot")
    screenshot = screenshot if isinstance(screenshot, dict) else {}
    screenshot_marker = screenshot.get("marker")
    screenshot_marker = screenshot_marker if isinstance(screenshot_marker, dict) else {}
    screenshot_is_live_page = (
        screenshot.get("status") == "captured"
        and screenshot.get("capturedDuringPatrol") is True
        and all(
            str(screenshot_marker.get(field) or "").strip()
            for field in ("environment", "suite", "route", "terminalKey")
        )
    )
    screenshot_ref = str(screenshot.get("path") or "").strip()
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
    first_receipt = first_run if isinstance(first_run, Mapping) else {}
    activation_receipt = report.get("hostRuntimeConfigActivation")
    try:
        typed_blocker = _safe_typed_blocker(first_evidence.get("typedBlocker"))
        artifact_blocker = _safe_typed_blocker(
            first_evidence.get("artifactBindingBlocker")
        )
        receipt_blocker = _closed_receipt_blocker(
            first_receipt,
            activation_receipt,
            report,
        )
    except ValueError:
        typed_blocker = {
            "errorCode": "APP.LAUNCH.receipt_invalid",
            "sourceOperationId": "environment_page_smoke.child_receipt",
            "httpStatus": None,
        }
        artifact_blocker = {}
        receipt_blocker = {}
    return {
        "status": str(report.get("status") or ""),
        "patrolTarget": str(report.get("target") or ""),
        "environmentAlias": str(report.get("environmentAlias") or ""),
        "platform": str(report.get("platform") or ""),
        "deviceId": str(
            (first_run.get("device") or {}).get("id")
            if isinstance(first_run.get("device"), dict)
            else ""
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
