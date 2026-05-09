#!/usr/bin/env python3
"""校验 quwoquan_data 原始来源与可发布 topic 的真实性链路。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(os.getenv('QWQ_REPO_ROOT', Path(__file__).resolve().parents[1])).resolve()
DATA_ROOT = Path(os.getenv('QWQ_DATA_ROOT', REPO_ROOT / 'quwoquan_data')).resolve()
RUNTIME_ROOT = Path(os.getenv('QWQ_RUNTIME_ROOT', DATA_ROOT / 'runtime')).resolve()
RUNS_ROOT = RUNTIME_ROOT / 'runs'
DOWNLOAD_SOURCE_ROOT = RUNTIME_ROOT / 'downloads' / 'sources'
DOWNLOAD_IMAGE_ROOT = RUNTIME_ROOT / 'downloads' / 'images'
PLACEHOLDER_TITLE_RE = re.compile(r'(公开样本|图片候选)\s*\d+$')
PLACEHOLDER_URL_RES = (
    re.compile(r'west_lake_(article|image|crawl_validation)_\d+', re.I),
    re.compile(r'west-lake-image', re.I),
    re.compile(r'mafengwo\.cn/i/[^/\d][^/]*$', re.I),
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def normalize_text(value: Any) -> str:
    return ' '.join(str(value or '').replace('\ufeff', '').split())


def strip_markdown_links(text: str) -> str:
    return re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)


def clean_markdown_line(text: str) -> str:
    value = normalize_text(strip_markdown_links(text))
    value = re.sub(r'^[#>*\-\d\.\s]+', '', value)
    return value.strip()


def extract_html_text(source: str) -> str:
    text = re.sub(r'<script[\s\S]*?</script>', ' ', source, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', ' ', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    return normalize_text(text)


def extract_source_body(source_markdown: str) -> str:
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


def looks_like_placeholder_url(url: str) -> bool:
    normalized = str(url or '').strip()
    if not normalized:
        return True
    return any(pattern.search(normalized) for pattern in PLACEHOLDER_URL_RES)


def validate_download_sources(errors: list[str]) -> None:
    if not DOWNLOAD_SOURCE_ROOT.exists():
        return
    for page_html in sorted(DOWNLOAD_SOURCE_ROOT.glob('*/*/*/page.html')):
        html_text = extract_html_text(page_html.read_text(encoding='utf-8'))
        if len(html_text) < 120:
            errors.append(f'{page_html}: runtime downloads 中的 page.html 为空壳')
    if not DOWNLOAD_IMAGE_ROOT.exists():
        return
    for image_path in sorted(DOWNLOAD_IMAGE_ROOT.glob('*/*/*/*')):
        if image_path.is_file() and image_path.stat().st_size <= 0:
            errors.append(f'{image_path}: runtime downloads 中存在空图片文件')


def validate_publishable_runs(errors: list[str]) -> None:
    if not RUNS_ROOT.exists():
        return
    for spec_dir in sorted(path for path in RUNS_ROOT.iterdir() if path.is_dir()):
        topic_tasks_path = spec_dir / 'topic_tasks.ndjson'
        for row in read_ndjson(topic_tasks_path):
            publish_ready = bool(row.get('publishReady'))
            post_count = int(row.get('postCount') or 0)
            if not publish_ready and post_count <= 0:
                continue
            topic_id = str(row.get('topicId', '')).strip()
            topic_dir = spec_dir / 'topics' / topic_id
            source_pool_path = topic_dir / 'source_pool.ndjson'
            for index, source_row in enumerate(read_ndjson(source_pool_path), start=1):
                url = str(source_row.get('sourceUrl', '')).strip()
                title = str(source_row.get('title', '')).strip()
                snippet = normalize_text(source_row.get('snippet', ''))
                if looks_like_placeholder_url(url):
                    errors.append(f'{source_pool_path}:{index}: publishable topic 含占位 URL {url}')
                if PLACEHOLDER_TITLE_RE.search(title):
                    errors.append(f'{source_pool_path}:{index}: publishable topic 含占位标题 {title}')
                if not snippet:
                    errors.append(f'{source_pool_path}:{index}: publishable topic snippet 为空')
                if row.get('taskType') == 'image':
                    score = int(source_row.get('imageQualityScore') or 0)
                    breakdown = source_row.get('imageQualityBreakdown') or {}
                    if score <= 0:
                        errors.append(f'{source_pool_path}:{index}: image topic 缺少非零 imageQualityScore')
                    if not isinstance(breakdown, dict) or not any(int(value or 0) > 0 for value in breakdown.values()):
                        errors.append(f'{source_pool_path}:{index}: image topic 缺少有效 imageQualityBreakdown')
            for source_md in sorted(topic_dir.glob('pages/*/source.md')):
                source_text = source_md.read_text(encoding='utf-8')
                if not has_valid_front_matter(source_text):
                    errors.append(f'{source_md}: source.md front matter 非法')
                body = normalize_text(extract_source_body(source_text))
                if len(body) < 240 and row.get('taskType') == 'article':
                    errors.append(f'{source_md}: publishable article topic 的 source.md 正文过短')
            for page_html in sorted(topic_dir.glob('pages/*/page.html')):
                html_text = extract_html_text(page_html.read_text(encoding='utf-8'))
                if len(html_text) < 240 and row.get('taskType') == 'article':
                    errors.append(f'{page_html}: publishable article topic 的 page.html 为空壳')
            for asset_manifest in sorted(topic_dir.glob('pages/*/asset_manifest.json')):
                payload = read_json(asset_manifest)
                for asset in payload.get('assets', []):
                    if not isinstance(asset, dict):
                        continue
                    local_path = str(asset.get('localPath', '')).strip()
                    if not local_path:
                        errors.append(f'{asset_manifest}: asset 缺少 localPath')
                        continue
                    image_path = RUNTIME_ROOT / local_path
                    if not image_path.exists():
                        errors.append(f'{asset_manifest}: 缺少真实下载文件 {local_path}')
                        continue
                    if image_path.stat().st_size <= 0:
                        errors.append(f'{asset_manifest}: 下载文件为空 {local_path}')
                    if row.get('taskType') == 'image':
                        if int(asset.get('imageQualityScore') or 0) <= 0:
                            errors.append(f'{asset_manifest}: asset {asset.get("assetId", "")} 缺少非零 imageQualityScore')
                        breakdown = asset.get('imageQualityBreakdown') or {}
                        if not isinstance(breakdown, dict) or not any(int(value or 0) > 0 for value in breakdown.values()):
                            errors.append(f'{asset_manifest}: asset {asset.get("assetId", "")} 缺少有效 imageQualityBreakdown')


def main() -> int:
    errors: list[str] = []
    validate_download_sources(errors)
    validate_publishable_runs(errors)
    if errors:
        print('FAIL: quwoquan_data source authenticity gate')
        for error in errors[:120]:
            print(f'- {error}')
        if len(errors) > 120:
            print(f'... and {len(errors) - 120} more')
        return 1
    print('OK: quwoquan_data source authenticity gate')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
