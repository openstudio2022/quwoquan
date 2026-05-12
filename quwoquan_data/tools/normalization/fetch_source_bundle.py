from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import hashlib

from common import ensure_directory, now_iso, runtime_rel_ref, write_json, write_ndjson, write_text
from native_fetch import NativeFetchError, download_binary, fetch_html_page, safe_filename_from_url
from normalization.io_contracts import (
    SOURCE_ASSET_MANIFEST_SCHEMA_VERSION,
    SOURCE_BLOCK_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA_VERSION,
    SOURCE_FETCH_INPUT_SCHEMA_VERSION,
    ensure_normalization_layout,
    source_bundle_asset_manifest_path,
    source_bundle_assets_dir,
    source_bundle_blocks_path,
    source_bundle_dir,
    source_bundle_fetch_receipt_path,
    source_bundle_markdown_path,
    source_bundle_page_html_path,
    source_bundle_page_json_path,
    source_bundle_page_text_path,
)
from normalization.source_ref import build_source_ref, normalize_domain


def _block_rows(*, source_ref: str, title: str, paragraphs: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if title:
        rows.append(
            {
                "schemaVersion": SOURCE_BLOCK_SCHEMA_VERSION,
                "sourceRef": source_ref,
                "blockId": "block_0000",
                "index": 0,
                "role": "title",
                "text": title,
                "charCount": len(title),
                "evidenceHint": "page_title",
            }
        )
    for index, paragraph in enumerate(paragraphs, start=1):
        role = "lead" if index == 1 else "paragraph"
        rows.append(
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
    return rows


def _markdown_text(
    *,
    source_ref: str,
    batch_label: str,
    source_url: str,
    final_url: str,
    fetched_at: str,
    page_title: str,
    paragraphs: list[str],
) -> str:
    lines = [
        "---",
        f"source_ref: {source_ref}",
        f"batch_label: {batch_label}",
        f"url: {source_url}",
        f"final_url: {final_url}",
        f"fetched_at: {fetched_at}",
        "---",
        "",
        f"# {page_title}",
        "",
    ]
    for paragraph in paragraphs:
        lines.extend([paragraph, ""])
    return "\n".join(lines).strip() + "\n"


def _asset_rows(
    *,
    batch_label: str,
    source_ref: str,
    page_title: str,
    source_url: str,
    image_urls: list[str],
    max_assets: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    assets_dir = source_bundle_assets_dir(batch_label, source_ref)
    ensure_directory(assets_dir)
    for index, image_url in enumerate(image_urls[:max_assets], start=1):
        filename = safe_filename_from_url(image_url, fallback=f"asset_{index:02d}.bin")
        target = assets_dir / filename
        try:
            downloaded = download_binary(image_url, target)
        except NativeFetchError:
            continue
        rows.append(
            {
                "assetId": f"{source_ref}_asset_{index:02d}",
                "assetSourceUrl": downloaded.source_url,
                "assetLocalPath": runtime_rel_ref(downloaded.local_path),
                "sourcePageUrl": source_url,
                "pageTitle": page_title,
                "sourcePlatform": normalize_domain(urlparse(downloaded.source_url).netloc)
                or normalize_domain(urlparse(source_url).netloc),
                "mimeType": downloaded.mime_type,
                "width": int(downloaded.width or 0),
                "height": int(downloaded.height or 0),
                "sha256": downloaded.sha256,
                "sizeBytes": downloaded.size_bytes,
                "downloadStatus": "downloaded",
                "rightsStatus": "unknown",
                "watermarkStatus": "unknown",
                "assetRoleHint": "embedded_candidate",
                "imageTypeCandidate": "unknown",
                "pageMetadataTitle": page_title,
                "pageMetadataSnippet": page_title,
                "pageMetadataAuthor": "",
                "pageMetadataDescription": "",
                "license": {"name": "unknown", "usage": "requires_review"},
            }
        )
    return rows


def fetch_source_bundle(
    *,
    batch_label: str,
    source_url: str,
    page_title: str = "",
    catalog_topic_id: str = "",
    catalog_name: str = "",
    source_type: str = "article",
    max_assets: int = 8,
) -> dict[str, Any]:
    ensure_normalization_layout(batch_label)
    input_payload = {
        "schemaVersion": SOURCE_FETCH_INPUT_SCHEMA_VERSION,
        "batchLabel": str(batch_label).strip(),
        "catalogTopicId": str(catalog_topic_id).strip(),
        "catalogName": str(catalog_name).strip(),
        "sourceType": str(source_type or "article").strip() or "article",
        "sourceUrl": str(source_url).strip(),
        "pageTitle": str(page_title).strip(),
        "maxAssets": int(max_assets),
    }
    fetched = fetch_html_page(str(source_url).strip())
    resolved_title = str(page_title or fetched.title).strip() or str(source_url).strip()
    source_ref = build_source_ref(
        source_url=fetched.final_url or str(source_url).strip(),
        page_title=resolved_title,
        catalog_topic_id=str(catalog_topic_id).strip(),
    )
    bundle_dir = source_bundle_dir(batch_label, source_ref)
    ensure_directory(bundle_dir)
    fetched_at = now_iso()
    html_path = source_bundle_page_html_path(batch_label, source_ref)
    write_text(html_path, fetched.html)
    text_path = source_bundle_page_text_path(batch_label, source_ref)
    write_text(text_path, fetched.text.strip() + ("\n" if fetched.text.strip() else ""))
    markdown_path = source_bundle_markdown_path(batch_label, source_ref)
    write_text(
        markdown_path,
        _markdown_text(
            source_ref=source_ref,
            batch_label=batch_label,
            source_url=str(source_url).strip(),
            final_url=fetched.final_url,
            fetched_at=fetched_at,
            page_title=resolved_title,
            paragraphs=fetched.paragraphs,
        ),
    )
    block_rows = _block_rows(source_ref=source_ref, title=resolved_title, paragraphs=fetched.paragraphs)
    blocks_path = source_bundle_blocks_path(batch_label, source_ref)
    write_ndjson(blocks_path, block_rows)
    assets = _asset_rows(
        batch_label=batch_label,
        source_ref=source_ref,
        page_title=resolved_title,
        source_url=fetched.final_url,
        image_urls=fetched.image_urls,
        max_assets=max_assets,
    )
    asset_manifest = {
        "schemaVersion": SOURCE_ASSET_MANIFEST_SCHEMA_VERSION,
        "sourceRef": source_ref,
        "sourceUrl": str(source_url).strip(),
        "finalUrl": fetched.final_url,
        "pageTitle": resolved_title,
        "assets": assets,
    }
    asset_manifest_path = source_bundle_asset_manifest_path(batch_label, source_ref)
    write_json(asset_manifest_path, asset_manifest)
    bundle_payload = {
        "schemaVersion": SOURCE_BUNDLE_SCHEMA_VERSION,
        "sourceRef": source_ref,
        "batchLabel": str(batch_label).strip(),
        "catalogTopicId": str(catalog_topic_id).strip(),
        "catalogName": str(catalog_name).strip(),
        "sourceType": str(source_type or "article").strip() or "article",
        "sourceUrl": str(source_url).strip(),
        "finalUrl": fetched.final_url,
        "pageTitle": resolved_title,
        "fetchedAt": fetched_at,
        "fetchMethod": "native_fetch",
        "contentType": "text/html",
        "htmlPath": runtime_rel_ref(html_path),
        "markdownPath": runtime_rel_ref(markdown_path),
        "plainTextPath": runtime_rel_ref(text_path),
        "sourceBlocksPath": runtime_rel_ref(blocks_path),
        "assetManifestPath": runtime_rel_ref(asset_manifest_path),
        "htmlSha256": hashlib.sha256(fetched.html.encode("utf-8")).hexdigest(),
        "textSha256": hashlib.sha256(fetched.text.encode("utf-8")).hexdigest(),
        "paragraphCount": len(fetched.paragraphs),
        "assetCount": len(assets),
        "fetchStatus": "fetched",
        "warnings": [],
        "inputs": input_payload,
    }
    write_json(source_bundle_page_json_path(batch_label, source_ref), bundle_payload)
    write_json(source_bundle_fetch_receipt_path(batch_label, source_ref), bundle_payload)
    return bundle_payload

