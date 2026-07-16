"""Source page payload retrieval without filesystem materialization."""
from __future__ import annotations

import hashlib
import http.client
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

from core.runtime_policy import active_runtime_policy
from content.source.fetch_http import _http_get_bytes
from content.source.fetch_text import (
    _USER_AGENT,
    _baike_layout_and_text,
    _toutiao_baike_layout_and_text,
    _wikipedia_api_extract_payload,
    _wikipedia_title_from_url,
    extract_page_text,
    extract_page_text_with_inline_images,
)
from content.source.fetch_wikitext import fetch_wikipedia_wikitext
from governance.coverage.source_registry import resolve_travel_source_runtime

_RUNTIME_POLICY = active_runtime_policy()
_DIRECT_FETCH_TIMEOUT_SECONDS = _RUNTIME_POLICY.direct_fetch_timeout_seconds
_SOURCE_FETCH_TIMEOUT_SECONDS = _RUNTIME_POLICY.source_fetch_timeout_seconds
_SOURCE_FETCH_MAX_RETRIES = _RUNTIME_POLICY.source_fetch_max_retries

def fetch_source(url: str, output_dir: Path) -> dict:
    """Fetch a URL and extract text content. Returns metadata dict."""
    output_dir.mkdir(parents=True, exist_ok=True)

    parsed = urllib.parse.urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.hostname, parsed.port, timeout=_DIRECT_FETCH_TIMEOUT_SECONDS)

    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    conn.request("GET", path, headers={"User-Agent": _USER_AGENT})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()

    html_path = output_dir / "page.html"
    html_path.write_bytes(body)

    runtime = resolve_travel_source_runtime(url)
    extractor = str(runtime.get("extractor") or "generic_html")
    text = extract_page_text(body, url, extractor=extractor)
    source_md_path = output_dir / "source.md"
    source_md_path.write_text(text, encoding="utf-8")

    return {
        "url": url,
        "statusCode": resp.status,
        "contentLength": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "htmlPath": str(html_path),
        "sourceMdPath": str(source_md_path),
        "runtime": runtime,
    }


def _source_fetchable_override(source: Mapping[str, Any] | None) -> bool:
    if not isinstance(source, Mapping):
        return False
    for key in ("fetchableOverride", "fetchable"):
        value = source.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
            return True
    return False


def fetch_source_payload(url: str, *, source: Mapping[str, Any] | None = None) -> dict:
    """抓取原文但不落盘，返回 {url, statusCode, htmlBytes, text, sha256}。

    供来源单元写入器把 page.html/source.md 落进 `sources/{sourceUnitId}/`。
    网络异常抛出，由调用方走离线兜底。
    """
    runtime = resolve_travel_source_runtime(url)
    fetchable_override = _source_fetchable_override(source)
    if runtime.get("matched") and not runtime.get("fetchable") and not fetchable_override:
        raise RuntimeError(
            f"fetch blocked for {url}: siteId={runtime.get('siteId')} marked fetchable=false in source registry"
        )
    if fetchable_override:
        runtime = {**runtime, "sourceFetchableOverride": True}
    source_extractor = str((source or {}).get("extractor") or "").strip()
    if source_extractor:
        runtime = {**runtime, "extractor": source_extractor, "sourceExtractorOverride": True}
    extractor = str(runtime.get("extractor") or "generic_html")
    if extractor == "wikipedia_api":
        wiki_payload = _wikipedia_api_extract_payload(url)
        text = wiki_payload.text
        body = wiki_payload.raw.encode("utf-8")
        if not body:
            raise RuntimeError(f"fetch failed for {url} (wikipedia_api empty response)")
        # 统一结构化 IR：wikitext 前端产出 source.layout.json 真相源
        # （表格降维列表项 + 行图/宫格连续 figure 占位，infobox factRow + 封面候选）。
        layout: dict[str, Any] | None = None
        wikitext = fetch_wikipedia_wikitext(url)
        if wikitext:
            from core.source_layout import render_source_markdown
            from core.wiki_wikitext import parse_wikitext_layout

            _host, wiki_title = _wikipedia_title_from_url(url)
            layout = parse_wikitext_layout(
                wikitext,
                source_kind="home_wikivoyage" if "wikivoyage" in (_host or "") else "home_wikipedia",
                title=wiki_payload.resolved_title or wiki_title,
            )
            if layout.get("parseStatus") == "ok":
                # source.md 底稿忠实还原：章节结构 + 图片原位 :::figure 占位（仅原图注）。
                # 占位编号与 plan imageUrls 的 placeholderId 同口径，下载成功后由
                # write_source_unit 绑定为真实 sourceAssetId，失败占位整块剥离。
                structured_text = render_source_markdown(layout)
                if structured_text:
                    text = structured_text
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": body,
            "text": text[:50000],
            "inlineImages": [],
            "layout": layout,
            "sha256": hashlib.sha256(body).hexdigest(),
            "runtime": {
                **runtime,
                "rawFormat": "mediawiki_api_json",
                "requestedTitle": wiki_payload.requested_title,
                "resolvedTitle": wiki_payload.resolved_title,
                "redirectChain": list(wiki_payload.redirect_chain),
            },
        }
    status, body, _ = _http_get_bytes(
        url,
        timeout=_SOURCE_FETCH_TIMEOUT_SECONDS,
        max_redirects=4,
        max_retries=_SOURCE_FETCH_MAX_RETRIES,
    )
    if status != 200 or not body:
        raise RuntimeError(f"fetch failed for {url} (status={status})")
    if extractor == "toutiao_baike_html":
        text, layout = _toutiao_baike_layout_and_text(body, url)
        return {
            "url": url,
            "statusCode": status,
            "htmlBytes": body,
            "text": text,
            "inlineImages": [],
            "layout": layout,
            "sha256": hashlib.sha256(body).hexdigest(),
            "runtime": runtime,
        }
    if extractor in {"baidu_baike_html", "sogou_baike_html"}:
        # 百科结构前端：HTML → 统一 IR + IR 渲染正文；解析失败落结构化 reject，
        # 禁止静默降级纯文本（rejected IR 仍随 payload 落盘可审计）。
        text, layout = _baike_layout_and_text(body, url, extractor=extractor)
        return {
            "url": url,
            "statusCode": status,
            "htmlBytes": body,
            "text": text,
            "inlineImages": [],
            "layout": layout,
            "sha256": hashlib.sha256(body).hexdigest(),
            "runtime": runtime,
        }
    # RC3：图文混排游记（qunar/generic）返回同源内联图清单（绝对 URL，与正文
    # asset://source-inline-NNN 占位同序），供来源单元写入器就地下载并锚定。
    text, inline_images = extract_page_text_with_inline_images(body, url, extractor=extractor)
    return {
        "url": url,
        "statusCode": status,
        "htmlBytes": body,
        "text": text,
        "inlineImages": inline_images,
        "sha256": hashlib.sha256(body).hexdigest(),
        "runtime": runtime,
    }
