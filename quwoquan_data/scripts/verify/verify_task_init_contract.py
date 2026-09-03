#!/usr/bin/env python3
"""Validate one current three-file task-init package."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from content.execution.identity import parse_execution_id, validate_execution_id
from core import paths
from core.io import read_json
from core.schema import assert_valid

_REQUIRED = {
    "execution_manifest.json": ("execution", "content_execution_manifest"),
    "0.plan/request.json": ("execution", "task_init_request"),
    "0.plan/target_set.json": ("execution", "target_set"),
}


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _safe_ref(value: object) -> str | None:
    ref = str(value or "")
    path = PurePosixPath(ref)
    if (
        not ref
        or "\x00" in ref
        or path.is_absolute()
        or ref != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    return ref


def _read_required(root: Path, failures: list[str]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for ref, (domain, schema) in _REQUIRED.items():
        path = root / ref
        if not path.is_file():
            failures.append(f"{ref} is missing")
            continue
        try:
            value = read_json(path)
            if not isinstance(value, dict):
                raise TypeError("must contain one object")
            assert_valid(value, domain, schema, label=f"task-init {ref}")
        except (OSError, TypeError, ValueError) as exc:
            failures.append(f"{ref} is invalid: {exc}")
            continue
        values[ref] = value
    return values


def _bound_document(
    binding: object, *, label: str, failures: list[str]
) -> Mapping[str, Any] | None:
    if not isinstance(binding, Mapping):
        failures.append(f"{label} binding is invalid")
        return None
    if binding.get("scope") != "output":
        failures.append(f"{label} scope drift")
    ref = _safe_ref(binding.get("ref"))
    if ref is None:
        failures.append(f"{label} ref is unsafe")
        return None
    path = (paths.OUTPUT_ROOT / ref).resolve()
    try:
        path.relative_to(paths.OUTPUT_ROOT.resolve())
    except ValueError:
        failures.append(f"{label} ref escapes output root")
        return None
    if not path.is_file():
        failures.append(f"{label} input is missing: {ref}")
        return None
    raw = path.read_bytes()
    if binding.get("digest") != _digest(raw):
        failures.append(f"{label} exact digest drift")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        failures.append(f"{label} input is invalid JSON: {exc}")
        return None
    if not isinstance(value, Mapping):
        failures.append(f"{label} input must contain one object")
        return None
    return value


def _target_ref(target: Mapping[str, Any], *, carrier: str) -> str | None:
    name = str(target.get("name") or "").strip()
    entity_type = str(target.get("entityType") or "").strip().strip("/")
    if not name or len(entity_type.split("/")) != 2:
        return None
    if carrier == "homepage":
        return f"entities/{entity_type}/{name}"
    angle = str(target.get("publishAngle") or "").strip()
    title = str(target.get("publishTitle") or "").strip()
    sequence = target.get("publishSeq", 1)
    if (
        not angle
        or not title
        or isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence < 1
    ):
        return None
    return f"posts/{carrier}/{angle}/{title}/{sequence}"


def _candidate_projection(
    value: object, *, carrier: str
) -> tuple[list[dict[str, Any]], list[str]] | None:
    if not isinstance(value, list):
        return None
    pairs: list[tuple[str, dict[str, Any]]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            return None
        target = dict(raw)
        target["name"] = str(target.get("name") or "").strip()
        target["entityType"] = str(target.get("entityType") or "").strip().strip("/")
        if carrier != "homepage":
            target["publishAngle"] = str(target.get("publishAngle") or "").strip()
            target["publishTitle"] = str(target.get("publishTitle") or "").strip()
            target["publishSeq"] = target.get("publishSeq", 1)
        ref = _target_ref(target, carrier=carrier)
        if ref is None:
            return None
        pairs.append((ref, target))
    pairs.sort(key=lambda pair: pair[0])
    return [target for _, target in pairs], [ref for ref, _ in pairs]


def issues(execution_id: str) -> list[str]:
    try:
        normalized = validate_execution_id(execution_id)
    except ValueError as exc:
        return [str(exc)]
    root = paths.DATA_EXECUTIONS_ROOT / normalized
    failures: list[str] = []
    values = _read_required(root, failures)
    if failures:
        return failures

    manifest = values["execution_manifest.json"]
    request = values["0.plan/request.json"]
    target_set = values["0.plan/target_set.json"]
    if any(value.get("executionId") != normalized for value in values.values()):
        failures.append("task-init document executionId drift")

    carrier = parse_execution_id(normalized).content_type.value
    if any(value.get("carrier") != carrier for value in values.values()):
        failures.append("task-init carrier drift")

    family = manifest.get("familyRef")
    family_ref = family.get("ref") if isinstance(family, Mapping) else None
    if request.get("familyRef") != family_ref:
        failures.append("task-init familyRef drift")
    if not isinstance(family_ref, str) or _safe_ref(family_ref) is None:
        failures.append("task-init familyRef is unsafe")
    else:
        family_path = paths.recipe_path(family_ref)
        if not family_path.is_file():
            failures.append(f"task-init familyRef is missing: {family_ref}")
        elif not isinstance(family, Mapping) or family.get("digest") != _digest(family_path.read_bytes()):
            failures.append("task-init family exact digest drift")

    expected_refs = {
        "request": "0.plan/request.json",
        "targetSet": "0.plan/target_set.json",
    }
    for field, ref in expected_refs.items():
        binding = manifest.get(field)
        if not isinstance(binding, Mapping) or binding.get("ref") != ref:
            failures.append(f"task-init {field} canonical ref drift")
        elif binding.get("digest") != _digest((root / ref).read_bytes()):
            failures.append(f"task-init {field} exact digest drift")

    init_inputs = manifest.get("initInputs")
    if not isinstance(init_inputs, Mapping):
        failures.append("task-init initInputs binding is invalid")
        init_inputs = {}
    bindings = {
        "carrierDemand": request.get("carrierDemand"),
        "immutableCandidateBindings": request.get("immutableCandidateBindings"),
    }
    bound_inputs: dict[str, Mapping[str, Any] | None] = {}
    for name, binding in bindings.items():
        if init_inputs.get(name) != binding:
            failures.append(f"task-init {name} binding drift")
        bound_inputs[name] = _bound_document(
            binding, label=f"task-init {name}", failures=failures
        )

    demand_input = bound_inputs["carrierDemand"]
    candidate_input = bound_inputs["immutableCandidateBindings"]
    if demand_input is not None:
        expected_demand = {
            "executionId": normalized,
            "carrier": carrier,
            "familyRef": request.get("familyRef"),
            "quota": request.get("quota"),
            "retryOf": request.get("retryOf"),
        }
        if any(demand_input.get(field) != value for field, value in expected_demand.items()):
            failures.append("task-init carrier demand projection drift")
    if candidate_input is not None:
        expected_candidate = {
            "executionId": normalized,
            "carrier": carrier,
            "entityCatalogDigest": target_set.get("entityCatalogDigest"),
            "candidateCount": request.get("candidateCount"),
        }
        projection = _candidate_projection(candidate_input.get("targets"), carrier=carrier)
        if (
            any(candidate_input.get(field) != value for field, value in expected_candidate.items())
            or projection is None
            or projection[0] != target_set.get("targets")
            or projection[1] != target_set.get("targetRefs")
        ):
            failures.append("task-init candidate projection drift")

    candidate = target_set.get("candidateBinding")
    immutable_binding = bindings["immutableCandidateBindings"]
    if not isinstance(candidate, Mapping) or not isinstance(immutable_binding, Mapping):
        failures.append("task-init candidate binding is invalid")
    elif any(candidate.get(field) != immutable_binding.get(field) for field in ("scope", "ref", "digest")):
        failures.append("task-init candidate binding drift")

    targets = target_set.get("targets")
    target_refs = target_set.get("targetRefs")
    if not isinstance(targets, list) or not isinstance(target_refs, list):
        failures.append("task-init targets are invalid")
        targets = []
        target_refs = []
    derived_refs = [
        _target_ref(target, carrier=carrier) if isinstance(target, Mapping) else None
        for target in targets
    ]
    if any(ref is None for ref in derived_refs) or target_refs != derived_refs:
        failures.append("task-init targetRefs drift")
    if target_set.get("targetCount") != len(targets) or len(target_refs) != len(targets):
        failures.append("task-init target count drift")

    candidate_count = candidate.get("candidateCount") if isinstance(candidate, Mapping) else None
    if request.get("candidateCount") != len(targets) or candidate_count != len(targets):
        failures.append("task-init candidate count drift")
    quota = request.get("quota")
    if isinstance(quota, bool) or not isinstance(quota, int) or quota < 1 or quota > len(targets):
        failures.append("task-init quota is not covered")

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify task-init-contract")
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
