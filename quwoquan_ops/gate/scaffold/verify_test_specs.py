#!/usr/bin/env python3
"""Verify the three-layer test evidence contract for feature-tree acceptance files."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
FEATURE_TREE = ROOT / "specs" / "feature-tree"

ALLOWED_LAYERS = {"local_contract", "api_integration", "user_acceptance"}
ALLOWED_ENVS = {"local", "alpha", "beta", "gamma", "prod", "gamma_local", "prod_gray_initial"}
ALLOWED_ENVS_BY_LAYER = {
    "local_contract": {"local", "alpha"},
    "api_integration": {"beta", "gamma", "prod", "prod_gray_initial"},
    "user_acceptance": {"gamma_local", "prod_gray_initial"},
}
ACCEPTANCE_GROUPS = {
    "uat_acceptance",
    "domain_acceptance",
    "sit_acceptance",
    "gwt_acceptance",
    "contract_acceptance",
}
REQUIRED_GROUP_BY_LEVEL = {
    "L1_domain_service": "domain_acceptance",
    "L2_business_capability": "sit_acceptance",
    "L3_story": "gwt_acceptance",
}
TEMPLATE_GROUPS = {
    "app_root_acceptance.yaml": "uat_acceptance",
    "domain_service_acceptance.yaml": "domain_acceptance",
    "business_capability_acceptance.yaml": "sit_acceptance",
    "story_acceptance.yaml": "gwt_acceptance",
}
ALLOWED_STATUSES = {"pending", "partial", "implemented", "completed", "pending_evidence", "blocked"}
DONE_STATUSES = {"implemented", "completed"}
CASE_ID_PATTERN = re.compile(
    r"^(local_contract|api_integration|user_acceptance)\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2,}$"
)
GENERIC_SUITES = {
    "static_contract",
    "module_interaction",
    "service_contract",
    "app_api_integration",
    "story_local_contract",
    "story_api_integration",
    "metadata_contract",
    "domain_static_contract",
    "domain_service_contract",
    "capability_api_integration",
    "capability_local_contract",
    "affected_user_journey",
    "app_root_journey",
    "app_root_api_integration",
    "suite_id",
}
COMMAND_PREFIXES = (
    "make ",
    "bash ",
    "python ",
    "python3 ",
    "go test ",
    "go vet ",
    "go build ",
    "go run ",
    "flutter test ",
    "flutter analyze ",
    "dart ",
    "cd ",
    "curl ",
)


class FailureCollector:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def add(self, message: str) -> None:
        self.failures.append(message)

    def exit_code(self) -> int:
        if not self.failures:
            print("[verify] OK: three-layer test specs checked")
            return 0
        for failure in self.failures:
            print(f"[verify] FAIL: {failure}", file=sys.stderr)
        return 1


def load_yaml(path: Path, failures: FailureCollector) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        failures.add(f"{path.relative_to(ROOT)} cannot be parsed as YAML: {exc}")
        return {}


def validate_evidence_entry(path: Path, item_id: str, entry: Any, failures: FailureCollector) -> None:
    if not isinstance(entry, dict):
        failures.add(f"{path.relative_to(ROOT)} {item_id} test_evidence entry must be mapping")
        return

    layer = entry.get("layer")
    if layer not in ALLOWED_LAYERS:
        failures.add(f"{path.relative_to(ROOT)} {item_id} invalid layer {layer!r}")
        return

    suite = entry.get("suite")
    if not isinstance(suite, str) or not suite.strip():
        failures.add(f"{path.relative_to(ROOT)} {item_id} missing suite")
    elif suite.strip() in GENERIC_SUITES:
        failures.add(f"{path.relative_to(ROOT)} {item_id} uses generic suite {suite!r}")

    cases = entry.get("cases")
    if not isinstance(cases, list) or not cases:
        failures.add(f"{path.relative_to(ROOT)} {item_id} missing cases")
    else:
        for case_id in cases:
            case_text = str(case_id)
            if not CASE_ID_PATTERN.match(case_text):
                failures.add(f"{path.relative_to(ROOT)} {item_id} invalid case id {case_text!r}")
            elif not case_text.startswith(f"{layer}."):
                failures.add(
                    f"{path.relative_to(ROOT)} {item_id} case {case_text!r} does not match layer {layer!r}"
                )

    envs = entry.get("envs")
    if not isinstance(envs, list) or not envs:
        failures.add(f"{path.relative_to(ROOT)} {item_id} missing envs")
    else:
        invalid_envs = [str(env) for env in envs if str(env) not in ALLOWED_ENVS]
        if invalid_envs:
            failures.add(f"{path.relative_to(ROOT)} {item_id} invalid envs {invalid_envs}")
        unexpected_envs = [
            str(env)
            for env in envs
            if str(env) in ALLOWED_ENVS and str(env) not in ALLOWED_ENVS_BY_LAYER[layer]
        ]
        if unexpected_envs:
            allowed = sorted(ALLOWED_ENVS_BY_LAYER[layer])
            failures.add(
                f"{path.relative_to(ROOT)} {item_id} layer {layer!r} uses disallowed envs {unexpected_envs}; allowed={allowed}"
            )


def validate_item(path: Path, group_name: str, item_id: str, item: Any, failures: FailureCollector) -> None:
    if not isinstance(item, dict):
        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} must be mapping")
        return

    for key in ("title", "done_when", "tests", "status"):
        if key not in item:
            failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} missing {key}")

    if "evidence" in item:
        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} uses retired evidence field")

    status = str(item.get("status", "")).strip()
    if status not in ALLOWED_STATUSES:
        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} invalid status {status!r}")

    test_evidence = item.get("test_evidence")
    if not isinstance(test_evidence, dict):
        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} missing test_evidence")
    else:
        primary = test_evidence.get("primary")
        if not isinstance(primary, list) or not primary:
            failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} missing test_evidence.primary")
        for entry in primary or []:
            validate_evidence_entry(path, f"{group_name}.{item_id}", entry, failures)
        supporting = test_evidence.get("supporting", [])
        if supporting is None:
            supporting = []
        if not isinstance(supporting, list):
            failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} test_evidence.supporting must be list")
        else:
            for entry in supporting:
                validate_evidence_entry(path, f"{group_name}.{item_id}", entry, failures)

    tests = item.get("tests")
    if not isinstance(tests, dict):
        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} tests must be mapping")
        return
    for key in ("planned", "recorded"):
        if key not in tests:
            failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} tests missing {key}")

    planned = tests.get("planned") or []
    if not isinstance(planned, list):
        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} tests.planned must be list")
        planned = []
    for record in planned:
        validate_test_ref(path, f"{group_name}.{item_id}", record, failures, bucket_name="planned")

    recorded = tests.get("recorded") or []
    if not isinstance(recorded, list):
        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} tests.recorded must be list")
        recorded = []

    if status in DONE_STATUSES and not recorded:
        failures.add(f"{path.relative_to(ROOT)} {group_name}.{item_id} status {status!r} requires recorded evidence")

    for record in recorded:
        validate_test_ref(path, f"{group_name}.{item_id}", record, failures, bucket_name="recorded")


def validate_test_ref(
    path: Path,
    item_id: str,
    record: Any,
    failures: FailureCollector,
    *,
    bucket_name: str,
) -> None:
    if isinstance(record, dict):
        file_path = record.get("file")
        command = record.get("command")
        artifact = record.get("artifact")
        if file_path:
            if bucket_name == "recorded" and not evidence_path_exists(str(file_path)):
                failures.add(f"{path.relative_to(ROOT)} {item_id} recorded file missing: {file_path}")
            return
        if artifact:
            if bucket_name == "recorded" and str(artifact).startswith(".qwq_output/runs/") and not evidence_path_exists(str(artifact)):
                failures.add(f"{path.relative_to(ROOT)} {item_id} recorded artifact missing: {artifact}")
            return
        if command or artifact:
            return
        failures.add(
            f"{path.relative_to(ROOT)} {item_id} tests.{bucket_name} mapping needs file, command, or artifact"
        )
        return

    record_text = str(record)
    if record_text.startswith(("command:", "artifact:", "file:")):
        return
    if any(record_text.startswith(prefix) for prefix in COMMAND_PREFIXES):
        return
    if any(ch.isspace() for ch in record_text):
        failures.add(
            f"{path.relative_to(ROOT)} {item_id} tests.{bucket_name} must be structured; free-text entry {record_text!r}"
        )
        return
    if bucket_name == "recorded" and not evidence_path_exists(record_text):
        failures.add(f"{path.relative_to(ROOT)} {item_id} recorded path missing: {record_text}")


def evidence_path_exists(record_text: str) -> bool:
    path_text = record_text.split("::", 1)[0]
    if any(ch.isspace() for ch in path_text):
        return False
    if len(path_text) > 512:
        return False
    candidates = [ROOT / path_text]
    if not path_text.startswith(("quwoquan_app/", "quwoquan_service/", "quwoquan_data/", "quwoquan_ops/")):
        candidates.extend(
            [
                ROOT / "quwoquan_service" / path_text,
                ROOT / "quwoquan_data" / path_text,
                ROOT / "quwoquan_ops" / path_text,
            ]
        )
    return any(candidate.exists() for candidate in candidates)


def validate_acceptance_file(path: Path, failures: FailureCollector, required_group: str | None = None) -> None:
    data = load_yaml(path, failures)
    if not data:
        return
    for key in ("version", "node", "scope", "execution"):
        if key not in data:
            failures.add(f"{path.relative_to(ROOT)} missing {key}")
    if required_group and required_group not in data:
        failures.add(f"{path.relative_to(ROOT)} missing required group {required_group}")

    for group_name in ACCEPTANCE_GROUPS:
        group = data.get(group_name)
        if group is None:
            continue
        if not isinstance(group, dict) or not group:
            failures.add(f"{path.relative_to(ROOT)} {group_name} must be non-empty mapping")
            continue
        for item_id, item in group.items():
            validate_item(path, group_name, str(item_id), item, failures)


def verify_case_id_coverage(failures: FailureCollector) -> None:
    acceptance_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in FEATURE_TREE.rglob("acceptance.yaml")
    )
    for layer in ALLOWED_LAYERS:
        if f"{layer}." not in acceptance_text:
            failures.add(f"feature-tree acceptance has no {layer} case id")


def verify_legacy_test_terms(failures: FailureCollector) -> None:
    for path in FEATURE_TREE.rglob("acceptance.yaml"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\bT[1-4]\b", text):
            failures.add(f"{path.relative_to(ROOT)} contains retired T1-T4 term")


def verify_feature_tree_groups(failures: FailureCollector) -> None:
    root_acceptance = FEATURE_TREE / "acceptance.yaml"
    validate_acceptance_file(root_acceptance, failures, "uat_acceptance")

    index = load_yaml(FEATURE_TREE / "tree_index.yaml", failures)
    features = index.get("features", []) if isinstance(index, dict) else []

    def visit(node: dict[str, Any]) -> None:
        level = str(node.get("level", ""))
        required_group = REQUIRED_GROUP_BY_LEVEL.get(level)
        if required_group:
            acceptance_path = FEATURE_TREE / str(node.get("path", "")) / "acceptance.yaml"
            validate_acceptance_file(acceptance_path, failures, required_group)
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                visit(child)

    for feature in features:
        if isinstance(feature, dict):
            visit(feature)

    template_dir = FEATURE_TREE / "templates"
    for template_name, required_group in TEMPLATE_GROUPS.items():
        validate_acceptance_file(template_dir / template_name, failures, required_group)


def main() -> int:
    failures = FailureCollector()
    verify_feature_tree_groups(failures)
    verify_case_id_coverage(failures)
    verify_legacy_test_terms(failures)
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
