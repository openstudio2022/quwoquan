"""HTML page parsing primitives for the bounded article frontier."""
from __future__ import annotations

import re
import urllib.parse
from html import unescape
from html.parser import HTMLParser

from content.source.research.article_frontier_contract import PublicSearchResult
from content.source.research.article_frontier_profile import canonicalize_article_url

_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_RELATED_SECTION_TITLES = frozenset(
    {
        "参见",
        "參見",
        "另见",
        "另見",
        "相关条目",
        "相關條目",
        "相关人物",
        "相關人物",
        "see also",
    }
)


class PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[PublicSearchResult] = []
        self.content_links: list[PublicSearchResult] = []
        self.related_content_links: list[PublicSearchResult] = []
        self.canonical_url = ""
        self._in_title = False
        self._active_link = ""
        self._active_link_text: list[str] = []
        self._active_link_in_content = False
        self._active_link_in_related_section = False
        self._active_heading = ""
        self._active_heading_text: list[str] = []
        self._content_section_is_related = False
        self._suppressed_depth = 0
        self._element_stack: list[tuple[str, bool]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._suppressed_depth += 1
            return
        if self._suppressed_depth:
            return
        attributes = dict(attrs)
        classes = frozenset(str(attributes.get("class") or "").split())
        in_content = (
            bool(self._element_stack and self._element_stack[-1][1])
            or attributes.get("id") == "mw-content-text"
            or "mw-parser-output" in classes
        )
        if tag not in _VOID_ELEMENTS:
            self._element_stack.append((tag, in_content))
        if in_content and tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._active_heading = tag
            self._active_heading_text = []
        if tag == "title":
            self._in_title = True
        if tag == "link":
            rel = {
                value.casefold()
                for value in str(attributes.get("rel") or "").split()
            }
            href = str(attributes.get("href") or "").strip()
            if "canonical" in rel and href and not self.canonical_url:
                self.canonical_url = urllib.parse.urljoin(self.base_url, href)
        if tag == "a" and not self._active_link:
            href = str(attributes.get("href") or "").strip()
            if href:
                self._active_link = urllib.parse.urljoin(self.base_url, href)
                self._active_link_text = []
                self._active_link_in_content = in_content
                self._active_link_in_related_section = (
                    in_content and self._content_section_is_related
                )

    def handle_data(self, data: str) -> None:
        if self._suppressed_depth:
            return
        value = " ".join(str(data or "").split())
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        if self._active_link:
            self._active_link_text.append(value)
        if self._active_heading:
            self._active_heading_text.append(value)
        if len(self.text_parts) < 1200:
            self.text_parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if (
            tag in {"script", "style", "noscript", "template"}
            and self._suppressed_depth
        ):
            self._suppressed_depth -= 1
            return
        if self._suppressed_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._active_link:
            title = " ".join(self._active_link_text).strip()
            result = PublicSearchResult(title=title, url=self._active_link)
            self.links.append(result)
            if self._active_link_in_content:
                self.content_links.append(result)
            if self._active_link_in_related_section:
                self.related_content_links.append(result)
            self._active_link = ""
            self._active_link_text = []
            self._active_link_in_content = False
            self._active_link_in_related_section = False
        if tag == self._active_heading:
            heading = " ".join(self._active_heading_text).strip().casefold()
            self._content_section_is_related = heading in _RELATED_SECTION_TITLES
            self._active_heading = ""
            self._active_heading_text = []
        for index in range(len(self._element_stack) - 1, -1, -1):
            if self._element_stack[index][0] == tag:
                del self._element_stack[index:]
                break

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)[:30000]


def sitemap_urls(body: bytes) -> tuple[str, ...]:
    text = body.decode("utf-8", errors="replace")
    urls: list[str] = []
    for value in re.findall(r"(?is)<loc>\s*(.*?)\s*</loc>", text):
        canonical = canonicalize_article_url(unescape(value.strip()))
        if canonical and canonical not in urls:
            urls.append(canonical)
    return tuple(urls)


__all__ = ["PageParser", "sitemap_urls"]
