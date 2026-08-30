"""Validate native black-box evidence from an already-running production AUT.

The Patrol host remains a driver/test container.  It is never relabelled with a
production application id, and its Flutter widget tree is not accepted as page
evidence.  The native platform test selects an independently installed
production application, proves process continuity while bringing it to the
foreground, and asserts the canonical home accessibility identity.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .external_aut_driver_artifact import (
    build_ios_external_aut_driver_artifact_binding,
    collect_android_external_aut_driver_artifact_binding,
    ios_external_aut_xcodebuild_command,
    materialize_ios_external_aut_xctestrun,
    resolve_ios_external_aut_xctestrun,
    validate_external_aut_driver_artifact_binding,
)
from .external_aut_driver_contract import (
    _CANONICAL_BINDING_PROJECTION_FIELDS,
    _EVIDENCE_FIELDS,
    _JOURNEY_FIELDS,
    _PLATFORM_CONTRACT,
    ANDROID_EXTERNAL_AUT_TEST_CLASS,
    APP_PAGE_ARTIFACT_BINDING_BLOCKER,
    EXTERNAL_AUT_CANONICAL_BINDING_ENV,
    EXTERNAL_AUT_HOMEPAGE_SCHEMA,
    EXTERNAL_AUT_JOURNEY_ID,
    EXTERNAL_AUT_JOURNEY_SCHEMA,
    EXTERNAL_AUT_JOURNEY_SET_SCHEMA,
    EXTERNAL_AUT_MARKER,
    HOME_SURFACE_ACCESSIBILITY_IDENTIFIER,
    IOS_EXTERNAL_AUT_ONLY_TESTING,
    PATROL_ANDROID_DRIVER_APPLICATION_ID,
    PATROL_ANDROID_HOST_APPLICATION_ID,
    PATROL_ANDROID_INSTRUMENTATION_COMPONENT,
    PATROL_IOS_HOST_APPLICATION_ID,
    PATROL_IOS_XCTEST_BUNDLE_ID,
    PATROL_IOS_XCTRUNNER_BUNDLE_ID,
    ExternalAutDriverEvidenceError,
    _application_id,
    _canonical_document_digest,
    _digest,
)

__all__ = [
    "ANDROID_EXTERNAL_AUT_TEST_CLASS",
    "APP_PAGE_ARTIFACT_BINDING_BLOCKER",
    "EXTERNAL_AUT_CANONICAL_BINDING_ENV",
    "EXTERNAL_AUT_HOMEPAGE_SCHEMA",
    "EXTERNAL_AUT_JOURNEY_ID",
    "EXTERNAL_AUT_JOURNEY_SCHEMA",
    "EXTERNAL_AUT_JOURNEY_SET_SCHEMA",
    "EXTERNAL_AUT_MARKER",
    "HOME_SURFACE_ACCESSIBILITY_IDENTIFIER",
    "IOS_EXTERNAL_AUT_ONLY_TESTING",
    "PATROL_ANDROID_DRIVER_APPLICATION_ID",
    "PATROL_ANDROID_HOST_APPLICATION_ID",
    "PATROL_ANDROID_INSTRUMENTATION_COMPONENT",
    "PATROL_IOS_HOST_APPLICATION_ID",
    "PATROL_IOS_XCTEST_BUNDLE_ID",
    "PATROL_IOS_XCTRUNNER_BUNDLE_ID",
    "ExternalAutDriverEvidenceError",
    "android_external_aut_instrumentation_command",
    "attach_external_aut_journey",
    "build_external_aut_homepage_journey",
    "build_ios_external_aut_driver_artifact_binding",
    "collect_android_external_aut_driver_artifact_binding",
    "collect_external_aut_homepage_evidence",
    "decode_external_aut_canonical_binding",
    "encode_external_aut_canonical_binding",
    "external_aut_canonical_binding_projection",
    "external_aut_journey_blocker",
    "external_aut_native_test_inputs",
    "ios_external_aut_xcodebuild_command",
    "materialize_ios_external_aut_xctestrun",
    "new_external_aut_journey_set",
    "parse_external_aut_homepage_evidence",
    "resolve_ios_external_aut_xctestrun",
    "settle_external_aut_journey_report",
    "unavailable_external_aut_journey",
    "validate_external_aut_driver_artifact_binding",
    "validate_external_aut_homepage_evidence",
    "validate_external_aut_homepage_journey",
]


def encode_external_aut_canonical_binding(
    binding: Mapping[str, Any],
) -> str:
    """Encode the already-validated canonical launch binding for one child run."""

    if not isinstance(binding, Mapping) or not binding:
        raise ExternalAutDriverEvidenceError(
            "canonical launch binding handoff is missing"
        )
    encoded = json.dumps(
        dict(binding),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.b64encode(encoded).decode("ascii")


def decode_external_aut_canonical_binding(encoded: str) -> dict[str, Any]:
    """Decode one canonical binding without accepting whitespace or extra bytes."""

    normalized = str(encoded or "").strip()
    if not normalized:
        raise ExternalAutDriverEvidenceError(
            "canonical launch binding handoff is missing"
        )
    try:
        raw = base64.b64decode(normalized, validate=True)
        decoded = json.loads(raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ExternalAutDriverEvidenceError(
            "canonical launch binding handoff is not canonical base64 JSON"
        ) from exc
    if not isinstance(decoded, dict) or not decoded:
        raise ExternalAutDriverEvidenceError(
            "canonical launch binding handoff must be an object"
        )
    canonical = json.dumps(
        decoded,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if raw != canonical:
        raise ExternalAutDriverEvidenceError(
            "canonical launch binding handoff JSON bytes are not canonical"
        )
    return decoded


def external_aut_canonical_binding_projection(
    binding: Mapping[str, Any],
    *,
    platform: str,
    device_id: str,
    target: str,
    environment: str,
) -> dict[str, object]:
    """Project only identities the external native journey is allowed to claim."""

    normalized_platform = str(platform or "").strip().lower()
    if normalized_platform not in _PLATFORM_CONTRACT:
        raise ExternalAutDriverEvidenceError(
            f"unsupported external AUT platform={platform or '<missing>'}"
        )
    expected = {
        "platform": normalized_platform,
        "deviceId": str(device_id or "").strip(),
        "target": str(target or "").strip(),
        "environment": str(environment or "").strip(),
    }
    mismatched = [
        field
        for field, value in expected.items()
        if not value or str(binding.get(field) or "").strip() != value
    ]
    if mismatched:
        raise ExternalAutDriverEvidenceError(
            "canonical launch binding differs from external AUT run on "
            + ",".join(mismatched)
        )
    application_id = _application_id(
        binding.get("applicationId"), "canonical applicationId"
    )
    artifact_digest = _digest(
        binding.get("artifactDigest"), "canonical artifactDigest"
    )
    candidate_digest = _digest(
        binding.get("candidateDigest"), "canonical candidateDigest"
    )
    launch_attempt_id = str(binding.get("launchAttemptId") or "").strip()
    if not launch_attempt_id:
        raise ExternalAutDriverEvidenceError(
            "canonical launchAttemptId is missing"
        )
    canonical_process_id = binding.get("canonicalProcessId")
    if (
        not isinstance(canonical_process_id, int)
        or isinstance(canonical_process_id, bool)
        or canonical_process_id <= 0
    ):
        raise ExternalAutDriverEvidenceError(
            "canonical device-observed production processId is missing"
        )
    return {
        **expected,
        "applicationId": application_id,
        "artifactDigest": artifact_digest,
        "candidateDigest": candidate_digest,
        "launchAttemptId": launch_attempt_id,
        "canonicalProcessId": canonical_process_id,
        "canonicalLaunchBindingDigest": _canonical_document_digest(binding),
    }


def external_aut_native_test_inputs(
    *, platform: str, production_application_id: str
) -> dict[str, object]:
    """Build only native-driver inputs; never mutate Patrol's host identity flags."""

    normalized_platform = platform.strip().lower()
    if normalized_platform not in _PLATFORM_CONTRACT:
        raise ExternalAutDriverEvidenceError(
            f"unsupported external AUT platform={platform or '<missing>'}"
        )
    production_id = _application_id(
        production_application_id, "production_application_id"
    )
    host_id = str(
        _PLATFORM_CONTRACT[normalized_platform]["testHostApplicationId"]
    )
    driver_id = str(
        _PLATFORM_CONTRACT[normalized_platform]["driverApplicationId"]
    )
    if production_id in {host_id, driver_id}:
        raise ExternalAutDriverEvidenceError(
            "production AUT identity equals a native driver/test host identity"
        )

    if normalized_platform == "android":
        return {
            "platform": "android",
            "testClass": ANDROID_EXTERNAL_AUT_TEST_CLASS,
            "instrumentationArguments": {
                "qwqTargetPackage": production_id,
                "qwqExpectedPackage": production_id,
            },
        }
    return {
        "platform": "ios",
        "onlyTesting": IOS_EXTERNAL_AUT_ONLY_TESTING,
        "testEnvironment": {
            "QWQ_IOS_TARGET_BUNDLE_ID": production_id,
            "QWQ_IOS_EXPECTED_BUNDLE_ID": production_id,
        },
    }


