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

from .base_ref import AUTO_BASE, resolve_auto_base
from .classification import classify_path
from .git_delta import (
    Change, blob, blobs, changes, index_blob, resolve_sha, working_tree_blob,
    working_tree_changes,
)
from .metrics import (
    candidate_duplicate_windows, changed_complexity_findings, duplicate_window_index,
    duplicate_windows, executable_magic, has_repository_entry, line_count, reuse_scope_key,
    tracked_paths,
)
from .policy import load_policy


REPORT_SCHEMA = "quwoquan.code-health-delta"


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
    finding = {"code": code, "path": path, "terminal": terminal, "message": message, **extra}
    if terminal == "GATE_BLOCK" and not finding.get("recovery"):
        raise ValueError(f"{code} GATE_BLOCK finding 缺 recovery")
    return finding


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


def _candidate_bytes(
    repo: Path, path: str, *, working_tree: bool, index_only: bool,
    commit_blobs: dict[str, bytes],
) -> bytes | None:
    if working_tree:
        return index_blob(repo, path) if index_only else working_tree_blob(repo, path)
    return commit_blobs.get(path)


def _drop_merge_inherited(
    repo: Path, delta: list[Change], parents: list[str], *, working_tree: bool,
    index_only: bool, commit_blobs: dict[str, bytes],
) -> list[Change]:
    """Drop paths a merge candidate inherits verbatim from another parent.

    A merge does not author bytes that already exist in one of its parents. Without
    this, every merge would re-report the whole other branch as its own delta and
    block on debt it did not introduce.
    """
    if not parents:
        return delta
    live = sorted({item.path for item in delta if item.status != "D"})
    dead = sorted({item.path for item in delta if item.status == "D"})
    parent_blobs = {parent: blobs(repo, parent, live) for parent in parents}
    parent_dead = {parent: blobs(repo, parent, dead) for parent in parents}
    kept: list[Change] = []
    for item in delta:
        if item.status == "D":
            inherited = any(item.path not in parent_dead[parent] for parent in parents)
        else:
            candidate = _candidate_bytes(
                repo, item.path, working_tree=working_tree,
                index_only=index_only, commit_blobs=commit_blobs,
            )
            inherited = candidate is not None and any(
                parent_blobs[parent].get(item.path) == candidate for parent in parents
            )
        if not inherited:
            kept.append(item)
    return kept


def _category_summary(policy: dict[str, Any], delta: list[Change]) -> dict[str, dict[str, int]]:
    result = {name: {"files": 0, "added": 0, "deleted": 0, "churn": 0} for name in policy["source_categories"]}
    for item in delta:
        category = classify_path(item.path if item.status != "D" else (item.old_path or item.path), policy)
        current = result[category]
        current["files"] += 1; current["added"] += item.added; current["deleted"] += item.deleted; current["churn"] += item.added + item.deleted
    return result


def _resolve_base(repo: Path, base: str) -> tuple[str, dict[str, str | None]]:
    if base != AUTO_BASE:
        return resolve_sha(repo, base), {"requested": base, "ref": None, "sha": None}
    resolved = resolve_auto_base(repo)
    return resolved["sha"], {"requested": AUTO_BASE, "ref": resolved["ref"], "sha": resolved["sha"]}


def _file_size_finding(path: str, before_lines: int, after_lines: int, file_lines: dict[str, int]) -> dict[str, object] | None:
    advisory = file_lines["advisory"]; block = file_lines["block"]
    measure = {"before": before_lines, "after": after_lines}
    if after_lines > block and before_lines <= block:
        return _finding("CODE_HEALTH.NEW_FILE_OVER_BLOCK", path, "GATE_BLOCK", f"file lines {before_lines}->{after_lines} crossed block threshold {block}", recovery="split_or_reduce_new_file_below_block_threshold", measure={**measure, "threshold": block})
    if after_lines > block and after_lines > before_lines:
        return _finding("CODE_HEALTH.OVERSIZED_FILE_GROWTH", path, "GATE_BLOCK", f"oversized file grew {before_lines}->{after_lines}; debt must only decrease", recovery="reduce_oversized_file_to_previous_or_below_block_size", measure={**measure, "threshold": block})
    if after_lines > advisory and after_lines > before_lines:
        return _finding("CODE_HEALTH.FILE_LINES_ADVISORY", path, "PR_WARN", f"file lines {before_lines}->{after_lines} exceeds advisory {advisory}", measure={**measure, "threshold": advisory})
    return None


