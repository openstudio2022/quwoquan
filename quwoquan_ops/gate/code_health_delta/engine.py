"""Canonical Code Health Delta orchestration and typed report."""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from quwoquan_ops.ci.impact_planner_core import canonical_digest as impact_digest, classify_impacts
from quwoquan_ops.cli.lib.evidence_fingerprint import build_evidence_fingerprint, canonical_digest

from .classification import classify_path
from .git_delta import Change, blob, blobs, changes, index_blob, resolve_sha, working_tree_blob, working_tree_changes
from .metrics import (
    changed_complexity_findings, duplicate_window_index, duplicate_windows, executable_magic,
    has_repository_entry, line_count, reuse_scope_key, tracked_paths,
)
from .policy import load_policy


_SEVERITY = {"PASS": 0, "PR_WARN": 1, "GATE_BLOCK": 2}


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _implementation_digest() -> str:
    package_root = Path(__file__).parent
    repository_root = package_root.parents[2]
    paths = [
        *sorted(package_root.glob("*.py"), key=lambda candidate: candidate.name),
        repository_root / "quwoquan_ops/ci/impact_planner_core.py",
        repository_root / "quwoquan_ops/cli/lib/evidence_fingerprint.py",
    ]
    assets = {
        item.relative_to(repository_root).as_posix(): _sha256_bytes(item.read_bytes())
        for item in paths
    }
    return canonical_digest(assets)


def _finding(code: str, path: str, terminal: str, message: str, **extra: object) -> dict[str, object]:
    return {"code": code, "path": path, "terminal": terminal, "message": message, **extra}


def _workspace_identity(repo: Path, head: str, delta: list[Change], *, working_tree: bool = False, index_only: bool = False, commit_blobs: dict[str, bytes] | None = None) -> dict[str, str]:
    tracked = []; untracked = []; deleted = []; renamed = []
    for item in delta:
        fact = {"path": item.path, "status": item.status, "contentDigest": _sha256_bytes(((index_blob(repo, item.path) if index_only else working_tree_blob(repo, item.path)) if working_tree else (commit_blobs or {}).get(item.path)) or b"")}
        if item.untracked: untracked.append(fact)
        elif item.status == "D": deleted.append(fact)
        elif item.status == "R": renamed.append({**fact, "oldPath": item.old_path})
        else: tracked.append(fact)
    empty = canonical_digest([])
    return {
        "tracked_digest": canonical_digest(tracked), "untracked_digest": canonical_digest(untracked),
        "deleted_digest": canonical_digest(deleted), "renamed_digest": canonical_digest(renamed),
        "symlink_digest": empty,
    }


def _category_summary(policy: dict[str, Any], delta: list[Change]) -> dict[str, dict[str, int]]:
    result = {name: {"files": 0, "added": 0, "deleted": 0, "churn": 0} for name in policy["source_categories"]}
    for item in delta:
        category = classify_path(item.path if item.status != "D" else (item.old_path or item.path), policy)
        current = result[category]
        current["files"] += 1; current["added"] += item.added; current["deleted"] += item.deleted; current["churn"] += item.added + item.deleted
    return result


