"""Harvest public Pinterest pins into attributed-asset manifests."""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping

from _common.image_safety import (
    ImageVerdict,
    STATUS_NEEDS_REVIEW,
    STATUS_SAFE,
    STATUS_TEXT_HEAVY,
    STATUS_UNSAFE,
    assess_image_cached,
)
from _common.image_rules import pixel_size_issue
from _common.io import read_json, write_json
from _common.paths import now_iso
from download.fetch import _curl_get_text, fetch_image_payload

from site_supply.core import _stable_ref

PINTEREST_PUBLIC_PIN_MANIFEST_SCHEMA = "quwoquan.site_supply.pinterest_public_pin_manifest/1"
PINTEREST_PUBLIC_PIN_HARVEST_REPORT_SCHEMA = "quwoquan.site_supply.pinterest_public_pin_harvest_report/1"
PINTEREST_TERMS_URL = "https://policy.pinterest.com/terms-of-service"
MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024
_JSON_WINDOW_CHARS = 4096


class _MetaCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self._in_title = False
        self._title_parts: list[str] = []

    @property
    def title(self) -> str:
        return "".join(self._title_parts).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "meta":
            attr_map = {str(key).lower(): str(value or "") for key, value in attrs}
            key = attr_map.get("property") or attr_map.get("name")
            content = attr_map.get("content") or ""
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and data:
            self._title_parts.append(data)


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _dedupe_keep_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _safe_file_stem(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "")).strip("._")
    return safe or "asset"


def _pin_path_token(pin_url: str) -> str:
    parsed = urllib.parse.urlparse(str(pin_url or "").strip())
    path = parsed.path or ""
    if "/pin/" not in path:
        return ""
    token = path.split("/pin/", 1)[1].strip("/")
    return token


def _normalize_pin_url(pin_url: str) -> str:
    raw = str(pin_url or "").strip()
    if not raw:
        raise ValueError("pinUrl is required")
    parsed = urllib.parse.urlparse(raw)
    if not parsed.scheme:
        parsed = urllib.parse.urlparse(f"https://{raw.lstrip('/')}")
    token = _pin_path_token(parsed.geturl())
    if not token:
        raise ValueError(f"not a Pinterest pin URL: {raw}")
    host = (parsed.hostname or "www.pinterest.com").lower()
    if host == "pinterest.com":
        host = "www.pinterest.com"
    return f"https://{host}/pin/{token}/"


def _pin_numeric_id(pin_url: str) -> str:
    token = _pin_path_token(pin_url)
    tail = token.rsplit("--", 1)[-1]
    return tail if tail.isdigit() else ""


def _parse_meta(html_text: str) -> tuple[dict[str, str], str]:
    parser = _MetaCollector()
    parser.feed(str(html_text or ""))
    return parser.meta, parser.title


def _decode_json_string(value: str) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw.replace('\\"', '"').replace("\\/", "/")


