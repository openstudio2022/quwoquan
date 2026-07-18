#!/usr/bin/env python3
"""Reject unowned control literals in the two-province execution chain."""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from core.control_types import (
    EXECUTION_MILESTONES,
    DeploymentEnvironment,
    ExecutionStateStatus,
)
from core.media_processing_policy import media_processing_policy
from core.paths import DATA_ROOT, REPO_ROOT
from core.runtime_policy import load_runtime_policy
from content.execution.recipe import HOMEPAGE_RECIPE, load_recipe
from content.release.canonical.rollout_contract import load_rollout_contract
from governance.coverage.cold_start_supply import load_cold_start_supply_policy


SCRIPTS_ROOT = DATA_ROOT / "scripts"
TYPE_OWNER = SCRIPTS_ROOT / "core/control_types.py"
TYPE_OWNER_LABEL = "quwoquan_data/scripts/core/control_types.py"
CONTROL_TYPES = {
    "AgentProvider", "ContentType", "DeploymentEnvironment", "ExecutionStage",
    "ExecutionSpecStatus", "ExecutionStateStatus", "ImageAssetStrategy",
    "ImageCountPolicy", "ModalityContract",
    "ReadinessMode", "ReplacementPolicy", "RolloutMilestone",
    "RuntimeEnvironment", "SelectionPolicy", "StageKind", "StageStatus",
}
CONTROL_CHOICE_VALUES = {
    *(item.value for item in EXECUTION_MILESTONES),
    "auto", "checkpoint", "done", "waiting", "failed", "skipped",
    *(item.value for item in ExecutionStateStatus),
    *(item.value for item in DeploymentEnvironment),
}
RUNTIME_CONTROL_NAME = re.compile(
    r"(?:TIMEOUT|RETRY|RETRIES|WORKERS|CONCURRENCY|STAGGER|ATTEMPTS|WAVES)$",
    re.IGNORECASE,
)
RUNTIME_ENV_NAME = re.compile(
    r"(?:TIMEOUT|RETRY|WORKER|CONCURRENCY|STAGGER|BUDGET|THRESHOLD|ATTEMPT|WAVE)"
)
RUNTIME_ARGUMENT_NAMES = {
    "concurrency",
    "max_workers",
    "retries",
    "retry_limit",
    "startup_timeout_seconds",
    "stagger_seconds",
    "timeout",
    "timeout_seconds",
}
ENVIRONMENT_VALUES = frozenset(item.value for item in DeploymentEnvironment)
MILESTONE_VALUES = {item.value for item in EXECUTION_MILESTONES}
LEGACY_PATTERNS = (
    re.compile(r"publish/v\d+"),
    re.compile(r"publish_version_root|publish_active_version"),
    re.compile(r"chuanxi", re.IGNORECASE),
    re.compile(r"四川旅行_v5|泰国旅行_v5|欧洲旅行_v5|_v5\b"),
)
VERSIONED_CONTRACT_PATTERN = re.compile(
    r"\b(?:quwoquan_(?:data|service)|quwoquan\.[A-Za-z0-9_.-]+)"
    r"[A-Za-z0-9_.-]*(?:/[0-9]+|\.v[0-9]+)\b"
)
VERSIONED_POLICY_PATTERN = re.compile(
    r"\b(?:encyclopedia-primary|execution-source-qualification|"
    r"execution-model-readiness)-v[0-9]+\b"
)
VERSION_FIELD_PATTERN = re.compile(
    r"(?:[\"'](?:schemaVersion|contractVersion)[\"']\s*:|"
    r"^(?:\s*)(?:schemaVersion|contractVersion)\s*:)",
    re.IGNORECASE,
)
RETIRED_WORKFLOW_TOKENS = (
    "abandoned" + "Objects",
    "abandonedContent" + "Objects",
    "replacement" + "Objects",
    "partialDelivery" + "Reports",
    "targetSetChange" + "Events",
    "targetSetInvalidated" + "Stages",
    "targetSetRequiresRerun" + "From",
    "allowContentQuota" + "Shortfall",
    "allowQuota" + "Shortfall",
    "allowMinEntity" + "Shortfall",
    "best_effort_with_reasoned" + "_rejects",
    "partial_with_replacement" + "_report",
)
RETIRED_WORKFLOW_MODULES = {
    "target_" + "replacement.py",
    "target_" + "state.py",
    "target_" + "policy.py",
    "workflow_" + "abandonment.py",
}
WORKFLOW_STATE_MUTATORS = {"clear", "get", "pop", "setdefault", "update"}


