"""Android 冷启动探针：安装、启动、截图/日志采集与单平台判定。"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Any

from .android_evidence import (
    android_device_kind,
    android_fresh_startup_log_evidence,
    native_launch_visual_provenance,
    parse_android_launcher_resolution,
    parse_android_task_snapshot,
    resolve_android_apk,
    resolve_android_launch_resource_profile,
)
from .context import (
    ANDROID_ANR_OBSERVATION_WINDOW_MS,
    FORBIDDEN_NATIVE_WELCOME_LOG_PATTERNS,
)
from .execution import run, sha256_file
from .screenshot_analysis import (
    ScreenshotAnalysis,
    analyze_screenshot,
    detect_native_static_petal_mismatch,
    detect_prolonged_system_blue,
    detect_repeated_splash,
    resolve_android_first_visible_ms,
)
from .startup_log import (
    _safe_terminal_within_deadline,
    classify_startup_terminal,
    extract_startup_watchdog_evidence,
    parse_qwqstartup_log,
    parse_startup_sequence_log,
)


def capture_android(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    # 多轮冷启动期间，外部清理器或 APK 安装脚本不应让后续 run 丢失证据目录。
    output_dir.mkdir(parents=True, exist_ok=True)
    apk = Path(args.android_apk)
    if args.android_install:
        apk = resolve_android_apk(apk, args.android_device)
        install = run(
            ["adb", "-s", args.android_device, "install", "-r", "-d", str(apk)],
            check=False,
            timeout=120,
        )
        if install.returncode != 0:
            run(
                ["adb", "-s", args.android_device, "uninstall", args.android_package],
                check=False,
                timeout=60,
            )
            reinstall = run(
                ["adb", "-s", args.android_device, "install", "-r", str(apk)],
                check=False,
                timeout=120,
            )
            install_output = f"{install.stdout}\n--- reinstall ---\n{reinstall.stdout}"
            if reinstall.returncode != 0:
                (output_dir / "android-install.txt").write_text(
                    install_output,
                    encoding="utf-8",
                )
                reinstall.check_returncode()
        else:
            install_output = install.stdout
        (output_dir / "android-install.txt").write_text(install_output, encoding="utf-8")
    run(["adb", "-s", args.android_device, "logcat", "-c"])
    run(["adb", "-s", args.android_device, "shell", "am", "force-stop", args.android_package])
    launcher_query = run(
        [
            "adb",
            "-s",
            args.android_device,
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            args.android_package,
        ],
        check=False,
        timeout=15,
    )
    (output_dir / "android-launcher-resolution.txt").write_text(
        launcher_query.stdout,
        encoding="utf-8",
    )
    launcher_resolution = parse_android_launcher_resolution(
        launcher_query.stdout,
        package=args.android_package,
        expected_activity=args.android_activity,
    )
    log_baseline = run(
        ["adb", "-s", args.android_device, "logcat", "-d"],
        check=False,
        timeout=15,
    ).stdout
    (output_dir / "android-logcat-baseline.txt").write_text(
        log_baseline,
        encoding="utf-8",
    )
    start_command = [
        "adb",
        "-s",
        args.android_device,
        "shell",
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.MAIN",
        "-c",
        "android.intent.category.LAUNCHER",
    ]
    resolved_launcher = str(launcher_resolution["resolvedActivity"])
    if resolved_launcher:
        # Android 12's `am start -p` can fail to resolve a package-scoped
        # launcher even when PackageManager has already selected the activity.
        # Bind the previously verified resolution while preserving the real
        # MAIN/LAUNCHER intent semantics.
        start_command.extend(["-n", resolved_launcher])
    else:
        start_command.extend(["-p", args.android_package])
    start_clock = time.monotonic()
    start = run(
        start_command,
        check=False,
        timeout=15,
    )
    (output_dir / "android-am-start.txt").write_text(start.stdout, encoding="utf-8")
    launcher_started = (
        start.returncode == 0
        and "unable to resolve Intent" not in start.stdout
        and "Error:" not in start.stdout
    )

    analyses: list[ScreenshotAnalysis] = []
    log: str | None = None
    if args.skip_screenshots:
        log = _wait_for_android_startup_log(
            args.android_device,
            hard_deadline_ms=args.welcome_exit_hard_ms,
            require_telemetry_ack=(
                args.require_telemetry_ack or bool(args.matrix_evidence_root)
            ),
            observation_not_before=(
                start_clock + ANDROID_ANR_OBSERVATION_WINDOW_MS / 1000
            ),
        )
    else:
        for offset in args.android_offsets_ms:
            target = start_clock + offset / 1000
            time.sleep(max(target - time.monotonic(), 0))
            actual_offset_ms = round((time.monotonic() - start_clock) * 1000)
            screenshot = output_dir / f"android-{offset:04d}ms.png"
            with screenshot.open("wb") as handle:
                run(
                    ["adb", "-s", args.android_device, "exec-out", "screencap", "-p"],
                    stdout=handle,
                    timeout=15,
                )
            analyses.append(analyze_screenshot(screenshot, actual_offset_ms))

    if log is None:
        observation_not_before = (
            start_clock + ANDROID_ANR_OBSERVATION_WINDOW_MS / 1000
        )
        time.sleep(max(observation_not_before - time.monotonic(), 0))
        log = run(
            ["adb", "-s", args.android_device, "logcat", "-d"],
            timeout=15,
        ).stdout
    (output_dir / "android-logcat.txt").write_text(log, encoding="utf-8")
    task_dump = run(
        [
            "adb",
            "-s",
            args.android_device,
            "shell",
            "dumpsys",
            "activity",
            "activities",
        ],
        check=False,
        timeout=15,
    ).stdout
    (output_dir / "android-task-stack.txt").write_text(
        task_dump,
        encoding="utf-8",
    )
    task_snapshot = parse_android_task_snapshot(
        task_dump,
        package=args.android_package,
        main_activity=args.android_main_activity,
    )
    fresh_log_evidence = android_fresh_startup_log_evidence(
        baseline=log_baseline,
        current=log,
        package=args.android_package,
    )
    gate_main_order = bool(fresh_log_evidence["gateMainOrderObserved"])
    launch_resource_profile = resolve_android_launch_resource_profile(
        args.android_device
    )
    launch_visual = native_launch_visual_provenance(launch_resource_profile)
    timings = parse_qwqstartup_log(log)
    sequence = parse_startup_sequence_log(log)
    terminal_surface = classify_startup_terminal(log, sequence)
    terminal_surface_classified = terminal_surface != "unresolved"
    native_welcome_hits = [
        pattern
        for pattern in FORBIDDEN_NATIVE_WELCOME_LOG_PATTERNS
        if pattern in log
    ]
    native_welcome_detected = bool(native_welcome_hits)
    system_splash_icon_detected = any(
        item.system_splash_icon for item in analyses
    )
    first_visible = (
        (
            sequence.get("firstVisibleMs")
            or timings.get("android_flutter_first_frame")
        )
        if args.skip_screenshots
        else resolve_android_first_visible_ms(
            analyses,
            renderer_first_frame_ms=timings.get("android_flutter_first_frame"),
            require_branded=args.require_branded_visible,
        )
    )
    flutter_ui_ms = timings.get("android_flutter_ui_displayed")
    activity_displayed_ms = timings.get("android_activity_displayed_ms")
    activity_on_create_ms = timings.get("android_activity_on_create")
    engine_configured_ms = timings.get("android_flutter_engine_configured")
    ttid_within_budget = (
        first_visible is not None and first_visible <= args.android_visible_by_ms
    )
    native_static_at_deadline = any(
        item.offset_ms is not None
        and item.offset_ms >= args.welcome_exit_hard_ms
        and (
            item.plain_background
            or (
                item.blue_background
                and not item.branded_or_content_visible
            )
        )
        for item in analyses
    )
    prolonged_system_blue_detected = (
        False
        if args.skip_screenshots
        else detect_prolonged_system_blue(
            analyses,
            transition_budget_ms=args.android_blue_transition_budget_ms,
        )
    )
    repeated_splash_detected = detect_repeated_splash(analyses, log)
    flutter_ui_within_budget = (
        flutter_ui_ms is None or flutter_ui_ms <= args.android_flutter_ui_max_ms
    )
    welcome_exit_ms = sequence.get("welcomeExitMs")
    shell_first_paint_ms = sequence.get("shellFirstPaintMs")
    overlay_removed_ms = sequence.get("overlayRemovedMs")
    sequence_events_present = bool(sequence["events"])
    sequence_motion_current = sequence.get("motionSpec") == "petal_bloom"
    welcome_exit_within_deadline = (
        welcome_exit_ms is not None
        and welcome_exit_ms <= args.welcome_exit_hard_ms
    )
    native_static_petal_mismatch = (
        False
        if args.skip_screenshots
        else detect_native_static_petal_mismatch(
            analyses,
            compare_after_ms=max(
                args.android_blue_transition_budget_ms,
                args.android_visible_by_ms,
            ),
            safe_terminal_reached=(
                terminal_surface_classified and welcome_exit_within_deadline
            ),
        )
    )
    blue_screen_detected = (
        (native_static_at_deadline and not terminal_surface_classified)
        or prolonged_system_blue_detected
    )
    shell_first_paint_within_target = (
        shell_first_paint_ms is not None
        and shell_first_paint_ms <= args.shell_first_paint_target_ms
    )
    overlay_removed_within_deadline = (
        overlay_removed_ms is not None
        and overlay_removed_ms <= args.welcome_exit_hard_ms
    )
    watchdog_evidence = extract_startup_watchdog_evidence(log)
    watchdog_evidence["canonicalTerminal"] = terminal_surface
    attempt_id = str(watchdog_evidence.get("attemptId") or "").strip()
    launch_mode = str(watchdog_evidence.get("launchMode") or "").strip()
    runtime_configuration_complete = (
        watchdog_evidence.get("runtimeConfigurationState") == "complete"
        and not watchdog_evidence.get("missingDefineKeys")
    )
    effective_manifest_bound = (
        re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(
                watchdog_evidence.get("effectiveLaunchManifestDigest") or ""
            ),
        )
        is not None
    )
    safe_terminal_within_deadline = (
        _safe_terminal_within_deadline(
            watchdog_evidence,
            args.welcome_exit_hard_ms,
        )
    )
    plain_background_detected = native_static_at_deadline and not terminal_surface_classified
    passed = (
        not native_welcome_detected
        and not blue_screen_detected
        and not plain_background_detected
        and not prolonged_system_blue_detected
        and not repeated_splash_detected
        and not native_static_petal_mismatch
        and terminal_surface_classified
        and terminal_surface != "nativeRecovery"
        and launcher_started
        and launcher_query.returncode == 0
        and launcher_resolution["matchesExpectedGate"]
        and fresh_log_evidence["passed"]
        and gate_main_order
        and task_snapshot["singleMainTask"]
        and launch_visual["contractVerified"]
        and bool(launch_visual["sourceDigest"])
        and ttid_within_budget
        and (first_visible is not None or not args.require_branded_visible)
        and flutter_ui_within_budget
        and (
            not args.require_startup_sequence_events
            or (
                sequence_events_present
                and sequence_motion_current
                and welcome_exit_within_deadline
                and overlay_removed_within_deadline
                and safe_terminal_within_deadline
                and attempt_id not in {"", "unknown"}
                and launch_mode not in {"", "unknown"}
                and runtime_configuration_complete
                and effective_manifest_bound
            )
        )
        and (
            not args.enforce_shell_target
            or shell_first_paint_within_target
        )
        and (
            not args.require_no_native_recovery
            or terminal_surface != "nativeRecovery"
        )
        and (
            not args.require_telemetry_ack
            and not args.matrix_evidence_root
            or watchdog_evidence.get("telemetryAcknowledged") is True
        )
    )
    return {
        "platform": "android",
        "device": args.android_device,
        "deviceKind": android_device_kind(args.android_device),
        "apk": str(apk) if args.android_install else None,
        "passed": passed,
        "launcherIntentUsed": True,
        "launcherStarted": launcher_started,
        "launcherResolution": launcher_resolution,
        "androidLogBaselineApplied": fresh_log_evidence["baselineApplied"],
        "androidLogBaselineLineCount": fresh_log_evidence["baselineLineCount"],
        "androidObservationLineCount": fresh_log_evidence["observationLineCount"],
        "androidAnrObservationWindowMs": ANDROID_ANR_OBSERVATION_WINDOW_MS,
        "startupAttemptLogUnique": fresh_log_evidence["startupAttemptLogUnique"],
        "gateEventCounts": fresh_log_evidence["gateEventCounts"],
        "gateMainOrderObserved": gate_main_order,
        "androidAnrDetected": fresh_log_evidence["androidAnrDetected"],
        "androidAnrSignals": fresh_log_evidence["androidAnrSignals"],
        "androidAnrMatchedLineCount": fresh_log_evidence[
            "androidAnrMatchedLineCount"
        ],
        "taskSnapshot": task_snapshot,
        "launchVisual": launch_visual,
        "visibleByMs": args.android_visible_by_ms,
        "firstVisibleMs": first_visible,
        "ttidWithinBudget": ttid_within_budget,
        "activityDisplayedMs": activity_displayed_ms,
        "activityOnCreateMs": activity_on_create_ms,
        "flutterEngineConfiguredMs": engine_configured_ms,
        "nativeWelcomeDetected": native_welcome_detected,
        "nativeWelcomeHits": native_welcome_hits,
        "systemSplashIconDetected": system_splash_icon_detected,
        "blueScreenDetected": blue_screen_detected,
        "prolongedSystemBlueDetected": prolonged_system_blue_detected,
        "repeatedSplashDetected": repeated_splash_detected,
        "nativeStaticPetalMismatch": native_static_petal_mismatch,
        "blueTransitionBudgetMs": args.android_blue_transition_budget_ms,
        "plainBackgroundDetected": plain_background_detected,
        "terminalSurface": terminal_surface,
        **watchdog_evidence,
        "terminalSurfaceClassified": terminal_surface_classified,
        "nativeStaticAtDeadline": native_static_at_deadline,
        "flutterUiDisplayedMaxMs": args.android_flutter_ui_max_ms,
        "flutterUiDisplayedWithinBudget": flutter_ui_within_budget,
        "startupSequenceEventsPresent": sequence_events_present,
        "startupSequenceMotionCurrent": sequence_motion_current,
        "welcomeExitHardMs": args.welcome_exit_hard_ms,
        "welcomeExitWithinDeadline": welcome_exit_within_deadline,
        "overlayRemovedWithinDeadline": overlay_removed_within_deadline,
        "safeTerminalWithinDeadline": safe_terminal_within_deadline,
        "shellFirstPaintTargetMs": args.shell_first_paint_target_ms,
        "shellFirstPaintWithinTarget": shell_first_paint_within_target,
        "startupSequence": sequence,
        "timings": timings,
        "apkSha256": sha256_file(apk) if args.android_install and apk.is_file() else None,
        "screenshots": [item.to_json() for item in analyses],
    }


def _wait_for_android_startup_log(
    device: str,
    *,
    hard_deadline_ms: int,
    require_telemetry_ack: bool,
    observation_not_before: float | None = None,
) -> str:
    host_deadline = time.monotonic() + hard_deadline_ms / 1000 + 12
    process_seen_at: float | None = None
    latest = ""
    while time.monotonic() < host_deadline:
        latest = run(
            ["adb", "-s", device, "logcat", "-d"],
            check=False,
            timeout=15,
        ).stdout
        if process_seen_at is None and "android_activity_on_create" in latest:
            process_seen_at = time.monotonic()
        sequence = parse_startup_sequence_log(latest)
        if (
            sequence.get("welcomeExitMs") is not None
            and sequence.get("shellFirstPaintMs") is not None
            and sequence.get("overlayRemovedMs") is not None
            and (
                observation_not_before is None
                or time.monotonic() >= observation_not_before
            )
            and (
                not require_telemetry_ack
                or "startup_telemetry_ack attemptId=" in latest
            )
        ):
            return latest
        if (
            process_seen_at is not None
            and time.monotonic() - process_seen_at
            > hard_deadline_ms / 1000 + 4
        ):
            return latest
        time.sleep(0.25)
    return latest
