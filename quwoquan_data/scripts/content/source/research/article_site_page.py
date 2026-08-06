"""HTML page parsing primitives for the bounded article frontier."""
from __future__ import annotations

import re
import urllib.parse
from html import unescape
from html.parser import HTMLParser

from content.source.research.article_frontier_contract import PublicSearchResult
from content.source.research.article_frontier_profile import canonicalize_article_url


class PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[PublicSearchResult] = []
        self.canonical_url = ""
        self._in_title = False
        self._active_link = ""
        self._active_link_text: list[str] = []
        self._suppressed_depth = 0

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
            self.links.append(PublicSearchResult(title=title, url=self._active_link))
            self._active_link = ""
            self._active_link_text = []

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
