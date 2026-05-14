from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from common import RUNTIME_ROOT, ensure_directory, read_json, read_text, runtime_rel_ref, write_json, write_ndjson, write_text
from crawl_runtime_contract import load_entities_catalog
from normalization.source_ref import build_source_ref
from normalization.io_contracts import (
    AUTHORITY_BACKCHECK_INPUT_SCHEMA_VERSION,
    EVIDENCE_ESCALATION_INPUT_SCHEMA_VERSION,
    SOURCE_EXTRACTION_INPUT_SCHEMA_VERSION,
    SOURCE_ASSET_MANIFEST_SCHEMA_VERSION,
    SOURCE_BLOCK_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA_VERSION,
    SOURCE_REVIEW_INPUT_SCHEMA_VERSION,
    source_bundle_asset_manifest_path,
    source_bundle_blocks_path,
    source_bundle_dir,
    source_bundle_markdown_path,
    source_bundle_page_html_path,
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


def _strip_markdown_front_matter(markdown: str) -> str:
    text = str(markdown or "")
    if not text.startswith("---"):
        return text
    parts = text.split("\n---", 1)
    if len(parts) != 2:
        return text
    return parts[1].lstrip()


def _markdown_title(markdown: str, fallback: str = "") -> str:
    for line in _strip_markdown_front_matter(markdown).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return str(fallback).strip()


def _markdown_body_text(markdown: str) -> str:
    lines = []
    for line in _strip_markdown_front_matter(markdown).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _resolve_runtime_ref(raw: str) -> Path:
    path = Path(str(raw or "").strip())
    if path.is_absolute():
        return path.resolve()
    return (RUNTIME_ROOT / path).resolve()


def _topic_asset_rows_to_source_manifest(
    *,
    asset_manifest_path: Path,
    source_ref: str,
    page_title: str,
    source_url: str,
) -> dict[str, Any]:
    payload = _read_json_if_exists(asset_manifest_path)
    assets = []
    for row in payload.get("assets") or []:
        if not isinstance(row, dict):
            continue
        assets.append(
            {
                "assetId": str(row.get("assetId", "")).strip(),
                "assetSourceUrl": str(row.get("sourceUrl", "")).strip(),
                "assetLocalPath": str(row.get("localPath", "")).strip(),
                "sourcePageUrl": source_url,
                "pageTitle": page_title,
                "sourcePlatform": "",
                "mimeType": str(row.get("mimeType", "")).strip(),
                "width": int(row.get("width") or 0),
                "height": int(row.get("height") or 0),
                "sha256": str(row.get("sha256", "")).strip(),
                "sizeBytes": int(row.get("sizeBytes") or 0),
                "downloadStatus": str(row.get("downloadStatus", "")).strip() or "downloaded",
                "rightsStatus": str(row.get("rightsStatus", "")).strip() or "unknown",
                "watermarkStatus": str(row.get("watermarkStatus", "")).strip() or "unknown",
                "assetRoleHint": "embedded_candidate",
                "imageTypeCandidate": str(row.get("imageTypeCandidate", "")).strip() or "unknown",
                "pageMetadataTitle": page_title,
                "pageMetadataSnippet": page_title,
                "pageMetadataAuthor": "",
                "pageMetadataDescription": "",
                "license": {"name": "unknown", "usage": "requires_review"},
            }
        )
    return {
        "schemaVersion": SOURCE_ASSET_MANIFEST_SCHEMA_VERSION,
        "sourceRef": source_ref,
        "sourceUrl": source_url,
        "finalUrl": source_url,
        "pageTitle": page_title,
        "assets": assets,
    }


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def import_hydrated_topic_page_and_build_extract_input(
    *,
    batch_label: str,
    spec_id: str,
    catalog_topic_id: str,
    catalog_name: str,
    source_row: dict[str, Any],
    page_dir: Path,
) -> dict[str, Any]:
    source_md_path = page_dir / "source.md"
    page_html_path = page_dir / "page.html"
    asset_manifest_path = page_dir / "asset_manifest.json"
    if not source_md_path.exists():
        raise FileNotFoundError(f"缺少 source.md: {source_md_path}")
    source_markdown = read_text(source_md_path)
    page_title = _markdown_title(source_markdown, fallback=str(source_row.get("title", "")).strip() or str(source_row.get("snippet", "")).strip())
    source_url = str(source_row.get("sourceUrl", "")).strip()
    if not source_url:
        raise ValueError(f"缺少 sourceUrl: spec={spec_id} entity={entity_id} topic={catalog_topic_id}")
    source_ref = build_source_ref(
        source_url=source_url,
        page_title=page_title,
        catalog_topic_id=str(catalog_topic_id).strip(),
    )
    bundle_dir = source_bundle_dir(batch_label, source_ref)
    ensure_directory(bundle_dir)
    imported_source_md = source_bundle_markdown_path(batch_label, source_ref)
    write_text(imported_source_md, source_markdown)
    if page_html_path.exists():
        shutil.copy2(page_html_path, source_bundle_page_html_path(batch_label, source_ref))
    write_text(source_bundle_page_text_path(batch_label, source_ref), _markdown_body_text(source_markdown) + "\n")
    body_text = _markdown_body_text(source_markdown)
    block_rows = []
    if page_title:
        block_rows.append(
            {
                "schemaVersion": SOURCE_BLOCK_SCHEMA_VERSION,
                "sourceRef": source_ref,
                "blockId": "block_0000",
                "index": 0,
                "role": "title",
                "text": page_title,
                "charCount": len(page_title),
                "evidenceHint": "page_title",
            }
        )
    for index, paragraph in enumerate([line for line in body_text.splitlines() if line.strip()], start=1):
        role = "lead" if index == 1 else "paragraph"
        block_rows.append(
            {
                "schemaVersion": SOURCE_BLOCK_SCHEMA_VERSION,
                "sourceRef": source_ref,
                "blockId": f"block_{index:04d}",
                "index": index,
                "role": role,
                "text": paragraph,
                "charCount": len(paragraph),
                "evidenceHint": role,
            }
        )
    write_ndjson(source_bundle_blocks_path(batch_label, source_ref), block_rows)
    asset_manifest = _topic_asset_rows_to_source_manifest(
        asset_manifest_path=asset_manifest_path,
        source_ref=source_ref,
        page_title=page_title,
        source_url=source_url,
    )
    write_json(source_bundle_asset_manifest_path(batch_label, source_ref), asset_manifest)
    bundle_payload = {
        "schemaVersion": SOURCE_BUNDLE_SCHEMA_VERSION,
        "sourceRef": source_ref,
        "batchLabel": str(batch_label).strip(),
        "catalogTopicId": str(catalog_topic_id).strip(),
        "catalogName": str(catalog_name).strip(),
        "sourceType": str(source_row.get("mediaType", "")).strip() or "article",
        "sourceUrl": source_url,
        "finalUrl": source_url,
        "pageTitle": page_title,
        "fetchedAt": "",
        "fetchMethod": "topic_hydrate_import",
        "contentType": "text/html",
        "htmlPath": runtime_rel_ref(source_bundle_page_html_path(batch_label, source_ref)) if page_html_path.exists() else "",
        "markdownPath": runtime_rel_ref(imported_source_md),
        "plainTextPath": runtime_rel_ref(source_bundle_page_text_path(batch_label, source_ref)),
        "sourceBlocksPath": runtime_rel_ref(source_bundle_blocks_path(batch_label, source_ref)),
        "assetManifestPath": runtime_rel_ref(source_bundle_asset_manifest_path(batch_label, source_ref)),
        "htmlSha256": "",
        "textSha256": "",
        "paragraphCount": len([line for line in body_text.splitlines() if line.strip()]),
        "assetCount": len(asset_manifest.get("assets") or []),
        "fetchStatus": "imported",
        "warnings": [],
        "inputs": {
            "specId": str(spec_id).strip(),
            "pageDir": runtime_rel_ref(page_dir),
        },
    }
    write_json(source_bundle_page_json_path(batch_label, source_ref), bundle_payload)
    return build_extract_input(
        batch_label=batch_label,
        source_markdown_path=str(imported_source_md),
        catalog_topic_id=str(catalog_topic_id).strip(),
        catalog_name=str(catalog_name).strip(),
    )


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

