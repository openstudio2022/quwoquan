"""Licensed asset ingest for site-supply image works."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import mimetypes
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from _common.image_rules import pixel_size_issue
from _common.io import read_json, write_json
from _common.paths import now_iso
from _common.works_classifier import load_works_classification_config
from vertical.license import validate_image_rights

from site_supply.core import *  # noqa: F403
from site_supply.packets import *  # noqa: F403
from site_supply.reports import build_site_rollup_report, write_site_rollup_report


AUTHORIZED_ASSET_INGEST_SCHEMA = "quwoquan.site_supply.authorized_asset_ingest_report/1"
ATTRIBUTED_ASSET_INGEST_SCHEMA = "quwoquan.site_supply.attributed_asset_ingest_report/1"

REQUIRED_AUTHORIZED_ASSET_FIELDS = (
    "assetId",
    "sourceUrl",
    "title",
    "creator",
    "credit",
    "license",
    "termsUrl",
    "usageScope",
    "authorizationProof",
    "modelReleaseStatus",
    "sourceCollectionId",
    "collectionPageUrl",
    "tags",
)

REQUIRED_ATTRIBUTED_ASSET_FIELDS = (
    "assetId",
    "pinUrl",
    "discoveryUrl",
    "originalAssetUrl",
    "sourceAuthor",
    "repostAttribution",
    "watermarkScan",
    "ocrScan",
    "modelReleaseStatus",
    "sourceCollectionId",
    "collectionPageUrl",
    "title",
    "tags",
    "collectedAt",
)

AUTHORIZED_ASSET_URL_FIELDS = ("downloadUrl", "localPath")

AUTHORIZED_TUCHONG_HOSTS = {
    "stock.tuchong.com",
    "open.tuchong.com",
}

TUCHONG_COMMUNITY_HOSTS = {
    "tuchong.com",
    "www.tuchong.com",
}

PHOTOGRAPHER_AUTHORIZED_POOL_SITE_ID = "photographer_authorized_pool"
PHOTOGRAPHER_AUTHORIZED_POOL_PLATFORM = "摄影师授权池"
PHOTOGRAPHER_AUTHORIZED_POOL_CANONICAL_HOST = "authorized.assets.quwoquan.local"
PINTEREST_SITE_IDS = {"pinterest", "pinterest_travel_reference"}
PINTEREST_PLATFORM = "Pinterest"
PINTEREST_TERMS_URL = "https://policy.pinterest.com/terms-of-service"
MAX_AUTHORIZED_ASSET_BYTES = 30 * 1024 * 1024

PUBLISHABLE_USAGE_SCOPES = {"app_publish", "commercial"}

TRAVEL_OR_PHOTOGRAPHY_TAG_PREFIXES = (
    "Topic/旅行",
    "Topic/摄影",
    "Topic/自然风光",
    "Topic/历史文化",
    "Format/表现手法/摄影",
    "Format/视觉风格",
    "Entity/地点",
)

HUMAN_OR_COMMERCIAL_TERMS = (
    "人像",
    "人物",
    "婚礼",
    "亲子",
    "商业",
    "广告",
    "模特",
)


def _min_assets_per_image_work() -> int:
    try:
        config = load_works_classification_config()
        rules = config.get("carrierRules") if isinstance(config.get("carrierRules"), Mapping) else {}
        return max(1, int(rules.get("minImagesForImageWork") or 4))
    except Exception:
        return 4


def _as_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        raw = data
    elif isinstance(data, Mapping):
        raw = data.get("assets") or data.get("items") or []
    else:
        raw = []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _host(value: str) -> str:
    return (urllib.parse.urlparse(str(value or "")).hostname or "").lower()


def _host_allowed(value: str) -> bool:
    host = _host(value)
    return host in AUTHORIZED_TUCHONG_HOSTS or any(host.endswith(f".{item}") for item in AUTHORIZED_TUCHONG_HOSTS)


def _pinterest_host_allowed(value: str) -> bool:
    host = _host(value)
    return host == "pinterest.com" or host.endswith(".pinterest.com")


def _is_tuchong_community_url(value: str) -> bool:
    host = _host(value)
    if not host:
        return False
    if _host_allowed(value):
        return False
    return host in TUCHONG_COMMUNITY_HOSTS or host.endswith(".tuchong.com")


def _site_platform(site_id: str) -> str:
    if site_id in PINTEREST_SITE_IDS:
        return PINTEREST_PLATFORM
    if site_id == PHOTOGRAPHER_AUTHORIZED_POOL_SITE_ID:
        return PHOTOGRAPHER_AUTHORIZED_POOL_PLATFORM
    return "图虫创意"


def _asset_tags(asset: Mapping[str, Any]) -> list[str]:
    tags = asset.get("tags")
    if isinstance(tags, list):
        return [str(item).strip() for item in tags if str(item).strip()]
    if isinstance(tags, str):
        return [item.strip() for item in tags.split(",") if item.strip()]
    return []


def _asset_context_text(asset: Mapping[str, Any]) -> str:
    tags = " ".join(_asset_tags(asset))
    return " ".join(
        str(asset.get(key) or "")
        for key in ("title", "caption", "description", "entityRef", "topicRef")
    ) + " " + tags


def _topic_or_entity_ref(asset: Mapping[str, Any]) -> str:
    entity_ref = str(asset.get("entityRef") or "").strip()
    topic_ref = str(asset.get("topicRef") or "").strip()
    return entity_ref or topic_ref


def _travel_or_photography_context(asset: Mapping[str, Any]) -> bool:
    tags = _asset_tags(asset)
    ref = _topic_or_entity_ref(asset)
    values = tags + ([ref] if ref else [])
    return any(
        any(value.startswith(prefix) for prefix in TRAVEL_OR_PHOTOGRAPHY_TAG_PREFIXES)
        for value in values
    )


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y"}


def _int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_asset_file_name(asset_id: str, suffix: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", asset_id).strip("._") or "asset"
    return f"{safe}{suffix or '.bin'}"


def _resolve_local_path(value: Any, *, manifest_dir: Path) -> Path:
    path = Path(str(value or "")).expanduser()
    return path if path.is_absolute() else manifest_dir / path


def _asset_bytes_from_local_path(asset: Mapping[str, Any], *, manifest_dir: Path) -> tuple[bytes | None, Path | None, list[str]]:
    asset_id = str(asset.get("assetId") or asset.get("sourceUrl") or "asset")
    local_value = str(asset.get("localPath") or "").strip()
    if not local_value:
        return None, None, []
    path = _resolve_local_path(local_value, manifest_dir=manifest_dir)
    if not path.is_file():
        return None, path, [f"{asset_id}: localPath does not exist: {path}"]
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, path, [f"{asset_id}: localPath unreadable: {path}: {exc}"]
    return data, path, []


def _download_asset_bytes(asset: Mapping[str, Any]) -> tuple[bytes | None, str, list[str]]:
    asset_id = str(asset.get("assetId") or asset.get("sourceUrl") or "asset")
    url = str(asset.get("downloadUrl") or "").strip()
    if not url:
        return None, "", [f"{asset_id}: downloadUrl is required when localPath is absent"]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None, "", [f"{asset_id}: downloadUrl must be an absolute http(s) URL"]
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - manifest URL is authorization-controlled input.
            content_type = str(response.headers.get("Content-Type") or "").split(";")[0].strip()
            data = response.read(MAX_AUTHORIZED_ASSET_BYTES + 1)
    except Exception as exc:  # noqa: BLE001
        return None, "", [f"{asset_id}: downloadUrl fetch failed: {exc}"]
    if len(data) > MAX_AUTHORIZED_ASSET_BYTES:
        return None, "", [f"{asset_id}: downloaded asset exceeds {MAX_AUTHORIZED_ASSET_BYTES} bytes"]
    if not data:
        return None, "", [f"{asset_id}: downloaded asset is empty"]
    return data, content_type, []


def _image_dimensions(data: bytes) -> tuple[int | None, int | None, str | None]:
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return None, None, f"Pillow unavailable for image dimension check: {exc}"
    import io

    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            return int(width), int(height), None
    except Exception as exc:  # noqa: BLE001
        return None, None, f"image bytes unreadable: {exc}"


def _guess_mime(path: Path | None, content_type: str, data: bytes) -> str:
    if content_type:
        return content_type
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if path is not None:
        return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return "application/octet-stream"


def _suffix_for_asset(path: Path | None, content_type: str, download_url: str) -> str:
    if path is not None and path.suffix:
        return path.suffix
    guessed = mimetypes.guess_extension(content_type) if content_type else ""
    if guessed:
        return guessed
    suffix = Path(urllib.parse.urlparse(download_url).path).suffix
    return suffix or ".bin"


def _asset_bytes_evidence(
    asset: Mapping[str, Any],
    *,
    manifest_dir: Path,
    download_assets: bool,
    asset_bytes_root: Path,
) -> tuple[dict[str, Any], list[str]]:
    asset_id = str(asset.get("assetId") or asset.get("sourceUrl") or "asset")
    row = dict(asset)
    data: bytes | None = None
    source_path: Path | None = None
    content_type = ""
    issues: list[str] = []
    local_data, local_path, local_issues = _asset_bytes_from_local_path(row, manifest_dir=manifest_dir)
    issues.extend(local_issues)
    if local_data is not None:
        data = local_data
        source_path = local_path
    elif download_assets:
        downloaded, content_type, download_issues = _download_asset_bytes(row)
        issues.extend(download_issues)
        data = downloaded
    if data is None:
        if download_assets and not issues:
            issues.append(f"{asset_id}: asset bytes missing")
        return row, issues
    sha256 = hashlib.sha256(data).hexdigest()
    width, height, dimension_issue = _image_dimensions(data)
    if dimension_issue:
        issues.append(f"{asset_id}: {dimension_issue}")
    mime_type = _guess_mime(source_path, content_type, data)
    if not mime_type.startswith("image/"):
        issues.append(f"{asset_id}: mimeType must be image/*; got {mime_type}")
    if width and height:
        row["width"] = width
        row["height"] = height
    row["sha256"] = sha256
    row["byteSize"] = len(data)
    row["mimeType"] = mime_type
    if download_assets and source_path is None:
        asset_bytes_root.mkdir(parents=True, exist_ok=True)
        suffix = _suffix_for_asset(source_path, content_type, str(row.get("downloadUrl") or ""))
        local_file = asset_bytes_root / _safe_asset_file_name(asset_id, suffix)
        local_file.write_bytes(data)
        row["localPath"] = str(local_file)
        row["downloadedAt"] = now_iso()
    elif source_path is not None:
        row["localPath"] = str(source_path)
    return row, issues


def _scan_status_passed(value: Any) -> bool:
    normalized = re.sub(r"\s+", "_", str(value or "").strip()).casefold()
    return normalized in {
        "clear",
        "pass",
        "passed",
        "none_detected",
        "no_explicit_watermark",
        "no_watermark_detected",
        "no_text_detected",
        "clean",
    }


def _normalize_attributed_manifest_row(asset: Mapping[str, Any], *, site_id: str) -> dict[str, Any]:
    source_author = str(asset.get("sourceAuthor") or asset.get("creator") or "").strip()
    pin_url = str(asset.get("pinUrl") or asset.get("sourceUrl") or "").strip()
    discovery_url = str(asset.get("discoveryUrl") or pin_url).strip()
    original_asset_url = str(
        asset.get("originalAssetUrl")
        or asset.get("downloadUrl")
        or asset.get("sourceUrl")
        or ""
    ).strip()
    row = dict(asset)
    if not str(row.get("assetId") or "").strip():
        row["assetId"] = _stable_ref("asset", pin_url, original_asset_url, source_author)
    if not str(row.get("downloadUrl") or "").strip():
        row["downloadUrl"] = str(asset.get("downloadUrl") or original_asset_url).strip()
    if not str(row.get("sourceUrl") or "").strip():
        row["sourceUrl"] = original_asset_url or pin_url
    if not str(row.get("title") or "").strip():
        row["title"] = str(asset.get("title") or asset.get("caption") or asset.get("sourceCollectionTitle") or "").strip()
    if not str(row.get("creator") or "").strip():
        row["creator"] = source_author
    if not str(row.get("credit") or "").strip():
        row["credit"] = str(asset.get("credit") or source_author).strip()
    if not str(row.get("license") or "").strip():
        row["license"] = "attribution_no_watermark"
    if not str(row.get("termsUrl") or "").strip():
        row["termsUrl"] = str(asset.get("termsUrl") or PINTEREST_TERMS_URL).strip()
    if not str(row.get("usageScope") or "").strip():
        row["usageScope"] = str(asset.get("usageScope") or "app_publish").strip()
    if not str(row.get("authorizationProof") or "").strip():
        row["authorizationProof"] = str(asset.get("authorizationProof") or original_asset_url or pin_url).strip()
    if not str(row.get("collectionPageUrl") or "").strip():
        row["collectionPageUrl"] = str(asset.get("collectionPageUrl") or pin_url).strip()
    if not str(row.get("authorizationBasis") or "").strip():
        row["authorizationBasis"] = "attribution_no_watermark"
    if not str(row.get("pinUrl") or "").strip():
        row["pinUrl"] = pin_url
    if not str(row.get("discoveryUrl") or "").strip():
        row["discoveryUrl"] = discovery_url
    if not str(row.get("originalAssetUrl") or "").strip():
        row["originalAssetUrl"] = original_asset_url or pin_url
    if not str(row.get("sourceAuthor") or "").strip():
        row["sourceAuthor"] = source_author
    if not str(row.get("repostAttribution") or "").strip():
        row["repostAttribution"] = str(asset.get("repostAttribution") or "").strip()
    if not str(row.get("watermarkScan") or "").strip():
        row["watermarkScan"] = str(asset.get("watermarkScan") or "").strip()
    if not str(row.get("ocrScan") or "").strip():
        row["ocrScan"] = str(asset.get("ocrScan") or "").strip()
    if not str(row.get("collectedAt") or "").strip():
        row["collectedAt"] = str(asset.get("collectedAt") or now_iso()).strip()
    if "watermarkDetected" not in row and _scan_status_passed(row.get("watermarkScan")):
        row["watermarkDetected"] = False
    if "platform" not in row:
        row["platform"] = _site_platform(site_id)
    return row


def _authorization_issues(asset: Mapping[str, Any], *, vertical: str, site_id: str) -> list[str]:
    asset_id = str(asset.get("assetId") or asset.get("sourceUrl") or "asset")
    issues: list[str] = []
    missing = [field for field in REQUIRED_AUTHORIZED_ASSET_FIELDS if asset.get(field) in (None, "", [], {})]
    if missing:
        issues.append(f"{asset_id}: missing authorized asset fields {missing}")
    if not any(str(asset.get(field) or "").strip() for field in AUTHORIZED_ASSET_URL_FIELDS):
        issues.append(f"{asset_id}: one of downloadUrl or localPath is required")
    if not _topic_or_entity_ref(asset):
        issues.append(f"{asset_id}: either entityRef or topicRef is required")
    if not _travel_or_photography_context(asset):
        issues.append(f"{asset_id}: asset must be tagged as China travel or photography context")
    if site_id == "tuchong_stock_authorized":
        if not _host_allowed(str(asset.get("sourceUrl") or "")):
            issues.append(f"{asset_id}: sourceUrl must be under stock.tuchong.com or open.tuchong.com")
        if str(asset.get("collectionPageUrl") or "").strip() and not _host_allowed(str(asset.get("collectionPageUrl") or "")):
            issues.append(f"{asset_id}: collectionPageUrl must be under stock.tuchong.com or open.tuchong.com")
    elif site_id == PHOTOGRAPHER_AUTHORIZED_POOL_SITE_ID:
        for field in ("sourceUrl", "collectionPageUrl"):
            value = str(asset.get(field) or "").strip()
            if value and _is_tuchong_community_url(value):
                issues.append(f"{asset_id}: {field} cannot be a Tuchong community publish asset URL")
    usage_scope = str(asset.get("usageScope") or "").strip()
    if usage_scope not in PUBLISHABLE_USAGE_SCOPES:
        issues.append(f"{asset_id}: usageScope must be app_publish or commercial")
    width = _int_or_none(asset.get("width"))
    height = _int_or_none(asset.get("height"))
    pixel_issue = pixel_size_issue(width, height, asset_id=asset_id)
    if pixel_issue:
        issues.append(pixel_issue)
    if _boolish(asset.get("watermarkDetected") or asset.get("hasWatermark")):
        issues.append(f"{asset_id}: imageSafety watermark/platform mark detected")
    entity_match = str(asset.get("entityMatch") or "").strip().casefold()
    if entity_match in {"weak", "off_entity", "off_entity_no_anchor", "no_anchor"}:
        issues.append(f"{asset_id}: entityMatch={entity_match} is not eligible for image work")
    context = _asset_context_text(asset)
    if any(term in context for term in HUMAN_OR_COMMERCIAL_TERMS):
        model_release = str(asset.get("modelReleaseStatus") or "").strip()
        if model_release not in {"obtained", "not_required"}:
            issues.append(f"{asset_id}: human/commercial scene requires modelReleaseStatus=obtained or not_required")
        property_release = str(asset.get("propertyReleaseStatus") or "").strip()
        if "商业" in context or "广告" in context:
            if property_release not in {"obtained", "not_required"}:
                issues.append(f"{asset_id}: commercial scene requires propertyReleaseStatus=obtained or not_required")
    rights_payload = {
        "platform": _site_platform(site_id),
        "license": asset.get("license") or "",
        "credit": asset.get("credit") or asset.get("creator") or "",
        "sourceUrl": asset.get("sourceUrl") or "",
        "termsUrl": asset.get("termsUrl") or "",
        "usageScope": usage_scope,
        "authorizationProof": asset.get("authorizationProof") or "",
        "modelReleaseStatus": asset.get("modelReleaseStatus") or "",
        "modelReleaseRequired": asset.get("modelReleaseRequired") or "",
    }
    issues.extend(f"{asset_id}: {issue}" for issue in validate_image_rights(rights_payload, vertical=vertical))
    return issues


def _attribution_issues(asset: Mapping[str, Any], *, vertical: str, site_id: str) -> list[str]:
    asset_id = str(asset.get("assetId") or asset.get("pinUrl") or "asset")
    issues: list[str] = []
    missing = [field for field in REQUIRED_ATTRIBUTED_ASSET_FIELDS if asset.get(field) in (None, "", [], {})]
    if missing:
        issues.append(f"{asset_id}: missing attributed asset fields {missing}")
    if not any(str(asset.get(field) or "").strip() for field in AUTHORIZED_ASSET_URL_FIELDS):
        issues.append(f"{asset_id}: one of downloadUrl or localPath is required")
    pin_url = str(asset.get("pinUrl") or "").strip()
    if not _pinterest_host_allowed(pin_url):
        issues.append(f"{asset_id}: pinUrl must be under pinterest.com")
    if not _scan_status_passed(asset.get("watermarkScan")):
        issues.append(f"{asset_id}: watermarkScan must state clear/pass/no_explicit_watermark")
    if not _scan_status_passed(asset.get("ocrScan")):
        issues.append(f"{asset_id}: ocrScan must state clear/pass/no_text_detected")
    if not _topic_or_entity_ref(asset):
        issues.append(f"{asset_id}: either entityRef or topicRef is required")
    if not _travel_or_photography_context(asset):
        issues.append(f"{asset_id}: asset must be tagged as China travel or photography context")
    usage_scope = str(asset.get("usageScope") or "").strip()
    if usage_scope not in PUBLISHABLE_USAGE_SCOPES:
        issues.append(f"{asset_id}: usageScope must be app_publish or commercial")
    width = _int_or_none(asset.get("width"))
    height = _int_or_none(asset.get("height"))
    pixel_issue = pixel_size_issue(width, height, asset_id=asset_id)
    if pixel_issue:
        issues.append(pixel_issue)
    if _boolish(asset.get("watermarkDetected") or asset.get("hasWatermark")):
        issues.append(f"{asset_id}: imageSafety watermark/platform mark detected")
    entity_match = str(asset.get("entityMatch") or "").strip().casefold()
    if entity_match in {"weak", "off_entity", "off_entity_no_anchor", "no_anchor"}:
        issues.append(f"{asset_id}: entityMatch={entity_match} is not eligible for image work")
    context = _asset_context_text(asset)
    if any(term in context for term in HUMAN_OR_COMMERCIAL_TERMS):
        model_release = str(asset.get("modelReleaseStatus") or "").strip()
        if model_release not in {"obtained", "not_required"}:
            issues.append(f"{asset_id}: human/commercial scene requires modelReleaseStatus=obtained or not_required")
    rights_payload = {
        "platform": _site_platform(site_id),
        "authorizationBasis": asset.get("authorizationBasis") or "attribution_no_watermark",
        "license": asset.get("license") or "attribution_no_watermark",
        "credit": asset.get("credit") or asset.get("sourceAuthor") or "",
        "sourceUrl": asset.get("sourceUrl") or asset.get("originalAssetUrl") or "",
        "termsUrl": asset.get("termsUrl") or PINTEREST_TERMS_URL,
        "usageScope": usage_scope,
        "authorizationProof": asset.get("authorizationProof") or asset.get("originalAssetUrl") or asset.get("pinUrl") or "",
        "modelReleaseStatus": asset.get("modelReleaseStatus") or "",
        "modelReleaseRequired": asset.get("modelReleaseRequired") or "",
        "pinUrl": asset.get("pinUrl") or "",
        "discoveryUrl": asset.get("discoveryUrl") or "",
        "originalAssetUrl": asset.get("originalAssetUrl") or "",
        "sourceAuthor": asset.get("sourceAuthor") or "",
        "repostAttribution": asset.get("repostAttribution") or "",
        "watermarkScan": asset.get("watermarkScan") or "",
        "ocrScan": asset.get("ocrScan") or "",
        "collectedAt": asset.get("collectedAt") or "",
    }
    issues.extend(f"{asset_id}: {issue}" for issue in validate_image_rights(rights_payload, vertical=vertical))
    return issues


def _normalize_asset(asset: Mapping[str, Any], *, site_id: str) -> dict[str, Any]:
    tags = _asset_tags(asset)
    source_url = str(asset.get("sourceUrl") or "").strip()
    download_url = str(asset.get("downloadUrl") or "").strip()
    local_path = str(asset.get("localPath") or "").strip()
    title = str(asset.get("title") or "").strip()
    creator = str(asset.get("creator") or "").strip()
    return {
        "assetId": str(asset.get("assetId") or _stable_ref("asset", source_url, download_url)),
        "url": download_url or source_url,
        "sourceUrl": source_url,
        "downloadUrl": download_url,
        "sourcePath": local_path,
        "license": str(asset.get("license") or "").strip(),
        "credit": str(asset.get("credit") or creator).strip(),
        "creator": creator,
        "termsUrl": str(asset.get("termsUrl") or "").strip(),
        "usageScope": str(asset.get("usageScope") or "").strip(),
        "authorizationProof": str(asset.get("authorizationProof") or "").strip(),
        "authorizationBasis": str(asset.get("authorizationBasis") or "").strip(),
        "modelReleaseStatus": str(asset.get("modelReleaseStatus") or "").strip(),
        "modelReleaseRequired": str(asset.get("modelReleaseRequired") or "").strip(),
        "propertyReleaseStatus": str(asset.get("propertyReleaseStatus") or "").strip(),
        "pinUrl": str(asset.get("pinUrl") or "").strip(),
        "discoveryUrl": str(asset.get("discoveryUrl") or "").strip(),
        "originalAssetUrl": str(asset.get("originalAssetUrl") or "").strip(),
        "sourceAuthor": str(asset.get("sourceAuthor") or "").strip(),
        "repostAttribution": str(asset.get("repostAttribution") or "").strip(),
        "watermarkScan": str(asset.get("watermarkScan") or "").strip(),
        "ocrScan": str(asset.get("ocrScan") or "").strip(),
        "collectedAt": str(asset.get("collectedAt") or "").strip(),
        "sourceCollectionId": str(asset.get("sourceCollectionId") or "").strip(),
        "collectionPageUrl": str(asset.get("collectionPageUrl") or "").strip(),
        "caption": str(asset.get("caption") or title).strip(),
        "relevance": str(asset.get("relevance") or title).strip(),
        "title": title,
        "width": _int_or_none(asset.get("width")) or 0,
        "height": _int_or_none(asset.get("height")) or 0,
        "platform": _site_platform(site_id),
        "byteSize": _int_or_none(asset.get("byteSize")) or 0,
        "sha256": str(asset.get("sha256") or "").strip(),
        "mimeType": str(asset.get("mimeType") or "").strip(),
        "localPath": local_path,
        "tags": tags,
        "publishable": True,
    }


def _entity_mentions(asset: Mapping[str, Any]) -> list[str]:
    entity_ref = str(asset.get("entityRef") or "").strip()
    if not entity_ref:
        return []
    return [entity_ref[1:] if entity_ref.startswith("/") else entity_ref]


def _tag_mentions(asset: Mapping[str, Any]) -> list[str]:
    out = _asset_tags(asset)
    topic_ref = str(asset.get("topicRef") or "").strip()
    if topic_ref:
        out.append(topic_ref[1:] if topic_ref.startswith("/") else topic_ref)
    # Preserve order while deduping.
    return list(dict.fromkeys(item for item in out if item))


def _merge_mentions(rows: list[Mapping[str, Any]], reader: Any) -> list[str]:
    merged: list[str] = []
    for row in rows:
        merged.extend(reader(row))
    return list(dict.fromkeys(item for item in merged if item))


def _stable_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return dt.date.today().isoformat()
    return text[:10]


def _candidate_collection_url(site_id: str, collection_id: str, first: Mapping[str, Any], assets: list[Mapping[str, Any]]) -> str:
    if site_id == PHOTOGRAPHER_AUTHORIZED_POOL_SITE_ID:
        encoded = urllib.parse.quote(collection_id or str(first.get("sourceCollectionId") or "collection"), safe="")
        return f"https://{PHOTOGRAPHER_AUTHORIZED_POOL_CANONICAL_HOST}/collections/{encoded}"
    if site_id in PINTEREST_SITE_IDS:
        return str(
            first.get("pinUrl")
            or first.get("sourceUrl")
            or assets[0].get("pinUrl")
            or assets[0].get("sourceUrl")
            or first.get("collectionPageUrl")
            or ""
        )
    return str(first.get("collectionPageUrl") or first.get("sourceUrl") or assets[0].get("sourceUrl") or "")


def _build_manifest_asset_ingest_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    manifest_path: Path,
    target_count: int,
    min_raw_count: int = 0,
    min_qualified_count: int = 0,
    daily_target: int = 10_000,
    queue_backend: str = "reliabletask",
    end_date: str | None = None,
    objects_per_hour: float | None = None,
    token_ledger_count: int | None = None,
    download_assets: bool = False,
    admission_mode: str,
    schema_version: str,
    stage_name: str,
    report_filename: str,
    asset_bytes_dirname: str,
    manifest_label: str,
    pre_normalize: Any,
    issue_checker: Any,
    min_assets_per_work: int | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    frontier = build_site_frontier_packet(
        vertical=vertical,
        site_id=site_id,
        batch_id=batch_id,
        daily_target=daily_target,
        queue_backend=queue_backend,
        end_date=end_date,
        admission_mode=admission_mode,
    )
    write_site_frontier_packet(frontier)
    blockers: list[str] = []
    warnings: list[str] = []
    if not frontier["gate"]["passed"]:
        blockers.extend(str(item) for item in frontier["gate"].get("blockers") or [])
    if not manifest_path.is_file():
        blockers.append(f"{manifest_label} manifest missing: {manifest_path}")
        rows = []
    else:
        try:
            rows = _as_rows(read_json(manifest_path))
        except Exception as exc:  # noqa: BLE001
            blockers.append(f"{manifest_label} manifest unreadable: {manifest_path}: {exc}")
            rows = []
    raw_count = len(rows)
    min_raw_count = int(min_raw_count or math.ceil(max(target_count, 1) * 1.5))
    min_qualified_count = int(min_qualified_count or math.ceil(max(target_count, 1) * 1.2))
    rejected: list[dict[str, Any]] = []
    qualified_assets: list[dict[str, Any]] = []
    seen_asset_keys: set[str] = set()
    asset_bytes_root = site_supply_root(vertical, site_id, batch_id) / "_shared" / asset_bytes_dirname
    for index, row in enumerate(rows, start=1):
        prepared_row = pre_normalize(row, site_id=site_id)
        asset_id = str(prepared_row.get("assetId") or f"asset-{index}")
        normalized_row, byte_issues = _asset_bytes_evidence(
            prepared_row,
            manifest_dir=manifest_path.parent,
            download_assets=download_assets,
            asset_bytes_root=asset_bytes_root,
        )
        issues = byte_issues + issue_checker(normalized_row, vertical=vertical, site_id=site_id)
        for key_name in ("assetId", "sourceUrl", "downloadUrl", "localPath", "sha256"):
            value = str(prepared_row.get(key_name) or "").strip()
            if key_name in {"localPath", "sha256"}:
                value = str(normalized_row.get(key_name) or "").strip()
            if not value:
                continue
            key = f"{key_name}:{value}"
            if key in seen_asset_keys:
                issues.append(f"{asset_id}: duplicate authorized asset key {key_name}={value}")
            seen_asset_keys.add(key)
        if issues:
            rejected.append({"assetId": asset_id, "reasons": issues})
            continue
        qualified_assets.append(normalized_row)
    min_assets_per_work = int(min_assets_per_work or _min_assets_per_image_work())
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in qualified_assets:
        collection_id = str(row.get("sourceCollectionId") or "").strip()
        grouped.setdefault(collection_id, []).append(row)
    eligible_groups: list[tuple[str, list[dict[str, Any]]]] = []
    for collection_id, group_rows in sorted(grouped.items()):
        if len(group_rows) < min_assets_per_work:
            rejected.append(
                {
                    "sourceCollectionId": collection_id,
                    "reasons": [
                        f"{collection_id}: image work requires at least {min_assets_per_work} authorized assets; got {len(group_rows)}"
                    ],
                }
            )
            continue
        eligible_groups.append((collection_id, group_rows))
    picked_groups = eligible_groups[: max(0, int(target_count))]
    for collection_id, group_rows in picked_groups:
        first = group_rows[0]
        assets = [_normalize_asset(row, site_id=site_id) for row in group_rows]
        source_url = _candidate_collection_url(site_id, collection_id, first, assets)
        candidate = build_site_candidate_packet(
            vertical=vertical,
            site_id=site_id,
            batch_id=batch_id,
            url=source_url,
            lane="image",
            title=str(first.get("sourceCollectionTitle") or first.get("title") or collection_id),
            text=str(first.get("caption") or first.get("description") or ""),
            published_at=_stable_date(first.get("publishedAt") or end_date),
            author=str(first.get("creator") or ""),
            assets=assets,
            entity_mentions=_merge_mentions(group_rows, _entity_mentions),
            tag_mentions=_merge_mentions(group_rows, _tag_mentions),
        )
        write_site_candidate_packet(candidate)
        if not candidate["gate"]["passed"]:
            rejected.append({"sourceCollectionId": collection_id, "reasons": list(candidate["gate"].get("blockers") or [])})
            continue
        score = build_site_score_packet(candidate)
        write_site_score_packet(score)
        if not score["gate"]["passed"]:
            rejected.append({"sourceCollectionId": collection_id, "reasons": list(score["gate"].get("blockers") or [])})
            continue
        mapped = build_site_map_packet(candidate, score)
        write_site_map_packet(mapped)
        if not mapped["gate"]["passed"]:
            rejected.append({"sourceCollectionId": collection_id, "reasons": list(mapped["gate"].get("blockers") or [])})
    elapsed_hours = max((time.monotonic() - started) / 3600.0, 0.000001)
    handoff_count = len(_read_handoff_refs(vertical, site_id, batch_id))
    measured_oph = float(objects_per_hour) if objects_per_hour is not None else handoff_count / elapsed_hours
    first_pass_rate = round(len(qualified_assets) / raw_count, 4) if raw_count else 0.0
    rollup = build_site_rollup_report(
        vertical=vertical,
        site_id=site_id,
        batch_id=batch_id,
        objects_per_hour=measured_oph,
        first_pass_rate=first_pass_rate,
        token_ledger_count=token_ledger_count if token_ledger_count is not None else max(handoff_count, 1),
    )
    write_site_rollup_report(rollup)
    if raw_count < min_raw_count:
        blockers.append(f"raw discovered {manifest_label} {raw_count} < required {min_raw_count}")
    if len(qualified_assets) < min_qualified_count:
        blockers.append(f"qualified {manifest_label} {len(qualified_assets)} < required {min_qualified_count}")
    if len(eligible_groups) < int(target_count):
        blockers.append(f"qualified image work collections {len(eligible_groups)} < targetCount {int(target_count)}")
    if handoff_count < int(target_count):
        blockers.append(f"picked image handoff {handoff_count} < targetCount {int(target_count)}")
    if not rollup.get("passed"):
        blockers.extend(str(item) for item in rollup.get("blockers") or [])
    report = {
        "schemaVersion": schema_version,
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "sourceManifest": str(manifest_path),
        "manifestLabel": manifest_label,
        "targetCount": int(target_count),
        "thresholds": {
            "minRawCount": min_raw_count,
            "minQualifiedCount": min_qualified_count,
            "minAssetsPerImageWork": min_assets_per_work,
            "downloadAssets": bool(download_assets),
        },
        "funnel": {
            "rawDiscovered": raw_count,
            "qualified": len(qualified_assets),
            "qualifiedImageWorks": len(eligible_groups),
            "picked": handoff_count,
            "authored": 0,
            "reviewed": 0,
            "released": 0,
            "imported": 0,
            "rejected": len(rejected),
        },
        "rejectedAssets": rejected[:200],
        "rollupPath": str(site_supply_root(vertical, site_id, batch_id) / "_shared" / "site_rollup_report.json"),
        "assetBytesRoot": str(asset_bytes_root),
        "gate": _gate_report(stage_name, blockers, warnings),
        "createdAt": now_iso(),
    }
    path = site_supply_root(vertical, site_id, batch_id) / "_shared" / report_filename
    write_json(path, report)
    _write_stage_triplet(site_supply_root(vertical, site_id, batch_id), stage_name, [str(path)], report["gate"])
    return report


def build_authorized_asset_ingest_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    manifest_path: Path,
    target_count: int,
    min_raw_count: int = 0,
    min_qualified_count: int = 0,
    daily_target: int = 10_000,
    queue_backend: str = "reliabletask",
    end_date: str | None = None,
    objects_per_hour: float | None = None,
    token_ledger_count: int | None = None,
    download_assets: bool = False,
) -> dict[str, Any]:
    return _build_manifest_asset_ingest_report(
        vertical=vertical,
        site_id=site_id,
        batch_id=batch_id,
        manifest_path=manifest_path,
        target_count=target_count,
        min_raw_count=min_raw_count,
        min_qualified_count=min_qualified_count,
        daily_target=daily_target,
        queue_backend=queue_backend,
        end_date=end_date,
        objects_per_hour=objects_per_hour,
        token_ledger_count=token_ledger_count,
        download_assets=download_assets,
        admission_mode=ADMISSION_LICENSED_ASSET_INGEST,
        schema_version=AUTHORIZED_ASSET_INGEST_SCHEMA,
        stage_name="authorized_asset_ingest",
        report_filename="authorized_asset_ingest_report.json",
        asset_bytes_dirname="authorized_asset_bytes",
        manifest_label="authorized asset",
        pre_normalize=lambda row, site_id: dict(row),
        issue_checker=_authorization_issues,
        min_assets_per_work=None,
    )


def build_attributed_asset_ingest_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    manifest_path: Path,
    target_count: int,
    min_raw_count: int = 0,
    min_qualified_count: int = 0,
    daily_target: int = 10_000,
    queue_backend: str = "reliabletask",
    end_date: str | None = None,
    objects_per_hour: float | None = None,
    token_ledger_count: int | None = None,
    download_assets: bool = True,
) -> dict[str, Any]:
    return _build_manifest_asset_ingest_report(
        vertical=vertical,
        site_id=site_id,
        batch_id=batch_id,
        manifest_path=manifest_path,
        target_count=target_count,
        min_raw_count=min_raw_count,
        min_qualified_count=min_qualified_count,
        daily_target=daily_target,
        queue_backend=queue_backend,
        end_date=end_date,
        objects_per_hour=objects_per_hour,
        token_ledger_count=token_ledger_count,
        download_assets=download_assets,
        admission_mode=ADMISSION_ATTRIBUTION_PUBLISH_INGEST,
        schema_version=ATTRIBUTED_ASSET_INGEST_SCHEMA,
        stage_name="attributed_asset_ingest",
        report_filename="attributed_asset_ingest_report.json",
        asset_bytes_dirname="attributed_asset_bytes",
        manifest_label="attributed asset",
        pre_normalize=_normalize_attributed_manifest_row,
        issue_checker=_attribution_issues,
        min_assets_per_work=1,
    )


def _read_handoff_refs(vertical: str, site_id: str, batch_id: str) -> list[str]:
    root = site_supply_root(vertical, site_id, batch_id)
    refs: list[str] = []
    for path in sorted((root / "map").glob("*/site_map_packet.json")):
        try:
            mapped = read_json(path)
        except Exception:
            continue
        if (mapped.get("contentPlanHandoff") or {}).get("eligible"):
            refs.append(str(mapped.get("candidateRef") or path.parent.name))
    return refs


def handle_authorized_assets(args: argparse.Namespace) -> None:
    report = build_authorized_asset_ingest_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        manifest_path=Path(args.manifest),
        target_count=args.target_count,
        min_raw_count=args.min_raw_count,
        min_qualified_count=args.min_qualified_count,
        daily_target=args.daily_target,
        queue_backend=args.queue_backend,
        end_date=args.end_date,
        objects_per_hour=args.objects_per_hour,
        token_ledger_count=args.token_ledger_count,
        download_assets=args.download_assets,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit(1)


def handle_attributed_assets(args: argparse.Namespace) -> None:
    report = build_attributed_asset_ingest_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        manifest_path=Path(args.manifest),
        target_count=args.target_count,
        min_raw_count=args.min_raw_count,
        min_qualified_count=args.min_qualified_count,
        daily_target=args.daily_target,
        queue_backend=args.queue_backend,
        end_date=args.end_date,
        objects_per_hour=args.objects_per_hour,
        token_ledger_count=args.token_ledger_count,
        download_assets=True if not hasattr(args, "download_assets") else bool(args.download_assets),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["gate"]["passed"]:
        raise SystemExit(1)


__all__ = [name for name in globals() if not name.startswith("__")]
