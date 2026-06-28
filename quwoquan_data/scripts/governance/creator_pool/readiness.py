"""Creator-scale-readiness gate (mirrors scale-readiness for creator pools)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from _common.creator_pool.io import (
    artifacts_readiness_path,
    iter_creator_refs,
    read_review_gate,
    repo_seed_fixture_dir,
)
from _common.creator_pool.persona_dedup import duplicate_persona_p95
from _common.creator_pool.persona_rubric import RUBRIC
from _common.io import read_json, write_json
from _common.paths import REPO_ROOT, creator_pool_shared_dir, now_iso
from governance.creator_pool.seed import check_scale10_prerequisite


def build_creator_readiness_report(
    *,
    vertical: str,
    batch_id: str,
    target: int,
    mode: str = "trial",
    min_pass_rate: float = 1.0,
) -> dict[str, Any]:
    refs = iter_creator_refs(vertical, batch_id)
    planned = len(refs)
    passed = sum(1 for ref in refs if _review_passed(vertical, batch_id, ref))
    pass_rate = passed / max(planned, 1)
    shared = creator_pool_shared_dir(vertical, batch_id)
    plan = read_json(shared / "creator_pool_plan.json") if (shared / "creator_pool_plan.json").is_file() else {}
    rollup_path = shared / "creator_rollup_report.json"
    rollup = read_json(rollup_path) if rollup_path.is_file() else {}
    diversity = (rollup.get("diversityReport") if isinstance(rollup, dict) else {}) or {}
    dedup_path = shared / "persona_dedup_report.json"
    dedup_report = read_json(dedup_path) if dedup_path.is_file() else {}
    rubric_path = shared / "persona_rubric_report.json"
    rubric_report = read_json(rubric_path) if rubric_path.is_file() else {}
    dedup_p95 = float(
        dedup_report.get("duplicatePersonaP95")
        or (rollup.get("funnel") or {}).get("duplicatePersonaP95")
        or 0.0
    )
    seed_ok = (shared / "seed_handoff.json").is_file()
    scale10_ok = check_scale10_prerequisite(target)
    min_bucket = 0.5 if target <= 10 else 1.0
    min_entropy = 0.6 if target <= 10 else 0.85
    bucket_fill = float(diversity.get("quotaFillRate") or diversity.get("minBucketFillRate") or 0.0)
    entropy = float(diversity.get("entropy") or 0.0)
    topic_count = int(diversity.get("topicCoverageCount") or 0)
    bucket_values = list((diversity.get("bucketFill") or {}).values())
    min_bucket_count = min(bucket_values) if bucket_values else 0
    synthetic_ratio = _synthetic_ratio(vertical, batch_id)
    rubric_rate = float(
        rubric_report.get("personaRubricPassRate")
        or (rollup.get("funnel") or {}).get("personaRubricPassRate")
        or pass_rate
    )
    merge_ok = (repo_seed_fixture_dir() / f"creator_{vertical}_batch100.seed.json").is_file()
    checks = {
        "creatorsValidatedRatio": pass_rate,
        "workflowAllReachedValidate": pass_rate >= min_pass_rate,
        "reviewGatePassRate": pass_rate,
        "provenanceCoverage": float((rollup.get("funnel") or {}).get("provenanceCoverage") or pass_rate),
        "tagResolveRate": float((rollup.get("funnel") or {}).get("tagResolveRate") or pass_rate),
        "duplicatePersonaP95": dedup_p95,
        "personaRubricPassRate": rubric_rate,
        "diversityMinBucketFill": bucket_fill,
        "diversityEntropy": entropy,
        "topicCoverageCount": topic_count,
        "seedHandoffOk": seed_ok,
        "contentBindSmokePass": 3 if target <= 10 else 10,
        "scale10PrerequisiteOk": scale10_ok,
        "syntheticSourceRatio": synthetic_ratio,
        "userPoolMergeOk": merge_ok,
    }
    commercial_checks = {
        "quality": {
            "personaComplete": pass_rate >= min_pass_rate,
            "dedupP95BelowThreshold": dedup_p95 < 0.75,
            "personaRubricPassRate": rubric_rate >= float(RUBRIC["commercialPassRate"] if mode == "commercial" else RUBRIC["trialPassRate"]),
            "agentEnrichEvidence": bool(plan.get("liveMode")) or not plan.get("fixtureMode"),
        },
        "stability": {
            "seedHandoffPresent": seed_ok,
            "userPoolMergePresent": merge_ok,
            "idempotentValidate": pass_rate >= min_pass_rate,
        },
        "diversity": {
            "quotaFillRate": bucket_fill >= min_bucket,
            "entropy": entropy >= min_entropy,
            "topicCoverage": topic_count >= (12 if target >= 100 else 4),
        },
        "representativeness": {
            "liveAcquire": bool(plan.get("liveMode")),
            "zeroSyntheticRatio": synthetic_ratio == 0.0 if mode == "commercial" else True,
            "provenanceCited": float((rollup.get("funnel") or {}).get("provenanceCoverage") or 0) >= 0.99,
        },
    }
    issues: list[str] = []
    if pass_rate < min_pass_rate:
        issues.append(f"reviewGatePassRate {pass_rate:.2f} < {min_pass_rate}")
    if target <= 10:
        if min_bucket_count < 1:
            issues.append(f"diversity min bucket count {min_bucket_count} < 1")
    elif bucket_fill < min_bucket:
        issues.append(f"diversityQuotaFill {bucket_fill:.2f} < {min_bucket}")
    if entropy < min_entropy and target >= 100:
        issues.append(f"diversityEntropy {entropy:.2f} < {min_entropy}")
    if target > 10 and not scale10_ok:
        issues.append("missing scale10 prerequisite go")
    if dedup_p95 >= 0.75:
        issues.append(f"duplicatePersonaP95 {dedup_p95:.2f} >= 0.75")
    min_rubric = float(RUBRIC["commercialPassRate"] if mode == "commercial" else RUBRIC["trialPassRate"])
    if rubric_rate < min_rubric:
        issues.append(f"personaRubricPassRate {rubric_rate:.2f} < {min_rubric}")
    if mode == "commercial":
        if bool(plan.get("fixtureMode")):
            issues.append("fixtureMode batch cannot pass commercial readiness")
        if synthetic_ratio > 0:
            issues.append(f"syntheticSourceRatio {synthetic_ratio} > 0")
        if not seed_ok:
            issues.append("missing seed handoff for commercial mode")
        if topic_count < 12 and target >= 100:
            issues.append(f"topicCoverage {topic_count} < 12")
        api_evidence = REPO_ROOT / "quwoquan_service/services/user-service/tests/local_contract/creator_pool_seed_contract__local_contract_test.go"
        if not api_evidence.is_file():
            issues.append("missing creator_pool seed contract test evidence")
    passed_all = not issues
    return {
        "schemaVersion": "quwoquan_data.creator_readiness_report/1",
        "vertical": vertical,
        "batchId": batch_id,
        "target": target,
        "mode": mode,
        "decision": "go" if passed_all else "no_go",
        "passed": passed_all,
        "checks": checks,
        "commercialChecks": commercial_checks,
        "issues": issues,
        "generatedAt": now_iso(),
    }


def write_creator_readiness_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, report)


def _review_passed(vertical: str, batch_id: str, creator_ref: str) -> bool:
    gate = read_review_gate(vertical, batch_id, creator_ref)
    return bool(gate and gate.get("decision") == "passed")


def _synthetic_ratio(vertical: str, batch_id: str) -> float:
    from _common.paths import creator_pool_stage_dir

    refs = iter_creator_refs(vertical, batch_id)
    if not refs:
        return 0.0
    synthetic = 0
    for ref in refs:
        bundle_path = creator_pool_stage_dir(vertical, batch_id, ref, "4.materialize") / "creator_bundle.json"
        if not bundle_path.is_file():
            continue
        bundle = read_json(bundle_path)
        if (bundle.get("provenance") or {}).get("sourceKind") == "fixture_synthetic":
            synthetic += 1
    return synthetic / max(len(refs), 1)
