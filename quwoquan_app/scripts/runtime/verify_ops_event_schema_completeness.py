#!/usr/bin/env python3
"""Verify OpsEventRecordInput schema completeness.

Checks that OpsEventRecordInput contains all required fields for the
four-layer observability framework:
  - Core identity: eventId, eventType, eventName, occurredAt
  - Session correlation: sessionId, pageVisitId, requestId, traceId
  - Surface context: surfaceId, routeId, operationId, pageName
  - Error context: errorCode, errorModule, errorKind, errorReason
  - Structured payload: payload, metrics

Also verifies JourneyEventTracker / AppLogUploader wiring in providers and
cloudHttpClientProvider usage for Remote HTTP.
"""

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parents[1]  # quwoquan_app/
REPO_ROOT = APP_ROOT.parent       # quwoquan/

OPS_EVENT_FILE = (
    APP_ROOT / "lib" / "cloud" / "services" / "ops" / "ops_event_repository.dart"
)

APP_LOG_UPLOADER_FILE = (
    APP_ROOT / "lib" / "assistant" / "observability" / "logging" / "app_log_uploader.dart"
)

JOURNEY_TRACKER_FILE = APP_ROOT / "lib" / "core" / "trackers" / "journey_event_tracker.dart"

APP_PROVIDERS_FILE = APP_ROOT / "lib" / "core" / "providers" / "app_providers.dart"

REQUIRED_FIELDS = [
    # Core identity
    "eventId",
    "eventType",
    "eventName",
    "occurredAt",
    # Session correlation
    "sessionId",
    "pageVisitId",
    "requestId",
    "traceId",
    # Surface / route context
    "surfaceId",
    "routeId",
    "operationId",
    "pageName",
    # Error context
    "errorCode",
    "errorModule",
    "errorKind",
    "errorReason",
    # Structured payload
    "payload",
    "metrics",
    # Timing
    "clientSentAt",
    # Producer / source
    "producer",
    "source",
]


def verify_ops_event_schema() -> list[str]:
    errors: list[str] = []
    if not OPS_EVENT_FILE.exists():
        errors.append(f"MISSING: {OPS_EVENT_FILE.relative_to(REPO_ROOT)}")
        return errors

    content = OPS_EVENT_FILE.read_text()

    # Extract fields from the class declaration
    class_match = re.search(
        r"class OpsEventRecordInput\b.*?\{(.*?)\n\}",
        content,
        re.DOTALL,
    )
    if not class_match:
        errors.append("Cannot find OpsEventRecordInput class body.")
        return errors

    class_body = class_match.group(1)

    for field in REQUIRED_FIELDS:
        # Check for `this.fieldName` in constructor or `final ... fieldName;` declaration
        pattern_this = rf"\bthis\.{field}\b"
        pattern_decl = rf"\bfinal\b.*\b{field}\b\s*;"
        if not re.search(pattern_this, class_body) and not re.search(
            pattern_decl, class_body
        ):
            errors.append(
                f"OpsEventRecordInput missing required field: {field}"
            )

    # Verify toJson emits required identity fields (not conditional)
    to_json_match = re.search(
        r"Map<String, dynamic> toJson\(\)\s*\{(.*?)\n\s*\}",
        content,
        re.DOTALL,
    )
    if to_json_match:
        to_json_body = to_json_match.group(1)
        for field in ["eventId", "eventType", "eventName", "occurredAt"]:
            if f"'{field}'" not in to_json_body:
                errors.append(
                    f"toJson() does not emit required field: {field}"
                )
    else:
        errors.append("Cannot find toJson() method in OpsEventRecordInput.")

    return errors


def verify_app_log_uploader() -> list[str]:
    errors: list[str] = []
    if not APP_LOG_UPLOADER_FILE.exists():
        errors.append(
            f"MISSING: {APP_LOG_UPLOADER_FILE.relative_to(REPO_ROOT)}"
        )
        return errors

    content = APP_LOG_UPLOADER_FILE.read_text()

    if "eventType: 'app_log'" not in content and "eventType: \"app_log\"" not in content:
        errors.append(
            "AppLogUploader must produce events with eventType='app_log'."
        )

    if "OpsEventRecordInput" not in content:
        errors.append(
            "AppLogUploader must construct OpsEventRecordInput instances."
        )

    if "reportEventBatch" not in content:
        errors.append(
            "AppLogUploader must call reportEventBatch to upload events."
        )

    return errors