def android_external_aut_instrumentation_command(
    *,
    adb: str,
    device_id: str,
    production_application_id: str,
) -> list[str]:
    """Address the independent driver package, never Patrol's AUT flags."""

    executable = str(adb or "").strip()
    normalized_device_id = str(device_id or "").strip()
    production_id = _application_id(
        production_application_id, "production_application_id"
    )
    if not executable or not normalized_device_id:
        raise ExternalAutDriverEvidenceError(
            "Android external AUT driver requires adb and an exact deviceId"
        )
    return [
        executable,
        "-s",
        normalized_device_id,
        "shell",
        "am",
        "instrument",
        "-w",
        "-r",
        "-e",
        "class",
        ANDROID_EXTERNAL_AUT_TEST_CLASS,
        "-e",
        "qwqTargetPackage",
        production_id,
        "-e",
        "qwqExpectedPackage",
        production_id,
        PATROL_ANDROID_INSTRUMENTATION_COMPONENT,
    ]




def parse_external_aut_homepage_evidence(output: str) -> dict[str, object]:
    """Read exactly one native JSON marker from logcat or XCTest output."""

    decoded: list[dict[str, object]] = []
    decoder = json.JSONDecoder()
    for line in output.splitlines():
        marker_index = line.find(EXTERNAL_AUT_MARKER)
        if marker_index < 0:
            continue
        candidate = line[marker_index + len(EXTERNAL_AUT_MARKER) :].strip()
        try:
            value, end = decoder.raw_decode(candidate)
        except (TypeError, ValueError) as exc:
            raise ExternalAutDriverEvidenceError(
                f"external AUT marker is not canonical JSON: {exc}"
            ) from exc
        if candidate[end:].strip():
            raise ExternalAutDriverEvidenceError(
                "external AUT marker has trailing non-JSON bytes"
            )
        if not isinstance(value, dict):
            raise ExternalAutDriverEvidenceError(
                "external AUT marker payload must be an object"
            )
        decoded.append(value)
    if len(decoded) != 1:
        raise ExternalAutDriverEvidenceError(
            f"expected exactly one external AUT marker, observed {len(decoded)}"
        )
    return decoded[0]


