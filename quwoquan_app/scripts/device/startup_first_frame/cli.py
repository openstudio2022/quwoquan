"""CLI：参数定义、多轮编排、报告/矩阵证据/基线写出。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from .android_capture import capture_android
from .context import (
    DEFAULT_ANDROID_ACTIVITY,
    DEFAULT_ANDROID_APK,
    DEFAULT_ANDROID_MAIN_ACTIVITY,
    DEFAULT_ANDROID_PACKAGE,
    DEFAULT_IOS_APP,
    DEFAULT_IOS_BUNDLE,
    DEFAULT_OUTPUT_DIR,
)
from .execution import build_provenance
from .ios_capture import capture_ios
from .metrics import build_platform_samples, summarize_startup_samples
from .screenshot_analysis import analyze_screenshot


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
    parser.add_argument(
        "--android-main-activity",
        default=DEFAULT_ANDROID_MAIN_ACTIVITY,
    )
    parser.add_argument("--android-apk", default=str(DEFAULT_ANDROID_APK))
    parser.add_argument("--android-install", action="store_true")
    parser.add_argument(
        "--android-offsets-ms",
        type=parse_offsets,
        default=[400, 600, 800, 1000, 1500, 2000, 3000, 6000],
    )
    parser.add_argument("--android-visible-by-ms", type=int, default=2000)
    parser.add_argument(
        "--android-blue-transition-budget-ms",
        type=int,
        default=2000,
        help=(
            "Maximum allowed pure Android 12 system-blue transition before "
            "branded native/Flutter welcome petals must appear."
        ),
    )
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
        "--require-telemetry-ack",
        action="store_true",
        help="Wait for and require the server-persisted startup telemetry ACK.",
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
    parser.add_argument(
        "--ios-physical",
        action="store_true",
        help="Use xcrun devicectl console capture for a signed app on a real iPhone.",
    )
    parser.add_argument("--ios-bundle", default=DEFAULT_IOS_BUNDLE)
    parser.add_argument("--ios-app", default=str(DEFAULT_IOS_APP))
    parser.add_argument("--ios-install", action="store_true")
    parser.add_argument(
        "--runtime-env",
        choices=("alpha", "beta", "gamma", "prod"),
        default="",
    )
    parser.add_argument(
        "--runtime-target",
        choices=(
            "alpha-local",
            "beta-local",
            "gamma-local",
            "prod-sim",
            "prod-hosted",
        ),
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
        if (
            args.runs > 1
            and (args.android_device or args.ios_device)
            and run_index + 1 < args.runs
        ):
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
        matrix_case = args.runtime_target or args.runtime_env
        matrix_root = Path(args.matrix_evidence_root) / matrix_case
        matrix_root.mkdir(parents=True, exist_ok=True)
        for platform in ("android", "ios"):
            platform_results = [
                result for result in results if result.get("platform") == platform
            ]
            if not platform_results:
                continue
            samples: list[dict[str, Any]] = []
            for result in platform_results:
                sample = {
                    "runtimeEnv": args.runtime_env,
                    "runtimeTarget": matrix_case,
                    "platform": platform,
                    "deviceKind": result.get("deviceKind", "unknown"),
                    "passed": result.get("passed") is True,
                    "attemptId": result.get("attemptId"),
                    "rendererFirstFrameMs": result.get("rendererFirstFrameMs"),
                    "safeTerminalMs": result.get("safeTerminalMs"),
                    "reportedSafeTerminalMs": result.get(
                        "reportedSafeTerminalMs"
                    ),
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
                    "startupSequenceMotionCurrent": result.get(
                        "startupSequenceMotionCurrent"
                    ),
                    "effectiveLaunchManifestDigest": result.get(
                        "effectiveLaunchManifestDigest"
                    ),
                    "telemetryAcknowledged": result.get(
                        "telemetryAcknowledged"
                    ),
                    "sourceReport": str(report_path),
                }
                if platform == "android":
                    sample.update(
                        {
                            "launcherIntentUsed": result.get(
                                "launcherIntentUsed"
                            ),
                            "launcherStarted": result.get("launcherStarted"),
                            "launcherResolution": result.get(
                                "launcherResolution"
                            ),
                            "gateMainOrderObserved": result.get(
                                "gateMainOrderObserved"
                            ),
                            "taskSnapshot": result.get("taskSnapshot"),
                            "launchVisual": result.get("launchVisual"),
                        }
                    )
                else:
                    sample.update(
                        {
                            "sceneLaunchUsed": result.get("sceneLaunchUsed"),
                            "sceneStarted": result.get("sceneStarted"),
                            "sceneLauncher": result.get("sceneLauncher"),
                        }
                    )
                samples.append(sample)
            evidence = {
                "schema": "qwq.startup-runtime-evidence",
                "runtimeEnv": args.runtime_env,
                "runtimeTarget": matrix_case,
                "platform": platform,
                "runs": len(samples),
                "passed": all(sample["passed"] for sample in samples),
                "samples": samples,
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
