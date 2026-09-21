"""验收 CLI 输入与源码身份预检，不启动环境、不移动 Git refs。"""
from __future__ import annotations

import argparse
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.integration_run_bundle import IntegrationRunError
from quwoquan_ops.cli.lib.dirty_worktree import overlapping_dirty_paths, parse_name_only_z, parse_porcelain_z

DEV_REF = "refs/heads/dev1.0"


def dirty_overlap_with_candidate(git: Callable[..., str], parent: str, candidate: str) -> tuple[str, ...]:
    """只拦与本次发布 diff（`parent...candidate`）重叠的 tracked dirty / untracked；空 range 不阻断。

    本树直接发布时 HEAD 就是 candidate，`HEAD...candidate` 恒空，因此范围一律取 expectedParent。
    """
    dirty = parse_porcelain_z(git("status", "--porcelain", "-z", "--untracked-files=all"))
    touched = parse_name_only_z(git("diff", "--name-only", "--no-renames", "-z", parent, candidate))
    return overlapping_dirty_paths(dirty, touched)


def validate_mode_inputs(args: argparse.Namespace) -> None:
    if args.validate_bundle_only and (args.mode != "integrate" or args.publish or not re.fullmatch(r"[0-9a-f]{40}", args.candidate)):
        raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "--validate-bundle-only requires integrate, exact --candidate SHA and no --publish")
    if args.mode == "published-validation":
        if args.publish or args.acceptance_bundle is not None or args.baseline or args.reuse:
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "published-validation cannot publish, import bundle, override baseline or reuse source EAF")
        if not args.candidate_ref or not args.publish_result:
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "published-validation requires exact candidate-ref and publish-result")
        return
    if args.mode == "acceptance":
        if args.acceptance_bundle is not None:
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "--acceptance-bundle is integrate-only; acceptance produces the bundle")
        return
    flags = ("baseline", "alpha", "beta", "reuse", "merged_lanes", "candidate_ref", "android_device_id", "ios_device_id",
             "release_attestation", "rollback_release_attestation", "release_handoff_ref")
    for field in flags:
        if getattr(args, field):
            raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", f"--{field.replace('_', '-')} is acceptance-only; integrate consumes --acceptance-bundle")
    if args.acceptance_bundle is None:
        raise IntegrationRunError("INTEGRATION_RUN.ACCEPTANCE_REQUIRED", "integrate requires --acceptance-bundle produced by make accept in the lane worktree; no environment runs here")


def preflight_identity(args: argparse.Namespace, *, git: Callable[..., str], is_ancestor: Callable[[str, str], bool]) -> dict[str, str]:
    commit = git("rev-parse", f"{args.candidate}^{{commit}}")
    remote_head = git("ls-remote", args.remote, DEV_REF).split()[0]
    parent = git("rev-parse", f"{args.baseline}^{{commit}}") if args.baseline else remote_head
    if parent != remote_head:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_STALE", "publishable acceptance baseline must equal current remote dev1.0")
    if commit == parent:
        code = "NOTHING_TO_ACCEPT" if args.mode == "acceptance" else "NOTHING_TO_INTEGRATE"
        raise IntegrationRunError(f"INTEGRATION_RUN.{code}", "candidate equals current published baseline; no new candidate to accept")
    if not is_ancestor(parent, commit):
        raise IntegrationRunError("INTEGRATION_RUN.NOT_FAST_FORWARD", "remote dev1.0 is not an ancestor of the candidate")
    overlap = dirty_overlap_with_candidate(git, parent, commit)
    if overlap:
        preview = ", ".join(overlap[:8])
        raise IntegrationRunError("INTEGRATION_RUN.DIRTY_WORKTREE", f"dirty path(s) overlap expectedParent...candidate: {preview}")
    if args.mode == "integrate":
        if git("symbolic-ref", "--quiet", "HEAD") != DEV_REF or (not args.validate_bundle_only and git("rev-parse", "HEAD") != commit):
            raise IntegrationRunError("INTEGRATION_RUN.INTEGRATION_IDENTITY_INVALID", "integrate requires refs/heads/dev1.0 with HEAD == candidate; validate bundle before FF")
    return {"commit": commit, "parent": parent, "remoteHead": remote_head, "tree": git("show", "-s", "--format=%T", commit)}


