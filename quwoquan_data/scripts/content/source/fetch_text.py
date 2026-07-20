"""Source text extraction and page-layout parsing."""
from __future__ import annotations

import html as html_lib
from html.parser import HTMLParser
import hashlib
import http.client
import json
import re
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

from core.runtime_policy import active_runtime_policy
from governance.coverage.source_registry import resolve_travel_source_runtime
from content.source.html_text import (
    _html_meta_plain_text,
    _html_to_plain_text,
    _html_to_plain_text_with_inline_images,
    _join_unique_text_chunks,
)

# Wikimedia/多数公共源要求 User-Agent 含 contact，否则触发严格限流(429)。
_USER_AGENT = (
    "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"
)
_RUNTIME_POLICY = active_runtime_policy()
DOWNLOAD_TEXT_TIMEOUT_SECONDS = _RUNTIME_POLICY.download_text_timeout_seconds
DOWNLOAD_BYTES_TIMEOUT_SECONDS = _RUNTIME_POLICY.download_bytes_timeout_seconds
DOWNLOAD_CURL_RETRIES = _RUNTIME_POLICY.curl_retries
SUPPORTED_TEXT_EXTRACTORS: frozenset[str] = frozenset(
    {
        "wikipedia_api",
        "baidu_baike_html",
        "toutiao_baike_html",
        "qunar_html",
        "static_official_html",
        "generic_html",
    }
)


def _curl_get_text(url: str, *, timeout: int = DOWNLOAD_TEXT_TIMEOUT_SECONDS) -> str:
    proc = subprocess.run(
        [
            "curl", "-sS", "-L", "-A", _USER_AGENT,
            "--retry", str(DOWNLOAD_CURL_RETRIES),
            "--retry-delay", str(_RUNTIME_POLICY.curl_retry_delay_seconds),
            "--retry-all-errors",
            "--max-time", str(timeout),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"curl exit {proc.returncode}")
    return proc.stdout


def _mediawiki_extmeta_value(meta: Mapping[str, Any], key: str) -> str:
    value = meta.get(key)
    if isinstance(value, Mapping):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def _mediawiki_clean_meta_text(value: str) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _wikipedia_api_plaintext(url: str) -> str:
    from content.source.mediawiki_page import fetch_mediawiki_page_bundle_for_url

    bundle = fetch_mediawiki_page_bundle_for_url(url)
    return bundle.rendered_text if bundle is not None else ""






# P3 三类解耦：来源页内联视频检测（文章类含视频则放弃——不把视频内容强行图文化）。
# 命中 <video>/<source type=video> 原生视频标签，或主流视频站点的 <iframe>/<embed> 嵌入。








def _baike_extractor_source_kind(extractor: str) -> str:
    return {
        "baidu_baike_html": "home_baidu_baike",
        "toutiao_baike_html": "home_toutiao_baike",
    }.get(extractor, extractor)


def _baike_layout_and_text(
    html_bytes: bytes, url: str, *, extractor: str
) -> tuple[str, dict[str, Any]]:
    """HTML 百科结构前端：页面 → 统一 IR + 从 IR 渲染的正文。

    禁止静默降级纯文本：解析失败返回空文本 + `parseStatus=rejected` 的 IR
    （含结构化 rejectReason），由质量门按真实正文快照裁决 retained/rejected。
    """
    from content.source.baike_layout import parse_baike_layout, render_layout_markdown

    body = html_bytes
    if not body:
        try:
            body = _curl_get_text(url).encode("utf-8")
        except Exception:
            body = b""
    layout = parse_baike_layout(
        body,
        source_kind=_baike_extractor_source_kind(extractor),
        extractor=extractor,
    )
    if layout.get("parseStatus") != "ok":
        return "", layout
    return render_layout_markdown(layout)[:50000], layout


def _toutiao_baike_layout_and_text(
    html_bytes: bytes,
    url: str,
) -> tuple[str, dict[str, Any]]:
    """今日头条百科专用 DOM extractor；身份仍由 toutiao_baike 严格契约校验。"""
    structured_text, layout = _baike_layout_and_text(
        html_bytes,
        url,
        extractor="toutiao_baike_html",
    )
    html = html_bytes.decode("utf-8", errors="replace")
    dom_text, _inline_images = _html_to_plain_text_with_inline_images(html, url)
    dom_text = dom_text.strip()
    if len(dom_text) > len(structured_text):
        layout = {
            **layout,
            "parseStatus": "ok",
            "sourceKind": "home_toutiao_baike",
            "extractor": "toutiao_baike_html",
            "extractionMode": "toutiao_dom",
        }
        return dom_text[:50000], layout
    return structured_text[:50000], layout


def _baidu_baike_layout_and_text(
    html_bytes: bytes,
    url: str,
) -> tuple[str, dict[str, Any]]:
    """百度百科公开词条 DOM extractor；只作事实引用，不抓取站内图片。"""
    raw = html_bytes.decode("utf-8", errors="replace")
    text = _html_to_plain_text(raw, url).strip()[:50000]
    return text, {
        "parseStatus": "ok" if text else "rejected",
        "sourceKind": "home_baidu_baike",
        "extractor": "baidu_baike_html",
        "extractionMode": "baidu_dom",
        **({} if text else {"rejectReason": "empty_dom_text"}),
    }




def _ems517_json_payload(url: str, *, raw_text: str | None = None) -> dict[str, object] | None:
    try:
        raw = raw_text if raw_text is not None else _curl_get_text(url)
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("code") or 0) != 0:
        return None
    return payload


