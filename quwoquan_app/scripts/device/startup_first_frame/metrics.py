"""多轮冷启动样本的 p50/p95 汇总与平台样本装配。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


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
