from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import sys
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from common import (
    DISCOVERY_SCHEMA_VERSION,
    LEGACY_PACKAGE_MANIFEST_SCHEMA_VERSIONS,
    LEGACY_TOPIC_ASSET_MANIFEST_SCHEMA_VERSIONS,
    LEGACY_TOPIC_ENRICHMENT_SCHEMA_VERSIONS,
    PACKAGE_MANIFEST_SCHEMA_VERSION,
    RUNTIME_ROOT,
    SUPPORTED_CONTENT_TYPES,
    SUPPORTED_SEARCH_PROVIDERS,
    SUPPORTED_TARGETS,
    TOPIC_ASSET_MANIFEST_SCHEMA_VERSION,
    TOPIC_ENRICHMENT_SCHEMA_VERSION,
    TOPIC_TASK_SCHEMA_VERSION,
    crawl_spec_path_from_arg,
    download_topic_image_dir,
    download_topic_source_dir,
    ensure_runtime_layout,
    discovery_path,
    entity_name_for_ref,
    entity_payload_for_ref,
    load_user_pool,
    now_iso,
    out_topic_dir,
    publish_topic_dir,
    read_json,
    read_ndjson,
    read_yaml,
    ref_exists,
    run_topic_dir,
    tag_id_for_ref,
    write_json,
    write_ndjson,
    write_text,
    runtime_rel_ref,
    topic_tasks_path,
)
from native_fetch import (
    NativeFetchError,
    download_binary,
    fetch_html_page,
    safe_filename_from_url,
)

ARTICLE_QUALITY_WEIGHTS = {
    "contentCompleteness": 25,
    "actionability": 20,
    "sourceCredibility": 15,
    "freshness": 10,
    "richness": 10,
    "engagementSignal": 10,
    "cleanliness": 10,
}
ARTICLE_PUBLISHABILITY_WEIGHTS = {
    "readerValue": 20,
    "routeSpecificity": 18,
    "factDensity": 16,
    "practicality": 16,
    "narrativePotential": 20,
    "encyclopedicPenalty": 20,
}
IMAGE_QUALITY_WEIGHTS = {
    "rightsClarity": 30,
    "watermarkCleanliness": 20,
    "resolution": 15,
    "composition": 15,
    "relevance": 10,
    "storytelling": 10,
}
TOPIC_COMPOSE_SUMMARY_SCHEMA_VERSION = "quwoquan_data.compose_summary"
TOPIC_AUDIT_SUMMARY_SCHEMA_VERSION = "quwoquan_data.topic_audit_summary"
POST_REVIEW_SCHEMA_VERSION = "quwoquan_data.post_review"
MIN_ARTICLE_SOURCE_BODY_CHARS = 280
MIN_ARTICLE_SOURCE_PARAGRAPH_CHARS = 45
MIN_IMAGE_SOURCE_BODY_CHARS = 40
MIN_ARTICLE_PAGE_TEXT_CHARS = 240
MIN_IMAGE_PAGE_TEXT_CHARS = 40
PLACEHOLDER_TITLE_RE = re.compile(r"(公开样本|图片候选)\s*\d+$")
PLACEHOLDER_URL_RES = (
    re.compile(r"west_lake_(article|image|crawl_validation)_\d+", re.I),
    re.compile(r"west-lake-image", re.I),
    re.compile(r"mafengwo\.cn/i/[^/\d][^/]*$", re.I),
)
ARTICLE_TEMPLATE_PHRASES = (
    "为什么这个选题值得写",
    "正文叙事骨架",
    "先定主步行段",
    "热度高样本可直通",
    "正文至少保留一个“实体锚点”段",
    "正文至少保留一个\"实体锚点\"段",
    "端侧可以消费的原创 Markdown 成品",
    "端侧可以消费的原创 markdown 成品",
    "来源页把重点落在",
    "补充判断时，可以继续盯住",
    "如果想把现场走顺，可以先盯住",
    "真实来源围绕",
    "这篇把",
    "适合想在半天到一天里",
)
ARTICLE_TRAVEL_KEYWORDS = (
    "西湖十景",
    "苏堤春晓",
    "三潭印月",
    "柳浪闻莺",
    "曲院风荷",
    "平湖秋月",
    "花港观鱼",
    "湖滨公园",
    "雷峰塔",
    "断桥",
    "苏堤",
    "白堤",
    "湖滨",
    "游船",
    "喝茶",
    "杭帮菜",
    "美食",
    "饭店",
    "南线",
    "东岸",
    "湖面",
    "西湖",
)
ARTICLE_ROUTE_KEYWORDS = (
    "雷峰塔",
    "苏堤",
    "白堤",
    "断桥",
    "三潭印月",
    "湖滨公园",
    "湖滨",
    "南线",
    "西湖十景",
    "西湖",
)
ARTICLE_PRACTICAL_KEYWORDS = (
    "游船",
    "喝茶",
    "杭帮菜",
    "美食",
    "饭店",
)


def _normalize_text(value: Any) -> str:
    return " ".join(unescape(str(value or "")).replace("\ufeff", "").split())


def _schema_matches(value: Any, canonical: Any, legacy: set[Any] | None = None) -> bool:
    normalized = str(value).strip()
    if normalized == str(canonical).strip():
        return True
    legacy_values = {str(item).strip() for item in (legacy or set())}
    return normalized in legacy_values


def _strip_markdown_links(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)


def _clean_markdown_line(text: str) -> str:
    value = _normalize_text(_strip_markdown_links(text))
    value = re.sub(r"^[#>*\-\d\.\s]+", "", value)
    return value.strip()


def _looks_like_placeholder_url(url: str) -> bool:
    normalized = str(url or "").strip()
    if not normalized:
        return True
    return any(pattern.search(normalized) for pattern in PLACEHOLDER_URL_RES)


def _looks_like_placeholder_title(value: str) -> bool:
    return bool(PLACEHOLDER_TITLE_RE.search(_normalize_text(value)))


def _looks_like_default_topic_title(topic_id: str, task_type: str, value: str) -> bool:
    return _normalize_text(value).lower() == _normalize_text(
        _default_topic_title(topic_id, task_type)
    ).lower()


