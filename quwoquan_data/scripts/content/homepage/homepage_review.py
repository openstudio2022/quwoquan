"""Homepage draft, provenance, review attestation, and evidence sidecars."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.article_package import compute_document_sha256, sha256_file, sha256_text
from governance.coverage.entity_extract import entity_ref
from core.entity_object import write_entity_object_index
from content.execution.runtime_contract import canonical_sha256, stage_execution_context
from core.io import read_json, write_json
from core.schema import assert_valid
from core.paths import (
    STAGE_DRAFT,
    STAGE_REVIEW,
    execution_entity_object_dir,
    execution_entity_page_input_path,
    execution_entity_stage_dir,
    execution_root,
)
from core.post_evidence_chain import build_finalization_report
from core.provenance import build_provenance


def homepage_media_review_dispositions(manifest: Mapping[str, Any]) -> list[dict[str, str]]:
    """Project structural media placement into the independent-review contract.

    `groupMember` and other `related` assets are a supplementary gallery by
    design.  They must not be judged as missing a body anchor merely because
    their source gallery appeared beside a section in MediaWiki.
    """
    raw_assets = manifest.get("imagePlacements") or manifest.get("assets") or []
    if not isinstance(raw_assets, list):
        return []
    rows: list[dict[str, str]] = []
    for raw in raw_assets:
        if not isinstance(raw, Mapping):
            continue
        asset_id = str(raw.get("assetId") or "").strip()
        if not asset_id:
            continue
        role = str(raw.get("role") or "").strip()
        placement_type = str(raw.get("placementType") or "").strip()
        if role == "cover":
            expected = "cover_frontmatter_only"
        elif role == "inline":
            expected = "bound_inline_figure"
        else:
            expected = "related_gallery_only"
        rows.append(
            {
                "assetId": asset_id,
                "role": role,
                "placementType": placement_type,
                "expected": expected,
            }
        )
    return rows


def homepage_asset_file_evidence(
    object_dir: Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, object]]:
    """Project deterministic asset existence into the semantic review packet."""
    raw_assets = manifest.get("assets") or []
    if not isinstance(raw_assets, list):
        return []
    assets_dir = (object_dir / "assets").resolve()
    rows: list[dict[str, object]] = []
    for raw in raw_assets:
        if not isinstance(raw, Mapping):
            continue
        asset_id = str(raw.get("assetId") or "").strip()
        file_name = str(raw.get("fileName") or "").strip()
        if not asset_id or not file_name:
            continue
        candidate = (assets_dir / file_name).resolve()
        inside_assets = candidate.is_relative_to(assets_dir)
        exists = inside_assets and candidate.is_file()
        rows.append(
            {
                "assetId": asset_id,
                "fileName": file_name,
                "relativePath": f"assets/{file_name}",
                "exists": exists,
                "sha256": sha256_file(candidate) if exists else "",
            }
        )
    return rows

def _entity_draft_dir(execution_id: str, domain: str, etype: str, name: str) -> Path:
    return execution_entity_stage_dir(execution_id, domain, etype, name, STAGE_DRAFT)
def _entity_draft_path(execution_id: str, domain: str, etype: str, name: str) -> Path:
    return execution_entity_stage_dir(execution_id, domain, etype, name, STAGE_DRAFT) / "page.md"

def _write_entity_draft(execution_id: str, domain: str, etype: str, name: str) -> Path:
    """返回创作 agent创作的 4.draft/page.md；不得用 finalize 终稿覆盖 Agent 正文。
    主页正文已由创作 agent在 4.draft/page.md 创作，finalize 只把它注入封面后写到 page.md。
    这里只在草稿意外缺失时，用终稿做一次性补写兜底，否则保留 Agent 原始草稿用于
    finalization_report 的 draft↔final 归一化对照。
    """
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    final_page = obj / "page.md"
    draft_page = _entity_draft_path(execution_id, domain, etype, name)
    if not draft_page.is_file() and final_page.is_file():
        draft_page.parent.mkdir(parents=True, exist_ok=True)
        draft_page.write_text(final_page.read_text(encoding="utf-8"), encoding="utf-8")
    return draft_page

def _entity_review_paths(execution_id: str, domain: str, etype: str, name: str) -> tuple[Path, Path, Path]:
    review_dir = execution_entity_stage_dir(execution_id, domain, etype, name, STAGE_REVIEW)
    return (
        review_dir / "review.json",
        review_dir / "provenance.json",
        review_dir / "finalization_report.json",
    )

def _build_entity_provenance(
    *,
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
    source_paths: list[str],
    review_payload: dict[str, Any],
) -> dict[str, Any]:
    rel_page = f"entities/{domain}/{etype}/{name}/page.md"
    rel_input = f"entities/{domain}/{etype}/{name}/3.compose/entity_page_input.json"
    cited_paths = [rel_page if item == "page.md" else item for item in source_paths]
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    draft_page = _entity_draft_dir(execution_id, domain, etype, name) / "page.md"
    prompt_page = _entity_draft_dir(execution_id, domain, etype, name) / "prompt.md"
    input_path = execution_entity_page_input_path(execution_id, domain, etype, name)
    final_page = obj / "page.md"
    source_bundle_text = ""
    for rel in source_paths:
        candidate = execution_root(execution_id) / rel
        if candidate.is_file():
            source_bundle_text += candidate.read_text(encoding="utf-8", errors="ignore")
    draft_text = draft_page.read_text(encoding="utf-8") if draft_page.is_file() else ""
    final_text = final_page.read_text(encoding="utf-8") if final_page.is_file() else draft_text
    entity_payload = read_json(obj / "_entity.json") if (obj / "_entity.json").is_file() else {}
    compose_payload = {
        "sourcePaths": source_paths,
        "sourceUrls": list(entity_payload.get("sourceUrls") or []),
        "citedSourceRefs": cited_paths or source_paths,
        "generator": "agent",
        "generatorModel": "homepage-agent",
        "articleMarkdownDigest": compute_document_sha256(final_text),
        "entityRefs": [entity_ref(domain, etype, name)],
    }
    draft_meta_path = _entity_draft_dir(execution_id, domain, etype, name) / "draft_meta.json"
    recorded_draft_meta = read_json(draft_meta_path) if draft_meta_path.is_file() else {}
    draft_meta = {
        "generator": str(recorded_draft_meta.get("generator") or "agent"),
        "model": str(recorded_draft_meta.get("model") or ""),
        "agentRunId": str(recorded_draft_meta.get("agentRunId") or ""),
        "agentId": str(recorded_draft_meta.get("agentId") or ""),
        "sessionTrace": "build_homepage",
        "styleFamily": "entity-homepage",
        "openingStrategy": "base_draft_light_edit",
        "citedSourcePaths": cited_paths or source_paths,
        "promptSha256": str(
            recorded_draft_meta.get("promptSha256")
            or (sha256_file(prompt_page) if prompt_page.is_file() else sha256_text(""))
        ),
        "writingPackSha256": sha256_file(input_path) if input_path.is_file() else sha256_text(""),
        "sourceBundleSha256": sha256_text(source_bundle_text),
        "draftSha256": str(
            recorded_draft_meta.get("draftSha256") or compute_document_sha256(draft_text)
        ),
    }
    manifest = {
        "publishTitle": name,
        "publishSeq": 1,
        "entityRefs": [entity_ref(domain, etype, name)],
    }
    provenance = build_provenance(
        entity_ref(domain, etype, name),
        writing_pack={"title": name, "styleFamily": "entity-homepage"},
        draft_meta=draft_meta,
        review_payload=review_payload,
        compose_payload=compose_payload,
        manifest=manifest,
    )
    provenance["agentInput"]["writingPack"] = rel_input
    provenance["agentInput"]["prompt"] = "4.draft/prompt.md"
    provenance["final"]["articleDigest"] = compute_document_sha256(final_text)
    return provenance

def _write_entity_review_sidecars(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    source_paths: list[str],
    review_payload: dict[str, Any],
) -> None:
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    final_page = obj / "page.md"
    draft_page = _write_entity_draft(execution_id, domain, etype, name)
    review_path, provenance_path, finalization_path = _entity_review_paths(execution_id, domain, etype, name)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    provenance = _build_entity_provenance(
        execution_id=execution_id,
        domain=domain,
        etype=etype,
        name=name,
        source_paths=source_paths,
        review_payload=review_payload,
    )
    execution = stage_execution_context(execution_id)
    finalization = build_finalization_report(
        entity_ref(domain, etype, name),
        draft_markdown=draft_page.read_text(encoding="utf-8") if draft_page.is_file() else "",
        final_markdown=final_page.read_text(encoding="utf-8") if final_page.is_file() else "",
        normalization_actions=["entity_homepage_draft_materialized"],
        article_source="4.draft/page.md",
        compose_snapshot_markdown=None,
        draft_ref="4.draft/page.md",
        final_ref="page.md",
        compose_snapshot_ref=None,
    )
    finalization.update(
        {
            "schema": "quwoquan_data.finalization",
            "stage": "5.review",
            **execution,
            "draftRef": str(finalization.get("draftArticleRef") or "4.draft/page.md"),
            "finalRef": str(finalization.get("finalArticleRef") or "page.md"),
        }
    )
    review_dir = review_path.parent
    object_ref = entity_ref(domain, etype, name)
    issues = [str(item) for item in review_payload.get("issues") or [] if str(item).strip()]
    raw_checks = review_payload.get("checks")
    deterministic_checks = [
        {
            "name": str(key),
            "passed": bool(value.get("passed")),
            "issues": [str(item) for item in value.get("issues") or [] if str(item).strip()],
        }
        for key, value in (raw_checks.items() if isinstance(raw_checks, Mapping) else [])
        if isinstance(value, Mapping)
    ]
    source_check = (
        raw_checks.get("sourceQualification")
        if isinstance(raw_checks, Mapping) and isinstance(raw_checks.get("sourceQualification"), Mapping)
        else {}
    )
    media_issues = [
        str(item)
        for item in review_payload.get("mediaIssues") or []
        if str(item).strip()
    ]
    reference_issues = [
        str(item)
        for item in source_check.get("issues") or []
        if str(item).strip()
    ]
    deterministic_gate = {
        "schema": "quwoquan_data.deterministic_gate",
        "stage": "5.review",
        "executionId": execution["executionId"],
        "objectRef": object_ref,
        "passed": not issues,
        "issues": issues,
        "checks": deterministic_checks,
    }
    media_ref_review = {
        "schema": "quwoquan_data.media_ref_review",
        "stage": "5.review",
        "executionId": execution["executionId"],
        "objectRef": object_ref,
        "passed": not media_issues and not reference_issues,
        "mediaIssues": media_issues,
        "referenceIssues": reference_issues,
    }
    reviewer = (
        review_payload.get("independentReviewer")
        if isinstance(review_payload.get("independentReviewer"), dict)
        else {}
    )
    reviewer_status = str(reviewer.get("status") or "pending")
    attestation = {
        "schema": "quwoquan_data.review_attestation",
        "stage": "5.review",
        **execution,
        "objectRef": object_ref,
        "decision": str(review_payload.get("decision") or ""),
        "deterministicGate": {
            "status": "passed" if deterministic_gate["passed"] else "failed",
            "issues": deterministic_gate["issues"],
        },
        "independentReviewer": {
            "status": reviewer_status,
            # 独立审阅尚未绑定结果时这三项必须自述「未绑定」。写死一个真实存在的
            # provider 名与角色名会让操作者把「审阅没跑成」误读成「某模型已审过」，
            # 排查时只能靠 resultHash 为 null 才发现，而那要翻到 publish 阶段。
            "provider": str(reviewer.get("provider") or "unbound"),
            "model": str(reviewer.get("model") or "unbound"),
            "modelFamily": str(reviewer.get("modelFamily") or "unbound"),
            "runId": str(
                reviewer.get("runId")
                or "review_"
                + canonical_sha256(
                    {
                        "executionId": execution["executionId"],
                        "objectRef": entity_ref(domain, etype, name),
                    }
                ).removeprefix("sha256:")[:20]
            ),
            "resultHash": reviewer.get("resultHash"),
        },
        "mediaRefReview": {
            "status": "passed" if media_ref_review["passed"] else "failed",
            "issues": [*media_issues, *reference_issues],
        },
        "repair": {"status": "not_required" if not review_payload.get("issues") else "pending"},
        "finalizationRef": "5.review/finalization_report.json",
        "evidenceIndexRef": "5.review/evidence_index.json",
    }
    assert_valid(
        finalization,
        "content",
        "finalization",
        label=f"finalization:{name}",
    )
    assert_valid(
        attestation,
        "content",
        "review_attestation",
        label=f"review_attestation:{name}",
    )
    assert_valid(
        deterministic_gate,
        "content",
        "deterministic_gate",
        label=f"deterministic_gate:{name}",
    )
    assert_valid(
        media_ref_review,
        "content",
        "media_ref_review",
        label=f"media_ref_review:{name}",
    )
    write_json(review_path, review_payload)
    write_json(provenance_path, provenance)
    write_json(finalization_path, finalization)
    write_json(review_dir / "deterministic_gate.json", deterministic_gate)
    write_json(review_dir / "media_ref_review.json", media_ref_review)
    write_json(review_dir / "attestation.json", attestation)
    evidence_paths = (
        ("deterministic_gate", review_dir / "deterministic_gate.json"),
        ("media_ref_review", review_dir / "media_ref_review.json"),
        ("review", review_path),
        ("provenance", provenance_path),
        ("finalization", finalization_path),
    )
    evidence_index = {
        "schema": "quwoquan_data.evidence_index",
        "stage": "5.review",
        "executionId": execution["executionId"],
        "executionBinding": execution["executionBinding"],
        "objectRef": object_ref,
        "evidence": [
            {
                "kind": kind,
                "ref": f"5.review/{path.name}",
                "sha256": sha256_file(path),
            }
            for kind, path in evidence_paths
        ],
    }
    assert_valid(
        evidence_index,
        "content",
        "evidence_index",
        label=f"evidence_index:{name}",
    )
    write_json(review_dir / "evidence_index.json", evidence_index)
    write_entity_object_index(execution_id, domain, etype, name)

def _entity_review_payload(
    *,
    issues: list[str],
    source_paths: list[str],
    base_draft_exists: bool,
) -> dict[str, Any]:
    base_source_issue = (not source_paths) or (not base_draft_exists)
    decision = "approved" if not issues else "revision_needed"
    fallback = "build_homepage" if issues else None
    if base_source_issue:
        fallback = "needs_source_repair"
    return {
        "decision": decision,
        "issues": issues,
        "fallbackStage": fallback,
        "checks": {
            "entityPageQuality": {"passed": not issues, "issues": issues},
            "sourceQualification": {
                "passed": not base_source_issue,
                "issues": [] if not base_source_issue else ["no readable base draft source available for homepage"],
            },
        },
    }


def apply_independent_homepage_review(
    *,
    review_dir: Path,
    provider: str,
    model: str,
    model_family: str,
    run_id: str,
    result_payload: dict[str, Any],
) -> list[str]:
    """Bind one independent Cursor review result to the compact review evidence."""
    review_path = review_dir / "review.json"
    attestation_path = review_dir / "attestation.json"
    evidence_index_path = review_dir / "evidence_index.json"
    if not review_path.is_file() or not attestation_path.is_file() or not evidence_index_path.is_file():
        return [f"{review_dir}: deterministic review evidence is incomplete"]
    try:
        assert_valid(
            result_payload,
            "content",
            "homepage_reviewer_response",
            label=f"homepage_reviewer_response:{review_dir.name}",
        )
    except ValueError as exc:
        return [str(exc)]
    run_id = run_id.strip()
    if not run_id or run_id.startswith("contract-output:"):
        return [f"{review_dir}: independent reviewer must bind a real provider runId"]
    decision = str(result_payload.get("decision") or "")
    issues = [str(item).strip() for item in result_payload.get("issues") or [] if str(item).strip()]
    findings = [str(item).strip() for item in result_payload.get("findings") or [] if str(item).strip()]
    if decision not in {"approved", "revision_needed", "rejected"}:
        return [f"{review_dir}: independent reviewer decision invalid"]
    if not findings:
        return [f"{review_dir}: independent reviewer findings missing"]
    passed = decision == "approved" and not issues
    reviewer_result = {
        "schema": "quwoquan_data.reviewer_result",
        "stage": "5.review",
        "executionId": str(result_payload.get("executionId") or ""),
        "executionBinding": "frozen",
        "objectRef": str(result_payload.get("objectRef") or ""),
        "provider": provider,
        "model": model,
        "modelFamily": model_family,
        "runId": run_id,
        "verdict": "passed" if passed else "failed",
        "issues": issues,
        "findings": findings,
        "resultHash": canonical_sha256(result_payload),
    }
    review_payload = read_json(review_path)
    review_payload["independentReviewer"] = {
        "status": reviewer_result["verdict"],
        "provider": provider,
        "model": model,
        "modelFamily": model_family,
        "runId": run_id,
        "resultHash": reviewer_result["resultHash"],
        "findings": findings,
    }
    if not passed:
        review_payload["decision"] = decision
        review_payload["issues"] = sorted(set([*review_payload.get("issues", []), *issues]))
        review_payload["fallbackStage"] = "build_homepage"
    attestation = read_json(attestation_path)
    attestation["decision"] = "approved" if passed else decision
    attestation["independentReviewer"] = {
        "status": reviewer_result["verdict"],
        "provider": provider,
        "model": model,
        "modelFamily": model_family,
        "runId": run_id,
        "resultHash": reviewer_result["resultHash"],
    }
    attestation["repair"] = {"status": "not_required" if passed else "pending"}
    try:
        assert_valid(
            reviewer_result,
            "content",
            "reviewer_result",
            label=f"reviewer_result:{review_dir.name}",
        )
        assert_valid(
            attestation,
            "content",
            "review_attestation",
            label=f"review_attestation:{review_dir.name}",
        )
    except ValueError as exc:
        return [str(exc)]
    write_json(review_dir / "reviewer_result.json", reviewer_result)
    write_json(review_path, review_payload)
    write_json(attestation_path, attestation)
    evidence_index = read_json(evidence_index_path)
    evidence = [item for item in evidence_index.get("evidence") or [] if isinstance(item, dict)]
    evidence = [item for item in evidence if str(item.get("ref") or "") != "5.review/reviewer_result.json"]
    evidence.append(
        {
            "kind": "independent_reviewer_result",
            "ref": "5.review/reviewer_result.json",
            "sha256": sha256_file(review_dir / "reviewer_result.json"),
        }
    )
    evidence_index["evidence"] = evidence
    try:
        assert_valid(
            evidence_index,
            "content",
            "evidence_index",
            label=f"evidence_index:{review_dir.name}",
        )
    except ValueError as exc:
        return [str(exc)]
    write_json(evidence_index_path, evidence_index)
    return [] if passed else issues or [f"{review_dir}: independent review {decision}"]