def validate_external_aut_homepage_evidence(
    evidence: dict[str, Any],
    *,
    platform: str,
    production_application_id: str,
    canonical_process_id: int | None = None,
) -> dict[str, object]:
    """Fail closed unless native evidence proves exact identity and PID continuity."""

    normalized_platform = platform.strip().lower()
    contract = _PLATFORM_CONTRACT.get(normalized_platform)
    if contract is None:
        raise ExternalAutDriverEvidenceError(
            f"unsupported external AUT platform={platform or '<missing>'}"
        )
    if set(evidence) != _EVIDENCE_FIELDS:
        missing = sorted(_EVIDENCE_FIELDS - set(evidence))
        unknown = sorted(set(evidence) - _EVIDENCE_FIELDS)
        raise ExternalAutDriverEvidenceError(
            f"external AUT evidence fields differ missing={missing} unknown={unknown}"
        )
    if evidence.get("schema") != EXTERNAL_AUT_HOMEPAGE_SCHEMA:
        raise ExternalAutDriverEvidenceError("external AUT evidence schema mismatch")
    if evidence.get("platform") != normalized_platform:
        raise ExternalAutDriverEvidenceError("external AUT platform mismatch")

    expected_production_id = _application_id(
        production_application_id, "production_application_id"
    )
    production_id = _application_id(
        evidence.get("productionApplicationId"), "productionApplicationId"
    )
    driver_id = _application_id(
        evidence.get("driverApplicationId"), "driverApplicationId"
    )
    test_host_id = _application_id(
        evidence.get("testHostApplicationId"), "testHostApplicationId"
    )
    if production_id != expected_production_id:
        raise ExternalAutDriverEvidenceError(
            "external AUT identity differs from the canonical artifact identity"
        )
    if test_host_id != contract["testHostApplicationId"]:
        raise ExternalAutDriverEvidenceError("Patrol test host identity mismatch")
    if driver_id != contract["driverApplicationId"]:
        raise ExternalAutDriverEvidenceError("native driver identity mismatch")
    if len({production_id, driver_id, test_host_id}) != 3:
        raise ExternalAutDriverEvidenceError(
            "production AUT, native driver, and Patrol host identities must be distinct"
        )

    pid_before = evidence.get("processIdBefore")
    pid_after = evidence.get("processIdAfter")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in (pid_before, pid_after)
    ):
        raise ExternalAutDriverEvidenceError("external AUT PIDs must be positive integers")
    if pid_before != pid_after:
        raise ExternalAutDriverEvidenceError(
            "external AUT process was replaced during native observation"
        )
    if canonical_process_id is not None and (
        not isinstance(canonical_process_id, int)
        or isinstance(canonical_process_id, bool)
        or canonical_process_id <= 0
        or canonical_process_id != pid_before
        or canonical_process_id != pid_after
    ):
        raise ExternalAutDriverEvidenceError(
            "external AUT process differs from the canonical safe-terminal process"
        )
    if evidence.get("stateBefore") not in contract["stateBefore"]:
        raise ExternalAutDriverEvidenceError(
            "external AUT was not already running before foreground activation"
        )
    if evidence.get("stateAfter") != contract["stateAfter"]:
        raise ExternalAutDriverEvidenceError(
            "external AUT did not reach the foreground running state"
        )
    if evidence.get("activationMode") != contract["activationMode"]:
        raise ExternalAutDriverEvidenceError("external AUT activation mode mismatch")
    if evidence.get("launchPerformed") is not False:
        raise ExternalAutDriverEvidenceError(
            "external AUT driver must not launch a replacement process"
        )
    if (
        evidence.get("homepageAccessibilityIdentifier")
        != HOME_SURFACE_ACCESSIBILITY_IDENTIFIER
        or evidence.get("homepageVisible") is not True
        or evidence.get("homepageFrameIntersectsVisibleWindow") is not True
    ):
        raise ExternalAutDriverEvidenceError(
            "production AUT home accessibility/visible-frame assertion did not pass"
        )

    canonical = copy.deepcopy(evidence)
    encoded = json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return {
        "schema": EXTERNAL_AUT_HOMEPAGE_SCHEMA,
        "provenance": "external_production_aut_native_accessibility",
        "evidenceDigest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "evidence": canonical,
    }


