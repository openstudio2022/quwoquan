"""环境 Patrol smoke 的常量与共享标识（target 路径、证据前缀、正则、目录）。

正文自 run_environment_patrol_smoke.py 逐字搬入；REPO_ROOT 因包层级加深由
parents[3] 改为 parents[4]，指向同一仓库根。
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.video_playback_evidence import (
    VIDEO_PLAYBACK_EVIDENCE_MARKER,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


APP_DIR = REPO_ROOT / "quwoquan_app"
APP_LAUNCHER_HANDOFF_BUILDER = (
    APP_DIR / "scripts" / "device" / "build_launcher_handoff.py"
)
PATROL_TEST_DIRECTORY = "test/user_acceptance/patrol"
DEFAULT_REPORT = REPO_ROOT / ".qwq_output" / "env" / "repo" / "runs" / "device-matrix" / "environment-smoke" / "report.json"
DEFAULT_TARGET = (
    "test/user_acceptance/journeys/home_video_playback/"
    "video_playback_canary__user_acceptance_test.dart"
)
HOME_VIDEO_PLAYBACK_TARGET = (
    "test/user_acceptance/journeys/home_video_playback/"
    "home_video_playback__user_acceptance_test.dart"
)
CORE_READBACK_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
    "app_core_readback__user_acceptance_test.dart"
)
PROFILE_JOURNEY_TARGET = (
    "test/user_acceptance/journeys/profile/"
    "profile_journey__user_acceptance_test.dart"
)
MESSAGE_HOME_TARGET = (
    "test/user_acceptance/service/chat_service/chat/chat_inbox_view/"
    "message_home_remote__user_acceptance_test.dart"
)
FEED_LOAD_TARGET = (
    "test/user_acceptance/service/content_service/content/feed_delivery_page/"
    "feed_load__user_acceptance_test.dart"
)
FEED_CONTENT_EVIDENCE_PREFIX = "QWQ_FEED_CONTENT_EVIDENCE "
APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX = (
    "QWQ_APP_CONTENT_PAGE_SCREENSHOT_READY "
)
CONTROLLED_EDGE_FAULT_TARGET = (
    "test/user_acceptance/service/content_service/content/feed_delivery_page/"
    "feed_controlled_edge_recovery__user_acceptance_test.dart"
)
CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX = (
    "QWQ_APP_CONTENT_EDGE_RESTORE_REQUEST "
)
CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX = "QWQ_APP_CONTENT_FAULT_EVIDENCE "
CONTROLLED_EDGE_FAULT_COPY_KEYS = frozenset(
    {
        "connectionUnavailable",
        "requestTimedOut",
        "serviceUnavailable",
        "guestSessionUnavailable",
    }
)
RELEASE_APP_UAT_DEFINES = (
    ("data_release_id", "DATA_RELEASE_ID"),
    ("data_release_class", "DATA_RELEASE_CLASS"),
    ("product_lifecycle_state", "PRODUCT_LIFECYCLE_STATE"),
    ("data_release_homepage_id", "DATA_RELEASE_HOMEPAGE_ID"),
    ("data_release_homepage_title", "DATA_RELEASE_HOMEPAGE_TITLE"),
    ("data_release_article_work_id", "DATA_RELEASE_ARTICLE_WORK_ID"),
    ("data_release_article_title", "DATA_RELEASE_ARTICLE_TITLE"),
    ("data_release_image_work_id", "DATA_RELEASE_IMAGE_WORK_ID"),
    ("data_release_image_title", "DATA_RELEASE_IMAGE_TITLE"),
    ("data_release_creator_name", "DATA_RELEASE_CREATOR_NAME"),
    ("data_release_creator_user_handle", "DATA_RELEASE_CREATOR_USER_HANDLE"),
    ("data_release_creator_persona_id", "DATA_RELEASE_CREATOR_PERSONA_ID"),
    (
        "data_release_creator_avatar_asset_id",
        "DATA_RELEASE_CREATOR_AVATAR_ASSET_ID",
    ),
    ("data_release_tag_label", "DATA_RELEASE_TAG_LABEL"),
    ("data_release_video_attribution", "DATA_RELEASE_VIDEO_ATTRIBUTION"),
)
APP_CONTENT_VIDEO_PAGE_COUNT_ENV = "QWQ_APP_CONTENT_VIDEO_PAGE_COUNT"
BASIC_VIABILITY_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
    "basic_viability__user_acceptance_test.dart"
)
ACCOUNT_CLOSURE_TARGET = (
    "test/user_acceptance/service/user_service/account/user_account/"
    "account_closure_remote__user_acceptance_test.dart"
)
RUNTIME_RECOVERY_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
    "runtime_recovery_journey__user_acceptance_test.dart"
)
RUNTIME_RECOVERY_EVIDENCE_PREFIX = "QWQ_RUNTIME_RECOVERY_EVIDENCE "
RUNTIME_RECOVERY_EVIDENCE_FIELDS = frozenset(
    {
        "authenticatedBefore",
        "authenticatedAfter",
        "sameOwner",
        "samePersona",
        "homeRestored",
        "secondFaultNoReentry",
    }
)
ACCOUNT_ENFORCEMENT_TARGETS = {
    "suspended": (
        "test/user_acceptance/journeys/account_enforcement/"
        "account_enforcement_suspended__user_acceptance_test.dart"
    ),
    "restored": (
        "test/user_acceptance/journeys/account_enforcement/"
        "account_enforcement_restored__user_acceptance_test.dart"
    ),
}
ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX = "QWQ_ACCOUNT_ENFORCEMENT_EVIDENCE "
ACCOUNT_ENFORCEMENT_CANDIDATE_DIGEST_PATTERN = re.compile(
    r"^sha256:[0-9a-f]{64}$"
)
CANONICAL_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV = (
    "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
)
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_SCHEMA = (
    "stackctl.provider_conformance_runtime_identity"
)
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_COMMON_FIELDS = frozenset(
    {
        "schema",
        "runtimeMode",
        "environment",
        "target",
        "workload",
        "startupAttemptId",
        "providerRuntimeDigest",
        "failureFree",
        "nonPromotable",
    }
)
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_IMMUTABLE_FIELDS = frozenset(
    {"candidateDigest"}
)
PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_MUTABLE_FIELDS = frozenset(
    {
        "mutableComposeDigest",
        "mutableConfigurationDigest",
        "mutableStateDigest",
        "mutableWorkspaceStatusDigest",
        "mutableResolverHandoffDigest",
        "mutableSourceRevision",
    }
)
CANONICAL_TEST_LIVE_DART_DEFINE_KEYS = frozenset(
    {
        "APP_RUNTIME_ENV",
        "QWQ_APP_LAUNCH_MODE",
        "APP_LAUNCH_POLICY",
        "CLOUD_GATEWAY_BASE_URL",
        "APP_LEGAL_BASE_URL",
        "PUBLIC_WEB_BASE_URL",
        "APP_DOWNLOAD_BASE_URL",
        "MEDIA_AVATAR_CDN_BASE_URL",
        "MEDIA_IMAGE_CDN_BASE_URL",
        "MEDIA_VIDEO_CDN_BASE_URL",
        "MEDIA_UPLOAD_BASE_URL",
        "RTC_MEDIA_CONNECTION_URL",
    }
)
ACCOUNT_ENFORCEMENT_EXPECTED_EVIDENCE: dict[str, dict[str, Any]] = {
    "suspended": {
        "phase": "suspended",
        "remoteCode": "USER.AUTH.account_suspended",
        "sessionCredentialsCleared": True,
        "restrictionSurfaceVisible": True,
    },
    "restored": {
        "phase": "restored",
        "remoteProfileRead": True,
        "sessionAuthenticated": True,
        "safeHomeVisible": True,
    },
}
IOS_SDK_VERSION_PATTERN = re.compile(r"iOS[- ](\d+)(?:[-._](\d+))?")
IOS_RUNTIME_VERSION_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
XCODE_IOS_SIMULATOR_SDK_PATTERN = re.compile(
    r"-sdk\s+iphonesimulator(\d+)(?:\.(\d+))?"
)
XCTEST_EXECUTION_SUMMARY_PATTERN = re.compile(
    r"Executed\s+(?P<executed>\d+)\s+tests?,\s+with\s+"
    r"(?:(?P<skipped>\d+)\s+tests?\s+skipped\s+and\s+)?"
    r"(?P<failed>\d+)\s+failures?",
)
PATROL_EXECUTION_SUMMARY_PATTERN = re.compile(
    r"📝\s+Total:\s*(?P<executed>\d+).*?"
    r"❌\s+Failed:\s*(?P<failed>\d+).*?"
    r"⏩\s+Skipped:\s*(?P<skipped>\d+)",
    re.DOTALL,
)
XCODE_GLOBAL_PRODUCTS_DIR = Path.home() / "Library" / "Developer" / "Xcode" / "XcodeDerivedData" / "Build" / "Products"
PATROL_IOS_PRODUCTS_DIR = APP_DIR / "build" / "ios_integ" / "Build" / "Products"
LOCAL_TARGETS = {"alpha-local", "beta-local", "gamma-local", "prod-sim"}
LOCAL_ENVIRONMENT_ALIAS_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
    "local-alpha": "alpha-local",
    "local-beta": "beta-local",
    "local-gamma": "gamma-local",
    "local-prod-sim": "prod-sim",
}
RUNTIME_ANONYMOUS_SESSION_MODES = {
    "local-beta": "runtime_anonymous_session",
    "beta-local": "runtime_anonymous_session",
    "local-gamma": "runtime_anonymous_session",
    "gamma-local": "runtime_anonymous_session",
    "local-prod-sim": "runtime_anonymous_session",
    "prod-sim": "runtime_anonymous_session",
}
TYPED_TEST_DATA_ACTOR_ENV = {
    "access_token": "QWQ_TEST_DATA_ACCESS_TOKEN",
    "refresh_token": "QWQ_TEST_DATA_REFRESH_TOKEN",
    "owner_id": "QWQ_TEST_DATA_OWNER_ID",
    "persona_id": "QWQ_TEST_DATA_PERSONA_ID",
}
TYPED_TEST_DATA_CONVERSATION_ENV = {
    "conversation_id": "QWQ_TEST_DATA_CONVERSATION_ID",
    "message_ids_json": "QWQ_TEST_DATA_MESSAGE_IDS_JSON",
}
TYPED_AUTHENTICATED_SESSION_TARGETS = (
    BASIC_VIABILITY_TARGET,
    CORE_READBACK_TARGET,
    HOME_VIDEO_PLAYBACK_TARGET,
    MESSAGE_HOME_TARGET,
    PROFILE_JOURNEY_TARGET,
)
TYPED_TEST_DATA_CONVERSATION_TARGETS = (MESSAGE_HOME_TARGET,)
ALPHA_APP_CONTENT_TYPED_SESSION_TARGETS = (
    FEED_LOAD_TARGET,
    DEFAULT_TARGET,
    CONTROLLED_EDGE_FAULT_TARGET,
)
FORBIDDEN_PROD_PLAYBACK_CANARY_TOKENS = frozenset(
    {"fixture", "mock", "seed", "test"}
)
# App 主包身份按 canonical application_identity 映射推导（环境 × BuildMode），
# 不再自持单一字面值；UITests xctrunner 的 bundle id 不随主包身份变化。
IOS_RUNNER_UITESTS_XCTRUNNER_BUNDLE_ID = (
    "com.example.quwoquanApp.RunnerUITests.xctrunner"
)


def ios_release_uat_bundle_ids(
    environment: str,
    build_mode: str = "debug",
) -> tuple[str, ...]:
    from quwoquan_ops.cli.lib.app_identity import application_id_for

    return (
        application_id_for("ios", environment, build_mode),
        IOS_RUNNER_UITESTS_XCTRUNNER_BUNDLE_ID,
    )


def android_release_uat_package(
    environment: str,
    build_mode: str = "debug",
) -> str:
    from quwoquan_ops.cli.lib.app_identity import application_id_for

    return application_id_for("android", environment, build_mode)
IOS_DEVICE_EVIDENCE_TOKENS = (
    FEED_CONTENT_EVIDENCE_PREFIX,
    APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX,
    VIDEO_PLAYBACK_EVIDENCE_MARKER,
    CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX,
    CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX,
    RUNTIME_RECOVERY_EVIDENCE_PREFIX,
    ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX,
    "[bootstrap] source=zone_guarded exception=",
    "feed recovery did not leave blocking error",
)
ANDROID_DEVICE_EVIDENCE_TOKENS = IOS_DEVICE_EVIDENCE_TOKENS
ANDROID_DEVICE_EVIDENCE_LOG_TAG = "QWQPatrolEvidence"
PATROL_FLUTTER_COMMAND_ENV = "PATROL_FLUTTER_COMMAND"
ANDROID_DEVICE_PROXY = (
    REPO_ROOT / "quwoquan_ops" / "cli" / "lib" / "flutter_android_device_proxy.py"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