def _duplication_findings(
    repo: Path, base_sha: str, policy: dict[str, Any], production: list[Change],
    live_candidates: list[tuple[str, bytes, frozenset[int]]],
) -> tuple[list[dict[str, object]], dict[str, float]]:
    """Changed-line duplication against the base corpus of the same reuse scopes and within the candidate."""
    duplication = policy["thresholds"]["duplication"]
    changed_old = {item.old_path or item.path for item in production}
    reuse_scopes = {reuse_scope_key(item.path) for item in production}
    baseline_paths = [
        path for path in tracked_paths(repo, base_sha)
        if path not in changed_old and reuse_scope_key(path) in reuse_scopes
        and classify_path(path, policy) == "handwritten-production"
    ]
    baseline_blobs = blobs(repo, base_sha, baseline_paths)
    baseline_index = duplicate_window_index(
        [(path, baseline_blobs[path]) for path in baseline_paths if path in baseline_blobs],
        block_lines=duplication["block_lines"],
    )
    # Agent 复制粘贴最常见的形态是同一 candidate 内互相复制：这些片段在基线里不存在，
    # 只查「新行 vs 基线」会全部漏掉，所以对 candidate 自身再做一次窗口匹配。
    intra_candidate = candidate_duplicate_windows(live_candidates, block_lines=duplication["block_lines"])
    added_by_path = {item.path: item.added for item in production}
    findings: list[dict[str, object]] = []
    duplicate_lines = 0
    measured_added = 0
    for path, new, changed_lines in live_candidates:
        measured_added += added_by_path[path]
        covered_by_baseline, source = duplicate_windows(
            new, block_lines=duplication["block_lines"], baseline_index=baseline_index,
            changed_lines=changed_lines, return_lines=True,
        )
        covered_by_candidate, candidate_source = intra_candidate.get(path, (frozenset(), None))
        covered = set(covered_by_baseline) | set(covered_by_candidate)
        if not covered:
            continue
        duplicate_lines += len(covered)
        origin = source if source is not None else candidate_source
        findings.append(_finding(
            "CODE_HEALTH.DUPLICATION_CANDIDATE", path, "PASS",
            f"changed production lines duplicate {origin}",
            sourcePath=origin, duplicatedLines=len(covered),
            baselineDuplicatedLines=len(covered_by_baseline),
            candidateDuplicatedLines=len(covered_by_candidate),
        ))
    minimum = duplication["minimum_measured_new_lines"]
    percent = 0.0 if measured_added < minimum else 100.0 * duplicate_lines / measured_added
    advisory_percent = float(duplication["advisory_percent"])
    if measured_added >= minimum and percent > advisory_percent:
        findings.append(_finding(
            "CODE_HEALTH.DUPLICATION_ADVISORY", "<candidate>", "PR_WARN",
            f"new production duplication {percent:.4f}% exceeds advisory {advisory_percent:.4f}%",
            measure={"measuredNewLines": measured_added, "duplicatedLines": duplicate_lines, "percent": round(percent, 4), "threshold": advisory_percent},
        ))
    return findings, {"measuredNewLines": measured_added, "duplicatedLines": duplicate_lines, "duplicationPercent": round(percent, 4)}