def _json_block_field(html_text: str, block: str, field: str) -> str:
    marker = f'"{block}":'
    start = html_text.find(marker)
    if start < 0:
        return ""
    chunk = html_text[start:start + _JSON_WINDOW_CHARS]
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:[^"\\\\]|\\\\.)*)"', chunk)
    return _decode_json_string(match.group(1)) if match else ""


def _json_field(html_text: str, field: str) -> str:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:[^"\\\\]|\\\\.)*)"', html_text)
    return _decode_json_string(match.group(1)) if match else ""


def _pinimg_suffix(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    parts = [part for part in parsed.path.lstrip("/").split("/") if part]
    if len(parts) < 2:
        return ""
    return "/".join(parts[1:])


def _pinimg_variant_score(url: str) -> tuple[int, int, int]:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    parts = [part for part in parsed.path.lstrip("/").split("/") if part]
    if not parts:
        return (0, 0, 0)
    size_token = parts[0]
    if size_token == "originals":
        return (3, 10_000, 10_000)
    match = re.match(r"(?P<width>\d+)x(?P<height>\d+)?", size_token)
    if match:
        width = int(match.group("width") or 0)
        height = int(match.group("height") or 0)
        return (2, max(width, height), width * max(height, 1))
    match = re.match(r"(?P<width>\d+)x$", size_token)
    if match:
        width = int(match.group("width") or 0)
        return (1, width, width)
    return (0, 0, 0)


def _best_download_url(html_text: str, meta: Mapping[str, str]) -> str:
    og_image = str(meta.get("og:image") or "").strip()
    candidates: list[str] = []
    for value in (
        _json_block_field(html_text, "images_orig", "url"),
        _json_field(html_text, "imageLargeUrl"),
        _json_block_field(html_text, "images_1200x", "url"),
        _json_block_field(html_text, "images_1200", "url"),
        _json_block_field(html_text, "images_736x", "url"),
        _json_block_field(html_text, "images_736", "url"),
        og_image,
    ):
        text = str(value or "").strip()
        if text:
            candidates.append(text)
    suffix = _pinimg_suffix(og_image)
    if suffix:
        urls = re.findall(r'https://i\.pinimg\.com/[^"\'\s<)]+', html_text)
        for url in urls:
            if _pinimg_suffix(url) == suffix:
                candidates.append(url)
    deduped = _dedupe_keep_order([str(value).strip() for value in candidates if str(value).strip()])
    if not deduped:
        return ""
    return max(deduped, key=_pinimg_variant_score)


def _clean_title(value: str) -> str:
    title = str(value or "").strip()
    if not title:
        return ""
    if " | " in title:
        title = title.split(" | ", 1)[0].strip()
    return re.sub(r"\s+", " ", title).strip()


def _extract_author_from_text(*values: str) -> str:
    patterns = (
        r"(?i)\bdownload this photo by\s+([^|,]+?)\s+on\b",
        r"(?i)\bphoto by\s+([^|,]+?)\s+on\b",
        r"(?i)copyright\s*[©(c)]*\s*([^|,.]{2,80}?)\s+photography\b",
        r"(?i)\bby\s+([^|,]+?)\s+on\s+(unsplash|pexels|pixabay)\b",
    )
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return re.sub(r"\s+", " ", match.group(1)).strip(" -|,")
    return ""


def _normalize_author_value(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip()).strip(" -|,;:@")
    if text.startswith("@"):
        text = text[1:].strip()
    return text


def _extract_pinner_username(pinner_url: str) -> str:
    parsed = urllib.parse.urlparse(str(pinner_url or "").strip())
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return ""
    return parts[0].strip()


def _extract_source_page_author(source_url: str) -> tuple[str, str]:
    url = str(source_url or "").strip()
    if not url or urllib.parse.urlparse(url).scheme not in {"http", "https"}:
        return "", ""
    try:
        html_text = _curl_get_text(url, timeout=15)
    except Exception:
        return "", ""
    meta, page_title = _parse_meta(html_text)
    for key, evidence in (
        ("author", "source_page_meta_author"),
        ("article:author", "source_page_article_author"),
        ("twitter:creator", "source_page_twitter_creator"),
    ):
        value = _normalize_author_value(meta.get(key) or "")
        if value:
            return value, evidence
    ld_json_author = _json_block_field(html_text, "author", "name")
    ld_json_author = _normalize_author_value(ld_json_author)
    if ld_json_author:
        return ld_json_author, "source_page_jsonld_author"
    description = str(
        meta.get("description")
        or meta.get("og:description")
        or meta.get("twitter:description")
        or ""
    ).strip()
    parsed = _extract_author_from_text(page_title, description)
    parsed = _normalize_author_value(parsed)
    if parsed:
        return parsed, "source_page_text_author"
    return "", ""


def _image_dimensions(path: Path) -> tuple[int, int]:
    from PIL import Image  # type: ignore

    with Image.open(path) as image:
        width, height = image.size
    return int(width), int(height)


def _fetch_public_pin_html(pin_url: str) -> str:
    return _curl_get_text(pin_url)


def _download_pin_asset(download_url: str, *, asset_id: str, download_root: Path) -> dict[str, Any]:
    payload = fetch_image_payload(download_url, min_bytes=1024, max_bytes=MAX_DOWNLOAD_BYTES)
    if payload is None:
        raise RuntimeError(f"download failed or non-image payload: {download_url}")
    ext = str(payload.get("ext") or ".jpg")
    file_name = f"{_safe_file_stem(asset_id)}{ext}"
    asset_path = download_root / "assets" / file_name
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    body = payload.get("bytes") or b""
    asset_path.write_bytes(body)
    width, height = _image_dimensions(asset_path)
    return {
        "localPath": str(asset_path),
        "sha256": str(payload.get("sha256") or ""),
        "byteSize": len(body),
        "mimeType": str(payload.get("contentType") or ""),
        "width": width,
        "height": height,
    }


def _assess_local_image(local_path: Path, *, cache_dir: Path) -> ImageVerdict:
    return assess_image_cached(local_path, cache_dir=cache_dir, require_ocr=True)


def _watermark_scan_status(verdict: ImageVerdict) -> str:
    if verdict.has_watermark:
        return "watermark_detected"
    if verdict.status == STATUS_NEEDS_REVIEW and any("ocr_unavailable" in reason for reason in verdict.reasons):
        return "needs_review"
    return "no_explicit_watermark"


def _ocr_scan_status(verdict: ImageVerdict) -> str:
    if verdict.status == STATUS_NEEDS_REVIEW and any("ocr_unavailable" in reason for reason in verdict.reasons):
        return "needs_review"
    if verdict.status == STATUS_TEXT_HEAVY:
        return "text_heavy_detected"
    if verdict.has_watermark:
        return "platform_text_detected"
    if str(verdict.ocr_text or "").strip():
        return "pass"
    return "no_text_detected"


def _extract_pin_metadata(html_text: str, pin_url: str) -> dict[str, str]:
    meta, page_title = _parse_meta(html_text)
    return {
        "pinUrl": pin_url,
        "pinTitle": _clean_title(_json_field(html_text, "gridTitle") or meta.get("og:title") or page_title),
        "pinDescription": str(
            _json_field(html_text, "description")
            or meta.get("description")
            or meta.get("twitter:description")
            or ""
        ).strip(),
        "downloadUrl": _best_download_url(html_text, meta),
        "linkedSourceUrl": str(meta.get("pinterestapp:source") or meta.get("og:see_also") or "").strip(),
        "pinnerUrl": str(meta.get("pinterestapp:pinner") or "").strip(),
        "boardUrl": str(meta.get("pinterestapp:pinboard") or "").strip(),
        "boardName": str(_json_block_field(html_text, "board", "name") or "").strip(),
        "originPinnerFullName": str(_json_block_field(html_text, "originPinner", "fullName") or "").strip(),
        "originPinnerUsername": str(_json_block_field(html_text, "originPinner", "username") or "").strip(),
        "pinnerFullName": str(_json_block_field(html_text, "pinner", "fullName") or "").strip(),
        "pinnerUsername": str(_json_block_field(html_text, "pinner", "username") or _extract_pinner_username(meta.get("pinterestapp:pinner") or "")).strip(),
        "createdAt": str(_json_field(html_text, "createdAt") or meta.get("og:updated_time") or "").strip(),
    }


def _resolve_source_author(seed: Mapping[str, Any], metadata: Mapping[str, str]) -> tuple[str, str]:
    manual = str(seed.get("sourceAuthor") or "").strip()
    if manual:
        return manual, "manual_override"
    parsed = _extract_author_from_text(
        str(metadata.get("pinTitle") or ""),
        str(metadata.get("pinDescription") or ""),
    )
    if parsed:
        return _normalize_author_value(parsed), "title_pattern"
    source_page_author, source_page_evidence = _extract_source_page_author(str(metadata.get("linkedSourceUrl") or ""))
    if source_page_author:
        return source_page_author, source_page_evidence
    for field, evidence in (
        ("originPinnerFullName", "origin_pinner_full_name"),
        ("originPinnerUsername", "origin_pinner_username"),
        ("pinnerFullName", "pinner_full_name"),
        ("pinnerUsername", "pinner_username"),
    ):
        value = _normalize_author_value(str(metadata.get(field) or ""))
        if value:
            return value, evidence
    return "", "missing"


def _seed_rows(input_path: Path) -> list[dict[str, Any]]:
    if input_path.suffix.lower() in {".txt", ".urls", ".list"}:
        rows = []
        for line in input_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text and not text.startswith("#"):
                rows.append({"pinUrl": text})
        return rows
    data = read_json(input_path)
    raw: Any
    if isinstance(data, list):
        raw = data
    elif isinstance(data, Mapping):
        raw = data.get("assets") or data.get("items") or data.get("pins") or data.get("urls") or []
    else:
        raw = []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            rows.append({"pinUrl": item})
        elif isinstance(item, Mapping):
            rows.append(dict(item))
    return rows


def _report_output_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_report.json")


def _harvest_single_pin(
    seed: Mapping[str, Any],
    *,
    download_root: Path,
    default_tags: list[str],
    default_entity_ref: str,
    default_topic_ref: str,
    usage_scope: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    try:
        pin_url = _normalize_pin_url(str(seed.get("pinUrl") or ""))
    except ValueError as exc:
        return None, [str(exc)]
    html_text = _fetch_public_pin_html(pin_url)
    metadata = _extract_pin_metadata(html_text, pin_url)
    download_url = str(seed.get("downloadUrl") or metadata.get("downloadUrl") or "").strip()
    if not download_url:
        issues.append("missing og:image download URL")
    linked_source_url = str(seed.get("sourceUrl") or seed.get("linkedSourceUrl") or metadata.get("linkedSourceUrl") or "").strip()
    source_author, author_evidence = _resolve_source_author(seed, metadata)
    if not source_author:
        issues.append("missing source author")
    if issues:
        return None, issues

    asset_id = str(
        seed.get("assetId")
        or _stable_ref("asset", pin_url, download_url, source_author or metadata.get("pinnerUsername") or "")
    ).strip()
    download_meta = _download_pin_asset(download_url, asset_id=asset_id, download_root=download_root)
    local_path = Path(str(download_meta["localPath"]))
    verdict = _assess_local_image(local_path, cache_dir=download_root / "_image_safety_cache")
    watermark_scan = _watermark_scan_status(verdict)
    ocr_scan = _ocr_scan_status(verdict)
    faces_detected = int(verdict.faces if verdict.faces >= 0 else 0)
    width = int(download_meta.get("width") or 0)
    height = int(download_meta.get("height") or 0)
    pixel_issue = pixel_size_issue(width, height, asset_id=asset_id)
    model_release_required = faces_detected > 0
    model_release_status = (
        "obtained"
        if str(seed.get("modelReleaseStatus") or "").strip() == "obtained"
        else ("editorial_only" if model_release_required else "not_required")
    )
    collected_at = str(seed.get("collectedAt") or now_iso()).strip()
    title = str(seed.get("title") or metadata.get("pinTitle") or "").strip()
    caption = str(seed.get("caption") or metadata.get("pinDescription") or title).strip()
    board_url = str(seed.get("collectionPageUrl") or metadata.get("boardUrl") or pin_url).strip()
    board_name = str(seed.get("sourceCollectionTitle") or metadata.get("boardName") or title).strip()
    pin_id = _pin_numeric_id(pin_url)
    source_collection_id = str(seed.get("sourceCollectionId") or (f"pin_{pin_id}" if pin_id else _stable_ref("collection", pin_url))).strip()
    published_at = str(seed.get("publishedAt") or collected_at[:10]).strip()
    entity_ref = str(seed.get("entityRef") or default_entity_ref or "").strip()
    topic_ref = str(seed.get("topicRef") or default_topic_ref or "").strip()
    tags = _dedupe_keep_order(default_tags + [str(item).strip() for item in (seed.get("tags") or []) if str(item).strip()])
    repost_attribution = str(seed.get("repostAttribution") or "").strip()
    if not repost_attribution:
        saver_name = (
            str(metadata.get("originPinnerFullName") or "").strip()
            or str(metadata.get("originPinnerUsername") or "").strip()
            or str(metadata.get("pinnerFullName") or "").strip()
            or str(metadata.get("pinnerUsername") or "").strip()
        )
        if saver_name and linked_source_url:
            repost_attribution = f"Pinterest pin saved by {saver_name}; linked source {linked_source_url}"
        elif linked_source_url:
            repost_attribution = f"Pinterest public pin linked source {linked_source_url}"
        else:
            repost_attribution = f"Pinterest public pin {pin_url}"

    row = {
        "assetId": asset_id,
        "pinUrl": pin_url,
        "discoveryUrl": str(seed.get("discoveryUrl") or pin_url).strip(),
        "sourceUrl": linked_source_url or pin_url,
        "linkedSourceUrl": linked_source_url or pin_url,
        "originalAssetUrl": str(seed.get("originalAssetUrl") or download_url).strip(),
        "downloadUrl": download_url,
        "localPath": str(local_path),
        "title": title,
        "caption": caption,
        "sourceAuthor": source_author,
        "credit": str(seed.get("credit") or source_author).strip(),
        "creator": str(seed.get("creator") or source_author).strip(),
        "authorEvidence": author_evidence,
        "repostAttribution": repost_attribution,
        "authorizationBasis": "attribution_no_watermark",
        "authorizationProof": str(seed.get("authorizationProof") or pin_url).strip(),
        "license": str(seed.get("license") or "attribution_no_watermark").strip(),
        "termsUrl": str(seed.get("termsUrl") or PINTEREST_TERMS_URL).strip(),
        "usageScope": str(seed.get("usageScope") or usage_scope or "commercial").strip(),
        "watermarkScan": str(seed.get("watermarkScan") or watermark_scan).strip(),
        "ocrScan": str(seed.get("ocrScan") or ocr_scan).strip(),
        "watermarkDetected": bool(verdict.has_watermark),
        "modelReleaseRequired": model_release_required,
        "modelReleaseStatus": model_release_status,
        "sourceCollectionId": source_collection_id,
        "sourceCollectionTitle": board_name,
        "collectionPageUrl": board_url,
        "pinnerUrl": str(metadata.get("pinnerUrl") or "").strip(),
        "pinnerUsername": str(metadata.get("pinnerUsername") or "").strip(),
        "pinnerDisplayName": str(metadata.get("pinnerFullName") or "").strip(),
        "boardUrl": str(metadata.get("boardUrl") or "").strip(),
        "boardName": str(metadata.get("boardName") or "").strip(),
        "pinDescription": str(metadata.get("pinDescription") or "").strip(),
        "collectedAt": collected_at,
        "publishedAt": published_at,
        "width": width,
        "height": height,
        "sha256": str(download_meta.get("sha256") or "").strip(),
        "byteSize": int(download_meta.get("byteSize") or 0),
        "mimeType": str(download_meta.get("mimeType") or "").strip(),
        "entityRef": entity_ref,
        "topicRef": topic_ref,
        "tags": tags,
        "entityMatch": str(seed.get("entityMatch") or ("strong" if entity_ref else "")).strip(),
        "pixelGateIssue": pixel_issue or "",
        "imageGateStatus": verdict.status,
        "imageGateReasons": list(verdict.reasons),
        "ocrTextPreview": str(verdict.ocr_text or "")[:200],
        "publishable": (
            verdict.status == STATUS_SAFE
            and not verdict.has_watermark
            and not model_release_required
            and not pixel_issue
            and str(seed.get("usageScope") or usage_scope or "commercial").strip() in {"app_publish", "commercial"}
        ),
    }
    return row, []


def build_pinterest_public_pin_manifest(
    *,
    input_path: Path,
    output_path: Path,
    download_root: Path | None = None,
    site_id: str = "pinterest",
    vertical: str = "photography",
    default_tags: list[str] | None = None,
    default_entity_ref: str = "",
    default_topic_ref: str = "",
    usage_scope: str = "commercial",
    publishable_only: bool = False,
    sleep_seconds: float = 0.0,
    limit: int = 0,
) -> dict[str, Any]:
    seeds = _seed_rows(input_path)
    if limit > 0:
        seeds = seeds[: int(limit)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    root = download_root or output_path.parent / f"{output_path.stem}_assets"
    root.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    default_tags = list(default_tags or [])
    for index, seed in enumerate(seeds):
        if index > 0 and sleep_seconds > 0:
            time.sleep(float(sleep_seconds))
        try:
            row, issues = _harvest_single_pin(
                seed,
                download_root=root,
                default_tags=default_tags,
                default_entity_ref=default_entity_ref,
                default_topic_ref=default_topic_ref,
                usage_scope=usage_scope,
            )
        except Exception as exc:  # noqa: BLE001
            row = None
            issues = [str(exc)]
        if row is None:
            rejected.append({"pinUrl": str(seed.get("pinUrl") or ""), "issues": issues})
            continue
        if publishable_only and not bool(row.get("publishable")):
            rejected.append(
                {
                    "pinUrl": str(row.get("pinUrl") or seed.get("pinUrl") or ""),
                    "issues": [
                        f"not publishable: imageGateStatus={row.get('imageGateStatus')}",
                        *([str(row.get("pixelGateIssue") or "").strip()] if str(row.get("pixelGateIssue") or "").strip() else []),
                        *[str(item) for item in (row.get("imageGateReasons") or [])],
                    ],
                }
            )
            continue
        assets.append(row)
    manifest = {
        "schemaVersion": PINTEREST_PUBLIC_PIN_MANIFEST_SCHEMA,
        "generatedAt": now_iso(),
        "vertical": vertical,
        "siteId": site_id,
        "platform": "Pinterest",
        "assets": assets,
    }
    report = {
        "schemaVersion": PINTEREST_PUBLIC_PIN_HARVEST_REPORT_SCHEMA,
        "generatedAt": now_iso(),
        "vertical": vertical,
        "siteId": site_id,
        "inputPath": str(input_path),
        "outputPath": str(output_path),
        "downloadRoot": str(root),
        "publishableOnly": bool(publishable_only),
        "funnel": {
            "requested": len(seeds),
            "harvested": len(assets),
            "publishable": sum(1 for asset in assets if bool(asset.get("publishable"))),
            "rejected": len(rejected),
        },
        "rejectedPins": rejected,
        "assetRefs": [
            {
                "assetId": str(asset.get("assetId") or ""),
                "pinUrl": str(asset.get("pinUrl") or ""),
                "sourceAuthor": str(asset.get("sourceAuthor") or ""),
                "authorEvidence": str(asset.get("authorEvidence") or ""),
                "localPath": str(asset.get("localPath") or ""),
                "publishable": bool(asset.get("publishable")),
            }
            for asset in assets
        ],
    }
    write_json(output_path, manifest)
    write_json(_report_output_path(output_path), report)
    return report


def handle_harvest_pinterest_pins(args: argparse.Namespace) -> None:
    report = build_pinterest_public_pin_manifest(
        input_path=Path(args.input),
        output_path=Path(args.output),
        download_root=Path(args.download_root) if getattr(args, "download_root", None) else None,
        site_id=args.site_id,
        vertical=args.vertical,
        default_tags=_split_csv(getattr(args, "default_tags", "")),
        default_entity_ref=str(getattr(args, "default_entity_ref", "") or ""),
        default_topic_ref=str(getattr(args, "default_topic_ref", "") or ""),
        usage_scope=str(getattr(args, "usage_scope", "commercial") or "commercial"),
        publishable_only=bool(getattr(args, "publishable_only", False)),
        sleep_seconds=float(getattr(args, "sleep_seconds", 0.0) or 0.0),
        limit=int(getattr(args, "limit", 0) or 0),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if int((report.get("funnel") or {}).get("harvested") or 0) <= 0:
        raise SystemExit(1)


__all__ = [name for name in globals() if not name.startswith("__")]
