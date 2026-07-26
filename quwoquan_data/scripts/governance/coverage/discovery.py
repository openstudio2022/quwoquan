"""Generic geographic entity discovery composed from provider adapters.

The caller owns the region, selected providers, size, and execution workspace.
This module owns only reusable provider behavior and normalized candidate shapes.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from governance.coverage.coverage_corroboration import (
    candidate_corroboration_key,
    discover_baike_corroborations,
)
from governance.coverage.discovery_shared import (
    _COVERAGE_POLICY,
    _OSM_QUERY_GROUPS,
    _OSM_TAG_TYPE_RULES,
    _OVERPASS_ENDPOINTS,
    _OVERPASS_HTTP_TIMEOUT_SECONDS,
    _OVERPASS_INTER_REQUEST_DELAY_SECONDS,
    _OVERPASS_RETRY_BACKOFF_SECONDS,
    _OVERPASS_RETRY_LIMIT,
    _OVERPASS_RESULT_LIMIT,
    _RETRY_BACKOFF_MULTIPLIER,
    _research_network,
    _title_blocked,
)
from governance.coverage.discovery_wiki import (
    _wiki_api_with_retry,
    _wiki_category_members,
    discover_wiki_candidates,
)
from governance.coverage.discovery_wikidata import (
    _wikidata_bindings,
    _wikidata_candidates_from_bindings,
    _wikidata_district_query,
    discover_wikidata_candidates,
)
from governance.coverage.master_list import (
    admin_children,
    admin_geo_ref,
    city_is_district_level,
)


ProviderName = str
ShardProgress = Callable[[str, str, str, str, list[dict[str, object]], str | None], None]


def _overpass_query(
    bridge: Any,
    query: str,
    *,
    retries: int = _OVERPASS_RETRY_LIMIT,
    backoff_seconds: float = _OVERPASS_RETRY_BACKOFF_SECONDS,
) -> tuple[list[dict[str, Any]], bool]:
    """Return a successful OSM element list, including a valid empty result."""
    endpoints = tuple(_OVERPASS_ENDPOINTS)
    if not endpoints:
        raise ValueError("runtime policy must declare at least one Overpass endpoint")
    delay = backoff_seconds
    for attempt in range(max(1, retries)):
        endpoint = endpoints[attempt % len(endpoints)]
        response = bridge.post_form_json(
            endpoint,
            fields={"data": query},
            timeout=_OVERPASS_HTTP_TIMEOUT_SECONDS,
        )
        elements = response.get("elements") if isinstance(response, Mapping) else None
        if isinstance(elements, list):
            return [item for item in elements if isinstance(item, Mapping)], True
        if attempt + 1 < retries:
            time.sleep(delay)
            delay *= _RETRY_BACKOFF_MULTIPLIER
    return [], False


def _osm_strong_signal(element: Mapping[str, Any]) -> bool:
    tags = element.get("tags")
    if not isinstance(tags, Mapping):
        return False
    for key, expected, _entity_type, _tag_ref in _OSM_TAG_TYPE_RULES:
        actual = str(tags.get(key) or "").strip()
        if actual and (expected == "*" or actual == expected):
            return True
    return False


def _osm_type_tag_refs(tags: Mapping[str, Any]) -> list[str]:
    refs = {
        tag_ref
        for key, expected, _entity_type, tag_ref in _OSM_TAG_TYPE_RULES
        if (actual := str(tags.get(key) or "").strip())
        and (expected == "*" or actual == expected)
    }
    return sorted(refs)


def _overpass_query_text(
    *, province: str, city: str, district: str, selector: str
) -> str:
    """Build one scoped Overpass query from logical administrative names."""
    return "\n".join(
        (
            "[out:json][timeout:%d];" % _COVERAGE_POLICY.request_timeout_seconds,
            f'area["name"="{province}"]->.p;',
            f'area(area.p)["name"="{city}"]->.c;',
            f'area(area.c)["name"="{district}"]->.a;',
            "(",
            selector,
            ");",
            "out center tags;",
        )
    )


def _osm_candidate(
    element: Mapping[str, Any],
    *, province: str,
    city: str,
    district: str,
) -> dict[str, object] | None:
    tags = element.get("tags")
    if not isinstance(tags, Mapping):
        return None
    name = str(tags.get("name") or "").strip()
    type_tag_refs = _osm_type_tag_refs(tags)
    if not name or _title_blocked(name) or not type_tag_refs:
        return None
    latitude = element.get("lat", (element.get("center") or {}).get("lat"))
    longitude = element.get("lon", (element.get("center") or {}).get("lon"))
    try:
        coordinates = {"lat": float(latitude), "lon": float(longitude)}
    except (TypeError, ValueError):
        return None
    osm_type = str(element.get("type") or "").strip()
    osm_id = str(element.get("id") or "").strip()
    if not osm_type or not osm_id:
        return None
    return {
        "name": name,
        "province": province,
        "city": city,
        "district": district,
        "source": "osm_poi",
        "identityRefs": {"osmType": osm_type, "osmId": osm_id},
        "coordinates": coordinates,
        "typeTagRefs": type_tag_refs,
    }


def discover_osm_candidates(
    region: str,
    *,
    cities: Iterable[str] | None = None,
    limit: int | None = None,
    sleep_seconds: float = _OVERPASS_INTER_REQUEST_DELAY_SECONDS,
    bridge: Any | None = None,
    country: str = "中国",
    failed_districts: list[str] | None = None,
    skip_shards: set[tuple[str, str, str, str]] | None = None,
    shard_progress: ShardProgress | None = None,
) -> list[dict[str, object]]:
    """Discover OSM candidates for any requested administrative region."""
    bridge = bridge or _research_network()
    requested_cities = {str(city).strip() for city in (cities or ()) if str(city).strip()}
    skipped = skip_shards or set()
    candidates: list[dict[str, object]] = []
    seen: set[tuple[str, ...]] = set()
    region_ref = admin_geo_ref(country, region)
    for city in admin_children(region_ref):
        if requested_cities and city not in requested_cities:
            continue
        districts = (
            [city]
            if city_is_district_level(country, region, city)
            else admin_children(f"{region_ref}/{city}")
        )
        for district in districts:
            shard_key = (region, city, district, "osm_poi")
            if shard_key in skipped:
                continue
            district_rows: list[dict[str, object]] = []
            failure: str | None = None
            for _group_name, selector in _OSM_QUERY_GROUPS:
                elements, ok = _overpass_query(
                    bridge,
                    _overpass_query_text(
                        province=region,
                        city=city,
                        district=district,
                        selector=selector,
                    ),
                )
                if not ok:
                    failure = "overpass_unavailable"
                    break
                for element in elements[:_OVERPASS_RESULT_LIMIT]:
                    if not _osm_strong_signal(element):
                        continue
                    candidate = _osm_candidate(
                        element,
                        province=region,
                        city=city,
                        district=district,
                    )
                    if candidate is None:
                        continue
                    key = candidate_corroboration_key(candidate)
                    if key not in seen:
                        seen.add(key)
                        district_rows.append(candidate)
                        candidates.append(candidate)
                        if limit is not None and len(candidates) >= limit:
                            if shard_progress:
                                shard_progress("osm_poi", region, city, district, district_rows, failure)
                            return candidates
                time.sleep(max(0.0, sleep_seconds))
            if failure and failed_districts is not None:
                failed_districts.append(f"{city}/{district}:{failure}")
            if shard_progress:
                shard_progress("osm_poi", region, city, district, district_rows, failure)
    return candidates


def _write_candidates(path: Path, candidates: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(dict(candidate), ensure_ascii=False, sort_keys=True) + "\n"
        for candidate in candidates
    )
    path.write_text(payload, encoding="utf-8")


def _dedupe_candidates(candidates: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    unique: dict[tuple[str, ...], dict[str, object]] = {}
    for candidate in candidates:
        unique.setdefault(candidate_corroboration_key(candidate), candidate)
    return sorted(
        unique.values(),
        key=lambda item: (
            str(item.get("province") or ""),
            str(item.get("city") or ""),
            str(item.get("district") or ""),
            str(item.get("name") or ""),
        ),
    )


def discover_candidates(
    regions: Iterable[str],
    *,
    sources: Iterable[ProviderName],
    cities: Iterable[str] | None = None,
    limit: int | None = None,
    out_dir: Path,
    seed_candidates: Iterable[dict[str, object]] | None = None,
    skip_shards: set[tuple[str, str, str, str]] | None = None,
    shard_progress: ShardProgress | None = None,
) -> dict[str, object]:
    """Run requested reusable provider adapters and write disposable evidence."""
    requested_sources = tuple(dict.fromkeys(str(source).strip() for source in sources if str(source).strip()))
    files: list[str] = []
    counts: dict[str, int] = {}
    unique_counts: dict[str, int] = {}
    source_gaps: list[dict[str, object]] = []
    seed_rows = list(seed_candidates or ())
    for region in (str(value).strip() for value in regions):
        if not region:
            continue
        rows = [row for row in seed_rows if str(row.get("province") or "") == region]
        for source in requested_sources:
            try:
                if source == "wiki_category":
                    rows.extend(discover_wiki_candidates(region, limit=limit))
                elif source == "wikidata_geo":
                    rows.extend(discover_wikidata_candidates(region, cities=list(cities or ()), limit=limit))
                elif source == "osm_poi":
                    rows.extend(
                        discover_osm_candidates(
                            region,
                            cities=cities,
                            limit=limit,
                            skip_shards=skip_shards,
                            shard_progress=shard_progress,
                        )
                    )
                elif source in {"baidu_baike_search", "toutiao_baike_search"}:
                    rows.extend(discover_baike_corroborations(rows, source=source, limit=limit))
                else:
                    source_gaps.append({"region": region, "source": source, "status": "typed_blocked", "reason": "provider_not_configured"})
            except (OSError, TypeError, ValueError) as exc:
                source_gaps.append({"region": region, "source": source, "status": "blocked", "reason": type(exc).__name__})
        unique_rows = _dedupe_candidates(rows)
        counts[region] = len(rows)
        unique_counts[region] = len(unique_rows)
        output_path = out_dir / f"{region}.ndjson"
        _write_candidates(output_path, unique_rows)
        files.append(str(output_path))
    return {"files": files, "counts": counts, "uniqueCounts": unique_counts, "sourceGaps": source_gaps}


__all__ = [
    "_osm_strong_signal",
    "_overpass_query",
    "_wiki_api_with_retry",
    "_wiki_category_members",
    "_wikidata_bindings",
    "_wikidata_candidates_from_bindings",
    "_wikidata_district_query",
    "discover_baike_corroborations",
    "discover_candidates",
    "discover_osm_candidates",
]
