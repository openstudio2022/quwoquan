"""Wikidata geographic discovery adapter."""
from __future__ import annotations

import re
import time
from typing import Any

from governance.coverage._coverage_discovery_shared import (
    _COVERAGE_POLICY,
    _RETRY_BACKOFF_MULTIPLIER,
    _WIKI_CATEGORY_PAGE_LIMIT,
    _WIKI_INTER_REQUEST_DELAY_SECONDS,
    _WIKI_RETRY_BACKOFF_SECONDS,
    _WIKI_RETRY_LIMIT,
    _WIKIDATA_RESULT_LIMIT,
    _WIKIDATA_ROOT_TYPE_REFS,
    _WIKIDATA_SPARQL_ENDPOINT,
    _research_network,
    _title_blocked,
)
from governance.coverage.master_list import (
    admin_children,
    admin_geo_ref,
    city_is_district_level,
)


def _sparql_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _wikidata_district_query(
    *,
    province: str,
    district: str,
    limit: int,
    offset: int,
) -> str:
    roots = " ".join(f"wd:{qid}" for qid in _WIKIDATA_ROOT_TYPE_REFS)
    return f"""
PREFIX bd: <http://www.bigdata.com/rdf#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?item ?itemLabel ?itemDescription ?coord ?travelRoot WHERE {{
  ?province rdfs:label "{_sparql_literal(province)}"@zh.
  ?district rdfs:label "{_sparql_literal(district)}"@zh;
            wdt:P131* ?province.
  ?item wdt:P131* ?district;
        wdt:P625 ?coord;
        wdt:P31 ?kind;
        rdfs:label ?itemLabel.
  FILTER(LANG(?itemLabel) = "zh")
  VALUES ?travelRoot {{ {roots} }}
  ?kind wdt:P279* ?travelRoot.
  OPTIONAL {{
    ?item schema:description ?itemDescription.
    FILTER(LANG(?itemDescription) = "zh")
  }}
}}
ORDER BY ?item ?travelRoot
LIMIT {max(1, int(limit))}
OFFSET {max(0, int(offset))}
""".strip()


def _wikidata_bindings(
    bridge: Any,
    query: str,
    *,
    retries: int = _WIKI_RETRY_LIMIT,
    backoff_seconds: float = _WIKI_RETRY_BACKOFF_SECONDS,
) -> tuple[list[dict[str, Any]], bool]:
    """执行一次逻辑 SPARQL 请求；网络重试由本 adapter 显式控制。"""
    delay = backoff_seconds
    for attempt in range(max(1, retries)):
        payload = bridge.post_form_json(
            _WIKIDATA_SPARQL_ENDPOINT,
            fields={"query": query, "format": "json"},
            timeout=_COVERAGE_POLICY.request_timeout_seconds,
        )
        results = payload.get("results") if isinstance(payload, dict) else None
        bindings = results.get("bindings") if isinstance(results, dict) else None
        if isinstance(bindings, list):
            return [row for row in bindings if isinstance(row, dict)], True
        if attempt + 1 < retries:
            time.sleep(delay)
            delay *= _RETRY_BACKOFF_MULTIPLIER
    return [], False


def _binding_value(binding: dict[str, Any], key: str) -> str:
    value = binding.get(key)
    return str(value.get("value") or "").strip() if isinstance(value, dict) else ""


def _wikidata_candidates_from_bindings(
    bindings: list[dict[str, Any]],
    *,
    province: str,
    city: str,
    district: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        item_url = _binding_value(binding, "item")
        qid = item_url.rsplit("/", 1)[-1]
        name = _binding_value(binding, "itemLabel")
        root_qid = _binding_value(binding, "travelRoot").rsplit("/", 1)[-1]
        type_ref = _WIKIDATA_ROOT_TYPE_REFS.get(root_qid)
        coord_match = re.fullmatch(
            r"Point\(([-+]?\d+(?:\.\d+)?) ([-+]?\d+(?:\.\d+)?)\)",
            _binding_value(binding, "coord"),
        )
        if (
            not re.fullmatch(r"Q[1-9]\d*", qid)
            or not name
            or len(name) < 2
            or _title_blocked(name)
            or type_ref is None
            or coord_match is None
        ):
            continue
        slot = grouped.setdefault(
            qid,
            {
                "name": name,
                "province": province,
                "city": city,
                "district": district,
                "source": "wikidata_geo",
                "identityRefs": {"qid": qid},
                "coordinates": {
                    "lat": float(coord_match.group(2)),
                    "lon": float(coord_match.group(1)),
                },
                "typeTagRefs": [],
                "extract": _binding_value(binding, "itemDescription"),
            },
        )
        if type_ref not in slot["typeTagRefs"]:
            slot["typeTagRefs"].append(type_ref)
    for candidate in grouped.values():
        candidate["typeTagRefs"].sort()
    return list(grouped.values())


def discover_wikidata_candidates(
    province: str,
    *,
    cities: list[str] | None = None,
    limit: int | None = None,
    sleep_seconds: float = _WIKI_INTER_REQUEST_DELAY_SECONDS,
    bridge: Any | None = None,
    country: str = "中国",
    failed_districts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """按行政区分页发现具稳定 QID、坐标和旅行根类证据的对象。"""
    bridge = bridge or _research_network()
    out: list[dict[str, Any]] = []
    seen_qids: set[str] = set()
    province_geo = admin_geo_ref(country, province)
    for city in admin_children(province_geo):
        if cities and city not in cities:
            continue
        districts = (
            [city]
            if city_is_district_level(country, province, city)
            else admin_children(f"{province_geo}/{city}")
        )
        for district in districts:
            exhausted = False
            for page in range(_WIKI_CATEGORY_PAGE_LIMIT):
                bindings, ok = _wikidata_bindings(
                    bridge,
                    _wikidata_district_query(
                        province=province,
                        district=district,
                        limit=_WIKIDATA_RESULT_LIMIT,
                        offset=page * _WIKIDATA_RESULT_LIMIT,
                    ),
                )
                if not ok:
                    if failed_districts is not None:
                        failed_districts.append(f"{city}/{district}")
                    break
                candidates = _wikidata_candidates_from_bindings(
                    bindings,
                    province=province,
                    city=city,
                    district=district,
                )
                for candidate in candidates:
                    qid = str((candidate.get("identityRefs") or {}).get("qid") or "")
                    if not qid or qid in seen_qids:
                        continue
                    seen_qids.add(qid)
                    out.append(candidate)
                    if limit and len(out) >= limit:
                        return out[:limit]
                if len(bindings) < _WIKIDATA_RESULT_LIMIT:
                    exhausted = True
                    break
                time.sleep(max(0.0, sleep_seconds))
            if not exhausted and ok and failed_districts is not None:
                failed_districts.append(
                    f"{city}/{district}:page_limit_{_WIKI_CATEGORY_PAGE_LIMIT}_reached"
                )
            time.sleep(max(0.0, sleep_seconds))
    return out
