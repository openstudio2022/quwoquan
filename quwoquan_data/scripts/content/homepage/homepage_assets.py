"""实体主页媒体资产选择、复制与 disposition 证据。"""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.execution.asset_registry import allocate_post_asset_id, load_execution_asset_registry
from content.execution.runtime_state import load_execution_runtime_state
from core.io import read_json, write_json
from core.page_media import HomepageMediaDisposition
from core.paths import execution_entity_object_dir, execution_root
from content.homepage.homepage_refs import same_source_unit as _same_source_unit


def _normalize_wiki_filename(value: str) -> str:
    """把 wiki 文件名规范化：unquote、空格/下划线归一、小写，供精确等值匹配。
    MediaWiki 视空格与下划线等价，故统一折叠；不做子串包含（避免实体名污染）。
    """
    from urllib.parse import unquote
    text = unquote(str(value or "")).strip()
    if not text:
        return ""
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text.lower()

def _asset_wiki_filename(asset: Mapping[str, Any]) -> str:
    """从下载资产还原其原始 wiki 文件名（供与 imagePlacements.fileName 精确匹配）。
    优先 ``authorizationProof`` / ``sourceUrl`` 里的 ``File:<name>``，其次末段路径。
    绝不使用 sourceAssetRef 的批次路径（含实体名会污染子串匹配）。
    """
    from urllib.parse import unquote
    for key in ("authorizationProof", "sourceUrl", "collectionPageUrl", "url", "requestedUrl"):
        raw = unquote(str(asset.get(key) or "")).strip()
        if not raw:
            continue
        match = re.search(r"[Ff]ile:([^/?#]+)", raw)
        candidate = match.group(1) if match else raw.rsplit("/", 1)[-1]
        norm = _normalize_wiki_filename(candidate)
        if norm and re.search(r"\.(?:jpe?g|png|gif|svg|webp|tif?f)$", norm):
            return norm
    return ""

def _placement_is_map_like(placement: Mapping[str, Any]) -> bool:
    """imagePlacements 行是否为地图/位置图（不可做封面，也不进正文内嵌）。"""
    if str(placement.get("placementType") or "") == "locatorMap":
        return True
    try:
        if int(placement.get("coverCandidateRank") or 0) < 0:
            return True
    except (TypeError, ValueError):
        pass
    return False

def _placement_caption_section_overlap(placement: Mapping[str, Any]) -> int:
    """Score whether a repeated visual's caption belongs to its declared section."""
    from core.localization import fold_to_simplified

    def _han_bigrams(value: object) -> set[str]:
        text = fold_to_simplified(str(value or ""))
        chars = "".join(re.findall(r"[\u3400-\u9fff]", text))
        return {chars[index : index + 2] for index in range(max(0, len(chars) - 1))}

    caption_terms = _han_bigrams(
        placement.get("subjectKey") or placement.get("caption")
    )
    section_terms = _han_bigrams(placement.get("sectionSlug"))
    return len(caption_terms & section_terms)