@dataclass(frozen=True, slots=True)
class _RolloutControlValues:
    """Control numbers derived from the only rollout contract, never copied here."""

    batch_counts: frozenset[int]
    completion_counts: frozenset[int]

@lru_cache(maxsize=1)
def _rollout_control_values() -> _RolloutControlValues:
    contract = load_rollout_contract()
    batch_counts = frozenset(
        target.count
        for milestone in contract.milestones
        for target in milestone.batch_targets
    )
    final_milestone = contract.milestones[-1]
    final_province_counts = tuple(
        target.count for target in final_milestone.cumulative_targets
    )
    completion_counts = frozenset((*final_province_counts, sum(final_province_counts)))
    return _RolloutControlValues(batch_counts, completion_counts)


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _uses_closed_type(node: ast.AST, type_name: str) -> bool:
    qualified = _qualified_name(node)
    return qualified.startswith(f"{type_name}.") or (
        isinstance(node, ast.Call) and _qualified_name(node.func) == type_name
    )


def _uses_execution_state_status(node: ast.AST) -> bool:
    if isinstance(node, ast.IfExp):
        return _uses_execution_state_status(node.body) and _uses_execution_state_status(
            node.orelse
        )
    qualified = _qualified_name(node)
    return qualified.startswith("ExecutionStateStatus.") and not qualified.endswith(
        ".value"
    )


def _contains_string_membership(node: ast.AST) -> bool:
    return any(
        isinstance(candidate, ast.Compare)
        and any(isinstance(operator, (ast.In, ast.NotIn)) for operator in candidate.ops)
        and any(
            isinstance(value, ast.Constant) and isinstance(value.value, str)
            for value in ast.walk(candidate)
        )
        for candidate in ast.walk(node)
    )


def _looks_like_message_control(node: ast.AST) -> bool:
    names = {
        candidate.id.lower()
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Name)
    }
    attributes = {
        candidate.attr.lower()
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Attribute)
    }
    return bool(
        attributes & {"message", "issues"}
        or any(
            token in name
            for name in names
            for token in ("issue", "message", "reason", "combined")
        )
    )