def verify_journey_event_tracker() -> list[str]:
    """Ensure JourneyEventTracker builds OpsEventRecordInput with key ops fields."""
    errors: list[str] = []
    if not JOURNEY_TRACKER_FILE.exists():
        errors.append(f"MISSING: {JOURNEY_TRACKER_FILE.relative_to(REPO_ROOT)}")
        return errors

    content = JOURNEY_TRACKER_FILE.read_text()
    if "class JourneyEventTracker" not in content:
        errors.append("JourneyEventTracker class not found.")
    if "OpsEventRecordInput(" not in content:
        errors.append("JourneyEventTracker must construct OpsEventRecordInput.")
        return errors

    # Fields JourneyEventTracker must bind for L1/L2 funnel / correlation
    tracker_named_args = [
        "eventId:",
        "eventType:",
        "eventName:",
        "occurredAt:",
        "clientSentAt:",
        "sessionId:",
        "pageVisitId:",
        "requestId:",
        "producer:",
        "source:",
        "pageName:",
        "targetType:",
        "targetKey:",
        "entityType:",
        "entityId:",
        "payload:",
    ]
    for name in tracker_named_args:
        if name not in content:
            errors.append(
                f"JourneyEventTracker OpsEventRecordInput missing named field: {name}"
            )

    if "reportEventBatch" not in content:
        errors.append("JourneyEventTracker must call reportEventBatch.")

    if "eventType: 'journey'" not in content and 'eventType: "journey"' not in content:
        errors.append("JourneyEventTracker must set eventType to 'journey'.")

    return errors


def verify_app_log_uploader_provider() -> list[str]:
    errors: list[str] = []
    if not APP_PROVIDERS_FILE.exists():
        errors.append(f"MISSING: {APP_PROVIDERS_FILE.relative_to(REPO_ROOT)}")
        return errors

    content = APP_PROVIDERS_FILE.read_text()
    if "appLogUploaderProvider" not in content:
        errors.append(
            "app_providers.dart must define appLogUploaderProvider for AppLogUploader."
        )
    if "AppLogUploader" not in content:
        errors.append("app_providers.dart must reference AppLogUploader.")

    return errors


def verify_cloud_http_client_remote_wiring() -> list[str]:
    """App must wire Remote repositories through cloudHttpClientProvider (central HTTP stack)."""
    errors: list[str] = []
    if not APP_PROVIDERS_FILE.exists():
        return errors

    content = APP_PROVIDERS_FILE.read_text()
    n_providers = len(
        re.findall(r"\bref\.(watch|read)\(\s*cloudHttpClientProvider\s*\)", content)
    )
    if n_providers < 5:
        errors.append(
            f"app_providers.dart must consume cloudHttpClientProvider in at least 5 "
            f"places (Remote HTTP wiring); found {n_providers}."
        )

    return errors


def main() -> int:
    all_errors: list[str] = []
    all_errors.extend(verify_ops_event_schema())
    all_errors.extend(verify_app_log_uploader())
    all_errors.extend(verify_journey_event_tracker())
    all_errors.extend(verify_app_log_uploader_provider())
    all_errors.extend(verify_cloud_http_client_remote_wiring())

    if all_errors:
        print("FAIL: OpsEvent schema completeness check failed:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("PASS: OpsEvent schema completeness verified.")
    print(f"  - OpsEventRecordInput has all {len(REQUIRED_FIELDS)} required fields.")
    print("  - AppLogUploader correctly constructs OpsEventRecordInput.")
    print("  - JourneyEventTracker wires OpsEventRecordInput journey events.")
    print("  - appLogUploaderProvider and cloudHttpClientProvider wiring checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