def _looks_like_placeholder_snippet(task_type: str, value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return True
    placeholder_phrases = [
        "被组织进同一条家庭半日路线",
        "优先看权利清晰、无平台水印",
        "适合做封面或组图",
    ]
    if task_type == "article":
        placeholder_phrases.append("文章任务")
    else:
        placeholder_phrases.append("图片任务")
    return any(phrase in normalized for phrase in placeholder_phrases)


def _extract_text_from_html(source: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", source, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return _normalize_text(text)


def _extract_source_body_text(source_markdown: str) -> str:
    text = source_markdown.replace("\ufeff", "").strip()
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            text = parts[1]
    body_lines: list[str] = []
    for raw_line in text.splitlines():
        cleaned = raw_line.rstrip()
        normalized = cleaned.strip()
        if not normalized:
            body_lines.append("")
            continue
        if re.match(r"^-\s*(source_id|candidate_id|url|source_url|fetched_at|round)\s*:", normalized):
            continue
        if re.match(r"^##\s*title\s*:", normalized, re.I):
            continue
        if re.match(r"^(title|summary|source_url|fetched_at|task_type)\s*:", normalized, re.I):
            continue
        body_lines.append(cleaned)
    return "\n".join(body_lines).strip()


def _extract_source_paragraphs(source_markdown: str) -> list[str]:
    body = _extract_source_body_text(source_markdown)
    if not body:
        return []
    paragraphs: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"\n\s*\n", body):
        cleaned = _clean_markdown_line(chunk)
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        paragraphs.append(cleaned)
    return paragraphs


def _placeholder_reasons(task_type: str, row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    title = str(row.get("title", "")).strip()
    snippet = str(row.get("snippet", "")).strip()
    source_url = str(row.get("sourceUrl", "")).strip()
    if _looks_like_placeholder_url(source_url):
        reasons.append("placeholder_source_url")
    if _looks_like_placeholder_title(title):
        reasons.append("placeholder_title")
    if _looks_like_placeholder_snippet(task_type, snippet):
        reasons.append("placeholder_snippet")
    if any(reasons) and any(_int_value(row.get(field)) > 0 for field in ("likes", "shares", "comments")):
        reasons.append("placeholder_engagement")
    return reasons


def _page_authenticity_reasons(
    task_type: str,
    row: dict[str, Any],
    page_html: str,
    source_markdown: str,
) -> tuple[list[str], dict[str, Any]]:
    reasons = _placeholder_reasons(task_type, row)
    page_text = _extract_text_from_html(page_html)
    source_body = _normalize_text(_extract_source_body_text(source_markdown))
    source_paragraphs = _extract_source_paragraphs(source_markdown)
    if 'data-topic-id="' in page_html or 'data-source-id="' in page_html:
        reasons.append("page_html_placeholder_shell")
    rel_tokens = row.get("relevanceTokens") or row.get("topicRelevanceTokens")
    if task_type == "article" and isinstance(rel_tokens, list) and rel_tokens:
        blob = _normalize_text(page_text + " " + source_body)
        hit = any(
            _normalize_text(str(tok).strip()) in blob
            for tok in rel_tokens
            if str(tok).strip() and len(_normalize_text(str(tok).strip())) >= 2
        )
        if not hit:
            reasons.append("topic_relevance_miss")
    min_page_chars = MIN_ARTICLE_PAGE_TEXT_CHARS if task_type == "article" else MIN_IMAGE_PAGE_TEXT_CHARS
    if len(page_text) < min_page_chars:
        reasons.append("page_html_too_short")
    min_body_chars = MIN_ARTICLE_SOURCE_BODY_CHARS if task_type == "article" else MIN_IMAGE_SOURCE_BODY_CHARS
    if len(source_body) < min_body_chars:
        reasons.append("source_markdown_too_short")
    if task_type == "article" and len(
        [item for item in source_paragraphs if len(item) >= MIN_ARTICLE_SOURCE_PARAGRAPH_CHARS]
    ) < 3:
        reasons.append("source_markdown_not_article_like")
    snippet = _normalize_text(row.get("snippet", ""))
    if snippet and source_body and snippet == source_body:
        reasons.append("source_markdown_equals_snippet")
    return _dedupe_strings(reasons), {
        "pageText": page_text,
        "sourceBodyText": source_body,
        "sourceParagraphs": source_paragraphs,
    }


def _default_topic_title(topic_id: str, task_type: str) -> str:
    compact = topic_id.replace("_", " ").strip()
    if task_type == "image":
        return f"{compact} 图片任务".strip()
    return f"{compact} 文章任务".strip()


def _default_enrichment_row(spec: dict[str, Any], topic_id: str, task_type: str) -> dict[str, Any]:
    return {
        "schemaVersion": TOPIC_ENRICHMENT_SCHEMA_VERSION,
        "specId": spec["spec_id"],
        "topicId": topic_id,
        "taskType": task_type,
        "publishReady": False,
        "title": _default_topic_title(topic_id, task_type),
        "summary": "",
        "entityRefs": list(spec.get("entity_refs", [])),
        "tagRefs": list(spec.get("tag_refs", [])),
        "selectedCandidateIds": [],
        "sourceUrls": [],
    }


def _ensure_topic_runtime_files(
    spec: dict[str, Any],
    topic_id: str,
    task_type: str,
) -> tuple[Path, Path, Path]:
    topic_dir = run_topic_dir(spec["spec_id"], topic_id)
    pages_root = topic_dir / "pages"
    source_pool_path = topic_dir / "source_pool.ndjson"
    enrichment_path = topic_dir / "enrichment.ndjson"
    pages_root.mkdir(parents=True, exist_ok=True)
    if not source_pool_path.exists():
        write_ndjson(source_pool_path, [])
    if not enrichment_path.exists():
        write_ndjson(enrichment_path, [_default_enrichment_row(spec, topic_id, task_type)])
    return topic_dir, source_pool_path, enrichment_path


def _asset_publish_eligibility(row: dict[str, Any]) -> str:
    if str(row.get("rightsStatus", "")).strip() != "clear":
        return "rejected"
    if str(row.get("watermarkStatus", "")).strip() != "clean":
        return "rejected"
    if str(row.get("sourceRole", "")).strip() == "discovery_only":
        return "rejected"
    return "approved"


def _asset_license_hint(source_url: str) -> dict[str, str]:
    normalized = _normalize_domain(urlparse(source_url).netloc)
    if (
        normalized.endswith("wikimedia.org")
        or normalized.endswith("wikivoyage.org")
        or normalized.endswith("wikipedia.org")
    ):
        return {
            "name": "wikimedia_source_page",
            "usage": "see_source_page_license",
        }
    return {"name": "unknown", "usage": "requires_review"}


def _top_downloaded_image_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    image_assets = [
        asset
        for asset in assets
        if str(asset.get("mimeType", "")).startswith("image/")
        and int(asset.get("width") or 0) > 0
        and int(asset.get("height") or 0) > 0
    ]
    if not image_assets:
        return None
    return max(
        image_assets,
        key=lambda asset: int(asset.get("width") or 0) * int(asset.get("height") or 0),
    )


def _keyword_relevance_score(*values: str) -> int:
    joined = " ".join(_normalize_text(value).lower() for value in values if value)
    if any(keyword in joined for keyword in ("西湖", "hangzhou", "west lake", "杭州")):
        return 10
    return 6 if joined else 0


def _image_quality_breakdown(
    row: dict[str, Any],
    assets: list[dict[str, Any]],
    *,
    page_text: str,
    source_body: str,
) -> dict[str, int]:
    top_asset = _top_downloaded_image_asset(assets)
    max_dimension = 0
    if top_asset is not None:
        max_dimension = max(
            int(top_asset.get("width") or 0),
            int(top_asset.get("height") or 0),
        )
    resolution = (
        15
        if max_dimension >= 2400
        else 13
        if max_dimension >= 1600
        else 11
        if max_dimension >= 1200
        else 8
        if max_dimension >= 800
        else 4
        if max_dimension > 0
        else 0
    )
    aspect_ratio = 0.0
    if top_asset is not None and int(top_asset.get("height") or 0) > 0:
        aspect_ratio = int(top_asset.get("width") or 0) / int(top_asset.get("height") or 1)
    composition = (
        15
        if 1.2 <= aspect_ratio <= 1.8
        else 12
        if 0.9 <= aspect_ratio <= 2.1
        else 8
        if aspect_ratio > 0
        else 0
    )
    storytelling = (
        10
        if len(_normalize_text(source_body)) >= 260 or len(_normalize_text(page_text)) >= 600
        else 8
        if len(_normalize_text(source_body)) >= 120 or len(_normalize_text(page_text)) >= 240
        else 5
        if top_asset is not None
        else 0
    )
    return {
        "rightsClarity": 30 if str(row.get("rightsStatus", "")).strip() == "clear" else 0,
        "watermarkCleanliness": 20
        if str(row.get("watermarkStatus", "")).strip() == "clean"
        else 0,
        "resolution": resolution,
        "composition": composition,
        "relevance": _keyword_relevance_score(
            str(row.get("title", "")),
            str(row.get("query", "")),
            page_text,
            source_body,
        ),
        "storytelling": storytelling,
    }


def _topic_keywords_for_paragraph_ranking(row: dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()
    for raw_value in (
        str(row.get("title", "")),
        str(row.get("topicTitle", "")),
        str(row.get("query", "")),
        str(row.get("snippet", "")),
    ):
        normalized = _normalize_text(raw_value)
        for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{4,}", normalized):
            cleaned = token.strip()
            lowered = cleaned.lower()
            if lowered in {"真实", "来源", "旅行", "指南", "topic", "image", "article"}:
                continue
            if lowered in seen:
                continue
            seen.add(lowered)
            keywords.append(cleaned)
    priority = ["西湖", "湖滨", "景区", "步行", "游览", "白堤", "苏堤", "断桥", "雷峰塔"]
    for keyword in reversed(priority):
        if keyword in keywords:
            keywords.remove(keyword)
            keywords.insert(0, keyword)
    if "西湖" in keywords:
        keywords = [keyword for keyword in keywords if keyword != "杭州"] or keywords
    return keywords[:12]


def _article_paragraph_relevance_score(paragraph: str, row: dict[str, Any]) -> int:
    normalized = _normalize_text(paragraph)
    if not normalized:
        return -999
    score = 0
    for keyword in _topic_keywords_for_paragraph_ranking(row):
        if keyword and keyword in normalized:
            score += 4 if keyword in {"西湖", "湖滨", "景区", "白堤", "苏堤", "断桥", "雷峰塔"} else 2
    transport_penalty_terms = (
        "机场",
        "火车站",
        "安检",
        "高速公路",
        "检票口",
        "候车",
        "出站",
        "班车",
        "客运",
        "地铁",
        "公交IC卡",
        "优惠月",
        "A卡",
        "B卡",
        "Y卡",
        "公交",
    )
    noise_penalty_terms = (
        "英语",
        "口语",
        "学习爱好者",
        "外国人",
    )
    admin_penalty_terms = (
        "省会",
        "政治",
        "经济",
        "文化",
        "金融",
        "交通中心",
        "常住人口",
        "总面积",
        "行政建制",
        "都城",
        "G20",
        "都市圈",
    )
    penalty_hits = sum(1 for term in transport_penalty_terms if term in normalized)
    if penalty_hits and "西湖" not in normalized and "景区" not in normalized:
        score -= penalty_hits * 4
    score -= sum(6 for term in noise_penalty_terms if term in normalized)
    score -= sum(8 for term in admin_penalty_terms if term in normalized)
    if "千岛湖" in normalized and "西湖十景" not in normalized and "湖滨" not in normalized:
        score -= 30
    if any(token in normalized for token in ("🕘", "💰", "地址", "更新日期")):
        score -= 18
    if re.match(r"^\d+\.\d+", normalized):
        score -= 18
    if (
        ("4A级" in normalized or "5A级" in normalized or "景区" in normalized)
        and normalized.count("、") >= 3
        and "西湖十景" not in normalized
        and "湖滨" not in normalized
        and "雷峰塔" not in normalized
    ):
        score -= 20
    if len(normalized) >= 45:
        score += 1
    return score


def _select_source_markdown_paragraphs(
    task_type: str,
    row: dict[str, Any],
    paragraphs: list[str],
) -> list[str]:
    cleaned = [_normalize_text(paragraph) for paragraph in paragraphs if _normalize_text(paragraph)]
    if task_type != "article":
        return cleaned[:12]
    scored = [
        (index, paragraph, _article_paragraph_relevance_score(paragraph, row))
        for index, paragraph in enumerate(cleaned)
    ]
    ranked = sorted(scored, key=lambda item: (-item[2], item[0]))
    selected = sorted(ranked[: min(8, len(ranked))], key=lambda item: item[0])
    if not selected:
        return cleaned[:12]
    if max(item[2] for item in selected) <= 0:
        return cleaned[:12]
    return [paragraph for _, paragraph, score in selected if score > -4][:8] or cleaned[:12]


def _hydrate_source_artifacts(
    spec: dict[str, Any],
    topic_id: str,
    task_type: str,
    row: dict[str, Any],
    *,
    force: bool = False,
) -> list[str]:
    errors: list[str] = []
    source_id = str(row.get("sourceId", "")).strip()
    source_url = str(row.get("sourceUrl", "")).strip()
    if not source_id:
        return ["source 缺少 sourceId，无法补抓取"]
    page_dir = run_topic_dir(spec["spec_id"], topic_id) / "pages" / source_id
    page_html_path = page_dir / "page.html"
    source_md_path = page_dir / "source.md"
    asset_manifest_path = page_dir / "asset_manifest.json"
    download_dir = download_topic_source_dir(spec["spec_id"], topic_id, source_id)
    image_download_dir = download_topic_image_dir(spec["spec_id"], topic_id, source_id)
    if force:
        shutil.rmtree(page_dir, ignore_errors=True)
        shutil.rmtree(download_dir, ignore_errors=True)
        shutil.rmtree(image_download_dir, ignore_errors=True)
    if (
        page_html_path.exists()
        and source_md_path.exists()
        and asset_manifest_path.exists()
    ):
        return []
    if _looks_like_placeholder_url(source_url):
        return []
    try:
        fetched = fetch_html_page(source_url)
    except NativeFetchError as error:
        return [str(error)]
    page_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)
    write_text(download_dir / "page.html", fetched.html)
    write_text(page_html_path, fetched.html)

    source_lines = [
        "---",
        f"title: {fetched.title}",
        f"source_url: {fetched.final_url}",
        f"fetched_at: {now_iso()}",
        f"task_type: {task_type}",
        "---",
        "",
    ]
    selected_paragraphs = _select_source_markdown_paragraphs(
        task_type,
        row,
        list(fetched.paragraphs) or [fetched.text],
    )
    for paragraph in selected_paragraphs or [fetched.text]:
        cleaned = _normalize_text(paragraph)
        if cleaned:
            source_lines.extend([cleaned, ""])
    write_text(source_md_path, "\n".join(source_lines).strip() + "\n")

    assets: list[dict[str, Any]] = []
    for index, image_url in enumerate(fetched.image_urls[:3], start=1):
        filename = safe_filename_from_url(image_url, fallback=f"{source_id}_{index:02d}.bin")
        target_path = download_topic_image_dir(spec["spec_id"], topic_id, source_id) / filename
        try:
            downloaded = download_binary(image_url, target_path)
        except NativeFetchError as error:
            errors.append(str(error))
            continue
        if not str(downloaded.mime_type).startswith("image/"):
            continue
        largest_dimension = max(downloaded.width or 0, downloaded.height or 0)
        if largest_dimension < 200:
            continue
        asset_id = f"{source_id}_asset_{index:02d}"
        assets.append(
            {
                "assetId": asset_id,
                "kind": "image",
                "scope": "runtime_download",
                "objectKey": runtime_rel_ref(downloaded.local_path),
                "localPath": runtime_rel_ref(downloaded.local_path),
                "downloadStatus": "downloaded",
                "sourceUrl": downloaded.source_url,
                "caption": str(row.get("title", "")).strip() if task_type == "image" else fetched.title,
                "sha256": downloaded.sha256,
                "mimeType": downloaded.mime_type,
                "width": downloaded.width,
                "height": downloaded.height,
                "license": _asset_license_hint(source_url),
                "rightsStatus": row.get("rightsStatus", ""),
                "watermarkStatus": row.get("watermarkStatus", ""),
                "publishEligibility": _asset_publish_eligibility(row),
                "platform": row.get("platform", row.get("domain", "")),
                "sourceId": source_id,
                "sourceCandidateId": row.get("candidateId", ""),
                "originPageUrl": fetched.final_url,
            }
        )
    write_json(
        asset_manifest_path,
        {
            "schemaVersion": TOPIC_ASSET_MANIFEST_SCHEMA_VERSION,
            "specId": spec["spec_id"],
            "topicId": topic_id,
            "sourceId": source_id,
            "taskType": task_type,
            "assets": assets,
        },
    )
    return errors


def _required_string(payload: dict[str, Any], field: str, errors: list[str]) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"crawl_spec 缺少 {field}")


def _required_string_list(payload: dict[str, Any], field: str, errors: list[str]) -> None:
    value = payload.get(field)
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        errors.append(f"crawl_spec 的 {field} 必须是非空字符串数组")


def _required_dict(payload: dict[str, Any], field: str, errors: list[str]) -> None:
    if not isinstance(payload.get(field), dict):
        errors.append(f"crawl_spec 缺少 {field}")


def _required_lane(spec: dict[str, Any], lane: str, errors: list[str]) -> None:
    lane_payload = spec.get(f"{lane}_lane")
    if not isinstance(lane_payload, dict):
        errors.append(f"crawl_spec 缺少 {lane}_lane")
        return
    allow_domains = lane_payload.get("allow_domains")
    if not isinstance(allow_domains, list) or not all(
        isinstance(item, str) and item.strip() for item in allow_domains
    ):
        errors.append(f"crawl_spec 的 {lane}_lane.allow_domains 必须是字符串数组")


def _discovery_policy(spec: dict[str, Any]) -> dict[str, int]:
    payload = dict(spec.get("discovery_policy", {}))
    return {
        "min_article_topics": int(payload.get("min_article_topics", 20)),
        "min_image_topics": int(payload.get("min_image_topics", 1)),
        "min_candidate_sources_per_task": int(
            payload.get("min_candidate_sources_per_task", 20)
        ),
        "min_article_publish_topics": int(payload.get("min_article_publish_topics", 6)),
        "min_image_publish_topics": int(payload.get("min_image_publish_topics", 1)),
    }


def _article_catalog_attraction_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    ref = str(spec.get("article_topic_catalog_ref") or "").strip()
    if not ref:
        return []
    path = (RUNTIME_ROOT / ref).resolve()
    if not path.is_file():
        return []
    if path.suffix.lower() == ".ndjson":
        rows = read_ndjson(path)
        return [r for r in rows if isinstance(r, dict) and str(r.get("topic_id") or r.get("topicId") or "").strip()]
    data = read_yaml(path)
    if not isinstance(data, dict):
        return []
    raw = data.get("attractions") or []
    return [r for r in raw if isinstance(r, dict)]


def _sample_topics(spec: dict[str, Any], lane: str) -> list[str]:
    payload = dict(spec.get("sample_topics", {}))
    value = payload.get(lane, [])
    if not isinstance(value, list):
        value = []
    merged: list[str] = [str(item).strip() for item in value if str(item).strip()]
    if lane == "article":
        for row in _article_catalog_attraction_rows(spec):
            tid = str(row.get("topic_id") or row.get("topicId") or "").strip()
            if tid:
                merged.append(tid)
    seen: set[str] = set()
    out: list[str] = []
    for item in merged:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _lane_creator_refs(spec: dict[str, Any], lane: str) -> list[str]:
    payload = dict(spec.get("creator_refs", {}))
    value = payload.get(lane, [])
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def validate_crawl_spec(spec: dict[str, Any], selected_targets: list[str]) -> list[str]:
    errors: list[str] = []
    for field in ("spec_id", "query", "search_provider"):
        _required_string(spec, field, errors)
    for field in ("entity_refs", "tag_refs", "target_envs"):
        _required_string_list(spec, field, errors)
    for field in ("publish_policy", "discovery_policy", "sample_topics", "creator_refs"):
        _required_dict(spec, field, errors)
    _required_lane(spec, "article", errors)
    _required_lane(spec, "image", errors)
    if errors:
        return errors

    if str(spec["search_provider"]).strip() not in SUPPORTED_SEARCH_PROVIDERS:
        errors.append(
            f"search_provider 只支持 {', '.join(sorted(SUPPORTED_SEARCH_PROVIDERS))}，收到 {spec['search_provider']}"
        )
    invalid_targets = sorted(
        (set(spec.get("target_envs", [])) | set(selected_targets)) - SUPPORTED_TARGETS
    )
    if invalid_targets:
        errors.append(f"target_envs 非法: {', '.join(invalid_targets)}")

    for lane in ("article", "image"):
        if not _sample_topics(spec, lane):
            errors.append(f"crawl_spec.sample_topics.{lane} 至少需要 1 个 topic_id")
        if not _lane_creator_refs(spec, lane):
            errors.append(f"crawl_spec.creator_refs.{lane} 至少需要 1 个作者")

    user_pool = load_user_pool()
    for lane in ("article", "image"):
        for user_id in _lane_creator_refs(spec, lane):
            if user_id not in user_pool:
                errors.append(f"creator_refs.{lane} 不存在于 user_pool: {user_id}")

    for ref in spec.get("entity_refs", []):
        if not ref_exists(ref):
            errors.append(f"entity_refs 引用不存在: {ref}")
    for ref in spec.get("tag_refs", []):
        if not ref_exists(ref):
            errors.append(f"tag_refs 引用不存在: {ref}")

    acref = str(spec.get("article_topic_catalog_ref") or "").strip()
    if acref:
        cpath = (RUNTIME_ROOT / acref).resolve()
        if not cpath.is_file():
            errors.append(f"article_topic_catalog_ref 文件不存在: {cpath}")

    policy = _discovery_policy(spec)
    for key, value in policy.items():
        if value < 1 and key != "min_image_publish_topics":
            errors.append(f"discovery_policy.{key} 必须 >= 1")
        if key == "min_image_publish_topics" and value < 0:
            errors.append("discovery_policy.min_image_publish_topics 必须 >= 0")

    publish_policy = dict(spec.get("publish_policy", {}))
    for field in ("visibility", "assistant_use_policy"):
        if not str(publish_policy.get(field, "")).strip():
            errors.append(f"publish_policy 缺少 {field}")
    return errors


def _normalize_domain(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip() or "0")
    except ValueError:
        return 0


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    single = str(value or "").strip()
    return [single] if single else []


def _source_id_from_row(row: dict[str, Any], index: int) -> str:
    source_id = str(row.get("sourceId") or row.get("source_id") or "").strip()
    if source_id:
        return source_id
    candidate_id = str(row.get("candidateId") or "").strip()
    if candidate_id:
        return candidate_id
    return f"source_{index:03d}"


def _coerce_breakdown(raw: Any, weights: dict[str, int]) -> dict[str, int]:
    source = dict(raw) if isinstance(raw, dict) else {}
    result: dict[str, int] = {}
    for key, maximum in weights.items():
        score = _int_value(source.get(key))
        result[key] = max(0, min(score, maximum))
    return result


def _sum_score(breakdown: dict[str, int]) -> int:
    return sum(int(value) for value in breakdown.values())


def _article_publishability_score(breakdown: dict[str, int]) -> int:
    positive_max = sum(
        maximum
        for key, maximum in ARTICLE_PUBLISHABILITY_WEIGHTS.items()
        if key != "encyclopedicPenalty"
    )
    positive = sum(
        int(value)
        for key, value in breakdown.items()
        if key != "encyclopedicPenalty"
    )
    penalty = int(breakdown.get("encyclopedicPenalty") or 0)
    raw = max(0, positive - penalty)
    if positive_max <= 0:
        return 0
    return round(raw * 100 / positive_max)


def _article_candidate_gate(row: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if str(row.get("rightsStatus", "")).strip() != "clear":
        reasons.append("rights_not_clear")
    if str(row.get("watermarkStatus", "")).strip() != "clean":
        reasons.append("watermark_not_clean")
    if _bool_value(row.get("adSignal")):
        reasons.append("advertorial")
    if str(row.get("duplicateStatus", "")).strip() == "high_repeat":
        reasons.append("high_duplicate")
    if str(row.get("sourceRole", "")).strip() == "discovery_only":
        reasons.append("discovery_only_source")
    return not reasons, reasons


def _image_candidate_gate(row: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if str(row.get("rightsStatus", "")).strip() != "clear":
        reasons.append("rights_not_clear")
    if str(row.get("watermarkStatus", "")).strip() != "clean":
        reasons.append("watermark_not_clean")
    if str(row.get("sourceRole", "")).strip() == "discovery_only":
        reasons.append("discovery_only_source")
    if "pinterest." in str(row.get("domain", "")).strip() and not _bool_value(
        row.get("manualRightsClearance")
    ):
        reasons.append("pinterest_discovery_only")
    return not reasons, reasons


def _article_publishability_breakdown(
    row: dict[str, Any],
    *,
    source_body: str,
    source_paragraphs: list[str],
) -> dict[str, int]:
    normalized = _normalize_text(source_body)
    route_tokens = _ordered_travel_tokens(
        normalized,
        keywords=ARTICLE_ROUTE_KEYWORDS,
        limit=8,
    )
    practical_tokens = _ordered_travel_tokens(
        normalized,
        keywords=ARTICLE_PRACTICAL_KEYWORDS,
        limit=8,
    )
    detail_tokens = _ordered_travel_tokens(
        normalized,
        keywords=ARTICLE_TRAVEL_KEYWORDS,
        limit=10,
    )
    relevant_paragraphs = [
        paragraph
        for paragraph in source_paragraphs
        if _article_paragraph_relevance_score(paragraph, row) > 0
    ]
    useful_sentences: list[str] = []
    categories: set[str] = set()
    for paragraph in source_paragraphs:
        for sentence in _split_sentences(paragraph):
            cleaned = _normalize_text(sentence)
            if len(cleaned) < 12 or not _article_useful_fact(cleaned):
                continue
            useful_sentences.append(cleaned)
            categories.add(_article_sentence_category(cleaned))
    practical_signal_terms = (
        "清晨",
        "早一点",
        "傍晚",
        "半天",
        "一天",
        "步行",
        "慢走",
        "散步",
        "坐船",
        "游船",
        "喝茶",
        "吃饭",
        "晚饭",
        "停下",
        "停留",
        "回头看",
        "湖边",
    )
    encyclopedic_terms = (
        "省会",
        "政治",
        "经济",
        "金融",
        "常住人口",
        "总面积",
        "行政建制",
        "都城",
        "交通中心",
        "都市圈",
        "世界遗产",
        "位于",
        "总长",
        "修建于",
    )
    reader_value = min(
        ARTICLE_PUBLISHABILITY_WEIGHTS["readerValue"],
        6
        + min(len(relevant_paragraphs), 4) * 2
        + min(len(practical_tokens), 2) * 3
        + min(len(detail_tokens), 3) * 2,
    )
    route_specificity = min(
        ARTICLE_PUBLISHABILITY_WEIGHTS["routeSpecificity"],
        min(len(route_tokens), 4) * 4 + (2 if len(detail_tokens) >= 4 else 0),
    )
    fact_density = min(
        ARTICLE_PUBLISHABILITY_WEIGHTS["factDensity"],
        min(len(useful_sentences), 5) * 2 + min(len(relevant_paragraphs), 3) * 2,
    )
    practicality_signals = len(
        [term for term in practical_signal_terms if term in normalized]
    )
    practicality = min(
        ARTICLE_PUBLISHABILITY_WEIGHTS["practicality"],
        min(len(practical_tokens), 3) * 4 + min(practicality_signals, 4),
    )
    narrative_potential = min(
        ARTICLE_PUBLISHABILITY_WEIGHTS["narrativePotential"],
        min(len(categories), 4) * 4
        + (4 if len(relevant_paragraphs) >= 4 else 0)
        + (4 if len(detail_tokens) >= 4 else 0),
    )
    encyclopedic_hits = sum(1 for term in encyclopedic_terms if term in normalized)
    list_like_penalty = len(
        [
            paragraph
            for paragraph in source_paragraphs
            if paragraph.count("、") >= 4 and "西湖十景" not in paragraph
        ]
    )
    encyclopedic_penalty = min(
        ARTICLE_PUBLISHABILITY_WEIGHTS["encyclopedicPenalty"],
        encyclopedic_hits * 3 + list_like_penalty * 2 + (4 if not practical_tokens else 0),
    )
    return {
        "readerValue": reader_value,
        "routeSpecificity": route_specificity,
        "factDensity": fact_density,
        "practicality": practicality,
        "narrativePotential": narrative_potential,
        "encyclopedicPenalty": encyclopedic_penalty,
    }


def _process_source_pool(
    task_type: str, rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    processed: list[dict[str, Any]] = []
    for index, raw in enumerate(rows, start=1):
        row = dict(raw)
        row["candidateId"] = str(row.get("candidateId") or f"candidate_{index:03d}")
        row["sourceId"] = _source_id_from_row(row, index)
        row["taskType"] = task_type
        row["sourceUrl"] = str(row.get("sourceUrl") or row.get("source_url") or "").strip()
        row["domain"] = _normalize_domain(
            str(row.get("domain") or urlparse(row["sourceUrl"]).netloc)
        )
        row["platform"] = str(row.get("platform") or row["domain"]).strip()
        row["title"] = str(row.get("title", "")).strip()
        row["query"] = str(row.get("query", "")).strip()
        row["rightsStatus"] = str(row.get("rightsStatus", "")).strip() or "unclear"
        row["watermarkStatus"] = str(row.get("watermarkStatus", "")).strip() or "unknown"
        row["duplicateStatus"] = str(row.get("duplicateStatus", "")).strip() or "unique"
        row["sourceRole"] = str(row.get("sourceRole", "")).strip() or "publish_candidate"
        row["likes"] = _int_value(row.get("likes"))
        row["shares"] = _int_value(row.get("shares"))
        row["comments"] = _int_value(row.get("comments"))
        row["engagementSum"] = row["likes"] + row["shares"] + row["comments"]
        row["selectionDecision"] = "rejected"
        row["selectionBucket"] = "candidate_gate_failed"
        row["selectionReason"] = ""
        row["retainedRank"] = 0

        if task_type == "article":
            breakdown = _coerce_breakdown(row.get("qualityBreakdown"), ARTICLE_QUALITY_WEIGHTS)
            row["qualityBreakdown"] = breakdown
            row["qualityScore"] = _sum_score(breakdown)
            publishability_breakdown = _coerce_breakdown(
                row.get("publishabilityBreakdown"),
                ARTICLE_PUBLISHABILITY_WEIGHTS,
            )
            row["publishabilityBreakdown"] = publishability_breakdown
            row["publishabilityScore"] = _article_publishability_score(
                publishability_breakdown
            )
            row["articlePriorityScore"] = row["qualityScore"] + row["publishabilityScore"]
            passed, reasons = _article_candidate_gate(row)
        else:
            breakdown = _coerce_breakdown(
                row.get("imageQualityBreakdown"), IMAGE_QUALITY_WEIGHTS
            )
            row["imageQualityBreakdown"] = breakdown
            row["imageQualityScore"] = _sum_score(breakdown)
            passed, reasons = _image_candidate_gate(row)

        row["complianceStatus"] = "approved" if passed else "rejected"
        row["complianceReasons"] = reasons
        if not passed:
            row["selectionReason"] = ",".join(reasons)
        processed.append(row)

    compliant = [row for row in processed if row["complianceStatus"] == "approved"]
    retained_order: list[str] = []
    high_value_count = 0
    quality_exception_count = 0

    if task_type == "article" and compliant:
        hot_count = max(1, math.ceil(len(compliant) * 0.10))
        quality_quota = max(1, math.ceil(len(compliant) * 0.20))
        hot = sorted(
            compliant,
            key=lambda row: (
                -row["engagementSum"],
                -row.get("articlePriorityScore", row["qualityScore"]),
                row["sourceUrl"],
            ),
        )[:hot_count]
        hot_ids = {row["candidateId"] for row in hot}
        high_value_count = len(hot_ids)
        remaining = [row for row in compliant if row["candidateId"] not in hot_ids]
        quality = sorted(
            remaining,
            key=lambda row: (
                -row.get("articlePriorityScore", row["qualityScore"]),
                -row["publishabilityScore"],
                -row["qualityScore"],
                -row["engagementSum"],
                row["sourceUrl"],
            ),
        )[:quality_quota]
        quality_ids = {row["candidateId"] for row in quality}

        for row in processed:
            if row["candidateId"] in hot_ids:
                row["selectionDecision"] = "retained"
                row["selectionBucket"] = "hot_top_10pct"
                row["selectionReason"] = "engagement_top_10pct"
                retained_order.append(row["candidateId"])
            elif row["candidateId"] in quality_ids:
                row["selectionDecision"] = "retained"
                row["selectionBucket"] = "quality_top_20pct"
                row["selectionReason"] = "quality_top_default_quota"
                retained_order.append(row["candidateId"])
            elif row["complianceStatus"] == "approved" and (
                row["qualityScore"] >= 85 or row.get("publishabilityScore", 0) >= 55
            ):
                row["selectionDecision"] = "retained"
                row["selectionBucket"] = "quality_exception"
                row["selectionReason"] = "quality_or_publishability_exception"
                retained_order.append(row["candidateId"])
                quality_exception_count += 1
            elif row["complianceStatus"] == "approved":
                row["selectionBucket"] = "default_ratio_overflow"
                row["selectionReason"] = "outside_default_keep_ratio"
    elif task_type == "image" and compliant:
        base_limit = max(1, math.ceil(len(compliant) * 0.30))
        primary = sorted(
            compliant,
            key=lambda row: (-row["imageQualityScore"], row["sourceUrl"]),
        )[:base_limit]
        primary_ids = {row["candidateId"] for row in primary}
        for row in processed:
            if row["candidateId"] in primary_ids:
                row["selectionDecision"] = "retained"
                row["selectionBucket"] = "image_top_30pct"
                row["selectionReason"] = "image_quality_top_default_quota"
                retained_order.append(row["candidateId"])
            elif row["complianceStatus"] == "approved" and row["imageQualityScore"] >= 88:
                row["selectionDecision"] = "retained"
                row["selectionBucket"] = "image_exception"
                row["selectionReason"] = "image_quality_ge_88_exception"
                retained_order.append(row["candidateId"])
                quality_exception_count += 1
            elif row["complianceStatus"] == "approved":
                row["selectionBucket"] = "default_ratio_overflow"
                row["selectionReason"] = "outside_default_keep_ratio"

    rank_map = {candidate_id: index for index, candidate_id in enumerate(retained_order, start=1)}
    for row in processed:
        row["retainedRank"] = rank_map.get(row["candidateId"], 0)

    return processed, {
        "candidateCount": len(processed),
        "compliantCount": len(compliant),
        "retainedCount": len([row for row in processed if row["selectionDecision"] == "retained"]),
        "highValueCount": high_value_count,
        "qualityExceptionCount": quality_exception_count,
    }


def _load_topic_context(
    spec: dict[str, Any],
    topic_id: str,
    task_type: str,
    *,
    write_source_pool: bool,
    skip_hydration: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    topic_dir, source_pool_path, enrichment_path = _ensure_topic_runtime_files(
        spec,
        topic_id,
        task_type,
    )
    errors: list[str] = []
    pages_root = topic_dir / "pages"
    raw_pool = read_ndjson(source_pool_path)
    enrichment_rows = read_ndjson(enrichment_path)
    if raw_pool:
        observed_task_type = str(
            raw_pool[0].get("taskType") or raw_pool[0].get("task_type") or ""
        ).strip()
        if observed_task_type and observed_task_type != task_type:
            errors.append(
                f"topic {topic_id} 的 taskType 与 lane 不一致: expected={task_type} observed={observed_task_type}"
            )

    processed_pool, pool_summary = _process_source_pool(task_type, raw_pool)
    page_snapshots: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    seen_asset_ids: set[str] = set()
    authenticity_blocking_rows: list[str] = []
    for index, row in enumerate(processed_pool, start=1):
        source_id = _source_id_from_row(row, index)
        row["sourceId"] = source_id
        hydration_errors: list[str] = []
        if not skip_hydration:
            hydration_errors = _hydrate_source_artifacts(spec, topic_id, task_type, row)
            for hydration_error in hydration_errors:
                errors.append(
                    f"topic {topic_id} source {source_id} 补抓取失败: {hydration_error}"
                )
        page_dir = pages_root / source_id
        page_html_path = page_dir / "page.html"
        source_md_path = page_dir / "source.md"
        asset_manifest_path = page_dir / "asset_manifest.json"
        page_html = page_html_path.read_text(encoding="utf-8") if page_html_path.exists() else ""
        source_markdown = source_md_path.read_text(encoding="utf-8") if source_md_path.exists() else ""
        authenticity_reasons, authenticity_payload = _page_authenticity_reasons(
            task_type,
            row,
            page_html,
            source_markdown,
        )
        row["authenticityStatus"] = "verified" if not authenticity_reasons else "rejected"
        row["authenticityReasons"] = authenticity_reasons
        row["pageTextLength"] = len(authenticity_payload["pageText"])
        row["sourceBodyTextLength"] = len(authenticity_payload["sourceBodyText"])
        row["sourceParagraphCount"] = len(authenticity_payload["sourceParagraphs"])
        if task_type == "article":
            publishability_breakdown = _article_publishability_breakdown(
                row,
                source_body=authenticity_payload["sourceBodyText"],
                source_paragraphs=authenticity_payload["sourceParagraphs"],
            )
            row["publishabilityBreakdown"] = publishability_breakdown
            row["publishabilityScore"] = _article_publishability_score(
                publishability_breakdown
            )
        if authenticity_reasons:
            authenticity_blocking_rows.append(row["candidateId"])
            row["selectionDecision"] = "rejected"
            row["selectionBucket"] = "authenticity_failed"
            row["selectionReason"] = ",".join(authenticity_reasons)
            row["retainedRank"] = 0
            row["complianceStatus"] = "rejected"
            row["complianceReasons"] = _dedupe_strings(
                list(row.get("complianceReasons", [])) + authenticity_reasons
            )
        page_manifest = read_json(asset_manifest_path) if asset_manifest_path.exists() else {}
        if page_manifest and not _schema_matches(
            page_manifest.get("schemaVersion", ""),
            TOPIC_ASSET_MANIFEST_SCHEMA_VERSION,
            LEGACY_TOPIC_ASSET_MANIFEST_SCHEMA_VERSIONS,
        ):
            errors.append(f"topic {topic_id} source {source_id} 的 asset_manifest.json schemaVersion 非法")
        if page_manifest and str(page_manifest.get("topicId", "")).strip() != topic_id:
            errors.append(f"topic {topic_id} source {source_id} 的 asset_manifest.json topicId 不匹配")
        if page_manifest and str(page_manifest.get("sourceId", "")).strip() != source_id:
            errors.append(f"topic {topic_id} source {source_id} 的 asset_manifest.json sourceId 不匹配")
        raw_assets = page_manifest.get("assets", [])
        if raw_assets and not isinstance(raw_assets, list):
            errors.append(f"topic {topic_id} source {source_id} 的 asset_manifest.json assets 必须是数组")
            raw_assets = []
        if task_type == "image" and isinstance(raw_assets, list):
            breakdown = _image_quality_breakdown(
                row,
                [asset for asset in raw_assets if isinstance(asset, dict)],
                page_text=authenticity_payload["pageText"],
                source_body=authenticity_payload["sourceBodyText"],
            )
            row["imageQualityBreakdown"] = breakdown
            row["imageQualityScore"] = _sum_score(breakdown)
            for asset in raw_assets:
                if not isinstance(asset, dict):
                    continue
                asset["imageQualityBreakdown"] = breakdown
                asset["imageQualityScore"] = row["imageQualityScore"]
            page_manifest["assets"] = raw_assets
            write_json(asset_manifest_path, page_manifest)
        for asset in raw_assets if isinstance(raw_assets, list) else []:
            if not isinstance(asset, dict):
                continue
            asset_row = dict(asset)
            asset_id = str(asset_row.get("assetId", "")).strip()
            if not asset_id or asset_id in seen_asset_ids:
                continue
            seen_asset_ids.add(asset_id)
            asset_row.setdefault("sourceId", source_id)
            asset_row.setdefault("sourceCandidateId", row["candidateId"])
            assets.append(asset_row)
        page_snapshots.append(
            {
                "sourceId": source_id,
                "pageDir": page_dir,
                "pageHtmlPath": page_html_path,
                "sourceMarkdownPath": source_md_path,
                "assetManifestPath": asset_manifest_path,
                "assetManifest": page_manifest,
                "pageHtml": page_html,
                "sourceMarkdown": source_markdown,
                "pageText": authenticity_payload["pageText"],
                "sourceBodyText": authenticity_payload["sourceBodyText"],
                "sourceParagraphs": authenticity_payload["sourceParagraphs"],
                "authenticityStatus": row["authenticityStatus"],
                "authenticityReasons": authenticity_reasons,
            }
        )

    if processed_pool:
        rescored_pool, _ = _process_source_pool(task_type, processed_pool)
        processed_pool = rescored_pool
        for row in processed_pool:
            if row.get("authenticityStatus") == "verified":
                continue
            row["selectionDecision"] = "rejected"
            row["selectionBucket"] = "authenticity_failed"
            row["selectionReason"] = ",".join(row.get("authenticityReasons", []))
            row["retainedRank"] = 0
            row["complianceStatus"] = "rejected"
            row["complianceReasons"] = _dedupe_strings(
                list(row.get("complianceReasons", [])) + list(row.get("authenticityReasons", []))
            )

    retained_rows = sorted(
        [row for row in processed_pool if row["selectionDecision"] == "retained"],
        key=lambda item: item.get("retainedRank", 0) or 999,
    )
    for rank, row in enumerate(retained_rows, start=1):
        row["retainedRank"] = rank
    pool_summary = {
        "candidateCount": len(processed_pool),
        "compliantCount": len(
            [row for row in processed_pool if row["complianceStatus"] == "approved"]
        ),
        "retainedCount": len(retained_rows),
        "highValueCount": len(
            [
                row
                for row in processed_pool
                if row["selectionDecision"] == "retained" and row["selectionBucket"] == "hot_top_10pct"
            ]
        ),
        "qualityExceptionCount": len(
            [
                row
                for row in processed_pool
                if row["selectionDecision"] == "retained"
                and row["selectionBucket"] in {"quality_exception", "image_exception"}
            ]
        ),
        "verifiedSourceCount": len(
            [row for row in processed_pool if row.get("authenticityStatus") == "verified"]
        ),
        "authenticityBlockedCount": len(
            [row for row in processed_pool if row.get("authenticityStatus") != "verified"]
        ),
    }
    if write_source_pool and source_pool_path.exists():
        write_ndjson(source_pool_path, processed_pool)

    asset_manifest = {
        "schemaVersion": TOPIC_ASSET_MANIFEST_SCHEMA_VERSION,
        "specId": spec["spec_id"],
        "topicId": topic_id,
        "taskType": task_type,
        "assets": assets,
    }
    if enrichment_rows:
        if not _schema_matches(
            enrichment_rows[0].get("schemaVersion", ""),
            TOPIC_ENRICHMENT_SCHEMA_VERSION,
            LEGACY_TOPIC_ENRICHMENT_SCHEMA_VERSIONS,
        ):
            errors.append(f"topic {topic_id} 的 enrichment.ndjson schemaVersion 非法")
    else:
        errors.append(f"topic {topic_id} 缺少 enrichment.ndjson 记录")

    title = ""
    if enrichment_rows:
        title = str(enrichment_rows[0].get("title", "")).strip()
    if not title and processed_pool:
        title = str(processed_pool[0].get("topicTitle", "")).strip()

    publish_dir = publish_topic_dir(topic_id)
    post_count = len(read_ndjson(publish_dir / "posts.ndjson")) if (publish_dir / "posts.ndjson").exists() else 0
    publish_ready = (
        bool(enrichment_rows)
        and _bool_value(enrichment_rows[0].get("publishReady"))
        and not authenticity_blocking_rows
        and bool([row for row in processed_pool if row.get("selectionDecision") == "retained"])
    )
    status = (
        "published"
        if publish_ready and post_count > 0
        else "ready_for_publish"
        if publish_ready
        else "needs_source_discovery"
        if not processed_pool
        else "needs_more_evidence"
    )

    return errors, {
        "topicId": topic_id,
        "taskType": task_type,
        "topicDir": topic_dir,
        "enrichmentPath": enrichment_path,
        "sourcePool": processed_pool,
        "sourcePoolSummary": pool_summary,
        "enrichmentRows": enrichment_rows,
        "assetManifest": asset_manifest,
        "title": title,
        "publishReady": publish_ready,
        "status": status,
        "postCount": post_count,
        "pageSnapshots": page_snapshots,
        "authenticityBlocked": bool(authenticity_blocking_rows),
        "authenticityBlockedCandidateIds": authenticity_blocking_rows,
    }


def _selected_source_rows(topic: dict[str, Any]) -> list[dict[str, Any]]:
    pool = list(topic["sourcePool"])
    enrichment_rows = list(topic["enrichmentRows"])
    if not enrichment_rows:
        return []
    selected_ids = _string_list(enrichment_rows[0].get("selectedCandidateIds"))
    if selected_ids:
        selected = [
            row
            for row in pool
            if row["candidateId"] in set(selected_ids)
            and row.get("selectionDecision") == "retained"
            and row.get("authenticityStatus") == "verified"
        ]
        if selected:
            return sorted(selected, key=lambda row: row["retainedRank"] or 999)
    return [
        row
        for row in pool
        if row["selectionDecision"] == "retained"
        and row.get("authenticityStatus") == "verified"
    ]


def _page_snapshot_map(topic: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(snapshot.get("sourceId", "")).strip(): snapshot
        for snapshot in topic.get("pageSnapshots", [])
        if str(snapshot.get("sourceId", "")).strip()
    }


def _asset_rows_by_id(asset_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = asset_manifest.get("assets", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("assetId", "")).strip(): dict(row)
        for row in rows
        if str(row.get("assetId", "")).strip()
    }


def _referenced_asset_ids(task_type: str, enrichment: dict[str, Any]) -> list[str]:
    cover_asset_id = str(
        enrichment.get("coverAssetId") or enrichment.get("cover_asset_id") or ""
    ).strip()
    ids = [cover_asset_id] if cover_asset_id else []
    if task_type == "article":
        ids.extend(_string_list(enrichment.get("figureAssetIds") or enrichment.get("figure_asset_ids")))
    else:
        ids.extend(_string_list(enrichment.get("mediaAssetIds") or enrichment.get("media_asset_ids")))
    deduped: list[str] = []
    seen: set[str] = set()
    for asset_id in ids:
        if asset_id and asset_id not in seen:
            seen.add(asset_id)
            deduped.append(asset_id)
    return deduped


def _approved_publish_assets(
    topic: dict[str, Any]
) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    errors: list[str] = []
    enrichment_rows = list(topic["enrichmentRows"])
    if not enrichment_rows:
        return ["缺少 enrichment 记录"], {}, {}, []
    enrichment = dict(enrichment_rows[0])
    selected_source_rows = _selected_source_rows(topic)
    if not selected_source_rows:
        errors.append(f"topic {topic['topicId']} 没有 retained 的 source_pool 候选")
    if topic.get("authenticityBlocked"):
        blocked = ",".join(topic.get("authenticityBlockedCandidateIds", [])[:8])
        errors.append(f"topic {topic['topicId']} 存在未通过真实性校验的来源: {blocked}")

    assets_by_id = _asset_rows_by_id(topic["assetManifest"])
    approved_assets: dict[str, dict[str, Any]] = {}
    for asset_id in _referenced_asset_ids(topic["taskType"], enrichment):
        asset = assets_by_id.get(asset_id)
        if asset is None:
            errors.append(f"topic {topic['topicId']} 缺少被正文引用的资产 {asset_id}")
            continue
        if str(asset.get("publishEligibility", "")).strip() != "approved":
            errors.append(f"topic {topic['topicId']} 资产 {asset_id} 未通过 publishEligibility")
        if str(asset.get("rightsStatus", "")).strip() != "clear":
            errors.append(f"topic {topic['topicId']} 资产 {asset_id} rightsStatus 非 clear")
        if str(asset.get("watermarkStatus", "")).strip() != "clean":
            errors.append(f"topic {topic['topicId']} 资产 {asset_id} watermarkStatus 非 clean")
        approved_assets[asset_id] = asset
    return errors, approved_assets, enrichment, selected_source_rows


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = " ".join(str(value).split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _asset_uri(asset_id: str) -> str:
    return f"asset://{asset_id}"


def _topic_post_id(topic_id: str, task_type: str, sequence: int = 1) -> str:
    return f"{topic_id}_{task_type}_{sequence:03d}"


def _compose_summary_path(spec_id: str, topic_id: str) -> Path:
    return run_topic_dir(spec_id, topic_id) / "compose_summary.json"


def _audit_summary_path(spec_id: str, topic_id: str) -> Path:
    return run_topic_dir(spec_id, topic_id) / "audit_summary.json"


def _string_or_default(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = str(payload.get(key, "")).strip()
        if value:
            return value
    return default


def _tag_ids(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for ref in refs:
        tag_id = tag_id_for_ref(ref)
        if tag_id not in seen:
            seen.add(tag_id)
            result.append(tag_id)
    return result


def _topic_entity_refs(spec: dict[str, Any], enrichment: dict[str, Any]) -> list[str]:
    return _string_list(enrichment.get("entityRefs") or enrichment.get("entity_refs")) or list(
        spec.get("entity_refs", [])
    )


def _topic_tag_refs(spec: dict[str, Any], enrichment: dict[str, Any]) -> list[str]:
    return _string_list(enrichment.get("tagRefs") or enrichment.get("tag_refs")) or list(
        spec.get("tag_refs", [])
    )


def _topic_source_urls(
    enrichment: dict[str, Any], selected_source_rows: list[dict[str, Any]]
) -> list[str]:
    source_urls = _string_list(enrichment.get("sourceUrls") or enrichment.get("source_urls"))
    if source_urls:
        return source_urls
    return [
        str(row.get("sourceUrl", "")).strip()
        for row in selected_source_rows
        if str(row.get("sourceUrl", "")).strip()
    ]


def _entity_anchor_lines(entity_refs: list[str]) -> list[str]:
    return [f"- {entity_name_for_ref(ref)} ({ref})" for ref in entity_refs if str(ref).strip()]


def _source_anchor_lines(selected_source_rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in selected_source_rows:
        domain = urlparse(str(row.get("sourceUrl", "")).strip()).netloc or str(
            row.get("domain", "")
        )
        title = str(row.get("title", "")).strip() or str(row.get("sourceUrl", "")).strip()
        lines.append(f"- {title} ({domain})")
    return _dedupe_strings(lines)


def _looks_like_generated_copy(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return True
    if any(phrase in normalized for phrase in ARTICLE_TEMPLATE_PHRASES):
        return True
    return any(
        phrase in normalized
        for phrase in ("文章任务", "图片任务", "高价值候选", "端侧可以消费", "publish", "topic_task")
    )


def _looks_like_process_copy(text: str) -> bool:
    normalized = _normalize_text(text).lower()
    if not normalized:
        return True
    return any(
        phrase in normalized
        for phrase in (
            "用来验证",
            "完整闭环",
            "抓取、清洗到发布",
            "image topic",
            "真实图片样例",
            "抓取生成",
            "真实来源基于",
            "来源页明确写出",
        )
    )


def _looks_like_old_article_summary(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return True
    return (
        normalized.startswith("这篇围绕")
        or normalized.startswith("这篇把")
        or "适合重组" in normalized
        or "整理成" in normalized
        or "适合想在半天到一天里" in normalized
    )


def _looks_like_source_snippet_copy(summary: str, selected_source_rows: list[dict[str, Any]]) -> bool:
    normalized_summary = _normalize_text(summary)
    if not normalized_summary:
        return False
    for row in selected_source_rows:
        snippet = _normalize_text(row.get("snippet", ""))
        if snippet and normalized_summary == snippet[: len(normalized_summary)]:
            return True
    return False


def _topic_display_title(topic: dict[str, Any], enrichment: dict[str, Any], selected_source_rows: list[dict[str, Any]]) -> str:
    title = _string_or_default(enrichment, "title")
    if (
        title
        and not _looks_like_placeholder_title(title)
        and not _looks_like_default_topic_title(topic["topicId"], topic["taskType"], title)
    ):
        return title
    if selected_source_rows:
        selected_title = str(selected_source_rows[0].get("title", "")).strip()
        if selected_title:
            return selected_title
    return str(topic.get("title", "")).strip() or "来源整理"


def _topic_display_summary(enrichment: dict[str, Any], article_sections: list[dict[str, Any]]) -> str:
    summary = _string_or_default(enrichment, "summary")
    if summary and not _looks_like_generated_copy(summary):
        return summary
    for section in article_sections:
        paragraphs = section.get("paragraphs", [])
        if paragraphs:
            return paragraphs[0][:96]
    return ""


def _topic_auto_summary(topic: dict[str, Any], selected_source_rows: list[dict[str, Any]]) -> str:
    if topic["taskType"] == "article":
        title = str(selected_source_rows[0].get("title", "")).strip() if selected_source_rows else str(topic.get("title", "")).strip()
        units = _article_sentence_units(topic, selected_source_rows)
        if units:
            return _article_user_summary(title or "西湖慢走路线", selected_source_rows, units)
    if topic["taskType"] == "image":
        title = str(selected_source_rows[0].get("title", "")).strip() if selected_source_rows else str(topic.get("title", "")).strip()
        if "雷峰塔" in title:
            return "塔影和开阔湖面一起铺开的那一瞬，会把西湖最舒服的层次一下子交代出来。"
        return "这一组画面把湖面、岸线和停顿感收得很完整，翻回来看时，仍然能想起杭州最松弛的节奏。"
    for row in selected_source_rows:
        snippet = _normalize_text(row.get("snippet", ""))
        if snippet and not _looks_like_placeholder_snippet(topic["taskType"], snippet):
            return snippet[:120]
    snapshots = _page_snapshot_map(topic)
    for row in selected_source_rows:
        snapshot = snapshots.get(str(row.get("sourceId", "")).strip(), {})
        for paragraph in snapshot.get("sourceParagraphs", []):
            cleaned = _normalize_text(paragraph)
            if len(cleaned) >= 45:
                return cleaned[:120]
    return ""


def _source_section_title(row: dict[str, Any], fallback_index: int) -> str:
    title = _clean_markdown_line(str(row.get("title", "")))
    if not title:
        return f"来源整理 {fallback_index}"
    title = re.split(r"[|｜\-]", title)[0].strip()
    return title[:30] if len(title) > 30 else title


def _source_asset_ids(
    source_id: str,
    approved_assets: dict[str, dict[str, Any]],
    *,
    exclude: set[str],
) -> list[str]:
    result: list[str] = []
    for asset_id, asset in approved_assets.items():
        if asset_id in exclude:
            continue
        if str(asset.get("sourceId", "")).strip() == source_id:
            result.append(asset_id)
    return result


def _ordered_approved_asset_ids(
    topic: dict[str, Any], selected_source_rows: list[dict[str, Any]]
) -> list[str]:
    assets_by_id = _asset_rows_by_id(topic["assetManifest"])
    ordered: list[str] = []
    seen: set[str] = set()
    for row in selected_source_rows:
        source_id = str(row.get("sourceId", "")).strip()
        source_assets = [
            (asset_id, asset)
            for asset_id, asset in assets_by_id.items()
            if str(asset.get("sourceId", "")).strip() == source_id
            and str(asset.get("publishEligibility", "")).strip() == "approved"
            and str(asset.get("rightsStatus", "")).strip() == "clear"
            and str(asset.get("watermarkStatus", "")).strip() == "clean"
            and str(asset.get("mimeType", "")).startswith("image/")
        ]
        source_assets.sort(
            key=lambda item: (
                -((int(item[1].get("width") or 0) * int(item[1].get("height") or 0))),
                item[0],
            )
        )
        for asset_id, _ in source_assets:
            if asset_id not in seen:
                seen.add(asset_id)
                ordered.append(asset_id)
    return ordered


def _auto_prepare_topic_enrichment(topic: dict[str, Any]) -> bool:
    enrichment_rows = list(topic.get("enrichmentRows", []))
    if not enrichment_rows:
        return False
    enrichment = dict(enrichment_rows[0])
    selected_source_rows = _selected_source_rows(topic)
    if not selected_source_rows:
        return False

    changed = False
    expected_candidate_ids = [
        str(row.get("candidateId", "")).strip()
        for row in selected_source_rows
        if str(row.get("candidateId", "")).strip()
    ]
    expected_source_urls = [
        str(row.get("sourceUrl", "")).strip()
        for row in selected_source_rows
        if str(row.get("sourceUrl", "")).strip()
    ]
    current_candidate_ids = _string_list(enrichment.get("selectedCandidateIds"))
    current_source_urls = _string_list(enrichment.get("sourceUrls") or enrichment.get("source_urls"))
    source_context_changed = (
        current_candidate_ids != expected_candidate_ids
        or current_source_urls != expected_source_urls
    )
    if source_context_changed:
        enrichment["selectedCandidateIds"] = expected_candidate_ids
        enrichment["sourceUrls"] = expected_source_urls
        selected_title = str(selected_source_rows[0].get("title", "")).strip()
        if selected_title:
            enrichment["title"] = selected_title
        auto_summary = _topic_auto_summary(topic, selected_source_rows)
        if auto_summary:
            enrichment["summary"] = auto_summary
        if topic["taskType"] == "image":
            enrichment["body"] = ""
        changed = True

    current_title = _string_or_default(enrichment, "title")
    if (
        not current_title
        or _looks_like_placeholder_title(current_title)
        or _looks_like_default_topic_title(topic["topicId"], topic["taskType"], current_title)
    ):
        enrichment["title"] = _topic_display_title(topic, enrichment, selected_source_rows)
        changed = True

    current_summary = _string_or_default(enrichment, "summary")
    if (
        not current_summary
        or _looks_like_generated_copy(current_summary)
        or (topic["taskType"] == "article" and _looks_like_old_article_summary(current_summary))
        or (topic["taskType"] == "image" and _looks_like_process_copy(current_summary))
        or _looks_like_source_snippet_copy(current_summary, selected_source_rows)
    ):
        auto_summary = _topic_auto_summary(topic, selected_source_rows)
        if auto_summary:
            enrichment["summary"] = auto_summary
            changed = True

    if not _string_list(enrichment.get("selectedCandidateIds")):
        enrichment["selectedCandidateIds"] = expected_candidate_ids
        changed = True

    if not _string_list(enrichment.get("sourceUrls")):
        enrichment["sourceUrls"] = expected_source_urls
        changed = True

    ordered_asset_ids = _ordered_approved_asset_ids(topic, selected_source_rows)
    if ordered_asset_ids:
        current_cover_asset_id = _string_or_default(enrichment, "coverAssetId", "cover_asset_id")
        if not current_cover_asset_id or current_cover_asset_id not in ordered_asset_ids:
            enrichment["coverAssetId"] = ordered_asset_ids[0]
            changed = True
        if topic["taskType"] == "article":
            current_figure_ids = _string_list(
                enrichment.get("figureAssetIds") or enrichment.get("figure_asset_ids")
            )
            valid_figure_ids = [asset_id for asset_id in current_figure_ids if asset_id in ordered_asset_ids]
            if valid_figure_ids != current_figure_ids or not valid_figure_ids:
                enrichment["figureAssetIds"] = valid_figure_ids[:1] or ordered_asset_ids[:1]
                changed = True
            if not _string_or_default(enrichment, "articleTemplate", "article_template"):
                enrichment["articleTemplate"] = "journal"
                changed = True
            if not _string_or_default(
                enrichment, "articleFontPreset", "article_font_preset"
            ):
                enrichment["articleFontPreset"] = "clean"
                changed = True
        else:
            current_media_ids = _string_list(
                enrichment.get("mediaAssetIds") or enrichment.get("media_asset_ids")
            )
            valid_media_ids = [asset_id for asset_id in current_media_ids if asset_id in ordered_asset_ids]
            if valid_media_ids != current_media_ids or not valid_media_ids:
                enrichment["mediaAssetIds"] = valid_media_ids[:1] or ordered_asset_ids[:1]
                changed = True
            current_body = _string_or_default(enrichment, "body")
            if not current_body or _looks_like_generated_copy(current_body) or _looks_like_process_copy(current_body):
                enrichment["body"] = ""
                changed = True

    if not _bool_value(enrichment.get("publishReady")) and ordered_asset_ids:
        enrichment["publishReady"] = True
        changed = True

    if not changed:
        return False
    topic["enrichmentRows"] = [enrichment]
    topic["publishReady"] = bool(enrichment.get("publishReady"))
    topic["title"] = str(enrichment.get("title", "")).strip() or topic.get("title", "")
    write_ndjson(topic["enrichmentPath"], [enrichment])
    return True


def _article_source_sections(
    topic: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    snapshots = _page_snapshot_map(topic)
    seen_paragraphs: set[str] = set()
    sections: list[dict[str, Any]] = []
    section_titles = [
        "先把沿湖范围走明白",
        "第一次到现场别急着打卡",
        "把停留节奏慢下来",
        "把沿线变化变成行走线索",
    ]
    for index, row in enumerate(selected_source_rows, start=1):
        source_id = str(row.get("sourceId", "")).strip()
        snapshot = snapshots.get(source_id, {})
        paragraphs: list[str] = []
        for paragraph in snapshot.get("sourceParagraphs", []):
            normalized = _normalize_text(paragraph)
            if len(normalized) < MIN_ARTICLE_SOURCE_PARAGRAPH_CHARS:
                continue
            if normalized in seen_paragraphs:
                continue
            seen_paragraphs.add(normalized)
            paragraphs.append(normalized)
            if len(paragraphs) >= 6:
                break
        if not paragraphs:
            continue
        for chunk_index, start in enumerate(range(0, len(paragraphs), 2)):
            chunk = paragraphs[start : start + 2]
            if not chunk:
                continue
            title = section_titles[min(len(sections), len(section_titles) - 1)]
            if index > 1:
                title = f"{_source_section_title(row, index)} · {title}"
            sections.append(
                {
                    "sourceId": source_id,
                    "title": title,
                    "paragraphs": chunk,
                    "sourceTitle": _source_section_title(row, index),
                    "chunkIndex": chunk_index,
                }
            )
    return sections


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for chunk in re.split(r"[。！？.!?]", _normalize_text(text)):
        cleaned = re.sub(r"\[[^\]]+\]", "", chunk).strip(" ，,、；;:：")
        if len(cleaned) >= 10:
            sentences.append(cleaned)
    return sentences


def _source_anchor_phrases(text: str, *, limit: int = 3) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for sentence in _split_sentences(text):
        clauses = [
            part.strip()
            for part in re.split(r"[，,、；;:：]", sentence)
            if len(part.strip()) >= 8
        ]
        candidate_parts = clauses or [sentence]
        for part in candidate_parts:
            snippet = re.sub(r"\s+", " ", part[:32]).strip()
            if len(snippet) < 8 or snippet in seen:
                continue
            seen.add(snippet)
            phrases.append(snippet)
            if len(phrases) >= limit:
                return phrases
    return phrases


def _section_support_sentences(paragraphs: list[str], *, limit: int = 2) -> list[str]:
    support: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
        for sentence in _split_sentences(paragraph):
            candidate = sentence.strip()
            if len(candidate) < 16 or candidate in seen:
                continue
            seen.add(candidate)
            support.append(candidate)
            if len(support) >= limit:
                return support
    return support


def _support_fragment(text: str) -> str:
    normalized = _normalize_text(text)
    clauses = [
        part.strip()
        for part in re.split(r"[，,、；;:：]", normalized)
        if len(part.strip()) >= 8
    ]
    candidate = clauses[0] if clauses else normalized
    if len(candidate) > 26:
        candidate = candidate[:26].rstrip("，,、；;:： ")
    return candidate

def _compose_article_section_paragraphs(section: dict[str, Any], index: int) -> list[str]:
    phrases: list[str] = []
    for paragraph in section.get("paragraphs", []):
        for phrase in _source_anchor_phrases(paragraph):
            if phrase not in phrases:
                phrases.append(phrase)
            if len(phrases) >= 4:
                break
        if len(phrases) >= 4:
            break
    if not phrases:
        return []
    support = _section_support_sentences(list(section.get("paragraphs", [])))
    opening_templates = [
        "第一次到西湖，最值得先记住的，是把“{a}”和“{b}”放进同一条行走逻辑里。",
        "真正决定这段体验感的，往往不是多走几个点，而是先把“{a}”和“{b}”看成一张完整的现场地图。",
        "如果想把现场走顺，可以先盯住“{a}”和“{b}”这两层信息，再决定自己要不要继续往深处走。",
        "比起机械打卡，更稳的做法是先把“{a}”和“{b}”连起来理解，脚步自然会慢下来。",
    ]
    closing_templates = [
        "真到现场时，再把“{c}”和“{d}”当成停留判断位，整段路线就不会散。",
        "继续往里走的时候，把“{c}”和“{d}”记在心里，回头看景就不会只剩下拍照动作。",
        "如果还想把体验写得更具体，“{c}”和“{d}”这两个细节最能帮你把现场感接起来。",
        "往下看的时候，不妨顺手留意“{c}”和“{d}”，它们能把这段体验从景点清单变成完整过程。",
    ]
    paragraphs: list[str] = []
    if len(phrases) >= 2:
        lead = opening_templates[(index - 1) % len(opening_templates)].format(
            a=phrases[0],
            b=phrases[1],
        )
        if support:
            paragraphs.append(f'{lead}来源页把重点落在“{_support_fragment(support[0])}”这一层。')
        else:
            paragraphs.append(lead)
    else:
        fallback = f"这一段最稳的抓手，其实就是先把“{phrases[0]}”记住。"
        paragraphs.append(
            f'{fallback}来源页也反复提到“{_support_fragment(support[0])}”。'
            if support
            else fallback
        )
    if len(phrases) >= 4:
        closing = closing_templates[(index - 1) % len(closing_templates)].format(
            c=phrases[2],
            d=phrases[3],
        )
        if len(support) >= 2:
            paragraphs.append(f'{closing}补充判断时，可以继续盯住“{_support_fragment(support[1])}”。')
        else:
            paragraphs.append(closing)
    elif len(phrases) == 3:
        extra = f"如果只留一个补充判断位，“{phrases[2]}”已经足够把停留节奏接起来。"
        if len(support) >= 2:
            paragraphs.append(f'{extra}来源页也把细节落在“{_support_fragment(support[1])}”。')
        else:
            paragraphs.append(extra)
    return paragraphs


def _gallery_body(
    enrichment: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
    approved_assets: dict[str, dict[str, Any]],
    resolved_asset_ids: list[str],
) -> str:
    preset = _string_or_default(enrichment, "body")
    if preset and not _looks_like_generated_copy(preset) and not _looks_like_process_copy(preset):
        return preset
    task_type = str(selected_source_rows[0].get("taskType", "")).strip() if selected_source_rows else ""
    title = _string_or_default(enrichment, "title") or (
        str(selected_source_rows[0].get("title", "")).strip() if selected_source_rows else "西湖图集"
    )
    source_title = str(selected_source_rows[0].get("title", "")).strip() if selected_source_rows else ""
    captions = [
        str(approved_assets[asset_id].get("caption", "")).strip()
        for asset_id in resolved_asset_ids[:2]
        if asset_id in approved_assets
    ]
    caption_text = "；".join(caption for caption in captions if caption)
    if task_type == "image":
        body = (
            "这一组画面更适合慢慢看。"
            "湖面、远山和岸线会一起把西湖最舒服的层次交代清楚。"
        )
        if caption_text and caption_text != title:
            body += f"画面里最先抓人的，是{caption_text}这样的开阔视角。"
        else:
            body += "画面里最先抓人的，是塔影和开阔湖面同时铺开的那一瞬。"
        body += "不管是拿来做行前种草，还是当作散步后的回望，都很容易让人重新想起杭州最松弛的节奏。"
        return body
    body = "这一组图片适合和正文一起看。先看湖面与岸线的展开，再看停留点和回望角度，整篇文章的路线感会更完整。"
    if caption_text:
        body += f"图里最值得留意的画面线索，是{caption_text}。"
    elif source_title:
        body += f"这一页的图像和“{source_title}”这条路线放在一起看，会更容易理解西湖为什么适合慢慢走。"
    body += "真正到了现场，图里的开阔感和停顿感，往往比景点名字本身更能决定一趟散步的心情。"
    return body


def _article_sentence_category(text: str) -> str:
    normalized = _normalize_text(text)
    if any(term in normalized for term in ("游船", "船夫", "喝茶", "饭店", "美食", "夜生活", "晚饭")):
        return "practical"
    if any(
        term in normalized
        for term in ("雷峰塔", "苏堤", "白堤", "断桥", "湖滨", "公园", "三潭印月", "平湖秋月", "曲院风荷")
    ):
        return "landmark"
    if any(term in normalized for term in ("世界遗产", "最为知名", "风景名胜", "西湖十景", "位于", "景观")):
        return "overview"
    return "general"


def _article_sentence_units(
    topic: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    snapshots = _page_snapshot_map(topic)
    units: list[dict[str, Any]] = []
    seen_sentences: set[str] = set()
    for source_order, row in enumerate(selected_source_rows, start=1):
        source_id = str(row.get("sourceId", "")).strip()
        snapshot = snapshots.get(source_id, {})
        for paragraph_order, paragraph in enumerate(snapshot.get("sourceParagraphs", []), start=1):
            paragraph_score = _article_paragraph_relevance_score(paragraph, row)
            for sentence_order, sentence in enumerate(_split_sentences(paragraph), start=1):
                cleaned = _normalize_text(sentence)
                if len(cleaned) < 14 or cleaned in seen_sentences:
                    continue
                seen_sentences.add(cleaned)
                category = _article_sentence_category(cleaned)
                score = paragraph_score
                if category == "landmark":
                    score += 3
                elif category == "overview":
                    score += 2
                elif category == "practical":
                    score += 1
                units.append(
                    {
                        "text": cleaned,
                        "sourceId": source_id,
                        "sourceTitle": str(row.get("title", "")).strip(),
                        "category": category,
                        "score": score,
                        "sourceOrder": source_order,
                        "paragraphOrder": paragraph_order,
                        "sentenceOrder": sentence_order,
                    }
                )
    units.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            int(item.get("sourceOrder", 0)),
            int(item.get("paragraphOrder", 0)),
            int(item.get("sentenceOrder", 0)),
        )
    )
    return units


def _article_pick_units(
    units: list[dict[str, Any]],
    *,
    categories: set[str],
    limit: int,
    used_texts: set[str] | None = None,
) -> list[dict[str, Any]]:
    used = used_texts if used_texts is not None else set()
    selected: list[dict[str, Any]] = []
    for unit in units:
        text = str(unit.get("text", "")).strip()
        if not text or text in used:
            continue
        if categories and str(unit.get("category", "")) not in categories:
            continue
        used.add(text)
        selected.append(unit)
        if len(selected) >= limit:
            return selected
    if categories:
        for unit in units:
            text = str(unit.get("text", "")).strip()
            if not text or text in used:
                continue
            used.add(text)
            selected.append(unit)
            if len(selected) >= limit:
                return selected
    return selected


def _article_useful_fact(text: str) -> bool:
    normalized = _normalize_text(text)
    if len(normalized) < 4:
        return False
    blocked_terms = (
        "省会",
        "政治",
        "经济",
        "金融",
        "常住人口",
        "总面积",
        "行政建制",
        "都城",
        "G20",
        "都市圈",
        "🕘",
        "💰",
        "更新日期",
    )
    return not any(term in normalized for term in blocked_terms)


def _article_prose_fact(text: str) -> str:
    normalized = _normalize_text(text)
    normalized = re.sub(r"[🕘💰]+", "", normalized)
    normalized = re.sub(r"^\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+\d+\s*", "", normalized)
    return normalized.strip(" ，,、；;:：。")


def _article_facts_from_units(
    units: list[dict[str, Any]],
    *,
    limit: int = 4,
) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()
    for unit in units:
        candidates = _source_anchor_phrases(str(unit.get("text", "")), limit=4)
        if not candidates:
            candidates = [_support_fragment(str(unit.get("text", "")))]
        for candidate in candidates:
            prose = _article_prose_fact(candidate)
            if not _article_useful_fact(prose) or prose in seen:
                continue
            seen.add(prose)
            facts.append(prose)
            if len(facts) >= limit:
                return facts
    return facts


def _article_fact(facts: list[str], index: int, fallback: str) -> str:
    if index < len(facts):
        return facts[index]
    return fallback


def _ordered_travel_tokens(
    text: str,
    *,
    keywords: tuple[str, ...] = ARTICLE_TRAVEL_KEYWORDS,
    limit: int = 6,
) -> list[str]:
    normalized = _normalize_text(text)
    hits: list[tuple[int, int, str]] = []
    for keyword in keywords:
        index = normalized.find(keyword)
        if index >= 0:
            hits.append((index, -len(keyword), keyword))
    hits.sort()
    tokens: list[str] = []
    seen: set[str] = set()
    for _, __, keyword in hits:
        if keyword in seen:
            continue
        seen.add(keyword)
        tokens.append(keyword)
        if len(tokens) >= limit:
            break
    return tokens


def _article_token_pool(
    title: str,
    selected_source_rows: list[dict[str, Any]],
    units: list[dict[str, Any]],
    *,
    keywords: tuple[str, ...] = ARTICLE_TRAVEL_KEYWORDS,
    limit: int = 8,
) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    sources: list[str] = [title]
    for row in selected_source_rows:
        sources.extend(
            [
                str(row.get("title", "")),
                str(row.get("query", "")),
                str(row.get("snippet", "")),
            ]
        )
    sources.extend(str(unit.get("text", "")) for unit in units[:12])
    for source in sources:
        for token in _ordered_travel_tokens(source, keywords=keywords, limit=6):
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
            if len(tokens) >= limit:
                break
        if len(tokens) >= limit:
            break
    if "西湖" not in seen:
        tokens.insert(0, "西湖")
    return tokens[:limit]


def _article_token_text(token: str) -> str:
    mapping = {
        "西湖": "西湖主湖区",
        "西湖十景": "十景里最想看的两三个点",
        "苏堤春晓": "苏堤春晓这条经典线",
        "三潭印月": "坐船去三潭印月",
        "柳浪闻莺": "柳浪闻莺这一带",
        "曲院风荷": "曲院风荷这一带",
        "平湖秋月": "平湖秋月这一侧",
        "花港观鱼": "花港观鱼这一带",
        "湖滨公园": "湖滨公园一带",
        "湖滨": "湖滨这一侧",
        "雷峰塔": "雷峰塔附近的南线",
        "断桥": "断桥这一侧",
        "苏堤": "苏堤这段长堤",
        "白堤": "白堤和断桥一侧",
        "游船": "坐一小段游船",
        "喝茶": "找个靠湖的位置喝茶",
        "杭帮菜": "晚饭留给一顿杭帮菜",
        "美食": "晚饭留给湖边",
        "饭店": "晚饭留给湖边",
        "南线": "南线这一段",
        "东岸": "东岸这一侧",
        "湖面": "开阔的湖面",
    }
    return mapping.get(token, token)


def _article_token(tokens: list[str], index: int, fallback: str) -> str:
    if index < len(tokens):
        return _article_token_text(tokens[index])
    return fallback


def _article_teaser_lead(title: str) -> str:
    normalized = _normalize_text(title)
    if "雷峰塔" in normalized:
        return "想把雷峰塔和南线留给一个下午，就别把路线切得太碎。"
    if "十景" in normalized:
        return "第一次来西湖，最容易累的，就是想着把十景一次追完。"
    if "苏堤" in normalized:
        return "苏堤最适合慢慢走，不用把每一个点都赶上。"
    if "白堤" in normalized:
        return "清晨的白堤最好慢慢走，不用急着把镜头和脚步都推到最满。"
    if "三潭印月" in normalized or "坐船" in normalized:
        return "想从船上看西湖，最好把时间整块留给三潭印月。"
    return "第一次逛西湖，不必急着把清单一口气追满。"


def _article_teaser_followup(
    tokens: list[str],
    practical_tokens: list[str],
) -> str:
    return (
        f"先从{_article_token(tokens, 0, '湖滨这一侧')}走进去，再把"
        f"{_article_token(tokens, 1, '一段最舒服的沿湖步行线')}和"
        f"{_article_token(tokens, 2, '后半程最值得停下来的点')}留到后面，"
        f"中间给{_article_token(practical_tokens, 0, '坐一小段游船')}或"
        f"{_article_token(practical_tokens, 1, '找个靠湖的位置喝茶')}留一点空档，"
        "整天的节奏就会舒服很多。"
    )


def _article_user_summary(
    title: str,
    selected_source_rows: list[dict[str, Any]],
    units: list[dict[str, Any]],
) -> str:
    tokens = _article_token_pool(title, selected_source_rows, units, limit=5)
    practical_tokens = _article_token_pool(
        title,
        selected_source_rows,
        units,
        keywords=ARTICLE_PRACTICAL_KEYWORDS,
        limit=3,
    )
    return f"{_article_teaser_lead(title)}{_article_teaser_followup(tokens, practical_tokens)}"


def _article_body_sections(
    title: str,
    selected_source_rows: list[dict[str, Any]],
    units: list[dict[str, Any]],
) -> list[tuple[str, list[str]]]:
    focus_tokens = _article_token_pool(title, selected_source_rows, units, limit=6)
    route_tokens = _article_token_pool(
        title,
        selected_source_rows,
        units,
        keywords=ARTICLE_ROUTE_KEYWORDS,
        limit=5,
    )
    practical_tokens = _article_token_pool(
        title,
        selected_source_rows,
        units,
        keywords=ARTICLE_PRACTICAL_KEYWORDS,
        limit=4,
    )

    return [
        (
            "先把湖区轮廓看明白",
            [
                (
                    f"第一次来西湖，先别急着把清单拉满。把"
                    f"{_article_token(route_tokens, 0, '湖滨这一侧')}、"
                    f"{_article_token(route_tokens, 1, '一段最舒服的沿湖步行线')}和"
                    f"{_article_token(route_tokens, 2, '今天最想停下来的一个点')}放进同一天里，"
                    "湖面、岸线和停顿感自然会慢慢连成一条线。"
                ),
                (
                    f"真正舒服的走法，是先接受这里适合慢下来。像"
                    f"{_article_token(focus_tokens, 0, '西湖主湖区')}这样负责把第一眼打开的地方，"
                    f"再加上{_article_token(focus_tokens, 1, '后半程最值得回望的一段')}"
                    "，就足够把第一次来杭州的节奏安顿好。"
                ),
            ],
        ),
        (
            "真正值得停下来的几个点",
            [
                (
                    f"到了真正好看的位置，别急着拍完就走。"
                    f"{_article_token(route_tokens, 0, '湖滨这一侧')}适合看湖面打开，"
                    f"{_article_token(route_tokens, 1, '另一处经典停留点')}则更适合把塔影、堤岸或水上的层次收进视线里。"
                ),
                (
                    f"如果今天只想留下两三个最记得住的画面，就把"
                    f"{_article_token(focus_tokens, 2, '前半程的一段经典线')}留给白天，再把"
                    f"{_article_token(focus_tokens, 3, '傍晚最适合回头看湖面的地方')}留到后面。"
                    "这样最后留下来的，不会只是到此一游，而是几段真正记得住的杭州画面。"
                ),
            ],
        ),
        (
            "把半天走成完整行程",
            [
                (
                    f"西湖最难得的，是风景和休息不会互相打断。走到合适的时候，"
                    f"{_article_token(practical_tokens, 0, '坐一小段游船')}、"
                    f"{_article_token(practical_tokens, 1, '找个靠湖的位置喝茶')}，"
                    "都能很自然地接到路线里，让这趟散步从看景变成真正有起承转合的一天。"
                ),
                (
                    f"等到傍晚，再回头看一眼"
                    f"{_article_token(route_tokens, 3, '那段最适合收尾的岸线')}，"
                    f"顺手把{_article_token(practical_tokens, 2, '晚饭放在湖边解决')}，"
                    "这趟行程就会收得很完整。你会记住的不是景点解释，而是杭州怎么把一个普通下午慢慢过成了值得回想的一天。"
                ),
            ],
        ),
    ]


def _build_article_markdown(
    spec: dict[str, Any],
    topic: dict[str, Any],
    enrichment: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
    approved_assets: dict[str, dict[str, Any]],
) -> str:
    article_units = _article_sentence_units(topic, selected_source_rows)
    if len(article_units) < 4:
        raise ValueError(f"topic {topic['topicId']} 缺少足够真实正文，无法生成 article.md")
    title = _topic_display_title(topic, enrichment, selected_source_rows)
    summary = _string_or_default(enrichment, "summary")
    if (
        not summary
        or _looks_like_generated_copy(summary)
        or _looks_like_old_article_summary(summary)
        or _looks_like_source_snippet_copy(summary, selected_source_rows)
    ):
        summary = _article_user_summary(title, selected_source_rows, article_units)
    entity_refs = _topic_entity_refs(spec, enrichment)
    cover_asset_id = _string_or_default(enrichment, "coverAssetId", "cover_asset_id")
    figure_asset_ids = _string_list(
        enrichment.get("figureAssetIds") or enrichment.get("figure_asset_ids")
    )
    asset_ids = _dedupe_strings([cover_asset_id, *figure_asset_ids])
    used_assets: set[str] = set()
    intro_tokens = _article_token_pool(title, selected_source_rows, article_units, limit=6)
    practical_tokens = _article_token_pool(
        title,
        selected_source_rows,
        article_units,
        keywords=ARTICLE_PRACTICAL_KEYWORDS,
        limit=3,
    )
    article_sections = _article_body_sections(title, selected_source_rows, article_units)

    lines = [
        "---",
        f"title: {title}",
        f"summary: {summary}",
    ]
    if cover_asset_id:
        lines.append(f"cover_asset_id: {cover_asset_id}")
    lines.extend(
        [
        f"template: {_string_or_default(enrichment, 'articleTemplate', 'article_template', default='journal')}",
        f"fontPreset: {_string_or_default(enrichment, 'articleFontPreset', 'article_font_preset', default='clean')}",
        ]
    )
    lines.extend(["---", "", f"# {title}", ""])

    lines.extend(
        [
            (
                f"真正舒服的开场，不是急着把路线踩满，而是先让"
                f"{_article_token(intro_tokens, 0, '西湖主湖区')}把视线打开。再把"
                f"{_article_token(intro_tokens, 1, '一段最舒服的沿湖步行线')}和"
                f"{_article_token(intro_tokens, 2, '一个今天最想停下来的点')}接进同一天里，"
                "湖面、岸线和停留点自然会慢慢连成一条线。"
            ),
            "",
            (
                f"如果时间只有半天到一天，就把"
                f"{_article_token(intro_tokens, 3, '前半程最舒服的一段步行线')}放在前半程，再把"
                f"{_article_token(intro_tokens, 4, '后半程最适合回望湖面的地方')}留到后面，"
                f"中间给{_article_token(practical_tokens, 0, '坐一小段游船')}或"
                f"{_article_token(practical_tokens, 1, '找个靠湖的位置喝茶')}这样的停顿一点空间。"
                "这样走下来，记住的会是杭州的节奏，而不是一张打卡清单。"
            ),
            "",
        ]
    )

    if cover_asset_id and cover_asset_id in approved_assets:
        caption = str(approved_assets[cover_asset_id].get("caption", "")).replace('"', '\\"')
        lines.extend(
            [
                f':::figure id="{cover_asset_id}" layout="wrapRight" caption="{caption}"',
                _asset_uri(cover_asset_id),
                ":::",
                "",
            ]
        )
        used_assets.add(cover_asset_id)

    for index, (section_title, section_paragraphs) in enumerate(article_sections, start=1):
        lines.extend([f"## {section_title}", ""])
        section_asset_candidates = [asset_id for asset_id in asset_ids if asset_id in approved_assets and asset_id not in used_assets]
        if section_asset_candidates:
            asset_id = section_asset_candidates[0]
            caption = str(approved_assets[asset_id].get("caption", "")).replace('"', '\\"')
            lines.extend(
                [
                    f':::figure id="{asset_id}" layout="wrapLeft" caption="{caption}"',
                    _asset_uri(asset_id),
                    ":::",
                    "",
                ]
            )
            used_assets.add(asset_id)
        for paragraph in section_paragraphs:
            lines.extend([paragraph, ""])

    lines.extend(["## 实体锚点", ""])
    for line in _entity_anchor_lines(entity_refs):
        lines.append(line)
    lines.append("")

    lines.extend(["## 来源锚点", ""])
    for line in _source_anchor_lines(selected_source_rows):
        lines.append(line)
    lines.append("")

    if asset_ids:
        gallery_ids = [asset_id for asset_id in asset_ids if asset_id in approved_assets]
        lines.extend(
            [
                f':::gallery ids="{",".join(gallery_ids)}" layout="masonry" caption="{title} 图像锚点"',
                ":::",
                "",
            ]
        )

    lines.extend(
        [
            f'<!-- spec:{spec["spec_id"]} topic:{topic["topicId"]} retained:{len(selected_source_rows)} -->',
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _build_gallery_markdown(
    spec: dict[str, Any],
    topic: dict[str, Any],
    enrichment: dict[str, Any],
    approved_assets: dict[str, dict[str, Any]],
    selected_source_rows: list[dict[str, Any]],
    *,
    asset_ids: list[str] | None = None,
    title_override: str = "",
    summary_override: str = "",
    cover_asset_id: str = "",
) -> str:
    title = title_override or _string_or_default(enrichment, "title")
    summary = summary_override or _string_or_default(enrichment, "summary")
    entity_refs = _topic_entity_refs(spec, enrichment)
    resolved_asset_ids = asset_ids or list(approved_assets)
    resolved_cover_asset_id = cover_asset_id or (
        resolved_asset_ids[0] if resolved_asset_ids else ""
    )

    lines = [
        "---",
        f"title: {title}",
        f"summary: {summary}",
    ]
    if resolved_cover_asset_id:
        lines.append(f"cover_asset_id: {resolved_cover_asset_id}")
    lines.extend(
        [
            "---",
            "",
            f"# {title}",
            "",
            _gallery_body(
                enrichment,
                selected_source_rows,
                approved_assets,
                resolved_asset_ids,
            ),
            "",
        ]
    )
    if resolved_asset_ids:
        lines.extend(
            [
                f':::gallery ids="{",".join(resolved_asset_ids)}" layout="masonry" caption="{title}"',
                ":::",
                "",
            ]
        )
    lines.extend(["## 实体锚点", ""])
    for line in _entity_anchor_lines(entity_refs):
        lines.append(line)
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _topic_compliance(
    topic: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
    approved_assets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    blocked_candidates = [
        row["candidateId"] for row in selected_source_rows if row["complianceStatus"] != "approved"
    ]
    blocked_assets = [
        asset_id
        for asset_id, asset in approved_assets.items()
        if str(asset.get("publishEligibility", "")).strip() != "approved"
        or str(asset.get("rightsStatus", "")).strip() != "clear"
        or str(asset.get("watermarkStatus", "")).strip() != "clean"
    ]
    return {
        "overallStatus": "approved" if not blocked_candidates and not blocked_assets else "rejected",
        "blockedCandidateIds": blocked_candidates,
        "blockedAssetIds": blocked_assets,
        "retainedCandidateCount": len(selected_source_rows),
        "approvedAssetCount": len(approved_assets),
    }


def _asset_manifest_row(asset_id: str, asset: dict[str, Any]) -> dict[str, Any]:
    package_path = _package_asset_path(asset_id, asset)
    return {
        "assetId": asset_id,
        "kind": asset.get("kind", "image"),
        "scope": "crawl_topic_task",
        "objectKey": asset.get("objectKey", ""),
        "localPath": asset.get("localPath", ""),
        "packagePath": package_path,
        "downloadStatus": asset.get("downloadStatus", ""),
        "sourceUrl": asset.get("sourceUrl", ""),
        "caption": asset.get("caption", ""),
        "sha256": asset.get("sha256", ""),
        "mimeType": asset.get("mimeType", ""),
        "width": asset.get("width"),
        "height": asset.get("height"),
        "imageQualityScore": asset.get("imageQualityScore"),
        "imageQualityBreakdown": asset.get("imageQualityBreakdown", {}),
        "license": asset.get("license", {}),
        "rightsStatus": asset.get("rightsStatus", ""),
        "watermarkStatus": asset.get("watermarkStatus", ""),
        "publishEligibility": asset.get("publishEligibility", ""),
        "platform": asset.get("platform", ""),
        "sourceId": asset.get("sourceId", ""),
        "sourceCandidateId": asset.get("sourceCandidateId", ""),
    }


def _package_asset_path(asset_id: str, asset: dict[str, Any]) -> str:
    suffix = Path(str(asset.get("localPath", "")).strip()).suffix
    if not suffix:
        mime_type = str(asset.get("mimeType", "")).strip()
        if mime_type == "image/jpeg":
            suffix = ".jpg"
        elif mime_type == "image/png":
            suffix = ".png"
        elif mime_type == "image/webp":
            suffix = ".webp"
        elif mime_type == "image/gif":
            suffix = ".gif"
    return f"images/{asset_id}{suffix}" if suffix else f"images/{asset_id}"


def _build_manifest_metadata(
    spec: dict[str, Any],
    topic: dict[str, Any],
    enrichment: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
    *,
    title: str = "",
    summary: str = "",
    cover_asset_id: str = "",
    template: str = "",
    font_preset: str = "",
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "title": title or _string_or_default(enrichment, "title"),
        "summary": summary or _string_or_default(enrichment, "summary"),
        "coverAssetId": cover_asset_id
        or _string_or_default(enrichment, "coverAssetId", "cover_asset_id"),
    }
    if topic["taskType"] == "article":
        metadata["template"] = template or _string_or_default(
            enrichment, "articleTemplate", "article_template", default="journal"
        )
        metadata["fontPreset"] = font_preset or _string_or_default(
            enrichment, "articleFontPreset", "article_font_preset", default="clean"
        )
    return {
        "contentMetadata": metadata,
        "entityRefs": _topic_entity_refs(spec, enrichment),
        "tagRefs": _topic_tag_refs(spec, enrichment),
        "sourceUrls": _topic_source_urls(enrichment, selected_source_rows),
        "selectedSourceIds": [
            str(row.get("sourceId", "")).strip()
            for row in selected_source_rows
            if str(row.get("sourceId", "")).strip()
        ],
    }


def _build_publish_manifest(
    spec: dict[str, Any],
    topic: dict[str, Any],
    post_id: str,
    article_markdown: str,
    approved_assets: dict[str, dict[str, Any]],
    compliance: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    assets = [_asset_manifest_row(asset_id, asset) for asset_id, asset in approved_assets.items()]
    payload: dict[str, Any] = {
        "schemaVersion": PACKAGE_MANIFEST_SCHEMA_VERSION,
        "specId": spec["spec_id"],
        "topicId": topic["topicId"],
        "postId": post_id,
        "contentType": topic["taskType"],
        **metadata,
        "compliance": compliance,
        "assets": assets,
    }
    if topic["taskType"] == "article":
        payload.update(
            {
                "articleMarkdown": "article.md",
                "galleryMarkdown": "gallery.md",
                "articleMarkdownVersion": "qwq-rich-md/1",
                "articleMarkdownDigest": "sha256:"
                + hashlib.sha256(article_markdown.encode("utf-8")).hexdigest(),
            }
        )
    else:
        payload["galleryMarkdown"] = "gallery.md"
    return payload


def _write_package_asset_refs(post_dir: Path, manifest: dict[str, Any]) -> None:
    images_dir = post_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for row in manifest.get("assets", []):
        asset_id = str(row.get("assetId", "")).strip()
        if not asset_id:
            continue
        local_path = str(row.get("localPath", "")).strip()
        package_path = str(row.get("packagePath", "")).strip()
        if local_path and package_path:
            source_path = RUNTIME_ROOT / local_path
            target_path = post_dir / package_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.exists():
                shutil.copy2(source_path, target_path)
        write_text(images_dir / f"{asset_id}.ref", json.dumps(row, ensure_ascii=False, indent=2) + "\n")


def _cover_url_from_assets(
    approved_assets: dict[str, dict[str, Any]], cover_asset_id: str = ""
) -> str:
    if cover_asset_id and cover_asset_id in approved_assets:
        return str(approved_assets[cover_asset_id].get("objectKey", ""))
    if approved_assets:
        first = next(iter(approved_assets.values()))
        return str(first.get("objectKey", ""))
    return ""


def _build_entities(spec: dict[str, Any], selected_source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_urls = [
        str(row.get("sourceUrl", "")).strip()
        for row in selected_source_rows
        if str(row.get("sourceUrl", "")).strip()
    ]
    entities: list[dict[str, Any]] = []
    for ref in spec.get("entity_refs", []):
        payload = entity_payload_for_ref(ref)
        payload["evidence_refs"] = _dedupe_strings(list(payload.get("evidence_refs", [])) + evidence_urls)
        entities.append(payload)
    return entities


def _write_publish_summary(
    topic_id: str, spec: dict[str, Any], post_rows: list[dict[str, Any]], selected_source_rows: list[dict[str, Any]]
) -> None:
    titles = [
        str(row.get("post_payload", {}).get("title", "")).strip()
        for row in post_rows
        if str(row.get("post_payload", {}).get("title", "")).strip()
    ]
    lines = [
        f"# 发布摘要：{topic_id}",
        "",
        f"- spec_id: `{spec['spec_id']}`",
        f"- query: `{spec['query']}`",
        f"- task_type: `{post_rows[0].get('post_payload', {}).get('contentType', '') if post_rows else ''}`",
        f"- retained_sources: {len(selected_source_rows)}",
        f"- post_count: {len(post_rows)}",
        f"- titles: {', '.join(titles)}",
        "",
    ]
    write_text(publish_topic_dir(topic_id) / "summary.md", "\n".join(lines).strip() + "\n")


def _projection_asset_refs(entities: list[dict[str, Any]], posts: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for entity in entities:
        refs.extend(_string_list(entity.get("media_refs")))
    for row in posts:
        semantic = row.get("semantic", {})
        if isinstance(semantic, dict):
            refs.extend(_string_list(semantic.get("asset_refs")))
        payload = row.get("post_payload", {})
        refs.extend(_string_list(payload.get("mediaUrls")))
        cover_url = str(payload.get("coverUrl", "")).strip()
        if cover_url:
            refs.append(cover_url)
    return _dedupe_strings(refs)


def _write_projection(
    topic_id: str, target: str, spec: dict[str, Any], entities: list[dict[str, Any]], posts: list[dict[str, Any]]
) -> None:
    payload = {
        "schemaVersion": "quwoquan_data.crawl_projection",
        "generated_at": now_iso(),
        "environment": target,
        "spec_id": spec["spec_id"],
        "topic_id": topic_id,
        "query": spec["query"],
        "task_type": posts[0]["post_payload"]["contentType"] if posts else "",
        "entity_ids": [row.get("entity_id", "") for row in entities],
        "entity_refs": [row.get("entity_ref", "") for row in entities],
        "post_titles": [row.get("post_payload", {}).get("title", "") for row in posts],
        "post_source_ids": [row.get("post_payload", {}).get("sourcePostId", "") for row in posts],
        "asset_refs": _projection_asset_refs(entities, posts),
        "scope": "dry_run",
        "dry_run_only": True,
    }
    write_json(out_topic_dir(topic_id) / f"{target}_projection.json", payload)


def _build_article_post(
    spec: dict[str, Any],
    topic: dict[str, Any],
    enrichment: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
    approved_assets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    topic_id = topic["topicId"]
    post_id = _topic_post_id(topic_id, "article")
    post_dir = publish_topic_dir(topic_id) / "posts" / post_id
    post_dir.mkdir(parents=True, exist_ok=True)

    article_markdown = _build_article_markdown(spec, topic, enrichment, selected_source_rows, approved_assets)
    gallery_markdown = _build_gallery_markdown(spec, topic, enrichment, approved_assets, selected_source_rows)
    compliance = _topic_compliance(topic, selected_source_rows, approved_assets)
    cover_asset_id = _string_or_default(enrichment, "coverAssetId", "cover_asset_id")
    semantic_entity_refs = _topic_entity_refs(spec, enrichment)
    semantic_tag_refs = _topic_tag_refs(spec, enrichment)
    source_urls = _topic_source_urls(enrichment, selected_source_rows)
    metadata = _build_manifest_metadata(
        spec,
        topic,
        enrichment,
        selected_source_rows,
        cover_asset_id=cover_asset_id,
    )
    manifest = _build_publish_manifest(
        spec, topic, post_id, article_markdown, approved_assets, compliance, metadata
    )
    write_text(post_dir / "article.md", article_markdown)
    write_text(post_dir / "gallery.md", gallery_markdown)
    write_json(post_dir / "manifest.json", manifest)
    _write_package_asset_refs(post_dir, manifest)

    users = load_user_pool()
    author = users[_lane_creator_refs(spec, "article")[0]]
    payload = {
        "post_payload": {
            "contentType": "article",
            "type": "article",
            "contentIdentity": "work",
            "title": _string_or_default(enrichment, "title"),
            "summary": _string_or_default(enrichment, "summary"),
            "coverUrl": _cover_url_from_assets(approved_assets, cover_asset_id),
            "tags": _tag_ids(semantic_tag_refs),
            "locationName": _string_or_default(enrichment, "locationName", "location_name"),
            "visibility": spec.get("publish_policy", {}).get("visibility", "public"),
            "assistantUsePolicy": spec.get("publish_policy", {}).get("assistant_use_policy", "inherit"),
            "authorId": author["userId"],
            "authorDisplayNameSnapshot": author["displayName"],
            "authorAvatarUrlSnapshot": author["avatarObjectKey"],
            "sourceType": "crawl_topic_task",
            "sourcePostId": post_id,
            "articleMarkdown": article_markdown,
            "articleMarkdownVersion": "qwq-rich-md/1",
            "articleMarkdownDigest": manifest["articleMarkdownDigest"],
            "articleRenderProfile": {
                "template": _string_or_default(
                    enrichment, "articleTemplate", "article_template", default="journal"
                ),
                "fontPreset": _string_or_default(
                    enrichment, "articleFontPreset", "article_font_preset", default="clean"
                ),
                "layoutPolicy": {
                    "wrapDowngrade": "compactWidthToFullWidth",
                    "galleryDowngrade": "singleColumn",
                },
            },
        },
        "semantic": {
            "spec_id": spec["spec_id"],
            "topic_id": topic_id,
            "entity_refs": semantic_entity_refs,
            "tag_refs": semantic_tag_refs,
            "source_urls": source_urls,
            "asset_refs": [
                str(asset.get("objectKey", "")).strip()
                for asset in approved_assets.values()
                if str(asset.get("objectKey", "")).strip()
            ],
        },
    }
    write_json(post_dir / "post.json", payload)
    return payload


def _chunk_asset_ids(asset_ids: list[str], *, chunk_size: int = 3) -> list[list[str]]:
    if not asset_ids:
        return []
    return [asset_ids[index : index + chunk_size] for index in range(0, len(asset_ids), chunk_size)]


def _build_image_posts(
    spec: dict[str, Any],
    topic: dict[str, Any],
    enrichment: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
    approved_assets: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    topic_id = topic["topicId"]
    users = load_user_pool()
    author = users[_lane_creator_refs(spec, "image")[0]]
    semantic_entity_refs = _topic_entity_refs(spec, enrichment)
    semantic_tag_refs = _topic_tag_refs(spec, enrichment)
    source_urls = _topic_source_urls(enrichment, selected_source_rows)
    ordered_asset_ids = [
        asset_id
        for asset_id in _referenced_asset_ids("image", enrichment)
        if asset_id in approved_assets
    ]
    if not ordered_asset_ids:
        ordered_asset_ids = list(approved_assets)
    post_rows: list[dict[str, Any]] = []
    asset_groups = _chunk_asset_ids(ordered_asset_ids)
    total_groups = len(asset_groups)
    base_title = _string_or_default(enrichment, "title")
    base_summary = _string_or_default(enrichment, "summary")
    for sequence, asset_ids in enumerate(asset_groups, start=1):
        post_id = _topic_post_id(topic_id, "image", sequence)
        post_dir = publish_topic_dir(topic_id) / "posts" / post_id
        post_dir.mkdir(parents=True, exist_ok=True)
        group_assets = {
            asset_id: approved_assets[asset_id]
            for asset_id in asset_ids
            if asset_id in approved_assets
        }
        post_title = base_title if total_groups == 1 else f"{base_title} · 第{sequence}组"
        post_summary = (
            base_summary
            if total_groups == 1
            else f"{base_summary}（第{sequence}组）"
        )
        cover_asset_id = asset_ids[0] if asset_ids else ""
        post_body = _gallery_body(
            enrichment,
            selected_source_rows,
            group_assets,
            asset_ids,
        )
        gallery_markdown = _build_gallery_markdown(
            spec,
            topic,
            enrichment,
            group_assets,
            selected_source_rows,
            asset_ids=asset_ids,
            title_override=post_title,
            summary_override=post_summary,
            cover_asset_id=cover_asset_id,
        )
        compliance = _topic_compliance(topic, selected_source_rows, group_assets)
        metadata = _build_manifest_metadata(
            spec,
            topic,
            enrichment,
            selected_source_rows,
            title=post_title,
            summary=post_summary,
            cover_asset_id=cover_asset_id,
        )
        manifest = _build_publish_manifest(
            spec, topic, post_id, "", group_assets, compliance, metadata
        )
        write_text(post_dir / "gallery.md", gallery_markdown)
        write_json(post_dir / "manifest.json", manifest)
        _write_package_asset_refs(post_dir, manifest)
        media_urls = [
            str(asset.get("objectKey", "")).strip()
            for asset in group_assets.values()
            if str(asset.get("objectKey", "")).strip()
        ]
        payload = {
            "post_payload": {
                "contentType": "image",
                "type": "image",
                "contentIdentity": "work",
                "title": post_title,
                "summary": post_summary,
                "body": post_body,
                "mediaUrls": media_urls,
                "coverUrl": _cover_url_from_assets(group_assets, cover_asset_id),
                "tags": _tag_ids(semantic_tag_refs),
                "locationName": _string_or_default(enrichment, "locationName", "location_name"),
                "visibility": spec.get("publish_policy", {}).get("visibility", "public"),
                "assistantUsePolicy": spec.get("publish_policy", {}).get("assistant_use_policy", "inherit"),
                "authorId": author["userId"],
                "authorDisplayNameSnapshot": author["displayName"],
                "authorAvatarUrlSnapshot": author["avatarObjectKey"],
                "sourceType": "crawl_topic_task",
                "sourcePostId": post_id,
            },
            "semantic": {
                "spec_id": spec["spec_id"],
                "topic_id": topic_id,
                "entity_refs": semantic_entity_refs,
                "tag_refs": semantic_tag_refs,
                "source_urls": source_urls,
                "asset_refs": media_urls,
            },
        }
        write_json(post_dir / "post.json", payload)
        post_rows.append(payload)
    return post_rows


def _strip_markdown_front_matter(markdown_text: str) -> str:
    text = markdown_text.replace("\ufeff", "").strip()
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            text = parts[1]
    return text.strip()


def _extract_markdown_body_paragraphs(markdown_text: str) -> list[str]:
    body = _strip_markdown_front_matter(markdown_text)
    paragraphs: list[str] = []
    for chunk in re.split(r"\n\s*\n", body):
        raw = chunk.strip()
        if not raw:
            continue
        if raw.startswith("#") or raw.startswith(":::") or raw.startswith("asset://") or raw.startswith("<!--"):
            continue
        cleaned = _clean_markdown_line(raw)
        if cleaned in {"实体锚点", "来源锚点"}:
            continue
        if cleaned.startswith("- "):
            continue
        if len(cleaned) >= 24:
            paragraphs.append(cleaned)
    return paragraphs


def _article_grounding_hits_by_source(
    article_text: str,
    topic: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
) -> dict[str, list[str]]:
    article_normalized = _normalize_text(article_text)
    snapshots = _page_snapshot_map(topic)
    result: dict[str, list[str]] = {}
    for row in selected_source_rows:
        source_id = str(row.get("sourceId", "")).strip()
        snapshot = snapshots.get(source_id, {})
        hits: set[str] = set()
        for paragraph in snapshot.get("sourceParagraphs", []):
            for phrase in _source_anchor_phrases(paragraph, limit=4) + _ordered_travel_tokens(
                paragraph,
                keywords=ARTICLE_TRAVEL_KEYWORDS,
                limit=4,
            ):
                if phrase and phrase in article_normalized:
                    hits.add(phrase)
        result[source_id] = sorted(hits)
    return result


def _article_post_review(
    spec: dict[str, Any],
    topic: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
    post_dir: Path,
    post_row: dict[str, Any],
) -> dict[str, Any]:
    article_path = post_dir / "article.md"
    article_text = article_path.read_text(encoding="utf-8")
    body_paragraphs = _extract_markdown_body_paragraphs(article_text)
    title = (
        str(post_row.get("post_payload", {}).get("title", "")).strip()
        or str(topic.get("title", "")).strip()
        or "西湖旅行长文"
    )
    article_units = _article_sentence_units(topic, selected_source_rows)
    core_tokens = _article_token_pool(
        title,
        selected_source_rows,
        article_units,
        limit=max(4, len(selected_source_rows) + 3),
    )
    article_normalized = _normalize_text(article_text)
    covered_tokens = [token for token in core_tokens if token in article_normalized]
    factual_ratio = len(covered_tokens) / max(1, len(core_tokens))
    factual_score = round(factual_ratio * 100)
    factual_pass = factual_ratio >= 0.5 and len(covered_tokens) >= min(3, len(core_tokens))

    blocked_phrases = [phrase for phrase in ARTICLE_TEMPLATE_PHRASES if phrase in article_text]
    reader_facing_score = max(0, 100 - len(blocked_phrases) * 25)
    reader_facing_pass = not blocked_phrases

    detail_tokens = sorted({token for token in ARTICLE_TRAVEL_KEYWORDS if token in article_normalized})
    specificity_score = min(100, 40 + len(detail_tokens) * 10)
    specificity_pass = len(detail_tokens) >= 4 and len(body_paragraphs) >= 6

    paragraph_prefixes = [paragraph[:14] for paragraph in body_paragraphs if len(paragraph) >= 14]
    duplicate_paragraph_count = len(body_paragraphs) - len(set(body_paragraphs))
    repeated_prefix_count = len(paragraph_prefixes) - len(set(paragraph_prefixes))
    redundancy_score = max(0, 100 - duplicate_paragraph_count * 35 - repeated_prefix_count * 8)
    redundancy_pass = duplicate_paragraph_count == 0 and repeated_prefix_count <= 2

    grounding_hits = _article_grounding_hits_by_source(article_text, topic, selected_source_rows)
    matched_source_count = len([source_id for source_id, hits in grounding_hits.items() if hits])
    total_source_count = max(1, len(selected_source_rows))
    grounding_score = round(100 * matched_source_count / total_source_count)
    grounding_pass = matched_source_count == total_source_count

    overall_score = round(
        (
            factual_score
            + reader_facing_score
            + specificity_score
            + redundancy_score
            + grounding_score
        )
        / 5
    )
    overall_status = (
        "approved"
        if factual_pass
        and reader_facing_pass
        and specificity_pass
        and redundancy_pass
        and grounding_pass
        and overall_score >= 70
        else "rejected"
    )
    return {
        "schemaVersion": POST_REVIEW_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "role": "audit",
        "specId": spec["spec_id"],
        "topicId": topic["topicId"],
        "postId": str(post_row.get("post_payload", {}).get("sourcePostId", "")).strip(),
        "taskType": "article",
        "overallStatus": overall_status,
        "overallScore": overall_score,
        "checks": {
            "factualCoverage": {
                "score": factual_score,
                "pass": factual_pass,
                "coveredTokenCount": len(covered_tokens),
                "coreTokenCount": len(core_tokens),
                "coveredTokens": covered_tokens,
                "coreTokens": core_tokens,
            },
            "readerFacingTone": {
                "score": reader_facing_score,
                "pass": reader_facing_pass,
                "blockedPhrases": blocked_phrases,
            },
            "specificity": {
                "score": specificity_score,
                "pass": specificity_pass,
                "detailTokenCount": len(detail_tokens),
                "detailTokens": detail_tokens,
                "bodyParagraphCount": len(body_paragraphs),
            },
            "redundancy": {
                "score": redundancy_score,
                "pass": redundancy_pass,
                "duplicateParagraphCount": duplicate_paragraph_count,
                "repeatedPrefixCount": repeated_prefix_count,
            },
            "sourceGrounding": {
                "score": grounding_score,
                "pass": grounding_pass,
                "matchedSourceCount": matched_source_count,
                "totalSourceCount": total_source_count,
                "perSourceHits": grounding_hits,
            },
        },
    }


def _image_post_review(
    spec: dict[str, Any],
    topic: dict[str, Any],
    post_dir: Path,
    post_row: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    gallery_text = (post_dir / "gallery.md").read_text(encoding="utf-8")
    asset_rows = [dict(row) for row in manifest.get("assets", []) if isinstance(row, dict)]
    runtime_missing: list[str] = []
    package_missing: list[str] = []
    quality_scores: list[int] = []
    for asset in asset_rows:
        local_path = str(asset.get("localPath", "")).strip()
        package_path = str(asset.get("packagePath", "")).strip()
        if local_path and not (RUNTIME_ROOT / local_path).exists():
            runtime_missing.append(local_path)
        if package_path and not (post_dir / package_path).exists():
            package_missing.append(package_path)
        quality_scores.append(int(asset.get("imageQualityScore") or 0))
    download_pass = bool(asset_rows) and not runtime_missing and not package_missing
    rights_values = sorted({str(asset.get("rightsStatus", "")).strip() for asset in asset_rows if str(asset.get("rightsStatus", "")).strip()})
    watermark_values = sorted({str(asset.get("watermarkStatus", "")).strip() for asset in asset_rows if str(asset.get("watermarkStatus", "")).strip()})
    rights_pass = all(value == "clear" for value in rights_values) if rights_values else False
    watermark_pass = all(value == "clean" for value in watermark_values) if watermark_values else False
    image_quality_score = round(sum(quality_scores) / max(1, len(quality_scores))) if quality_scores else 0
    narrative_tokens = sorted({token for token in ARTICLE_TRAVEL_KEYWORDS if token in _normalize_text(gallery_text)})
    narrative_score = min(100, 40 + len(narrative_tokens) * 12)
    narrative_pass = len(narrative_tokens) >= 2 or any(term in gallery_text for term in ("西湖", "湖面", "岸线", "塔影"))
    overall_score = round(
        (
            (100 if download_pass else 0)
            + (100 if rights_pass else 0)
            + (100 if watermark_pass else 0)
            + image_quality_score
            + narrative_score
        )
        / 5
    )
    overall_status = (
        "approved"
        if download_pass and rights_pass and watermark_pass and image_quality_score >= 70 and narrative_pass
        else "rejected"
    )
    return {
        "schemaVersion": POST_REVIEW_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "role": "audit",
        "specId": spec["spec_id"],
        "topicId": topic["topicId"],
        "postId": str(post_row.get("post_payload", {}).get("sourcePostId", "")).strip(),
        "taskType": "image",
        "overallStatus": overall_status,
        "overallScore": overall_score,
        "checks": {
            "imageQualityScore": {
                "score": image_quality_score,
                "pass": image_quality_score >= 70,
                "assetScores": quality_scores,
            },
            "downloadVerified": {
                "pass": download_pass,
                "runtimeFilesVerified": not runtime_missing,
                "packageFilesVerified": not package_missing,
                "missingRuntimePaths": runtime_missing,
                "missingPackagePaths": package_missing,
            },
            "rightsReview": {
                "pass": rights_pass,
                "values": rights_values,
            },
            "watermarkReview": {
                "pass": watermark_pass,
                "values": watermark_values,
            },
            "narrativeFit": {
                "score": narrative_score,
                "pass": narrative_pass,
                "matchedTokens": narrative_tokens,
            },
        },
    }


def _write_post_review(post_dir: Path, review: dict[str, Any]) -> None:
    review_path = post_dir / "review.json"
    write_json(review_path, review)
    manifest_path = post_dir / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        manifest["qualityAudit"] = {
            "role": "audit",
            "overallStatus": review.get("overallStatus", ""),
            "overallScore": review.get("overallScore"),
            "reviewPath": "review.json",
        }
        write_json(manifest_path, manifest)


def _audit_topic_posts(
    spec: dict[str, Any],
    topic: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    publish_dir = publish_topic_dir(topic["topicId"])
    post_rows = read_ndjson(publish_dir / "posts.ndjson")
    if not post_rows:
        raise ValueError(f"topic {topic['topicId']} 缺少 publish/posts.ndjson，无法执行 audit")
    review_rows: list[dict[str, Any]] = []
    for post_row in post_rows:
        post_id = str(post_row.get("post_payload", {}).get("sourcePostId", "")).strip()
        if not post_id:
            continue
        post_dir = publish_dir / "posts" / post_id
        manifest = read_json(post_dir / "manifest.json")
        if topic["taskType"] == "article":
            review = _article_post_review(spec, topic, selected_source_rows, post_dir, post_row)
        else:
            review = _image_post_review(spec, topic, post_dir, post_row, manifest)
        _write_post_review(post_dir, review)
        review_rows.append(review)
    if not review_rows:
        raise ValueError(f"topic {topic['topicId']} 没有可审核的 post review")
    overall_score = round(
        sum(int(review.get("overallScore") or 0) for review in review_rows) / len(review_rows)
    )
    overall_status = (
        "approved"
        if all(str(review.get("overallStatus", "")).strip() == "approved" for review in review_rows)
        else "rejected"
    )
    summary = {
        "schemaVersion": TOPIC_AUDIT_SUMMARY_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "role": "audit",
        "specId": spec["spec_id"],
        "topicId": topic["topicId"],
        "taskType": topic["taskType"],
        "overallStatus": overall_status,
        "overallScore": overall_score,
        "reviewCount": len(review_rows),
        "approvedReviewCount": len([review for review in review_rows if review.get("overallStatus") == "approved"]),
        "rejectedReviewCount": len([review for review in review_rows if review.get("overallStatus") != "approved"]),
        "retainedSourceIds": [str(row.get("sourceId", "")).strip() for row in selected_source_rows],
        "reviewPaths": [
            f"publish/{topic['topicId']}/posts/{review['postId']}/review.json"
            for review in review_rows
        ],
        "reviews": [
            {
                "postId": review.get("postId", ""),
                "overallStatus": review.get("overallStatus", ""),
                "overallScore": review.get("overallScore"),
            }
            for review in review_rows
        ],
    }
    write_json(_audit_summary_path(spec["spec_id"], topic["topicId"]), summary)
    return summary


def _write_compose_summary(
    spec: dict[str, Any],
    topic: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
    approved_assets: dict[str, dict[str, Any]],
    post_rows: list[dict[str, Any]],
    targets: list[str],
) -> dict[str, Any]:
    summary = {
        "schemaVersion": TOPIC_COMPOSE_SUMMARY_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "role": "compose",
        "overallStatus": "composed",
        "specId": spec["spec_id"],
        "topicId": topic["topicId"],
        "taskType": topic["taskType"],
        "retainedSourceIds": [str(row.get("sourceId", "")).strip() for row in selected_source_rows],
        "approvedAssetIds": list(approved_assets.keys()),
        "postIds": [
            str(row.get("post_payload", {}).get("sourcePostId", "")).strip()
            for row in post_rows
            if str(row.get("post_payload", {}).get("sourcePostId", "")).strip()
        ],
        "targets": targets,
        "publishDir": str(publish_topic_dir(topic["topicId"])),
        "projectionPaths": [
            str(out_topic_dir(topic["topicId"]) / f"{target}_projection.json")
            for target in targets
        ],
    }
    write_json(_compose_summary_path(spec["spec_id"], topic["topicId"]), summary)
    return summary


def _refresh_discovery_artifacts(spec: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    topic_errors, topic_tasks = _collect_topic_tasks(spec, write_source_pool=False, skip_hydration=False)
    discovery = _build_discovery_summary(spec, topic_tasks)
    write_ndjson(topic_tasks_path(spec["spec_id"]), topic_tasks)
    write_json(discovery_path(spec["spec_id"]), discovery)
    return topic_errors, topic_tasks, discovery


def _resolve_topic_task_type(spec: dict[str, Any], topic_id: str) -> str:
    article_topics = _sample_topics(spec, "article")
    image_topics = _sample_topics(spec, "image")
    if topic_id not in (article_topics + image_topics):
        return ""
    return "image" if topic_id in image_topics else "article"


def _rehydrate_topic_sources(
    spec: dict[str, Any],
    topic_id: str,
    task_type: str,
    source_rows: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for row in source_rows:
        source_id = str(row.get("sourceId") or row.get("candidateId") or "").strip()
        source_url = str(row.get("sourceUrl", "")).strip()
        if not source_id or not source_url:
            continue
        hydration_errors = _hydrate_source_artifacts(
            spec,
            topic_id,
            task_type,
            row,
            force=True,
        )
        errors.extend(hydration_errors)
    return errors


def _prepare_topic_for_compose(
    spec: dict[str, Any],
    topic_id: str,
) -> tuple[list[str], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    task_type = _resolve_topic_task_type(spec, topic_id)
    if not task_type:
        return [f"topic 不属于当前 spec: {topic_id}"], {}, {}, {}, []
    context_errors, topic = _load_topic_context(
        spec,
        topic_id,
        task_type,
        write_source_pool=True,
    )
    _auto_prepare_topic_enrichment(topic)
    asset_errors, approved_assets, enrichment, selected_source_rows = _approved_publish_assets(topic)
    if not topic["publishReady"] or not approved_assets:
        rehydrate_errors = _rehydrate_topic_sources(spec, topic_id, task_type, list(topic.get("sourcePool", [])))
        if rehydrate_errors:
            context_errors.extend(rehydrate_errors)
        else:
            context_errors, topic = _load_topic_context(
                spec,
                topic_id,
                task_type,
                write_source_pool=True,
            )
            _auto_prepare_topic_enrichment(topic)
            asset_errors, approved_assets, enrichment, selected_source_rows = _approved_publish_assets(topic)
    discovery_policy = _discovery_policy(spec)
    if topic["sourcePoolSummary"]["candidateCount"] < discovery_policy["min_candidate_sources_per_task"]:
        context_errors.append(
            f"topic {topic_id} 的 source_pool 候选不足 {discovery_policy['min_candidate_sources_per_task']} 条"
        )
    if not topic["publishReady"]:
        context_errors.append(f"topic {topic_id} 尚未 ready_for_publish")
    return context_errors + asset_errors, topic, enrichment, approved_assets, selected_source_rows


def _compose_topic_outputs(
    spec: dict[str, Any],
    topic: dict[str, Any],
    enrichment: dict[str, Any],
    selected_source_rows: list[dict[str, Any]],
    approved_assets: dict[str, dict[str, Any]],
    targets: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    topic_id = topic["topicId"]
    audit_summary_path = _audit_summary_path(spec["spec_id"], topic_id)
    if audit_summary_path.exists():
        audit_summary_path.unlink()
    publish_dir = publish_topic_dir(topic_id)
    if publish_dir.exists():
        shutil.rmtree(publish_dir)
    publish_dir.mkdir(parents=True, exist_ok=True)
    topic_out_dir = out_topic_dir(topic_id)
    if topic_out_dir.exists():
        shutil.rmtree(topic_out_dir)
    entities = _build_entities(spec, selected_source_rows)
    if topic["taskType"] == "article":
        post_rows = [_build_article_post(spec, topic, enrichment, selected_source_rows, approved_assets)]
    else:
        post_rows = _build_image_posts(spec, topic, enrichment, selected_source_rows, approved_assets)
    write_ndjson(publish_dir / "entities.ndjson", entities)
    write_ndjson(publish_dir / "posts.ndjson", post_rows)
    _write_publish_summary(topic_id, spec, post_rows, selected_source_rows)
    for target in targets:
        _write_projection(topic_id, target, spec, entities, post_rows)
    compose_summary = _write_compose_summary(
        spec,
        topic,
        selected_source_rows,
        approved_assets,
        post_rows,
        targets,
    )
    return entities, post_rows, compose_summary


def _topic_task_row(
    spec: dict[str, Any],
    lane: str,
    topic_id: str,
    *,
    write_source_pool: bool,
    skip_hydration: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    errors, topic = _load_topic_context(
        spec,
        topic_id,
        lane,
        write_source_pool=write_source_pool,
        skip_hydration=skip_hydration,
    )
    selected_rows = _selected_source_rows(topic)
    discovery_policy = _discovery_policy(spec)
    approved_asset_count = len(
        [
            row
            for row in _asset_rows_by_id(topic["assetManifest"]).values()
            if str(row.get("publishEligibility", "")).strip() == "approved"
        ]
    )
    compose_summary_path = _compose_summary_path(spec["spec_id"], topic_id)
    compose_summary = read_json(compose_summary_path) if compose_summary_path.exists() else {}
    audit_summary_path = _audit_summary_path(spec["spec_id"], topic_id)
    audit_summary = read_json(audit_summary_path) if audit_summary_path.exists() else {}
    status = topic["status"]
    audit_status = str(audit_summary.get("overallStatus", "")).strip()
    if topic["postCount"] > 0 and compose_summary_path.exists() and not audit_status:
        status = "awaiting_quality_review"
    elif topic["postCount"] > 0 and audit_status == "rejected":
        status = "needs_quality_review"
    row = {
        "schemaVersion": TOPIC_TASK_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "specId": spec["spec_id"],
        "topicId": topic_id,
        "taskType": topic["taskType"],
        "lane": lane,
        "title": topic["title"],
        "status": status,
        "publishReady": topic["publishReady"],
        "candidateCount": topic["sourcePoolSummary"]["candidateCount"],
        "candidateFloorMet": topic["sourcePoolSummary"]["candidateCount"]
        >= discovery_policy["min_candidate_sources_per_task"],
        "retainedCandidateCount": topic["sourcePoolSummary"]["retainedCount"],
        "highValueCandidateCount": topic["sourcePoolSummary"]["highValueCount"],
        "qualityExceptionCount": topic["sourcePoolSummary"]["qualityExceptionCount"],
        "verifiedSourceCount": topic["sourcePoolSummary"].get("verifiedSourceCount", 0),
        "authenticityBlockedCount": topic["sourcePoolSummary"].get("authenticityBlockedCount", 0),
        "authenticityBlocked": topic.get("authenticityBlocked", False),
        "approvedAssetCount": approved_asset_count,
        "selectedAssetCount": len(_referenced_asset_ids(topic["taskType"], topic["enrichmentRows"][0]))
        if topic["enrichmentRows"]
        else 0,
        "selectedSourceUrls": [str(item.get("sourceUrl", "")).strip() for item in selected_rows],
        "queries": _dedupe_strings([str(item.get("query", "")).strip() for item in topic["sourcePool"]]),
        "runtimeTopicDir": str(topic["topicDir"]),
        "postCount": topic["postCount"],
        "scoringModel": "article_quality_v1" if topic["taskType"] == "article" else "image_quality_v1",
        "composeSummaryPath": str(compose_summary_path) if compose_summary_path.exists() else "",
        "composeStatus": str(compose_summary.get("overallStatus", "")).strip() or (
            "composed" if topic["postCount"] > 0 else "pending"
        ),
        "auditSummaryPath": str(audit_summary_path) if audit_summary_path.exists() else "",
        "auditStatus": audit_status or "pending",
        "auditOverallScore": audit_summary.get("overallScore"),
        "pipelineRoles": {
            "crawl": "hydrated"
            if topic["sourcePoolSummary"].get("verifiedSourceCount", 0)
            else "pending",
            "compose": str(compose_summary.get("overallStatus", "")).strip()
            or ("composed" if topic["postCount"] > 0 else "pending"),
            "audit": audit_status or "pending",
        },
    }
    return errors, row


def _collect_topic_tasks(
    spec: dict[str, Any], *, write_source_pool: bool, skip_hydration: bool = False
) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    for lane in ("article", "image"):
        for topic_id in _sample_topics(spec, lane):
            topic_errors, row = _topic_task_row(
                spec,
                lane,
                topic_id,
                write_source_pool=write_source_pool,
                skip_hydration=skip_hydration,
            )
            errors.extend(topic_errors)
            rows.append(row)
    return errors, rows


def _build_discovery_summary(spec: dict[str, Any], topic_tasks: list[dict[str, Any]]) -> dict[str, Any]:
    policy = _discovery_policy(spec)
    article_tasks = [row for row in topic_tasks if row["taskType"] == "article"]
    image_tasks = [row for row in topic_tasks if row["taskType"] == "image"]
    article_published = len([row for row in article_tasks if row["status"] == "published"])
    image_published = len([row for row in image_tasks if row["status"] == "published"])
    article_ready = len([row for row in article_tasks if row["publishReady"]])
    image_ready = len([row for row in image_tasks if row["publishReady"]])
    overall_status = (
        "ready_for_topic_work"
        if article_ready or image_ready
        else "needs_source_discovery"
        if any(row["status"] == "needs_source_discovery" for row in topic_tasks)
        else "needs_more_evidence"
        if topic_tasks
        else "empty"
    )
    return {
        "schemaVersion": DISCOVERY_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "specId": spec["spec_id"],
        "query": spec["query"],
        "status": overall_status,
        "articleTopicCount": len(article_tasks),
        "imageTopicCount": len(image_tasks),
        "articleReadyCount": article_ready,
        "imageReadyCount": image_ready,
        "articlePublishedCount": article_published,
        "imagePublishedCount": image_published,
        "articleAuthenticityBlockedCount": len(
            [row for row in article_tasks if row.get("authenticityBlocked")]
        ),
        "imageAuthenticityBlockedCount": len(
            [row for row in image_tasks if row.get("authenticityBlocked")]
        ),
        "articleAuditApprovedCount": len([row for row in article_tasks if row.get("auditStatus") == "approved"]),
        "imageAuditApprovedCount": len([row for row in image_tasks if row.get("auditStatus") == "approved"]),
        "minArticleTopics": policy["min_article_topics"],
        "minImageTopics": policy["min_image_topics"],
        "minCandidateSourcesPerTask": policy["min_candidate_sources_per_task"],
        "minArticlePublishTopics": policy["min_article_publish_topics"],
        "minImagePublishTopics": policy["min_image_publish_topics"],
        "articleTopicFloorMet": len(article_tasks) >= policy["min_article_topics"],
        "imageTopicFloorMet": len(image_tasks) >= policy["min_image_topics"],
        "articlePublishFloorMet": article_published >= policy["min_article_publish_topics"],
        "imagePublishFloorMet": image_published >= policy["min_image_publish_topics"],
    }


def _load_spec(spec_arg: str, selected_targets: list[str]) -> tuple[list[str], dict[str, Any], Path]:
    ensure_runtime_layout()
    spec_path = crawl_spec_path_from_arg(spec_arg)
    if not spec_path.exists():
        return [f"spec 不存在 {spec_path}"], {}, spec_path
    spec = read_yaml(spec_path)
    errors = validate_crawl_spec(spec, selected_targets)
    return errors, spec, spec_path


def handle_spec_discovery(args) -> int:
    ensure_runtime_layout()
    errors, spec, spec_path = _load_spec(args.spec, [])
    if errors:
        for error in errors:
            print(f"[crawl spec-discovery] FAIL: {error}", file=sys.stderr)
        return 1

    skip_hydration = bool(getattr(args, "skip_hydrate", False))
    topic_errors, topic_tasks = _collect_topic_tasks(
        spec, write_source_pool=True, skip_hydration=skip_hydration
    )
    discovery = _build_discovery_summary(spec, topic_tasks)
    write_ndjson(topic_tasks_path(spec["spec_id"]), topic_tasks)
    write_json(discovery_path(spec["spec_id"]), discovery)

    for error in topic_errors[:80]:
        print(f"[crawl spec-discovery] WARN: {error}", file=sys.stderr)
    print(
        "[crawl spec-discovery] OK: "
        f"spec={spec['spec_id']} article_topics={discovery['articleTopicCount']} "
        f"image_topics={discovery['imageTopicCount']} spec_path={spec_path}"
    )
    return 0


def handle_status(args) -> int:
    ensure_runtime_layout()
    errors, spec, _ = _load_spec(args.spec, [])
    if errors:
        for error in errors:
            print(f"[crawl status] FAIL: {error}", file=sys.stderr)
        return 1

    skip_hydration = bool(getattr(args, "skip_hydrate", False))
    topic_errors, topic_tasks = _collect_topic_tasks(
        spec, write_source_pool=False, skip_hydration=skip_hydration
    )
    discovery = _build_discovery_summary(spec, topic_tasks)
    payload = {
        **discovery,
        "topicTasksPath": str(topic_tasks_path(spec["spec_id"])),
        "discoveryPath": str(discovery_path(spec["spec_id"])),
        "errors": topic_errors,
        "topics": [
            {
                "topicId": row["topicId"],
                "taskType": row["taskType"],
                "status": row["status"],
                "publishReady": row["publishReady"],
                "candidateCount": row["candidateCount"],
                "retainedCandidateCount": row["retainedCandidateCount"],
                "verifiedSourceCount": row.get("verifiedSourceCount", 0),
                "authenticityBlocked": row.get("authenticityBlocked", False),
                "postCount": row["postCount"],
                "composeStatus": row.get("composeStatus", "pending"),
                "auditStatus": row.get("auditStatus", "pending"),
                "auditOverallScore": row.get("auditOverallScore"),
            }
            for row in topic_tasks
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def handle_fetch_source(args) -> int:
    ensure_runtime_layout()
    errors, spec, _ = _load_spec(args.spec, [])
    if errors:
        for error in errors:
            print(f"[crawl fetch-source] FAIL: {error}", file=sys.stderr)
        return 1
    task_type = str(args.task_type).strip()
    if task_type not in SUPPORTED_CONTENT_TYPES:
        print(
            f"[crawl fetch-source] FAIL: task_type 只支持 image/article，收到 {task_type}",
            file=sys.stderr,
        )
        return 1
    topic_id = str(args.topic).strip()
    source_id = str(args.source_id).strip()
    source_url = str(args.url).strip()
    if not topic_id or not source_id or not source_url:
        print("[crawl fetch-source] FAIL: topic/source_id/url 不能为空", file=sys.stderr)
        return 1
    _, source_pool_path, _ = _ensure_topic_runtime_files(spec, topic_id, task_type)
    raw_pool = read_ndjson(source_pool_path)
    row = {
        "candidateId": source_id,
        "sourceId": source_id,
        "taskType": task_type,
        "topicTitle": str(args.title or _default_topic_title(topic_id, task_type)).strip(),
        "query": str(args.query or spec.get("query", "")).strip(),
        "title": str(args.title or source_id).strip(),
        "sourceUrl": source_url,
        "domain": _normalize_domain(urlparse(source_url).netloc),
        "platform": _normalize_domain(urlparse(source_url).netloc),
        "snippet": str(args.snippet or "").strip(),
        "sourceRole": str(args.source_role or "publish_candidate").strip(),
        "rightsStatus": str(args.rights_status or "clear").strip(),
        "watermarkStatus": str(args.watermark_status or "clean").strip(),
        "duplicateStatus": "unique",
        "adSignal": False,
        "likes": 0,
        "shares": 0,
        "comments": 0,
        "qualityBreakdown": {},
        "publishabilityBreakdown": {},
        "imageQualityBreakdown": {},
    }
    replaced = False
    for index, existing in enumerate(raw_pool):
        existing_source_id = str(existing.get("sourceId") or existing.get("candidateId") or "").strip()
        if existing_source_id == source_id:
            raw_pool[index] = row
            replaced = True
            break
    if not replaced:
        raw_pool.append(row)
    write_ndjson(source_pool_path, raw_pool)
    hydration_errors = _hydrate_source_artifacts(
        spec,
        topic_id,
        task_type,
        row,
        force=True,
    )
    if hydration_errors:
        for error in hydration_errors:
            print(f"[crawl fetch-source] FAIL: {error}", file=sys.stderr)
        return 1
    _load_topic_context(
        spec,
        topic_id,
        task_type,
        write_source_pool=True,
    )
    print(
        "[crawl fetch-source] OK: "
        f"spec={spec['spec_id']} topic={topic_id} source_id={source_id} task_type={task_type}"
    )
    return 0


def _compose_topic_command(
    spec: dict[str, Any],
    topic_id: str,
    selected_targets: list[str],
) -> tuple[list[str], list[str], dict[str, Any]]:
    prep_errors, topic, enrichment, approved_assets, selected_source_rows = _prepare_topic_for_compose(
        spec,
        topic_id,
    )
    if prep_errors:
        return prep_errors, [], {}
    targets = selected_targets or list(spec.get("target_envs", []))
    try:
        entities, post_rows, compose_summary = _compose_topic_outputs(
            spec,
            topic,
            enrichment,
            selected_source_rows,
            approved_assets,
            targets,
        )
    except ValueError as error:
        publish_dir = publish_topic_dir(topic_id)
        if publish_dir.exists():
            shutil.rmtree(publish_dir)
        return [str(error)], [], {}
    topic_errors, _, _ = _refresh_discovery_artifacts(spec)
    return [], topic_errors, {
        "topic": topic,
        "entities": entities,
        "postRows": post_rows,
        "targets": targets,
        "approvedAssets": approved_assets,
        "selectedSourceRows": selected_source_rows,
        "composeSummary": compose_summary,
    }


def _audit_topic_command(
    spec: dict[str, Any],
    topic_id: str,
) -> tuple[list[str], list[str], dict[str, Any]]:
    task_type = _resolve_topic_task_type(spec, topic_id)
    if not task_type:
        return [f"topic 不属于当前 spec: {topic_id}"], [], {}
    context_errors, topic = _load_topic_context(
        spec,
        topic_id,
        task_type,
        write_source_pool=False,
    )
    selected_source_rows = _selected_source_rows(topic)
    if not selected_source_rows:
        context_errors.append(f"topic {topic_id} 没有 retained 的真实来源，无法执行 audit")
    publish_dir = publish_topic_dir(topic_id)
    if not (publish_dir / "posts.ndjson").exists():
        context_errors.append(f"topic {topic_id} 缺少 compose 产物，无法执行 audit")
    if context_errors:
        return context_errors, [], {}
    try:
        audit_summary = _audit_topic_posts(spec, topic, selected_source_rows)
    except ValueError as error:
        return [str(error)], [], {}
    topic_errors, _, _ = _refresh_discovery_artifacts(spec)
    return [], topic_errors, {
        "topic": topic,
        "selectedSourceRows": selected_source_rows,
        "auditSummary": audit_summary,
    }


def handle_compose_topic(args) -> int:
    ensure_runtime_layout()
    if not args.dry_run:
        print("[crawl compose-topic] FAIL: 原型阶段只支持 --dry-run", file=sys.stderr)
        return 1
    selected_targets = [item.strip() for item in str(args.targets or "").split(",") if item.strip()]
    errors, spec, _ = _load_spec(args.spec, selected_targets)
    if errors:
        for error in errors:
            print(f"[crawl compose-topic] FAIL: {error}", file=sys.stderr)
        return 1
    topic_id = str(args.topic).strip()
    compose_errors, warnings, payload = _compose_topic_command(spec, topic_id, selected_targets)
    if compose_errors:
        for error in compose_errors:
            print(f"[crawl compose-topic] FAIL: {error}", file=sys.stderr)
        return 1
    for warning in warnings[:80]:
        print(f"[crawl compose-topic] WARN: {warning}", file=sys.stderr)
    topic = payload["topic"]
    print(
        "[crawl compose-topic] OK: "
        f"spec={spec['spec_id']} topic={topic_id} task_type={topic['taskType']} "
        f"retained_sources={len(payload['selectedSourceRows'])} assets={len(payload['approvedAssets'])} "
        f"posts={len(payload['postRows'])} targets={','.join(payload['targets'])}"
    )
    return 0


def handle_audit_topic(args) -> int:
    ensure_runtime_layout()
    errors, spec, _ = _load_spec(args.spec, [])
    if errors:
        for error in errors:
            print(f"[crawl audit-topic] FAIL: {error}", file=sys.stderr)
        return 1
    topic_id = str(args.topic).strip()
    audit_errors, warnings, payload = _audit_topic_command(spec, topic_id)
    if audit_errors:
        for error in audit_errors:
            print(f"[crawl audit-topic] FAIL: {error}", file=sys.stderr)
        return 1
    for warning in warnings[:80]:
        print(f"[crawl audit-topic] WARN: {warning}", file=sys.stderr)
    audit_summary = payload["auditSummary"]
    if str(audit_summary.get("overallStatus", "")).strip() != "approved":
        print(
            f"[crawl audit-topic] FAIL: topic {topic_id} 审核未通过 overall_score={audit_summary.get('overallScore')}",
            file=sys.stderr,
        )
        return 1
    print(
        "[crawl audit-topic] OK: "
        f"spec={spec['spec_id']} topic={topic_id} task_type={payload['topic']['taskType']} "
        f"review_count={audit_summary.get('reviewCount', 0)} "
        f"overall_score={audit_summary.get('overallScore', 0)}"
    )
    return 0


def handle_run_topic(args) -> int:
    ensure_runtime_layout()
    if not args.dry_run:
        print("[crawl run-topic] FAIL: 原型阶段只支持 --dry-run", file=sys.stderr)
        return 1
    selected_targets = [item.strip() for item in str(args.targets or "").split(",") if item.strip()]
    errors, spec, _ = _load_spec(args.spec, selected_targets)
    if errors:
        for error in errors:
            print(f"[crawl run-topic] FAIL: {error}", file=sys.stderr)
        return 1

    topic_id = str(args.topic).strip()
    compose_errors, compose_warnings, compose_payload = _compose_topic_command(
        spec,
        topic_id,
        selected_targets,
    )
    if compose_errors:
        for error in compose_errors:
            print(f"[crawl run-topic] FAIL: {error}", file=sys.stderr)
        return 1
    audit_errors, audit_warnings, audit_payload = _audit_topic_command(spec, topic_id)
    if audit_errors:
        for error in audit_errors:
            print(f"[crawl run-topic] FAIL: {error}", file=sys.stderr)
        return 1
    for error in (compose_warnings + audit_warnings)[:80]:
        print(f"[crawl run-topic] WARN: {error}", file=sys.stderr)

    print(
        "[crawl run-topic] OK: "
        f"spec={spec['spec_id']} topic={topic_id} task_type={compose_payload['topic']['taskType']} "
        f"retained_sources={len(compose_payload['selectedSourceRows'])} assets={len(compose_payload['approvedAssets'])} "
        f"posts={len(compose_payload['postRows'])} "
        f"targets={','.join(compose_payload['targets'])} "
        f"audit={audit_payload['auditSummary'].get('overallStatus', '')} "
        f"audit_score={audit_payload['auditSummary'].get('overallScore', 0)}"
    )
    return 0


def handle_pool_bootstrap(args) -> int:
    ensure_runtime_layout()
    errors, spec, spec_path = _load_spec(args.spec, [])
    if errors:
        for error in errors:
            print(f"[crawl pool-bootstrap] FAIL: {error}", file=sys.stderr)
        return 1

    from crawl_topic_pool import bootstrap_from_attractions_yaml, load_travel_url_seed_ndjson

    catalog_arg = str(getattr(args, "catalog", "") or "").strip()
    cref = str(spec.get("article_topic_catalog_ref") or "").strip()
    if catalog_arg:
        catalog_path = Path(catalog_arg)
        if not catalog_path.is_absolute():
            catalog_path = (Path.cwd() / catalog_path).resolve()
        else:
            catalog_path = catalog_path.resolve()
    elif cref:
        catalog_path = (RUNTIME_ROOT / cref).resolve()
    else:
        print(
            "[crawl pool-bootstrap] FAIL: 需要 --catalog 或 spec.article_topic_catalog_ref",
            file=sys.stderr,
        )
        return 1
    if not catalog_path.is_file():
        print(f"[crawl pool-bootstrap] FAIL: catalog 不存在 {catalog_path}", file=sys.stderr)
        return 1

    if catalog_path.suffix.lower() == ".ndjson":
        catalog = {"attractions": read_ndjson(catalog_path)}
    else:
        catalog = read_yaml(catalog_path)

    travel_seed_arg = str(getattr(args, "travel_seed", "") or "").strip()
    travel_by: dict[str, list[dict[str, Any]]]
    if travel_seed_arg:
        tsp = Path(travel_seed_arg)
        if not tsp.is_absolute():
            tsp = (Path.cwd() / tsp).resolve()
        else:
            tsp = tsp.resolve()
        travel_by = load_travel_url_seed_ndjson(tsp)
    else:
        travel_by = {}

    merge = bool(getattr(args, "merge", False))
    topics_arg = str(getattr(args, "topics", "") or "").strip()
    topic_filter = {t.strip() for t in topics_arg.split(",") if t.strip()} if topics_arg else None

    wiki_expand = str(getattr(args, "wiki_expand", "filtered") or "filtered").strip().lower()
    if wiki_expand not in {"none", "filtered", "full"}:
        print(
            f"[crawl pool-bootstrap] FAIL: wiki_expand 必须是 none|filtered|full，收到 {wiki_expand}",
            file=sys.stderr,
        )
        return 1

    bootstrap_from_attractions_yaml(
        spec,
        catalog,
        max_sources=int(getattr(args, "max_sources", 22)),
        wiki_expand=wiki_expand,
        wiki_link_budget=int(getattr(args, "wiki_link_budget", 40)),
        baike_link_budget=int(getattr(args, "baike_link_budget", 24)),
        wikivoyage_limit=int(getattr(args, "wikivoyage_limit", 12)),
        sleep_s=float(getattr(args, "sleep", 0.35)),
        skip_baike_scrape=bool(getattr(args, "skip_baike_scrape", False)),
        merge=merge,
        topic_filter=topic_filter,
        travel_seed_by_topic=travel_by,
    )
    print(
        "[crawl pool-bootstrap] OK: "
        f"spec={spec['spec_id']} catalog={catalog_path} merge={merge} wiki_expand={wiki_expand}",
        file=sys.stderr,
    )
    return 0


def handle_export_poi_topics(args) -> int:
    """将 Overpass JSON（elements）转为 article_topic_catalog_ref 可用的 NDJSON。"""
    in_path = Path(str(getattr(args, "input", "") or "").strip())
    out_path = Path(str(getattr(args, "output", "") or "").strip())
    if not in_path.is_absolute():
        in_path = (Path.cwd() / in_path).resolve()
    else:
        in_path = in_path.resolve()
    if not out_path.is_absolute():
        out_path = (Path.cwd() / out_path).resolve()
    else:
        out_path = out_path.resolve()
    if not in_path.is_file():
        print(f"[crawl export-poi-topics] FAIL: 输入不存在 {in_path}", file=sys.stderr)
        return 1
    data = read_json(in_path)
    elements = data.get("elements") or []
    rows: list[dict[str, Any]] = []
    prefix = str(getattr(args, "topic_id_prefix", "poi") or "poi").strip() or "poi"
    for el in elements:
        if not isinstance(el, dict):
            continue
        el_type = str(el.get("type") or "x").strip()
        el_id = el.get("id")
        if el_id is None:
            continue
        tags = el.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        name = str(tags.get("name:zh") or tags.get("name") or "").strip()
        if not name:
            continue
        tourism = str(tags.get("tourism") or "").strip()
        historic = str(tags.get("historic") or "").strip()
        amenity = str(tags.get("amenity") or "").strip()
        if not (tourism or historic or amenity in {"museum", "arts_centre"}):
            continue
        topic_id = f"{prefix}_{el_type}_{el_id}"
        rows.append(
            {
                "topic_id": topic_id,
                "name": name,
                "wiki_title": name,
                "baike_item": name,
            }
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_ndjson(out_path, rows)
    print(
        f"[crawl export-poi-topics] OK: wrote {len(rows)} rows -> {out_path}",
        file=sys.stderr,
    )
    return 0
