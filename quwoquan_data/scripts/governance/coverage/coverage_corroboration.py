"""覆盖候选身份归并与百科精确词条核验。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

def candidate_corroboration_key(candidate: dict[str, Any]) -> tuple[str, ...]:
    """返回跨来源核验与唯一计数共用的稳定候选身份。"""
    identity = (
        candidate.get("identityRefs")
        if isinstance(candidate.get("identityRefs"), dict)
        else {}
    )
    for key in ("qid", "wikipediaPageId"):
        value = str(identity.get(key) or "").strip()
        if value:
            return (key, value)
    osm_type = str(identity.get("osmType") or "").strip()
    osm_id = str(identity.get("osmId") or "").strip()
    if osm_type and osm_id:
        return ("osm", osm_type, osm_id)
    return (
        "name_geo",
        str(candidate.get("name") or "").strip(),
        str(candidate.get("province") or "").strip(),
        str(candidate.get("city") or "").strip(),
        str(candidate.get("district") or "").strip(),
    )


def discover_baike_corroborations(
    candidates: list[dict[str, Any]],
    *,
    source: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """对已发现稳定对象做百科精确词条校验，不把模糊搜索页当作候选。"""
    if source not in {"baidu_baike_search", "toutiao_baike_search"}:
        raise ValueError(f"unsupported baike corroboration source: {source}")
    if source == "baidu_baike_search":
        from content.source.research.baidu_baike import resolve_baidu_baike_page

        resolver = resolve_baidu_baike_page
    else:
        from content.source.research.baike_com import resolve_toutiao_baike_page

        resolver = resolve_toutiao_baike_page

    unique: dict[tuple[str, ...], dict[str, Any]] = {}
    for candidate in candidates:
        name = str(candidate.get("name") or "").strip()
        if not name:
            continue
        unique.setdefault(candidate_corroboration_key(candidate), candidate)
    selected = list(unique.values())
    if limit:
        selected = selected[:limit]

    def resolve(candidate: dict[str, Any]) -> dict[str, Any] | None:
        resolution = resolver(
            str(candidate.get("name") or ""),
            geo_context_terms=tuple(
                str(candidate.get(key) or "").strip()
                for key in ("province", "city", "district")
                if str(candidate.get(key) or "").strip()
            ),
        )
        if resolution is None:
            return None
        return {
            **{
                key: candidate[key]
                for key in ("name", "province", "city", "district")
                if candidate.get(key) not in (None, "")
            },
            "source": source,
            "identityRefs": dict(candidate.get("identityRefs") or {}),
            **(
                {"coordinates": dict(candidate["coordinates"])}
                if isinstance(candidate.get("coordinates"), dict)
                else {}
            ),
            "typeTagRefs": list(candidate.get("typeTagRefs") or []),
            "sourceUrl": resolution.url,
            "resolvedTitle": resolution.title,
            "matchedTerm": resolution.matched_term,
            "matchConfidence": resolution.match_confidence,
        }

    out: list[dict[str, Any]] = []
    if selected:
        with ThreadPoolExecutor(max_workers=len(selected)) as pool:
            futures = [pool.submit(resolve, candidate) for candidate in selected]
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception:  # noqa: BLE001 - isolate one failed corroboration.
                    continue
                if result is not None:
                    out.append(result)
    return sorted(
        out,
        key=lambda item: (
            str(item.get("province") or ""),
            str(item.get("city") or ""),
            str(item.get("district") or ""),
            str(item.get("name") or ""),
        ),
    )
