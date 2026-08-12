"""Resolve a homepage structured fact from immutable public Wikidata claims."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from collections.abc import Mapping

from core.runtime_policy import active_runtime_policy

from content.source.research import network_io

_TIMEOUT_SECONDS = active_runtime_policy().provider_timeouts.mediawiki_seconds
def _same_https_authority(original: str, final: str) -> bool:
    original_url = urllib.parse.urlsplit(original)
    final_url = urllib.parse.urlsplit(final)
    if final_url.scheme != "https" or not final_url.hostname:
        return False
    original_host = str(original_url.hostname or "").lower().removeprefix("www.")
    final_host = str(final_url.hostname or "").lower().removeprefix("www.")
    return bool(original_host) and original_host == final_host


def _governed_https_url(value: object) -> tuple[str, dict[str, object]] | None:
    if not isinstance(value, str):
        return None
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    candidate = value.strip() if parsed.scheme == "https" else urllib.parse.urlunsplit(
        ("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment)
    )
    response = network_io.fetch_http(candidate, timeout=_TIMEOUT_SECONDS)
    final_url = str(response.final_url or candidate).strip()
    if not response.ok or not _same_https_authority(candidate, final_url):
        return None
    return final_url, {
        "requestedUrl": candidate,
        "finalUrl": final_url,
        "statusCode": response.status_code,
        "bodySha256": "sha256:" + hashlib.sha256(response.body).hexdigest(),
    }


def wikidata_structured_fact(
    title: str,
) -> tuple[str, object, str, str, float, bytes] | None:
    """Discover and prove an official-site fact without admitting Wikidata as body evidence."""

    try:
        pageprops = network_io.wiki_api(
            "zh.wikipedia.org",
            {
                "action": "query",
                "titles": title,
                "prop": "pageprops",
                "format": "json",
            },
        )
        pages = (pageprops.get("query") or {}).get("pages") or {}
        qid = next(
            (
                str((row.get("pageprops") or {}).get("wikibase_item") or "")
                for row in pages.values()
                if isinstance(row, Mapping)
            ),
            "",
        )
        if not re.fullmatch(r"Q[1-9][0-9]*", qid):
            return None
        claims_url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"}
        )
        claims_payload = network_io.curl_json(claims_url, timeout=_TIMEOUT_SECONDS)
        claims = ((claims_payload.get("entities") or {}).get(qid) or {}).get("claims") or {}
        for claim in claims.get("P856") or []:
            value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            admitted = _governed_https_url(value)
            if admitted is None:
                continue
            website, access = admitted
            raw = json.dumps(
                {
                    "pageprops": pageprops,
                    "claims": claims_payload,
                    "officialWebsiteAccess": access,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            return (
                "officialWebsite",
                website,
                "official_site",
                website,
                0.95,
                raw,
            )
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    return None


__all__ = ["wikidata_structured_fact"]