def collect_external_aut_homepage_evidence(
    output: str,
    *,
    platform: str,
    production_application_id: str,
    canonical_process_id: int | None = None,
) -> dict[str, object]:
    """Parse and validate a native driver's single black-box evidence marker."""

    return validate_external_aut_homepage_evidence(
        parse_external_aut_homepage_evidence(output),
        platform=platform,
        production_application_id=production_application_id,
        canonical_process_id=canonical_process_id,
    )


def build_external_aut_homepage_journey(
    *,
    native_evidence: dict[str, Any],
    native_driver_artifact_binding: Mapping[str, Any],
    canonical_binding: Mapping[str, Any],
    patrol_target: str,
    environment_alias: str,
    platform: str,
    device_id: str,
    target: str,
    environment: str,
) -> dict[str, object]:
    """Bind native PID/home proof to application, artifact, and candidate."""

    projection = external_aut_canonical_binding_projection(
        canonical_binding,
        platform=platform,
        device_id=device_id,
        target=target,
        environment=environment,
    )
    validated_driver = validate_external_aut_driver_artifact_binding(
        native_driver_artifact_binding,
        expected_platform=platform,
        expected_device_id=device_id,
    )
    validated_native = validate_external_aut_homepage_evidence(
        native_evidence,
        platform=platform,
        production_application_id=str(projection["applicationId"]),
        canonical_process_id=int(projection["canonicalProcessId"]),
    )
    journey: dict[str, object] = {
        "schema": EXTERNAL_AUT_JOURNEY_SCHEMA,
        "status": "passed",
        "journeyId": EXTERNAL_AUT_JOURNEY_ID,
        "patrolTarget": str(patrol_target or "").strip(),
        "environmentAlias": str(environment_alias or "").strip(),
        "platform": str(platform or "").strip().lower(),
        "deviceId": str(device_id or "").strip(),
        "canonicalLaunch": projection,
        "nativeEvidence": validated_native,
        "nativeDriverArtifactBindingDigest": _canonical_document_digest(
            validated_driver
        ),
    }
    validate_external_aut_homepage_journey(
        journey,
        launch_binding=canonical_binding,
        native_driver_artifact_binding=validated_driver,
        expected_patrol_target=journey["patrolTarget"],
        expected_environment_alias=journey["environmentAlias"],
        expected_platform=journey["platform"],
        expected_device_id=journey["deviceId"],
        expected_target=target,
        expected_environment=environment,
    )
    return journey