def _change_size_finding(production: list[Change], size: dict[str, int]) -> tuple[dict[str, object] | None, dict[str, Any]]:
    files = len(production)
    churn = sum(item.added + item.deleted for item in production if item.status not in {"D", "R"})
    scopes = sorted({reuse_scope_key(item.path) for item in production})
    summary = {"handwrittenFiles": files, "handwrittenChurn": churn, "handwrittenScopes": scopes}
    measure = {"churn": churn, "files": files, "scopes": scopes}
    oversized = churn > size["split_analysis_churn"] or files > size["split_analysis_files"]
    # 拆分信号只针对「混入多个 owner scope 的大 candidate」（DEC-031）；单 owner 的大迁移
    # 只是规模提示，不要求拆分分析。
    if oversized and len(scopes) >= size["split_analysis_scopes"]:
        return _finding("CODE_HEALTH.SPLIT_ANALYSIS_REQUIRED", "<candidate>", "PR_WARN", f"candidate needs split analysis: handwritten churn={churn}, files={files}, owner scopes={len(scopes)}", measure=measure), summary
    if oversized or churn > size["warn_handwritten_churn"] or files > size["warn_handwritten_files"]:
        return _finding("CODE_HEALTH.CHANGE_SIZE_ADVISORY", "<candidate>", "PR_WARN", f"large handwritten candidate: churn={churn}, files={files}, owner scopes={len(scopes)}", measure=measure), summary
    return None, summary


