#!/usr/bin/env python3
"""Device-level startup first-frame probe for Android, iOS, and Web.

This is a user-acceptance probe, not a unit test. It catches regressions where
the app remains on a plain native transition background for too long, or where
Android native code reintroduces a mirrored welcome page before Flutter's real
WelcomeScreen can render.
"""

from __future__ import annotations

import argparse
import json
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
DEFAULT_ANDROID_PACKAGE = "com.quwoquan.quwoquan_app"
DEFAULT_ANDROID_ACTIVITY = "com.quwoquan.quwoquan_app/.MainActivity"
DEFAULT_ANDROID_APK = APP_DIR / "build/app/outputs/flutter-apk/app-debug.apk"
DEFAULT_IOS_BUNDLE = "com.example.quwoquanApp"
DEFAULT_IOS_APP = APP_DIR / "build/ios/iphonesimulator/Runner.app"
DEFAULT_OUTPUT_DIR = APP_DIR / "artifacts/startup_first_frame/probe"
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
    branded_or_content_visible = foreground_ratio >= 0.18 or stddev_avg >= 14.0
    blue_background = (
        not branded_or_content_visible
        and median_rgb[0] <= 40
        and 90 <= median_rgb[1] <= 170
        and median_rgb[2] >= 210
    )
    return ScreenshotAnalysis(
        path=str(path),
        offset_ms=offset_ms,
        foreground_ratio=foreground_ratio,
        stddev_avg=stddev_avg,
        median_rgb=median_rgb,
        plain_background=not branded_or_content_visible,
        blue_background=blue_background,
        branded_or_content_visible=branded_or_content_visible,
    )


def parse_qwqstartup_log(raw: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for key in ("android_flutter_engine_configured", "android_flutter_ui_displayed"):
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


def capture_android(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    apk = Path(args.android_apk)
    if args.android_install and apk.exists():
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
    start_clock = time.monotonic()
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

    log = run(["adb", "-s", args.android_device, "logcat", "-d"], timeout=15).stdout
    (output_dir / "android-logcat.txt").write_text(log, encoding="utf-8")
    timings = parse_qwqstartup_log(log)
    native_welcome_hits = [
        pattern
        for pattern in FORBIDDEN_NATIVE_WELCOME_LOG_PATTERNS
        if pattern in log
    ]
    native_welcome_detected = bool(native_welcome_hits)
    first_visible = next(
        (
            item.offset_ms
            for item in analyses
            if item.branded_or_content_visible
            and item.offset_ms is not None
            and item.offset_ms <= args.android_visible_by_ms
        ),
        None,
    )
    flutter_ui_ms = timings.get("android_flutter_ui_displayed")
    activity_displayed_ms = timings.get("android_activity_displayed_ms")
    blue_screen_detected = any(
        item.blue_background
        and item.offset_ms is not None
        and item.offset_ms >= args.android_visible_by_ms
        for item in analyses
    )
    flutter_ui_within_budget = (
        flutter_ui_ms is None or flutter_ui_ms <= args.android_flutter_ui_max_ms
    )
    first_frame_within_budget = (
        activity_displayed_ms <= args.android_visible_by_ms
        if activity_displayed_ms is not None
        else first_visible is not None
    )
    plain_background_detected = (
        not first_frame_within_budget
        and any(
            item.plain_background
            and item.offset_ms is not None
            and item.offset_ms >= args.android_visible_by_ms
            for item in analyses
        )
    )
    passed = (
        not native_welcome_detected
        and not blue_screen_detected
        and not plain_background_detected
        and first_frame_within_budget
    )
    return {
        "platform": "android",
        "device": args.android_device,
        "passed": passed,
        "visibleByMs": args.android_visible_by_ms,
        "firstVisibleMs": first_visible,
        "activityDisplayedMs": activity_displayed_ms,
        "firstFrameWithinBudget": first_frame_within_budget,
        "nativeWelcomeDetected": native_welcome_detected,
        "nativeWelcomeHits": native_welcome_hits,
        "blueScreenDetected": blue_screen_detected,
        "plainBackgroundDetected": plain_background_detected,
        "flutterUiDisplayedMaxMs": args.android_flutter_ui_max_ms,
        "flutterUiDisplayedWithinBudget": flutter_ui_within_budget,
        "timings": timings,
        "screenshots": [item.to_json() for item in analyses],
    }


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
    launch = run(
        ["xcrun", "simctl", "launch", args.ios_device, args.ios_bundle],
        timeout=15,
    )
    (output_dir / "ios-simctl-launch.txt").write_text(launch.stdout, encoding="utf-8")

    analyses: list[ScreenshotAnalysis] = []
    start_clock = time.monotonic()
    for offset in args.ios_offsets_ms:
        target = start_clock + offset / 1000
        time.sleep(max(target - time.monotonic(), 0))
        actual_offset_ms = round((time.monotonic() - start_clock) * 1000)
        screenshot = output_dir / f"ios-{offset:04d}ms.png"
        run(
            ["xcrun", "simctl", "io", args.ios_device, "screenshot", str(screenshot)],
            timeout=15,
        )
        analyses.append(analyze_screenshot(screenshot, actual_offset_ms))

    first_visible = next(
        (
            item.offset_ms
            for item in analyses
            if item.branded_or_content_visible
            and item.offset_ms is not None
            and item.offset_ms <= args.ios_visible_by_ms
        ),
        None,
    )
    blue_screen_detected = any(item.blue_background for item in analyses)
    plain_background_detected = (
        first_visible is None
        and any(
            item.plain_background
            and item.offset_ms is not None
            and item.offset_ms >= args.ios_visible_by_ms
            for item in analyses
        )
    )
    passed = (
        first_visible is not None
        and not blue_screen_detected
        and not plain_background_detected
    )
    return {
        "platform": "ios",
        "device": args.ios_device,
        "passed": passed,
        "visibleByMs": args.ios_visible_by_ms,
        "firstVisibleMs": first_visible,
        "blueScreenDetected": blue_screen_detected,
        "plainBackgroundDetected": plain_background_detected,
        "screenshots": [item.to_json() for item in analyses],
    }


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
    parser.add_argument("--android-install", action="store_true")
    parser.add_argument(
        "--android-offsets-ms",
        type=parse_offsets,
        default=[200, 250, 500, 2000, 3000],
    )
    parser.add_argument("--android-visible-by-ms", type=int, default=3000)
    parser.add_argument("--android-flutter-ui-max-ms", type=int, default=3000)
    parser.add_argument("--ios-device")
    parser.add_argument("--ios-bundle", default=DEFAULT_IOS_BUNDLE)
    parser.add_argument("--ios-app", default=str(DEFAULT_IOS_APP))
    parser.add_argument("--ios-install", action="store_true")
    parser.add_argument("--ios-offsets-ms", type=parse_offsets, default=[200, 1400])
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
    if args.android_device:
        results.append(capture_android(args, output_dir))
    if args.ios_device:
        results.append(capture_ios(args, output_dir))
    results.extend(analyze_existing_screenshots(args))
    if not results:
        print("No startup probe target supplied.", file=sys.stderr)
        return 2

    report = {
        "outputDir": str(output_dir),
        "passed": all(item["passed"] for item in results),
        "results": results,
    }
    report_path = output_dir / "startup_first_frame_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