def validate_external_aut_homepage_journey(
    journey: Mapping[str, Any],
    *,
    launch_binding: Mapping[str, Any],
    native_driver_artifact_binding: Mapping[str, Any],
    expected_patrol_target: object,
    expected_environment_alias: object,
    expected_platform: object,
    expected_device_id: object,
    expected_target: object | None = None,
    expected_environment: object | None = None,
) -> dict[str, object]:
    """Validate the report projection against the live canonical launch binding."""

    if set(journey) != _JOURNEY_FIELDS:
        raise ExternalAutDriverEvidenceError(
            "external AUT journey fields differ from the canonical schema"
        )
    if (
        journey.get("schema") != EXTERNAL_AUT_JOURNEY_SCHEMA
        or journey.get("status") != "passed"
        or journey.get("journeyId") != EXTERNAL_AUT_JOURNEY_ID
    ):
        raise ExternalAutDriverEvidenceError(
            "external AUT journey status or schema is invalid"
        )
    expected_page = {
        "patrolTarget": str(expected_patrol_target or "").strip(),
        "environmentAlias": str(expected_environment_alias or "").strip(),
        "platform": str(expected_platform or "").strip().lower(),
        "deviceId": str(expected_device_id or "").strip(),
    }
    mismatched_page = [
        field
        for field, expected in expected_page.items()
        if not expected or journey.get(field) != expected
    ]
    if mismatched_page:
        raise ExternalAutDriverEvidenceError(
            "external AUT journey page identity differs on "
            + ",".join(mismatched_page)
        )
    target = str(
        expected_target
        if expected_target is not None
        else launch_binding.get("target")
        or ""
    ).strip()
    environment = str(
        expected_environment
        if expected_environment is not None
        else launch_binding.get("environment")
        or ""
    ).strip()
    projection = external_aut_canonical_binding_projection(
        launch_binding,
        platform=expected_page["platform"],
        device_id=expected_page["deviceId"],
        target=target,
        environment=environment,
    )
    reported_projection = journey.get("canonicalLaunch")
    if (
        not isinstance(reported_projection, Mapping)
        or set(reported_projection) != _CANONICAL_BINDING_PROJECTION_FIELDS
        or dict(reported_projection) != projection
    ):
        raise ExternalAutDriverEvidenceError(
            "external AUT canonical application/artifact/candidate binding drifted"
        )
    validated_driver = validate_external_aut_driver_artifact_binding(
        native_driver_artifact_binding,
        expected_platform=expected_page["platform"],
        expected_device_id=expected_page["deviceId"],
    )
    if journey.get("nativeDriverArtifactBindingDigest") != (
        _canonical_document_digest(validated_driver)
    ):
        raise ExternalAutDriverEvidenceError(
            "external AUT native driver artifact binding drifted"
        )
    native = journey.get("nativeEvidence")
    if not isinstance(native, Mapping) or set(native) != {
        "schema",
        "provenance",
        "evidenceDigest",
        "evidence",
    }:
        raise ExternalAutDriverEvidenceError(
            "external AUT native evidence envelope is malformed"
        )
    raw_evidence = native.get("evidence")
    if not isinstance(raw_evidence, dict):
        raise ExternalAutDriverEvidenceError(
            "external AUT native evidence payload is malformed"
        )
    revalidated = validate_external_aut_homepage_evidence(
        raw_evidence,
        platform=expected_page["platform"],
        production_application_id=str(projection["applicationId"]),
        canonical_process_id=int(projection["canonicalProcessId"]),
    )
    if dict(native) != revalidated:
        raise ExternalAutDriverEvidenceError(
            "external AUT native evidence digest or provenance drifted"
        )
    comparison = {
        "applicationId": projection["applicationId"],
        "artifactDigest": projection["artifactDigest"],
        "candidateDigest": projection["candidateDigest"],
        "launchAttemptId": projection["launchAttemptId"],
        "canonicalProcessId": projection["canonicalProcessId"],
    }
    return {
        "status": "passed",
        "provenance": "external_production_aut_native_accessibility",
        "journeyId": EXTERNAL_AUT_JOURNEY_ID,
        "comparisonKeys": list(comparison),
        "tested": comparison,
        "canonical": dict(comparison),
        "canonicalLaunchBindingDigest": projection[
            "canonicalLaunchBindingDigest"
        ],
        "nativeEvidenceDigest": revalidated["evidenceDigest"],
        "nativeDriverArtifactBindingDigest": _canonical_document_digest(
            validated_driver
        ),
    }


