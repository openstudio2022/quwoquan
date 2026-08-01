"""Source page payload retrieval without filesystem materialization."""
from __future__ import annotations

import hashlib
import http.client
from datetime import datetime, timezone
import threading
import urllib.parse
import urllib.robotparser
from pathlib import Path
from typing import Any, Mapping

from core.runtime_policy import active_runtime_policy
from content.source.fetch_http import _http_get_bytes
from content.source.fetch_text import (
    _USER_AGENT,
    _baidu_baike_layout_and_text,
    _toutiao_baike_layout_and_text,
    extract_page_text,
    extract_page_text_with_inline_images,
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
from content.source.research import network_io
from content.source.research.article_frontier_contract import FileDailyPageBudget
from content.source.research.article_frontier_profile import (
    article_url_allowed,
    canonicalize_article_url,
    resolve_article_source_binding,
)
from content.source.research.article_frontier_robots import (
    fetch_with_backoff,
    robots_for_url,
    shared_rate_limiter,
)

_ARTICLE_ROBOTS_LOCK = threading.Lock()
_ARTICLE_ROBOTS: dict[
    tuple[str, str], urllib.robotparser.RobotFileParser
] = {}

def fetch_source(url: str, output_dir: Path) -> dict:
    """Fetch a URL and extract text content. Returns metadata dict."""
    output_dir.mkdir(parents=True, exist_ok=True)

    parsed = urllib.parse.urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(
        parsed.hostname,
        parsed.port,
        timeout=active_runtime_policy().direct_fetch_timeout_seconds,
    )

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


def _commercial_article_fetch_response(
    url: str,
    *,
    source: Mapping[str, Any],
    runtime: Mapping[str, Any],
    fetch_page: bool,
) -> tuple[dict[str, Any], Any | None]:
    """Reapply the registered crawl controls before a frozen article refetch."""
    site = resolve_article_source_binding(
        url,
        site_id=str(source.get("articleSiteId") or ""),
        profile_digest=str(source.get("sourceDiscoveryProfileDigest") or ""),
    )
    site_id = str(site.get("siteId") or "")
    if str(runtime.get("siteId") or "") != site_id:
        raise RuntimeError(
            "commercial article source registry match differs from frozen "
            f"site binding: expected={site_id}, actual={runtime.get('siteId')}"
        )
    if _source_fetchable_override(source):
        raise RuntimeError(
            "commercial article source cannot use a fetchable override"
        )
    declared_extractor = str(source.get("extractor") or "").strip()
    expected_extractor = str(site.get("extractor") or "").strip()
    if declared_extractor and declared_extractor != expected_extractor:
        raise RuntimeError(
            "commercial article source extractor differs from registry binding"
        )
    profile = site.get("siteCrawlProfile")
    profile = profile if isinstance(profile, Mapping) else {}
    rate_limit = profile.get("rateLimit")
    rate_limit = rate_limit if isinstance(rate_limit, Mapping) else {}
    max_requests_per_second = float(
        rate_limit.get("maxRequestsPerSecond") or 0.0
    )
    backoff_statuses = frozenset(
        int(value)
        for value in (rate_limit.get("backoffOnStatus") or ())
        if str(value).isdigit()
    )
    max_pages_per_day = int(profile.get("maxPagesPerDay") or 0)
    if max_requests_per_second <= 0 or max_pages_per_day <= 0:
        raise RuntimeError(
            f"commercial article source lacks a positive crawl limit: {site_id}"
        )
    canonical_url = canonicalize_article_url(url)
    parsed = urllib.parse.urlsplit(canonical_url)
    origin = f"https://{parsed.netloc}"
    robots_key = (site_id, origin)
    with _ARTICLE_ROBOTS_LOCK:
        robots = _ARTICLE_ROBOTS.get(robots_key)
    if robots is None:
        robots, _, robots_issue = robots_for_url(
            canonical_url,
            site_id=site_id,
            timeout=active_runtime_policy().source_fetch_timeout_seconds,
            backoff_statuses=backoff_statuses,
        )
        if robots is None or robots_issue is not None:
            raise RuntimeError(
                f"commercial article robots policy unavailable: {site_id}"
            )
        with _ARTICLE_ROBOTS_LOCK:
            _ARTICLE_ROBOTS[robots_key] = robots
    if not robots.can_fetch(network_io.USER_AGENT, canonical_url):
        raise RuntimeError(
            f"commercial article robots denied source URL: {site_id}"
        )
    reservation = FileDailyPageBudget().reserve(
        site_id,
        day=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        max_pages_per_day=max_pages_per_day,
    )
    if not reservation.allowed:
        raise RuntimeError(
            f"commercial article daily page budget exhausted: {site_id}"
        )
    crawl_delay = (
        robots.crawl_delay(network_io.USER_AGENT)
        or robots.crawl_delay("*")
        or 0
    )
    limiter = shared_rate_limiter(
        site_id,
        origin,
        max_requests_per_second=max_requests_per_second,
        crawl_delay=float(crawl_delay),
    )
    if not fetch_page:
        limiter.wait()
        return dict(site), None
    response = fetch_with_backoff(
        canonical_url,
        timeout=active_runtime_policy().source_fetch_timeout_seconds,
        backoff_statuses=backoff_statuses,
        limiter=limiter,
    )
    if not response.ok:
        raise RuntimeError(
            f"commercial article fetch failed for {canonical_url} "
            f"(status={response.status_code})"
        )
    final_url = canonicalize_article_url(response.final_url or canonical_url)
    if not article_url_allowed(final_url, site):
        raise RuntimeError(
            f"commercial article redirect outside allowed paths: {site_id}"
        )
    return {**site, "finalUrl": final_url}, response


def fetch_source_payload(
    url: str,
    *,
    source: Mapping[str, Any] | None = None,
    include_page_images: bool = True,
) -> dict:
    """抓取原文但不落盘，返回 {url, statusCode, htmlBytes, text, sha256}。

    供来源单元写入器把 page.html/source.md 落进 `sources/{sourceUnitId}/`。
    网络异常抛出，由调用方走离线兜底。
    """
    runtime = resolve_travel_source_runtime(url)
    commercial_article = (
        isinstance(source, Mapping)
        and str(source.get("articleCommercialAdmission") or "")
        == "commercial_release"
    )
    fetchable_override = _source_fetchable_override(source)
    if runtime.get("matched") and not runtime.get("fetchable") and not fetchable_override:
        raise RuntimeError(
            f"fetch blocked for {url}: siteId={runtime.get('siteId')} marked fetchable=false in source registry"
        )
    source_extractor = str((source or {}).get("extractor") or "").strip()
    extractor = str(runtime.get("extractor") or "generic_html")
    governed_runtime: dict[str, Any] = {}
    governed_response = None
    if commercial_article:
        governed_runtime, governed_response = _commercial_article_fetch_response(
            url,
            source=source,
            runtime=runtime,
            fetch_page=extractor != "wikipedia_api",
        )
        runtime = {
            **runtime,
            "articleSiteId": governed_runtime.get("siteId"),
            "fetchFinalUrl": governed_runtime.get("finalUrl", url),
        }
    if fetchable_override:
        runtime = {**runtime, "sourceFetchableOverride": True}
    if source_extractor:
        runtime = {**runtime, "extractor": source_extractor, "sourceExtractorOverride": True}
    extractor = str(runtime.get("extractor") or extractor)
    if extractor == "wikipedia_api":
        bundle = fetch_mediawiki_page_bundle_for_url(
            url,
            include_images=include_page_images,
        )
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
    if governed_response is None:
        status, body, _ = _http_get_bytes(
            url,
            timeout=active_runtime_policy().source_fetch_timeout_seconds,
        )
    else:
        status, body = governed_response.status_code, governed_response.body
    if status != 200 or not body:
        raise RuntimeError(f"fetch failed for {url} (status={status})")
    if extractor == "baidu_baike_html":
        text, layout = _baidu_baike_layout_and_text(body, url)
        return {
            "url": url,
            "statusCode": status,
            "htmlBytes": body,
            "text": text,
            "inlineImages": [],
            "layout": layout,
            "sha256": hashlib.sha256(body).hexdigest(),
            "runtime": {**runtime, "rawFormat": "baidu_baike_html"},
        }
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
