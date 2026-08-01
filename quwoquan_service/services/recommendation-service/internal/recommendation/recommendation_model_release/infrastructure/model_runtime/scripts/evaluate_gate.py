#!/usr/bin/env python3
"""Pure quality gate for immutable model-release evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from time_utils import utc_iso


AUC_ABSOLUTE_MIN = 0.65
NDCG_ABSOLUTE_MIN = 0.15
FUSED_AUC_ABSOLUTE_MIN = 0.60
AUC_RELATIVE_DROP_MAX = 0.02
NDCG_RELATIVE_DROP_MAX = 0.03

DRY_RUN_AUC_MIN = 0.50
DRY_RUN_NDCG_MIN = 0.05
DRY_RUN_FUSED_AUC_MIN = 0.45


def evaluate_metrics(
    *,
    scenario: str,
    candidate_metrics: dict[str, Any],
    active_metrics: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> tuple[str, str, dict[str, Any]]:
    active = active_metrics or {}
    auc_min = DRY_RUN_AUC_MIN if dry_run else AUC_ABSOLUTE_MIN
    ndcg_min = DRY_RUN_NDCG_MIN if dry_run else NDCG_ABSOLUTE_MIN
    fused_min = DRY_RUN_FUSED_AUC_MIN if dry_run else FUSED_AUC_ABSOLUTE_MIN

    candidate_auc = float(candidate_metrics.get("auc") or 0)
    candidate_ndcg = float(candidate_metrics.get("ndcg_20") or 0)
    candidate_fused = float(candidate_metrics.get("fused_auc") or 0)
    active_auc = float(active.get("auc") or 0)
    active_ndcg = float(active.get("ndcg_20") or 0)
    active_fused = float(active.get("fused_auc") or 0)
    is_multiobjective = scenario.endswith("_multiobjective") or (
        candidate_fused > 0 and candidate_auc == 0
    )
    diversity_keys = (
        "item_coverage_at_20",
        "author_repeat_rate_at_20",
        "topic_entropy_at_20",
        "author_hhi_at_20",
        "geo_coverage_at_20",
        "distinct_authors_at_20",
        "distinct_topics_at_20",
        "distinct_geo_buckets_at_20",
    )
    diversity = {
        key: candidate_metrics[key]
        for key in diversity_keys
        if key in candidate_metrics
    }
    failures: list[str] = []
    if candidate_auc == 0 and candidate_ndcg == 0 and candidate_fused == 0:
        failures.append("all evaluation metrics are zero")
    if 0 < candidate_auc < auc_min:
        failures.append(f"AUC {candidate_auc:.4f} < absolute min {auc_min}")
    if 0 < candidate_ndcg < ndcg_min:
        failures.append(f"NDCG@20 {candidate_ndcg:.4f} < absolute min {ndcg_min}")
    if 0 < candidate_fused < fused_min:
        failures.append(
            f"fused_auc {candidate_fused:.4f} < absolute min {fused_min}"
        )
    if is_multiobjective and active_fused > 0 and candidate_fused > 0:
        drop = active_fused - candidate_fused
        if drop > AUC_RELATIVE_DROP_MAX:
            failures.append(
                f"fused_auc dropped {drop:.4f} vs active (max {AUC_RELATIVE_DROP_MAX})"
            )
    elif active_auc > 0 and candidate_auc > 0:
        drop = active_auc - candidate_auc
        if drop > AUC_RELATIVE_DROP_MAX:
            failures.append(
                f"AUC dropped {drop:.4f} vs active (max {AUC_RELATIVE_DROP_MAX})"
            )
    if active_ndcg > 0 and candidate_ndcg > 0:
        drop = active_ndcg - candidate_ndcg
        if drop > NDCG_RELATIVE_DROP_MAX:
            failures.append(
                f"NDCG@20 dropped {drop:.4f} vs active (max {NDCG_RELATIVE_DROP_MAX})"
            )

    if failures:
        return "blocked", "; ".join(failures), diversity
    if is_multiobjective:
        return "pass", f"fused_auc={candidate_fused:.4f}", diversity
    return (
        "pass",
        f"AUC={candidate_auc:.4f} NDCG={candidate_ndcg:.4f}",
        diversity,
    )


def verification_evidence(
    *,
    release_id: str,
    scenario: str,
    model_digest: str,
    artifact_uri: str,
    feature_contract_digest: str,
    candidate_metrics: dict[str, Any],
    active_metrics: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    status, reason, diversity = evaluate_metrics(
        scenario=scenario,
        candidate_metrics=candidate_metrics,
        active_metrics=active_metrics,
        dry_run=dry_run,
    )
    return {
        "releaseId": release_id,
        "scenario": scenario,
        "modelDigest": model_digest,
        "artifactUri": artifact_uri,
        "featureContractDigest": feature_contract_digest,
        "evaluationMetrics": candidate_metrics,
        "activeEvaluationMetrics": active_metrics or {},
        "status": status,
        "reason": reason,
        "diversityMetrics": diversity,
        "evaluatedAt": utc_iso(),
    }


def _load_evidence(path: str) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("evidence must be a JSON object")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Model release quality gate")
    parser.add_argument("--candidate-evidence", required=True)
    parser.add_argument("--active-evidence", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use non-commercial thresholds for local algorithm iteration only",
    )
    args = parser.parse_args()

    candidate = _load_evidence(args.candidate_evidence)
    active = _load_evidence(args.active_evidence) if args.active_evidence else {}
    metrics = candidate.get("evaluationMetrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("candidate evidence requires evaluationMetrics")
    active_metrics = active.get("evaluationMetrics") or {}
    evidence = verification_evidence(
        release_id=str(candidate.get("releaseId") or ""),
        scenario=str(candidate.get("scenario") or ""),
        model_digest=str(candidate.get("modelDigest") or ""),
        artifact_uri=str(candidate.get("artifactUri") or ""),
        feature_contract_digest=str(candidate.get("featureContractDigest") or ""),
        candidate_metrics=metrics,
        active_metrics=active_metrics,
        dry_run=args.dry_run,
    )
    Path(args.out).write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[evaluate_gate] {evidence['status'].upper()}: {evidence['reason']}")
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