def new_external_aut_journey_set(*, required: bool) -> dict[str, object]:
    return {
        "schema": EXTERNAL_AUT_JOURNEY_SET_SCHEMA,
        "status": "pending" if required else "not_required",
        "required": required,
        "journeys": [],
    }


def external_aut_journey_blocker() -> dict[str, object]:
    return {
        "errorCode": APP_PAGE_ARTIFACT_BINDING_BLOCKER,
        "sourceOperationId": (
            "environment_page_smoke.external_production_aut_homepage"
        ),
        "httpStatus": None,
    }


def unavailable_external_aut_journey(
    *,
    reason: str,
    platform: str,
    device_id: str,
    status: str = "gate_block",
) -> dict[str, object]:
    if status not in {"gate_block", "not_executed"}:
        raise ValueError("external AUT unavailable status is invalid")
    journey: dict[str, object] = {
        "schema": EXTERNAL_AUT_JOURNEY_SCHEMA,
        "status": status,
        "journeyId": EXTERNAL_AUT_JOURNEY_ID,
        "platform": str(platform or "").strip().lower(),
        "deviceId": str(device_id or "").strip(),
        "reason": " ".join(str(reason).split()).strip(),
    }
    if status == "gate_block":
        journey["errorCode"] = APP_PAGE_ARTIFACT_BINDING_BLOCKER
    return journey


