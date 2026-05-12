from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from common import read_json, read_ndjson, write_ndjson
from crawl_runtime_contract import build_entity_row, entities_catalog_path, replace_ndjson_rows, stable_entity_id
from normalization.io_contracts import (
    ENTITY_RESOLUTION_RECORD_SCHEMA_VERSION,
    IMAGE_RESOLUTION_RECORD_SCHEMA_VERSION,
    entity_resolution_path,
    image_resolution_path,
    pending_resolution_path,
    source_resolution_path,
    stage_result_path,
)


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def _pick_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _accepted_main_entities(review: dict[str, Any], authority: dict[str, Any], escalate: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(escalate.get("resolvedMainEntities"), list):
        return [item for item in escalate.get("resolvedMainEntities") or [] if isinstance(item, dict)]
    if isinstance(review.get("acceptedMainEntities"), list):
        return [item for item in review.get("acceptedMainEntities") or [] if isinstance(item, dict)]
    return []


def _accepted_members(review: dict[str, Any], authority: dict[str, Any], escalate: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(escalate.get("resolvedMembers"), list):
        return [item for item in escalate.get("resolvedMembers") or [] if isinstance(item, dict)]
    members = [item for item in review.get("acceptedMembers") or [] if isinstance(item, dict)]
    rejected = {
        str(item.get("candidateRef", "")).strip()
        for checked in authority.get("checkedEntities") or []
        if isinstance(checked, dict)
        for item in checked.get("membershipRejected") or []
        if isinstance(item, dict)
    }
    if not rejected:
        return members
    return [item for item in members if str(item.get("candidateRef", "")).strip() not in rejected]


def _accepted_aliases(review: dict[str, Any], authority: dict[str, Any], escalate: dict[str, Any]) -> list[str]:
    values: list[str] = []
    if isinstance(escalate.get("resolvedAliases"), list):
        values.extend(str(item).strip() for item in escalate.get("resolvedAliases") or [] if str(item).strip())
    for row in review.get("acceptedAliases") or []:
        if isinstance(row, dict):
            alias = str(row.get("alias", "")).strip()
            if alias:
                values.append(alias)
    for checked in authority.get("checkedEntities") or []:
        if not isinstance(checked, dict):
            continue
        values.extend(str(item).strip() for item in checked.get("confirmedAliases") or [] if str(item).strip())
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _selected_assets(extract: dict[str, Any], review: dict[str, Any], escalate: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    image_rows = [item for item in extract.get("imageDecisions") or [] if isinstance(item, dict)]
    selected_refs = {
        str(item.get("assetId", "")).strip()
        for item in review.get("selectedContentAssets") or []
        if isinstance(item, dict)
    }
    selected_refs.update(
        {
            str(item.get("assetId", "")).strip()
            for item in escalate.get("selectedContentAssets") or []
            if isinstance(item, dict)
        }
    )
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in image_rows:
        asset_id = str(row.get("assetId", "")).strip()
        image_type = _pick_text(row, "imageType", "imageTypeCandidate")
        watermark = _pick_text(row, "watermarkStatus", "watermarkStatusCandidate") or "unknown"
        rights = _pick_text(row, "rightsStatus", "rightsStatusCandidate") or "unknown"
        record = {
            "assetId": asset_id,
            "assetSourceUrl": _pick_text(row, "assetSourceUrl", "sourceUrl"),
            "assetLocalPath": _pick_text(row, "assetLocalPath", "localPath"),
            "imageType": image_type or "unknown",
            "watermarkStatus": watermark,
            "rightsStatus": rights,
            "selectionReason": _pick_text(row, "selectionReason", "reasoningSummary"),
            "pageTitle": _pick_text(row, "pageTitle"),
        }
        is_selected = asset_id in selected_refs or (
            image_type == "content_photo"
            and watermark == "clean"
            and rights == "clear"
        )
        if is_selected:
            selected.append(record)
        else:
            rejected.append(record)
    return selected, rejected


def _authority_status(main: dict[str, Any], authority: dict[str, Any]) -> tuple[str, list[str]]:
    canonical = _pick_text(main, "canonicalZhHans", "nameCanonicalZhHansCandidate")
    refs: list[str] = []
    status = "pending"
    for checked in authority.get("checkedEntities") or []:
        if not isinstance(checked, dict):
            continue
        if _pick_text(checked, "confirmedCanonicalZhHans") == canonical and bool(checked.get("authorityMatched")):
            status = "verified"
            url = _pick_text(checked, "authorityUrl")
            if url:
                refs.append(url)
    return status, refs


def _main_entity_payload(main: dict[str, Any], authority: dict[str, Any], aliases: list[str]) -> dict[str, Any]:
    canonical = _pick_text(main, "confirmedCanonicalZhHans", "canonicalZhHans", "nameCanonicalZhHansCandidate")
    entity_type = _pick_text(main, "entityType", "entityTypeCandidate") or "scenic_spot"
    authority_status, refs = _authority_status(main, authority)
    return {
        "canonicalZhHans": canonical,
        "entityType": entity_type,
        "summary": _pick_text(main, "summary", "reasoningSummary", "authoritySummary"),
        "authorityStatus": authority_status,
        "authorityRefs": refs,
        "aliases": [item for item in aliases if item and item != canonical],
    }


def _append_unique_text(target: list[str], value: str) -> None:
    item = str(value or "").strip()
    if item and item not in target:
        target.append(item)


def _dedupe_texts(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        _append_unique_text(out, value)
    return out


def _admission_track(main: dict[str, Any], resolution: dict[str, Any]) -> str:
    has_authority = bool(main.get("authorityRefs")) or _pick_text(main, "authorityStatus") == "verified"
    evidence_urls = [str(item).strip() for item in resolution.get("evidenceArticleUrls") or [] if str(item).strip()]
    if has_authority and evidence_urls:
        return "authority_plus_post"
    if has_authority:
        return "authority"
    if len(evidence_urls) >= 2:
        return "post_evidence"
    return str(main.get("admissionTrack") or "authority").strip() or "authority"


def _conflict_check_status(main: dict[str, Any], resolution: dict[str, Any]) -> str:
    explicit = str(
        resolution.get("conflictCheckStatus")
        or main.get("conflictCheckStatus")
        or ""
    ).strip()
    if explicit:
        return explicit
    evidence_urls = [str(item).strip() for item in resolution.get("evidenceArticleUrls") or [] if str(item).strip()]
    if _pick_text(main, "authorityStatus") == "verified":
        return "pass"
    return "pass" if len(evidence_urls) >= 2 and not bool(resolution.get("manualReviewRequired")) else "pending"


def compile_batch(batch_label: str) -> dict[str, Any]:
    source_records: list[dict[str, Any]] = []
    pending_records: list[dict[str, Any]] = []
    image_records: list[dict[str, Any]] = []
    aggregated: dict[str, dict[str, Any]] = {}
    extract_dir = stage_result_path(batch_label, "extract", "placeholder").parent
    for result_path in sorted(extract_dir.glob("*.json")):
        extract = _read_json_if_exists(result_path)
        source_ref = _pick_text(extract, "sourceRef")
        if not source_ref:
            continue
        review = _read_json_if_exists(stage_result_path(batch_label, "review", source_ref))
        authority = _read_json_if_exists(stage_result_path(batch_label, "authority", source_ref))
        escalate = _read_json_if_exists(stage_result_path(batch_label, "escalate", source_ref))
        mains = _accepted_main_entities(review, authority, escalate)
        members = _accepted_members(review, authority, escalate)
        aliases = _accepted_aliases(review, authority, escalate)
        selected_assets, rejected_assets = _selected_assets(extract, review, escalate)
        source_summary = {
            "sourceRef": source_ref,
            "sourceUrl": _pick_text(extract, "sourceUrl"),
            "sourceTitle": _pick_text(extract, "sourceTitle"),
            "catalogTopicId": _pick_text(extract, "catalogTopicId"),
            "mainEntityCount": len(mains),
            "memberCount": len(members),
            "selectedAssetCount": len(selected_assets),
            "manualReviewRequired": bool(review.get("needsAuthorityBackcheck"))
            or not mains,
        }
        source_records.append(source_summary)
        if not mains:
            pending_records.append(
                {
                    "sourceRef": source_ref,
                    "sourceUrl": _pick_text(extract, "sourceUrl"),
                    "sourceTitle": _pick_text(extract, "sourceTitle"),
                    "catalogTopicId": _pick_text(extract, "catalogTopicId"),
                    "reason": "missing_main_entity",
                }
            )
            continue
        for main in mains:
            canonical = _pick_text(main, "confirmedCanonicalZhHans", "canonicalZhHans", "nameCanonicalZhHansCandidate")
            entity_type = _pick_text(main, "entityType", "entityTypeCandidate") or "scenic_spot"
            key = hashlib.sha1(f"{canonical}|{entity_type}".encode("utf-8")).hexdigest()[:20]
            record = aggregated.setdefault(
                key,
                {
                    "schemaVersion": ENTITY_RESOLUTION_RECORD_SCHEMA_VERSION,
                    "sourceRefs": [],
                    "catalogTopicIds": [],
                    "mainEntity": _main_entity_payload(main, authority, aliases),
                    "members": [],
                    "rejectedMembers": [],
                    "rawPoiRefs": [],
                    "sourceResultRefs": [],
                    "selectedContentAssets": [],
                    "rejectedAssets": [],
                    "normalizationStatus": "compiled",
                    "manualReviewRequired": False,
                    "evidenceArticleUrls": [],
                    "evidenceIndependenceNotes": [],
                    "conflictCheckStatus": "pending",
                },
            )
            if source_ref not in record["sourceRefs"]:
                record["sourceRefs"].append(source_ref)
            topic_id = _pick_text(extract, "catalogTopicId")
            if topic_id and topic_id not in record["catalogTopicIds"]:
                record["catalogTopicIds"].append(topic_id)
            record["manualReviewRequired"] = bool(record["manualReviewRequired"]) or bool(
                review.get("needsAuthorityBackcheck")
            )
            source_url = _pick_text(extract, "sourceUrl")
            _append_unique_text(record["evidenceArticleUrls"], source_url)
            _append_unique_text(
                record["evidenceIndependenceNotes"],
                f"source_ref:{source_ref}",
            )
            for member in members:
                member_name = _pick_text(member, "nameCanonicalZhHans", "nameCanonicalZhHansCandidate")
                if not member_name:
                    continue
                entry = {
                    "nameCanonicalZhHans": member_name,
                    "memberRole": _pick_text(member, "memberRole"),
                    "ordinal": _pick_text(member, "ordinal"),
                    "catalogTopicIds": [topic_id] if topic_id else [],
                    "evidenceRefs": list(member.get("evidenceRefs") or []),
                }
                if entry not in record["members"]:
                    record["members"].append(entry)
            for asset in selected_assets:
                asset_entry = dict(asset)
                asset_entry["sourceRef"] = source_ref
                if asset_entry not in record["selectedContentAssets"]:
                    record["selectedContentAssets"].append(asset_entry)
            for asset in rejected_assets:
                asset_entry = dict(asset)
                asset_entry["sourceRef"] = source_ref
                if asset_entry not in record["rejectedAssets"]:
                    record["rejectedAssets"].append(asset_entry)
            record["sourceResultRefs"].append(
                {
                    "extract": str(result_path),
                    "review": str(stage_result_path(batch_label, "review", source_ref)),
                    "authority": str(stage_result_path(batch_label, "authority", source_ref)),
                    "escalate": str(stage_result_path(batch_label, "escalate", source_ref)),
                }
            )
        for asset in selected_assets + rejected_assets:
            image_records.append(
                {
                    "schemaVersion": IMAGE_RESOLUTION_RECORD_SCHEMA_VERSION,
                    **asset,
                    "sourceRef": source_ref,
                    "catalogTopicId": _pick_text(extract, "catalogTopicId"),
                }
            )
    for record in aggregated.values():
        main = record.get("mainEntity") or {}
        if not isinstance(main, dict):
            continue
        record["evidenceArticleUrls"] = _dedupe_texts(list(record.get("evidenceArticleUrls") or []))
        record["evidenceIndependenceNotes"] = _dedupe_texts(list(record.get("evidenceIndependenceNotes") or []))
        main["admissionTrack"] = _admission_track(main, record)
        main["conflictCheckStatus"] = _conflict_check_status(main, record)
        record["conflictCheckStatus"] = main["conflictCheckStatus"]
    write_ndjson(source_resolution_path(batch_label), source_records)
    write_ndjson(entity_resolution_path(batch_label), list(aggregated.values()))
    write_ndjson(pending_resolution_path(batch_label), pending_records)
    write_ndjson(image_resolution_path(batch_label), image_records)
    return {
        "sourceCount": len(source_records),
        "entityCount": len(aggregated),
        "pendingCount": len(pending_records),
        "imageCount": len(image_records),
    }


def build_entity_catalog_rows(
    *,
    resolution_rows: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
    source: str = "normalization",
) -> list[dict[str, Any]]:
    topic_to_row = {
        str(row.get("topic_id") or row.get("topicId") or "").strip(): row
        for row in catalog_rows
        if isinstance(row, dict) and str(row.get("topic_id") or row.get("topicId") or "").strip()
    }
    rows: list[dict[str, Any]] = []
    for resolution in resolution_rows:
        main = resolution.get("mainEntity") or {}
        if not isinstance(main, dict):
            continue
        canonical = _pick_text(main, "canonicalZhHans")
        entity_type = _pick_text(main, "entityType") or "scenic_spot"
        if not canonical:
            continue
        catalog_topic_ids = [str(item).strip() for item in resolution.get("catalogTopicIds") or [] if str(item).strip()]
        sample = topic_to_row.get(catalog_topic_ids[0], {}) if catalog_topic_ids else {}
        aliases = [str(item).strip() for item in main.get("aliases") or [] if str(item).strip()]
        tag_refs = [str(item).strip() for item in sample.get("tagRefs") or [] if str(item).strip()]
        rows.append(
            build_entity_row(
                entity_id=stable_entity_id(canonical, entity_type),
                canonical_name=canonical,
                entity_type=entity_type,
                aliases=aliases,
                tag_refs=tag_refs,
                topic_id=catalog_topic_ids[0] if catalog_topic_ids else "",
                source=source,
                extensions={
                    "labelZh": canonical,
                    "labelEn": "",
                    "displayLocale": "zh-Hans",
                    "entityTypeLabelZh": str(sample.get("entity_type_label_zh") or sample.get("entityTypeLabelZh") or "").strip(),
                    "wikiTitle": str(sample.get("wiki_title") or sample.get("wikiTitle") or canonical).strip(),
                    "baikeItem": str(sample.get("baike_item") or sample.get("baikeItem") or canonical).strip(),
                    "rawName": str(sample.get("raw_name") or sample.get("rawName") or canonical).strip(),
                    "normalizedName": canonical,
                    "province": str(sample.get("province") or "").strip(),
                    "prefecture": str(sample.get("prefecture") or "").strip(),
                    "district": str(sample.get("district") or "").strip(),
                    "expectedRegionKeywords": list(sample.get("expected_region_keywords") or sample.get("expectedRegionKeywords") or []),
                    "coreTokens": list(sample.get("core_tokens") or sample.get("coreTokens") or []),
                    "members": resolution.get("members") or [],
                    "selectedContentAssets": resolution.get("selectedContentAssets") or [],
                    "rejectedAssets": resolution.get("rejectedAssets") or [],
                    "sourceRefs": resolution.get("sourceRefs") or [],
                    "authorityStatus": _pick_text(main, "authorityStatus") or "pending",
                    "authorityRefs": list(main.get("authorityRefs") or []),
                    "admissionTrack": _admission_track(main, resolution),
                    "evidenceArticleUrls": list(resolution.get("evidenceArticleUrls") or []),
                    "evidenceIndependenceNotes": list(resolution.get("evidenceIndependenceNotes") or []),
                    "conflictCheckStatus": _conflict_check_status(main, resolution),
                    "undevelopedOrWildAccess": bool(
                        resolution.get("undevelopedOrWildAccess")
                        or main.get("undevelopedOrWildAccess")
                        or sample.get("undeveloped_or_wild_access")
                        or sample.get("undevelopedOrWildAccess")
                    ),
                    "normalizationStatus": str(resolution.get("normalizationStatus") or "compiled"),
                    "manualReviewRequired": bool(resolution.get("manualReviewRequired")),
                },
            )
        )
    return rows


def materialize_entity_catalog(*, batch_label: str, catalog_rows: list[dict[str, Any]], output_name: str = "entities.ndjson") -> dict[str, Any]:
    rows = build_entity_catalog_rows(
        resolution_rows=read_ndjson(entity_resolution_path(batch_label)),
        catalog_rows=catalog_rows,
        source="normalization",
    )
    path = entities_catalog_path(output_name)
    result = replace_ndjson_rows(path, rows, key_fields=["entityId"])
    return {"count": len(result), "path": str(path)}

