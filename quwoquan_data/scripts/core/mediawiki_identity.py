"""Strongly typed MediaWiki page identity extracted from API query responses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MediaWikiPageIdentity:
    requested_title: str
    resolved_title: str
    redirect_chain: tuple[str, ...]


def parse_mediawiki_page_identity(
    payload: Mapping[str, Any],
    *,
    requested_title: str,
) -> MediaWikiPageIdentity:
    query = payload.get("query") if isinstance(payload.get("query"), Mapping) else {}
    redirects = query.get("redirects") if isinstance(query, Mapping) else []
    redirect_chain = tuple(
        f"{str(row.get('from') or '').strip()} -> {str(row.get('to') or '').strip()}"
        for row in (redirects or [])
        if isinstance(row, Mapping)
        and str(row.get("from") or "").strip()
        and str(row.get("to") or "").strip()
    )
    pages = query.get("pages") if isinstance(query, Mapping) else {}
    pages = pages if isinstance(pages, Mapping) else {}
    resolved_title = next(
        (
            str(page.get("title") or "").strip()
            for page in pages.values()
            if isinstance(page, Mapping) and str(page.get("title") or "").strip()
        ),
        "",
    )
    if not resolved_title and redirects:
        last_redirect = redirects[-1] if isinstance(redirects[-1], Mapping) else {}
        resolved_title = str(last_redirect.get("to") or "").strip()
    requested = str(requested_title or "").strip()
    return MediaWikiPageIdentity(
        requested_title=requested,
        resolved_title=resolved_title or requested,
        redirect_chain=redirect_chain,
    )


__all__ = ["MediaWikiPageIdentity", "parse_mediawiki_page_identity"]
