"""iOS 冷启动探针：simctl/devicectl 启动、日志采集与单平台判定。"""

from __future__ import annotations

import argparse
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .context import APP_DIR
from .execution import run
from .screenshot_analysis import (
    ScreenshotAnalysis,
    analyze_screenshot,
    resolve_first_visible_ms,
)
from .startup_log import (
    _safe_terminal_within_deadline,
    classify_startup_terminal,
    extract_startup_watchdog_evidence,
    parse_qwqstartup_log,
    parse_startup_sequence_log,
)


def capture_ios(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    app = Path(args.ios_app)
    if args.ios_physical and not args.skip_screenshots:
        raise ValueError("physical iOS startup probes require --skip-screenshots")
    launch_pid: int | None = None
    ios_log: str | None = None
    scene_launcher = (
        "xcrun_devicectl" if args.ios_physical else "xcrun_simctl"
    )
    if args.ios_physical:
        if args.ios_install and app.exists():
            run(
                [
                    "xcrun",
                    "devicectl",
                    "device",
                    "install",
                    "app",
                    "--device",
                    args.ios_device,
                    str(app),
                ],
                timeout=180,
            )
        start_clock = time.monotonic()
        console = subprocess.Popen(
            [
                "xcrun",
                "devicectl",
                "device",
                "process",
                "launch",
                "--device",
                args.ios_device,
                "--terminate-existing",
                "--console",
                args.ios_bundle,
            ],
            cwd=APP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            ios_log, _ = console.communicate(
                timeout=args.welcome_exit_hard_ms / 1000 + 8,
            )
        except subprocess.TimeoutExpired:
            console.terminate()
            ios_log, _ = console.communicate(timeout=10)
        (output_dir / "ios-devicectl-launch.txt").write_text(
            ios_log,
            encoding="utf-8",
        )
    else:
        if args.ios_install and app.exists():
            run(
                ["xcrun", "simctl", "uninstall", args.ios_device, args.ios_bundle],
                check=False,
                timeout=60,
            )
            run(
                ["xcrun", "simctl", "install", args.ios_device, str(app)],
                timeout=120,
            )
        run(
            ["xcrun", "simctl", "terminate", args.ios_device, args.ios_bundle],
            check=False,
            timeout=15,
        )
        start_clock = time.monotonic()
        launch = run(
            ["xcrun", "simctl", "launch", args.ios_device, args.ios_bundle],
            timeout=15,
        )
        (output_dir / "ios-simctl-launch.txt").write_text(
            launch.stdout,
            encoding="utf-8",
        )
        launch_pid_match = re.search(r":\s*(\d+)\s*$", launch.stdout)
        launch_pid = int(launch_pid_match.group(1)) if launch_pid_match else None

    analyses: list[ScreenshotAnalysis] = []
    if args.skip_screenshots and ios_log is None:
        ios_log = _wait_for_ios_startup_log(
            args.ios_device,
            launch_pid=launch_pid,
            hard_deadline_ms=args.welcome_exit_hard_ms,
            require_telemetry_ack=(
                args.require_telemetry_ack or bool(args.matrix_evidence_root)
            ),
        )
    elif not args.skip_screenshots:
        for offset in args.ios_offsets_ms:
            target = start_clock + offset / 1000
            time.sleep(max(target - time.monotonic(), 0))
            actual_offset_ms = round((time.monotonic() - start_clock) * 1000)
            screenshot = output_dir / f"ios-{offset:04d}ms.png"
            run(
                [
                    "xcrun",
                    "simctl",
                    "io",
                    args.ios_device,
                    "screenshot",
                    str(screenshot),
                ],
                timeout=15,
            )
            analyses.append(analyze_screenshot(screenshot, actual_offset_ms))

    if ios_log is None:
        ios_log = _read_ios_startup_log(args.ios_device, launch_pid=launch_pid)
    (output_dir / "ios-startup-log.txt").write_text(
        ios_log,
        encoding="utf-8",
    )
    sequence = parse_startup_sequence_log(ios_log)
    terminal_surface = classify_startup_terminal(ios_log, sequence)
    terminal_surface_classified = terminal_surface != "unresolved"
    welcome_exit_ms = sequence.get("welcomeExitMs")
    shell_first_paint_ms = sequence.get("shellFirstPaintMs")
    sequence_events_present = bool(sequence["events"])
    sequence_motion_current = sequence.get("motionSpec") == "petal_bloom"
    timings = parse_qwqstartup_log(ios_log)
    welcome_exit_within_deadline = (
        welcome_exit_ms is not None
        and welcome_exit_ms <= args.welcome_exit_hard_ms
    )
    shell_first_paint_within_target = (
        shell_first_paint_ms is not None
        and shell_first_paint_ms <= args.shell_first_paint_target_ms
    )
    overlay_removed_ms = sequence.get("overlayRemovedMs")
    overlay_removed_within_deadline = (
        overlay_removed_ms is not None
        and overlay_removed_ms <= args.welcome_exit_hard_ms
    )
    watchdog_evidence = extract_startup_watchdog_evidence(ios_log)
    watchdog_evidence["canonicalTerminal"] = terminal_surface
    scene_started = (
        bool(
            re.search(
                r"ios_(?:did_finish_launching|dart_startup_attempt|"
                r"startup_safe_terminal)",
                ios_log,
            )
        )
        if args.ios_physical
        else launch_pid is not None
    )
    attempt_id = str(watchdog_evidence.get("attemptId") or "").strip()
    launch_provenance = str(
        watchdog_evidence.get("launchProvenance") or ""
    ).strip()
    runtime_config_supply_mode = str(
        watchdog_evidence.get("runtimeConfigSupplyMode") or ""
    ).strip()
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
    first_visible = (
        (
            sequence.get("firstVisibleMs")
            or timings.get("ios_flutter_first_frame")
        )
        if args.skip_screenshots
        else resolve_first_visible_ms(
            analyses,
            args.ios_visible_by_ms,
            require_branded=True,
        )
    )
    ttid_within_budget = (
        first_visible is not None and first_visible <= args.ios_visible_by_ms
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
    blue_screen_detected = native_static_at_deadline and not terminal_surface_classified
    plain_background_detected = native_static_at_deadline and not terminal_surface_classified
    passed = (
        scene_started
        and ttid_within_budget
        and not blue_screen_detected
        and not plain_background_detected
        and terminal_surface_classified
        and (
            not args.require_startup_sequence_events
            or (
                sequence_events_present
                and sequence_motion_current
                and welcome_exit_within_deadline
                and overlay_removed_within_deadline
                and safe_terminal_within_deadline
                and attempt_id not in {"", "unknown"}
                and launch_provenance not in {"", "unknown"}
                and runtime_config_supply_mode == "external_runtime_package"
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
        "platform": "ios",
        "device": args.ios_device,
        "deviceKind": "physical" if args.ios_physical else "simulator",
        "sceneLaunchUsed": True,
        "sceneStarted": scene_started,
        "sceneLauncher": scene_launcher,
        "passed": passed,
        "visibleByMs": args.ios_visible_by_ms,
        "firstVisibleMs": first_visible,
        "ttidWithinBudget": ttid_within_budget,
        "blueScreenDetected": blue_screen_detected,
        "plainBackgroundDetected": plain_background_detected,
        "terminalSurface": terminal_surface,
        **watchdog_evidence,
        "terminalSurfaceClassified": terminal_surface_classified,
        "nativeStaticAtDeadline": native_static_at_deadline,
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
        "screenshots": [item.to_json() for item in analyses],
    }


def _read_ios_startup_log(device: str, *, launch_pid: int | None) -> str:
    predicate = (
        'eventMessage CONTAINS "startup_welcome_sequence" '
        'OR eventMessage CONTAINS "startup_probe" '
        'OR eventMessage CONTAINS "ios_flutter_first_frame" '
        'OR eventMessage CONTAINS "ios_startup_safe_terminal" '
        'OR eventMessage CONTAINS "ios_native_first_frame_timeout" '
        'OR eventMessage CONTAINS "ios_dart_startup_attempt" '
        'OR eventMessage CONTAINS "startup_telemetry_ack" '
        'OR eventMessage CONTAINS "ios_startup_bootstrap_failure"'
    )
    if launch_pid is not None:
        predicate = f"processIdentifier == {launch_pid} AND ({predicate})"
    return run(
        [
            "xcrun",
            "simctl",
            "spawn",
            device,
            "log",
            "show",
            "--last",
            "2m",
            "--style",
            "compact",
            "--predicate",
            predicate,
        ],
        check=False,
        timeout=30,
    ).stdout


def _wait_for_ios_startup_log(
    device: str,
    *,
    launch_pid: int | None,
    hard_deadline_ms: int,
    require_telemetry_ack: bool,
) -> str:
    deadline = time.monotonic() + hard_deadline_ms / 1000 + 4
    latest = ""
    while time.monotonic() < deadline:
        latest = _read_ios_startup_log(device, launch_pid=launch_pid)
        sequence = parse_startup_sequence_log(latest)
        if (
            sequence.get("welcomeExitMs") is not None
            and sequence.get("shellFirstPaintMs") is not None
            and sequence.get("overlayRemovedMs") is not None
            and (
                not require_telemetry_ack
                or "startup_telemetry_ack attemptId=" in latest
            )
        ):
            return latest
        time.sleep(0.25)
    return latest
