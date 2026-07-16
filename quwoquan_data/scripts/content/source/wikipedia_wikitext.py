"""Wikipedia wikitext enrichment for source-unit evidence."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from core.io import read_json, write_json
from core.runtime_policy import active_runtime_policy
from content.post.evidence_text import clean_source_markdown
from core.source_layout import render_source_markdown, write_source_layout
from content.source.source_unit import (
    SOURCE_UNIT_ASSET_INDEX,
    SOURCE_UNIT_MANIFEST,
    bind_inline_source_placeholders,
)
from core.wiki_wikitext import enrich_meta_from_wikitext, parse_wikitext_layout

_MEDIAWIKI_WIKITEXT_MAX_RETRIES = active_runtime_policy().mediawiki_wikitext_max_retries


def fetch_wikitext(
    url: str,
    *,
    api_url_for: Callable[[str], str],
    fetch_text: Callable[[str], str],
    fetch_bytes: Callable[..., tuple[int, bytes, Any]],
    decode_json: Callable[[str], Mapping[str, Any]],
    timeout: int,
) -> str:
    """Fetch the source wikitext while preserving MediaWiki's v1 response shape."""
    api_url = api_url_for(url)
    if not api_url:
        return ""
    try:
        raw = fetch_text(api_url)
    except Exception:  # noqa: BLE001
        try:
            status, body, _ = fetch_bytes(
                api_url,
                timeout=timeout,
                max_redirects=4,
                max_retries=_MEDIAWIKI_WIKITEXT_MAX_RETRIES,
            )
            raw = body.decode("utf-8", errors="ignore") if status == 200 else ""
        except Exception:  # noqa: BLE001
            return ""
    data = decode_json(raw)
    parse_block = data.get("parse") if isinstance(data, Mapping) else {}
    if not isinstance(parse_block, Mapping):
        return ""
    raw_wikitext = parse_block.get("wikitext")
    if isinstance(raw_wikitext, Mapping):
        return str(raw_wikitext.get("*") or "").strip()
    return str(raw_wikitext or parse_block.get("*") or "").strip()


def enrich_source_unit_meta(
    unit_dir: Path,
    page_url: str,
    *,
    fetcher: Callable[[str], str],
) -> None:
    """Persist section/image placement evidence and authoritative captions."""
    wikitext = fetcher(page_url)
    if not wikitext:
        return
    meta_path = unit_dir / SOURCE_UNIT_MANIFEST
    if not meta_path.is_file():
        return
    meta = read_json(meta_path)
    if not isinstance(meta, dict):
        return
    enriched = enrich_meta_from_wikitext(meta, wikitext)

    placements = enriched.get("imagePlacements") or []
    if not isinstance(placements, list) or not placements:
        write_json(meta_path, enriched)
        return
    caption_by_file = {
        str(row.get("fileName") or "").strip().lower(): str(row.get("caption") or "").strip()
        for row in placements
        if isinstance(row, dict)
        and str(row.get("fileName") or "").strip()
        and str(row.get("caption") or "").strip()
    }
    index_path = unit_dir / SOURCE_UNIT_ASSET_INDEX
    index_payload = read_json(index_path) if index_path.is_file() else {}
    assets = index_payload.get("assets") if isinstance(index_payload, dict) else []
    assets = assets if isinstance(assets, list) else []
    changed = False
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        current = str(asset.get("caption") or "").strip()
        if current and not re.match(r"^\d{2,}[-_]", current):
            continue
        candidates = (
            str(asset.get("fileName") or ""),
            Path(str(asset.get("url") or "")).name,
            Path(str(asset.get("sourceUrl") or "")).name,
        )
        matched = ""
        for candidate in candidates:
            stem = Path(candidate.replace(" ", "_")).stem.lower()
            matched = next(
                (
                    caption
                    for file_name, caption in caption_by_file.items()
                    if stem == Path(file_name).stem.lower()
                    or Path(file_name).stem.lower() in stem
                    or stem in Path(file_name).stem.lower()
                ),
                "",
            )
            if matched:
                break
        if matched:
            asset["caption"] = matched
            if not str(asset.get("relevance") or "").strip() or asset.get("relevance") == current:
                asset["relevance"] = matched
            changed = True
    if changed:
        write_json(index_path, index_payload)

    # The delayed wikitext enrichment is authoritative for both metadata and
    # source.layout/source.md. Previously it only changed meta.json, leaving
    # an empty or stale layout beside 17 enumerated placements. That split made
    # inline images lose their paragraph anchor during materialization.
    source_kind = (
        "home_wikivoyage"
        if "wikivoyage.org" in page_url
        else "home_wikipedia"
    )
    layout = parse_wikitext_layout(
        wikitext,
        source_kind=source_kind,
        title=str(enriched.get("resolvedTitle") or enriched.get("title") or ""),
    )
    if layout.get("parseStatus") == "ok":
        write_source_layout(unit_dir, layout)
        existing_source = (unit_dir / "source.md").read_text(encoding="utf-8")
        frontmatter = ""
        if existing_source.startswith("---\n"):
            closing = existing_source.find("\n---\n", 4)
            if closing >= 0:
                frontmatter = existing_source[: closing + len("\n---\n")]
        rendered = render_source_markdown(layout)
        placeholder_to_asset = {
            str(asset.get("inlinePlaceholderId") or "").strip(): str(
                asset.get("sourceAssetId") or ""
            ).strip()
            for asset in assets
            if isinstance(asset, dict)
            and str(asset.get("inlinePlaceholderId") or "").strip()
            and str(asset.get("sourceAssetId") or "").strip()
        }
        source_text = bind_inline_source_placeholders(
            f"{frontmatter}{rendered}".strip(),
            placeholder_to_asset,
        )
        (unit_dir / "source.md").write_text(source_text + "\n", encoding="utf-8")
        clean_text = clean_source_markdown(source_text)
        (unit_dir / "source.clean.md").write_text(clean_text + "\n", encoding="utf-8")
        enriched["layoutSummary"] = {
            "parseStatus": "ok",
            "blockCount": len(layout.get("blocks") or []),
            "figureCount": int(layout.get("figureCount") or 0),
            "tableCount": len(layout.get("tables") or []),
        }
        enriched["cleanSha256"] = "sha256:" + hashlib.sha256(
            clean_text.encode("utf-8")
        ).hexdigest()
    write_json(meta_path, enriched)
