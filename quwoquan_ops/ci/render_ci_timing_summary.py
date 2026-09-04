#!/usr/bin/env python3
"""Render the canonical CI timing summary from measured workflow evidence."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET_FILE = (
    REPO_ROOT / "quwoquan_ops" / "environments" / "pr_gate_timing_budgets.json"
)
CANONICAL_SCHEMA = "ci-timing-summary"
OFFICIAL_CRITICAL_PATH_SOURCE = "github_run_calendar"

TIMESTAMP_ARGUMENTS = {
    "runCreatedAt": "run_created_at",
    "candidateReadyAt": "candidate_ready_at",
    "approvalRequestedAt": "approval_requested_at",
    "approvalApprovedAt": "approval_approved_at",
    "prodFullyVerifiedAt": "prod_fully_verified_at",
}
OPTIONAL_DURATION_ARGUMENTS = {
    "queueSeconds": "queue_seconds",
    "setupSeconds": "setup_seconds",
    "executionSeconds": "execution_seconds",
    "humanDecisionWaitSeconds": "human_decision_wait_seconds",
    "approvalWaitSeconds": "approval_wait_seconds",
    "calendarLeadTimeSeconds": "calendar_lead_time_seconds",
}


def parse_non_negative_int(raw_value: str) -> int:
    value = int(float(raw_value.strip()))
    if value < 0:
        raise argparse.ArgumentTypeError("duration must be non-negative")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-key", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--workflow", default=os.environ.get("GITHUB_WORKFLOW", ""))
    parser.add_argument(
        "--workflow-run-id", default=os.environ.get("GITHUB_RUN_ID", "")
    )
    parser.add_argument(
        "--source-git-sha", default=os.environ.get("GITHUB_SHA", "")
    )
    parser.add_argument(
        "--candidate-digest", default=os.environ.get("QWQ_CANDIDATE_DIGEST", "")
    )
    parser.add_argument(
        "--budget-file",
        default=str(DEFAULT_BUDGET_FILE),
    )
    parser.add_argument(
        "--budget-profile",
        default="",
        help="Select one profile entry from the canonical gate timing policy.",
    )
    parser.add_argument(
        "--machine-critical-path-seconds", type=parse_non_negative_int
    )
    parser.add_argument(
        "--critical-path-source",
        choices=(OFFICIAL_CRITICAL_PATH_SOURCE, "shell_timer", "historical_import"),
        default=os.environ.get("QWQ_CI_CRITICAL_PATH_SOURCE", "") or None,
    )
    parser.add_argument("--run-created-at", default="")
    parser.add_argument("--candidate-ready-at", default="")
    parser.add_argument("--approval-requested-at", default="")
    parser.add_argument("--approval-approved-at", default="")
    parser.add_argument("--prod-fully-verified-at", default="")
    parser.add_argument("--queue-seconds", type=parse_non_negative_int)
    parser.add_argument("--setup-seconds", type=parse_non_negative_int)
    parser.add_argument("--execution-seconds", type=parse_non_negative_int)
    parser.add_argument("--human-decision-wait-seconds", type=parse_non_negative_int)
    parser.add_argument("--approval-wait-seconds", type=parse_non_negative_int)
    parser.add_argument("--calendar-lead-time-seconds", type=parse_non_negative_int)
    parser.add_argument("--phase", action="append", default=[])
    parser.add_argument("--missing-evidence", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument(
        "--functional-outcome",
        choices=("pass", "fail", "unknown"),
        default="unknown",
    )
    parser.add_argument(
        "--telemetry-classification",
        choices=("attempted", "runnable", "skipped", "infra"),
        default="attempted",
    )
    parser.add_argument(
        "--release-outcome",
        choices=(
            "not_applicable",
            "released",
            "rolled-back",
            "rollback-failed",
            "dry-run",
        ),
        default="not_applicable",
        help="Known terminal release outcome; non-release summaries omit it.",
    )
    parser.add_argument("--write-json", default="")
    parser.add_argument("--write-step-summary", action="store_true")
    return parser.parse_args()


def parse_key_value(item: str) -> Tuple[str, int]:
    if "=" not in item:
        raise ValueError("expected key=value, got {0!r}".format(item))
    key, raw_value = item.split("=", 1)
    key = key.strip()
    raw_value = raw_value.strip()
    if not key or not raw_value:
        raise ValueError("phase key and duration are required: {0!r}".format(item))
    seconds = int(float(raw_value))
    if seconds < 0:
        raise ValueError("phase duration must be non-negative: {0!r}".format(item))
    return key, seconds


def load_budget(path: Path, gate_key: str) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    gates = payload.get("gates") or {}
    if gate_key not in gates:
        raise KeyError("gate budget not found: {0}".format(gate_key))
    return dict(gates[gate_key])


def optional_budget_seconds(gate_budget: Dict[str, Any], key: str) -> Optional[int]:
    raw_value = gate_budget.get(key)
    if raw_value is None or raw_value == "":
        return None
    value = int(raw_value)
    if value < 0:
        raise ValueError("budget must be non-negative: {0}".format(key))
    return value


def timing_policy(
    gate_budget: Dict[str, Any], budget_profile: str
) -> tuple[Optional[str], Optional[int], Optional[int], str]:
    profile = budget_profile.strip() or None
    gate_hard_seconds = optional_budget_seconds(gate_budget, "hardFailSeconds")
    raw_policy = gate_budget.get("timingPolicy", "release_sla")
    if raw_policy not in {"release_sla", "telemetry_advisory"}:
        raise ValueError("canonical timing policy is invalid: {0}".format(raw_policy))
    policy = str(raw_policy)
    if profile is None:
        return None, gate_hard_seconds, gate_hard_seconds, policy
    raw_profiles = gate_budget.get("profileTiming")
    if not isinstance(raw_profiles, dict) or profile not in raw_profiles:
        raise ValueError(
            "canonical profile timing budget is missing: {0}".format(profile)
        )
    profile_budget = raw_profiles[profile]
    if not isinstance(profile_budget, dict):
        raise ValueError("canonical profile timing budget must be an object: {0}".format(profile))
    raw_value = profile_budget.get("hardFailSeconds")
    if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value <= 0:
        raise ValueError(
            "canonical profile hard budget must be a positive integer: {0}".format(profile)
        )
    raw_profile_policy = profile_budget.get("policy")
    if raw_profile_policy not in {"release_sla", "telemetry_advisory"}:
        raise ValueError("canonical profile timing policy is invalid: {0}".format(profile))
    return profile, raw_value, gate_hard_seconds, str(raw_profile_policy)


def normalize_optional_timestamp(raw_value: str) -> Optional[str]:
    value = raw_value.strip()
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone: {0!r}".format(value))
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def format_seconds(value: Optional[int]) -> str:
    if value is None:
        return "missing"
    minutes, seconds = divmod(max(int(value), 0), 60)
    if minutes == 0:
        return "{0}s".format(seconds)
    return "{0}m {1:02d}s".format(minutes, seconds)


def budget_status(
    *,
    end_to_end_seconds: Optional[int],
    soft_seconds: Optional[int],
    hard_seconds: Optional[int],
    missing_evidence: List[str],
    release_outcome: str = "not_applicable",
) -> str:
    if missing_evidence:
        return "historical_incomplete"
    if release_outcome == "dry-run":
        return "historical_incomplete"
    if release_outcome in {"rolled-back", "rollback-failed"}:
        return "failed"
    if end_to_end_seconds is None:
        return "historical_incomplete"
    if hard_seconds is not None and end_to_end_seconds > hard_seconds:
        return "failed"
    if soft_seconds is not None and end_to_end_seconds > soft_seconds:
        return "released_over_soft_budget"
    return "within_budget"


def build_payload(
    *,
    title: str,
    gate_key: str,
    workflow: str,
    workflow_run_id: str,
    source_git_sha: str,
    candidate_digest: str,
    gate_budget: Dict[str, Any],
    budget_profile: str,
    machine_critical_path_seconds: Optional[int],
    critical_path_source: Optional[str],
    timestamps: Dict[str, Optional[str]],
    optional_durations: Dict[str, Optional[int]],
    phases: List[Tuple[str, int]],
    upstream_missing_evidence: List[str],
    notes: List[str],
    release_outcome: str = "not_applicable",
    functional_outcome: str = "unknown",
    telemetry_classification: str = "attempted",
) -> Dict[str, Any]:
    soft_seconds = optional_budget_seconds(gate_budget, "budgetSeconds")
    normalized_budget_profile, hard_seconds, gate_hard_seconds, timing_policy_class = (
        timing_policy(gate_budget, budget_profile)
    )
    critical_definition = str(gate_budget.get("criticalPath", "")).strip() or None
    raw_phase_budgets = gate_budget.get("phaseBudgetsSeconds") or {}
    phase_budgets = {
        str(key): int(value)
        for key, value in raw_phase_budgets.items()
        if isinstance(value, int) and value >= 0
    }

    normalized_workflow = workflow.strip() or title.strip() or gate_key
    normalized_run_id = workflow_run_id.strip() or None
    normalized_source_sha = source_git_sha.strip() or None
    normalized_candidate_digest = candidate_digest.strip() or None
    normalized_notes = [note.strip() for note in notes if note.strip()]
    if release_outcome != "not_applicable":
        normalized_notes.append(f"releaseOutcome={release_outcome}")

    missing_evidence = [
        item.strip() for item in upstream_missing_evidence if item.strip()
    ]
    required_values = {
        "workflowRunId": normalized_run_id,
        "sourceGitSha": normalized_source_sha,
        "candidateDigest": normalized_candidate_digest,
        **{"timestamps.{0}".format(key): value for key, value in timestamps.items()},
        **{
            "durations.{0}".format(key): value
            for key, value in optional_durations.items()
        },
        "durations.machineCriticalPathSeconds": machine_critical_path_seconds,
        "budget.softSeconds": soft_seconds,
        "budget.hardSeconds": hard_seconds,
        "criticalPath.source": critical_path_source,
    }
    missing_evidence.extend(
        key for key, value in required_values.items() if value is None
    )
    if critical_path_source != OFFICIAL_CRITICAL_PATH_SOURCE:
        missing_evidence.append("criticalPath.githubRunCalendar")
    if not phases:
        missing_evidence.append("phases")
    missing_evidence = sorted(set(missing_evidence))

    durations = dict(optional_durations)
    durations["machineCriticalPathSeconds"] = machine_critical_path_seconds
    end_to_end_seconds = optional_durations.get("calendarLeadTimeSeconds")
    status = budget_status(
        end_to_end_seconds=end_to_end_seconds,
        soft_seconds=soft_seconds,
        hard_seconds=hard_seconds,
        missing_evidence=missing_evidence,
        release_outcome=release_outcome,
    )
    hard_budget_exceeded = (
        not missing_evidence
        and end_to_end_seconds is not None
        and hard_seconds is not None
        and end_to_end_seconds > hard_seconds
    )
    timing_projection = "PASS"
    if functional_outcome == "fail":
        timing_projection = "FUNCTIONAL_FAIL"
    elif timing_policy_class == "release_sla" and hard_budget_exceeded:
        timing_projection = "GATE_BLOCK"
    elif status == "historical_incomplete":
        timing_projection = "PR_WARN"
    elif timing_policy_class == "telemetry_advisory" and hard_budget_exceeded:
        timing_projection = "PR_WARN"
    elif functional_outcome == "pass" and telemetry_classification in {
        "runnable", "skipped", "infra"
    }:
        timing_projection = "PR_WARN"

    budget_payload: Dict[str, Any] = {
        "policy": timing_policy_class,
        "softSeconds": soft_seconds,
        "hardSeconds": hard_seconds,
        "deltaFromSoftSeconds": (
            end_to_end_seconds - soft_seconds
            if soft_seconds is not None and end_to_end_seconds is not None
            else None
        ),
        "deltaFromHardSeconds": (
            end_to_end_seconds - hard_seconds
            if hard_seconds is not None and end_to_end_seconds is not None
            else None
        ),
        "phaseSeconds": phase_budgets,
    }
    if normalized_budget_profile is not None:
        budget_payload["profile"] = normalized_budget_profile
        budget_payload["gateHardSeconds"] = gate_hard_seconds

    return {
        "schema": CANONICAL_SCHEMA,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workflow": {
            "gateKey": gate_key,
            "name": normalized_workflow,
            "title": title.strip() or gate_key,
        },
        "workflowRunId": normalized_run_id,
        "sourceGitSha": normalized_source_sha,
        "candidateDigest": normalized_candidate_digest,
        "status": status,
        "outcomePolicy": {
            "functional": functional_outcome,
            "telemetryClassification": telemetry_classification,
            "timing": timing_projection,
        },
        "timestamps": timestamps,
        "durations": durations,
        "budget": budget_payload,
        "criticalPath": {
            "source": critical_path_source,
            "definition": critical_definition,
            "seconds": end_to_end_seconds,
        },
        "phases": [
            {
                "name": key,
                "durationSeconds": seconds,
                "budgetSeconds": phase_budgets.get(key),
                "status": (
                    "within_budget"
                    if key in phase_budgets and seconds <= phase_budgets[key]
                    else "over_budget"
                    if key in phase_budgets
                    else "unbudgeted"
                ),
            }
            for key, seconds in phases
        ],
        "missingEvidence": missing_evidence,
        "notes": normalized_notes,
    }


def render_markdown(payload: Dict[str, Any]) -> str:
    workflow = payload["workflow"]
    budget = payload["budget"]
    critical_path = payload["criticalPath"]
    lines = [
        "## {0}".format(workflow["title"]),
        "",
        "- schema: `{0}`".format(payload["schema"]),
        "- soft budget: `{0}`".format(format_seconds(budget["softSeconds"])),
        "- timing policy: `{0}`".format(budget["policy"]),
        "- hard budget: `{0}`".format(format_seconds(budget["hardSeconds"])),
        "- end-to-end critical path: `{0}`".format(format_seconds(critical_path["seconds"])),
        "- machine critical path diagnostic: `{0}`".format(
            format_seconds(payload["durations"]["machineCriticalPathSeconds"])
        ),
        "- status: `{0}`".format(payload["status"]),
    ]
    if critical_path["definition"]:
        lines.append(
            "- critical path definition: `{0}`".format(
                critical_path["definition"]
            )
        )
    if payload["phases"]:
        lines.append("- phases:")
        for phase in payload["phases"]:
            suffix = ""
            if phase["budgetSeconds"] is not None:
                suffix = " (budget {0})".format(
                    format_seconds(phase["budgetSeconds"])
                )
            lines.append(
                "  - `{0}`: {1}{2}".format(
                    phase["name"], format_seconds(phase["durationSeconds"]), suffix
                )
            )
    if payload["missingEvidence"]:
        lines.append(
            "- missing evidence: `{0}`".format(
                "`, `".join(payload["missingEvidence"])
            )
        )
    for note in payload["notes"]:
        lines.append("- note: {0}".format(note))
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    budget_path = Path(args.budget_file)
    if not budget_path.is_absolute():
        budget_path = REPO_ROOT / budget_path
    phases = [parse_key_value(item) for item in args.phase]
    gate_budget = load_budget(budget_path, args.gate_key)
    title = args.title.strip() or args.gate_key
    timestamps = {
        canonical_key: normalize_optional_timestamp(getattr(args, argument_name))
        for canonical_key, argument_name in TIMESTAMP_ARGUMENTS.items()
    }
    optional_durations = {
        canonical_key: getattr(args, argument_name)
        for canonical_key, argument_name in OPTIONAL_DURATION_ARGUMENTS.items()
    }
    payload = build_payload(
        title=title,
        gate_key=args.gate_key,
        workflow=args.workflow,
        workflow_run_id=args.workflow_run_id,
        source_git_sha=args.source_git_sha,
        candidate_digest=args.candidate_digest,
        gate_budget=gate_budget,
        budget_profile=args.budget_profile,
        machine_critical_path_seconds=args.machine_critical_path_seconds,
        critical_path_source=args.critical_path_source,
        timestamps=timestamps,
        optional_durations=optional_durations,
        phases=phases,
        upstream_missing_evidence=args.missing_evidence,
        notes=args.note,
        release_outcome=args.release_outcome,
        functional_outcome=args.functional_outcome,
        telemetry_classification=args.telemetry_classification,
    )
    markdown = render_markdown(payload)
    print(markdown)
    if args.write_json.strip():
        json_path = Path(args.write_json.strip())
        if not json_path.is_absolute():
            json_path = REPO_ROOT / json_path
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.write_step_summary:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(markdown + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
