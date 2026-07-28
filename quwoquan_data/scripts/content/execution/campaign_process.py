"""Concurrent subprocess execution for frozen campaign clones."""
from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from content.execution.campaign_submission import campaign_root
from content.execution.campaign_workspace import (
    CampaignRuntimePaths,
    DetachedClone,
)


CAMPAIGN_CARRIERS = ("homepage", "article", "image", "video")
LaneRunner = Callable[[list[str], Path, dict[str, str], Path, float], int]


def _lane_argv(submission: dict[str, Any], *, stage: str) -> list[str]:
    argv = [
        "task",
        "execute",
        "--execution-id",
        str(submission["executionId"]),
        "--campaign-root-execution-id",
        str(submission["rootExecutionId"]),
        "--family",
        str(submission["familyRef"]),
        "--region-ref",
        str(submission["regionRef"]),
        "--selector",
        str(submission["selector"]),
        "--quota",
        str(submission["quota"]),
        "--count",
        str(submission["count"]),
        "--stage",
        stage,
    ]
    retry_of = str(submission.get("retryOf") or "").strip()
    if retry_of:
        argv.extend(["--retry-of", retry_of])
    topic = str(submission.get("topic") or "").strip()
    if topic:
        argv.extend(["--topic", topic])
    for provider in submission.get("sourceProviders") or []:
        argv.extend(["--source-provider", str(provider)])
    for name in submission.get("targetNames") or []:
        argv.extend(["--target", str(name)])
    return argv


def _default_lane_runner(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    timeout_seconds: float,
) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
    return int(proc.returncode)


def _run_lane(
    clone: DetachedClone,
    submission: dict[str, Any],
    *,
    stage: str,
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    timeout_seconds: float,
    lane_runner: LaneRunner,
) -> tuple[int, str | None]:
    log_path = (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "logs"
        / f"{clone.carrier}-{stage}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cli = clone.path / "quwoquan_data" / "scripts" / "cli.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "QWQ_OUTPUT_ROOT": str(runtime.output_root),
            "QWQ_PUBLISH_ROOT": str(runtime.publish_root),
        }
    )
    command = [sys.executable, "-B", str(cli), *_lane_argv(submission, stage=stage)]
    try:
        return (
            lane_runner(command, clone.path, env, log_path, timeout_seconds),
            None,
        )
    except subprocess.TimeoutExpired:
        return 124, f"{stage} timed out after {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001
        return 2, f"{type(exc).__name__}: {exc}"


def run_phase(
    clones: dict[str, DetachedClone],
    submissions: dict[str, dict[str, Any]],
    *,
    stage: str,
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    timeout_seconds: float,
    worker_count: int,
    lane_runner: LaneRunner | None = None,
) -> dict[str, tuple[int, str | None]]:
    runner = lane_runner or _default_lane_runner
    results: dict[str, tuple[int, str | None]] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {
            pool.submit(
                _run_lane,
                clones[carrier],
                submissions[carrier],
                stage=stage,
                runtime=runtime,
                root_execution_id=root_execution_id,
                timeout_seconds=timeout_seconds,
                lane_runner=runner,
            ): carrier
            for carrier in CAMPAIGN_CARRIERS
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


__all__ = [
    "CAMPAIGN_CARRIERS",
    "LaneRunner",
    "run_phase",
]
