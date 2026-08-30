"""Calculate the reusable App candidate machine path from GitHub Jobs API facts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.lib.github_actions_api import (
    GithubActionsApiError,
    load_run_and_jobs,
)
from quwoquan_ops.cli.lib.app_identity import supported_build_products

BUILD_PRODUCT_IDS = tuple(
    product.build_product_id for product in supported_build_products()
)
if len(BUILD_PRODUCT_IDS) != 5 or len(set(BUILD_PRODUCT_IDS)) != 5:
    raise ValueError("baseline App build product set must contain exactly five products")
SHARD_JOB_PATTERN = "App package product"
AGGREGATE_JOB_PATTERN = "App candidate OCI / aggregate"
READY_STEP = "Expose immutable App OCI identity"


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"authoritative timestamp is missing: {label}")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _seconds(start: Any, end: Any, label: str) -> int:
    value = int((_timestamp(end, label + ".end") - _timestamp(start, label + ".start")).total_seconds())
    if value < 0:
        raise ValueError(f"authoritative timestamps are reversed: {label}")
    return value


def _one(jobs: list[dict[str, Any]], pattern: str) -> dict[str, Any]:
    matches = [job for job in jobs if pattern in str(job.get("name") or "")]
    if len(matches) != 1:
        raise ValueError(f"expected one App timing job matching {pattern!r}, got {len(matches)}")
    return matches[0]


def calculate(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    shard_seconds: dict[str, int] = {}
    shard_completed: list[datetime] = []
    for build_product_id in BUILD_PRODUCT_IDS:
        job_pattern = f"{SHARD_JOB_PATTERN} / {build_product_id}"
        job = _one(jobs, job_pattern)
        if job.get("conclusion") != "success":
            raise ValueError(f"App build-product shard is not successful: {job_pattern}")
        shard_seconds[build_product_id] = _seconds(
            job.get("started_at"), job.get("completed_at"), job_pattern
        )
        shard_completed.append(
            _timestamp(job.get("completed_at"), job_pattern + ".completed_at")
        )

    aggregate = _one(jobs, AGGREGATE_JOB_PATTERN)
    ready_steps = [
        step
        for step in aggregate.get("steps") or []
        if str((step or {}).get("name") or "") == READY_STEP
    ]
    if len(ready_steps) != 1 or ready_steps[0].get("conclusion") != "success":
        raise ValueError("App OCI ready step is not yet a unique successful API fact")
    ready_at = _timestamp(ready_steps[0].get("completed_at"), "App OCI ready step")
    aggregate_seconds = _seconds(
        aggregate.get("started_at"),
        ready_steps[0].get("completed_at"),
        "App aggregate to immutable OCI",
    )
    if _timestamp(aggregate.get("started_at"), "App aggregate.started_at") < max(shard_completed):
        raise ValueError("App aggregate started before all declared shard dependencies completed")
    return {
        "machine_critical_path_seconds": max(shard_seconds.values()) + aggregate_seconds,
        "candidate_ready_at": ready_at.isoformat().replace("+00:00", "Z"),
        "shard_seconds": shard_seconds,
        "aggregate_seconds": aggregate_seconds,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--jobs-json", type=Path)
    parser.add_argument("--github-output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.jobs_json is not None:
            decoded = json.loads(args.jobs_json.read_text(encoding="utf-8"))
            jobs = decoded.get("jobs") if isinstance(decoded, dict) else decoded
            if not isinstance(jobs, list):
                raise ValueError("jobs fixture must contain a list")
            result = calculate([item for item in jobs if isinstance(item, dict)])
        else:
            if not args.repository or not args.run_id or not args.token:
                raise ValueError("repository, run id and GitHub token are required")
            last_error: ValueError | None = None
            for delay in (0, 2, 5):
                if delay:
                    time.sleep(delay)
                try:
                    _, jobs, _ = load_run_and_jobs(
                        args.repository,
                        args.run_id,
                        args.token,
                    )
                    result = calculate(jobs)
                    break
                except ValueError as error:
                    last_error = error
            else:
                assert last_error is not None
                raise last_error
        args.github_output.write_text(
            f"machine_critical_path_seconds={result['machine_critical_path_seconds']}\n"
            f"candidate_ready_at={result['candidate_ready_at']}\n",
            encoding="utf-8",
        )
    except (GithubActionsApiError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"GATE_BLOCK: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
