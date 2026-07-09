"""Bridge site-supply map packets into content plan packets."""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import functools
import hashlib
import json
import math
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.io import read_json, write_json
from _common.paths import DATA_ROOT, RUNTIME_ROOT, now_iso
from download.fetch import fetch_image_payload, fetch_source_payload

from site_supply.core import *  # noqa: F403
from site_supply.packets import *  # noqa: F403
from site_supply.targets import *  # noqa: F403
from site_supply import bridge

def _download_candidate_images(candidate: Mapping[str, Any], *, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    images: list[dict[str, Any]] = []
    issues: list[str] = []
    for asset in [a for a in (candidate.get("assets") or []) if isinstance(a, Mapping)][: max(1, int(limit))]:
        url = str(asset.get("url") or asset.get("sourceUrl") or "").strip()
        if not url:
            issues.append(f"{asset.get('assetId') or 'asset'}: missing image url")
            continue
        payload = bridge.call("fetch_image_payload", fetch_image_payload, url)
        if payload is None:
            issues.append(f"{asset.get('assetId') or url}: image download failed or not an image")
            continue
        image = {
            **dict(asset),
            **payload,
            "url": str(payload.get("url") or url),
            "sourceUrl": str(asset.get("sourceUrl") or asset.get("collectionPageUrl") or url),
            "termsUrl": str(asset.get("termsUrl") or ""),
            "license": str(asset.get("license") or ""),
            "credit": str(asset.get("credit") or ""),
            "usageScope": str(asset.get("usageScope") or ""),
            "sourceCollectionId": str(asset.get("sourceCollectionId") or _stable_ref("collection", url)),
            "title": str(asset.get("title") or asset.get("fileTitle") or candidate.get("title") or ""),
            "caption": str(asset.get("caption") or ""),
            "relevance": str(candidate.get("title") or ""),
        }
        missing = [field for field in REQUIRED_ASSET_RIGHTS_FIELDS if not str(image.get(field) or "").strip()]
        if missing:
            issues.append(f"{asset.get('assetId') or url}: missing rights fields {missing}")
            continue
        images.append(image)
    return images, issues

def _content_plan_title(candidate: Mapping[str, Any], entity_name: str, intent_label: str) -> str:
    raw_title = str(candidate.get("title") or entity_name).strip()
    if raw_title and raw_title != entity_name:
        return f"{entity_name}·{intent_label}：{raw_title[:40]}"
    return f"{entity_name}·{intent_label}"


def _min_assets_per_image_work() -> int:
    try:
        from _common.works_classifier import load_works_classification_config

        config = load_works_classification_config()
        rules = config.get("carrierRules") if isinstance(config.get("carrierRules"), Mapping) else {}
        return max(1, int(rules.get("minImagesForImageWork") or 4))
    except Exception:
        return 4


def _effective_min_assets_per_image_work(candidate: Mapping[str, Any]) -> int:
    source = candidate.get("source") if isinstance(candidate.get("source"), Mapping) else {}
    rights_policy = str(source.get("rightsPolicy") or "").strip()
    admission_mode = str(source.get("admissionMode") or "").strip()
    if rights_policy == "attribution_no_watermark" or admission_mode == ADMISSION_ATTRIBUTION_PUBLISH_INGEST:
        return 1
    for asset in [row for row in (candidate.get("assets") or []) if isinstance(row, Mapping)]:
        if str(asset.get("authorizationBasis") or "").strip() == "attribution_no_watermark":
            return 1
    return _min_assets_per_image_work()


def _authorized_candidate_images(candidate: Mapping[str, Any], *, min_count: int) -> tuple[list[dict[str, Any]], list[str]]:
    images: list[dict[str, Any]] = []
    issues: list[str] = []
    for asset in [a for a in (candidate.get("assets") or []) if isinstance(a, Mapping)]:
        asset_id = str(asset.get("assetId") or asset.get("sourceUrl") or "asset")
        source_path = str(asset.get("sourcePath") or asset.get("localPath") or "").strip()
        if not source_path:
            issues.append(f"{asset_id}: authorized image work requires sourcePath/localPath from ingest")
            continue
        path = Path(source_path)
        if not path.is_file():
            issues.append(f"{asset_id}: authorized sourcePath missing: {path}")
            continue
        images.append(
            {
                **dict(asset),
                "sourcePath": str(path),
                "url": str(asset.get("downloadUrl") or asset.get("sourceUrl") or ""),
                "requestedUrl": str(asset.get("downloadUrl") or asset.get("sourceUrl") or ""),
                "sourceUrl": str(asset.get("sourceUrl") or ""),
                "contentType": str(asset.get("mimeType") or asset.get("contentType") or ""),
                "ext": path.suffix or ".jpg",
                "caption": str(asset.get("caption") or ""),
                "relevance": str(asset.get("relevance") or asset.get("title") or candidate.get("title") or ""),
            }
        )
    if len(images) < int(min_count):
        issues.append(f"image work requires at least {int(min_count)} authorized local assets; got {len(images)}")
    return images, issues


def _compact_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= int(limit):
        return text
    return text[: int(limit)].rstrip()


def _image_source_markdown(candidate: Mapping[str, Any], images: list[Mapping[str, Any]]) -> str:
    first = images[0] if images else {}
    heading = str(candidate.get("title") or first.get("title") or "").strip()
    lines = [
        f"# {heading}" if heading else "# 图片来源记录",
        "",
        f"sourceCollectionId: {str(first.get('sourceCollectionId') or '').strip()}",
        f"creator: {str(first.get('creator') or '').strip()}",
        f"credit: {str(first.get('credit') or '').strip()}",
        f"collectionPageUrl: {str(first.get('collectionPageUrl') or '').strip()}",
        f"license: {str(first.get('license') or '').strip()}",
        f"termsUrl: {str(first.get('termsUrl') or '').strip()}",
        f"authorizationProof: {str(first.get('authorizationProof') or '').strip()}",
        f"authorizationBasis: {str(first.get('authorizationBasis') or '').strip()}",
        f"pinUrl: {str(first.get('pinUrl') or '').strip()}",
        f"discoveryUrl: {str(first.get('discoveryUrl') or '').strip()}",
        f"originalAssetUrl: {str(first.get('originalAssetUrl') or '').strip()}",
        f"sourceAuthor: {str(first.get('sourceAuthor') or '').strip()}",
        f"repostAttribution: {str(first.get('repostAttribution') or '').strip()}",
        f"watermarkScan: {str(first.get('watermarkScan') or '').strip()}",
        f"ocrScan: {str(first.get('ocrScan') or '').strip()}",
        f"collectedAt: {str(first.get('collectedAt') or '').strip()}",
        "",
        "## Assets",
    ]
    for asset in images:
        lines.append(
            "- "
            f"{asset.get('assetId')}: {asset.get('title') or asset.get('caption') or ''} "
            f"({asset.get('width') or 0}x{asset.get('height') or 0})"
        )
    return "\n".join(lines).strip() + "\n"


def _source_unit_asset_refs(
    *,
    task_id: str,
    batch_id: str,
    source_ref: str,
    batch_root_path: Path,
    relative_batch_ref_fn: Any,
) -> list[str]:
    source_path = batch_root_path / source_ref
    index_path = source_path.parent / "assets" / "index.json"
    if not index_path.is_file():
        return []
    try:
        rows = read_json(index_path).get("assets") or []
    except (OSError, ValueError, TypeError):
        return []
    refs: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        file_name = str(row.get("fileName") or "").strip()
        if not file_name:
            continue
        asset_file = source_path.parent / "assets" / file_name
        if asset_file.is_file():
            refs.append(relative_batch_ref_fn(asset_file, task_id, batch_id))
    return refs

def build_site_content_plan(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    task_id: str,
    target_batch: str,
    limit: int = 10,
    refs: list[str] | None = None,
    entity_type: str = "地点/景区",
    intent: str = "行前指南",
    audience: str = "leisureTraveler",
    max_images_per_candidate: int = 3,
    allow_partial: bool = False,
) -> dict[str, Any]:
    from _common.base_draft import extract_base_draft_body
    from _common.content_source_registry import resolve_source_class
    from _common.content_plan import CONTENT_PLAN_SCHEMA, validate_content_plan
    from _common.content_object import write_brief_object
    from _common.paths import (
        batch_content_plan_packet_path,
        batch_root,
        committed_task_spec,
        ensure_batch_layout,
        relative_batch_ref,
    )
    from _common.release_integrity import MIN_ARTICLE_BASE_DRAFT_CHARS
    from _common.source_unit import resolve_entity_object_dir, write_source_unit
    from _common.works_classifier import classify_works
    from _common.batch_manifest import write_batch_manifest
    from plan.brief import resolve_compose_brief
    from template.registry import TemplateRegistry
    from template.router import RouteRequest

    source_root = site_supply_root(vertical, site_id, batch_id)
    explicit_refs = [str(ref).strip() for ref in (refs or []) if str(ref).strip()]
    all_refs = explicit_refs or _eligible_site_map_refs(source_root)
    scan_refs = all_refs[: int(limit)] if explicit_refs and limit > 0 else all_refs
    blockers: list[str] = []
    warnings: list[str] = []
    items: list[dict[str, Any]] = []
    validation_targets: list[dict[str, str]] = []
    validation_target_keys: set[tuple[str, str]] = set()
    skipped: dict[str, list[str]] = {}
    scanned_refs: list[str] = []
    outputs: list[str] = []
    target_root = batch_root(task_id, target_batch)
    target_task_spec = committed_task_spec(task_id)
    if not target_task_spec.is_file():
        blockers.append(f"committed task spec missing for taskId {task_id!r}; repair at task/site-plan")
        skipped = {
            ref: ["committed task spec missing; repair at task/site-plan"]
            for ref in scan_refs
        }
        report = {
            "schemaVersion": "quwoquan.site_supply.content_plan_report/1",
            "vertical": vertical,
            "siteId": site_id,
            "batchId": batch_id,
            "taskId": task_id,
            "targetBatch": target_batch,
            "eligibleAvailableCount": len(all_refs),
            "selectedCount": len(scan_refs),
            "requestedCount": int(limit),
            "itemCount": 0,
            "skipped": skipped,
            "outputs": outputs,
            "createdAt": now_iso(),
        }
        gate = _gate_report("content_plan", blockers, warnings)
        report["gate"] = gate
        report_path = target_root / "_shared" / "site_supply_content_plan_report.json"
        write_json(report_path, report)
        outputs.append(str(report_path))
        _write_stage_triplet(source_root, "content_plan", outputs, gate)
        return report
    ensure_batch_layout(task_id, target_batch, "download")
    ensure_batch_layout(task_id, target_batch, "produce")
    # 一批次一内容类型：批次 contentType 由首个可用候选的 lane 定调（article/image），
    # 后续不同 lane 的候选必须另起批次（循环内 skipped 拦截）。
    batch_lane = ""
    for _ref in scan_refs:
        _candidate_file = _candidate_path(source_root, _ref)
        if not _candidate_file.is_file():
            continue
        _lane = str((read_json(_candidate_file) or {}).get("lane") or "")
        if _lane in {"article", "image"}:
            batch_lane = _lane
            break
    # 站点主线 handoff 固化：supplyMode=site_primary、sourceKey=siteId（目录规范单一供给门）。
    write_batch_manifest(
        task_id,
        target_batch,
        command="site-supply:content-plan",
        content_type=batch_lane,
        supply_mode="site_primary",
        source_key=site_id,
    )
    registry = TemplateRegistry.load()
    etype_parts = [p for p in str(entity_type).strip("/").split("/") if p]
    entity_domain = etype_parts[0] if len(etype_parts) >= 2 else "地点"
    entity_leaf_type = etype_parts[-1] if etype_parts else "景区"
    source_category = _source_category_for_site(site_id)

    for ref in scan_refs:
        if limit > 0 and len(items) >= int(limit):
            break
        scanned_refs.append(ref)
        ref_issues: list[str] = []
        candidate_path = _candidate_path(source_root, ref)
        score_path = _score_path(source_root, ref)
        map_path = _map_path(source_root, ref)
        if not candidate_path.is_file():
            ref_issues.append("site_candidate_packet missing; repair at site_extract")
        if not score_path.is_file():
            ref_issues.append("site_score_packet missing; repair at site_score")
        if not map_path.is_file():
            ref_issues.append("site_map_packet missing; repair at site_map")
        if ref_issues:
            skipped[ref] = ref_issues
            continue
        candidate = read_json(candidate_path)
        score = read_json(score_path)
        mapped = read_json(map_path)
        if not _packet_gate_passed(candidate):
            ref_issues.append("site_extract gate failed; repair at site_extract")
        if not bool(score.get("productionEligible")) or not _packet_gate_passed(score):
            ref_issues.append("site_score not productionEligible; repair at site_score")
        if not _packet_gate_passed(mapped) or not ((mapped.get("contentPlanHandoff") or {}).get("eligible")):
            ref_issues.append("site_map handoff not eligible; repair at site_map")
        lane = str(candidate.get("lane") or "")
        if lane not in {"article", "image"}:
            ref_issues.append(f"content-plan bridge only supports article/image lane; got {lane!r}")
        elif batch_lane and lane != batch_lane:
            ref_issues.append(
                f"batch contentType is {batch_lane!r}; lane {lane!r} candidate must go to a separate batch"
            )
        mentions = candidate.get("semanticMentions") if isinstance(candidate.get("semanticMentions"), Mapping) else {}
        expected_entity_type = f"{entity_domain}/{entity_leaf_type}"
        raw_entity_values = [str(x).strip() for x in (mentions.get("entities") or []) if str(x).strip()]
        entity_name = ""
        raw_entity_name = ""
        mismatched_typed: list[str] = []
        unresolved_raw: list[str] = []
        for raw_entity_value in raw_entity_values:
            typed_entity_type, typed_entity_name = _typed_entity_mention(raw_entity_value)
            if typed_entity_type:
                if typed_entity_type == expected_entity_type:
                    entity_name = typed_entity_name
                    break
                mismatched_typed.append(raw_entity_value)
                continue
            candidate_entity_name = _entity_name_from_mention(raw_entity_value)
            known_target = _resolve_known_entity_target(candidate_entity_name, expected_entity_type=expected_entity_type)
            if known_target:
                entity_name = str(known_target.get("name") or candidate_entity_name).strip()
                raw_entity_name = candidate_entity_name
                break
            if candidate_entity_name:
                unresolved_raw.append(candidate_entity_name)
        if not entity_name:
            raw_entity_name = unresolved_raw[0] if unresolved_raw else str(candidate.get("title") or "").strip()
            if mismatched_typed:
                ref_issues.append(
                    f"candidate lacks {expected_entity_type} mention; mismatched typed mentions={mismatched_typed[:3]}"
                )
            elif raw_entity_name:
                ref_issues.append(
                    f"candidate lacks verified {expected_entity_type} mapping for {raw_entity_name!r}; repair at site_map"
                )
        if not entity_name and not raw_entity_name:
            ref_issues.append("candidate has no entity mention/title; repair at site_map")
        text = str(candidate.get("text") or "").strip()
        source_id = f"{site_id}_{_site_candidate_ref_slug(ref)}"
        if lane == "image":
            min_assets_per_work = _effective_min_assets_per_image_work(candidate)
            images, image_issues = _authorized_candidate_images(candidate, min_count=min_assets_per_work)
            if image_issues:
                ref_issues.extend(image_issues)
            if ref_issues:
                skipped[ref] = ref_issues
                continue
            entity_ref = f"/entity/{entity_domain}/{entity_leaf_type}/{entity_name}"
            object_dir = resolve_entity_object_dir(task_id, target_batch, entity_ref)
            source_ordinal = len(items) + 1
            source_md = _image_source_markdown(candidate, images)
            manifest = write_source_unit(
                object_dir,
                ordinal=source_ordinal,
                source_id=source_id,
                source_md=source_md,
                clean_md=source_md,
                html_bytes=None,
                quality={
                    "sourceId": source_id,
                    "quality": "A-image",
                    "score": max(7, min(10, int(float((score.get("scores") or {}).get("overall") or 0.8) * 10))),
                    "reasons": ["site_supply_handoff", site_id, "licensed_asset_ingest", "image_work"],
                    "excerpt": source_md[:180],
                    "url": str(candidate.get("canonicalUrl") or ""),
                },
                platform=str((candidate.get("source") or {}).get("platform") or site_id),
                source_category=source_category,
                source_use_mode="licensed_publish_asset",
                source_role="image",
                image_evidence_mode="source_unit_assets",
                research_lane="image",
                license_value=str((candidate.get("source") or {}).get("rightsPolicy") or "licensed_asset_required"),
                url=str(candidate.get("canonicalUrl") or ""),
                title=str(candidate.get("title") or entity_name),
                target_ref=entity_ref,
                relevance=f"{entity_name} 摄影图片作品授权来源集合",
                images=images,
                task_id=task_id,
                batch_id=target_batch,
                build_variants=False,
            )
            source_ref = str(manifest.get("sourceRef") or "")
            asset_refs = _source_unit_asset_refs(
                task_id=task_id,
                batch_id=target_batch,
                source_ref=source_ref,
                batch_root_path=batch_root(task_id, target_batch),
                relative_batch_ref_fn=relative_batch_ref,
            )
            if len(asset_refs) < min_assets_per_work:
                skipped[ref] = [
                    f"image work source unit materialized {len(asset_refs)} assets < required {min_assets_per_work}"
                ]
                continue
            first_image = images[0]
            collection_id = str(first_image.get("sourceCollectionId") or "").strip()
            validation_target_key = (f"{entity_domain}/{entity_leaf_type}", entity_name)
            caption = _compact_text(
                str(first_image.get("caption") or candidate.get("caption") or "").strip(),
                300,
            )
            title = _compact_text(
                str(candidate.get("title") or first_image.get("title") or "").strip(),
                80,
            )
            brief = {
                "titleHint": title,
                "carrier": "image",
                "entityRefs": [entity_ref],
                "entityTags": [entity_name],
                "mustIncludeFacts": [
                    f"{entity_name} 摄影图片作品",
                    "图片来自同一授权来源集合（单一 source unit），禁止跨作者/页面/底稿混图",
                ],
                "templateId": "travel.entity.gallery",
                "sourceCollectionId": collection_id,
                "baseSourceRef": source_ref,
                "assetRefs": asset_refs,
                "caption": caption,
            }
            write_brief_object(task_id, target_batch, ref, brief, content_type="image")
            items.append(
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "image",
                    "researchLane": "image",
                    "title": title,
                    "caption": caption,
                    "entityRefs": [entity_ref],
                    "entityTags": [entity_name],
                    "evidenceRefs": [source_ref],
                    "rationale": "site_map eligible licensed image candidate converted to one-source-one-work image plan",
                    "mustIncludeFacts": brief["mustIncludeFacts"],
                    "baseSourceRef": source_ref,
                    "assetRefs": asset_refs,
                    "sourceCandidateRef": ref,
                    "sourceUrl": str(candidate.get("canonicalUrl") or ""),
                    "sourceCollectionId": collection_id,
                }
            )
            if validation_target_key not in validation_target_keys:
                validation_target_keys.add(validation_target_key)
                validation_targets.append({"entityType": validation_target_key[0], "name": validation_target_key[1]})
            outputs.append(str(batch_root(task_id, target_batch) / source_ref))
            source_unit_ref = str(manifest.get("sourceUnitRef") or "").strip()
            if source_unit_ref:
                outputs.append(str(batch_root(task_id, target_batch) / source_unit_ref / "meta.json"))
            continue
        base_draft_text = extract_base_draft_body(text)
        effective_text_len = len(re.sub(r"\s+", "", base_draft_text))
        if effective_text_len < MIN_ARTICLE_BASE_DRAFT_CHARS:
            ref_issues.append(
                f"candidate baseDraftText too short for content_plan "
                f"({effective_text_len} < {MIN_ARTICLE_BASE_DRAFT_CHARS}); repair at site_extract"
            )
        platform = str((candidate.get("source") or {}).get("platform") or site_id)
        source_class = resolve_source_class(source_id=source_id, platform=platform)
        works_verdict = classify_works(
            ref,
            source_class=source_class,
            source_text=base_draft_text,
            entity_name=entity_name or raw_entity_name or str(candidate.get("title") or ""),
            narrative_volume=0,
            image_count=0,
            declared_carrier="article",
            rights_blocked=False,
        )
        if str(works_verdict.get("decision") or "") != "work":
            ref_issues.append(
                "works classifier rejected content_plan candidate as "
                f"{works_verdict.get('decision')!r} "
                f"(abandonReason={works_verdict.get('abandonReason')}, "
                f"sourceTier={works_verdict.get('sourceTier')}, score={works_verdict.get('score')}); "
                "repair at site_score"
            )
        text_only_article = int(max_images_per_candidate) <= 0
        images, image_issues = ([], []) if text_only_article else _download_candidate_images(candidate, limit=max_images_per_candidate)
        if not images and not text_only_article:
            ref_issues.append("no downloadable/right-cleared source images; repair at site_extract or source rights")
        if text_only_article:
            warnings.append(f"{ref}: text-only article plan; source images are not requested or published")
        if image_issues:
            warnings.extend(f"{ref}: {issue}" for issue in image_issues[:5])
        if ref_issues:
            skipped[ref] = ref_issues
            continue

        entity_ref = f"/entity/{entity_domain}/{entity_leaf_type}/{entity_name}"
        object_dir = resolve_entity_object_dir(task_id, target_batch, entity_ref)
        source_ordinal = len(items) + 1
        manifest = write_source_unit(
            object_dir,
            ordinal=source_ordinal,
            source_id=source_id,
            source_md=text,
            clean_md=text,
            html_bytes=None,
            quality={
                "sourceId": source_id,
                "quality": "A-story" if float((score.get("scores") or {}).get("overall") or 0) >= 0.7 else "B-fact",
                "score": max(4, min(10, int(float((score.get("scores") or {}).get("overall") or 0.5) * 10))),
                "reasons": ["site_supply_handoff", site_id, "rights_checked"],
                "excerpt": text[:180],
                "url": str(candidate.get("canonicalUrl") or ""),
            },
            platform=str((candidate.get("source") or {}).get("platform") or site_id),
            source_category=source_category,
            source_use_mode="factual_reference_only",
            source_role="base",
            image_evidence_mode="source_unit_assets",
            research_lane="article",
            license_value=str((candidate.get("source") or {}).get("rightsPolicy") or "factual_citation_only"),
            url=str(candidate.get("canonicalUrl") or ""),
            title=str(candidate.get("title") or entity_name),
            target_ref=entity_ref,
            relevance=f"{entity_name} 网站供给线候选；仅作事实参考，正文需独立表达",
            images=images,
            task_id=task_id,
            batch_id=target_batch,
            build_variants=False,
        )
        source_ref = str(manifest.get("sourceRef") or "")
        title = _content_plan_title(candidate, entity_name, intent)
        brief = resolve_compose_brief(
            registry,
            RouteRequest(
                vertical="travel",
                subject_kind="entity",
                subject_type=f"{entity_domain}/{entity_leaf_type}",
                intent=intent,
                audience=audience,
            ),
            title=title,
            entity_refs=[entity_ref],
        )
        update_fields = {
            "baseSourceRef": source_ref,
            "sourceUseMode": "factual_reference_only",
            "writingIntent": "planning_consultation",
            "routeCoverageExpectations": {"minCoveredEntityRefs": 1, "requireAllPrimaryNodes": False},
            "evidenceRequirements": {
                "fact": {"required": True},
                "emotion": {"required": False},
                "mainline": {"required": True, "minSignals": 1},
            },
            "explicitFeelings": {"requireLike": False, "requireDislike": False},
            "mustIncludeFacts": [entity_name],
            "bannedRegisterTerms": sorted(set(list(brief.get("bannedRegisterTerms") or []) + ["携程", "马蜂窝", "去哪儿", "维基导游", "Wikivoyage"])),
        }
        if images:
            update_fields["imagePlan"] = [{"slot": "来源封面", "imageLayout": "fullWidth"}]
        else:
            update_fields["imagePlan"] = []
            update_fields["publishMediaMode"] = "text_only"
        brief.update(update_fields)
        write_brief_object(task_id, target_batch, ref, brief, content_type="article")
        items.append(
            {
                "ref": ref,
                "kind": "entity",
                "carrier": "article",
                "researchLane": "article",
                "title": title,
                "entityRefs": [entity_ref],
                "evidenceRefs": [source_ref],
                "rationale": "site_map eligible candidate converted to one-source-one-work factual article plan",
                "mustIncludeFacts": brief["mustIncludeFacts"],
                "writingIntent": "planning_consultation",
                "baseSourceRef": source_ref,
                "sourceUseMode": "factual_reference_only",
                "sourceCandidateRef": ref,
                "sourceUrl": str(candidate.get("canonicalUrl") or ""),
            }
        )
        validation_target_key = (f"{entity_domain}/{entity_leaf_type}", entity_name)
        if validation_target_key not in validation_target_keys:
            validation_target_keys.add(validation_target_key)
            validation_targets.append({"entityType": validation_target_key[0], "name": validation_target_key[1]})
        outputs.append(str(batch_root(task_id, target_batch) / source_ref))
        source_unit_ref = str(manifest.get("sourceUnitRef") or "").strip()
        if source_unit_ref:
            outputs.append(str(batch_root(task_id, target_batch) / source_unit_ref / "meta.json"))

    if not items:
        blockers.append("content_plan produced no eligible items")
    if skipped and not allow_partial:
        for ref, issues in skipped.items():
            blockers.append(f"{ref}: " + "; ".join(issues))
    report = {
        "schemaVersion": "quwoquan.site_supply.content_plan_report/1",
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "taskId": task_id,
        "targetBatch": target_batch,
        "eligibleAvailableCount": len(all_refs),
        "selectedCount": len(scanned_refs),
        "requestedCount": int(limit),
        "itemCount": len(items),
        "skipped": skipped,
        "outputs": outputs,
        "createdAt": now_iso(),
    }
    if items:
        write_batch_manifest(
            task_id,
            target_batch,
            coverage_targets=validation_targets,
            command="site-supply:content-plan",
            supply_mode="site_primary",
            source_key=site_id,
        )
        write_json(
            batch_content_plan_packet_path(task_id, target_batch),
            {
                "schemaVersion": CONTENT_PLAN_SCHEMA,
                "taskId": task_id,
                "batchId": target_batch,
                "generatedBy": "site_supply_content_plan_bridge",
                "sourceSite": {"vertical": vertical, "siteId": site_id, "batchId": batch_id},
                "items": items,
            },
        )
        outputs.append(str(batch_content_plan_packet_path(task_id, target_batch)))
        validation_issues = validate_content_plan(
            task_id,
            target_batch,
            {"scope": {"coverageTargets": validation_targets}, "content": {"quotas": {}}},
        )
        if validation_issues:
            blockers.extend(f"content_plan validator: {issue}" for issue in validation_issues)
    write_json(target_root / "_shared" / "site_supply_content_plan_report.json", report)
    outputs.append(str(target_root / "_shared" / "site_supply_content_plan_report.json"))
    gate = _gate_report("content_plan", blockers, warnings)
    report["gate"] = gate
    write_json(target_root / "_shared" / "site_supply_content_plan_report.json", report)
    _write_stage_triplet(source_root, "content_plan", outputs, gate)
    return report

def handle_content_plan(args: argparse.Namespace) -> None:
    report = build_site_content_plan(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        task_id=args.task,
        target_batch=args.target_batch,
        limit=args.limit,
        refs=_split_csv(args.refs),
        entity_type=args.entity_type,
        intent=args.intent,
        audience=args.audience,
        max_images_per_candidate=args.max_images_per_candidate,
        allow_partial=args.allow_partial,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not (report.get("gate") or {}).get("passed"):
        raise SystemExit(1)

__all__ = [name for name in globals() if not name.startswith("__")]
