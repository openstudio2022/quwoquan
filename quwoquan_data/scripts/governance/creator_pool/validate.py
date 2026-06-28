"""Creator pool validate stage."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.diversity import diversity_report
from _common.creator_pool.io import (
    iter_creator_refs,
    stage_gate_path,
    write_gate,
    write_stage_result,
)
from _common.creator_pool.persona_dedup import duplicate_persona_p95
from _common.creator_pool.persona_rubric import archetype_coverage, evaluate_persona_rubric, persona_rubric_pass_rate
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, creator_pool_stage_dir, now_iso


def run_validate(*, vertical: str, batch_id: str, dry_run: bool = False) -> dict[str, Any]:
    plan = read_json(creator_pool_shared_dir(vertical, batch_id) / "creator_pool_plan.json")
    live_mode = bool(plan.get("liveMode"))
    matrix_path = creator_pool_shared_dir(vertical, batch_id) / "diversity_matrix.yaml"
    import yaml

    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) if matrix_path.is_file() else {}
    topic_min = int(matrix.get("topicCoverageMin") or 12) if live_mode else 4
    bundles: list[dict[str, Any]] = []
    validated = 0
    for creator_ref in iter_creator_refs(vertical, batch_id):
        bundle_path = creator_pool_stage_dir(vertical, batch_id, creator_ref, "4.materialize") / "creator_bundle.json"
        if not bundle_path.is_file():
            write_gate(
                stage_gate_path(vertical, batch_id, creator_ref, "5.validate", "review_gate.json"),
                gate_id="review",
                passed=False,
                issues=["missing creator_bundle.json"],
            )
            continue
        bundle = read_json(bundle_path)
        enrich_meta_path = creator_pool_stage_dir(vertical, batch_id, creator_ref, "3.enrich") / "enrich_meta.json"
        enrich_meta = read_json(enrich_meta_path) if enrich_meta_path.is_file() else {}
        issues = _validate_bundle(bundle, enrich_meta=enrich_meta, live_mode=live_mode)
        rubric_ok, rubric_issues = evaluate_persona_rubric(
            bundle,
            enrich_meta=enrich_meta,
            live_mode=live_mode,
            peer_bundles=None,
        )
        if not rubric_ok:
            issues.extend(rubric_issues)
        passed = not issues
        stage_dir = creator_pool_stage_dir(vertical, batch_id, creator_ref, "5.validate")
        stage_dir.mkdir(parents=True, exist_ok=True)
        provenance = bundle.get("provenance") or {}
        write_json(stage_dir / "review.json", {"passed": passed, "issues": issues})
        write_json(
            stage_dir / "provenance.json",
            {
                "derivationPolicy": provenance.get("derivationPolicy"),
                "citedSourcePaths": provenance.get("citedSourcePaths") or [],
                "coverage": 1.0 if provenance.get("citedSourcePaths") else 0.0,
            },
        )
        write_json(stage_dir / "finalization_report.json", {"creatorRef": creator_ref, "readyForSeed": passed})
        write_gate(
            stage_gate_path(vertical, batch_id, creator_ref, "5.validate", "review_gate.json"),
            gate_id="review",
            passed=passed,
            issues=issues,
        )
        write_stage_result(vertical, batch_id, creator_ref, "5.validate", {"status": "ok" if passed else "failed"})
        if passed:
            validated += 1
            bundles.append(bundle)
    div = diversity_report(bundles, vertical=vertical, batch_id=batch_id)
    dedup_p95 = duplicate_persona_p95(bundles)
    rubric_rate = persona_rubric_pass_rate(bundles, live_mode=live_mode)
    arch_cov = archetype_coverage(bundles)
    shared = creator_pool_shared_dir(vertical, batch_id)
    write_json(shared / "diversity_report.json", div)
    write_json(shared / "persona_dedup_report.json", {"duplicatePersonaP95": dedup_p95})
    write_json(
        shared / "persona_rubric_report.json",
        {
            "personaRubricPassRate": rubric_rate,
            "archetypeCoverage": arch_cov,
            "minArchetypeCoverage": 6,
        },
    )
    batch_issues: list[str] = []
    if live_mode and div.get("quotaFillRate", 0) < 1.0:
        batch_issues.append(f"quotaFillRate {div.get('quotaFillRate')} < 1.0")
    if live_mode and float(div.get("entropy") or 0) < 0.85:
        batch_issues.append(f"entropy {div.get('entropy')} < 0.85")
    if live_mode and int(div.get("topicCoverageCount") or 0) < topic_min:
        batch_issues.append(f"topicCoverage {div.get('topicCoverageCount')} < {topic_min}")
    if dedup_p95 >= 0.75:
        batch_issues.append(f"duplicatePersonaP95 {dedup_p95} >= 0.75")
    if live_mode and rubric_rate < 0.95:
        batch_issues.append(f"personaRubricPassRate {rubric_rate} < 0.95")
    if live_mode and arch_cov < 6:
        batch_issues.append(f"archetypeCoverage {arch_cov} < 6")
    rollup = {
        "schemaVersion": "quwoquan_data.creator_rollup_report/1",
        "batchId": batch_id,
        "vertical": vertical,
        "counts": {
            "planned": len(iter_creator_refs(vertical, batch_id)),
            "validated": validated,
        },
        "funnel": {
            "reviewGatePassRate": validated / max(len(iter_creator_refs(vertical, batch_id)), 1),
            "provenanceCoverage": sum(
                1 for b in bundles if (b.get("provenance") or {}).get("citedSourcePaths")
            )
            / max(len(bundles), 1),
            "tagResolveRate": 1.0 if validated else 0.0,
            "duplicatePersonaP95": dedup_p95,
            "personaRubricPassRate": rubric_rate,
            "archetypeCoverage": arch_cov,
        },
        "diversityReport": div,
        "generatedAt": now_iso(),
    }
    write_json(shared / "creator_rollup_report.json", rollup)
    gate_passed = validated == len(iter_creator_refs(vertical, batch_id)) and not batch_issues
    write_gate(shared / "gate_report.json", gate_id="batch_validate", passed=gate_passed, issues=batch_issues)
    return {"validated": validated, "diversity": div, "duplicatePersonaP95": dedup_p95, "dryRun": dry_run}


def _validate_bundle(bundle: dict[str, Any], *, enrich_meta: dict[str, Any], live_mode: bool) -> list[str]:
    issues: list[str] = []
    for field in ("creatorProfileId", "subAccountId", "authorId", "creatorArchetype"):
        if not str(bundle.get(field) or "").strip():
            issues.append(f"missing {field}")
    provenance = bundle.get("provenance") or {}
    if provenance.get("derivationPolicy") != "derivative_persona_v1":
        issues.append("invalid derivationPolicy")
    if live_mode and provenance.get("sourceKind") == "fixture_synthetic":
        issues.append("fixture_synthetic not allowed in live batch")
    cited = provenance.get("citedSourcePaths") or enrich_meta.get("citedSourcePaths") or []
    if live_mode and not cited:
        issues.append("missing citedSourcePaths")
    profile = bundle.get("profile") or {}
    for field in ("displayName", "userHandle", "bio", "headline"):
        if not str(profile.get(field) or "").strip():
            issues.append(f"missing profile.{field}")
    content = bundle.get("content") or {}
    if not (content.get("disclosure") or {}).get("displayText"):
        issues.append("missing disclosure")
    return issues
