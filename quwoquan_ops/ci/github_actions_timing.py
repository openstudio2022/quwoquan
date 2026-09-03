#!/usr/bin/env python3
"""Read authoritative workflow/job/step timing from the GitHub Actions API.

No missing duration is converted to zero.  Optional phase matches are simply
omitted; callers therefore produce ``historical_incomplete`` timing evidence
until GitHub exposes every required fact.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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
    parse_timestamp,
)


APPROVAL_EVIDENCE_REASON = (
    "GitHub Deployment and Deployment Status timestamps describe deployment/job "
    "state, not an explicitly timed required-reviewer decision; queued or in_progress "
    "can include runner/concurrency queue. A durable deployment_review event bound to "
    "the repository, workflow run, head SHA, and production environment is required."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--run-json", type=Path)
    parser.add_argument("--jobs-json", type=Path)
    parser.add_argument(
        "--phase",
        action="append",
        default=[],
        help="Phase selector NAME=job-name-substring. Repeatable.",
    )
    parser.add_argument(
        "--require-count",
        action="append",
        default=[],
        help="Required completed job count NAME=COUNT. Repeatable.",
    )
    parser.add_argument(
        "--dag-layer",
        action="append",
        default=[],
        help="Comma-separated phase names running in parallel; layers run in order.",
    )
    parser.add_argument(
        "--dag-branch",
        action="append",
        default=[],
        help=(
            "Semicolon-separated serial layers for one parallel branch; each layer "
            "is a comma-separated phase set. Machine critical path is the longest branch."
        ),
    )
    parser.add_argument(
        "--external-phase",
        action="append",
        default=[],
        help=(
            "Official machine-path diagnostic from a reusable workflow as "
            "NAME=SECONDS. Repeatable."
        ),
    )
    parser.add_argument(
        "--candidate-job",
        default="",
        help="Unique candidate-ready job substring; defaults to the last matched phase job.",
    )
    parser.add_argument("--prod-job", default="")
    parser.add_argument(
        "--critical-start",
        choices=("run",),
        default="run",
        help="End-to-end evidence always starts at the official workflow run created_at.",
    )
    parser.add_argument("--github-output", required=True)
    return parser.parse_args()


def load_api_evidence(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if args.run_json or args.jobs_json:
        if not args.run_json or not args.jobs_json:
            raise ValueError("run-json and jobs-json must be supplied together")
        run = json.loads(args.run_json.read_text(encoding="utf-8"))
        jobs_payload = json.loads(args.jobs_json.read_text(encoding="utf-8"))
        jobs = jobs_payload.get("jobs") if isinstance(jobs_payload, dict) else jobs_payload
        if not isinstance(run, dict) or not isinstance(jobs, list):
            raise ValueError("timing fixture shape is invalid")
        return run, [item for item in jobs if isinstance(item, dict)]
    if not args.repository or not args.run_id or not args.token:
        raise ValueError("repository, run id and GitHub token are required")
    run, jobs, _ = load_run_and_jobs(args.repository, args.run_id, args.token)
    return run, jobs


def _parse_pairs(items: list[str], *, integer: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        name, separator, value = item.partition("=")
        if not separator or not name.strip() or not value.strip():
            raise ValueError(f"expected NAME=VALUE, got {item!r}")
        key = name.strip()
        if key in result:
            raise ValueError(f"duplicate timing selector: {key}")
        result[key] = int(value) if integer else value.strip()
    return result


def _job_seconds(job: dict[str, Any]) -> int:
    start = parse_timestamp(job.get("started_at"), f"{job.get('name')}.started_at")
    end = parse_timestamp(job.get("completed_at"), f"{job.get('name')}.completed_at")
    return max(0, int((end - start).total_seconds()))


def classify_job_attempt(job: dict[str, Any]) -> str:
    """Classify Actions job state without treating a skipped job as attempted."""

    conclusion = str(job.get("conclusion") or "")
    status = str(job.get("status") or "")
    if conclusion == "skipped":
        return "skipped"
    if status != "completed" and conclusion not in {
        "success", "failure", "cancelled", "timed_out", "action_required", "neutral"
    }:
        return "runnable"
    if conclusion in {"cancelled", "timed_out", "action_required"}:
        return "infra"
    return "attempted"


def _match_completed(jobs: list[dict[str, Any]], pattern: str) -> list[dict[str, Any]]:
    return [
        job
        for job in jobs
        if pattern in str(job.get("name") or "")
        and classify_job_attempt(job) == "attempted"
        and isinstance(job.get("started_at"), str)
        and isinstance(job.get("completed_at"), str)
    ]


def _one(jobs: list[dict[str, Any]], pattern: str, label: str) -> dict[str, Any]:
    matched = _match_completed(jobs, pattern)
    if len(matched) != 1:
        raise ValueError(
            f"expected exactly one completed {label} job matching {pattern!r}, "
            f"got {len(matched)}"
        )
    return matched[0]


def calculate(
    run: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    phases: dict[str, str],
    required_counts: dict[str, int],
    candidate_job: str,
    prod_job: str,
    critical_start: str,
    dag_layers: list[tuple[str, ...]],
    dag_branches: list[tuple[tuple[str, ...], ...]] | None = None,
    external_phases: dict[str, int] | None = None,
) -> dict[str, str | int]:
    external_phases = external_phases or {}
    if set(external_phases) & set(phases):
        overlap = sorted(set(external_phases) & set(phases))
        raise ValueError(f"timing phases are both API and external: {overlap}")
    if any(seconds < 0 for seconds in external_phases.values()):
        raise ValueError("external phase timing cannot be negative")
    run_created = parse_timestamp(run.get("created_at"), "run.created_at")
    matched_by_phase: dict[str, list[dict[str, Any]]] = {}
    for name, pattern in phases.items():
        matched = _match_completed(jobs, pattern)
        expected = required_counts.get(name)
        if expected is not None and len(matched) != expected:
            raise ValueError(
                f"phase {name} requires {expected} completed jobs, got {len(matched)}"
            )
        if matched:
            matched_by_phase[name] = matched
    unknown_counts = set(required_counts) - set(phases)
    if unknown_counts:
        raise ValueError(f"required counts have no phase selector: {sorted(unknown_counts)}")
    relevant = [job for group in matched_by_phase.values() for job in group]
    job_classifications = {
        "attempted": 0, "runnable": 0, "skipped": 0, "infra": 0
    }
    for job in jobs:
        job_classifications[classify_job_attempt(job)] += 1
    if not relevant:
        raise ValueError("no completed jobs matched the timing phases")

    candidate = (
        _one(jobs, candidate_job, "candidate")
        if candidate_job
        else max(
            relevant,
            key=lambda job: parse_timestamp(
                job.get("completed_at"), f"{job.get('name')}.completed_at"
            ),
        )
    )
    candidate_ready = parse_timestamp(
        candidate.get("completed_at"), "candidate.completed_at"
    )
    if critical_start != "run":
        raise ValueError("end-to-end timing must start at workflow run created_at")
    calendar_start = run_created
    calendar_end = candidate_ready
    prod: dict[str, Any] | None = None
    if prod_job:
        prod = _one(jobs, prod_job, "Prod")
        calendar_end = parse_timestamp(prod.get("completed_at"), "prod.completed_at")
    calendar_seconds = max(0, int((calendar_end - calendar_start).total_seconds()))

    result: dict[str, str | int] = {
        **{f"jobs_{name}": count for name, count in job_classifications.items()},
        "run_created_at": str(run["created_at"]),
        "candidate_ready_at": str(candidate["completed_at"]),
        "calendar_lead_time_seconds": calendar_seconds,
    }
    for name, matched in matched_by_phase.items():
        result[f"phase_{name}"] = max(_job_seconds(job) for job in matched)
    for name, seconds in external_phases.items():
        result[f"phase_{name}"] = seconds
    dag_branches = dag_branches or []
    if not dag_layers and not dag_branches:
        raise ValueError("official machine critical path requires explicit DAG layers or branches")
    if dag_layers and dag_branches:
        raise ValueError("machine critical path must use DAG layers or branches, not both")
    phase_seconds = {
        name: int(result[f"phase_{name}"])
        for name in (*matched_by_phase, *external_phases)
    }
    branch_layers = list(dag_branches) if dag_branches else [tuple(dag_layers)]
    unknown_dag_phases = {
        name
        for branch in branch_layers
        for layer in branch
        for name in layer
        if name not in phases and name not in external_phases
    }
    if unknown_dag_phases:
        raise ValueError(f"DAG names unknown timing phases: {sorted(unknown_dag_phases)}")
    missing_dag_evidence = {
        name
        for branch in branch_layers
        for layer in branch
        for name in layer
        if name not in phase_seconds
    }
    if missing_dag_evidence:
        raise ValueError(
            "DAG phase timing is missing; cannot calculate machine critical path: "
            + ", ".join(sorted(missing_dag_evidence))
        )
    result["machine_critical_path_seconds"] = max(
        sum(max(phase_seconds[name] for name in layer) for layer in branch)
        for branch in branch_layers
    )

    # These are official long-tail observations, not guessed additive values.
    queues: list[int] = []
    setups: list[int] = []
    executions: list[int] = []
    setup_complete = True
    missing_job_created_at = False
    for job in relevant:
        started = parse_timestamp(job.get("started_at"), f"{job.get('name')}.started_at")
        completed = parse_timestamp(
            job.get("completed_at"), f"{job.get('name')}.completed_at"
        )
        raw_created = job.get("created_at")
        created = (
            parse_timestamp(raw_created, f"{job.get('name')}.created_at")
            if isinstance(raw_created, str) and raw_created
            else None
        )
        if created is None:
            missing_job_created_at = True
        # A protected Prod job's pre-start interval can mix required review,
        # concurrency, and runner queue.  Keep the ambiguous interval out of
        # queueSeconds instead of assigning it to any one category.
        if job is not prod and created is not None:
            queues.append(max(0, int((started - created).total_seconds())))
        setup_steps = [
            step
            for step in (job.get("steps") or [])
            if str((step or {}).get("name") or "").strip().lower() == "set up job"
        ]
        if len(setup_steps) != 1:
            setup_complete = False
            continue
        setup_end = parse_timestamp(
            setup_steps[0].get("completed_at"), f"{job.get('name')}.setup.completed_at"
        )
        setup_start = parse_timestamp(
            setup_steps[0].get("started_at"), f"{job.get('name')}.setup.started_at"
        )
        setups.append(max(0, int((setup_end - setup_start).total_seconds())))
        executions.append(max(0, int((completed - setup_end).total_seconds())))
    if queues and not missing_job_created_at:
        result["queue_seconds"] = max(queues)
    if missing_job_created_at:
        result["missing_evidence"] = "githubJobs.createdAt"
    if setup_complete and setups and executions:
        result["setup_seconds"] = max(setups)
        result["execution_seconds"] = max(executions)

    if prod is not None:
        # GitHub Jobs timestamps do not identify environment review request or
        # approval events.  In particular, dependency completion and Prod job
        # started_at are not approval timestamps.  Leave those facts absent so
        # the canonical renderer records missing evidence instead of inventing
        # an approval wait or a zero human-decision wait.
        result["prod_completed_at"] = str(prod["completed_at"])
        result["approval_evidence_reason"] = APPROVAL_EVIDENCE_REASON
    return result


def write_github_output(path: Path, values: dict[str, str | int]) -> None:
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    try:
        run, jobs = load_api_evidence(args)
        values = calculate(
            run,
            jobs,
            phases=_parse_pairs(args.phase),
            required_counts=_parse_pairs(args.require_count, integer=True),
            candidate_job=args.candidate_job,
            prod_job=args.prod_job,
            critical_start=args.critical_start,
            dag_layers=[
                tuple(name.strip() for name in layer.split(",") if name.strip())
                for layer in args.dag_layer
                if layer.strip()
            ],
            dag_branches=[
                tuple(
                    tuple(name.strip() for name in layer.split(",") if name.strip())
                    for layer in branch.split(";")
                    if layer.strip()
                )
                for branch in args.dag_branch
                if branch.strip()
            ],
            external_phases=_parse_pairs(args.external_phase, integer=True),
        )
        write_github_output(Path(args.github_output), values)
    except (GithubActionsApiError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"github_actions_timing: FAIL: {error}")
        return 1
    print(json.dumps(values, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
