#!/usr/bin/env python3
"""Validate one current host-only three-file task-init package."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from content.execution.identity import parse_execution_id, validate_execution_id
from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import ExecutionBundleIdentity, SourceDefinitionSnapshot


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _target_set_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def issues(execution_id: str) -> list[str]:
    try:
        normalized = validate_execution_id(execution_id)
    except ValueError as exc:
        return [str(exc)]
    root = paths.DATA_EXECUTIONS_ROOT / normalized
    required = {
        "execution_manifest.json": ("execution", "content_execution_manifest"),
        "0.plan/request.json": ("execution", "task_init_request"),
        "0.plan/target_set.json": ("execution", "target_set"),
    }
    failures: list[str] = []
    values: dict[str, dict[str, object]] = {}
    for ref, (domain, schema) in required.items():
        path = root / ref
        if not path.is_file():
            failures.append(f"{ref} is missing")
            continue
        value = read_json(path)
        if not isinstance(value, dict):
            failures.append(f"{ref} must contain one object")
            continue
        try:
            assert_valid(value, domain, schema, label=f"task-init {ref}")
        except (FileNotFoundError, TypeError, ValueError) as exc:
            failures.append(str(exc))
            continue
        values[ref] = value
    if failures:
        return failures
    manifest = values["execution_manifest.json"]
    request = values["0.plan/request.json"]
    target_set = values["0.plan/target_set.json"]
    if any(value.get("executionId") != normalized for value in values.values()):
        failures.append("task-init document executionId drift")
    identity = parse_execution_id(normalized)
    carrier = identity.content_type.value
    if request.get("carrier") != carrier:
        failures.append("task-init request carrier drift")
    if request.get("familyRef") != (manifest.get("familyRef") or {}).get("ref"):
        failures.append("task-init familyRef drift")
    if manifest.get("requestRef") != "0.plan/request.json" or manifest.get("targetSetRef") != "0.plan/target_set.json":
        failures.append("task-init canonical refs drift")
    if manifest.get("targetSetDigest") != _target_set_digest(target_set):
        failures.append("task-init targetSetDigest drift")
    candidate = target_set.get("candidateBinding")
    targets = target_set.get("targets")
    if not isinstance(candidate, Mapping) or not isinstance(targets, list):
        failures.append("task-init target_set candidate binding is invalid")
    elif candidate.get("candidateCount") != len(targets) or request.get("workUnitCount") != len(targets):
        failures.append("task-init candidate count drift")
    if not isinstance(request.get("quota"), int) or int(request["quota"]) < 1 or len(targets) < int(request["quota"]):
        failures.append("task-init quota is not covered")
    try:
        SourceDefinitionSnapshot.from_document(manifest.get("sourceDigest"))
        ExecutionBundleIdentity.from_document(manifest.get("executionBundle"))
    except (TypeError, ValueError) as exc:
        failures.append(f"task-init source identity invalid: {exc}")
    if manifest.get("hostRuntime") != "external_host_agent":
        failures.append("task-init hostRuntime is not external_host_agent")
    fingerprint = manifest.get("operationalFingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 71 or not fingerprint.startswith("sha256:"):
        failures.append("task-init operationalFingerprint is invalid")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_task_init_contract")
    parser.add_argument("--execution-id", required=True)
    args = parser.parse_args(argv)
    failures = issues(args.execution_id)
    if failures:
        print("[verify_task_init_contract] FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("[verify_task_init_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
