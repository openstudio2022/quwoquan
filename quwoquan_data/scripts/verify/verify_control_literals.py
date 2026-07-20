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
    ReviewItemKind,
    ReviewJudgment,
    ReviewOverride,
    ReviewPublishState,
)
from core.media_processing_policy import media_processing_policy
from core.paths import DATA_ROOT, REPO_ROOT
from core.runtime_policy import load_runtime_policy
from content.execution.recipe import HOMEPAGE_RECIPE, load_recipe
from content.release.canonical.rollout_contract import load_rollout_contract
from governance.coverage.cold_start_supply import load_cold_start_supply_policy
from content.review.policy import review_policy
from verify.control_literal_ast import (
    contains_string_membership,
    document_field,
    looks_like_message_control,
    qualified_name,
    uses_closed_type,
    uses_execution_state_status,
    uses_queue_job_state,
)
from verify.control_literal_text import text_control_literal_issues

SCRIPTS_ROOT = DATA_ROOT / "scripts"
TYPE_OWNER = SCRIPTS_ROOT / "core/control_types.py"
TYPE_OWNER_LABEL = "quwoquan_data/scripts/core/control_types.py"
CONTROL_TYPES = {
    "AgentProvider", "AppUatDataSource", "AppUatStatus", "ContentImportStatus",
    "ContentType", "DeploymentEnvironment", "ExecutionStage",
    "ExecutionSpecStatus", "ExecutionStateStatus", "ImageAssetStrategy",
    "ImageCountPolicy", "ModalityContract",
    "QueueBackend", "QueueFailureKind", "QueueJobStage", "QueueJobState", "QueueTimelineEvent",
    "ReleaseDeletePolicy", "ReleaseRunKind", "ReleaseRunStatus", "ReleaseSourceOwner", "ReleaseSyncMode",
    "ManagedAgentCheckpointStatus", "ReadinessMode", "ReplacementPolicy", "RolloutMilestone",
    "ReviewItemKind", "ReviewJudgment", "ReviewOverride", "ReviewPublishState",
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
    queue_module = label.startswith(
        "quwoquan_data/scripts/content/execution/queue/"
    )
    queue_core_module = label.endswith("content/execution/queue/core.py")
    queue_codec_module = label.endswith((
        "content/execution/queue/model.py",
        "content/execution/queue/jobs.py",
    ))
    review_module = label.startswith("quwoquan_data/scripts/content/review/")
    review_ledger_module = label.endswith("content/review/ledger.py")
    post_module = label.startswith("quwoquan_data/scripts/content/post/")
    rollout_attestation_module = label.endswith(
        "content/release/canonical/rollout_attestation.py"
    )
    typed_agent_outcome_module = label.endswith((
        "content/execution/agent/agent_runner.py",
        "content/execution/agent/agent_worker.py",
        "content/execution/agent/managed_checkpoint.py",
        "content/execution/controller/homepage_author_finalization.py",
        "content/execution/controller/stage_download_build.py",
    ))
    typed_agent_history_module = label.endswith((
        "content/execution/agent/agent_checkpoint.py",
        "content/execution/agent/agent_managed.py",
        "content/execution/agent/managed_checkpoint.py",
        "content/execution/controller/completion.py",
        "content/execution/controller/control.py",
        "content/execution/controller/homepage_author_evidence.py",
        "content/execution/controller/metrics.py",
        "content/execution/controller/token_ledger.py",
        "content/execution/readiness_audit.py",
        "content/homepage/homepage_review.py",
    ))
    agent_history_boundary_module = label.endswith("content/execution/agent/history.py")
    for node in ast.walk(tree):
        if (
            typed_agent_history_module
            and not agent_history_boundary_module
            and isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in {"state", "audit_state"}
            and node.attr in {"agent_run_history", "last_agent_run"}
            and isinstance(node.ctx, ast.Load)
        ):
            issues.append(
                f"{label}:{node.lineno}: managed-agent history must be decoded by agent/history.py"
            )
        if queue_module and not queue_core_module and not queue_codec_module:
            if document_field(node, "state"):
                if isinstance(node, ast.Subscript) and isinstance(
                    parents.get(node), (ast.Assign, ast.AnnAssign)
                ):
                    assignment = parents[node]
                    value = assignment.value
                    if not uses_queue_job_state(value):
                        issues.append(
                            f"{label}:{node.lineno}: queue state writes must use QueueJobState"
                        )
                elif isinstance(node, ast.Call):
                    issues.append(
                        f"{label}:{node.lineno}: queue state must be decoded by queue_job_state() before control flow"
                    )
            if document_field(node, "queueBackend") and isinstance(node, ast.Call):
                issues.append(
                    f"{label}:{node.lineno}: queue backend must be decoded by queue_job_backend() before control flow"
                )
        if review_module and not review_ledger_module:
            if isinstance(node, ast.Call) and any(
                document_field(node, field)
                for field in ("publishState", "agentJudgment", "humanJudgment", "humanOverride")
            ):
                issues.append(
                    f"{label}:{node.lineno}: review verdict fields must be decoded by ReviewVerdict before control flow"
                )
        if review_module and isinstance(node, ast.ClassDef) and node.name == "ReviewVerdict" and not review_ledger_module:
            issues.append(
                f"{label}:{node.lineno}: ReviewVerdict must be owned by content/review/ledger.py"
            )
        if (
            rollout_attestation_module
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id
            in {
                "header",
                "desired",
                "payload",
                "result",
                "importer",
                "cases",
                "api",
                "app",
                "rollback",
                "receipt",
            }
        ):
            issues.append(
                f"{label}:{node.lineno}: rollout attestation evidence must use typed receipts, not wire get()"
            )
        if (
            typed_agent_outcome_module
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"outcome", "job_outcome"}
        ):
            issues.append(
                f"{label}:{node.lineno}: managed-agent control flow must use AgentRunOutcome attributes, not wire get()"
            )
        if (
            typed_agent_outcome_module
            and isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in {"outcome", "job_outcome"}
        ):
            issues.append(
                f"{label}:{node.lineno}: managed-agent control flow must use AgentRunOutcome attributes, not wire subscripts"
            )
        if execution_module and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                if argument.arg not in {"state", "audit_state"}:
                    continue
                annotation = qualified_name(argument.annotation) if argument.annotation else ""
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
                if not uses_execution_state_status(value):
                    issues.append(
                        f"{label}:{node.lineno}: workflow status must store ExecutionStateStatus, not wire values"
                    )
        if (
            execution_module
            and isinstance(node, ast.ClassDef)
            and node.name in {"ExecutionSpec", "ExecutionState", "ExecutionRuntimeState"}
            and any(qualified_name(base).endswith("Mapping") for base in node.bases)
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
                and contains_string_membership(node.test)
                and looks_like_message_control(node.test)
            ):
                issues.append(
                    f"{label}:{node.lineno}: issue control flow must use DataIssueCode/RecoveryAction, not message substrings"
                )
            if (
                (execution_module or post_module)
                and isinstance(node, ast.ExceptHandler)
                and (
                    node.type is None
                    or qualified_name(node.type) in {"Exception", "BaseException"}
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
                module_control_constant = isinstance(parents.get(node), ast.Module)
                if (
                    module_control_constant
                    and isinstance(value, ast.Constant)
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
                parent = parents.get(node)
                target_names: list[str] = []
                if isinstance(parent, ast.Assign):
                    target_names = [
                        target.id
                        for target in parent.targets
                        if isinstance(target, ast.Name)
                    ]
                elif isinstance(parent, ast.AnnAssign) and isinstance(
                    parent.target, ast.Name
                ):
                    target_names = [parent.target.id]
                lowered = [name.lower() for name in target_names]
                if any(
                    "rollout" in name
                    or "completion" in name
                    or "coverage_target" in name
                    or "target_count" in name
                    or "targetcount" in name
                    for name in lowered
                ):
                    issues.append(
                        f"{label}:{node.lineno}: rollout scale belongs to rollout contract"
                    )
            continue
        call_name = qualified_name(node.func)
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
                if index >= len(node.args) or not uses_closed_type(node.args[index], type_name):
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
    issues.extend(text_control_literal_issues(source, label=label))
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
            issues.extend(text_control_literal_issues(text, label=label))

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
        policy = review_policy()
        contract = load_rollout_contract()
    except (OSError, TypeError, ValueError) as exc:
        issues.append(f"control truth source invalid: {exc}")
    else:
        if tuple(item.milestone for item in contract.milestones) != EXECUTION_MILESTONES:
            issues.append("rollout milestone keys drift from shared RolloutMilestone")
        if (
            policy.policy_id != "review"
            or policy.minimum_score > policy.maximum_score
            or not policy.quality_score_bands
        ):
            issues.append("review policy contract is invalid")
    for review_type in (
        ReviewItemKind,
        ReviewJudgment,
        ReviewOverride,
        ReviewPublishState,
    ):
        if not tuple(review_type):
            issues.append(f"review closed type is empty: {review_type.__name__}")
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
