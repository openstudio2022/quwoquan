#!/usr/bin/env python3
"""Clean-candidate adapter binding Code Health Delta to Delivery impact identity."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.impact_planner_core import canonical_digest, validate_exact_sha
from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.render import render_candidate


def verify_delivery(
    repo: Path,
    *,
    base_sha: str,
    head_sha: str,
    expected_path_digest: str,
    expected_impact_plan_digest: str,
    policy_path: Path | None = None,
    write_report: bool = True,
) -> tuple[dict[str, Any], Path, str]:
    """Recompute one immutable candidate and bind it to canonical impact identity."""
    repo = repo.resolve()
    base_sha = validate_exact_sha(base_sha, label="base_sha")
    head_sha = validate_exact_sha(head_sha, label="head_sha")
    if not expected_impact_plan_digest.startswith("sha256:"):
        raise ValueError("Delivery impact plan digest is not canonical")
    report = analyze_delta(
        repo,
        base=base_sha,
        head=head_sha,
        policy_path=(policy_path or repo / "quwoquan_ops/policies/code_health_policy.yaml"),
        mode="full",
    )
    if report["changedPathsDigest"] != expected_path_digest:
        raise ValueError("changed-path digest differs from canonical Delivery impact plan")
    identity = canonical_digest(
        {
            "impactPlanDigest": expected_impact_plan_digest,
            "changedPathsDigest": expected_path_digest,
            "policyDigest": report["policyDigest"],
            "implementationDigest": report["implementationDigest"],
            "toolchainDigest": report["evidenceFingerprint"]["digest_payload"]["execution"]["toolchain_digest"],
        }
    )
    fingerprint = report["evidenceFingerprint"]["digest"].removeprefix("sha256:")
    output = repo / ".qwq_output/env/repo/runs/code-health" / fingerprint / "report.json"
    if write_report:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report, output, identity


def validate_delivery_report(
    repo: Path, report: dict[str, Any], *, base_sha: str, head_sha: str,
    expected_path_digest: str, expected_impact_plan_digest: str,
) -> None:
    """使用同一 engine 重验完整报告，拒绝伪造 PASS、旧工具/策略和窄范围证据。"""
    if (report.get("schema") != "quwoquan.code-health-delta"
            or report.get("mode") != "full" or report.get("candidateSource") != "commit"
            or report.get("baseSha") != base_sha or report.get("headSha") != head_sha):
        raise ValueError("health report must bind the current full commit range")
    current, _, _ = verify_delivery(
        repo, base_sha=base_sha, head_sha=head_sha,
        expected_path_digest=expected_path_digest,
        expected_impact_plan_digest=expected_impact_plan_digest,
        write_report=False,
    )
    # generatedAt 是非身份元数据；其他全部字段（含 findings 与 fingerprint）必须等值。
    if ({key: value for key, value in report.items() if key != "generatedAt"}
            != {key: value for key, value in current.items() if key != "generatedAt"}):
        raise ValueError("health report differs from current canonical full measurement")
    if report.get("terminal") == "GATE_BLOCK":
        raise ValueError("health report contains GATE_BLOCK")


def promotion_health_plan(repository: Path, base: str, head: str) -> dict[str, Any]:
    """完整 promotion range，不以最后一次 publish 的 ImpactPlan 替代。"""
    from quwoquan_ops.ci.impact_planner_core import build_delivery_impact_plan
    from quwoquan_ops.ci.promotion_evidence import _changed_paths, _git

    tree = _git(repository, "rev-parse", f"{head}^{{tree}}")
    return build_delivery_impact_plan(
        _changed_paths(repository, base, head), base_sha=base, source_sha=head,
        source_tree_digest=f"sha1:{tree}", execution_profile="promotion",
    )


def read_review_evidence(root: Path, exact: dict[str, str]) -> tuple[dict[str, Any], dict[str, str]]:
    """保持已有 Review producer 原始序列化字节；不重新编码签发过的 report/receipt。"""
    from quwoquan_ops.ci.promotion_evidence import PromotionEvidenceError, _valid_exact_identity, digest
    from quwoquan_ops.cli.lib.descriptor_safe_io import read_repo_relative_regular_single_link

    if not _valid_exact_identity(exact):
        raise PromotionEvidenceError("PROMOTION.HEALTH_INVALID", "invalid exact Review evidence ref")
    try:
        raw = read_repo_relative_regular_single_link(root, exact["ref"])
        if digest(raw) != exact["digest"]:
            raise PromotionEvidenceError("PROMOTION.STALE", "required Review evidence bytes drifted")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Review evidence must be an object")
        return value, exact
    except (OSError, ValueError) as exc:
        if isinstance(exc, PromotionEvidenceError):
            raise
        raise PromotionEvidenceError("PROMOTION.HEALTH_INVALID", str(exc)) from exc


def _review_document(documents: dict, ref: str) -> tuple[str, dict]:
    if not isinstance(ref, str) or not ref:
        raise ValueError("Review exact dependency ref must be nonempty")
    if ref not in documents:
        raise ValueError(f"Review exact dependency missing: {ref}")
    return ref, documents[ref]


def _review_pairs(root: Path, documents: dict, identities: list, field: str) -> tuple[list, dict]:
    from quwoquan_ops.ci.promotion_evidence import digest
    from quwoquan_ops.cli.lib.descriptor_safe_io import read_repo_relative_regular_single_link

    pairs, exact_bytes = [], {}
    for identity in identities:
        ref = identity[field]
        path, value = _review_document(documents, ref)
        raw = read_repo_relative_regular_single_link(root, path)
        if digest(raw) != identity["canonical_bytes_sha256"]:
            raise ValueError(f"Review exact identity drifted: {ref}")
        exact_bytes[ref] = raw
        pairs.append((ref, value))
    return pairs, exact_bytes


def _review_health_binding(root: Path, documents: dict, pairs: list, plan: dict, report: dict) -> None:
    from quwoquan_ops.ci.promotion_evidence import digest
    from quwoquan_ops.cli import review_consolidator

    if (plan["head_sha"] != report["headSha"] or plan["merge_base_sha"] != report["baseSha"]
            or plan["changed_paths"] != report["changedPaths"]):
        raise ValueError("Review plan does not bind full promotion range/paths")
    artifacts = []
    for _, receipt in pairs:
        review_consolidator.evidence_runner.require_admission_eligible(receipt, label="promotion Review evidence")
        metadata = receipt["execution_fingerprint"]["captured_metadata"]
        path, exact_plan = _review_document(documents, metadata["plan_input_ref"])
        if exact_plan != plan or digest(root / path) != metadata["plan_bytes_sha256"]:
            raise ValueError("Review plan bytes differ from named receipt input")
        artifacts.extend(entry["artifact"] for entry in receipt["evidence"]
            if (entry.get("artifact") or {}).get("kind") == "code-health-report-v1")
    matched = False
    for artifact in artifacts:
        path, original = _review_document(documents, artifact["ref"])
        if digest(root / path) != artifact["canonical_bytes_sha256"]:
            raise ValueError("Review original report exact bytes drifted")
        expected = {"base_sha": report["baseSha"], "head_sha": report["headSha"],
            "findings": report["findings"], "changed_paths_digest": report["changedPathsDigest"]}
        matched |= original == report and all(artifact.get(key) == value for key, value in expected.items())
    if not matched:
        raise ValueError("Review artifact does not bind the original full report/findingId")


def validate_promotion_review(
    repository: Path, root: Path, documents: dict[str, dict[str, Any]], report: dict[str, Any],
) -> None:
    """装载 existing Review 链；不接受独立 PASS 或无原始 report 的裁决。"""
    from quwoquan_ops.ci.promotion_evidence import PromotionEvidenceError
    from quwoquan_ops.cli import review_consolidator

    consolidations = [(ref, value) for ref, value in documents.items()
        if "reviewer_result_identities" in value and "evidence_identities" in value]
    if len(consolidations) != 1:
        raise PromotionEvidenceError("PROMOTION.HEALTH_DISPOSITION_REQUIRED", "exactly one existing Review consolidation is required")
    consolidation_ref, consolidation = consolidations[0]
    # 唯一 hosted transport 目录；其余模式使用根内 canonical ref，不用 suffix 反猜路径。
    prefix = "qualification-bundle/" if consolidation_ref.startswith("qualification-bundle/") else ""
    if prefix:
        root = root / "qualification-bundle"
        documents = {ref[len(prefix):]: value for ref, value in documents.items() if ref.startswith(prefix)}
    try:
        evidence_pairs, exact_evidence = _review_pairs(root, documents, consolidation["evidence_identities"], "receipt_ref")
        reviewer_pairs, exact_results = _review_pairs(root, documents, consolidation["reviewer_result_identities"], "result_ref")
        plans = [value for value in documents.values() if "candidate_evidence_identity" in value
                 and "reviewers" in value and "owner_identity" in value]
        if len(plans) != 1:
            raise ValueError("exactly one existing Review plan is required")
        _review_health_binding(root, documents, evidence_pairs, plans[0], report)
        review_consolidator.validate_exact_consolidation(
            consolidation, plan=plans[0], evidence_pairs=evidence_pairs,
            reviewer_pairs=reviewer_pairs, exact_bytes_by_ref={**exact_evidence, **exact_results},
            source_repository=repository, dependency_root=root,
        )
    except (KeyError, TypeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise PromotionEvidenceError("PROMOTION.HEALTH_DISPOSITION_INVALID", str(exc)) from exc


def verify_promotion_health_evidence(
    repository: Path, root: Path, fact: dict[str, Any], *, base: str, head: str,
) -> None:
    from quwoquan_ops.ci.promotion_evidence import PromotionEvidenceError

    refs = fact.get("evidence")
    documents = {}
    if not isinstance(refs, list) or not refs:
        raise PromotionEvidenceError("PROMOTION.HEALTH_MISSING", "required evidence lacks full health report")
    reports = []
    seen: set[str] = set()
    for exact in refs:
        payload, normalized = read_review_evidence(root, exact)
        if normalized["ref"] in seen:
            raise PromotionEvidenceError("PROMOTION.HEALTH_INVALID", "duplicate required evidence")
        seen.add(normalized["ref"])
        documents[normalized["ref"]] = payload
        if payload.get("schema") == "quwoquan.code-health-delta":
            reports.append(payload)
    if len(reports) != 1:
        raise PromotionEvidenceError("PROMOTION.HEALTH_MISSING", "exactly one full health report is required")
    try:
        plan = promotion_health_plan(repository, base, head)
        if (fact.get("headTree") != plan["source_tree_digest"].removeprefix("sha1:")
                or fact.get("impactPlanDigest") != plan["plan_digest"]
                or fact.get("changedPathsDigest") != plan["changed_paths_digest"]):
            raise ValueError("health evidence tree or promotion ImpactPlan drifted")
        validate_delivery_report(
            repository, reports[0], base_sha=base, head_sha=head,
            expected_path_digest=plan["changed_paths_digest"],
            expected_impact_plan_digest=plan["plan_digest"],
        )
    except (ValueError, OSError) as exc:
        raise PromotionEvidenceError("PROMOTION.HEALTH_INVALID", str(exc)) from exc
    if reports[0]["terminal"] == "PR_WARN":
        validate_promotion_review(repository, root, documents, reports[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--expected-path-digest", required=True)
    parser.add_argument("--expected-impact-plan-digest", required=True)
    parser.add_argument(
        "--summary-markdown", type=Path,
        help="Also write the Markdown projection (blockers, recovery, debt delta) for the PR step summary",
    )
    args = parser.parse_args()
    try:
        report, output, identity = verify_delivery(
            ROOT,
            base_sha=args.base_sha,
            head_sha=args.head_sha,
            expected_path_digest=args.expected_path_digest,
            expected_impact_plan_digest=args.expected_impact_plan_digest,
        )
        markdown = render_candidate(report)
        if args.summary_markdown is not None:
            args.summary_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.summary_markdown.write_text(markdown, encoding="utf-8")
        print(markdown, end="")
        print(f"code-health-delivery: {report['terminal']} identity={identity} output={output}")
        return 1 if report["terminal"] == "GATE_BLOCK" else 0
    except Exception as exc:
        print(f"code-health-delivery: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
