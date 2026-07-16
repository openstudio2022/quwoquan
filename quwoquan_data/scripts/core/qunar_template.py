"""Qunar travelogue template classification and freshness rules."""
from __future__ import annotations

from datetime import date
import hashlib
import html as html_lib
import re
import urllib.parse
from typing import Any, Mapping

QUNAR_SITE_ID = "qunar"
QUNAR_PAGE_SEARCH_RESULT = "search_result"
QUNAR_PAGE_TRAVELOGUE_DETAIL = "travelogue_detail"
QUNAR_PAGE_UNKNOWN = "unknown"

QUNAR_FRESH_RECENT_3Y = "recent_3y"
QUNAR_FRESH_STALE_OVER_3Y = "stale_over_3y"
QUNAR_FRESH_UNKNOWN = "unknown"

QUNAR_RECENT_TRAVELOGUE_YEARS = 3

_QUNAR_DETAIL_RE = re.compile(r"/(?:youji|travelbook/note)/(\d+)(?:\D|$)")
_QUNAR_URL_RE = re.compile(r"https?://[^\s)\"']*qunar[^\s)\"']+", re.I)
_QUNAR_RELATIVE_DETAIL_RE = re.compile(r"(?<![\w/])/(?:youji|travelbook/note)/(\d+)(?:\D|$)")
_QUNAR_DETAIL_LINK_RE = re.compile(
    r"https?://[^\s)\"']*qunar[^\s)\"']*/(?:youji|travelbook/note)/\d+[^\s)\"']*"
    r"|(?<![\w/])/(?:youji|travelbook/note)/\d+(?:\D|$)",
    re.I,
)
_DATE_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})[./年-](\d{1,2})[./月-](\d{1,2})(?:日)?(?!\d)")
_AUTHOR_RE = re.compile(r"(?:作者|用户名|用户|发布者)\s*[：:]\s*([^\n\r]{1,48})")
_QUNAR_AUTHOR_BOOKS_RE = re.compile(
    r"https?://touch\.travel\.qunar\.com/([A-Za-z0-9_.-]+@qunar)/books"
    r"|/(?:travel/)?([A-Za-z0-9_.-]+@qunar)/books",
    re.I,
)
_TITLE_AUTHOR_BLOCK_RE = re.compile(
    r"<div[^>]+class=[\"'][^\"']*title-content[^\"']*[\"'][^>]*>.*?"
    r"<span[^>]+class=[\"'][^\"']*t_date[^\"']*[\"'][^>]*>(.*?)</span>",
    re.I | re.S,
)


def _frontmatter_value(text: str, key: str) -> str:
    lines = str(text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:80]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        raw_key, raw_value = line.split(":", 1)
        if raw_key.strip() == key:
            return raw_value.strip()
    return ""


