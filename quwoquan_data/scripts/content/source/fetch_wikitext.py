"""MediaWiki wikitext retrieval and source-unit enrichment."""
from __future__ import annotations

from pathlib import Path
import urllib.parse

from content.source.fetch_http import _http_get_bytes
from content.source import fetch_text

def _wikipedia_wikitext_api_url(url: str) -> str:
    host, title = fetch_text._wikipedia_title_from_url(url)
    if not host or not title:
        return ""
    q = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "format": "json",
        }
    )
    return f"https://{host}/w/api.php?{q}"


def fetch_wikipedia_wikitext(url: str) -> str:
    from content.source.wikipedia_wikitext import fetch_wikitext

    return fetch_wikitext(
        url,
        api_url_for=_wikipedia_wikitext_api_url,
        fetch_text=fetch_text._curl_get_text,
        fetch_bytes=_http_get_bytes,
        decode_json=fetch_text._mediawiki_json_loads,
        timeout=fetch_text.DOWNLOAD_TEXT_TIMEOUT_SECONDS,
    )


def enrich_source_unit_meta_wikitext(unit_dir: Path, page_url: str) -> None:
    from content.source.wikipedia_wikitext import enrich_source_unit_meta

    enrich_source_unit_meta(unit_dir, page_url, fetcher=fetch_wikipedia_wikitext)
