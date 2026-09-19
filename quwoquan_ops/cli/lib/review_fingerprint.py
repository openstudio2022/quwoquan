"""Canonical Review plan fingerprint construction and path identity helpers."""
from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import subprocess
import sys
from pathlib import Path
from typing import Any

from .agent_governance_contract import contract_schema_version
from .evidence_fingerprint import (
    EvidenceFingerprintError,
    build_evidence_fingerprint,
    canonical_digest,
    normalize_repo_relative_path,
    snapshot_path,
    snapshot_paths,
    workspace_digests,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCES_DIR = REPO_ROOT / ".agents/skills/review/references"
REGISTRY_PATH = REFERENCES_DIR / "registry.yaml"
GRADING_PATH = REFERENCES_DIR / "grading.md"

_SOURCE_ROOT: ContextVar[Path | None] = ContextVar("review_source_repository", default=None)
_DEPENDENCY_ROOT: ContextVar[Path | None] = ContextVar("review_dependency_root", default=None)


def source_root(default: Path = REPO_ROOT) -> Path:
    return _SOURCE_ROOT.get() or default


def dependency_root(default: Path = REPO_ROOT) -> Path:
    return _DEPENDENCY_ROOT.get() or source_root(default)


def repository_inputs(function):
    """为 canonical 边界提供显式 source_repository/dependency_root，嵌套读取共享同一上下文。"""
    @wraps(function)
    def invoke(*args, source_repository=None, dependency_root=None, **kwargs):
        from .feature_tree import context
        requested = source_repository or _SOURCE_ROOT.get() or kwargs.get("repo_root") or kwargs.get("cwd") or REPO_ROOT
        source = Path(requested).absolute()
        dependencies = Path(dependency_root).absolute() if dependency_root is not None else (_DEPENDENCY_ROOT.get() or source)
        if source.is_symlink() or dependencies.is_symlink():
            raise EvidenceFingerprintError("Review root 不得为 symlink")
        source_token = _SOURCE_ROOT.set(source)
        dependency_token = _DEPENDENCY_ROOT.set(dependencies)
        try:
            with context.source_repository(source):
                return function(*args, **kwargs)
        finally:
            _DEPENDENCY_ROOT.reset(dependency_token)
            _SOURCE_ROOT.reset(source_token)
    return invoke


def snapshot(relative: str) -> dict[str, Any]:
    return snapshot_path(relative, repo_root=source_root())

def normalize_path(raw_path: str) -> str:
    return normalize_repo_relative_path(raw_path, source_root())

def head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root(),
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"

def merge_base_sha() -> str:
    for base in ("dev1.0", "main"):
        result = subprocess.run(
            ["git", "merge-base", "HEAD", base], cwd=source_root(),
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return head_sha()

def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()

def validate_git_range(value: dict[str, str], *, repo_root: Path) -> dict[str, str]:
    """只从真实 source Git 验证，不允许 transport root 代替源码仓库。"""
    from .agent_governance_contract import validate_declared_fields

    if not isinstance(value, dict):
        raise EvidenceFingerprintError("Review git_range 必须为 mapping")
    validate_declared_fields(value, "review_plan", "git_range_fields")
    for key, sha in value.items():
        if not isinstance(sha, str) or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", sha) is None:
            raise EvidenceFingerprintError(f"Review git_range.{key} 必须为 exact Git SHA")
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, check=False)
        if result.returncode:
            raise EvidenceFingerprintError(f"Review git_range Git 校验失败: {' '.join(args)}")
        return result.stdout.strip()
    if git("rev-parse", "HEAD") != value["head_sha"]:
        raise EvidenceFingerprintError("Review git_range HEAD 已 stale")
    if git("rev-parse", f"{value['head_sha']}^{{tree}}") != value["head_tree"]:
        raise EvidenceFingerprintError("Review git_range head tree 不匹配")
    if git("rev-parse", f"{value['base_sha']}^{{commit}}") != value["base_sha"]:
        raise EvidenceFingerprintError("Review git_range base 必须为 commit")
    git("merge-base", "--is-ancestor", value["base_sha"], value["head_sha"])
    return dict(value)


def build_review_fingerprint(
    *, workflow: str, deliverable: str, scope: str,
    candidate_evidence_identity: dict[str, Any],
    human_decision_projection: dict[str, Any], terminal: dict[str, Any],
    changed_paths: list[str], profiles: list[str], contexts: list[dict[str, Any]],
    initial_reviewers: list[dict[str, Any]], evidence: list[dict[str, Any]],
    git_range: dict[str, str] | None = None,
) -> dict[str, Any]:
    asset_paths = [REGISTRY_PATH.relative_to(REPO_ROOT).as_posix()]
    if (source_root() / ".agents/skills/review/references/grading.md").is_file():
        asset_paths.append(GRADING_PATH.relative_to(REPO_ROOT).as_posix())
    for reviewer in initial_reviewers:
        asset_paths.extend((
            f".agents/skills/review/references/roles/{reviewer['role']}/ROLE.md",
            (REFERENCES_DIR / reviewer["checklist"]).relative_to(REPO_ROOT).as_posix(),
        ))
    generator_path = "quwoquan_ops/cli/review_dispatch.py"
    # 每次重算独立批读，恢复原顺序及重复项，保持exact digest语义。
    by_path = {item["path"]: item for item in snapshot_paths([*asset_paths, generator_path], repo_root=source_root())}
    assets = [by_path[path] for path in asset_paths]
    review_identity = {
        "workflow": workflow, "deliverable": deliverable, "scope": scope,
        "candidate_evidence_identity": candidate_evidence_identity,
        "human_decision_projection": human_decision_projection,
        "terminal": terminal,
        "changed_paths": changed_paths, "profiles": profiles, "contexts": contexts,
        "reviewers": [
            {key: item[key] for key in ("role", "kind", "required", "profile", "checklist")}
            for item in initial_reviewers
        ],
        "evidence": [
            {
                key: item[key]
                for key in (
                    "id",
                    "required",
                    "covers",
                    "timeout_seconds",
                    "command_digest",
                )
            }
            for item in evidence
        ],
    }
    git_identity = {"head_sha": canonical_digest("review-head-independent"), "merge_base_sha": canonical_digest("review-merge-base-independent")}
    if git_range is not None:
        review_identity["git_range"] = validate_git_range(git_range, repo_root=source_root())
        git_identity = {"head_sha": git_range["head_sha"], "merge_base_sha": git_range["base_sha"]}
    return build_evidence_fingerprint(
        {
            "git": git_identity,
            "workspace": workspace_digests([], repo_root=source_root()),
            "assets": {
                "canonical_assets_digest": canonical_digest(contexts),
                "review_assets_digest": canonical_digest(
                    {"assets": assets, "review_identity": review_identity}
                ),
            },
            "execution": {
                "commands_digest": canonical_digest(
                    [item["command_digest"] for item in evidence]
                ),
                "toolchain_digest": canonical_digest({
                    "python": list(sys.version_info[:3]),
                    "review_plan_schema": contract_schema_version("review_plan"),
                }),
                "provider_digest": canonical_digest([
                    {key: item[key] for key in ("role", "kind", "required")}
                    for item in initial_reviewers
                ]),
                "generator_digest": canonical_digest(
                    by_path[generator_path]
                ),
            },
        },
        captured_by="review_dispatch",
        captured_metadata={"consumer": "review_plan.fingerprint"},
    )

__all__ = [
    "EvidenceFingerprintError", "build_review_fingerprint", "head_sha",
    "merge_base_sha", "normalize_path", "sha256_text", "snapshot",
]
