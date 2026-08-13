#!/usr/bin/env python3
"""Device-level startup first-frame probe for Android, iOS, and Web.

This is a user-acceptance probe, not a unit test. It catches regressions where
the app remains on a plain native transition background for too long, or where
Android native code reintroduces a mirrored welcome page before Flutter's real
WelcomeScreen can render.

实现单轨落在 ``startup_first_frame/`` 包内（context / execution /
screenshot_analysis / startup_log / android_evidence / metrics /
android_capture / ios_capture / cli）；本文件是稳定 CLI 入口，并为既有
消费者（pytest、verify_ios_hot_restart 等）re-export 包 API。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from startup_first_frame import *  # noqa: E402,F401,F403
from startup_first_frame import (  # noqa: E402,F401
    ANDROID_ANR_OBSERVATION_WINDOW_MS,
    APP_DIR,
    DEFAULT_ANDROID_ACTIVITY,
    DEFAULT_ANDROID_APK,
    DEFAULT_ANDROID_APK_DIR,
    DEFAULT_ANDROID_APK_METADATA,
    DEFAULT_ANDROID_MAIN_ACTIVITY,
    DEFAULT_ANDROID_PACKAGE,
    DEFAULT_IOS_APP,
    DEFAULT_IOS_BUNDLE,
    DEFAULT_OUTPUT_DIR,
    FORBIDDEN_NATIVE_WELCOME_LOG_PATTERNS,
    ROOT,
    ScreenshotAnalysis,
    analyze_existing_screenshots,
    analyze_screenshot,
    android_device_kind,
    android_fresh_startup_log_evidence,
    android_gate_main_order_evidence,
    android_gate_main_order_observed,
    android_log_after_baseline,
    android_package_anr_evidence,
    build_arg_parser,
    build_platform_samples,
    build_provenance,
    capture_android,
    capture_ios,
    classify_startup_terminal,
    detect_native_static_petal_mismatch,
    detect_prolonged_system_blue,
    detect_repeated_splash,
    extract_dart_startup_attempts,
    extract_startup_watchdog_evidence,
    first_branded_offset_ms,
    main,
    native_launch_visual_provenance,
    normalize_android_component,
    parse_android_launcher_resolution,
    parse_android_task_snapshot,
    parse_offsets,
    parse_qwqstartup_log,
    parse_startup_sequence_log,
    percentile,
    read_android_device_abi,
    resolve_android_apk,
    resolve_android_first_visible_ms,
    resolve_android_launch_resource_profile,
    resolve_first_visible_ms,
    run,
    sha256_file,
    summarize_metric_runs,
    summarize_startup_samples,
)

if __name__ == "__main__":
    raise SystemExit(main())
