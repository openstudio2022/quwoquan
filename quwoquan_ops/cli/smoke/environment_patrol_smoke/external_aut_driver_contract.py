"""Shared closed-set contract for external production AUT evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.generated.app_launch_contract import LAUNCH_BLOCKERS

APP_PAGE_ARTIFACT_BINDING_BLOCKER = "APP.UAT.page_artifact_binding_missing"
if APP_PAGE_ARTIFACT_BINDING_BLOCKER not in LAUNCH_BLOCKERS:
    raise RuntimeError(
        "canonical app-launch contract is missing the page artifact binding blocker"
    )

EXTERNAL_AUT_HOMEPAGE_SCHEMA = (
    "environment-page-smoke.external-aut-homepage.v1"
)
EXTERNAL_AUT_JOURNEY_SCHEMA = (
    "environment-page-smoke.external-production-aut-journey.v1"
)
EXTERNAL_AUT_JOURNEY_SET_SCHEMA = (
    "environment-page-smoke.external-production-aut-journey-set.v1"
)
EXTERNAL_AUT_DRIVER_ARTIFACT_SCHEMA = (
    "environment-page-smoke.external-aut-native-driver-artifact.v1"
)
EXTERNAL_AUT_MARKER = "QWQ_EXTERNAL_AUT "
EXTERNAL_AUT_JOURNEY_ID = "production-startup-homepage"
EXTERNAL_AUT_CANONICAL_BINDING_ENV = (
    "QWQ_EXTERNAL_AUT_CANONICAL_BINDING_B64"
)
HOME_SURFACE_ACCESSIBILITY_IDENTIFIER = "qwq.surface.home"
PATROL_ANDROID_HOST_APPLICATION_ID = "com.quwoquan.testhost.patrol"
PATROL_IOS_HOST_APPLICATION_ID = "com.quwoquan.testhost.patrol"
PATROL_ANDROID_INSTRUMENTATION_COMPONENT = (
    "com.quwoquan.testhost.patrol.test/"
    "pl.leancode.patrol.PatrolJUnitRunner"
)
PATROL_ANDROID_DRIVER_APPLICATION_ID = "com.quwoquan.testhost.patrol.test"
PATROL_IOS_XCTRUNNER_BUNDLE_ID = (
    "com.quwoquan.testhost.patrol.RunnerUITests.xctrunner"
)
PATROL_IOS_XCTEST_BUNDLE_ID = "com.quwoquan.testhost.patrol.RunnerUITests"
ANDROID_EXTERNAL_AUT_TEST_CLASS = (
    "com.quwoquan.testhost.patrol.ProductionHomepageExternalAutTest"
)
IOS_EXTERNAL_AUT_ONLY_TESTING = (
    "RunnerUITests/QWQProductionHomepageExternalAUTTests/"
    "testReusesCanonicalProductionProcessAndFindsHomeSurface"
)

_APPLICATION_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)+$"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_FIELDS = frozenset(
    {
        "schema",
        "platform",
        "driverApplicationId",
        "testHostApplicationId",
        "productionApplicationId",
        "processIdBefore",
        "processIdAfter",
        "stateBefore",
        "stateAfter",
        "activationMode",
        "launchPerformed",
        "homepageAccessibilityIdentifier",
        "homepageVisible",
        "homepageFrameIntersectsVisibleWindow",
    }
)
_PLATFORM_CONTRACT = {
    "android": {
        "driverApplicationId": PATROL_ANDROID_DRIVER_APPLICATION_ID,
        "testHostApplicationId": PATROL_ANDROID_HOST_APPLICATION_ID,
        "stateBefore": {"running_foreground"},
        "stateAfter": "running_foreground",
        "activationMode": "observe_existing_foreground_process",
    },
    "ios": {
        "driverApplicationId": PATROL_IOS_XCTRUNNER_BUNDLE_ID,
        "testHostApplicationId": PATROL_IOS_HOST_APPLICATION_ID,
        "stateBefore": {"running_background", "running_foreground"},
        "stateAfter": "running_foreground",
        "activationMode": "activate_existing_process",
    },
}
_CANONICAL_BINDING_PROJECTION_FIELDS = frozenset(
    {
        "environment",
        "target",
        "platform",
        "deviceId",
        "applicationId",
        "artifactDigest",
        "candidateDigest",
        "launchAttemptId",
        "canonicalProcessId",
        "canonicalLaunchBindingDigest",
    }
)
_JOURNEY_FIELDS = frozenset(
    {
        "schema",
        "status",
        "journeyId",
        "patrolTarget",
        "environmentAlias",
        "platform",
        "deviceId",
        "canonicalLaunch",
        "nativeEvidence",
        "nativeDriverArtifactBindingDigest",
    }
)
_DRIVER_ARTIFACT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "provenance",
        "platform",
        "deviceId",
        "driverApplicationId",
        "testHostApplicationId",
        "artifactKind",
        "artifactDigest",
        "evidenceDigest",
        "evidence",
    }
)
_ANDROID_DRIVER_APK_RELATIVE = Path(
    "build/app/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
)


class ExternalAutDriverEvidenceError(RuntimeError):
    """Typed failure for proxy, replacement-process, or non-home evidence."""

    code = APP_PAGE_ARTIFACT_BINDING_BLOCKER

    def __init__(self, detail: str) -> None:
        normalized = " ".join(str(detail).split()).strip() or "invalid evidence"
        super().__init__(f"{self.code}: {normalized}")
        self.detail = normalized


def _application_id(value: object, field: str) -> str:
    normalized = str(value or "").strip()
    if not _APPLICATION_ID.fullmatch(normalized):
        raise ExternalAutDriverEvidenceError(f"{field} is not an exact application id")
    return normalized


def _digest(value: object, field: str) -> str:
    normalized = str(value or "").strip()
    if _DIGEST.fullmatch(normalized) is None:
        raise ExternalAutDriverEvidenceError(f"{field} is not a canonical digest")
    return normalized


def _canonical_document_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
