#!/usr/bin/env python3
"""Activate a staged model release from immutable evaluation evidence.

This orchestration never reads or mutates model-registry storage directly. The
quality decision is reproduced from the same evidence used by Stage, and the
state transition is submitted only through the canonical CAS Activate facade.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import evaluate_gate
import model_release_client


def _load_evidence(path: str) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("model release evidence must be a JSON object")
    return document


def evaluate_activation_evidence(
    candidate: dict[str, Any],
    active: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    release_id = str(candidate.get("releaseId") or "").strip()
    scenario = str(candidate.get("scenario") or "").strip()
    metrics = candidate.get("evaluationMetrics")
    if not release_id or not scenario:
        return False, "candidate evidence requires releaseId and scenario"
    if not isinstance(metrics, dict) or not metrics:
        return False, "candidate evidence requires evaluationMetrics"

    active_metrics = (active or {}).get("evaluationMetrics") or {}
    if not isinstance(active_metrics, dict):
        return False, "active evidence evaluationMetrics must be an object"
    status, reason, _diversity = evaluate_gate.evaluate_metrics(
        scenario=scenario,
        candidate_metrics=metrics,
        active_metrics=active_metrics,
    )
    if status != "pass":
        return False, reason
    if candidate.get("status") not in {None, "pass"}:
        return False, "candidate evidence is not a passing Stage input"
    return True, reason


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Activate a staged model release from immutable evidence"
    )
    parser.add_argument("--candidate-evidence", required=True)
    parser.add_argument("--active-evidence", default="")
    parser.add_argument(
        "--expected-active-release-id",
        default=None,
        help="Exact current active release for CAS; omit only when none is active",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    candidate = _load_evidence(args.candidate_evidence)
    active = _load_evidence(args.active_evidence) if args.active_evidence else {}
    passed, reason = evaluate_activation_evidence(candidate, active)
    release_id = str(candidate.get("releaseId") or "").strip()
    scenario = str(candidate.get("scenario") or "").strip()

    if not passed:
        result: dict[str, Any] = {
            "status": "BLOCKED",
            "reason": reason,
            "releaseId": release_id,
            "scenario": scenario,
        }
        exit_code = 1
    elif args.dry_run:
        result = {
            "status": "PASS_DRYRUN",
            "reason": reason,
            "releaseId": release_id,
            "scenario": scenario,
        }
        exit_code = 0
    else:
        activation = model_release_client.activate_release(
            release_id=release_id,
            scenario=scenario,
            expected_active_release_id=args.expected_active_release_id,
        )
        result = {
            "status": "ACTIVATED",
            "reason": reason,
            "releaseId": release_id,
            "scenario": scenario,
            "release": activation,
        }
        exit_code = 0

    if args.out:
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"[activation_gate] {result['status']}: {result['reason']}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