def source_control_literal_issues(source: str, *, label: str) -> list[str]:
    try:
        tree = ast.parse(source, filename=label)
    except SyntaxError as exc:
        return [f"{label}:{exc.lineno}: invalid Python syntax"]
    issues: list[str] = []
    try:
        rollout_control_values = _rollout_control_values()
    except (OSError, TypeError, ValueError) as exc:
        return [f"control truth source invalid: {exc}"]
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    execution_module = label.startswith(
        "quwoquan_data/scripts/content/execution/"
    )
    for node in ast.walk(tree):
        if execution_module and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                if argument.arg not in {"state", "audit_state"}:
                    continue
                annotation = _qualified_name(argument.annotation) if argument.annotation else ""
                if annotation and not annotation.endswith("ExecutionStateTransition"):
                    issues.append(
                        f"{label}:{node.lineno}: workflow state parameter must use ExecutionStateTransition"
                    )
        if execution_module and isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id in {"state", "audit_state"}:
                issues.append(
                    f"{label}:{node.lineno}: workflow state must use typed attributes, not mapping subscripts"
                )
        if execution_module and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"state", "audit_state"}
                and node.func.attr in WORKFLOW_STATE_MUTATORS
            ):
                issues.append(
                    f"{label}:{node.lineno}: workflow state must use typed transitions, not mapping {node.func.attr}()"
                )
        if execution_module and isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if any(
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id in {"state", "audit_state"}
                and target.attr == "status"
                for target in targets
            ):
                if not _uses_execution_state_status(value):
                    issues.append(
                        f"{label}:{node.lineno}: workflow status must store ExecutionStateStatus, not wire values"
                    )
        if (
            execution_module
            and isinstance(node, ast.ClassDef)
            and node.name in {"ExecutionSpec", "ExecutionState", "ExecutionRuntimeState"}
            and any(_qualified_name(base).endswith("Mapping") for base in node.bases)
        ):
            issues.append(
                f"{label}:{node.lineno}: execution documents must use explicit frozen fields, not Mapping inheritance"
            )
        if (
            label.startswith((
                "quwoquan_data/scripts/content/",
                "quwoquan_data/scripts/core/",
                "quwoquan_data/scripts/governance/",
            ))
            and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            positional = [*node.args.posonlyargs, *node.args.args]
            positional_defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
            default_pairs = [*zip(positional, positional_defaults), *zip(node.args.kwonlyargs, node.args.kw_defaults)]
            for argument, default in default_pairs:
                if (
                    default is not None
                    and isinstance(default, ast.Constant)
                    and isinstance(default.value, (int, float))
                    and argument.arg.lower() in RUNTIME_ARGUMENT_NAMES | {
                        "backoff_seconds", "max_retries", "sleep_seconds",
                    }
                ):
                    issues.append(
                        f"{label}:{node.lineno}: runtime control default {argument.arg} belongs to runtime policy"
                    )
        if isinstance(node, ast.ClassDef) and node.name in CONTROL_TYPES and label != TYPE_OWNER_LABEL:
            issues.append(f"{label}:{node.lineno}: {node.name} must be owned by core/control_types.py")
        if not isinstance(node, ast.Call):
            if (
                execution_module
                and isinstance(node, (ast.Assign, ast.AnnAssign))
            ):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                if (
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and value.value in {item.value for item in ExecutionStateStatus}
                    and any(
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id in {"state", "audit_state"}
                        and isinstance(target.slice, ast.Constant)
                        and target.slice.value == "status"
                        for target in targets
                    )
                ):
                    issues.append(
                        f"{label}:{node.lineno}: execution state status must use ExecutionStateStatus"
                    )
            if (
                execution_module
                and isinstance(node, (ast.If, ast.While, ast.IfExp, ast.Assert))
                and _contains_string_membership(node.test)
                and _looks_like_message_control(node.test)
            ):
                issues.append(
                    f"{label}:{node.lineno}: issue control flow must use DataIssueCode/RecoveryAction, not message substrings"
                )
            if (
                execution_module
                and isinstance(node, ast.ExceptHandler)
                and (
                    node.type is None
                    or _qualified_name(node.type) in {"Exception", "BaseException"}
                )
                and any(isinstance(statement, ast.Pass) for statement in node.body)
            ):
                issues.append(
                    f"{label}:{node.lineno}: broad exception must become a typed issue, not pass silently"
                )
            if (
                label.startswith("quwoquan_data/scripts/content/")
                and isinstance(node, (ast.Assign, ast.AnnAssign))
                and isinstance(parents.get(node), (ast.Module, ast.ClassDef))
            ):
                value = node.value
                names = []
                if isinstance(node, ast.Assign):
                    names = [
                        target.id
                        for target in node.targets
                        if isinstance(target, ast.Name)
                    ]
                elif isinstance(node.target, ast.Name):
                    names = [node.target.id]
                lowered_names = [name.lower() for name in names]
                if (
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, (int, float))
                    and any(RUNTIME_CONTROL_NAME.search(name) for name in names)
                ):
                    issues.append(
                        f"{label}:{node.lineno}: runtime control number belongs to runtime policy"
                    )
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    if value.value in ENVIRONMENT_VALUES and any(
                        name == "env" or "environment" in name
                        for name in lowered_names
                    ):
                        issues.append(
                            f"{label}:{node.lineno}: environment literal must use DeploymentEnvironment"
                        )
                    if value.value in MILESTONE_VALUES and any(
                        "milestone" in name for name in lowered_names
                    ):
                        issues.append(
                            f"{label}:{node.lineno}: milestone literal must use RolloutMilestone"
                        )
                if (
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, int)
                    and value.value in rollout_control_values.batch_counts
                    and any(
                        name == "limit" or "target_count" in name or "targetcount" in name
                        for name in lowered_names
                    )
                ):
                    issues.append(
                        f"{label}:{node.lineno}: rollout batch size belongs to rollout contract"
                    )
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and node.value in rollout_control_values.completion_counts
                and label.startswith("quwoquan_data/scripts/")
            ):
                issues.append(
                    f"{label}:{node.lineno}: rollout scale belongs to rollout contract"
                )
            continue
        call_name = _qualified_name(node.func)
        if call_name == "getattr" and len(node.args) >= 3:
            attribute, default = node.args[1:3]
            if (
                isinstance(attribute, ast.Constant)
                and isinstance(attribute.value, str)
                and attribute.value.lower() in RUNTIME_ARGUMENT_NAMES
                and isinstance(default, ast.Constant)
                and isinstance(default.value, (int, float, str))
                and default.value not in (None, "")
            ):
                issues.append(
                    f"{label}:{node.lineno}: runtime getattr fallback {attribute.value} belongs to runtime policy"
                )
        if call_name in {"os.environ.get", "os.getenv"} and len(node.args) >= 2:
            key, default = node.args[:2]
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and RUNTIME_ENV_NAME.search(key.value)
                and isinstance(default, ast.Constant)
                and isinstance(default.value, str)
                and re.fullmatch(r"-?\d+(?:\.\d+)?", default.value)
            ):
                issues.append(
                    f"{label}:{node.lineno}: numeric runtime env fallback belongs to runtime policy"
                )
        if call_name.endswith("StageResult"):
            for index, type_name in ((0, "ExecutionStage"), (2, "StageStatus")):
                if index >= len(node.args) or not _uses_closed_type(node.args[index], type_name):
                    issues.append(
                        f"{label}:{node.lineno}: StageResult argument {index + 1} must use {type_name}"
                    )
            for keyword in node.keywords:
                if keyword.arg == "issues":
                    issues.append(
                        f"{label}:{node.lineno}: StageResult accepts typed issue_records only"
                    )
                if keyword.arg == "fallback_stage" and isinstance(keyword.value, ast.Constant):
                    issues.append(
                        f"{label}:{node.lineno}: fallback_stage must use ExecutionStage, not a string literal"
                    )
        if call_name.endswith("add_argument"):
            argument_names = {
                value.value.lstrip("-").replace("-", "_")
                for value in node.args
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            }
            for keyword in node.keywords:
                if (
                    keyword.arg == "default"
                    and argument_names & RUNTIME_ARGUMENT_NAMES
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value not in (None, "")
                ):
                    issues.append(
                        f"{label}:{node.lineno}: argparse runtime default belongs to runtime policy"
                    )
                if keyword.arg != "choices" or not isinstance(keyword.value, (ast.List, ast.Tuple, ast.Set)):
                    continue
                values = {
                    item.value
                    for item in keyword.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
                if values & CONTROL_CHOICE_VALUES:
                    issues.append(
                        f"{label}:{node.lineno}: argparse controlled choices must derive from closed enums/contracts"
                    )
    for lineno, line in enumerate(source.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if VERSION_FIELD_PATTERN.search(line):
            issues.append(
                f"{label}:{lineno}: explicit contract version field is forbidden; "
                "current data contracts are single-track"
            )
        if VERSIONED_CONTRACT_PATTERN.search(line) or VERSIONED_POLICY_PATTERN.search(line):
            issues.append(
                f"{label}:{lineno}: versioned data contract is forbidden; use the single unversioned contract"
            )
        if any(pattern.search(line) for pattern in LEGACY_PATTERNS):
            issues.append(f"{label}:{lineno}: retired regional/version hardcode")
        if label.startswith("quwoquan_data/scripts/governance/") and re.search(r"\[timeout:\d+\]", line):
            issues.append(f"{label}:{lineno}: provider query timeout belongs to runtime policy")
        for token in RETIRED_WORKFLOW_TOKENS:
            if token in line:
                issues.append(
                    f"{label}:{lineno}: retired mutable-target/partial-delivery contract {token}"
                )
    return issues


def control_literal_issues() -> list[str]:
    issues: list[str] = []
    for path in sorted(SCRIPTS_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts or path.resolve() == Path(__file__).resolve():
            continue
        label = path.relative_to(REPO_ROOT).as_posix()
        if path.name in RETIRED_WORKFLOW_MODULES:
            issues.append(f"{label}: retired workflow module must be deleted")
        issues.extend(source_control_literal_issues(path.read_text(encoding="utf-8"), label=label))

    for root in (DATA_ROOT / "schema", DATA_ROOT / "control_plane"):
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in {".json", ".yaml", ".yml"}:
                continue
            label = path.relative_to(REPO_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if VERSION_FIELD_PATTERN.search(line):
                    issues.append(
                        f"{label}:{lineno}: explicit contract version field is forbidden; "
                        "current data contracts are single-track"
                    )
                if VERSIONED_CONTRACT_PATTERN.search(line) or VERSIONED_POLICY_PATTERN.search(line):
                    issues.append(
                        f"{label}:{lineno}: versioned data contract is forbidden; use the single unversioned contract"
                    )
                for token in RETIRED_WORKFLOW_TOKENS:
                    if token in line:
                        issues.append(
                            f"{label}:{lineno}: retired mutable-target/partial-delivery contract {token}"
                        )

    recipe = load_recipe(HOMEPAGE_RECIPE)
    forbidden_recipe_keys = {
        "limit", "reserveRatio", "targetObjectCount", "dailyTarget", "target",
        "maxWorkers", "startupTimeoutSeconds", "downloadPrefetchConcurrency",
        "authRetryLimit", "authRetryDelaySeconds", "noProgressRoundLimit",
    }
    for section_name in ("selection", "contract", "execution", "readiness"):
        section = recipe.get(section_name) or {}
        for key in sorted(set(section) & forbidden_recipe_keys):
            issues.append(
                f"recipe {HOMEPAGE_RECIPE}: {section_name}.{key} belongs to rollout/runtime policy"
            )
    try:
        load_runtime_policy(str(recipe.get("runtimeProfile") or ""))
        media_processing_policy()
        load_cold_start_supply_policy()
        contract = load_rollout_contract()
    except (OSError, TypeError, ValueError) as exc:
        issues.append(f"control truth source invalid: {exc}")
    else:
        if tuple(item.milestone for item in contract.milestones) != EXECUTION_MILESTONES:
            issues.append("rollout milestone keys drift from shared RolloutMilestone")
    state_schema_path = DATA_ROOT / "schema/execution/execution_state.schema.json"
    try:
        state_schema = json.loads(state_schema_path.read_text(encoding="utf-8"))
        schema_statuses = tuple(
            state_schema["properties"]["status"]["enum"]
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        issues.append(f"execution state schema status contract invalid: {exc}")
    else:
        if schema_statuses != tuple(item.value for item in ExecutionStateStatus):
            issues.append("execution state schema statuses drift from ExecutionStateStatus")
    return issues


def main() -> int:
    issues = control_literal_issues()
    if issues:
        print("[verify_control_literals] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_control_literals] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
