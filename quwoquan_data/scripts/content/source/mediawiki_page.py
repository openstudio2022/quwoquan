"""Canonical MediaWiki page acquisition contract.

One query entry owns rendered prose, revision wikitext, page identity and the
complete image-title inventory.  Consumers must not fetch a second wikitext or
image list and then overwrite evidence produced from this bundle.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import urllib.parse
from typing import Any, Mapping

from core.mediawiki_identity import parse_mediawiki_page_identity
from content.source.research import network_io


@dataclass(frozen=True, slots=True)
class MediaWikiPageBundle:
    requested_title: str
    resolved_title: str
    redirect_chain: tuple[str, ...]
    page_id: int
    revision_id: int
    content_sha256: str
    rendered_text: str
    wikitext: str
    rendered_image_titles: tuple[str, ...]
    raw: str


def mediawiki_title_from_url(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if not any(host.endswith(domain) for domain in ("wikipedia.org", "wikivoyage.org")):
        return "", ""
    if "/wiki/" not in parsed.path:
        return host, ""
    title = urllib.parse.unquote(parsed.path.split("/wiki/", 1)[1].split("#", 1)[0])
    return host, title


def _revision_wikitext(revision: Mapping[str, Any]) -> str:
    slots = revision.get("slots")
    if isinstance(slots, Mapping):
        main = slots.get("main")
        if isinstance(main, Mapping):
            return str(main.get("*") or main.get("content") or "")
    return str(revision.get("*") or revision.get("content") or "")


def _first_page(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    query = payload.get("query")
    pages = query.get("pages") if isinstance(query, Mapping) else None
    if not isinstance(pages, Mapping):
        return None
    return next((page for page in pages.values() if isinstance(page, Mapping)), None)


def fetch_mediawiki_page_bundle(host: str, title: str) -> MediaWikiPageBundle | None:
    """Fetch one typed page bundle, following image continuation explicitly."""
    if not host or not title:
        return None
    params: dict[str, str | int] = {
        "action": "query",
        "prop": "extracts|revisions|images",
        "explaintext": 1,
        "redirects": 1,
        "titles": title,
        "rvprop": "ids|content",
        "rvslots": "main",
        "imlimit": "max",
        "format": "json",
    }
    responses: list[dict[str, Any]] = []
    image_titles: list[str] = []
    seen_images: set[str] = set()
    first_payload: Mapping[str, Any] | None = None
    first_page: Mapping[str, Any] | None = None

    while True:
        payload = network_io.wiki_api(host, params)
        if not isinstance(payload, dict) or not payload:
            return None
        responses.append(payload)
        page = _first_page(payload)
        if page is None:
            return None
        if first_payload is None:
            first_payload = payload
            first_page = page
        for row in page.get("images") or []:
            if not isinstance(row, Mapping):
                continue
            image_title = str(row.get("title") or "").strip()
            if image_title and image_title not in seen_images:
                seen_images.add(image_title)
                image_titles.append(image_title)
        continuation = payload.get("continue")
        image_continue = (
            str(continuation.get("imcontinue") or "").strip()
            if isinstance(continuation, Mapping)
            else ""
        )
        if not image_continue:
            break
        page_id = int(page.get("pageid") or 0)
        params = {
            "action": "query",
            "prop": "images",
            "pageids": str(page_id),
            "imlimit": "max",
            "imcontinue": image_continue,
            "format": "json",
        }

    assert first_payload is not None and first_page is not None
    identity = parse_mediawiki_page_identity(first_payload, requested_title=title)
    revisions = first_page.get("revisions")
    revision = (
        next((row for row in revisions if isinstance(row, Mapping)), {})
        if isinstance(revisions, list)
        else {}
    )
    wikitext = _revision_wikitext(revision)
    raw = json.dumps(
        {"responses": responses},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return MediaWikiPageBundle(
        requested_title=identity.requested_title,
        resolved_title=identity.resolved_title,
        redirect_chain=identity.redirect_chain,
        page_id=int(first_page.get("pageid") or 0),
        revision_id=int(revision.get("revid") or first_page.get("lastrevid") or 0),
        content_sha256=hashlib.sha256(wikitext.encode("utf-8")).hexdigest(),
        rendered_text=str(first_page.get("extract") or "").strip(),
        wikitext=wikitext.strip(),
        rendered_image_titles=tuple(image_titles),
        raw=raw,
    )


def fetch_mediawiki_page_bundle_for_url(url: str) -> MediaWikiPageBundle | None:
    host, title = mediawiki_title_from_url(url)
    return fetch_mediawiki_page_bundle(host, title)


__all__ = [
    "MediaWikiPageBundle",
    "fetch_mediawiki_page_bundle",
    "fetch_mediawiki_page_bundle_for_url",
    "mediawiki_title_from_url",
]