def analyze_delta(repo: Path, *, base: str, head: str, policy_path: Path, mode: str = "full", explicit_paths: list[str] | None = None, working_tree: bool = False, index_only: bool = False, merge_parents: list[str] | None = None) -> dict[str, Any]:
    if mode not in {"fast", "full"}:
        raise ValueError("code health mode 必须为 fast/full")
    if index_only and not working_tree:
        raise ValueError("index_only requires working_tree")
    repo = repo.resolve(); policy_path = policy_path.resolve()
    policy = load_policy(policy_path)
    base_sha, base_resolution = _resolve_base(repo, base)
    head_sha = resolve_sha(repo, head)
    delta = working_tree_changes(repo, base_sha, explicit_paths, index_only=index_only) if working_tree else changes(repo, base_sha, head_sha, explicit_paths)
    resolved_parents = sorted({
        resolve_sha(repo, parent) for parent in (merge_parents or [])
    } - {base_sha})
    commit_current_blobs = {} if working_tree else blobs(
        repo, head_sha, [item.path for item in delta if item.status != "D"]
    )
    delta = _drop_merge_inherited(
        repo, delta, resolved_parents, working_tree=working_tree,
        index_only=index_only, commit_blobs=commit_current_blobs,
    )
    paths = [item.path for item in delta]
    impact = classify_impacts(paths)
    findings: list[dict[str, object]] = []
    thresholds = policy["thresholds"]
    categories = {item.path: classify_path(item.path if item.status != "D" else (item.old_path or item.path), policy) for item in delta}

    # Executable build artifacts are a source-tree invariant, independent of the
    # suffix-based source category. Suffixless ELF/Mach-O/PE files otherwise land
    # in config-data and would bypass the production-only metric loop.
    for item in delta:
        if item.status == "D":
            continue
        magic = executable_magic(_candidate_bytes(repo, item.path, working_tree=working_tree, index_only=index_only, commit_blobs=commit_current_blobs))
        if magic:
            findings.append(_finding(
                "CODE_HEALTH.TRACKED_SOURCE_EXECUTABLE", item.path, "GATE_BLOCK",
                f"tracked source path contains {magic} executable build artifact",
                recovery="remove_executable_artifact_from_source_tree",
            ))

    production = [item for item in delta if categories[item.path] == "handwritten-production"]
    base_production_paths = sorted({item.old_path or item.path for item in production})
    base_changed_blobs = blobs(repo, base_sha, base_production_paths)
    live_candidates: list[tuple[str, bytes, frozenset[int]]] = []
    for item in production:
        if item.status == "D":
            continue
        old = base_changed_blobs.get(item.old_path or item.path)
        new = _candidate_bytes(repo, item.path, working_tree=working_tree, index_only=index_only, commit_blobs=commit_current_blobs)
        live_candidates.append((item.path, new or b"", item.changed_new_lines))
        size_finding = _file_size_finding(item.path, line_count(old), line_count(new), thresholds["file_lines"])
        if size_finding is not None:
            findings.append(size_finding)
        if item.status == "A" and item.path.startswith("quwoquan_data/scripts/") and item.path.endswith(".py") and not has_repository_entry(repo, head_sha, item.path, working_tree=working_tree, index_only=index_only):
            findings.append(_finding("CODE_HEALTH.NEW_PRIVATE_PYTHON_WITHOUT_ENTRY", item.path, "GATE_BLOCK", "new Data package module has no language or repository entry edge", recovery="add_canonical_repository_entry_or_remove_private_module"))
        if mode == "full":
            findings.extend(changed_complexity_findings(item.path, old, new, item.changed_new_lines, thresholds["complexity"]["cyclomatic_advisory"], thresholds["complexity"]["cognitive_advisory"]))

    duplication_summary = {"measuredNewLines": 0, "duplicatedLines": 0, "duplicationPercent": 0.0}
    if mode == "full":
        duplication_findings, duplication_summary = _duplication_findings(repo, base_sha, policy, production, live_candidates)
        findings.extend(duplication_findings)

    size_finding, size_summary = _change_size_finding(production, thresholds["change_size"])
    if size_finding is not None:
        findings.append(size_finding)

    findings.sort(key=lambda item: (-_SEVERITY[str(item["terminal"])], str(item["path"]), str(item["code"])))
    terminal = max((str(item["terminal"]) for item in findings), key=_SEVERITY.get, default="PASS")
    policy_bytes = policy_path.read_bytes(); policy_digest = _sha256_bytes(policy_bytes)
    commands = {"mode": mode, "base": base_sha, "head": head_sha, "paths": paths, "workingTree": working_tree, "indexOnly": index_only, "mergeParents": resolved_parents}
    implementation_digest = _implementation_digest()
    toolchain = {"python": list(sys.version_info[:3]), "builtin": 1, "metricsProvider": policy["notes"]["metrics_provider"]}
    fingerprint = build_evidence_fingerprint({
        "git": {"head_sha": head_sha, "merge_base_sha": base_sha},
        "workspace": _workspace_identity(repo, head_sha, delta, working_tree=working_tree, index_only=index_only, commit_blobs=commit_current_blobs),
        "assets": {"canonical_assets_digest": policy_digest, "review_assets_digest": str(impact["path_digest"])},
        "execution": {"commands_digest": canonical_digest(commands), "toolchain_digest": canonical_digest(toolchain), "provider_digest": canonical_digest("incremental-code-health"), "generator_digest": implementation_digest},
    }, captured_at="code-health-delta-v1", captured_by="verify_incremental_code_health", captured_metadata={"mode": mode, "changed_paths_digest": impact["path_digest"]})
    category_summary = _category_summary(policy, delta)
    return {
        "schema": REPORT_SCHEMA, "terminal": terminal,
        "baseSha": base_sha, "headSha": head_sha, "baseResolution": base_resolution,
        "mergeParents": resolved_parents, "changedPaths": paths,
        "changedPathsDigest": impact_digest(paths), "impactPlanner": impact["source"],
        "policyId": policy["policy_id"], "policyDigest": policy_digest, "implementationDigest": implementation_digest,
        "mode": mode, "candidateSource": ("index" if index_only else "working-tree") if working_tree else "commit", "categorySummary": category_summary,
        "summary": {"changedFiles": len(delta), "renamedFiles": sum(item.status == "R" for item in delta), "deletedFiles": sum(item.status == "D" for item in delta), **size_summary, **duplication_summary, "findingCount": len(findings)},
        "findings": findings, "tools": toolchain,
        "rollout": {"automaticPromotion": False, "calibration": policy["rollout"]["calibration"], "advisoryOnlyCodes": policy["notes"]["advisory_only_codes"]},
        "evidenceFingerprint": fingerprint,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
