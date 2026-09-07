#!/usr/bin/env python3
"""Hosted `03. Delivery Gate` 的原生证据生产者。

三类职责，全部只读 GitHub REST/GraphQL 读回结果或本地证据树，不做任何 ref mutation：

1. `publish-oci-bundle` / `materialize-oci-bundle`：把 IQF 及其完整前驱证据树（A/B/G EAF、
   publish result/admission、candidate、命名证据、case results）作为一个确定性 tar 发布/取回，
   Gate 侧才能以 `verify_references=True` 校验整条链。
2. `hosted-authority`：由 Gate 自己从 hosted readback 生成 approval / threads / ruleset /
   changedBoundary / required-evidence 五类 canonical 事实，替代要求 PR 作者预先生产 OCI ref。
handoff check-run 本身由 `promotion_evidence.py create-handoff` + GITHUB_TOKEN（github-actions
integration，与 main ruleset 信任的 required check 同一身份）创建，不再依赖自建 GitHub App。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.promotion_evidence import (
    _EXACT_OCI,
    _OCI_REPOSITORY,
    PromotionEvidenceError,
    _sha,
    _text,
    _write_once,
    canonical_bytes,
    digest,
)

BUNDLE_ARTIFACT_TYPE = "application/vnd.quwoquan.promotion-evidence-bundle.v1"
BUNDLE_LAYER_TYPE = "application/vnd.quwoquan.promotion-evidence-bundle.v1.tar"
BUNDLE_MANIFEST = "bundle-manifest.json"
DELIVERY_GATE_CHECK = "03. Delivery Gate"
_AUTHORITY_SCHEMAS = {
    "approval": "quwoquan_ops.promotion_approval_fact.v1",
    "threads": "quwoquan_ops.promotion_thread_fact.v1",
    "ruleset": "quwoquan_ops.promotion_ruleset_fact.v1",
    "changedBoundary": "quwoquan_ops.promotion_boundary_fact.v1",
}
_REQUIRED_EVIDENCE_SCHEMA = "quwoquan_ops.promotion_required_evidence_fact.v1"
_SAFE_MEMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


# --------------------------------------------------------------------------- bundle


def _bundle_members(bundle_root: Path) -> list[Path]:
    root = bundle_root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise PromotionEvidenceError("PROMOTION.BUNDLE_INVALID", "bundle root must be a directory")
    members: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PromotionEvidenceError("PROMOTION.BUNDLE_INVALID", f"bundle must not contain symlinks: {path}")
        if path.is_dir():
            continue
        relative = path.relative_to(root).as_posix()
        if _SAFE_MEMBER.fullmatch(relative) is None or ".." in PurePosixPath(relative).parts:
            raise PromotionEvidenceError("PROMOTION.BUNDLE_INVALID", f"bundle member name is unsafe: {relative}")
        members.append(path)
    if not members:
        raise PromotionEvidenceError("PROMOTION.BUNDLE_INVALID", "bundle is empty")
    return members


def build_bundle_tar(*, bundle_root: Path, output_file: Path) -> dict[str, Any]:
    """确定性 tar：成员按路径排序，mtime/uid/gid 归零，只含 regular file。"""
    root = bundle_root.resolve()
    members = _bundle_members(root)
    manifest_entries = []
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in members:
            relative = path.relative_to(root).as_posix()
            data = path.read_bytes()
            info = tarfile.TarInfo(name=relative)
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
            manifest_entries.append({"ref": relative, "digest": "sha256:" + hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    raw = buffer.getvalue()
    output = output_file.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    return {
        "schema": "quwoquan_ops.promotion_evidence_bundle_manifest.v1",
        "tarSha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "entries": manifest_entries,
    }


def publish_oci_bundle(*, bundle_root: Path, repository: str, transport_tag: str) -> dict[str, Any]:
    if _OCI_REPOSITORY.fullmatch(_text(repository, "repository")) is None:
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "repository must be canonical GHCR")
    tag = _text(transport_tag, "transportTag")
    if any(character.isspace() for character in tag) or ":" in tag or "/" in tag:
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "transport tag is invalid")
    with tempfile.TemporaryDirectory(prefix="qwq-promotion-bundle-") as directory:
        stage = Path(directory)
        manifest = build_bundle_tar(bundle_root=bundle_root, output_file=stage / "bundle.tar")
        (stage / BUNDLE_MANIFEST).write_bytes(canonical_bytes(manifest) + b"\n")
        completed = subprocess.run(
            [
                "oras", "push", "--no-tty", "--format", "json", "--artifact-type", BUNDLE_ARTIFACT_TYPE,
                f"{repository}:{tag}", f"bundle.tar:{BUNDLE_LAYER_TYPE}",
                f"{BUNDLE_MANIFEST}:application/vnd.quwoquan.promotion-evidence-bundle-manifest.v1+json",
            ],
            cwd=stage, text=True, capture_output=True, check=False,
        )
    if completed.returncode:
        raise PromotionEvidenceError("PROMOTION.OCI_UNAVAILABLE", " ".join(completed.stderr.split()))
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "ORAS did not return JSON") from exc
    exact_ref = str(payload.get("reference") or "") if isinstance(payload, dict) else ""
    match = _EXACT_OCI.fullmatch(exact_ref)
    if match is None or match.group("repository") != repository:
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "ORAS did not return the expected exact reference")
    return {"exactRef": exact_ref, "tarSha256": manifest["tarSha256"], "entries": len(manifest["entries"])}


def extract_bundle(*, stage: Path, output_dir: Path) -> dict[str, Any]:
    """从 `bundle.tar` + manifest 安全展开证据树：只接受 regular file、安全相对路径与逐文件 digest 匹配。"""
    output = output_dir.expanduser().resolve()
    if output.exists():
        raise PromotionEvidenceError("PROMOTION.CREATE_CONFLICT", "bundle destination already exists")
    files = sorted(entry for entry in stage.rglob("*") if entry.is_file())
    if any(entry.is_symlink() for entry in stage.rglob("*")) or {entry.name for entry in files} != {"bundle.tar", BUNDLE_MANIFEST}:
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "bundle artifact must contain bundle.tar and its manifest only")
    tar_bytes = (stage / "bundle.tar").read_bytes()
    try:
        manifest = json.loads((stage / BUNDLE_MANIFEST).read_bytes())
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "bundle manifest is not JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("tarSha256") != "sha256:" + hashlib.sha256(tar_bytes).hexdigest():
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "bundle manifest does not bind tar bytes")
    expected = {entry["ref"]: entry["digest"] for entry in manifest.get("entries", [])}
    output.mkdir(parents=True, mode=0o700)
    seen: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
        for member in tar.getmembers():
            if not member.isfile() or _SAFE_MEMBER.fullmatch(member.name) is None or ".." in PurePosixPath(member.name).parts:
                raise PromotionEvidenceError("PROMOTION.BUNDLE_INVALID", f"bundle member is unsafe: {member.name}")
            data = tar.extractfile(member)
            if data is None:
                raise PromotionEvidenceError("PROMOTION.BUNDLE_INVALID", f"bundle member unreadable: {member.name}")
            raw = data.read()
            if expected.get(member.name) != "sha256:" + hashlib.sha256(raw).hexdigest():
                raise PromotionEvidenceError("PROMOTION.BUNDLE_INVALID", f"bundle member digest drifted: {member.name}")
            destination = output / member.name
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination.write_bytes(raw)
            seen.add(member.name)
    if seen != set(expected):
        raise PromotionEvidenceError("PROMOTION.BUNDLE_INVALID", "bundle members differ from manifest")
    return {"path": str(output), "entries": len(expected), "tarSha256": manifest["tarSha256"]}


def materialize_oci_bundle(*, exact_ref: str, output_dir: Path) -> dict[str, Any]:
    if _EXACT_OCI.fullmatch(_text(exact_ref, "exactRef")) is None:
        raise PromotionEvidenceError("PROMOTION.OCI_INVALID", "bundle ref must be exact GHCR @sha256")
    with tempfile.TemporaryDirectory(prefix="qwq-promotion-bundle-pull-") as directory:
        stage = Path(directory)
        completed = subprocess.run(["oras", "pull", "--output", str(stage), exact_ref], text=True, capture_output=True, check=False)
        if completed.returncode:
            raise PromotionEvidenceError("PROMOTION.OCI_UNAVAILABLE", " ".join((completed.stderr or completed.stdout).split()))
        return extract_bundle(stage=stage, output_dir=output_dir)


# --------------------------------------------------------------------------- hosted authority facts


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromotionEvidenceError("PROMOTION.AUTHORITY_INVALID", f"{label} is not readable JSON") from exc


def approval_fact(*, reviews: Sequence[Mapping[str, Any]], head_sha: str, base_sha: str, author_login: str) -> dict[str, Any]:
    """按 head commit 统计非作者的 APPROVED 评审；每个 reviewer 只取其最后一条评审。"""
    head = _sha(head_sha, "headSha")
    latest: dict[str, Mapping[str, Any]] = {}
    for review in reviews:
        if not isinstance(review, Mapping):
            continue
        user = review.get("user") if isinstance(review.get("user"), Mapping) else {}
        login = str(user.get("login") or "")
        if not login or login == author_login or review.get("commit_id") != head:
            continue
        if review.get("state") not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            continue
        latest[login] = review
    approvers = sorted(login for login, review in latest.items() if review.get("state") == "APPROVED")
    blockers = sorted(login for login, review in latest.items() if review.get("state") == "CHANGES_REQUESTED")
    passed = bool(approvers) and not blockers
    return {
        "schema": _AUTHORITY_SCHEMAS["approval"], "status": "passed" if passed else "failed",
        "decision": "approved" if passed else "not_approved", "headSha": head, "baseSha": _sha(base_sha, "baseSha"),
        "commitSha": head, "approvalCount": len(approvers), "approvers": approvers, "changesRequestedBy": blockers,
        "source": "github_rest:/pulls/{number}/reviews",
    }


def threads_fact(*, threads: Sequence[Mapping[str, Any]], head_sha: str, base_sha: str) -> dict[str, Any]:
    unresolved = sum(1 for thread in threads if isinstance(thread, Mapping) and thread.get("isResolved") is False)
    return {
        "schema": _AUTHORITY_SCHEMAS["threads"], "status": "passed" if unresolved == 0 else "failed",
        "headSha": _sha(head_sha, "headSha"), "baseSha": _sha(base_sha, "baseSha"), "commitSha": _sha(head_sha, "headSha"),
        "threadCount": len(threads), "unresolvedCount": unresolved, "source": "github_graphql:pullRequest.reviewThreads",
    }


def ruleset_fact(*, rulesets: Sequence[Mapping[str, Any]], head_sha: str, base_sha: str) -> dict[str, Any]:
    """main 分支必须有 active ruleset：要求 PR、无 bypass actor、required check 精确为 03. Delivery Gate。"""
    matched: list[dict[str, Any]] = []
    for ruleset in rulesets:
        if not isinstance(ruleset, Mapping) or ruleset.get("enforcement") != "active" or ruleset.get("target") != "branch":
            continue
        conditions = ruleset.get("conditions") if isinstance(ruleset.get("conditions"), Mapping) else {}
        ref_name = conditions.get("ref_name") if isinstance(conditions.get("ref_name"), Mapping) else {}
        if "refs/heads/main" not in (ref_name.get("include") or []):
            continue
        rules = ruleset.get("rules") if isinstance(ruleset.get("rules"), list) else []
        checks: list[str] = []
        strict = False
        requires_pr = False
        for rule in rules:
            if not isinstance(rule, Mapping):
                continue
            if rule.get("type") == "required_status_checks":
                parameters = rule.get("parameters") if isinstance(rule.get("parameters"), Mapping) else {}
                checks = [str(item.get("context")) for item in parameters.get("required_status_checks", []) if isinstance(item, Mapping)]
                strict = parameters.get("strict_required_status_checks_policy") is True
            if rule.get("type") == "pull_request":
                requires_pr = True
        if DELIVERY_GATE_CHECK in checks:
            matched.append({"id": ruleset.get("id"), "name": ruleset.get("name"), "checks": checks, "strict": strict, "requiresPullRequest": requires_pr, "bypassActors": list(ruleset.get("bypass_actors") or [])})
    enforced = len(matched) == 1 and matched[0]["strict"] and matched[0]["requiresPullRequest"] and matched[0]["bypassActors"] == []
    return {
        "schema": _AUTHORITY_SCHEMAS["ruleset"], "status": "passed" if enforced else "failed",
        "headSha": _sha(head_sha, "headSha"), "baseSha": _sha(base_sha, "baseSha"), "commitSha": _sha(head_sha, "headSha"),
        "requiredCheck": DELIVERY_GATE_CHECK, "requiredCheckEnforced": enforced,
        "bypassActors": matched[0]["bypassActors"] if matched else ["<no matching active ruleset>"],
        "rulesets": matched, "source": "github_rest:/repos/{repo}/rulesets/{id}",
    }


def boundary_fact(*, head_sha: str, base_sha: str, branch_policy_exit: int, changed_boundary_exit: int,
                  impact_plan_digest: str, changed_paths_digest: str) -> dict[str, Any]:
    passed = branch_policy_exit == 0 and changed_boundary_exit == 0
    return {
        "schema": _AUTHORITY_SCHEMAS["changedBoundary"], "status": "passed" if passed else "failed",
        "headSha": _sha(head_sha, "headSha"), "baseSha": _sha(base_sha, "baseSha"),
        "verifiedHeadSha": _sha(head_sha, "headSha"), "verifiedBaseSha": _sha(base_sha, "baseSha"),
        "secretStatus": "passed" if changed_boundary_exit == 0 else "failed",
        "generatedBoundaryStatus": "passed" if changed_boundary_exit == 0 else "failed",
        "branchPolicyStatus": "passed" if branch_policy_exit == 0 else "failed",
        "impactPlanDigest": impact_plan_digest, "changedPathsDigest": changed_paths_digest,
        "source": "verify_git_branch_policy + detect_ci_impacted_scopes + verify_ci_changed_boundary",
    }


def required_evidence_fact(*, head_sha: str, base_sha: str, evidence: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    items = [{"ref": _text(item.get("ref"), "evidence.ref"), "digest": _text(item.get("digest"), "evidence.digest")} for item in evidence]
    if not items:
        raise PromotionEvidenceError("PROMOTION.EVIDENCE_INVALID", "required evidence cannot be empty")
    return {
        "schema": _REQUIRED_EVIDENCE_SCHEMA, "status": "passed",
        "headSha": _sha(head_sha, "headSha"), "baseSha": _sha(base_sha, "baseSha"),
        "evidence": sorted(items, key=lambda item: (item["ref"], item["digest"])),
    }


def write_hosted_authority_facts(*, evidence_root: Path, head_sha: str, base_sha: str, reviews_file: Path, threads_file: Path,
                                 rulesets_file: Path, author_login: str, branch_policy_exit: int, changed_boundary_exit: int,
                                 impact_plan_digest: str, changed_paths_digest: str,
                                 required_evidence: Sequence[Mapping[str, str]]) -> dict[str, dict[str, str]]:
    root = evidence_root.resolve()
    reviews = _load_json(reviews_file, "reviews")
    threads = _load_json(threads_file, "threads")
    rulesets = _load_json(rulesets_file, "rulesets")
    if not isinstance(reviews, list) or not isinstance(threads, list) or not isinstance(rulesets, list):
        raise PromotionEvidenceError("PROMOTION.AUTHORITY_INVALID", "hosted readback files must be JSON arrays")
    facts = {
        "approval": approval_fact(reviews=reviews, head_sha=head_sha, base_sha=base_sha, author_login=author_login),
        "threads": threads_fact(threads=threads, head_sha=head_sha, base_sha=base_sha),
        "ruleset": ruleset_fact(rulesets=rulesets, head_sha=head_sha, base_sha=base_sha),
        "boundary": boundary_fact(head_sha=head_sha, base_sha=base_sha, branch_policy_exit=branch_policy_exit,
                                  changed_boundary_exit=changed_boundary_exit, impact_plan_digest=impact_plan_digest,
                                  changed_paths_digest=changed_paths_digest),
        "required-evidence": required_evidence_fact(head_sha=head_sha, base_sha=base_sha, evidence=required_evidence),
    }
    written: dict[str, dict[str, str]] = {}
    for name, fact in facts.items():
        fact = {**fact, "recordedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        path = root / "promotion" / "authority" / head_sha / f"{name}.json"
        _write_once(path, fact)
        written[name] = {"ref": path.relative_to(root).as_posix(), "digest": digest(path), "status": fact["status"]}
    return written


# --------------------------------------------------------------------------- CLI


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    publish = sub.add_parser("publish-oci-bundle")
    publish.add_argument("--bundle-root", required=True, type=Path)
    publish.add_argument("--repository", required=True)
    publish.add_argument("--transport-tag", required=True)
    materialize = sub.add_parser("materialize-oci-bundle")
    materialize.add_argument("--ref", required=True)
    materialize.add_argument("--output-dir", required=True, type=Path)
    authority = sub.add_parser("hosted-authority")
    authority.add_argument("--evidence-root", required=True, type=Path)
    authority.add_argument("--head-sha", required=True)
    authority.add_argument("--base-sha", required=True)
    authority.add_argument("--reviews-file", required=True, type=Path)
    authority.add_argument("--threads-file", required=True, type=Path)
    authority.add_argument("--rulesets-file", required=True, type=Path)
    authority.add_argument("--author-login", required=True)
    authority.add_argument("--branch-policy-exit", required=True, type=int)
    authority.add_argument("--changed-boundary-exit", required=True, type=int)
    authority.add_argument("--impact-plan-digest", required=True)
    authority.add_argument("--changed-paths-digest", required=True)
    authority.add_argument("--required-evidence", action="append", required=True, help="ref=digest（bundle 内路径）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "publish-oci-bundle":
            result: object = publish_oci_bundle(bundle_root=args.bundle_root, repository=args.repository, transport_tag=args.transport_tag)
        elif args.command == "materialize-oci-bundle":
            result = materialize_oci_bundle(exact_ref=args.ref, output_dir=args.output_dir)
        elif args.command == "hosted-authority":
            evidence = []
            for item in args.required_evidence:
                ref, _, item_digest = item.partition("=")
                evidence.append({"ref": ref, "digest": item_digest})
            result = write_hosted_authority_facts(
                evidence_root=args.evidence_root, head_sha=args.head_sha, base_sha=args.base_sha,
                reviews_file=args.reviews_file, threads_file=args.threads_file, rulesets_file=args.rulesets_file,
                author_login=args.author_login, branch_policy_exit=args.branch_policy_exit,
                changed_boundary_exit=args.changed_boundary_exit, impact_plan_digest=args.impact_plan_digest,
                changed_paths_digest=args.changed_paths_digest, required_evidence=evidence,
            )
        else:
            raise PromotionEvidenceError("PROMOTION.INVALID", f"unknown command {args.command}")
    except (OSError, PromotionEvidenceError) as error:
        code = error.code if isinstance(error, PromotionEvidenceError) else "PROMOTION.IO_ERROR"
        print(json.dumps({"terminal": "GATE_BLOCK", "code": code, "detail": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
