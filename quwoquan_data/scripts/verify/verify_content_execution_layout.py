#!/usr/bin/env python3
"""Fail closed on content execution work-package drift."""
from __future__ import annotations

import sys
from pathlib import Path
import json

import yaml

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import DATA_EXECUTIONS_ROOT, OBJECT_STAGES, REPO_ROOT, is_execution_id
from content.execution.spec_contract import ExecutionSpec
from content.execution.store import load_spec
from content.execution.workspace import load_execution_manifest, load_frozen_target_set


_ROOT_ALLOWED = {
    "execution_manifest.json",
    "0.plan",
    "sources",
    "entities",
    "posts",
    "_shared",
    "evidence",
    "publish_ref.json",
}
_RETIRED_SOURCE_DIRS = (
    "control_plane/tasks",
    "sop",
    "docs",
    "deploy",
)
_RETIRED_RUNTIME_PATHS = (
    "runtime/tasks",
    "runtime/batches",
    "data/runs",
    "content_runs",
)
_STAGES = {"1.download", "2.quality", "3.compose", "4.draft", "5.review"}
# Keep the forbidden evidence keys as runtime values. The source-level purity
# verifier must inspect product code, not report this verifier's own contract.
_RETIRED_IDENTITY_KEYS = frozenset(("task" + "Id", "batch" + "Id"))
_RETIRED_RUNTIME_IDENTITY_KEYS = frozenset(
    {
        "env",
        "contentType",
        "phase",
        "supplyMode",
        "sourceKey",
        "salt",
        "params",
        "coverageTargets",
        "executionInstance",
    }
)


def _identity_issues(execution_root: Path) -> list[str]:
    issues: list[str] = []

    def walk(value: object, path: str, source: Path) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _RETIRED_IDENTITY_KEYS:
                    issues.append(
                        f"{source.relative_to(REPO_ROOT)}:{path}.{key}: retired identity; use executionId"
                    )
                walk(child, f"{path}.{key}", source)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", source)

    for source in execution_root.rglob("*"):
        if not source.is_file() or source.suffix not in {".json", ".yaml", ".yml", ".ndjson", ".jsonl"}:
            continue
        try:
            if source.suffix in {".ndjson", ".jsonl"}:
                values = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
            elif source.suffix in {".yaml", ".yml"}:
                values = [yaml.safe_load(source.read_text(encoding="utf-8"))]
            else:
                values = [json.loads(source.read_text(encoding="utf-8"))]
        except (OSError, ValueError, yaml.YAMLError) as exc:
            issues.append(f"{source.relative_to(REPO_ROOT)}: unreadable structured evidence: {exc}")
            continue
        for value in values:
            walk(value, "$", source)
    return issues


def _object_stage_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for stage in root.rglob("1.download"):
        object_root = stage.parent
        missing = sorted(name for name in _STAGES if not (object_root / name).is_dir())
        if missing:
            issues.append(
                f"{object_root.relative_to(DATA_EXECUTIONS_ROOT)}: missing execution stages {', '.join(missing)}"
            )
    return issues