def _prefer_homepage_placement(
    existing: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Choose one semantic authority when a source page repeats a visual."""
    existing_caption = str(existing.get("caption") or "").strip()
    candidate_caption = str(candidate.get("caption") or "").strip()
    existing_rank = (
        _placement_caption_section_overlap(existing),
        int(bool(existing_caption)),
    )
    candidate_rank = (
        _placement_caption_section_overlap(candidate),
        int(bool(candidate_caption)),
    )
    return candidate if candidate_rank > existing_rank else existing


@dataclass(frozen=True, slots=True)
class HomepageAssetSelection:
    """Typed publish decision for all page images considered by a homepage."""

    publishable: tuple[dict[str, Any], ...]
    excluded: tuple["HomepageMediaDisposition", ...]


def select_homepage_assets(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    primary_ref: str,
) -> HomepageAssetSelection:
    """主页图片优先正文同源资产，缺失时使用独立且权利完整的主页媒体单元。"""
    from content.source.source_assets import object_image_candidates
    unit_ref = str(primary_ref or "").strip()
    if not unit_ref:
        return HomepageAssetSelection((), ())
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    placements: list[dict[str, Any]] = []
    meta_path = execution_root(execution_id) / Path(unit_ref).parent / "meta.json"
    if meta_path.is_file():
        meta = read_json(meta_path)
        raw_placements = meta.get("imagePlacements") if isinstance(meta, dict) else []
        if isinstance(raw_placements, list):
            placements = [row for row in raw_placements if isinstance(row, dict)]
    # imagePlacements 按规范化后的原始 wiki 文件名精确索引（禁止实体名子串污染）。
    # 同名多行时选择图注主题与章节最贴合的一行；同分保持来源顺序。
    placement_by_name: dict[str, dict[str, Any]] = {}
    for row in placements:
        key = _normalize_wiki_filename(str(row.get("fileName") or ""))
        if not key:
            continue
        existing = placement_by_name.get(key)
        placement_by_name[key] = (
            row if existing is None else dict(_prefer_homepage_placement(existing, row))
        )
    def _placement_for(image: dict[str, Any]) -> dict[str, Any]:
        key = _asset_wiki_filename(image)
        if key:
            return placement_by_name.get(key, {})
        return {}
    all_images = object_image_candidates(obj, execution_id)
    from core.page_media import HomepageAssetDisposition
    from content.execution.identity import parse_execution_id
    from governance.coverage.license import rights_proof_required

    vertical = parse_execution_id(execution_id).vertical
    require_rights_proof = rights_proof_required(vertical)

    excluded: list[HomepageMediaDisposition] = []

    def _exclude(
        image: Mapping[str, Any],
        disposition: HomepageAssetDisposition,
        reason: str,
    ) -> None:
        source_asset_ref = str(image.get("sourceAssetRef") or "").strip()
        if not source_asset_ref:
            return
        excluded.append(
            HomepageMediaDisposition(
                source_asset_ref=source_asset_ref,
                source_asset_id=str(image.get("sourceAssetId") or "").strip(),
                disposition=disposition,
                reason=reason,
            )
        )

    candidates: list[dict[str, Any]] = []
    for image in all_images:
        if not _same_source_unit(str(image.get("sourceRef") or ""), unit_ref):
            continue
        if not str(image.get("sourceRef") or "").endswith("/source.md"):
            continue
        if not str(image.get("sourceAssetRef") or ""):
            continue
        if require_rights_proof and not (
            str(image.get("authorizationProof") or "").strip()
            or str(image.get("termsUrl") or "").strip()
        ):
            continue
        placement = _placement_for(image)
        # 地图/位置图（locatorMap / coverCandidateRank<0）不可做封面，也不进正文内嵌：
        # 直接从主页可发布集合剔除（IR 已在 add_figure 标注，此处按真相源过滤）。
        if placement and _placement_is_map_like(placement):
            _exclude(
                image,
                HomepageAssetDisposition.POLICY_EXCLUDED,
                "locator_map_not_publishable",
            )
            continue
        if placement:
            from core.page_media import normalized_subject_key

            image = {
                **image,
                "caption": str(placement.get("caption") or image.get("caption") or image.get("relevance") or ""),
                "sectionAnchor": str(placement.get("sectionSlug") or ""),
                "paragraphIndex": int(placement.get("paragraphIndex") or 0),
                "sourceOrder": int(placement.get("sourceOrder") or 0),
                "placementType": str(placement.get("placementType") or "inline"),
                "groupId": str(placement.get("groupId") or ""),
                "coverCandidateRank": int(placement.get("coverCandidateRank") or 0),
                "subjectKey": str(placement.get("subjectKey") or "")
                or normalized_subject_key(
                    str(placement.get("caption") or image.get("caption") or ""),
                    str(placement.get("fileName") or ""),
                ),
            }
        candidates.append(image)
    if not candidates:
        candidates = [
            image
            for image in all_images
            if str(image.get("researchLane") or "") == "homepage_image"
            and str(image.get("sourceRef") or "").endswith("/source.md")
            and str(image.get("sourceAssetRef") or "")
            and (not require_rights_proof or (
                str(image.get("authorizationProof") or "").strip()
                or str(image.get("termsUrl") or "").strip()
            ))
        ]
    publishable_candidates: list[dict[str, Any]] = []
    from governance.content_supply_policy import load_content_supply_policy

    media_subject_policy = load_content_supply_policy(vertical).media_subject
    for image in candidates:
        prohibited_indicator = media_subject_policy.prohibited_indicator(
            image.get("caption"),
            image.get("relevance"),
            image.get("visualSubject"),
            image.get("sourceUrl"),
        )
        if prohibited_indicator or image.get("isRepresentativeVisual") is False:
            _exclude(
                image,
                HomepageAssetDisposition.POLICY_EXCLUDED,
                f"media_subject_not_representative:{prohibited_indicator or 'source_verdict'}",
            )
            continue
        publishable_candidates.append(image)
    candidates = publishable_candidates

    candidates.sort(
        key=lambda item: (
            int(item["sourceOrder"]) if "sourceOrder" in item else 9999,
            str(item.get("sourceAssetRef") or ""),
            str(item.get("caption") or ""),
        )
    )
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for image in candidates:
        key = str(image.get("sha256") or "") or str(image.get("sourceAssetRef") or "")
        if key in seen:
            _exclude(
                image,
                HomepageAssetDisposition.DUPLICATE_ALIAS,
                "duplicate_source_bytes",
            )
            continue
        seen.add(key)
        picked.append(image)
    if not picked:
        return HomepageAssetSelection((), tuple(excluded))

    from core.page_media import (
        normalized_subject_core,
        normalized_subject_key,
        subject_keys_conflict,
    )

    def _subject_core(item: Mapping[str, Any]) -> str:
        subject_key = str(item.get("subjectKey") or "").strip() or normalized_subject_key(
            str(item.get("caption") or item.get("relevance") or ""),
            str(item.get("sourceUrl") or item.get("sourceAssetRef") or ""),
        )
        return normalized_subject_core(
            subject_key,
            entity_name=name,
        )

    # 同一视觉主题只发布一张：正文锚定图优先于 lead/infobox/图集别名。
    # 被折叠的照片仍保留在 source unit 证据，不进入最终主页 manifest。
    deduped: list[dict[str, Any]] = []
    subject_index: dict[str, int] = {}
    for item in picked:
        subject = _subject_core(item)
        if not subject:
            deduped.append(item)
            continue
        previous_index = subject_index.get(subject)
        if previous_index is None:
            subject_index[subject] = len(deduped)
            deduped.append(item)
            continue
        previous = deduped[previous_index]
        if (
            str(item.get("placementType") or "") == "inline"
            and str(previous.get("placementType") or "") != "inline"
        ):
            _exclude(
                previous,
                HomepageAssetDisposition.DUPLICATE_ALIAS,
                "duplicate_visual_subject_prefers_inline_anchor",
            )
            deduped[previous_index] = item
        else:
            _exclude(
                item,
                HomepageAssetDisposition.DUPLICATE_ALIAS,
                "duplicate_visual_subject",
            )
    picked = deduped

    anchored_subjects = {
        _subject_core(item)
        for item in picked
        if str(item.get("placementType") or "") == "inline"
        and str(item.get("sectionAnchor") or "")
        and _subject_core(item)
    }

    def _subject_conflicts(item: Mapping[str, Any]) -> bool:
        subject = _subject_core(item)
        if not subject:
            return False
        return any(
            subject_keys_conflict(subject, anchored, entity_name=name)
            for anchored in anchored_subjects
        )
    cover_pool = [
        item
        for item in picked
        if str(item.get("placementType") or "") not in {"groupMember", "locatorMap"}
        and not bool(item.get("isMapLike"))
    ]
    non_conflicting = [
        item
        for item in cover_pool
        if not _subject_conflicts(item)
    ]

    def _cover_key(item: Mapping[str, Any]) -> tuple[int, int, int]:
        placement_type = str(item.get("placementType") or "")
        type_rank = {"lead": 0, "infoboxLead": 1, "inline": 2}.get(placement_type, 3)
        candidate_rank = int(item.get("coverCandidateRank") or 0)
        return (
            type_rank,
            candidate_rank if candidate_rank > 0 else 9999,
            int(item.get("sourceOrder") or 0),
        )

    cover = min(non_conflicting or cover_pool or picked, key=_cover_key)
    cover_subject = _subject_core(cover)
    publishable = [cover]
    for item in picked:
        if item is cover:
            continue
        subject = _subject_core(item)
        if cover_subject and subject and subject_keys_conflict(
            cover_subject,
            subject,
            entity_name=name,
        ):
            _exclude(
                item,
                HomepageAssetDisposition.DUPLICATE_ALIAS,
                "cover_visual_subject_conflict",
            )
            continue
        publishable.append(item)
    return HomepageAssetSelection(
        publishable=tuple(publishable),
        excluded=tuple(excluded),
    )


def copy_homepage_asset(
    execution_id: str,
    entity_dir: Path,
    name: str,
    image: dict[str, Any],
    *,
    role: str = "cover",
) -> dict[str, Any]:
    src = Path(str(image.get("path") or ""))
    if not src.is_file():
        return {}
    manifest = load_execution_runtime_state(execution_id)
    execution_sequence = manifest.execution_sequence if manifest is not None else 0
    if execution_sequence <= 0:
        return {}
    registry = load_execution_asset_registry(execution_id, execution_sequence)
    asset_id = allocate_post_asset_id(
        entity_name=name,
        role=role,
        ref=str(image.get("sourceAssetRef") or image.get("sourceRef") or entity_dir.as_posix()),
        execution_sequence=execution_sequence,
        registry=registry,
        caption=str(image.get("caption") or image.get("relevance") or ""),
        section_slug=str(image.get("sectionAnchor") or ""),
        ordinal=int(image.get("sourceOrder") or 0) + 1,
    )
    assets_dir = entity_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix or ".jpg"
    file_name = f"{asset_id}{suffix}"
    shutil.copyfile(src, assets_dir / file_name)
    return {
        "assetId": asset_id,
        "fileName": file_name,
        "role": role,
        "caption": str(image.get("caption") or image.get("relevance") or name).strip(),
        "license": str(image.get("license") or "").strip(),
        "credit": str(image.get("creator") or "").strip(),
        "relevance": str(image.get("relevance") or "").strip(),
        "placementType": str(image.get("placementType") or ""),
        "groupId": str(image.get("groupId") or ""),
        "sectionAnchor": str(image.get("sectionAnchor") or ""),
        "paragraphIndex": int(image.get("paragraphIndex") or 0),
        "sourceOrder": int(image.get("sourceOrder") or 0),
        "coverCandidateRank": int(image.get("coverCandidateRank") or 0),
        "subjectKey": str(image.get("subjectKey") or ""),
        "sourceRef": str(image.get("sourceRef") or "").strip(),
        "sourceAssetId": str(image.get("sourceAssetId") or "").strip(),
        "sourceAssetRef": str(image.get("sourceAssetRef") or "").strip(),
        "termsUrl": str(image.get("termsUrl") or "").strip(),
        "authorizationProof": str(image.get("authorizationProof") or "").strip(),
        "rightsAuditStatus": str(image.get("rightsAuditStatus") or "").strip(),
        "rightsAuditIssues": [
            str(issue)
            for issue in (image.get("rightsAuditIssues") or [])
            if str(issue).strip()
        ],
    }


def write_homepage_media_dispositions(
    *,
    entity_dir: Path,
    execution_id: str,
    object_ref: str,
    records: list["HomepageMediaDisposition"],
) -> None:
    """Persist one complete, schema-validated disposition per source asset."""

    from core.schema import assert_valid

    refs = [record.source_asset_ref for record in records]
    if len(refs) != len(set(refs)):
        raise ValueError(f"{object_ref}: homepage media disposition duplicates source assets")
    payload = {
        "schema": "quwoquan_data.homepage_media_dispositions",
        "executionId": execution_id,
        "objectRef": object_ref,
        "assets": [record.as_dict() for record in records],
    }
    assert_valid(
        payload,
        "content",
        "homepage_media_dispositions",
        label=f"homepage_media_dispositions:{object_ref}",
    )
    write_json(entity_dir / "evidence" / "media_dispositions.json", payload)