def published_identity(args: argparse.Namespace, *, repository: Path, store: Path, policy: Path,
                       git: Callable[..., str]) -> tuple[dict, dict, dict]:
    """发布后环境运行只消费验真的已发布候选，不创建新 candidate。"""
    from quwoquan_ops.ci.scoped_candidate.core import _load_exact_ref, _identity_digest, _validated_admission
    def exact(value: str) -> dict:
        ref, digest = value.rsplit("=", 1)
        return {"ref": ref, "digest": digest}
    result, _ = _load_exact_ref(store, exact(args.publish_result), "publish-result")
    _identity_digest(result, "publishResultId")
    if result.get("terminal") != "published" or result.get("targetRef") != DEV_REF:
        raise IntegrationRunError("INTEGRATION_RUN.PUBLISHED_IDENTITY_INVALID", "published result required")
    admission_ref = result["admission"]
    admission = _validated_admission(repository, store / admission_ref["ref"], policy, admission_ref["digest"])
    candidate_ref = exact(args.candidate_ref)
    candidate, _ = _load_exact_ref(store, candidate_ref, "candidate")
    _identity_digest(candidate, "candidateId")
    if (admission["candidate"] != candidate_ref or result.get("admissionId") != admission["admissionId"]
            or result.get("beforeOid") != candidate["expectedParent"]
            or result.get("afterOid") != candidate["commit"] or result.get("readbackOid") != candidate["commit"]):
        raise IntegrationRunError("INTEGRATION_RUN.PUBLISHED_IDENTITY_INVALID", "candidate/publish-result/admission drift")
    remote = git("ls-remote", args.remote, DEV_REF).split()[0]
    if remote != candidate["commit"] or git("rev-parse", "HEAD") != remote or git("show", "-s", "--format=%T", remote) != candidate["tree"]:
        raise IntegrationRunError("INTEGRATION_RUN.PUBLISHED_IDENTITY_INVALID", "published HEAD/tree no longer current")
    # 外域 WIP 必须保留。打包走 published commit 的隔离源码树，因此只拦与
    # expectedParent...candidate 重叠、可能污染身份核对的脏路径。
    overlap = dirty_overlap_with_candidate(git, candidate["expectedParent"], candidate["commit"])
    if overlap:
        preview = ", ".join(overlap[:8])
        raise IntegrationRunError("INTEGRATION_RUN.DIRTY_WORKTREE", f"dirty path(s) overlap expectedParent...candidate: {preview}")
    return candidate_ref, candidate, result


def validate_source_inputs(args: argparse.Namespace, *, repository: Path) -> None:
    from quwoquan_ops.cli.lib.local_readiness.admission import load_review_inputs
    from quwoquan_ops.cli.lib.local_readiness.core import LocalReadinessError

    if args.readiness_level != "scope":
        raise IntegrationRunError("INTEGRATION_RUN.INPUT_INVALID", "publishable acceptance requires scope readiness")
    try:
        load_review_inputs(Path(args.review_consolidation) if args.review_consolidation else None,
                           [Path(item) for item in args.required_evidence or []], repo_root=repository, required=False)
    except LocalReadinessError as exc:
        raise IntegrationRunError("INTEGRATION_RUN.SOURCE_REQUIRED", str(exc)) from exc


def record_imported_bundle(summary: dict[str, Any], imported: Mapping[str, Any], *, bundle_dir: Path) -> None:
    manifest, candidate = imported["manifest"], imported["candidate"]
    summary["candidate"].update({"candidateId": candidate["candidateId"], "candidateRef": dict(manifest["candidate"]), "claimRef": candidate["claimRef"]})
    summary["acceptanceBundle"] = {
        "path": str(bundle_dir), "bundleId": manifest["bundleId"], "runId": manifest.get("runId"),
        "laneBranch": manifest.get("laneBranch"), "mergedLanes": manifest.get("mergedLanes"),
        "baseline": manifest.get("baseline"), "beta": manifest.get("beta"),
        "importedFiles": imported["importedFiles"], "storeFiles": imported["storeFiles"],
    }
    summary["impactPlan"] = dict(manifest.get("impactPlan") or {})
    summary["dataReleases"] = manifest.get("dataReleases")
    summary["dataReleaseHandoffRef"] = manifest.get("dataReleaseHandoffRef")
    summary["sourceFact"] = dict(manifest["sourceFact"])
    summary["environments"] = {
        "alpha": {"environment": "alpha", "executed": bool((manifest.get("alpha") or {}).get("executed", True)),
                 "imported": True, "reasonCode": (manifest.get("alpha") or {}).get("reasonCode"),
                 "acceptance": dict(manifest["alphaFact"])},
        "beta": {"environment": "beta", "executed": bool((manifest.get("beta") or {}).get("executed")), "imported": True,
                 "reasonCode": (manifest.get("beta") or {}).get("reasonCode"), "acceptance": dict(manifest["betaFact"])},
    }