def _ems517_record_plaintext(record: dict[str, object]) -> str:
    chunks: list[str] = []
    for key in ("title", "name", "titleEn", "subtitle", "cateName", "columnName", "intro", "note"):
        value = str(record.get(key) or "").strip()
        if value:
            chunks.append(value)
    content = str(record.get("content") or "").strip()
    if content:
        chunks.append(_html_to_plain_text(content))
    ext_button = str(record.get("ext1value") or "").strip()
    if ext_button and "http" not in ext_button.lower():
        chunks.append(ext_button)
    return _join_unique_text_chunks(chunks)


def _ems517_payload_plaintext(payload: dict[str, object]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        records = data.get("records")
        if isinstance(records, list):
            return _join_unique_text_chunks(
                [
                    _ems517_record_plaintext(record)
                    for record in records[:5]
                    if isinstance(record, dict)
                ]
            )
        return _ems517_record_plaintext(data)
    if isinstance(data, list):
        return _join_unique_text_chunks(
            [_ems517_record_plaintext(record) for record in data[:5] if isinstance(record, dict)]
        )
    return ""


def _ems517_api_plaintext(url: str, *, raw_text: str | None = None) -> str:
    payload = _ems517_json_payload(url, raw_text=raw_text)
    if payload is None:
        return ""
    return _ems517_payload_plaintext(payload)[:50000]


def _ems517_shell_plaintext(url: str, html: str) -> str:
    parsed = urllib.parse.urlparse(url)
    api_base = urllib.parse.urljoin(f"{parsed.scheme}://{parsed.netloc}", "/new_api/")
    query = urllib.parse.parse_qs(parsed.query)
    chunks: list[str] = []

    if query.get("id"):
        article_id = str(query["id"][0]).strip()
        if article_id:
            chunks.append(_ems517_api_plaintext(urllib.parse.urljoin(api_base, f"api/article/{article_id}")))

    if parsed.path.startswith("/new/visitor"):
        for category_id in ("31", "33", "34", "94"):
            chunks.append(_ems517_api_plaintext(urllib.parse.urljoin(api_base, f"api/category/{category_id}")))
        category_payload = _ems517_json_payload(urllib.parse.urljoin(api_base, "api/category/31"))
        root_item_id = ""
        if category_payload and isinstance(category_payload.get("data"), dict):
            root_item_id = str(category_payload["data"].get("itemId") or "").strip()
        if root_item_id:
            chunks.append(
                _ems517_api_plaintext(
                    urllib.parse.urljoin(
                        api_base,
                        f"api/notice/list?page=1&limit=3&itemId={root_item_id}",
                    )
                )
            )
            chunks.append(
                _ems517_api_plaintext(
                    urllib.parse.urljoin(
                        api_base,
                        f"api/article/list?page=1&limit=3&itemId={root_item_id}",
                    )
                )
            )

    joined = _join_unique_text_chunks(chunks)
    if joined:
        return joined[:50000]
    return _html_to_plain_text(html)[:50000]


def _qunar_html_plaintext(html_bytes: bytes, url: str = "") -> str:
    raw = html_bytes.decode("utf-8", errors="replace")
    return _html_to_plain_text(raw, url)[:50000]


def _qunar_html_with_inline_images(
    html_bytes: bytes, url: str = ""
) -> tuple[str, list[dict[str, str]]]:
    raw = html_bytes.decode("utf-8", errors="replace")
    text, imgs = _html_to_plain_text_with_inline_images(raw, url)
    return text[:50000], imgs


def _flatten_json_strings(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        if (
            len(text) >= 4
            and re.search(r"[\u4e00-\u9fff]", text)
            and not re.search(r"[\u3040-\u30ff\uac00-\ud7af]", text)
        ):
            return [text]
        return []
    if isinstance(value, dict):
        chunks: list[str] = []
        for item in value.values():
            chunks.extend(_flatten_json_strings(item))
        return chunks
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            chunks.extend(_flatten_json_strings(item))
        return chunks
    return []


def _spa_bundle_plaintext(url: str, html: str) -> str:
    """Extract public copy embedded in SPA bundles for official scenic sites."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    script_srcs = re.findall(r'(?is)<script[^>]+src=["\']?([^"\' >]+)', html)
    chunks: list[str] = []
    for src in script_srcs:
        if not src:
            continue
        src_host = urllib.parse.urlparse(src).hostname
        if src_host and src_host != host:
            continue
        if not src.endswith(".js") and ".js" not in src:
            continue
        try:
            js = _curl_get_text(urllib.parse.urljoin(url, src), timeout=DOWNLOAD_TEXT_TIMEOUT_SECONDS)
        except Exception:
            continue
        for match in re.finditer(r"JSON\.parse\('((?:\\.|[^'])*)'\)", js):
            raw = match.group(1).replace("\\'", "'")
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            chunks.extend(_flatten_json_strings(payload))
        if chunks:
            break
    positive = ("景区", "旅游", "游客", "开放", "门票", "竹海", "风景", "度假", "交通", "服务")
    negative = ("観光", "発車", "検索", "詳細", "閉館", "推奨", "敷地", "総建築", "物語", "連絡")

    def _locale_score(text: str) -> int:
        return sum(token in text for token in positive) - sum(token in text for token in negative)

    chunks = [
        chunk for chunk in chunks
        if not (any(token in chunk for token in negative) and not any(token in chunk for token in positive))
    ]
    chunks = sorted(chunks, key=_locale_score, reverse=True)
    return _join_unique_text_chunks(chunks)[:50000]


def _static_official_plaintext(url: str) -> str:
    try:
        html = _curl_get_text(url)
    except Exception:
        return ""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.endswith("ems517.com"):
        if "/new_api/" in parsed.path:
            text = _ems517_api_plaintext(url, raw_text=html)
            if text:
                return text[:50000]
        if parsed.path.startswith("/new/"):
            text = _ems517_shell_plaintext(url, html)
            if text:
                return text[:50000]
    meta_text = _html_meta_plain_text(html)
    text = _join_unique_text_chunks([meta_text, _html_to_plain_text(html)])
    if len(text) < 200 or "加载中" in text:
        bundle_text = _spa_bundle_plaintext(url, html)
        if bundle_text:
            return _join_unique_text_chunks([meta_text, bundle_text])[:50000]
    return text[:50000]


def _extract_text_by_extractor(extractor: str, html_bytes: bytes, url: str = "") -> str:
    if extractor == "wikipedia_api":
        return _wikipedia_api_plaintext(url)[:50000]
    if extractor == "baidu_baike_html":
        text, _layout = _baidu_baike_layout_and_text(html_bytes, url)
        return text
    if extractor == "toutiao_baike_html":
        text, _layout = _toutiao_baike_layout_and_text(html_bytes, url)
        return text
    if extractor == "qunar_html":
        return _qunar_html_plaintext(html_bytes, url)
    if extractor == "static_official_html":
        return _static_official_plaintext(url)
    raw = html_bytes.decode("utf-8", errors="replace")
    return _html_to_plain_text(raw)[:50000]


def extract_page_text(html_bytes: bytes, url: str = "", *, extractor: str = "generic_html") -> str:
    """从 HTML 响应抽取可读正文（按 registry extractor 分发）。"""
    return _extract_text_by_extractor(extractor, html_bytes, url)[:50000]


def extract_page_text_with_inline_images(
    html_bytes: bytes, url: str = "", *, extractor: str = "generic_html"
) -> tuple[str, list[dict[str, str]]]:
    """抽取正文 + 同源内联 <img> 清单（RC3：图文混排游记就地配图真相源）。

    - qunar_html / generic_html：解析 html_bytes，返回 (正文, 内联图清单)；正文与
      extract_page_text 一致，清单 src 已解析为绝对 URL，按出现顺序与正文里的
      asset://source-inline-NNN 占位符一一对应。
    - 其它 extractor（wikipedia_api 图片走 source plan 单一入口，baike/official 非图文混排游记）：
      返回 (正文, [])，不就地抓内联图，避免引入跨源/二次网络的第二图源。
    """
    if extractor in {"qunar_html", "generic_html"}:
        return _qunar_html_with_inline_images(html_bytes, url)
    return extract_page_text(html_bytes, url, extractor=extractor), []
