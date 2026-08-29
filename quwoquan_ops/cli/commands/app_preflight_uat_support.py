"""Stable parser, target constants, and small helpers for app-content UAT."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# 与 stackctl.ROOT 同源同值(仓库根);仅用于模块加载期常量绑定,
# 函数体内仍统一经 `_stackctl.ROOT` 访问。
_REPO_ROOT = Path(__file__).resolve().parents[3]


VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET = "test/user_acceptance/journeys/home_video_playback/video_playback_canary__user_acceptance_test.dart"
HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET = "test/user_acceptance/journeys/home_video_playback/home_video_playback__user_acceptance_test.dart"
DISCOVERY_FEED_UAT_TEST_TARGET = (
    "test/user_acceptance/service/content_service/content/feed_delivery_page/"
    "feed_load__user_acceptance_test.dart"
)
CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET = (
    "test/user_acceptance/service/content_service/content/feed_delivery_page/"
    "feed_controlled_edge_recovery__user_acceptance_test.dart"
)
APP_CORE_READBACK_UAT_TEST_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
    "app_core_readback__user_acceptance_test.dart"
)
PROFILE_JOURNEY_UAT_TEST_TARGET = (
    "test/user_acceptance/journeys/profile/"
    "profile_journey__user_acceptance_test.dart"
)
MESSAGE_HOME_UAT_TEST_TARGET = (
    "test/user_acceptance/service/chat_service/chat/chat_inbox_view/"
    "message_home_remote__user_acceptance_test.dart"
)
IOS_DIRECT_FLUTTER_RUN_UAT = (
    _REPO_ROOT / "quwoquan_app/scripts/device/verify_ios_hot_restart.py"
)
STARTUP_FIRST_FRAME_UAT = (
    _REPO_ROOT / "quwoquan_app/scripts/device/verify_startup_first_frame.py"
)
APP_CONTENT_UAT_ENVELOPE_ARGUMENTS = (
    ("releaseId", "--data-release-id"),
    ("releaseClass", "--data-release-class"),
    ("productLifecycleState", "--product-lifecycle-state"),
    ("homepageId", "--data-release-homepage-id"),
    ("homepageTitle", "--data-release-homepage-title"),
    ("articleWorkId", "--data-release-article-work-id"),
    ("articleTitle", "--data-release-article-title"),
    ("imageWorkId", "--data-release-image-work-id"),
    ("imageTitle", "--data-release-image-title"),
    ("creatorName", "--data-release-creator-name"),
    ("creatorUserHandle", "--data-release-creator-user-handle"),
    ("creatorPersonaId", "--data-release-creator-persona-id"),
    (
        "creatorAvatarAssetId",
        "--data-release-creator-avatar-asset-id",
    ),
    ("tagLabel", "--data-release-tag-label"),
    ("videoAttribution", "--data-release-video-attribution"),
)


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    app_content_uat_parser = subparsers.add_parser(
        "app-content-uat",
        help="顺序执行 Alpha/Beta/Gamma release-bound App 内容自动验收",
    )
    app_content_uat_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    app_content_uat_parser.add_argument(
        "--targets",
        default="alpha-local,beta-local,gamma-local",
    )
    app_content_uat_parser.add_argument(
        "--platform",
        choices=("ios-simulator", "android"),
        default="ios-simulator",
    )
    app_content_uat_parser.add_argument("--device-id", required=True)
    app_content_uat_parser.add_argument("--dry-run", action="store_true")


_ALPHA_APP_CONTENT_TYPED_ACTOR_TARGETS = frozenset(
    {
        DISCOVERY_FEED_UAT_TEST_TARGET,
        # 作者主页旅程含关注/取关真实往返，需要真实非生产身份。
        PROFILE_JOURNEY_UAT_TEST_TARGET,
        MESSAGE_HOME_UAT_TEST_TARGET,
        APP_CORE_READBACK_UAT_TEST_TARGET,
        HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
        VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
        CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
    }
)
_BETA_GAMMA_APP_CONTENT_TYPED_ACTOR_TARGETS = frozenset(
    {
        PROFILE_JOURNEY_UAT_TEST_TARGET,
        MESSAGE_HOME_UAT_TEST_TARGET,
        APP_CORE_READBACK_UAT_TEST_TARGET,
        HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
    }
)


def _app_content_uat_requires_typed_actor(
    environment: str,
    patrol_target: str,
) -> bool:
    import quwoquan_ops.cli.stackctl as _stackctl

    if environment == "alpha":
        return patrol_target in _stackctl._ALPHA_APP_CONTENT_TYPED_ACTOR_TARGETS
    if environment in {"beta", "gamma"}:
        return patrol_target in _stackctl._BETA_GAMMA_APP_CONTENT_TYPED_ACTOR_TARGETS
    return False


def _app_content_experience_screenshot_digests(
    runs: Sequence[Mapping[str, Any]],
    *,
    target: str,
) -> dict[str, str]:
    required = (
        "homepage-feed",
        "app-core-readback",
        "message-home",
        "profile-journey",
    )
    selected = {
        suite: next(
            item
            for item in runs
            if item.get("target") == target
            and item.get("suite") == suite
            and int(item.get("exitCode", 1)) == 0
        )
        for suite in required
    }
    expected_environment = target.removesuffix("-local")
    digests: dict[str, str] = {}
    for suite, item in selected.items():
        evidence = item.get("evidence", {})
        evidence = evidence if isinstance(evidence, Mapping) else {}
        marker = evidence.get("screenshotMarker", {})
        marker = marker if isinstance(marker, Mapping) else {}
        if (
            marker.get("environment") != expected_environment
            or marker.get("suite") != suite
            or not str(marker.get("route") or "").strip()
            or not str(marker.get("terminalKey") or "").strip()
        ):
            raise ValueError(
                f"{suite} page screenshot lacks exact route/key marker"
            )
        digests[suite] = str(evidence.get("screenshotDigest", ""))
    missing = [suite for suite, digest in digests.items() if not digest]
    if missing:
        raise ValueError(
            "required page screenshot digest is missing: " + ", ".join(missing)
        )
    if len(set(digests.values())) != len(digests):
        raise ValueError(
            "homepage/video-book/message/profile screenshots must be distinct"
        )
    return digests


def _app_content_android_launch_command(
    *,
    environment: str,
    target: str,
    device_id: str,
    attempt_path: Path,
    report_path: Path,
    output_root: Path,
    app_root: Path = _REPO_ROOT / "quwoquan_app",
    launch_control: Mapping[str, Any] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Build the only Android page-UAT prelaunch command.

    `--exit-after-launch` is guarded again by run.sh's internal actor check; the
    explicit actor environment here is evidence that stackctl, rather than an
    ordinary developer session, owns the bounded launch proof.
    """

    command = [
        "bash",
        str(app_root / "run.sh"),
        "--env",
        environment,
        "--target",
        target,
        "--mode",
        "content-live",
        "--launch-receipt",
        str(attempt_path),
        "--test-live-report",
        str(report_path),
        "--exit-after-launch",
        "-d",
        device_id,
    ]
    environment_values = {
        "QWQ_OUTPUT_ROOT": str(Path(output_root).expanduser().resolve()),
        "QWQ_CANONICAL_LAUNCH_ACTOR": "app-content-uat",
        "QWQ_APP_LAUNCH_PROVENANCE": "canonical_launcher",
    }
    if launch_control:
        environment_values["QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST"] = (
            launch_control["sourceCapsuleManifestRef"]
        )
        environment_values["QWQ_CANONICAL_LAUNCH_CONTROL"] = launch_control[
            "controlRef"
        ]
        environment_values["QWQ_CANONICAL_LAUNCH_CONTROL_DIGEST"] = (
            launch_control["controlDigest"]
        )
        environment_values["QWQ_APP_STARTUP_TERMINAL_RECEIPT"] = (
            launch_control["startupTerminalReceiptRef"]
        )
    return command, environment_values