def _qunar_host(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(str(url or "")).hostname or ""
    except ValueError:
        return False
    return "qunar.com" in host or "qunar.cn" in host


def qunar_url_from_text(text: str) -> str:
    url = _frontmatter_value(text, "url")
    if url:
        return url
    match = _QUNAR_URL_RE.search(str(text or ""))
    return match.group(0) if match else ""


def is_qunar_url(url: str) -> bool:
    return _qunar_host(url)


def qunar_page_type(url: str = "", text: str = "") -> str:
    raw_url = str(url or "").strip() or qunar_url_from_text(text)
    if raw_url and _qunar_host(raw_url):
        parsed = urllib.parse.urlparse(raw_url)
        path = parsed.path.rstrip("/")
        if path.endswith("/search") or path == "/search":
            return QUNAR_PAGE_SEARCH_RESULT
        if _QUNAR_DETAIL_RE.search(parsed.path):
            return QUNAR_PAGE_TRAVELOGUE_DETAIL
    body = str(text or "")
    if "游记搜索结果" in body or "bookList" in body:
        if len(extract_qunar_detail_links(body, base_url=raw_url)) >= 2:
            return QUNAR_PAGE_SEARCH_RESULT
    return QUNAR_PAGE_UNKNOWN if raw_url and _qunar_host(raw_url) else ""


def extract_qunar_detail_links(text: str, *, base_url: str = "") -> list[str]:
    body = str(text or "")
    links: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        item = urllib.parse.urljoin(base_url or "https://touch.travel.qunar.com/", url)
        if not _qunar_host(item):
            return
        match = _QUNAR_DETAIL_RE.search(urllib.parse.urlparse(item).path)
        if not match:
            return
        normalized = f"https://touch.travel.qunar.com/youji/{match.group(1)}"
        if normalized not in seen:
            seen.add(normalized)
            links.append(normalized)

    for match in _QUNAR_DETAIL_LINK_RE.finditer(body):
        add(match.group(0))
    return links


def parse_qunar_published_at(text: str, source: Mapping[str, Any] | None = None) -> str:
    if source:
        for key in ("publishedAt", "publishDate", "date", "createdAt", "updatedAt"):
            value = str(source.get(key) or "").strip()
            parsed = _parse_date(value)
            if parsed:
                return parsed
    parsed = _parse_date(_frontmatter_value(text, "publishedAt"))
    if parsed:
        return parsed
    for match in _DATE_RE.finditer(str(text or "")):
        parsed = _parse_date(match.group(0))
        if parsed:
            return parsed
    return ""


def _parse_date(value: str) -> str:
    match = _DATE_RE.search(str(value or ""))
    if not match:
        return ""
    try:
        dt = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return ""
    return dt.isoformat()


def recent_travelogue_boundary(today: date | None = None) -> date:
    base = today or date.today()
    try:
        return base.replace(year=base.year - QUNAR_RECENT_TRAVELOGUE_YEARS)
    except ValueError:
        return base.replace(month=2, day=28, year=base.year - QUNAR_RECENT_TRAVELOGUE_YEARS)


def qunar_freshness_tier(published_at: str, *, today: date | None = None) -> str:
    if not published_at:
        return QUNAR_FRESH_UNKNOWN
    try:
        dt = date.fromisoformat(str(published_at)[:10])
    except ValueError:
        return QUNAR_FRESH_UNKNOWN
    return QUNAR_FRESH_RECENT_3Y if dt >= recent_travelogue_boundary(today) else QUNAR_FRESH_STALE_OVER_3Y


def source_author_ref(author_name: str) -> str:
    normalized = re.sub(r"\s+", "", str(author_name or "")).strip()
    if not normalized:
        return ""
    digest = hashlib.sha1(f"qunar:{normalized}".encode("utf-8")).hexdigest()[:16]
    return f"sourceAuthor:qunar:{digest}"


def _clean_html_text(value: str) -> str:
    text = re.sub(r"(?is)<[^>]+>", " ", str(value or ""))
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_qunar_author(text: str = "", html: str = "", source: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Extract Qunar author identity from API rows or detail-page template HTML."""

    author_name = ""
    author_id = ""
    books_url = ""
    if source:
        author_name = str(source.get("authorName") or source.get("author") or source.get("userName") or "").strip()
        author_id = str(source.get("authorId") or source.get("userId") or source.get("uid") or "").strip()
        books_url = str(source.get("authorBooksUrl") or source.get("userBooksUrl") or "").strip()
    body = f"{text or ''}\n{html or ''}"
    if not author_name:
        match = _AUTHOR_RE.search(str(text or ""))
        author_name = match.group(1).strip() if match else ""
    if not books_url or not author_id:
        match = _QUNAR_AUTHOR_BOOKS_RE.search(body)
        if match:
            author_id = author_id or str(match.group(1) or match.group(2) or "").strip()
            books_url = books_url or f"https://touch.travel.qunar.com/{author_id}/books"
    if not author_name and html:
        match = _TITLE_AUTHOR_BLOCK_RE.search(html)
        author_name = _clean_html_text(match.group(1)) if match else ""
    if not author_name and html:
        match = re.search(r"<div[^>]+class=[\"'][^\"']*txt tit[^\"']*[\"'][^>]*>(.*?)邀您来去哪儿攻略", html, re.I | re.S)
        author_name = _clean_html_text(match.group(1)) if match else ""
    result: dict[str, str] = {}
    if author_name:
        result["authorName"] = author_name
    if author_id:
        result["authorId"] = author_id
        result["sourceAuthorRef"] = source_author_ref(author_id)
    elif author_name:
        result["sourceAuthorRef"] = source_author_ref(author_name)
    if books_url:
        result["authorBooksUrl"] = books_url
    return result


def qunar_template_metadata(
    *,
    url: str = "",
    text: str = "",
    html: str = "",
    title: str = "",
    source: Mapping[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    raw_url = str(url or "").strip() or qunar_url_from_text(text)
    page_type = qunar_page_type(raw_url, text)
    if not page_type:
        return {}
    meta: dict[str, Any] = {
        "site": QUNAR_SITE_ID,
        "pageType": page_type,
    }
    if raw_url:
        meta["canonicalUrl"] = raw_url
    if title:
        meta["title"] = str(title)
    detail_links = extract_qunar_detail_links(f"{text}\n{html}", base_url=raw_url)
    if detail_links:
        meta["discoveredDetailLinks"] = detail_links[:20]
    published = parse_qunar_published_at(text, source)
    if published:
        meta["publishedAt"] = published
    if page_type == QUNAR_PAGE_TRAVELOGUE_DETAIL:
        meta["freshnessTier"] = qunar_freshness_tier(published, today=today)
    author_meta = extract_qunar_author(text=text, html=html, source=source)
    if author_meta:
        meta.update(author_meta)
    return meta


def _site_template(source_meta: Mapping[str, Any]) -> Mapping[str, Any]:
    value = source_meta.get("siteTemplate")
    return value if isinstance(value, Mapping) else {}


def qunar_source_freshness_rank(row: Mapping[str, Any]) -> int:
    tier = str(row.get("sourceFreshnessTier") or "").strip()
    if not tier:
        tier = str(_site_template(row).get("freshnessTier") or "").strip()
    if tier == QUNAR_FRESH_RECENT_3Y:
        return 0
    if tier == QUNAR_FRESH_STALE_OVER_3Y:
        return 2
    return 1


def qunar_article_base_block_reason(source_meta: Mapping[str, Any], focus_verdict: str = "") -> str:
    site_template = _site_template(source_meta)
    url = str(source_meta.get("url") or "").strip()
    is_qunar = str(site_template.get("site") or "") == QUNAR_SITE_ID or is_qunar_url(url)
    if not is_qunar:
        return ""
    page_type = str(site_template.get("pageType") or "") or qunar_page_type(url)
    if page_type == QUNAR_PAGE_SEARCH_RESULT:
        return "qunar_search_result_directory"
    if page_type == QUNAR_PAGE_TRAVELOGUE_DETAIL and str(focus_verdict or "").strip() == "off_entity":
        return "qunar_off_entity_no_anchor"
    return ""
