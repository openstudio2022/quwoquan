#!/usr/bin/env python3
"""Fail closed on content execution work-package drift."""
from __future__ import annotations

import sys
from pathlib import Path
import json

import yaml

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import (
    DATA_EXECUTIONS_ROOT,
    EXECUTION_ROOT_ALLOWED_ENTRIES,
    OBJECT_STAGES,
    REPO_ROOT,
    is_execution_id,
)
from content.execution.execution_terminal import (
    InvalidTerminalExecutionEvidenceError,
    load_terminal_execution_evidence,
)
from content.execution.spec_contract import ExecutionSpec
from content.execution.store import load_spec
from content.execution.workspace import load_execution_manifest, load_frozen_target_set


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


def _is_execution_work_package_root(path: Path) -> bool:
    """用 canonical execution identity 或根 manifest 识别工作包。"""
    return is_execution_id(path.name) or (path / "execution_manifest.json").exists()


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _identity_issues(execution_root: Path) -> list[str]:
    issues: list[str] = []

    def walk(value: object, path: str, source: Path) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _RETIRED_IDENTITY_KEYS:
                    issues.append(
                        f"{_display_path(source)}:{path}.{key}: retired identity; use executionId"
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
            issues.append(f"{_display_path(source)}: unreadable structured evidence: {exc}")
            continue
        for value in values:
            walk(value, "$", source)
    return issues


def _object_stage_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for stage in root.rglob("1.download"):
        object_root = stage.parent
        missing = [name for name in OBJECT_STAGES if not (object_root / name).is_dir()]
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
        return [f"{_display_path(execution_root)}: invalid execution identity contract: {exc}"]
    if target_set.get("selectionPolicy") != "frozen":
        issues.append(f"{_display_path(execution_root)}: target-set selectionPolicy must be frozen")
    if manifest.get("requestRef") != "0.plan/request.json":
        issues.append(f"{_display_path(execution_root)}: manifest requestRef must be 0.plan/request.json")
    if manifest.get("targetSetRef") != "0.plan/target_set.json":
        issues.append(f"{_display_path(execution_root)}: manifest targetSetRef must be 0.plan/target_set.json")
    targets = target_set.get("targets")
    if not isinstance(targets, list):
        return [*issues, f"{_display_path(execution_root)}: target set targets must be an array"]
    frozen_by_name = {
        target.get("name"): target
        for target in targets
        if isinstance(target, dict) and isinstance(target.get("name"), str)
    }
    if len(frozen_by_name) != len(targets):
        issues.append(f"{_display_path(execution_root)}: target set names must be unique objects")
    spec_names = {target.name for target in execution_spec.scope.coverage_targets}
    if set(frozen_by_name) != spec_names:
        issues.append(
            f"{_display_path(execution_root)}: execution spec and frozen target set names differ"
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
                f"{_display_path(execution_root)}: {spec_target.name} qualifiedHomepageSource "
                "must exactly match the immutable execution spec"
            )
    carriers = [carrier.value for carrier in execution_spec.content.carriers]
    carrier = carriers[0] if len(carriers) == 1 else None
    if carrier is None:
        issues.append(
            f"{_display_path(execution_root)}: execution spec must freeze exactly one content carrier"
        )
    for target in targets:
        if not isinstance(target, dict):
            issues.append(f"{_display_path(execution_root)}: frozen target must be an object")
            continue
        parts = str(target.get("entityType") or "").strip("/").split("/")
        name = str(target.get("name") or "").strip()
        if len(parts) != 2 or not name:
            issues.append(f"{_display_path(execution_root)}: invalid frozen target {target}")
            continue
        if carrier is None:
            continue
        # DEC-027：对象根按载体分根 fail closed，工作包与 canonical 坐标同构。
        if carrier == "homepage":
            object_root = execution_root / "entities" / parts[0] / parts[1] / name
        else:
            angle = str(target.get("publishAngle") or "").strip()
            title = str(target.get("publishTitle") or "").strip()
            seq = target.get("publishSeq") or 1
            if not angle or not title:
                issues.append(
                    f"{_display_path(execution_root)}: {name} post carrier target "
                    "requires frozen publishAngle/publishTitle"
                )
                continue
            object_root = execution_root / "posts" / carrier / angle / title / str(seq)
        missing = [stage for stage in OBJECT_STAGES if not (object_root / stage).is_dir()]
        if missing:
            issues.append(
                f"{object_root.relative_to(DATA_EXECUTIONS_ROOT)}: frozen target missing stages "
                + ", ".join(missing)
            )
    if carrier is not None:
        wrong_root = (
            execution_root / "posts"
            if carrier == "homepage"
            else execution_root / "entities"
        )
        for stage_dir in wrong_root.rglob("1.download"):
            issues.append(
                f"{stage_dir.parent.relative_to(DATA_EXECUTIONS_ROOT)}: "
                f"object is outside the {carrier} carrier root (DEC-027)"
            )
    runtime_path = execution_root / "_shared/runtime_state.json"
    if runtime_path.is_file():
        try:
            runtime_state = json.loads(runtime_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(f"{_display_path(runtime_path)}: unreadable runtime state: {exc}")
        else:
            leaked = sorted(_RETIRED_RUNTIME_IDENTITY_KEYS.intersection(runtime_state))
            if leaked:
                issues.append(
                    f"{_display_path(runtime_path)}: duplicated execution identity keys "
                    + ", ".join(leaked)
                )
    return issues


def _execution_work_package_issues(entry: Path) -> list[str]:
    """Validate exactly one runtime work package."""
    issues: list[str] = []
    manifest = entry / "execution_manifest.json"
    if not manifest.is_file():
        issues.append(f"{_display_path(entry)}: execution_manifest.json missing")
    for child in entry.iterdir():
        if child.name not in EXECUTION_ROOT_ALLOWED_ENTRIES:
            issues.append(f"{_display_path(child)}: not allowed in an execution work package")
    issues.extend(_identity_issues(entry))
    issues.extend(_frozen_target_issues(entry))
    issues.extend(_object_stage_issues(entry / "entities"))
    issues.extend(_object_stage_issues(entry / "posts"))
    return issues


def _terminal_evidence(
    entry: Path,
    *,
    issues: list[str],
) -> tuple[object | None, bool]:
    try:
        return load_terminal_execution_evidence(entry), False
    except InvalidTerminalExecutionEvidenceError as exc:
        issues.append(
            f"{_display_path(entry)}: invalid terminal execution evidence: {exc}"
        )
        return None, True
    except (OSError, TypeError, ValueError) as exc:
        issues.append(
            f"{_display_path(entry)}: invalid terminal execution evidence: {exc}"
        )
        return None, False


def content_execution_layout_issues(
    *,
    execution_id: str | None = None,
    allow_succeeded_terminal: bool = False,
) -> list[str]:
    """Validate either every live work package or one explicitly named package.

    Repository gates own the global scan. A release-readiness decision owns only
    its immutable execution package, so disposable test output cannot alter an
    unrelated production execution's verdict. Readiness may validate a succeeded
    terminal package without making that package resumable.
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
            return [*issues, f"{_display_path(entry)}: execution work package does not exist"]
        terminal, invalid_terminal = _terminal_evidence(entry, issues=issues)
        if invalid_terminal:
            return issues
        if terminal is not None and not (
            allow_succeeded_terminal and terminal.decision == "succeeded"
        ):
            issues.append(
                f"{_display_path(entry)}: execution is protected and non-resumable; create retryOf"
            )
            return issues
        return [*issues, *_execution_work_package_issues(entry)]
    if not DATA_EXECUTIONS_ROOT.exists():
        return issues
    for entry in sorted(DATA_EXECUTIONS_ROOT.iterdir()):
        if not entry.is_dir():
            issues.append(f"{_display_path(entry)}: tasks root only allows execution directories")
            continue
        if not _is_execution_work_package_root(entry):
            continue
        terminal, invalid_terminal = _terminal_evidence(entry, issues=issues)
        if invalid_terminal or terminal is not None:
            continue
        issues.extend(_execution_work_package_issues(entry))
    return issues


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="verify_content_execution_layout")
    parser.add_argument("--execution-id", default=None)
    args = parser.parse_args(argv)
    issues = content_execution_layout_issues(execution_id=args.execution_id)
    if issues:
        print("[verify_content_execution_layout] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_content_execution_layout] OK")
    return 0
