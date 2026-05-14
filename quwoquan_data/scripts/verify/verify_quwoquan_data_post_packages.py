#!/usr/bin/env python3
"""校验 quwoquan_data 的 topic publish package。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(os.getenv('QWQ_REPO_ROOT', Path(__file__).resolve().parents[3])).resolve()
DATA_ROOT = Path(os.getenv('QWQ_DATA_ROOT', REPO_ROOT / 'quwoquan_data')).resolve()
RUNTIME_ROOT = Path(os.getenv('QWQ_RUNTIME_ROOT', DATA_ROOT / 'runtime')).resolve()
PUBLISH_ROOT = RUNTIME_ROOT / 'publish'
RUNS_ROOT = RUNTIME_ROOT / 'runs'
ASSET_REF_RE = re.compile(r'asset://([A-Za-z0-9_.:-]+)')
PLACEHOLDER_TITLE_RE = re.compile(r'(公开样本|图片候选)\s*\d+$')
PLACEHOLDER_URL_RES = (
    re.compile(r'west_lake_(article|image|crawl_validation)_\d+', re.I),
    re.compile(r'west-lake-image', re.I),
    re.compile(r'mafengwo\.cn/i/[^/\d][^/]*$', re.I),
)
ARTICLE_TEMPLATE_PHRASES = (
    '为什么这个选题值得写',
    '正文叙事骨架',
    '先定主步行段',
    '热度高样本可直通',
    '正文至少保留一个“实体锚点”段',
    '正文至少保留一个"实体锚点"段',
    '端侧可以消费的原创 Markdown 成品',
    '文章任务',
    '图片任务',
    '来源页把重点落在',
    '补充判断时，可以继续盯住',
    '如果想把现场走顺，可以先盯住',
    '真实来源围绕',
    '这篇把',
    '适合想在半天到一天里',
)
ARTICLE_TRAVEL_KEYWORDS = (
    '西湖十景',
    '苏堤春晓',
    '三潭印月',
    '柳浪闻莺',
    '曲院风荷',
    '平湖秋月',
    '花港观鱼',
    '湖滨公园',
    '雷峰塔',
    '断桥',
    '苏堤',
    '白堤',
    '湖滨',
    '游船',
    '喝茶',
    '杭帮菜',
    '美食',
    '饭店',
    '南线',
    '东岸',
    '湖面',
    '西湖',
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def markdown_asset_refs(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(ASSET_REF_RE.findall(path.read_text(encoding='utf-8')))


def normalize_text(value: Any) -> str:
    return ' '.join(str(value or '').replace('\ufeff', '').split())


def strip_markdown_links(text: str) -> str:
    return re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)


def clean_markdown_line(text: str) -> str:
    value = normalize_text(strip_markdown_links(text))
    value = re.sub(r'^[#>*\-\d\.\s]+', '', value)
    return value.strip()


def extract_source_body_text(source_markdown: str) -> str:
    text = source_markdown.strip()
    if text.startswith('---'):
        parts = text.split('\n---', 1)
        if len(parts) == 2:
            text = parts[1]
    body_lines: list[str] = []
    for raw_line in text.splitlines():
        normalized = raw_line.strip()
        if re.match(r'^-\s*(source_id|candidate_id|url|source_url|fetched_at|round)\s*:', normalized):
            continue
        if re.match(r'^##\s*title\s*:', normalized, re.I):
            continue
        if re.match(r'^(title|summary|source_url|fetched_at|task_type)\s*:', normalized, re.I):
            continue
        body_lines.append(raw_line)
    return '\n'.join(body_lines).strip()


def has_valid_front_matter(markdown_text: str) -> bool:
    text = markdown_text.replace('\r\n', '\n')
    return text.startswith('---\n') and '\n---\n' in text[4:]


def extract_source_paragraphs(source_markdown: str) -> list[str]:
    body = extract_source_body_text(source_markdown)
    if not body:
        return []
    paragraphs: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r'\n\s*\n', body):
        cleaned = clean_markdown_line(chunk)
        if len(cleaned) < 45 or cleaned in seen:
            continue
        seen.add(cleaned)
        paragraphs.append(cleaned)
    return paragraphs


def extract_article_body_paragraphs(article_markdown: str) -> list[str]:
    text = article_markdown.strip()
    if text.startswith('---'):
        parts = text.split('\n---', 1)
        if len(parts) == 2:
            text = parts[1]
    paragraphs: list[str] = []
    for chunk in re.split(r'\n\s*\n', text):
        raw = chunk.strip()
        if not raw:
            continue
        if raw.startswith('#') or raw.startswith(':::') or raw.startswith('asset://') or raw.startswith('<!--'):
            continue
        cleaned = clean_markdown_line(raw)
        if cleaned in {'实体锚点', '来源锚点'}:
            continue
        if cleaned.startswith('- '):
            continue
        if len(cleaned) >= 32:
            paragraphs.append(cleaned)
    return paragraphs


def extract_article_sections(article_markdown: str) -> list[tuple[str, str]]:
    text = article_markdown.strip()
    if text.startswith('---'):
        parts = text.split('\n---', 1)
        if len(parts) == 2:
            text = parts[1]
    sections: list[tuple[str, str]] = []
    current_title = ''
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        if raw_line.startswith('## '):
            if current_title and current_lines:
                body = '\n'.join(current_lines).strip()
                if body:
                    sections.append((current_title, body))
            current_title = clean_markdown_line(raw_line)
            current_lines = []
            continue
        if current_title:
            current_lines.append(raw_line)
    if current_title and current_lines:
        body = '\n'.join(current_lines).strip()
        if body:
            sections.append((current_title, body))
    return [
        (title, body)
        for title, body in sections
        if title not in {'实体锚点', '来源锚点'}
    ]


def split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for chunk in re.split(r'[。！？!?]', normalize_text(text)):
        cleaned = chunk.strip(' ，、；;:：')
        if len(cleaned) >= 10:
            sentences.append(cleaned)
    return sentences


def source_anchor_phrases(text: str, *, limit: int = 3) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for sentence in split_sentences(text):
        clauses = [
            part.strip()
            for part in re.split(r'[，、；;:：]', sentence)
            if len(part.strip()) >= 8
        ]
        candidate_parts = clauses or [sentence]
        for part in candidate_parts:
            snippet = part[:28].strip()
            if len(snippet) < 8 or snippet in seen:
                continue
            seen.add(snippet)
            phrases.append(snippet)
            if len(phrases) >= limit:
                return phrases
    return phrases


def travel_tokens(text: str, *, limit: int = 6) -> list[str]:
    normalized = normalize_text(text)
    hits: list[tuple[int, int, str]] = []
    for keyword in ARTICLE_TRAVEL_KEYWORDS:
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


def looks_like_placeholder_url(url: str) -> bool:
    normalized = str(url or '').strip()
    if not normalized:
        return True
    return any(pattern.search(normalized) for pattern in PLACEHOLDER_URL_RES)


def article_source_overlap(article_text: str, manifest: dict[str, Any]) -> int:
    spec_id = str(manifest.get('specId', '')).strip()
    topic_id = str(manifest.get('topicId', '')).strip()
    if not spec_id or not topic_id:
        return 0
    runs_topic_dir = RUNS_ROOT / spec_id / 'topics' / topic_id / 'pages'
    selected_source_ids = [
        str(item).strip()
        for item in manifest.get('selectedSourceIds', [])
        if str(item).strip()
    ]
    article_normalized = normalize_text(article_text)
    hit_count = 0
    for source_id in selected_source_ids:
        source_md_path = runs_topic_dir / source_id / 'source.md'
        if not source_md_path.exists():
            continue
        for paragraph in extract_source_paragraphs(source_md_path.read_text(encoding='utf-8')):
            if any(phrase in article_normalized for phrase in source_anchor_phrases(paragraph)):
                hit_count += 1
                break
    return hit_count


def article_source_phrase_hits_by_source(article_text: str, manifest: dict[str, Any]) -> dict[str, int]:
    spec_id = str(manifest.get('specId', '')).strip()
    topic_id = str(manifest.get('topicId', '')).strip()
    if not spec_id or not topic_id:
        return {}
    runs_topic_dir = RUNS_ROOT / spec_id / 'topics' / topic_id / 'pages'
    selected_source_ids = [
        str(item).strip()
        for item in manifest.get('selectedSourceIds', [])
        if str(item).strip()
    ]
    article_normalized = normalize_text(article_text)
    hit_map: dict[str, set[str]] = {}
    for source_id in selected_source_ids:
        source_hits: set[str] = set()
        source_md_path = runs_topic_dir / source_id / 'source.md'
        if not source_md_path.exists():
            continue
        for paragraph in extract_source_paragraphs(source_md_path.read_text(encoding='utf-8')):
            seen: set[str] = set()
            for phrase in source_anchor_phrases(paragraph, limit=4) + travel_tokens(paragraph, limit=4):
                if phrase in seen:
                    continue
                seen.add(phrase)
                if phrase in article_normalized:
                    source_hits.add(phrase)
        hit_map[source_id] = source_hits
    return {source_id: len(hits) for source_id, hits in hit_map.items()}


def article_source_phrase_hits(article_text: str, manifest: dict[str, Any]) -> int:
    return sum(article_source_phrase_hits_by_source(article_text, manifest).values())


def article_section_has_source_support(section_text: str, manifest: dict[str, Any]) -> bool:
    spec_id = str(manifest.get('specId', '')).strip()
    topic_id = str(manifest.get('topicId', '')).strip()
    if not spec_id or not topic_id:
        return False
    runs_topic_dir = RUNS_ROOT / spec_id / 'topics' / topic_id / 'pages'
    selected_source_ids = [
        str(item).strip()
        for item in manifest.get('selectedSourceIds', [])
        if str(item).strip()
    ]
    section_normalized = normalize_text(section_text)
    for source_id in selected_source_ids:
        source_md_path = runs_topic_dir / source_id / 'source.md'
        if not source_md_path.exists():
            continue
        for paragraph in extract_source_paragraphs(source_md_path.read_text(encoding='utf-8')):
            for phrase in source_anchor_phrases(paragraph, limit=4) + travel_tokens(paragraph, limit=4):
                if phrase and phrase in section_normalized:
                    return True
    return False


def required_article_overlap_hits(manifest: dict[str, Any]) -> int:
    selected_source_ids = [
        str(item).strip()
        for item in manifest.get('selectedSourceIds', [])
        if str(item).strip()
    ]
    if not selected_source_ids:
        return 2
    return min(2, len(selected_source_ids))


def required_article_phrase_hits(manifest: dict[str, Any]) -> int:
    selected_source_ids = [
        str(item).strip()
        for item in manifest.get('selectedSourceIds', [])
        if str(item).strip()
    ]
    if len(selected_source_ids) <= 1:
        return 4
    return len(selected_source_ids) + 1


def expected_post_rows(topic_dir: Path) -> dict[str, dict[str, Any]]:
    rows = read_ndjson(topic_dir / 'posts.ndjson')
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        post_payload = row.get('post_payload')
        if isinstance(post_payload, dict):
            source_post_id = str(post_payload.get('sourcePostId', '')).strip()
            if source_post_id:
                by_id[source_post_id] = row
    return by_id


def validate_article_package(post_dir: Path, post: dict[str, Any], manifest: dict[str, Any], errors: list[str]) -> None:
    article_path = post_dir / 'article.md'
    if not article_path.exists():
        errors.append(f'{post_dir}: article package 缺少 article.md')
        return
    article_text = article_path.read_text(encoding='utf-8')
    if not has_valid_front_matter(article_text):
        errors.append(f'{post_dir}: article.md front matter 非法')
    payload = post.get('post_payload', {})
    if 'articleDocument' in payload:
        errors.append(f'{post_dir}: article payload 不得包含 articleDocument')
    for field in ('articleMarkdown', 'articleMarkdownVersion', 'articleRenderProfile'):
        if field not in payload:
            errors.append(f'{post_dir}: article payload 缺少 {field}')
    if payload.get('articleMarkdown') != article_text:
        errors.append(f'{post_dir}: post.json.articleMarkdown 与 article.md 不一致')
    if 'articleAssetManifest' in payload:
        errors.append(f'{post_dir}: article payload 不应重复内嵌 articleAssetManifest')
    manifest_ids = {str(row.get('assetId', '')) for row in manifest.get('assets', [])}
    missing = markdown_asset_refs(article_path) - manifest_ids
    if missing:
        errors.append(f'{post_dir}: article.md 引用未登记素材 {sorted(missing)}')
    if 'cover_asset_id:' not in article_text:
        errors.append(f'{post_dir}: article.md front matter 缺少 cover_asset_id')
    if 'entity_refs:' in article_text:
        errors.append(f'{post_dir}: article.md front matter 不应重复 entity_refs')
    if 'source_urls:' in article_text:
        errors.append(f'{post_dir}: article.md front matter 不应重复 source_urls')
    if '## 实体锚点' not in article_text:
        errors.append(f'{post_dir}: article.md 缺少正文实体锚点段')
    for forbidden in ('source_url:', 'fetched_at:', 'task_type:'):
        if forbidden in article_text:
            errors.append(f'{post_dir}: article.md 正文混入来源元数据字段 {forbidden}')
            break
    for phrase in ARTICLE_TEMPLATE_PHRASES:
        if phrase in article_text:
            errors.append(f'{post_dir}: article.md 包含模板化固定文案 {phrase}')
            break
    body_paragraphs = extract_article_body_paragraphs(article_text)
    if len(body_paragraphs) < 6:
        errors.append(f'{post_dir}: article.md 正文段落不足，当前 {len(body_paragraphs)} 段，要求至少 6 段')
    if sum(len(paragraph) for paragraph in body_paragraphs) < 520:
        errors.append(f'{post_dir}: article.md 正文篇幅不足，要求至少 520 字')
    unsupported_sections = [
        title
        for title, body in extract_article_sections(article_text)
        if not article_section_has_source_support(body, manifest)
    ]
    if unsupported_sections:
        errors.append(f'{post_dir}: article.md 二级段落缺少来源事实支撑 {unsupported_sections}')
    overlap_hits = article_source_overlap(article_text, manifest)
    required_hits = required_article_overlap_hits(manifest)
    phrase_hits_by_source = article_source_phrase_hits_by_source(article_text, manifest)
    phrase_hits = sum(phrase_hits_by_source.values())
    required_phrase_hits = required_article_phrase_hits(manifest)
    source_without_hits = sorted(source_id for source_id, count in phrase_hits_by_source.items() if count <= 0)
    if source_without_hits:
        errors.append(f'{post_dir}: article.md 未覆盖所有 retained 来源锚点，缺失来源 {source_without_hits}')
    if overlap_hits < required_hits and phrase_hits < required_phrase_hits:
        errors.append(
            f'{post_dir}: article.md 与 source.md 的真实锚点关联不足，段落命中 {overlap_hits}/{required_hits}，短语命中 {phrase_hits}/{required_phrase_hits}'
        )


def validate_image_package(post_dir: Path, post: dict[str, Any], manifest: dict[str, Any], errors: list[str]) -> None:
    gallery_path = post_dir / 'gallery.md'
    if not gallery_path.exists():
        errors.append(f'{post_dir}: image package 缺少 gallery.md')
        return
    gallery_text = gallery_path.read_text(encoding='utf-8')
    if not has_valid_front_matter(gallery_text):
        errors.append(f'{post_dir}: gallery.md front matter 非法')
    payload = post.get('post_payload', {})
    manifest_ids = {str(row.get('assetId', '')) for row in manifest.get('assets', [])}
    missing = markdown_asset_refs(gallery_path) - manifest_ids
    if missing:
        errors.append(f'{post_dir}: gallery.md 引用未登记素材 {sorted(missing)}')
    if 'cover_asset_id:' not in gallery_text:
        errors.append(f'{post_dir}: gallery.md front matter 缺少 cover_asset_id')
    if 'entity_refs:' in gallery_text:
        errors.append(f'{post_dir}: gallery.md front matter 不应重复 entity_refs')
    object_keys = {str(row.get('objectKey', '')) for row in manifest.get('assets', [])}
    media_urls = payload.get('mediaUrls', [])
    if not isinstance(media_urls, list) or not media_urls:
        errors.append(f'{post_dir}: image payload 缺少 mediaUrls')
    for url in media_urls:
        if str(url) not in object_keys:
            errors.append(f'{post_dir}: mediaUrl {url} 不来自 manifest.objectKey')
    cover_url = str(payload.get('coverUrl', '')).strip()
    if cover_url and cover_url not in object_keys:
        errors.append(f'{post_dir}: coverUrl {cover_url} 不来自 manifest.objectKey')


def validate_review_artifact(post_dir: Path, manifest: dict[str, Any], content_type: str, errors: list[str]) -> None:
    review_path = post_dir / 'review.json'
    if not review_path.exists():
        errors.append(f'{post_dir}: 缺少 review.json')
        return
    review = read_json(review_path)
    audit = manifest.get('qualityAudit')
    if not isinstance(audit, dict):
        errors.append(f'{post_dir}: manifest 缺少 qualityAudit')
    else:
        if str(audit.get('role', '')).strip() != 'audit':
            errors.append(f'{post_dir}: manifest.qualityAudit.role 必须是 audit')
        if str(audit.get('reviewPath', '')).strip() != 'review.json':
            errors.append(f'{post_dir}: manifest.qualityAudit.reviewPath 必须是 review.json')
        if str(audit.get('overallStatus', '')).strip() != 'approved':
            errors.append(f'{post_dir}: manifest.qualityAudit.overallStatus 必须是 approved')
        if int(audit.get('overallScore') or 0) <= 0:
            errors.append(f'{post_dir}: manifest.qualityAudit.overallScore 必须是正整数')
    if str(review.get('role', '')).strip() != 'audit':
        errors.append(f'{post_dir}: review.role 必须是 audit')
    if str(review.get('taskType', '')).strip() != content_type:
        errors.append(f'{post_dir}: review.taskType 必须与 contentType 一致')
    if str(review.get('overallStatus', '')).strip() != 'approved':
        errors.append(f'{post_dir}: review.overallStatus 必须是 approved')
    if int(review.get('overallScore') or 0) < 70:
        errors.append(f'{post_dir}: review.overallScore 必须至少 70')
    checks = review.get('checks')
    if not isinstance(checks, dict):
        errors.append(f'{post_dir}: review 缺少 checks')
        return
    if content_type == 'article':
        required = (
            'factualCoverage',
            'readerFacingTone',
            'specificity',
            'redundancy',
            'sourceGrounding',
        )
    else:
        required = (
            'imageQualityScore',
            'downloadVerified',
            'rightsReview',
            'watermarkReview',
            'narrativeFit',
        )
    for key in required:
        item = checks.get(key)
        if not isinstance(item, dict):
            errors.append(f'{post_dir}: review.checks 缺少 {key}')
            continue
        if not bool(item.get('pass')):
            errors.append(f'{post_dir}: review.checks.{key} 未通过')


def validate_package(post_dir: Path, expected_row: dict[str, Any], errors: list[str]) -> None:
    post_json = post_dir / 'post.json'
    manifest_json = post_dir / 'manifest.json'
    if not post_json.exists():
        errors.append(f'{post_dir}: 缺少 post.json')
        return
    if not manifest_json.exists():
        errors.append(f'{post_dir}: 缺少 manifest.json')
        return
    post = read_json(post_json)
    manifest = read_json(manifest_json)
    if post != expected_row:
        errors.append(f'{post_dir}: post.json 与 posts.ndjson 对应行不一致')
    payload = post.get('post_payload', {})
    content_type = str(payload.get('contentType') or payload.get('type') or manifest.get('contentType'))
    if str(manifest.get('schemaVersion', '')) not in {'quwoquan_data.package_manifest', '2'}:
        errors.append(f"{post_dir}: manifest.schemaVersion 必须是 quwoquan_data.package_manifest（兼容旧值 2）")
    compliance = manifest.get('compliance')
    if not isinstance(compliance, dict):
        errors.append(f'{post_dir}: manifest 缺少 compliance')
    elif str(compliance.get('overallStatus', '')).strip() != 'approved':
        errors.append(f'{post_dir}: manifest.compliance.overallStatus 必须是 approved')
    metadata = manifest.get('contentMetadata')
    if not isinstance(metadata, dict):
        errors.append(f'{post_dir}: manifest 缺少 contentMetadata')
    else:
        for field in ('title', 'summary', 'coverAssetId'):
            if not str(metadata.get(field, '')).strip():
                errors.append(f'{post_dir}: manifest.contentMetadata 缺少 {field}')
    for field in ('entityRefs', 'sourceUrls'):
        value = manifest.get(field)
        if not isinstance(value, list) or not any(str(item).strip() for item in value):
            errors.append(f'{post_dir}: manifest 缺少非空 {field}')
    source_urls = manifest.get('sourceUrls', [])
    if isinstance(source_urls, list):
        for source_url in source_urls:
            if looks_like_placeholder_url(str(source_url)):
                errors.append(f'{post_dir}: manifest.sourceUrls 包含占位 URL {source_url}')
                break
    selected_source_ids = manifest.get('selectedSourceIds', [])
    if not isinstance(selected_source_ids, list) or not any(str(item).strip() for item in selected_source_ids):
        errors.append(f'{post_dir}: manifest 缺少 selectedSourceIds')
    manifest_ids: set[str] = set()
    for asset in manifest.get('assets', []):
        asset_id = str(asset.get('assetId', '')).strip()
        if not asset_id:
            errors.append(f'{post_dir}: manifest.assets 存在空 assetId')
            continue
        manifest_ids.add(asset_id)
        for field in ('objectKey', 'sourceUrl', 'sha256', 'mimeType', 'downloadStatus'):
            if not str(asset.get(field, '')).strip():
                errors.append(f'{post_dir}: asset {asset_id} 缺少 {field}')
        if content_type == 'image':
            if int(asset.get('imageQualityScore') or 0) <= 0:
                errors.append(f'{post_dir}: asset {asset_id} 缺少非零 imageQualityScore')
            breakdown = asset.get('imageQualityBreakdown') or {}
            if not isinstance(breakdown, dict) or not any(int(value or 0) > 0 for value in breakdown.values()):
                errors.append(f'{post_dir}: asset {asset_id} 缺少有效 imageQualityBreakdown')
        if str(asset.get('publishEligibility', '')).strip() != 'approved':
            errors.append(f'{post_dir}: asset {asset_id} publishEligibility 必须是 approved')
        if str(asset.get('rightsStatus', '')).strip() != 'clear':
            errors.append(f'{post_dir}: asset {asset_id} rightsStatus 必须是 clear')
        if str(asset.get('watermarkStatus', '')).strip() != 'clean':
            errors.append(f'{post_dir}: asset {asset_id} watermarkStatus 必须是 clean')
        if not (post_dir / 'images' / f'{asset_id}.ref').exists():
            errors.append(f'{post_dir}: images/{asset_id}.ref 不存在')
        package_path = str(asset.get('packagePath', '')).strip()
        if not package_path:
            errors.append(f'{post_dir}: asset {asset_id} 缺少 packagePath')
        else:
            package_file = post_dir / package_path
            if not package_file.exists():
                errors.append(f'{post_dir}: {package_path} 不存在')
            elif package_file.stat().st_size <= 0:
                errors.append(f'{post_dir}: {package_path} 为空文件')
    image_refs = {path.stem for path in (post_dir / 'images').glob('*.ref')} if (post_dir / 'images').exists() else set()
    extras = sorted(image_refs - manifest_ids)
    if extras:
        errors.append(f'{post_dir}: images/ 存在 manifest 未登记素材 {extras}')
    validate_review_artifact(post_dir, manifest, content_type, errors)
    if content_type == 'article':
        validate_article_package(post_dir, post, manifest, errors)
    elif content_type == 'image':
        validate_image_package(post_dir, post, manifest, errors)
    else:
        errors.append(f'{post_dir}: 未支持 contentType={content_type}')


def main() -> int:
    errors: list[str] = []
    if not PUBLISH_ROOT.exists():
        print('OK: quwoquan_data post package gate (no publish output)')
        return 0
    for topic_dir in sorted(path for path in PUBLISH_ROOT.iterdir() if path.is_dir()):
        posts_dir = topic_dir / 'posts'
        rows_by_id = expected_post_rows(topic_dir)
        expected_ids = set(rows_by_id)
        actual_ids = {path.name for path in posts_dir.iterdir() if path.is_dir()} if posts_dir.exists() else set()
        if expected_ids != actual_ids:
            missing = sorted(expected_ids - actual_ids)
            extras = sorted(actual_ids - expected_ids)
            if missing:
                errors.append(f'{topic_dir}: posts.ndjson 缺少 package 目录 {missing}')
            if extras:
                errors.append(f'{topic_dir}: posts/ 存在多余目录 {extras}')
        for post_id in sorted(expected_ids):
            validate_package(posts_dir / post_id, rows_by_id[post_id], errors)
    if errors:
        print('FAIL: quwoquan_data post package gate')
        for error in errors[:120]:
            print(f'- {error}')
        if len(errors) > 120:
            print(f'... and {len(errors) - 120} more')
        return 1
    print('OK: quwoquan_data post package gate')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
