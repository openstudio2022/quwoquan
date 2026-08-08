"""Resolve multilingual Wikimedia subject evidence for page-owned images."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.source.research import network_io


def _metadata_value(metadata: Mapping[str, Any], key: str) -> str:
    row = metadata.get(key)
    return str(row.get("value") or "").strip() if isinstance(row, Mapping) else ""


def _category_names(row: Mapping[str, Any]) -> tuple[str, ...]:
    info = ((row.get("imageinfo") or [{}])[0] or {})
    metadata = info.get("extmetadata") if isinstance(info, Mapping) else {}
    if not isinstance(metadata, Mapping):
        return ()
    return tuple(
        value
        for value in dict.fromkeys(
            item.strip()
            for item in _metadata_value(metadata, "Categories").split("|")
        )
        if value
    )


def _wikidata_values(entity: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = []
    for language in ("zh", "en"):
        label = (entity.get("labels") or {}).get(language)
        if isinstance(label, Mapping) and str(label.get("value") or "").strip():
            values.append((language, str(label["value"]).strip()))
        for alias in (entity.get("aliases") or {}).get(language) or ():
            if isinstance(alias, Mapping) and str(alias.get("value") or "").strip():
                values.append((language, str(alias["value"]).strip()))
    return tuple(dict.fromkeys(values))


def _is_subject_entity(entity: Mapping[str, Any]) -> bool:
    labels = [
        str(row.get("value") or "").strip()
        for row in (entity.get("labels") or {}).values()
        if isinstance(row, Mapping) and str(row.get("value") or "").strip()
    ]
    return bool(labels) and any(
        not value.casefold().startswith(("category:", "commonsmetadata-"))
        for value in labels
    )


def wikimedia_subject_evidence_by_file(
    info_by_key: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    """Bind Commons categories to Wikidata labels/aliases in two batch reads.

    A filename or an English Commons caption is not enough to establish that an
    image depicts a Chinese landmark.  Category page -> Wikidata identity makes
    the multilingual subject link explicit and leaves a stable provider/QID
    trail in the frozen source-unit asset index.
    """
    file_categories = {
        key: _category_names(row)
        for key, row in info_by_key.items()
        if _category_names(row)
    }
    categories = tuple(
        dict.fromkeys(
            category
            for values in file_categories.values()
            for category in values
        )
    )[:50]
    if not categories:
        return {}
    category_response = network_io.wiki_api(
        "commons.wikimedia.org",
        {
            "action": "query",
            "titles": "|".join(f"Category:{value}" for value in categories),
            "prop": "pageprops",
            "format": "json",
        },
    )
    category_qids: dict[str, str] = {}
    for row in ((category_response.get("query") or {}).get("pages") or {}).values():
        if not isinstance(row, Mapping):
            continue
        title = str(row.get("title") or "").removeprefix("Category:").strip()
        qid = str((row.get("pageprops") or {}).get("wikibase_item") or "").strip()
        if title and qid:
            category_qids[title] = qid
    qids = tuple(dict.fromkeys(category_qids.values()))
    if not qids:
        return {}
    entity_response = network_io.wiki_api(
        "www.wikidata.org",
        {
            "action": "wbgetentities",
            "ids": "|".join(qids),
            "props": "labels|aliases",
            "languages": "zh|en",
            "format": "json",
        },
    )
    entities = entity_response.get("entities") or {}
    result: dict[str, list[dict[str, str]]] = {}
    for file_key, file_values in file_categories.items():
        evidence: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for category in file_values:
            qid = category_qids.get(category, "")
            entity = entities.get(qid) if qid else None
            if not isinstance(entity, Mapping) or not _is_subject_entity(entity):
                continue
            for language, value in _wikidata_values(entity):
                identity = (language, value.casefold())
                if identity in seen:
                    continue
                seen.add(identity)
                evidence.append(
                    {
                        "value": value,
                        "language": language,
                        "commonsCategory": category,
                        "wikidataItem": qid,
                    }
                )
                if len(evidence) >= 24:
                    break
            if len(evidence) >= 24:
                break
        if evidence:
            result[file_key] = evidence
    return result


__all__ = ["wikimedia_subject_evidence_by_file"]
