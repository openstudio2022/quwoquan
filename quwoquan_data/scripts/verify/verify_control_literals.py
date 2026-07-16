#!/usr/bin/env python3
"""Reject unowned control literals in the two-province execution chain."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from core.control_types import EXECUTION_MILESTONES
from core.paths import DATA_ROOT, REPO_ROOT
from core.runtime_policy import load_runtime_policy
from content.execution.recipe import GEO_HOMEPAGE_RECIPE, load_recipe
from content.release.canonical.rollout_contract import load_rollout_contract


SCRIPTS_ROOT = DATA_ROOT / "scripts"
TYPE_OWNER = SCRIPTS_ROOT / "core/control_types.py"
TYPE_OWNER_LABEL = "quwoquan_data/scripts/core/control_types.py"
CONTROL_TYPES = {
    "AgentProvider", "ContentType", "DeploymentEnvironment", "ExecutionStage",
    "ReadinessMode", "ReplacementPolicy", "RolloutMilestone",
    "RuntimeEnvironment", "SelectionPolicy", "StageKind", "StageStatus",
}
CONTROL_CHOICE_VALUES = {
    *(item.value for item in EXECUTION_MILESTONES),
    "alpha", "beta", "gamma", "prod",
    "auto", "checkpoint", "done", "waiting", "failed", "skipped",
}
RUNTIME_CONTROL_NAME = re.compile(
    r"(?:TIMEOUT|RETRY|RETRIES|WORKERS|CONCURRENCY|STAGGER|ATTEMPTS|WAVES)$",
    re.IGNORECASE,
)
RUNTIME_ENV_NAME = re.compile(
    r"(?:TIMEOUT|RETRY|WORKER|CONCURRENCY|STAGGER|BUDGET|THRESHOLD|ATTEMPT|WAVE)"
)
ROLLOUT_SCALE_LITERALS = {922, 1977, 2899}
ROLLOUT_BATCH_LITERALS = {100, 320, 500, 1376}
ENVIRONMENT_VALUES = {"alpha", "beta", "gamma", "prod"}
MILESTONE_VALUES = {item.value for item in EXECUTION_MILESTONES}
LEGACY_PATTERNS = (
    re.compile(r"publish/v\d+"),
    re.compile(r"publish_version_root|publish_active_version"),
    re.compile(r"chuanxi", re.IGNORECASE),
    re.compile(r"四川旅行_v5|泰国旅行_v5|欧洲旅行_v5|_v5\b"),
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
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    for node in ast.walk(tree):
        if (
            label.startswith((
                "quwoquan_data/scripts/content/",
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
                    and argument.arg.lower() in {
                        "timeout", "timeout_seconds", "retries", "max_retries",
                        "retry_limit", "backoff_seconds", "sleep_seconds",
                        "stagger_seconds",
                    }
                ):
                    issues.append(
                        f"{label}:{node.lineno}: runtime control default {argument.arg} belongs to runtime policy"
                    )
        if isinstance(node, ast.ClassDef) and node.name in CONTROL_TYPES and label != TYPE_OWNER_LABEL:
            issues.append(f"{label}:{node.lineno}: {node.name} must be owned by core/control_types.py")
        if not isinstance(node, ast.Call):
            if (
                label.startswith("quwoquan_data/scripts/content/execution/")
                and isinstance(node, (ast.If, ast.While, ast.IfExp, ast.Assert))
                and _contains_string_membership(node.test)
                and _looks_like_message_control(node.test)
            ):
                issues.append(
                    f"{label}:{node.lineno}: issue control flow must use DataIssueCode/RecoveryAction, not message substrings"
                )
            if (
                label.startswith("quwoquan_data/scripts/content/execution/")
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
                    and value.value in ROLLOUT_BATCH_LITERALS
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
                and node.value in ROLLOUT_SCALE_LITERALS
                and label.startswith("quwoquan_data/scripts/")
            ):
                issues.append(
                    f"{label}:{node.lineno}: rollout scale belongs to rollout contract"
                )
            continue
        call_name = _qualified_name(node.func)
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
            for keyword in node.keywords:
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
                for token in RETIRED_WORKFLOW_TOKENS:
                    if token in line:
                        issues.append(
                            f"{label}:{lineno}: retired mutable-target/partial-delivery contract {token}"
                        )

    recipe = load_recipe(GEO_HOMEPAGE_RECIPE)
    forbidden_recipe_keys = {
        "limit", "reserveRatio", "targetObjectCount", "dailyTarget", "target",
        "maxWorkers", "startupTimeoutSeconds", "downloadPrefetchConcurrency",
        "authRetryLimit", "authRetryDelaySeconds", "noProgressRoundLimit",
    }
    for section_name in ("selection", "contract", "execution", "readiness"):
        section = recipe.get(section_name) or {}
        for key in sorted(set(section) & forbidden_recipe_keys):
            issues.append(
                f"recipe {GEO_HOMEPAGE_RECIPE}: {section_name}.{key} belongs to rollout/runtime policy"
            )
    try:
        load_runtime_policy(str(recipe.get("runtimeProfile") or ""))
        contract = load_rollout_contract()
    except (OSError, TypeError, ValueError) as exc:
        issues.append(f"control truth source invalid: {exc}")
    else:
        if tuple(contract.milestone_batch_targets) != EXECUTION_MILESTONES:
            issues.append("rollout milestone keys drift from shared RolloutMilestone")
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
