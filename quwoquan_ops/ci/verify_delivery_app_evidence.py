#!/usr/bin/env python3
"""Verify the unique push-owned App evidence closure for a Delivery PR."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.lib.github_actions_api import (
    GithubActionsApiError,
    load_paginated_items,
    load_run_and_jobs,
    parse_timestamp,
    request_json,
)
from quwoquan_ops.gate.verify_git_branch_policy import load_policy


EXPECTED_APP_JOBS = (
    "Delivery Gate — App Static",
    "Delivery Gate — App Tests Shard 0",
    "Delivery Gate — App Tests Shard 1",
    "Delivery Gate — App Tests Shard 2",
    "Delivery Gate — App Tests Shard 3",
    "Delivery Gate — App Serial",
    "Delivery Gate — App Canonical Coverage",
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PHASE_BY_JOB = {
    "Delivery Gate — App Static": "quwoquan_app_static",
    "Delivery Gate — App Serial": "quwoquan_app_serial",
    "Delivery Gate — App Canonical Coverage": "quwoquan_app_coverage",
}


class EvidenceError(RuntimeError):
    pass


def _fail(reason: str, detail: str) -> EvidenceError:
    return EvidenceError(f"{reason}: {detail}")


def _seconds(job: dict[str, object]) -> int:
    try:
        started = parse_timestamp(job.get("started_at"), "job.started_at")
        completed = parse_timestamp(job.get("completed_at"), "job.completed_at")
    except (TypeError, ValueError) as error:
        raise _fail("JOB_TIMESTAMP_INVALID", str(error)) from error
    seconds = int((completed - started).total_seconds())
    if seconds < 0:
        raise _fail("JOB_TIMESTAMP_INVALID", "job timestamps are reversed")
    return seconds


def verify_app_evidence(
    *,
    runs: list[dict[str, object]],
    jobs: list[dict[str, object]],
    expected_repository: str,
    expected_workflow: str,
    expected_branch: str,
    expected_sha: str,
    observed_at: str,
    deadline_at: str,
) -> dict[str, object]:
    observed = parse_timestamp(observed_at, "observedAt")
    deadline = parse_timestamp(deadline_at, "deadlineAt")
    if observed > deadline:
        raise _fail("EVIDENCE_DEADLINE_EXCEEDED", "observation occurred after deadline")

    run_ids = {run.get("id") for run in runs}
    if not runs:
        raise _fail("RUN_NOT_FOUND", "no push Delivery run matched the source SHA")
    if len(run_ids) != 1 or None in run_ids:
        raise _fail("RUN_AMBIGUOUS", f"matched {len(run_ids)} distinct run IDs")
    run = max(runs, key=lambda item: int(item.get("run_attempt") or 0))
    identity = {
        "repository": (run.get("repository") or {}).get("full_name")
        if isinstance(run.get("repository"), dict)
        else None,
        "path": run.get("path"),
        "event": run.get("event"),
        "head_branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
    }
    expected_identity = {
        "repository": expected_repository,
        "path": expected_workflow,
        "event": "push",
        "head_branch": expected_branch,
        "head_sha": expected_sha,
    }
    if identity != expected_identity:
        raise _fail("RUN_IDENTITY_MISMATCH", f"expected {expected_identity}, got {identity}")
    if run.get("status") != "completed":
        raise _fail(
            "RUN_NOT_COMPLETED",
            f"status={run.get('status')}",
        )
    attempt = int(run.get("run_attempt") or 0)
    if attempt <= 0:
        raise _fail("RUN_IDENTITY_MISMATCH", "run attempt is missing")

    names = [str(job.get("name") or "") for job in jobs]
    counts = Counter(names)
    if set(counts) != set(EXPECTED_APP_JOBS) or any(value != 1 for value in counts.values()):
        raise _fail(
            "JOB_CLOSURE_MISMATCH",
            f"expected {list(EXPECTED_APP_JOBS)}, got {sorted(names)}",
        )
    for job in jobs:
        if int(job.get("run_attempt") or 0) != attempt:
            raise _fail("JOB_ATTEMPT_MISMATCH", str(job.get("name")))
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise _fail(
                "JOB_NOT_SUCCESSFUL",
                f"{job.get('name')}: status={job.get('status')} conclusion={job.get('conclusion')}",
            )

    seconds_by_job = {str(job["name"]): _seconds(job) for job in jobs}
    phase_seconds = {
        phase: seconds_by_job[name]
        for name, phase in PHASE_BY_JOB.items()
    }
    phase_seconds["quwoquan_app_tests"] = max(
        seconds
        for name, seconds in seconds_by_job.items()
        if name.startswith("Delivery Gate — App Tests Shard ")
    )
    closure_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            {
                "runId": run["id"],
                "runAttempt": attempt,
                "jobs": [
                    {
                        "name": name,
                        "seconds": seconds_by_job[name],
                    }
                    for name in sorted(seconds_by_job)
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "delivery-push-app-evidence",
        "status": "verified",
        "repository": expected_repository,
        "workflow": expected_workflow,
        "headBranch": expected_branch,
        "headSha": expected_sha,
        "runId": run["id"],
        "runAttempt": attempt,
        "observedAt": observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "deadlineAt": deadline.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "jobClosureDigest": closure_digest,
        "phaseSeconds": phase_seconds,
    }


def _delivery_workflow(policy: Any) -> str:
    matches = [
        check.workflow
        for check in policy.required_promotion_checks
        if check.name == "03. Delivery Gate"
    ]
    if len(matches) != 1:
        raise EvidenceError("POLICY_INVALID: Delivery workflow identity is not unique")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--current-run-id", required=True)
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--run-created-at", default="")
    parser.add_argument("--evidence-deadline-seconds", type=int, default=1500)
    parser.add_argument("--runs-json", type=Path)
    parser.add_argument("--jobs-json", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        if not args.repository or not SHA_PATTERN.fullmatch(args.head_sha) or not args.current_run_id:
            raise EvidenceError("INPUT_INVALID: repository, run ID and exact head SHA are required")
        policy = load_policy()
        workflow = _delivery_workflow(policy)
        authority_stats: dict[str, int | None] = {
            "requestCount": 0,
            "retryCount": 0,
            "lastHttpStatus": None,
            "rateLimitRemaining": None,
            "rateLimitResetEpoch": None,
        }
        run_created_value = args.run_created_at
        if not run_created_value:
            if not args.token:
                raise EvidenceError("INPUT_INVALID: GitHub token is required")
            current_run, current_stats = request_json(
                f"https://api.github.com/repos/{args.repository}/actions/runs/{args.current_run_id}",
                args.token,
            )
            authority_stats = current_stats
            run_created_value = (
                current_run.get("created_at")
                if isinstance(current_run, dict)
                else ""
            )
        run_created = parse_timestamp(run_created_value, "runCreatedAt")
        deadline = run_created.timestamp() + args.evidence_deadline_seconds
        deadline_at = datetime.fromtimestamp(deadline, timezone.utc)
        if args.runs_json is not None or args.jobs_json is not None:
            if args.runs_json is None or args.jobs_json is None:
                raise EvidenceError("INPUT_INVALID: runs-json and jobs-json must be paired")
            decoded_runs = json.loads(args.runs_json.read_text(encoding="utf-8"))
            decoded_jobs = json.loads(args.jobs_json.read_text(encoding="utf-8"))
            runs = decoded_runs.get("workflow_runs") if isinstance(decoded_runs, dict) else decoded_runs
            jobs = decoded_jobs.get("jobs") if isinstance(decoded_jobs, dict) else decoded_jobs
            if not isinstance(runs, list) or not isinstance(jobs, list):
                raise EvidenceError("AUTHORITY_RESPONSE_INVALID: fixtures must contain lists")
        else:
            if not args.token:
                raise EvidenceError("INPUT_INVALID: GitHub token is required")
            while True:
                runs, run_stats = load_paginated_items(
                    f"https://api.github.com/repos/{args.repository}/actions/workflows/{urllib_quote(workflow)}/runs",
                    args.token,
                    key="workflow_runs",
                    query={
                        "event": "push",
                        "branch": policy.integration_branch,
                        "head_sha": args.head_sha,
                    },
                    deadline=deadline_at,
                )
                run_ids = {run.get("id") for run in runs if isinstance(run, dict)}
                if len(run_ids) > 1:
                    jobs = []
                    break
                if len(run_ids) == 1:
                    _, all_jobs, job_stats = load_run_and_jobs(
                        args.repository,
                        str(next(iter(run_ids))),
                        args.token,
                        deadline=deadline_at,
                    )
                    authority_stats = {
                        "requestCount": int(run_stats["requestCount"] or 0)
                        + int(job_stats["requestCount"] or 0),
                        "retryCount": int(run_stats["retryCount"] or 0)
                        + int(job_stats["retryCount"] or 0),
                        "lastHttpStatus": job_stats["lastHttpStatus"],
                        "rateLimitRemaining": job_stats.get("rateLimitRemaining"),
                        "rateLimitResetEpoch": job_stats.get("rateLimitResetEpoch"),
                    }
                    jobs = [
                        job
                        for job in all_jobs
                        if str(job.get("name") or "") in EXPECTED_APP_JOBS
                        or str(job.get("name") or "").startswith(
                            "Delivery Gate — App Tests Shard "
                        )
                    ]
                    latest = max(
                        (run for run in runs if isinstance(run, dict)),
                        key=lambda item: int(item.get("run_attempt") or 0),
                    )
                    if latest.get("status") == "completed":
                        break
                remaining = (deadline_at - datetime.now(timezone.utc)).total_seconds()
                if remaining <= 0:
                    jobs = []
                    break
                time.sleep(min(15.0, remaining))
        observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result = verify_app_evidence(
            runs=[item for item in runs if isinstance(item, dict)],
            jobs=[item for item in jobs if isinstance(item, dict)],
            expected_repository=args.repository,
            expected_workflow=workflow,
            expected_branch=policy.integration_branch,
            expected_sha=args.head_sha,
            observed_at=observed_at,
            deadline_at=deadline_at.isoformat().replace("+00:00", "Z"),
        )
        result["authority"] = {
            **authority_stats,
            "matchedRunCount": len(
                {run.get("id") for run in runs if isinstance(run, dict)}
            ),
        }
        if args.github_output is not None:
            lines = [
                f"run_id={result['runId']}",
                f"run_attempt={result['runAttempt']}",
                f"job_closure_digest={result['jobClosureDigest']}",
                *[
                    f"phase_{name}={seconds}"
                    for name, seconds in sorted(result["phaseSeconds"].items())
                ],
            ]
            args.github_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (EvidenceError, GithubActionsApiError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def urllib_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


if __name__ == "__main__":
    raise SystemExit(main())
