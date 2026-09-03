#!/usr/bin/env python3
"""Verify deterministic one-source-plan-per-target coverage."""
from __future__ import annotations

import argparse
import hashlib
from collections.abc import Mapping
from pathlib import Path

from content.execution.identity import validate_execution_id
from core import paths
from core.io import read_json
from core.schema import assert_valid

PLAN_ROOT = "sources/plans"


def plan_ref(target_ref: str) -> str:
    digest = hashlib.sha256(target_ref.encode("utf-8")).hexdigest()
    return f"{PLAN_ROOT}/{digest}.json"


def issues(execution_id: str) -> list[str]:
    try:
        normalized = validate_execution_id(execution_id)
    except ValueError as exc:
        return [str(exc)]
    root = paths.DATA_EXECUTIONS_ROOT / normalized
    target_set_path = root / "0.plan/target_set.json"
    if not target_set_path.is_file():
        return ["0.plan/target_set.json is missing"]
    try:
        target_set = read_json(target_set_path)
        assert_valid(target_set, "execution", "target_set", label="source-plan target_set")
    except (OSError, TypeError, ValueError) as exc:
        return [f"target_set is invalid: {exc}"]
    if not isinstance(target_set, Mapping):
        return ["target_set must contain one object"]

    failures: list[str] = []
    if target_set.get("executionId") != normalized:
        failures.append("target_set executionId drift")
    carrier = str(target_set.get("carrier") or "")
    refs = target_set.get("targetRefs")
    if not isinstance(refs, list) or not refs:
        return [*failures, "target_set must declare targetRefs"]

    expected = {plan_ref(str(ref)): str(ref) for ref in refs}
    plan_root = root / PLAN_ROOT
    observed = {
        path.relative_to(root).as_posix()
        for path in plan_root.glob("*.json")
        if path.is_file()
    } if plan_root.is_dir() else set()
    for extra in sorted(observed - set(expected)):
        failures.append(f"undeclared source plan: {extra}")

    covered: set[str] = set()
    for ref, target_ref in expected.items():
        path = root / ref
        if not path.is_file():
            failures.append(f"missing source plan: {ref}")
            continue
        try:
            plan = read_json(path)
            if not isinstance(plan, Mapping):
                raise TypeError("must contain one object")
            assert_valid(plan, "source", "source_plan", label=ref)
        except (OSError, TypeError, ValueError) as exc:
            failures.append(f"{ref}: schema invalid ({exc})")
            continue
        if plan.get("executionId") != normalized:
            failures.append(f"{ref}: executionId drift")
        if plan.get("targetRef") != target_ref:
            failures.append(f"{ref}: targetRef drift")
        if plan.get("carrier") != carrier:
            failures.append(f"{ref}: carrier drift")
        bound_target = str(plan.get("targetRef") or "")
        if bound_target in covered:
            failures.append(f"duplicate target coverage: {bound_target}")
        covered.add(bound_target)
        candidates = plan.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            failures.append(f"{ref}: candidates are missing")
        elif any(
            not isinstance(candidate, Mapping)
            or not str(candidate.get("url") or "").startswith("https://")
            for candidate in candidates
        ):
            failures.append(f"{ref}: every candidate URL must use https")
    if covered != set(str(ref) for ref in refs):
        failures.append("source plans do not uniquely cover target_set")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify source-plan")
    parser.add_argument("--execution-id", required=True)
    args = parser.parse_args(argv)
    failures = issues(args.execution_id)
    if failures:
        print("[verify_source_plan] FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("[verify_source_plan] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
