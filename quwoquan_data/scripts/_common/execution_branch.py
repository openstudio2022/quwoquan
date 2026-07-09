"""Single-source execution branch helpers for commercial content runs."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

EXECUTION_BRANCH_ENV = "QWQ_CONTENT_SUPPLY_EXECUTION_BRANCH"
HOMEPAGE_ONLY_EXECUTION_BRANCH_ENV = "QWQ_HOMEPAGE_ONLY_EXECUTION_BRANCH"
DEFAULT_HOMEPAGE_ONLY_EXECUTION_BRANCH = "feature/homepage-commercial-lane"


def _quota_int(spec: Mapping[str, Any] | None, key: str) -> int:
    content = (spec or {}).get("content") if isinstance(spec, Mapping) else {}
    quotas = content.get("quotas") if isinstance(content, Mapping) else {}
    quotas = quotas if isinstance(quotas, Mapping) else {}
    try:
        return int(quotas.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def is_homepage_only_spec(spec: Mapping[str, Any] | None = None) -> bool:
    return (
        _quota_int(spec, "entityHomepagesPerTarget") > 0
        and _quota_int(spec, "entityArticlesPerTarget") <= 0
        and _quota_int(spec, "imageWorksPerTarget") <= 0
        and _quota_int(spec, "routeArticles") <= 0
    )


def frozen_execution_branch(spec: Mapping[str, Any] | None = None) -> str:
    if not is_homepage_only_spec(spec):
        return ""
    return str(
        os.environ.get(HOMEPAGE_ONLY_EXECUTION_BRANCH_ENV)
        or DEFAULT_HOMEPAGE_ONLY_EXECUTION_BRANCH
    ).strip()


def current_git_branch(*, cwd: str | Path | None = None) -> str:
    root = str(Path(cwd).resolve()) if cwd else None
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return ""
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def configured_execution_branch(spec: Mapping[str, Any] | None = None) -> str:
    workflow = (spec or {}).get("workflowPolicy") if isinstance(spec, Mapping) else {}
    workflow = workflow if isinstance(workflow, Mapping) else {}
    return str(workflow.get("executionBranch") or "").strip()


def resolve_execution_branch(
    spec: Mapping[str, Any] | None = None,
    *,
    cwd: str | Path | None = None,
) -> str:
    configured = configured_execution_branch(spec)
    if configured:
        return configured
    frozen = frozen_execution_branch(spec)
    if frozen:
        return frozen
    env_value = str(os.environ.get(EXECUTION_BRANCH_ENV) or "").strip()
    if env_value:
        return env_value
    return current_git_branch(cwd=cwd)


def stamp_execution_branch(
    spec: dict[str, Any],
    *,
    cwd: str | Path | None = None,
) -> str:
    workflow = spec.setdefault("workflowPolicy", {})
    if not isinstance(workflow, dict):
        raise ValueError("workflowPolicy must be a mapping")
    branch = str(workflow.get("executionBranch") or "").strip()
    if branch:
        return branch
    branch = resolve_execution_branch(spec, cwd=cwd)
    if branch:
        workflow["executionBranch"] = branch
    return branch


def execution_branch_payload(
    spec: Mapping[str, Any] | None = None,
    *,
    cwd: str | Path | None = None,
) -> dict[str, str]:
    return {
        "configuredExecutionBranch": configured_execution_branch(spec),
        "frozenExecutionBranch": frozen_execution_branch(spec),
        "envExecutionBranch": str(os.environ.get(EXECUTION_BRANCH_ENV) or "").strip(),
        "currentGitBranch": current_git_branch(cwd=cwd),
        "resolvedExecutionBranch": resolve_execution_branch(spec, cwd=cwd),
    }


def execution_branch_issues(
    spec: Mapping[str, Any] | None = None,
    *,
    cwd: str | Path | None = None,
) -> list[str]:
    payload = execution_branch_payload(spec, cwd=cwd)
    expected = payload["resolvedExecutionBranch"]
    actual = payload["currentGitBranch"]
    issues: list[str] = []
    if not expected:
        issues.append(
            "workflowPolicy.executionBranch is unresolved; set QWQ_CONTENT_SUPPLY_EXECUTION_BRANCH "
            "or run from the intended git branch before commercial execution"
        )
        return issues
    if not actual:
        issues.append("current git branch is unavailable; cannot verify workflowPolicy.executionBranch")
        return issues
    if actual != expected:
        issues.append(
            f"workflowPolicy.executionBranch={expected} but current git branch is {actual}; "
            "switch to the single commercial execution branch before running"
        )
    return issues


__all__ = [
    "DEFAULT_HOMEPAGE_ONLY_EXECUTION_BRANCH",
    "EXECUTION_BRANCH_ENV",
    "HOMEPAGE_ONLY_EXECUTION_BRANCH_ENV",
    "configured_execution_branch",
    "current_git_branch",
    "execution_branch_issues",
    "execution_branch_payload",
    "frozen_execution_branch",
    "is_homepage_only_spec",
    "resolve_execution_branch",
    "stamp_execution_branch",
]