def _frozen_target_issues(execution_root: Path) -> list[str]:
    issues: list[str] = []
    execution_id = execution_root.name
    try:
        manifest = load_execution_manifest(execution_id)
        target_set = load_frozen_target_set(execution_id)
        execution_spec = ExecutionSpec.from_mapping(load_spec(execution_id))
    except (OSError, TypeError, ValueError) as exc:
        return [f"{execution_root.relative_to(REPO_ROOT)}: invalid execution identity contract: {exc}"]
    if target_set.get("selectionPolicy") != "frozen":
        issues.append(f"{execution_root.relative_to(REPO_ROOT)}: target-set selectionPolicy must be frozen")
    if manifest.get("requestRef") != "0.plan/request.json":
        issues.append(f"{execution_root.relative_to(REPO_ROOT)}: manifest requestRef must be 0.plan/request.json")
    if manifest.get("targetSetRef") != "0.plan/target_set.json":
        issues.append(f"{execution_root.relative_to(REPO_ROOT)}: manifest targetSetRef must be 0.plan/target_set.json")
    targets = target_set.get("targets")
    if not isinstance(targets, list):
        return [*issues, f"{execution_root.relative_to(REPO_ROOT)}: target set targets must be an array"]
    frozen_by_name = {
        target.get("name"): target
        for target in targets
        if isinstance(target, dict) and isinstance(target.get("name"), str)
    }
    if len(frozen_by_name) != len(targets):
        issues.append(f"{execution_root.relative_to(REPO_ROOT)}: target set names must be unique objects")
    spec_names = {target.name for target in execution_spec.scope.coverage_targets}
    if set(frozen_by_name) != spec_names:
        issues.append(
            f"{execution_root.relative_to(REPO_ROOT)}: execution spec and frozen target set names differ"
        )
    for spec_target in execution_spec.scope.coverage_targets:
        frozen_target = frozen_by_name.get(spec_target.name)
        if not isinstance(frozen_target, dict):
            continue
        expected_binding = (
            spec_target.qualified_homepage_source.to_dict()
            if spec_target.qualified_homepage_source is not None
            else None
        )
        actual_binding = frozen_target.get("qualifiedHomepageSource")
        if actual_binding != expected_binding:
            issues.append(
                f"{execution_root.relative_to(REPO_ROOT)}: {spec_target.name} qualifiedHomepageSource "
                "must exactly match the immutable execution spec"
            )
    for target in targets:
        if not isinstance(target, dict):
            issues.append(f"{execution_root.relative_to(REPO_ROOT)}: frozen target must be an object")
            continue
        parts = str(target.get("entityType") or "").strip("/").split("/")
        name = str(target.get("name") or "").strip()
        if len(parts) != 2 or not name:
            issues.append(f"{execution_root.relative_to(REPO_ROOT)}: invalid frozen target {target}")
            continue
        object_root = execution_root / "entities" / parts[0] / parts[1] / name
        missing = [stage for stage in OBJECT_STAGES if not (object_root / stage).is_dir()]
        if missing:
            issues.append(
                f"{object_root.relative_to(DATA_EXECUTIONS_ROOT)}: frozen target missing stages "
                + ", ".join(missing)
            )
    runtime_path = execution_root / "_shared/runtime_state.json"
    if runtime_path.is_file():
        try:
            runtime_state = json.loads(runtime_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(f"{runtime_path.relative_to(REPO_ROOT)}: unreadable runtime state: {exc}")
        else:
            leaked = sorted(_RETIRED_RUNTIME_IDENTITY_KEYS.intersection(runtime_state))
            if leaked:
                issues.append(
                    f"{runtime_path.relative_to(REPO_ROOT)}: duplicated execution identity keys "
                    + ", ".join(leaked)
                )
    return issues


def _execution_work_package_issues(entry: Path) -> list[str]:
    """Validate exactly one runtime work package."""
    issues: list[str] = []
    manifest = entry / "execution_manifest.json"
    if not manifest.is_file():
        issues.append(f"{entry.relative_to(REPO_ROOT)}: execution_manifest.json missing")
    for child in entry.iterdir():
        if child.name not in _ROOT_ALLOWED:
            issues.append(f"{child.relative_to(REPO_ROOT)}: not allowed in an execution work package")
    issues.extend(_identity_issues(entry))
    issues.extend(_frozen_target_issues(entry))
    issues.extend(_object_stage_issues(entry / "entities"))
    issues.extend(_object_stage_issues(entry / "posts"))
    return issues


def content_execution_layout_issues(*, execution_id: str | None = None) -> list[str]:
    """Validate either every live work package or one explicitly named package.

    Repository gates own the global scan. A release-readiness decision owns only
    its immutable execution package, so disposable test output cannot alter an
    unrelated production execution's verdict.
    """
    issues: list[str] = []
    for rel in _RETIRED_SOURCE_DIRS:
        path = REPO_ROOT / "quwoquan_data" / rel
        if path.exists():
            issues.append(f"quwoquan_data/{rel}: retired; reusable inputs must use families/prompts/templates/schema")
    for rel in _RETIRED_RUNTIME_PATHS:
        path = REPO_ROOT / rel
        if path.exists():
            issues.append(f"{rel}: retired runtime path; use .qwq_output/data/tasks/<executionId>")
    if execution_id is not None:
        if not is_execution_id(execution_id):
            return [*issues, f"invalid executionId: {execution_id}"]
        entry = DATA_EXECUTIONS_ROOT / execution_id
        if not entry.is_dir():
            return [*issues, f"{entry.relative_to(REPO_ROOT)}: execution work package does not exist"]
        return [*issues, *_execution_work_package_issues(entry)]
    if not DATA_EXECUTIONS_ROOT.exists():
        return issues
    for entry in sorted(DATA_EXECUTIONS_ROOT.iterdir()):
        if not entry.is_dir():
            issues.append(f"{entry.relative_to(REPO_ROOT)}: tasks root only allows execution directories")
            continue
        if not is_execution_id(entry.name):
            issues.append(f"{entry.relative_to(REPO_ROOT)}: invalid executionId directory")
            continue
        issues.extend(_execution_work_package_issues(entry))
    return issues


def main() -> int:
    issues = content_execution_layout_issues()
    if issues:
        print("[verify_content_execution_layout] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_content_execution_layout] OK")
    return 0
