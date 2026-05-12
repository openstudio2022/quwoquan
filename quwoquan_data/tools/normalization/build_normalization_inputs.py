from __future__ import annotations

from pathlib import Path
from typing import Any

from common import read_json, read_text, runtime_rel_ref, write_json
from crawl_runtime_contract import load_entities_catalog
from normalization.io_contracts import (
    AUTHORITY_BACKCHECK_INPUT_SCHEMA_VERSION,
    EVIDENCE_ESCALATION_INPUT_SCHEMA_VERSION,
    SOURCE_EXTRACTION_INPUT_SCHEMA_VERSION,
    SOURCE_REVIEW_INPUT_SCHEMA_VERSION,
    source_bundle_asset_manifest_path,
    source_bundle_page_json_path,
    source_bundle_page_text_path,
    stage_input_path,
    stage_result_path,
)


def _entity_context_refs(catalog_topic_id: str) -> list[dict[str, Any]]:
    topic_id = str(catalog_topic_id).strip()
    if not topic_id:
        return []
    rows: list[dict[str, Any]] = []
    for entity in load_entities_catalog():
        if str(entity.get("topicId", "")).strip() != topic_id:
            continue
        rows.append(
            {
                "entityId": str(entity.get("entityId", "")).strip(),
                "canonicalName": str(entity.get("canonicalName", "")).strip(),
                "entityType": str(entity.get("entityType", "")).strip(),
                "aliases": list(entity.get("aliases") or []),
            }
        )
    return rows


def _bundle_from_source_md(source_markdown_path: str) -> tuple[dict[str, Any], Path]:
    path = Path(str(source_markdown_path).strip())
    if not path.is_absolute():
        path = path.resolve()
    bundle_dir = path.parent
    bundle = read_json(bundle_dir / "page.json")
    if not isinstance(bundle, dict):
        raise ValueError(f"bundle 非法（非 object）: {bundle_dir / 'page.json'}")
    return bundle, bundle_dir


def build_extract_input(
    *,
    batch_label: str,
    source_markdown_path: str,
    catalog_topic_id: str = "",
    catalog_name: str = "",
) -> dict[str, Any]:
    bundle, bundle_dir = _bundle_from_source_md(source_markdown_path)
    source_ref = str(bundle.get("sourceRef", "")).strip()
    batch = str(bundle.get("batchLabel", "")).strip() or str(batch_label).strip()
    topic_id = str(catalog_topic_id or bundle.get("catalogTopicId") or "").strip()
    catalog_label = str(catalog_name or bundle.get("catalogName") or "").strip()
    page_text = read_text(source_bundle_page_text_path(batch, source_ref)) if source_ref else ""
    asset_manifest = read_json(source_bundle_asset_manifest_path(batch, source_ref))
    assets = asset_manifest.get("assets") or []
    payload = {
        "schemaVersion": SOURCE_EXTRACTION_INPUT_SCHEMA_VERSION,
        "sourceRef": source_ref,
        "batchLabel": batch,
        "catalogTopicId": topic_id,
        "catalogName": catalog_label,
        "entityContextRefs": _entity_context_refs(topic_id),
        "sourceType": str(bundle.get("sourceType", "article")).strip() or "article",
        "sourceUrl": str(bundle.get("sourceUrl", "")).strip(),
        "sourceTitle": str(bundle.get("pageTitle", "")).strip(),
        "sourceBodyText": page_text,
        "sourceMarkdownPath": str(Path(source_markdown_path).resolve()),
        "imageAssetRefs": [str(item.get("assetId", "")).strip() for item in assets if str(item.get("assetId", "")).strip()],
        "assetLocalPaths": [str(item.get("assetLocalPath", "")).strip() for item in assets if str(item.get("assetLocalPath", "")).strip()],
        "authorityHints": {
            "bundlePath": runtime_rel_ref(bundle_dir),
            "finalUrl": str(bundle.get("finalUrl", "")).strip(),
        },
        "regionHints": {"catalogName": catalog_label},
        "catalogHints": {
            "catalogTopicId": topic_id,
            "catalogName": catalog_label,
        },
        "normalizationHints": {
            "canonicalLanguage": "zh-Hans",
            "allowSyntheticParent": False,
            "outputModel": "main_entity_members_aliases",
        },
        "requiredOutputSchema": "source_extraction_result.schema.json",
    }
    write_json(stage_input_path(batch, "extract", source_ref), payload)
    return payload