def analyze_delta(repo: Path, *, base: str, head: str, policy_path: Path, mode: str = "full", explicit_paths: list[str] | None = None, working_tree: bool = False, index_only: bool = False) -> dict[str, Any]:
    if mode not in {"fast", "full"}:
        raise ValueError("code health mode 必须为 fast/full")
    if index_only and not working_tree:
        raise ValueError("index_only requires working_tree")
    repo = repo.resolve(); policy_path = policy_path.resolve()
    policy = load_policy(policy_path)
    base_sha = resolve_sha(repo, base); head_sha = resolve_sha(repo, head)
    delta = working_tree_changes(repo, base_sha, explicit_paths, index_only=index_only) if working_tree else changes(repo, base_sha, head_sha, explicit_paths)
    paths = [item.path for item in delta]
    impact = classify_impacts(paths)
    findings: list[dict[str, object]] = []
    thresholds = policy["thresholds"]
    categories = {item.path: classify_path(item.path if item.status != "D" else (item.old_path or item.path), policy) for item in delta}
    commit_current_blobs = {} if working_tree else blobs(
        repo, head_sha, [item.path for item in delta if item.status != "D"]
    )

    # Executable build artifacts are a source-tree invariant, independent of the
    # suffix-based source category. Suffixless ELF/Mach-O/PE files otherwise land
    # in config-data and would bypass the production-only metric loop.
    for item in delta:
        if item.status == "D":
            continue
        new = (
            index_blob(repo, item.path) if index_only else working_tree_blob(repo, item.path)
        ) if working_tree else commit_current_blobs.get(item.path)
        magic = executable_magic(new)
        if magic:
            findings.append(_finding(
                "CODE_HEALTH.TRACKED_SOURCE_EXECUTABLE", item.path, "GATE_BLOCK",
                f"tracked source path contains {magic} executable build artifact",
            ))

    production = [item for item in delta if categories[item.path] == "handwritten-production"]
    base_production_paths = sorted({item.old_path or item.path for item in production})
    base_changed_blobs = blobs(repo, base_sha, base_production_paths)
    for item in production:
        old = base_changed_blobs.get(item.old_path or item.path)
        new = (index_blob(repo, item.path) if index_only else working_tree_blob(repo, item.path)) if working_tree else commit_current_blobs.get(item.path)
        if item.status == "D":
            continue
        before_lines = line_count(old); after_lines = line_count(new)
        advisory = thresholds["file_lines"]["advisory"]; block = thresholds["file_lines"]["block"]
        if after_lines > block and before_lines <= block:
            findings.append(_finding("CODE_HEALTH.NEW_FILE_OVER_BLOCK", item.path, "GATE_BLOCK", f"file lines {before_lines}->{after_lines} crossed block threshold {block}", measure={"before": before_lines, "after": after_lines, "threshold": block}))
        elif after_lines > block and after_lines > before_lines:
            findings.append(_finding("CODE_HEALTH.OVERSIZED_FILE_GROWTH", item.path, "GATE_BLOCK", f"oversized file grew {before_lines}->{after_lines}; debt must only decrease", measure={"before": before_lines, "after": after_lines, "threshold": block}))
        elif after_lines > advisory and after_lines > before_lines:
            findings.append(_finding("CODE_HEALTH.FILE_LINES_ADVISORY", item.path, "PR_WARN", f"file lines {before_lines}->{after_lines} exceeds advisory {advisory}", measure={"before": before_lines, "after": after_lines, "threshold": advisory}))
        if item.status == "A" and item.path.startswith("quwoquan_data/scripts/") and item.path.endswith(".py") and not has_repository_entry(repo, head_sha, item.path, working_tree=working_tree, index_only=index_only):
            findings.append(_finding("CODE_HEALTH.NEW_PRIVATE_PYTHON_WITHOUT_ENTRY", item.path, "GATE_BLOCK", "new Data package module has no language or repository entry edge"))
        if mode == "full":
            findings.extend(changed_complexity_findings(item.path, old, new, item.changed_new_lines, thresholds["complexity"]["cyclomatic_advisory"], thresholds["complexity"]["cognitive_advisory"]))

    if mode == "full":
        changed_old = {item.old_path or item.path for item in production}
        reuse_scopes = {reuse_scope_key(item.path) for item in production}
        baseline_paths = [
            path
            for path in tracked_paths(repo, base_sha)
            if path not in changed_old
            and reuse_scope_key(path) in reuse_scopes
            and classify_path(path, policy) == "handwritten-production"
        ]
        baseline_blobs = blobs(repo, base_sha, baseline_paths)
        base_production = [(path, baseline_blobs[path]) for path in baseline_paths if path in baseline_blobs]
        baseline_index = duplicate_window_index(
            base_production,
            block_lines=thresholds["duplication"]["block_lines"],
        )
        duplicate_lines = 0
        measured_added = 0
        for item in production:
            if item.status == "D":
                continue
            new = ((index_blob(repo, item.path) if index_only else working_tree_blob(repo, item.path)) if working_tree else commit_current_blobs.get(item.path)) or b""
            measured_added += item.added
            duplicated, source = duplicate_windows(
                new,
                block_lines=thresholds["duplication"]["block_lines"],
                baseline_index=baseline_index,
                changed_lines=item.changed_new_lines,
            )
            if duplicated:
                duplicate_lines += duplicated
                findings.append(_finding(
                    "CODE_HEALTH.DUPLICATION_CANDIDATE", item.path, "PASS",
                    f"changed production lines duplicate {source}",
                    sourcePath=source, duplicatedLines=duplicated,
                ))
        minimum = thresholds["duplication"]["minimum_measured_new_lines"]
        duplication_percent = 0.0 if measured_added < minimum or measured_added == 0 else 100.0 * duplicate_lines / measured_added
        advisory_percent = float(thresholds["duplication"]["advisory_percent"])
        if measured_added >= minimum and duplication_percent > advisory_percent:
            findings.append(_finding(
                "CODE_HEALTH.DUPLICATION_ADVISORY", "<candidate>", "PR_WARN",
                f"new production duplication {duplication_percent:.4f}% exceeds advisory {advisory_percent:.4f}%",
                measure={
                    "measuredNewLines": measured_added,
                    "duplicatedLines": duplicate_lines,
                    "percent": round(duplication_percent, 4),
                    "threshold": advisory_percent,
                },
            ))
    else:
        measured_added = 0; duplicate_lines = 0; duplication_percent = 0.0

    handwritten_files = len(production)
    handwritten_churn = sum(item.added + item.deleted for item in production if item.status not in {"D", "R"})
    size = thresholds["change_size"]
    if handwritten_churn > size["split_analysis_churn"] or handwritten_files > size["split_analysis_files"]:
        findings.append(_finding("CODE_HEALTH.SPLIT_ANALYSIS_REQUIRED", "<candidate>", "PR_WARN", f"candidate needs split analysis: handwritten churn={handwritten_churn}, files={handwritten_files}"))
    elif handwritten_churn > size["warn_handwritten_churn"] or handwritten_files > size["warn_handwritten_files"]:
        findings.append(_finding("CODE_HEALTH.CHANGE_SIZE_ADVISORY", "<candidate>", "PR_WARN", f"large handwritten candidate: churn={handwritten_churn}, files={handwritten_files}"))

    findings.sort(key=lambda item: (-_SEVERITY[str(item["terminal"])], str(item["path"]), str(item["code"])))
    terminal = max((str(item["terminal"]) for item in findings), key=_SEVERITY.get, default="PASS")
    policy_bytes = policy_path.read_bytes(); policy_digest = _sha256_bytes(policy_bytes)
    commands = {"mode": mode, "base": base_sha, "head": head_sha, "paths": paths, "workingTree": working_tree, "indexOnly": index_only}
    implementation_digest = _implementation_digest()
    toolchain = {"python": list(sys.version_info[:3]), "builtin": 1, "configured": policy["tools"]}
    fingerprint = build_evidence_fingerprint({
        "git": {"head_sha": head_sha, "merge_base_sha": base_sha},
        "workspace": _workspace_identity(repo, head_sha, delta, working_tree=working_tree, index_only=index_only, commit_blobs=commit_current_blobs),
        "assets": {"canonical_assets_digest": policy_digest, "review_assets_digest": str(impact["path_digest"])},
        "execution": {"commands_digest": canonical_digest(commands), "toolchain_digest": canonical_digest(toolchain), "provider_digest": canonical_digest("incremental-code-health"), "generator_digest": implementation_digest},
    }, captured_at="code-health-delta-v1", captured_by="verify_incremental_code_health", captured_metadata={"mode": mode, "changed_paths_digest": impact["path_digest"]})
    category_summary = _category_summary(policy, delta)
    return {
        "schema": "quwoquan.code-health-delta.v1", "terminal": terminal,
        "baseSha": base_sha, "headSha": head_sha, "changedPaths": paths,
        "changedPathsDigest": impact_digest(paths), "impactPlanner": impact["source"],
        "policyId": policy["policy_id"], "policyDigest": policy_digest, "implementationDigest": implementation_digest,
        "mode": mode, "candidateSource": ("index" if index_only else "working-tree") if working_tree else "commit", "categorySummary": category_summary,
        "summary": {"changedFiles": len(delta), "renamedFiles": sum(item.status == "R" for item in delta), "deletedFiles": sum(item.status == "D" for item in delta), "handwrittenFiles": handwritten_files, "handwrittenChurn": handwritten_churn, "measuredNewLines": measured_added, "duplicatedLines": duplicate_lines, "duplicationPercent": round(duplication_percent, 4), "findingCount": len(findings)},
        "findings": findings, "tools": toolchain,
        "rollout": {"automaticPromotion": False, "calibration": policy["rollout"]["calibration"], "advisoryMetrics": policy["rollout"]["advisory_metrics"]},
        "evidenceFingerprint": fingerprint,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
