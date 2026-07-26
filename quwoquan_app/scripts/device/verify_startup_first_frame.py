#!/usr/bin/env python3
"""Device-level startup first-frame probe for Android, iOS, and Web.

This is a user-acceptance probe, not a unit test. It catches regressions where
the app remains on a plain native transition background for too long, or where
Android native code reintroduces a mirrored welcome page before Flutter's real
WelcomeScreen can render.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageStat


APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
DEFAULT_ANDROID_PACKAGE = "com.quwoquan.quwoquan_app"
DEFAULT_ANDROID_ACTIVITY = "com.quwoquan.quwoquan_app/.MainActivity"
DEFAULT_ANDROID_APK_DIR = APP_DIR / "build/app/outputs/flutter-apk"
DEFAULT_ANDROID_APK = DEFAULT_ANDROID_APK_DIR / "app-debug.apk"
DEFAULT_ANDROID_APK_METADATA = APP_DIR / "build/app/outputs/apk/debug/output-metadata.json"
DEFAULT_IOS_BUNDLE = "com.example.quwoquanApp"
DEFAULT_IOS_APP = APP_DIR / "build/ios/iphonesimulator/Runner.app"
DEFAULT_OUTPUT_DIR = (
    Path(os.environ.get("QWQ_OUTPUT_ROOT", ROOT / ".qwq_output"))
    / "env"
    / "alpha"
    / "runs"
    / "startup_first_frame"
    / "probe"
)
FORBIDDEN_NATIVE_WELCOME_LOG_PATTERNS = (
    "android_startup_welcome_first_draw",
    "android_startup_activity_handoff",
    "android_native_welcome_first_draw",
    "android_native_welcome_host_installed",
    "android_flutter_welcome_ready",
    "android_native_welcome_completion_received",
    "android_flutter_welcome_ready_timeout",
)


@dataclass(frozen=True)
class ScreenshotAnalysis:
    path: str
    offset_ms: int | None
    foreground_ratio: float
    stddev_avg: float
    median_rgb: tuple[int, int, int]
    plain_background: bool
    blue_background: bool
    branded_or_content_visible: bool

    @property
    def brand_transition_visible(self) -> bool:
        return self.blue_background or self.branded_or_content_visible

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "offsetMs": self.offset_ms,
            "foregroundRatio": round(self.foreground_ratio, 5),
            "stddevAvg": round(self.stddev_avg, 3),
            "medianRgb": list(self.median_rgb),
            "plainBackground": self.plain_background,
            "blueBackground": self.blue_background,
            "brandedOrContentVisible": self.branded_or_content_visible,
            "brandTransitionVisible": self.brand_transition_visible,
        }


def run(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: float | None = None,
    stdout: Any = subprocess.PIPE,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=stdout,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def read_android_device_abi(device: str) -> str:
    abi = run(
        ["adb", "-s", device, "shell", "getprop", "ro.product.cpu.abi"],
        timeout=15,
    ).stdout.strip()
    if not abi:
        raise RuntimeError(f"Unable to resolve Android ABI for device {device}")
    return abi


def android_device_kind(device: str) -> str:
    qemu = run(
        ["adb", "-s", device, "shell", "getprop", "ro.kernel.qemu"],
        check=False,
        timeout=15,
    ).stdout.strip()
    return "simulator" if qemu == "1" else "true_device"


def resolve_android_apk(apk: Path, device: str) -> Path:
    if apk.exists():
        return apk

    default_apk_requested = (
        apk.resolve(strict=False) == DEFAULT_ANDROID_APK.resolve(strict=False)
    )
    if default_apk_requested:
        abi = read_android_device_abi(device)
        if DEFAULT_ANDROID_APK_METADATA.exists():
            metadata = json.loads(
                DEFAULT_ANDROID_APK_METADATA.read_text(encoding="utf-8")
            )
            for element in metadata.get("elements", []):
                filters = {
                    item.get("filterType"): item.get("value")
                    for item in element.get("filters", [])
                }
                if filters.get("ABI") != abi:
                    continue
                output_file = element.get("outputFile")
                if not output_file:
                    continue
                for base_dir in (
                    DEFAULT_ANDROID_APK_DIR,
                    DEFAULT_ANDROID_APK_METADATA.parent,
                ):
                    candidate = base_dir / output_file
                    if candidate.exists():
                        return candidate

        candidate = DEFAULT_ANDROID_APK_DIR / f"app-{abi}-debug.apk"
        if candidate.exists():
            return candidate

        available = ", ".join(
            path.name for path in sorted(DEFAULT_ANDROID_APK_DIR.glob("app-*-debug.apk"))
        )
        raise FileNotFoundError(
            "Android install requested but default app-debug.apk was not found; "
            f"device ABI is {abi}, available split APKs: {available or 'none'}"
        )

    raise FileNotFoundError(f"Android install requested but APK was not found: {apk}")


def analyze_screenshot(path: Path, offset_ms: int | None = None) -> ScreenshotAnalysis:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    crop = image.crop(
        (
            round(width * 0.14),
            round(height * 0.14),
            round(width * 0.86),
            round(height * 0.86),
        )
    )
    get_pixels = getattr(crop, "get_flattened_data", None)
    pixels = list(get_pixels() if get_pixels is not None else crop.getdata())
    median_rgb = tuple(int(median(channel)) for channel in zip(*pixels))
    foreground = 0
    for r, g, b in pixels:
        distance = (
            (r - median_rgb[0]) ** 2
            + (g - median_rgb[1]) ** 2
            + (b - median_rgb[2]) ** 2
        ) ** 0.5
        if distance > 34:
            foreground += 1
    foreground_ratio = foreground / max(len(pixels), 1)
    stddev = ImageStat.Stat(crop).stddev
    stddev_avg = sum(stddev) / max(len(stddev), 1)
    near_white_background = min(median_rgb) >= 250
    branded_or_content_visible = (
        foreground_ratio >= 0.18
        or (
            stddev_avg >= 14.0
            and foreground_ratio >= 0.08
            and not near_white_background
        )
    )
    blue_background = (
        not branded_or_content_visible
        and median_rgb[0] <= 40
        and 90 <= median_rgb[1] <= 170
        and median_rgb[2] >= 210
    )
    brand_transition_visible = blue_background or branded_or_content_visible
    return ScreenshotAnalysis(
        path=str(path),
        offset_ms=offset_ms,
        foreground_ratio=foreground_ratio,
        stddev_avg=stddev_avg,
        median_rgb=median_rgb,
        plain_background=not brand_transition_visible,
        blue_background=blue_background,
        branded_or_content_visible=branded_or_content_visible,
    )


def parse_qwqstartup_log(raw: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for key in (
        "android_activity_on_create",
        "android_flutter_engine_configured",
        "android_flutter_first_frame",
        "android_flutter_ui_displayed",
        "ios_flutter_first_frame",
    ):
        match = re.search(rf"{re.escape(key)} elapsedMs=(\d+)", raw)
        if match:
            values[key] = int(match.group(1))
    displayed_match = re.search(
        r"Displayed com\.quwoquan\.quwoquan_app/\.MainActivity for user \d+: \+((?:(\d+)s)?(\d+)ms)",
        raw,
    )
    if displayed_match:
        seconds = int(displayed_match.group(2) or "0")
        milliseconds = int(displayed_match.group(3))
        values["android_activity_displayed_ms"] = seconds * 1000 + milliseconds
    return values


def parse_startup_sequence_log(raw: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        json_marker = "startup_event "
        if json_marker in line:
            payload = line.split(json_marker, 1)[1].strip()
            try:
                decoded = json.loads(payload)
            except json.JSONDecodeError:
                decoded = None
            if (
                isinstance(decoded, dict)
                and decoded.get("eventName") == "startup_welcome_sequence"
            ):
                events.append(decoded)
            continue
        marker = next(
            (
                candidate
                for candidate in ("startup_welcome_sequence ", "startup_probe ")
                if candidate in line
            ),
            None,
        )
        if marker is None:
            continue
        payload = line.split(marker, 1)[1]
        event: dict[str, Any] = {}
        for key, value in re.findall(r"([A-Za-z][A-Za-z0-9]*)=([^\s]+)", payload):
            if re.fullmatch(r"-?\d+", value):
                event[key] = int(value)
            elif value in ("true", "false"):
                event[key] = value == "true"
            else:
                event[key] = value
        if event:
            events.append(event)

    finished = next(
        (event for event in reversed(events) if event.get("phase") == "finished"),
        None,
    )
    shell = next(
        (
            event
            for event in reversed(events)
            if event.get("phase") == "main_shell_first_paint"
        ),
        None,
    )
    overlay_removed = next(
        (
            event
            for event in reversed(events)
            if event.get("phase") == "welcome_overlay_removed"
        ),
        None,
    )
    safe_recovery = next(
        (
            event
            for event in reversed(events)
            if event.get("phase") == "safe_recovery_shown"
        ),
        None,
    )
    return {
        "events": events,
        "motionSpec": next(
            (
                event.get("motionSpec")
                for event in reversed(events)
                if event.get("motionSpec") is not None
            ),
            None,
        ),
        "firstVisibleMs": next(
            (
                event.get("elapsedSinceProcessStartMs")
                for event in events
                if event.get("phase") == "nativeStatic"
            ),
            None,
        ),
        "welcomeExitMs": finished.get("welcomeExitMs") if finished else None,
        "exitReason": finished.get("exitReason") if finished else None,
        "replayCount": finished.get("replayCount") if finished else None,
        "shellFirstPaintMs": shell.get("shellFirstPaintMs") if shell else None,
        "overlayRemovedMs": (
            overlay_removed.get("overlayRemovedMs") if overlay_removed else None
        ),
        "safeRecoveryShown": safe_recovery is not None,
    }


def _native_watchdog_timeout_logged(raw_log: str) -> bool:
    return (
        "android_native_first_frame_timeout" in raw_log
        or "ios_native_first_frame_timeout" in raw_log
        or "web_first_frame_timeout" in raw_log
    )


def _flutter_safe_terminal_confirmed(raw_log: str) -> bool:
    """Flutter 已到可操作终态时，原生 watchdog 不得覆盖已可见 Flutter UI。"""

    return (
        "android_startup_safe_terminal_race_dismissed" in raw_log
        or "ios_startup_safe_terminal_race_dismissed" in raw_log
        or "android_startup_safe_terminal reportedElapsedMs=" in raw_log
        or "ios_startup_safe_terminal reportedElapsedMs=" in raw_log
        or "android_startup_safe_terminal elapsedMs=" in raw_log
        or "ios_startup_safe_terminal elapsedMs=" in raw_log
        or '"eventName":"startup_safe_terminal"' in raw_log
        or '"eventName": "startup_safe_terminal"' in raw_log
    )


def extract_dart_startup_attempts(raw_log: str) -> list[dict[str, Any]]:
    """Extract one bounded record for each Dart isolate startup attempt."""

    attempts: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?:android|ios)_dart_startup_attempt "
        r"attemptId=(?P<attemptId>[A-Za-z0-9_-]+)"
        r"(?:\s+launchMode=(?P<launchMode>[A-Za-z0-9_-]+))?"
        r"(?:\s+hotRestart=(?P<hotRestart>true|false))?"
        r"(?:\s+configurationState=(?P<configurationState>[A-Za-z0-9_-]+))?"
        r"(?:\s+missingDefineKeys=(?P<missingDefineKeys>[A-Z0-9_,]+))?"
    )
    for match in pattern.finditer(raw_log):
        attempts.append(
            {
                key: value
                for key, value in match.groupdict().items()
                if value is not None
            }
        )
    return attempts


def extract_startup_watchdog_evidence(raw_log: str) -> dict[str, Any]:
    """Emit the same attempt-level fields for Android and iOS probe evidence."""

    renderer = re.search(
        r"(?:android|ios)_flutter_first_frame elapsedMs=(\d+).*source=\S+",
        raw_log,
    )
    safe_terminal = re.search(
        r"(?:android|ios)_startup_safe_terminal (?:elapsedMs|reportedElapsedMs)=(\d+)",
        raw_log,
    )
    reported_safe_terminal = re.search(
        r"(?:android|ios)_startup_safe_terminal reportedElapsedMs=(\d+)",
        raw_log,
    )
    native_received_safe_terminal = re.search(
        r"(?:android|ios)_startup_safe_terminal .*?receivedMs=(\d+)",
        raw_log,
    )
    dart_attempt = re.search(
        r"(?:android|ios)_dart_startup_attempt "
        r"attemptId=([A-Za-z0-9_-]+)"
        r"(?:\s+launchMode=([A-Za-z0-9_-]+))?"
        r"(?:\s+hotRestart=(true|false))?"
        r"(?:\s+configurationState=([A-Za-z0-9_-]+))?"
        r"(?:\s+missingDefineKeys=([A-Z0-9_,]+))?",
        raw_log,
    )
    attempt = re.search(
        r'(?:attemptId=|"attemptId"\s*:\s*")([A-Za-z0-9_-]+)',
        raw_log,
    )
    failure_code = re.search(
        r'(?:failureCode=|"failureCode"\s*:\s*")([A-Za-z0-9_.-]+)',
        raw_log,
    )
    race_dismissed = "startup_safe_terminal_race_dismissed" in raw_log
    return {
        "rendererFirstFrameMs": int(renderer.group(1)) if renderer else None,
        "safeTerminalMs": int(safe_terminal.group(1)) if safe_terminal else None,
        "reportedSafeTerminalMs": (
            int(reported_safe_terminal.group(1))
            if reported_safe_terminal
            else int(safe_terminal.group(1))
            if safe_terminal
            else None
        ),
        "nativeReceivedSafeTerminalMs": (
            int(native_received_safe_terminal.group(1))
            if native_received_safe_terminal
            else None
        ),
        "watchdogOutcome": (
            "race_dismissed"
            if race_dismissed
            else "native_recovery"
            if _native_watchdog_timeout_logged(raw_log)
            else "not_triggered"
        ),
        "canonicalTerminal": None,
        "attemptId": dart_attempt.group(1) if dart_attempt else attempt.group(1) if attempt else None,
        "launchMode": dart_attempt.group(2) if dart_attempt else None,
        "hotRestart": (
            dart_attempt.group(3) == "true"
            if dart_attempt and dart_attempt.group(3) is not None
            else None
        ),
        "runtimeConfigurationState": dart_attempt.group(4) if dart_attempt else None,
        "missingDefineKeys": dart_attempt.group(5) if dart_attempt else None,
        "failureCode": failure_code.group(1) if failure_code else "",
    }


def _safe_terminal_within_deadline(
    evidence: dict[str, Any],
    deadline_ms: int,
) -> bool:
    reported = evidence.get("reportedSafeTerminalMs")
    received = evidence.get("nativeReceivedSafeTerminalMs")
    return (
        isinstance(reported, int)
        and reported <= deadline_ms
        and isinstance(received, int)
        and received <= deadline_ms
    )


def classify_startup_terminal(
    raw_log: str,
    sequence: dict[str, Any],
) -> str:
    """Return one of routerShell/safeRecovery/nativeRecovery/unresolved.

    A six-second sample is only meaningful when it reaches one of these
    explicit visual terminal surfaces. A static native branded background is
    never a terminal surface.
    """

    if sequence.get("safeRecoveryShown"):
        return "safeRecovery"
    if (
        sequence.get("shellFirstPaintMs") is not None
        and sequence.get("overlayRemovedMs") is not None
    ):
        return "routerShell"
    # watchdog timeout 与 Flutter safe_terminal 可能差几毫秒；若 Flutter 已确认
    # 安全终态（或已撤销竞态恢复面），不得再把样本判成 nativeRecovery。
    if _native_watchdog_timeout_logged(raw_log) and not _flutter_safe_terminal_confirmed(
        raw_log
    ):
        return "nativeRecovery"
    return "unresolved"


def percentile(values: list[int], ratio: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def summarize_metric_runs(samples: list[dict[str, Any]], key: str) -> dict[str, int | None]:
    values = [int(item[key]) for item in samples if item.get(key) is not None]
    return {
        "p50": percentile(values, 0.5),
        "p95": percentile(values, 0.95),
    }


def build_platform_samples(
    results: list[dict[str, Any]],
    platform: str,
    *,
    stamp: str,
    runs: int,
    output_dir: Path,
) -> list[dict[str, Any]]:
    platform_results = [item for item in results if item.get("platform") == platform]
    return [
        {
            "runId": stamp if runs <= 1 else f"{stamp}-run-{index + 1:02d}",
            "platform": platform,
            "activityDisplayedMs": item.get("activityDisplayedMs"),
            "activityOnCreateMs": item.get("activityOnCreateMs"),
            "flutterEngineConfiguredMs": item.get("flutterEngineConfiguredMs"),
            "firstVisibleMs": item.get("firstVisibleMs"),
            "welcomeExitMs": item.get("startupSequence", {}).get("welcomeExitMs"),
            "shellFirstPaintMs": item.get("startupSequence", {}).get(
                "shellFirstPaintMs"
            ),
            "overlayRemovedMs": item.get("startupSequence", {}).get(
                "overlayRemovedMs"
            ),
            "replayCount": item.get("startupSequence", {}).get("replayCount"),
            "exitReason": item.get("startupSequence", {}).get("exitReason"),
            "motionSpec": item.get("startupSequence", {}).get(
                "motionSpec"
            ),
            "deviceKind": item.get("deviceKind", "unknown"),
            "reportPath": str(output_dir),
        }
        for index, item in enumerate(platform_results)
    ]


def summarize_startup_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = (
        "activityDisplayedMs",
        "activityOnCreateMs",
        "flutterEngineConfiguredMs",
        "firstVisibleMs",
        "welcomeExitMs",
        "shellFirstPaintMs",
        "overlayRemovedMs",
    )
    return {
        "samples": samples,
        "p50": {
            metric: summarize_metric_runs(samples, metric)["p50"]
            for metric in metric_names
        },
        "p95": {
            metric: summarize_metric_runs(samples, metric)["p95"]
            for metric in metric_names
        },
    }


def resolve_first_visible_ms(
    analyses: list[ScreenshotAnalysis],
    budget_ms: int,
    *,
    require_branded: bool,
) -> int | None:
    predicate = (
        (lambda item: item.branded_or_content_visible)
        if require_branded
        else (lambda item: item.brand_transition_visible)
    )
    return next(
        (
            item.offset_ms
            for item in analyses
            if predicate(item)
            and item.offset_ms is not None
            and item.offset_ms <= budget_ms
        ),
        None,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_android_local_ca(raw_path: str) -> dict[str, str]:
    if not raw_path.strip():
        return {"state": "not_provided"}
    path = Path(raw_path).expanduser()
    if not path.is_file():
        return {"state": "missing", "path": str(path)}
    content = path.read_bytes()
    if b"quwoquan-local-debug-placeholder" in content:
        return {"state": "placeholder", "path": str(path)}
    certificate = run(
        ["openssl", "x509", "-noout", "-fingerprint", "-sha256", "-in", str(path)],
        check=False,
        timeout=15,
    )
    if certificate.returncode != 0:
        return {"state": "invalid", "path": str(path)}
    return {
        "state": "valid",
        "path": str(path),
        "sha256Fingerprint": certificate.stdout.strip(),
        "sha256": sha256_file(path),
    }


def build_provenance() -> dict[str, Any]:
    revision = run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        timeout=15,
    )
    dirty = run(
        ["git", "status", "--porcelain"],
        check=False,
        timeout=15,
    )
    return {
        "revision": revision.stdout.strip() if revision.returncode == 0 else "unknown",
        "workspaceDirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
    }


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
    start_clock = time.monotonic()
    start = run(
        [
            "adb",
            "-s",
            args.android_device,
            "shell",
            "am",
            "start",
            "-n",
            args.android_activity,
        ],
        timeout=15,
    )
    (output_dir / "android-am-start.txt").write_text(start.stdout, encoding="utf-8")

    analyses: list[ScreenshotAnalysis] = []
    log: str | None = None
    if args.skip_screenshots:
        log = _wait_for_android_startup_log(
            args.android_device,
            hard_deadline_ms=args.welcome_exit_hard_ms,
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
        log = run(
            ["adb", "-s", args.android_device, "logcat", "-d"],
            timeout=15,
        ).stdout
    (output_dir / "android-logcat.txt").write_text(log, encoding="utf-8")
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
    first_visible = (
        (
            sequence.get("firstVisibleMs")
            or timings.get("android_flutter_first_frame")
        )
        if args.skip_screenshots
        else resolve_first_visible_ms(
            analyses,
            args.android_visible_by_ms,
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
    blue_screen_detected = native_static_at_deadline and not terminal_surface_classified
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
        and terminal_surface_classified
        and ttid_within_budget
        and (first_visible is not None or not args.require_branded_visible)
        and flutter_ui_within_budget
        and (
            not args.require_startup_sequence_events
            or (
                sequence_events_present
                and welcome_exit_within_deadline
                and overlay_removed_within_deadline
                and safe_terminal_within_deadline
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
    )
    return {
        "platform": "android",
        "device": args.android_device,
        "deviceKind": android_device_kind(args.android_device),
        "apk": str(apk) if args.android_install else None,
        "passed": passed,
        "visibleByMs": args.android_visible_by_ms,
        "firstVisibleMs": first_visible,
        "ttidWithinBudget": ttid_within_budget,
        "activityDisplayedMs": activity_displayed_ms,
        "activityOnCreateMs": activity_on_create_ms,
        "flutterEngineConfiguredMs": engine_configured_ms,
        "nativeWelcomeDetected": native_welcome_detected,
        "nativeWelcomeHits": native_welcome_hits,
        "blueScreenDetected": blue_screen_detected,
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
        "localCa": inspect_android_local_ca(args.android_local_ca_path),
        "screenshots": [item.to_json() for item in analyses],
    }


def _wait_for_android_startup_log(device: str, *, hard_deadline_ms: int) -> str:
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


def capture_ios(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    app = Path(args.ios_app)
    if args.ios_install and app.exists():
        run(
            ["xcrun", "simctl", "uninstall", args.ios_device, args.ios_bundle],
            check=False,
            timeout=60,
        )
        run(["xcrun", "simctl", "install", args.ios_device, str(app)], timeout=120)
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
    (output_dir / "ios-simctl-launch.txt").write_text(launch.stdout, encoding="utf-8")
    launch_pid_match = re.search(r":\s*(\d+)\s*$", launch.stdout)
    launch_pid = int(launch_pid_match.group(1)) if launch_pid_match else None

    analyses: list[ScreenshotAnalysis] = []
    ios_log: str | None = None
    if args.skip_screenshots:
        ios_log = _wait_for_ios_startup_log(
            args.ios_device,
            launch_pid=launch_pid,
            hard_deadline_ms=args.welcome_exit_hard_ms,
        )
    else:
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
        ttid_within_budget
        and not blue_screen_detected
        and not plain_background_detected
        and terminal_surface_classified
        and (
            not args.require_startup_sequence_events
            or (
                sequence_events_present
                and welcome_exit_within_deadline
                and overlay_removed_within_deadline
                and safe_terminal_within_deadline
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
    )
    return {
        "platform": "ios",
        "device": args.ios_device,
        "deviceKind": "simulator",
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
        ):
            return latest
        time.sleep(0.25)
    return latest


def analyze_existing_screenshots(args: argparse.Namespace) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for raw in args.screenshot:
        label, path_raw = raw.split("=", 1)
        path = Path(path_raw)
        analysis = analyze_screenshot(path)
        results.append(
            {
                "platform": label,
                "passed": analysis.branded_or_content_visible,
                "screenshots": [analysis.to_json()],
            }
        )
    return results


def parse_offsets(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--android-device")
    parser.add_argument("--android-package", default=DEFAULT_ANDROID_PACKAGE)
    parser.add_argument("--android-activity", default=DEFAULT_ANDROID_ACTIVITY)
    parser.add_argument("--android-apk", default=str(DEFAULT_ANDROID_APK))
    parser.add_argument(
        "--android-local-ca-path",
        default="",
        help="Inspect the debug CA used to build the Android APK and record its fingerprint.",
    )
    parser.add_argument("--android-install", action="store_true")
    parser.add_argument(
        "--android-offsets-ms",
        type=parse_offsets,
        default=[400, 600, 800, 1000, 1500, 2000, 3000, 6000],
    )
    parser.add_argument("--android-visible-by-ms", type=int, default=2000)
    parser.add_argument("--android-flutter-ui-max-ms", type=int, default=3000)
    parser.add_argument("--shell-first-paint-target-ms", type=int, default=3000)
    parser.add_argument("--welcome-exit-hard-ms", type=int, default=6000)
    parser.add_argument(
        "--require-startup-sequence-events",
        action="store_true",
        help="Require terminal timing evidence and <= hard deadline.",
    )
    parser.add_argument(
        "--skip-screenshots",
        action="store_true",
        help="Measure startup timing without screencap-induced renderer stalls.",
    )
    parser.add_argument(
        "--enforce-shell-target",
        action="store_true",
        help="Fail when shellFirstPaintMs exceeds shell-first-paint-target-ms.",
    )
    parser.add_argument(
        "--require-no-native-recovery",
        action="store_true",
        help="Fail a run when native recovery is shown; required for repeated release probes.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Repeat cold-start probe N times and emit p50/p95 summary.",
    )
    parser.add_argument(
        "--write-baseline",
        help="Write aggregated baseline JSON to this path after multi-run probe.",
    )
    parser.add_argument(
        "--require-branded-visible",
        action="store_true",
        help="Fail when branded welcome is not visible within visible-by-ms.",
    )
    parser.add_argument("--ios-device")
    parser.add_argument("--ios-bundle", default=DEFAULT_IOS_BUNDLE)
    parser.add_argument("--ios-app", default=str(DEFAULT_IOS_APP))
    parser.add_argument("--ios-install", action="store_true")
    parser.add_argument(
        "--runtime-env",
        choices=("alpha", "beta", "gamma", "prod"),
        default="",
    )
    parser.add_argument(
        "--matrix-evidence-root",
        default="",
        help="Write one normalized platform evidence file for the startup matrix.",
    )
    parser.add_argument(
        "--ios-offsets-ms",
        type=parse_offsets,
        default=[200, 400, 600, 800, 1000, 1400, 3000, 6000],
    )
    parser.add_argument("--ios-visible-by-ms", type=int, default=1500)
    parser.add_argument(
        "--screenshot",
        action="append",
        default=[],
        help="Analyze an existing screenshot as label=/path/file.png.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    stamp = time.strftime("%Y%m%dT%H%M%S")
    output_dir = Path(args.output_dir) / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    run_reports: list[dict[str, Any]] = []
    for run_index in range(max(args.runs, 1)):
        run_dir = output_dir
        if args.runs > 1:
            run_dir = output_dir / f"run-{run_index + 1:02d}"
            run_dir.mkdir(parents=True, exist_ok=True)
        run_results: list[dict[str, Any]] = []
        if args.android_device:
            # 多轮冷启动应复用同一已安装的当前 APK；每轮 reinstall 不仅
            # 偏离冷启动语义，也会耗尽 emulator 的 PackageInstaller 临时空间。
            args.android_install = run_index == 0 and bool(args.android_install)
            run_results.append(capture_android(args, run_dir))
        if args.ios_device:
            run_results.append(capture_ios(args, run_dir))
        if run_index == 0:
            run_results.extend(analyze_existing_screenshots(args))
        if not run_results and run_index == 0:
            print("No startup probe target supplied.", file=sys.stderr)
            return 2
        results.extend(run_results)
        if args.runs > 1 and run_results:
            run_reports.append(
                {
                    "run": run_index + 1,
                    "outputDir": str(run_dir),
                    "results": run_results,
                }
            )
        if args.runs > 1 and args.android_device and run_index + 1 < args.runs:
            time.sleep(1.5)

    platform_samples = {
        platform: build_platform_samples(
            results,
            platform,
            stamp=stamp,
            runs=args.runs,
            output_dir=output_dir,
        )
        for platform in ("android", "ios")
    }
    platform_summaries = {
        platform: summarize_startup_samples(samples)
        for platform, samples in platform_samples.items()
        if samples
    }
    summary: dict[str, Any] | None = (
        platform_summaries.get("android")
        or platform_summaries.get("ios")
    )

    report = {
        "outputDir": str(output_dir),
        "buildProvenance": build_provenance(),
        "runs": args.runs,
        "passed": all(item["passed"] for item in results),
        "summary": summary,
        "summaryByPlatform": platform_summaries,
        "runReports": run_reports or None,
        "results": results,
    }
    report_path = output_dir / "startup_first_frame_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.matrix_evidence_root:
        if not args.runtime_env:
            raise ValueError("--runtime-env is required with --matrix-evidence-root")
        if args.runs != 1:
            raise ValueError("matrix evidence export requires --runs 1")
        matrix_root = Path(args.matrix_evidence_root) / args.runtime_env
        matrix_root.mkdir(parents=True, exist_ok=True)
        for result in results:
            platform = result.get("platform")
            if platform not in {"android", "ios"}:
                continue
            evidence = {
                "runtimeEnv": args.runtime_env,
                "platform": platform,
                "attemptId": result.get("attemptId"),
                "rendererFirstFrameMs": result.get("rendererFirstFrameMs"),
                "safeTerminalMs": result.get("safeTerminalMs"),
                "reportedSafeTerminalMs": result.get("reportedSafeTerminalMs"),
                "nativeReceivedSafeTerminalMs": result.get(
                    "nativeReceivedSafeTerminalMs"
                ),
                "watchdogOutcome": result.get("watchdogOutcome"),
                "canonicalTerminal": result.get("canonicalTerminal"),
                "launchMode": result.get("launchMode"),
                "hotRestart": result.get("hotRestart"),
                "runtimeConfigurationState": result.get(
                    "runtimeConfigurationState"
                ),
                "missingDefineKeys": result.get("missingDefineKeys"),
                "failureCode": result.get("failureCode", ""),
                "sourceReport": str(report_path),
            }
            (matrix_root / f"{platform}.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    if args.write_baseline:
        baseline_path = Path(args.write_baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        selected_platforms = [
            platform for platform, samples in platform_samples.items() if samples
        ]
        baseline_samples = [
            sample
            for platform in selected_platforms
            for sample in platform_samples[platform]
        ]
        baseline = {
            "schema": "startup-first-frame-report",
            "capturedAt": time.strftime("%Y-%m-%d"),
            "platform": "+".join(selected_platforms),
            "deviceProfile": args.android_device or args.ios_device or "unknown",
            "deviceKind": "+".join(
                sorted({str(sample["deviceKind"]) for sample in baseline_samples})
            ),
            "buildMode": "release",
            "metric": "startupWelcome3s6s",
            "sampleCount": len(baseline_samples),
            "samples": baseline_samples,
            "p50": summary["p50"] if summary else {},
            "p95": summary["p95"] if summary else {},
            "slaTargetRelease": {
                "ttidP50Ms": 1000,
                "ttidP95Ms": 2000,
                "shellFirstPaintMs": args.shell_first_paint_target_ms,
                "welcomeExitHardMs": args.welcome_exit_hard_ms,
            },
            "sourceReport": str(report_path),
        }
        baseline_path.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