def build_review_input(*, extract_result_path: str) -> dict[str, Any]:
    extract_path = Path(str(extract_result_path).strip()).resolve()
    extract_result = read_json(extract_path)
    source_ref = str(extract_result.get("sourceRef", "")).strip()
    batch = str(extract_result.get("batchLabel", "")).strip()
    extract_input = read_json(stage_input_path(batch, "extract", source_ref))
    payload = {
        "schemaVersion": SOURCE_REVIEW_INPUT_SCHEMA_VERSION,
        "sourceRef": source_ref,
        "batchLabel": batch,
        "sourceUrl": str(extract_result.get("sourceUrl", "")).strip(),
        "sourceTitle": str(extract_result.get("sourceTitle", "")).strip(),
        "sourceMarkdownPath": str(extract_result.get("sourceMarkdownPath", "")).strip(),
        "extractInputPath": str(stage_input_path(batch, "extract", source_ref)),
        "extractResultPath": str(extract_path),
        "extractInput": extract_input,
        "extractResult": extract_result,
        "requiredOutputSchema": "source_review_result.schema.json",
    }
    write_json(stage_input_path(batch, "review", source_ref), payload)
    return payload


def build_authority_backcheck_input(*, review_result_path: str) -> dict[str, Any]:
    review_path = Path(str(review_result_path).strip()).resolve()
    review_result = read_json(review_path)
    source_ref = str(review_result.get("sourceRef", "")).strip()
    batch = str(review_result.get("batchLabel", "")).strip()
    if not batch:
        batch = str(Path(review_path).parents[3].name)
    extract_result = read_json(stage_result_path(batch, "extract", source_ref))
    payload = {
        "schemaVersion": AUTHORITY_BACKCHECK_INPUT_SCHEMA_VERSION,
        "sourceRef": source_ref,
        "batchLabel": batch,
        "sourceUrl": str(review_result.get("sourceUrl", "")).strip(),
        "sourceTitle": str(review_result.get("sourceTitle", "")).strip(),
        "reviewResultPath": str(review_path),
        "extractResultPath": str(stage_result_path(batch, "extract", source_ref)),
        "reviewResult": review_result,
        "extractResult": extract_result,
        "authorityHints": {
            "mainEntityCandidates": review_result.get("acceptedMainEntities") or [],
            "aliasCandidates": review_result.get("acceptedAliases") or [],
        },
        "requiredOutputSchema": "authority_backcheck_result.schema.json",
    }
    write_json(stage_input_path(batch, "authority", source_ref), payload)
    return payload


def build_escalation_input(*, authority_result_path: str) -> dict[str, Any]:
    authority_path = Path(str(authority_result_path).strip()).resolve()
    authority_result = read_json(authority_path)
    source_ref = str(authority_result.get("sourceRef", "")).strip()
    batch = str(authority_result.get("batchLabel", "")).strip()
    if not batch:
        batch = str(Path(authority_path).parents[3].name)
    review_result = read_json(stage_result_path(batch, "review", source_ref))
    payload = {
        "schemaVersion": EVIDENCE_ESCALATION_INPUT_SCHEMA_VERSION,
        "sourceRef": source_ref,
        "batchLabel": batch,
        "sourceUrl": str(authority_result.get("sourceUrl", "")).strip(),
        "sourceTitle": str(authority_result.get("sourceTitle", "")).strip(),
        "reviewResultPath": str(stage_result_path(batch, "review", source_ref)),
        "authorityResultPath": str(authority_path),
        "reviewResult": review_result,
        "authorityResult": authority_result,
        "requiredOutputSchema": "evidence_escalation_result.schema.json",
    }
    write_json(stage_input_path(batch, "escalate", source_ref), payload)
    return payload