def attach_external_aut_journey(
    report: dict[str, Any], journey: dict[str, object]
) -> None:
    collection = report.get("externalProductionAutJourneys")
    if (
        not isinstance(collection, dict)
        or collection.get("schema") != EXTERNAL_AUT_JOURNEY_SET_SCHEMA
        or collection.get("required") is not True
    ):
        raise ExternalAutDriverEvidenceError(
            "external AUT report collection was not requested"
        )
    journeys = collection.get("journeys")
    if not isinstance(journeys, list):
        raise ExternalAutDriverEvidenceError(
            "external AUT report journeys are malformed"
        )
    if journeys:
        raise ExternalAutDriverEvidenceError(
            "external AUT report accepts exactly one named journey"
        )
    journeys.append(copy.deepcopy(journey))


def settle_external_aut_journey_report(report: dict[str, Any]) -> None:
    collection = report.get("externalProductionAutJourneys")
    if not isinstance(collection, dict) or collection.get("schema") != (
        EXTERNAL_AUT_JOURNEY_SET_SCHEMA
    ):
        collection = new_external_aut_journey_set(required=False)
        report["externalProductionAutJourneys"] = collection
    required = collection.get("required") is True
    journeys = collection.get("journeys")
    if not isinstance(journeys, list):
        journeys = []
        collection["journeys"] = journeys
    if not required:
        collection["status"] = "not_required"
        collection.pop("errorCode", None)
        return
    if len(journeys) == 1 and isinstance(journeys[0], dict):
        status = journeys[0].get("status")
        if status == "passed":
            platform = str(journeys[0].get("platform") or "").strip().lower()
            device_id = str(journeys[0].get("deviceId") or "").strip()
            native_driver = report.get(
                "externalProductionAutDriverArtifact"
            )
            try:
                if not isinstance(native_driver, Mapping):
                    raise ExternalAutDriverEvidenceError(
                        "external AUT native driver artifact is missing"
                    )
                validated_driver = validate_external_aut_driver_artifact_binding(
                    native_driver,
                    expected_platform=platform,
                    expected_device_id=device_id,
                )
                if journeys[0].get(
                    "nativeDriverArtifactBindingDigest"
                ) != _canonical_document_digest(validated_driver):
                    raise ExternalAutDriverEvidenceError(
                        "external AUT native driver artifact differs from its journey"
                    )
            except ExternalAutDriverEvidenceError:
                collection["status"] = "gate_block"
                collection["errorCode"] = APP_PAGE_ARTIFACT_BINDING_BLOCKER
            else:
                collection["status"] = "passed"
                collection.pop("errorCode", None)
                return
        if status == "not_executed" and report.get("status") == "dry_run":
            collection["status"] = "not_executed"
            collection.pop("errorCode", None)
            return
    collection["status"] = "gate_block"
    collection["errorCode"] = APP_PAGE_ARTIFACT_BINDING_BLOCKER
    if report.get("status") == "passed":
        report["status"] = "gate_block"
        report["failureReason"] = (
            "external production AUT startup/homepage journey is missing or invalid"
        )
