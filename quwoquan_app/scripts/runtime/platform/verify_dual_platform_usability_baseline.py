#!/usr/bin/env python3
"""Static component-readiness gate for dual-platform runtime wiring.

This gate checks only repository-controlled wiring.  It never claims runtime
or commercial readiness; those facts belong to the canonical startup
environment CaseResult report.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT


ROOT = REPO_ROOT
APP = ROOT / "quwoquan_app"
OPS = ROOT / "quwoquan_ops"
WORKFLOWS = ROOT / ".github" / "workflows"

ERROR_STATE = APP / "lib/design_system/feedback/error_states/app_error_states.dart"
ANDROID_GRADLE = APP / "android/app/build.gradle.kts"
IOS_WRAPPER = APP / "scripts/ios/build_xcode_backend.sh"
RUN_SH = APP / "run.sh"
CORE_READBACK_PATROL = (
    APP
    / "test/user_acceptance/journeys/app_startup"
    / "app_core_readback__user_acceptance_test.dart"
)
BASIC_READBACK_PATROL = (
    APP
    / "test/user_acceptance/journeys/app_startup"
    / "basic_viability__user_acceptance_test.dart"
)
CORE_READBACK_SUPPORT = (
    APP / "test/support/runtime/patrol/patrol_core_readback_support.dart"
)
SMOKE = OPS / "cli/smoke/run_environment_patrol_smoke.py"
VALIDATION = OPS / "environments/gamma/validation_suites.json"
DEVICE_MATRIX = WORKFLOWS / "app-env-device-matrix-self-hosted.yml"
GAMMA_RELEASE_CONSUMER = APP / "scripts/gamma/run_local_gamma_release_consumer_api.py"

def fail(failures: list[str], message: str) -> None:
    failures.append(message)


def main() -> int:
    failures: list[str] = []

    for path in (
        ERROR_STATE,
        ANDROID_GRADLE,
        IOS_WRAPPER,
        RUN_SH,
        CORE_READBACK_PATROL,
        BASIC_READBACK_PATROL,
        CORE_READBACK_SUPPORT,
        SMOKE,
        VALIDATION,
        DEVICE_MATRIX,
        GAMMA_RELEASE_CONSUMER,
    ):
        if not path.is_file():
            fail(
                failures,
                f"missing required component artifact: {path.relative_to(ROOT)}",
            )

    if failures:
        _emit(failures)
        return 1

    error_text = ERROR_STATE.read_text(encoding="utf-8")
    for token in (
        "UiErrorVisualKind",
        "app-page-error-diagnostics",
        "app-page-error-illustration",
    ):
        if token in error_text:
            fail(
                failures,
                f"{ERROR_STATE.relative_to(ROOT)}: forbidden user-visible error surface token {token}",
            )
    page_body = ""
    match = re.search(
        r"class _ErrorEmptyPageBody[\s\S]*?(?=class _ErrorSoftCardBody|\Z)",
        error_text,
    )
    if match is None:
        fail(
            failures,
            f"{ERROR_STATE.relative_to(ROOT)}: missing _ErrorEmptyPageBody page contract",
        )
    else:
        page_body = match.group(0)
        if "Icon(" in page_body or "CupertinoIcons." in page_body:
            fail(
                failures,
                f"{ERROR_STATE.relative_to(ROOT)}: page error body must not show icons",
            )
        if re.search(
            r"Text\([^\)]*(sourceOperationId|sourceCode|requestId|traceId|sourceRouteId)",
            page_body,
        ):
            fail(
                failures,
                f"{ERROR_STATE.relative_to(ROOT)}: technical fields must not be rendered as Text",
            )
        if "liveRegion: true" not in page_body:
            fail(
                failures,
                f"{ERROR_STATE.relative_to(ROOT)}: page error state must expose accessibility live region",
            )

    gradle = ANDROID_GRADLE.read_text(encoding="utf-8")
    if "verifyAndroidLocalLauncherContract" not in gradle:
        fail(
            failures,
            f"{ANDROID_GRADLE.relative_to(ROOT)}: missing verifyAndroidLocalLauncherContract",
        )
    if "startLocalStackIfNeeded" in gradle or "autoStartStack" in gradle:
        fail(
            failures,
            f"{ANDROID_GRADLE.relative_to(ROOT)}: must not auto-start local stack",
        )
    if "ProcessBuilder" in gradle and "reverse" in gradle and "verifyAndroidLocalLauncherContract" not in gradle:
        fail(
            failures,
            f"{ANDROID_GRADLE.relative_to(ROOT)}: Gradle must not establish adb reverse itself",
        )

    wrapper = IOS_WRAPPER.read_text(encoding="utf-8")
    if "build_prepare_dart_defines.sh" not in wrapper:
        fail(
            failures,
            f"{IOS_WRAPPER.relative_to(ROOT)}: must invoke build_prepare_dart_defines.sh",
        )
    if "set -euo pipefail" not in wrapper and "set -e" not in wrapper:
        fail(failures, f"{IOS_WRAPPER.relative_to(ROOT)}: must propagate non-zero exit codes")

    run_sh = RUN_SH.read_text(encoding="utf-8")
    for required in (
        "ANDROID_SERIAL",
        "enable_android_adb_reverse",
        'export QWQ_ENVIRONMENT="${REQUESTED_ENVIRONMENT:-alpha}"',
        'export QWQ_APP_RUNTIME_ENV="$QWQ_ENVIRONMENT"',
        'export QWQ_LAUNCH_TARGET="${REQUESTED_TARGET:-${QWQ_APP_RUNTIME_ENV}-local}"',
        'app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"',
        '--target "$QWQ_LAUNCH_TARGET" --runtime-mode test_live',
        '--env "$QWQ_APP_RUNTIME_ENV"',
        '--target "$QWQ_LAUNCH_TARGET"',
    ):
        if required not in run_sh:
            fail(failures, f"{RUN_SH.relative_to(ROOT)}: missing launcher requirement {required}")

    patrol = CORE_READBACK_PATROL.read_text(encoding="utf-8")
    if "skip: !kRunPatrolAcceptance" not in patrol:
        fail(
            failures,
            (
                f"{CORE_READBACK_PATROL.relative_to(ROOT)}: required readback "
                "must use only the canonical Patrol compile guard"
            ),
        )
    for needle in (
        "environment_app_core_readback",
        "home-feed-card-0",
        "video-player-ready",
        "DATA_RELEASE_CREATOR_USER_HANDLE",
        "DATA_RELEASE_CREATOR_PERSONA_ID",
        "DATA_RELEASE_CREATOR_AVATAR_ASSET_ID",
        "profile-header-avatar-image",
        "startupRecoveryTitle",
    ):
        if needle not in patrol:
            fail(
                failures,
                f"{CORE_READBACK_PATROL.relative_to(ROOT)}: missing journey assertion {needle}",
            )

    basic_patrol = BASIC_READBACK_PATROL.read_text(encoding="utf-8")
    if "skip: !kRunPatrolAcceptance" not in basic_patrol:
        fail(
            failures,
            (
                f"{BASIC_READBACK_PATROL.relative_to(ROOT)}: required readback "
                "must use only the canonical Patrol compile guard"
            ),
        )
    for needle in (
        "environment_post_auth_core_social_readback",
        "provisionPatrolCoreChatConversation",
        "chat-inbox-row-",
        "AppRoutePaths.profile",
        "profile-header-avatar-image",
        "startupRecoveryTitle",
    ):
        if needle not in basic_patrol:
            fail(
                failures,
                f"{BASIC_READBACK_PATROL.relative_to(ROOT)}: missing journey assertion {needle}",
            )

    support = CORE_READBACK_SUPPORT.read_text(encoding="utf-8")
    for needle in (
        "createConversation",
        "sendMessage",
        "ChatSendMessageCommand",
        "messageHomeRowsStateProvider",
    ):
        if needle not in support:
            fail(
                failures,
                f"{CORE_READBACK_SUPPORT.relative_to(ROOT)}: missing Remote provision step {needle}",
            )

    smoke = SMOKE.read_text(encoding="utf-8")
    if "CORE_READBACK_TARGET" not in smoke or "BASIC_VIABILITY_TARGET" not in smoke:
        fail(
            failures,
            (
                f"{SMOKE.relative_to(ROOT)}: must declare both content and "
                "content-free core readback targets"
            ),
        )
    if '"local-gamma"' not in smoke or "runtime_anonymous_session" not in smoke:
        fail(
            failures,
            f"{SMOKE.relative_to(ROOT)}: runtime anonymous session must support local-gamma",
        )

    suites = json.loads(VALIDATION.read_text(encoding="utf-8"))
    pr_light = suites["profiles"]["pr_light"]["deviceMatrix"]
    matrix_kinds = set(pr_light.get("matrixKinds") or [])
    if matrix_kinds != {"assistant", "environment-smoke"}:
        fail(
            failures,
            (
                f"{VALIDATION.relative_to(ROOT)}: pr_light must keep the "
                "content-free assistant and environment-smoke device baseline"
            ),
        )
    if pr_light.get("requireAllPlatforms") is not True:
        fail(
            failures,
            (
                f"{VALIDATION.relative_to(ROOT)}: pr_light must require both "
                "Android and iOS platform evidence"
            ),
        )
    for profile_name in ("manual_full", "nightly_full", "release_candidate"):
        full_matrix_kinds = set(
            suites["profiles"][profile_name]["deviceMatrix"].get("matrixKinds") or []
        )
        if "app-core-readback" not in full_matrix_kinds:
            fail(
                failures,
                (
                    f"{VALIDATION.relative_to(ROOT)}: {profile_name} must retain "
                    "release-bound app-core-readback"
                ),
            )

    workflow = DEVICE_MATRIX.read_text(encoding="utf-8")
    if "app-core-readback" not in workflow:
        fail(
            failures,
            f"{DEVICE_MATRIX.relative_to(ROOT)}: must wire app-core-readback matrix kind",
        )
    if 'smoke_env_alias="gamma-local"' in workflow:
        fail(
            failures,
            f"{DEVICE_MATRIX.relative_to(ROOT)}: gamma Patrol must use local-gamma session alias",
        )

    release_consumer = GAMMA_RELEASE_CONSUMER.read_text(encoding="utf-8")
    for required in (
        "load_release_content_identity",
        "resolve_readiness_path",
        'expected_environment="gamma"',
        'parser.add_argument(\n        "--release-readiness"',
        '"mutationPolicy": "read_only"',
        '"ship"',
        '"verify"',
    ):
        if required not in release_consumer:
            fail(
                failures,
                f"{GAMMA_RELEASE_CONSUMER.relative_to(ROOT)}: missing release-bound read-only contract {required}",
            )
    for forbidden_argument in (
        'parser.add_argument("--release-id"',
        'parser.add_argument("--import-run-id"',
        'parser.add_argument("--verification-run-id"',
    ):
        if forbidden_argument in release_consumer:
            fail(
                failures,
                (
                    f"{GAMMA_RELEASE_CONSUMER.relative_to(ROOT)}: release identity must come from "
                    f"canonical readiness receipt, found {forbidden_argument}"
                ),
            )
    for forbidden in ("seed_content", "seed_entity", "seed-only", "media.quwoquan.invalid"):
        if forbidden in release_consumer:
            fail(
                failures,
                f"{GAMMA_RELEASE_CONSUMER.relative_to(ROOT)}: forbidden environment mutation token {forbidden}",
            )

    _emit(failures)
    return 1 if failures else 0


def _emit(failures: list[str]) -> None:
    if failures:
        print("[verify_dual_platform_component_readiness] FAILED")
        for item in failures:
            print(f"- {item}")
        return
    print("[verify_dual_platform_component_readiness] COMPONENT_READY")
    print("Runtime readiness is decided only by the startup environment CaseResult report.")


if __name__ == "__main__":
    sys.exit(main())
