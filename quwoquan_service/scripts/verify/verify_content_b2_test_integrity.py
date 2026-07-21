#!/usr/bin/env python3
"""Block stale B2 content/media contract-test bindings.

The B2 object contracts cite named Go tests as evidence.  A path-only check is
insufficient: a renamed or deleted test function made earlier readiness claims
look complete while executing no asserted behavior.  This verifier keeps the
object-level contract, readiness inventory, and executable Go test symbols
aligned without inferring product behavior from test names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
METADATA_CONTENT = ROOT / "quwoquan_service/contracts/metadata/content"
CONTENT_SERVICE = ROOT / "quwoquan_service/services/content-service"

B2_OBJECTS = (
    "content_reaction",
    "media_asset",
    "media_upload_session",
    "media_original_access_fact",
    "outbound_share_fact",
    "report",
    "post_moderation_case",
    "deleted_post_tombstone",
    "profile_interaction_activity_view",
    "profile_interaction_read_fact",
)

# Tombstone and media-binding evidence intentionally anchors to canonical Post
# operations.  They remain explicit rather than becoming a compatibility map.
EXTERNAL_OPERATION_ANCHORS = {
    "DeletePost",
    "GetPost",
    "SubmitPostPublication",
}

GO_TEST_FUNCTION = re.compile(r"^func\s+(Test[A-Za-z0-9_]+)\s*\(", re.MULTILINE)
OPERATION_TOKEN = re.compile(r"[A-Z][A-Za-z0-9_]*")


@dataclass(frozen=True)
class IntegrityReport:
    checked_objects: int
    checked_bindings: int
    issues: tuple[str, ...]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value = yaml.safe_load(source) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def collect_go_test_functions(content_service_root: Path) -> set[str]:
    functions: set[str] = set()
    for path in content_service_root.rglob("*_test.go"):
        functions.update(GO_TEST_FUNCTION.findall(path.read_text(encoding="utf-8")))
    return functions


def contract_entries(contract: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    entries = contract.get("scenarios", contract.get("tests"))
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path} must define non-empty scenarios or tests")
    if not all(isinstance(entry, dict) for entry in entries):
        raise ValueError(f"{path} scenarios/tests entries must be mappings")
    return entries


def declared_operations(entry: dict[str, Any]) -> set[str]:
    values = [entry.get("operation"), entry.get("command")]
    operations: set[str] = set()
    for value in values:
        if isinstance(value, str):
            operations.update(OPERATION_TOKEN.findall(value))
    return operations


def verify_integrity(
    metadata_content_root: Path = METADATA_CONTENT,
    content_service_root: Path = CONTENT_SERVICE,
    repository_root: Path = ROOT,
) -> IntegrityReport:
    issues: list[str] = []
    go_test_functions = collect_go_test_functions(content_service_root)
    bindings = 0

    for object_name in B2_OBJECTS:
        object_root = metadata_content_root / object_name
        readiness_path = object_root / "readiness.yaml"
        contract_path = object_root / "tests/contract.yaml"
        if not readiness_path.is_file():
            issues.append(f"{object_name}: missing readiness.yaml")
            continue
        if not contract_path.is_file():
            issues.append(f"{object_name}: missing tests/contract.yaml")
            continue

        try:
            readiness = load_yaml(readiness_path)
            entries = contract_entries(load_yaml(contract_path), contract_path)
        except (OSError, ValueError, yaml.YAMLError) as error:
            issues.append(f"{object_name}: invalid test metadata: {error}")
            continue

        declared_object_operations = {
            operation
            for operation in readiness.get("operations", [])
            if isinstance(operation, str) and operation.strip()
        }
        valid_operations = declared_object_operations | EXTERNAL_OPERATION_ANCHORS
        covered_operations: set[str] = set()

        for entry in entries:
            name = str(entry.get("name", "")).strip()
            operation = str(entry.get("operation", "")).strip()
            go_func = str(entry.get("go_func", "")).strip()
            status = str(entry.get("status", "")).strip()
            prefix = f"{object_name}:{name or '<unnamed>'}"

            if not name:
                issues.append(f"{object_name}: contract entry missing name")
            if not operation:
                issues.append(f"{prefix}: missing operation")
            elif operation not in valid_operations:
                issues.append(
                    f"{prefix}: operation {operation!r} is neither owned nor an explicit canonical anchor"
                )
            if not go_func:
                issues.append(f"{prefix}: missing go_func")
            elif go_func not in go_test_functions:
                issues.append(f"{prefix}: go_func {go_func!r} does not exist in content-service tests")
            if status in {"pending", "blocked"}:
                issues.append(f"{prefix}: unresolved contract scenario status={status!r}")

            covered_operations.update(declared_operations(entry))
            bindings += 1

        missing_operations = sorted(declared_object_operations - covered_operations)
        if missing_operations:
            issues.append(
                f"{object_name}: readiness operations lack contract-test coverage {missing_operations}"
            )

        tests = readiness.get("tests")
        if not isinstance(tests, dict):
            issues.append(f"{object_name}: readiness tests must be a mapping")
            continue
        for layer in ("local_contract", "api_integration"):
            paths = tests.get(layer)
            if not isinstance(paths, list) or not paths:
                issues.append(f"{object_name}: readiness lacks {layer} evidence")
                continue
            for value in paths:
                if not isinstance(value, str) or not value.strip():
                    issues.append(f"{object_name}: invalid {layer} evidence path {value!r}")
                    continue
                if not (repository_root / value).is_file():
                    issues.append(f"{object_name}: missing {layer} evidence file {value}")

    return IntegrityReport(
        checked_objects=len(B2_OBJECTS),
        checked_bindings=bindings,
        issues=tuple(issues),
    )


def main() -> int:
    report = verify_integrity()
    if report.issues:
        for issue in report.issues:
            print(f"FAIL: {issue}", file=sys.stderr)
        return 1
    print(
        "verify_content_b2_test_integrity: "
        f"OK ({report.checked_objects} objects, {report.checked_bindings} bindings)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
