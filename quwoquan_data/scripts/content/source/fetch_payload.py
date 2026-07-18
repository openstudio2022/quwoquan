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
    _toutiao_baike_layout_and_text,
    extract_page_text,
    extract_page_text_with_inline_images,
)
from content.source.research.baidu_baike import (
    baidu_baike_api_url,
    decode_baidu_baike_payload,
)
from content.source.mediawiki_page import fetch_mediawiki_page_bundle_for_url
from core.data_issue import (
    DataIssueCode,
    DataIssueError,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.source_fidelity import assess_source_content_fidelity
from governance.coverage.source_registry import resolve_travel_source_runtime

_RUNTIME_POLICY = active_runtime_policy()
_DIRECT_FETCH_TIMEOUT_SECONDS = _RUNTIME_POLICY.direct_fetch_timeout_seconds
_SOURCE_FETCH_TIMEOUT_SECONDS = _RUNTIME_POLICY.source_fetch_timeout_seconds

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
    if extractor == "baidu_baike_openapi":
        parsed = urllib.parse.urlparse(url)
        source_title = str((source or {}).get("sourceTitle") or "").strip()
        if not source_title:
            source_title = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1]).strip()
        if not source_title:
            raise RuntimeError("Baidu Baike API adapter requires a resolved source title")
        api_url = baidu_baike_api_url(source_title)
        status, body, _ = _http_get_bytes(
            api_url,
            timeout=_SOURCE_FETCH_TIMEOUT_SECONDS,
        )
        if status != 200 or not body:
            raise RuntimeError(f"fetch failed for {url} (status={status})")
        page = decode_baidu_baike_payload(body)
        if page is None:
            raise RuntimeError("Baidu Baike API returned no readable exact page")
        return {
            "url": url,
            "statusCode": status,
            "htmlBytes": body,
            "text": page.text,
            "inlineImages": [],
            "sha256": hashlib.sha256(body).hexdigest(),
            "runtime": {
                **runtime,
                "rawFormat": "baidu_baike_openapi_json",
                "resolvedTitle": page.title,
            },
        }
    if extractor == "wikipedia_api":
        bundle = fetch_mediawiki_page_bundle_for_url(url)
        if bundle is None or not bundle.rendered_text or not bundle.wikitext:
            raise DataIssueError(
                (
                    data_issue(
                        DataIssueCode.SOURCE_CONTENT_INCOMPLETE,
                        stage=DataIssueStage.DOWNLOAD_FETCH,
                        ref=url,
                        recovery=DataRecoveryAction.REPLACE_SOURCE,
                        message="MediaWiki page bundle is missing rendered prose or revision wikitext",
                    ),
                )
            )
        from core.source_layout import merge_rendered_text_layout, render_source_markdown
        from core.wiki_wikitext import parse_wikitext_layout

        host = urllib.parse.urlparse(url).hostname or ""
        parsed_layout = parse_wikitext_layout(
            bundle.wikitext,
            source_kind="home_wikivoyage" if "wikivoyage" in host else "home_wikipedia",
            title=bundle.resolved_title,
        )
        layout = merge_rendered_text_layout(parsed_layout, bundle.rendered_text)
        text = render_source_markdown(layout)
        fidelity = assess_source_content_fidelity(bundle.rendered_text, text)
        if not fidelity.complete:
            raise DataIssueError(
                (
                    data_issue(
                        DataIssueCode.SOURCE_CONTENT_INCOMPLETE,
                        stage=DataIssueStage.DOWNLOAD_FETCH,
                        ref=url,
                        recovery=DataRecoveryAction.REPLACE_SOURCE,
                        message="MediaWiki rendered prose was not preserved by the source layout",
                        attributes={
                            "authoritativeParagraphCount": fidelity.authoritative_paragraph_count,
                            "matchedParagraphCount": fidelity.matched_paragraph_count,
                            "missingPreview": fidelity.missing_paragraphs[0][:240],
                        },
                    ),
                )
            )
        body = bundle.raw.encode("utf-8")
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": body,
            "text": text[:50000],
            "renderedText": bundle.rendered_text,
            "inlineImages": [],
            "layout": layout,
            "sha256": hashlib.sha256(body).hexdigest(),
            "runtime": {
                **runtime,
                "rawFormat": "mediawiki_api_json",
                "requestedTitle": bundle.requested_title,
                "resolvedTitle": bundle.resolved_title,
                "redirectChain": list(bundle.redirect_chain),
                "pageId": bundle.page_id,
                "pageRevisionId": bundle.revision_id,
                "pageContentSha256": bundle.content_sha256,
                "renderedImageCount": len(bundle.rendered_image_titles),
            },
        }
    status, body, _ = _http_get_bytes(
        url,
        timeout=_SOURCE_FETCH_TIMEOUT_SECONDS,
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
