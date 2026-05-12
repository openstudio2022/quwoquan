#!/usr/bin/env python3
"""
通用地理 POI 目录构建器。

特性：
- 配置驱动：省 / 市州切片、OSM 过滤、命名规则、地域带规则
- 产出目录候选层 NDJSON
- 产出 slice 报告（raw / kept / reject / area probe）

说明：
- 目录候选层是“实体候选目录层”，不是实体类型。
- 国内默认要求 `label_zh` 可用；海外可通过 config 放开英文回退。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(os.getenv("QWQ_REPO_ROOT", Path(__file__).resolve().parents[3])).resolve()
DATA_ROOT = Path(os.getenv("QWQ_DATA_ROOT", REPO_ROOT / "quwoquan_data")).resolve()
RUNTIME_ROOT = Path(os.getenv("QWQ_RUNTIME_ROOT", DATA_ROOT / "runtime")).resolve()
SLICE_REPORT_SCHEMA_VERSION = "quwoquan_data.geo_catalog_slice_report"
DEFAULT_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def _ensure_repo_paths() -> None:
    sys.path.insert(0, str(DATA_ROOT / "tools"))


def _resolve_path(base_dir: Path, raw: str) -> Path:
    path = Path(str(raw or "").strip())
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"YAML 必须是 object: {path}")
    return payload


def _overpass_urls() -> tuple[str, ...]:
    configured = tuple(
        str(item).strip()
        for item in str(os.getenv("QWQ_OVERPASS_URLS") or "").split(",")
        if str(item).strip()
    )
    return configured or DEFAULT_OVERPASS_URLS


def _http_overpass(query: str, retries: int = 6) -> dict[str, Any]:
    urls = _overpass_urls()
    data = query.encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "quwoquan-data-build-geo-catalog/1.0 (+https://github.com/quwoquan/quwoquan)",
    }
    last_err: Exception | None = None
    for attempt in range(retries):
        url = urls[attempt % len(urls)]
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=420) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, ssl.SSLError) as exc:
            last_err = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"Overpass 请求失败（urls={','.join(urls)}）: {last_err}")


def _load_json_inputs(paths: list[Path]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_uid: set[str] = set()
    for p in paths:
        if not p.is_file():
            print(f"[build_geo_catalog] SKIP missing {p}", file=sys.stderr)
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for el in data.get("elements") or []:
            if not isinstance(el, dict):
                continue
            et = str(el.get("type") or "x").strip()
            el_id = el.get("id")
            if el_id is None:
                continue
            uid = f"{et}:{el_id}"
            if uid in seen_uid:
                continue
            seen_uid.add(uid)
            merged.append(el)
    return merged


def _slice_cache_dir(output_path: Path) -> Path:
    return output_path.parent / ".geo_catalog_cache" / output_path.stem


def _slice_cache_path(output_path: Path, *, index: int, slice_name: str) -> Path:
    digest = hashlib.sha1(slice_name.encode("utf-8")).hexdigest()[:12]
    return _slice_cache_dir(output_path) / f"{index:02d}_{digest}.json"


def _overpass_union_fragments(filters: dict[str, Any], area_ref: str) -> list[str]:
    fragments: list[str] = []
    for value in filters.get("tourism_allowed") or []:
        v = str(value).strip()
        if not v:
            continue
        fragments.extend(
            [
                f'  node["tourism"="{v}"]({area_ref});',
                f'  way["tourism"="{v}"]({area_ref});',
                f'  relation["tourism"="{v}"]({area_ref});',
            ]
        )
    for value in filters.get("amenity_allowed") or []:
        v = str(value).strip()
        if not v:
            continue
        fragments.extend(
            [
                f'  node["amenity"="{v}"]({area_ref});',
                f'  way["amenity"="{v}"]({area_ref});',
                f'  relation["amenity"="{v}"]({area_ref});',
            ]
        )
    for value in filters.get("historic_allowed") or []:
        v = str(value).strip()
        if not v:
            continue
        fragments.extend(
            [
                f'  node["historic"="{v}"]({area_ref});',
                f'  way["historic"="{v}"]({area_ref});',
                f'  relation["historic"="{v}"]({area_ref});',
            ]
        )
    return fragments


def _slice_query(scope: dict[str, Any], filters: dict[str, Any], slice_name: str) -> str:
    name_key = str(scope.get("slice_name_key") or "name:zh").strip() or "name:zh"
    slice_admin_level = str(scope.get("slice_admin_level") or "5").strip() or "5"
    area_ref = "area.a"
    fragments = _overpass_union_fragments(filters, area_ref)
    return "\n".join(
        [
            "[out:json][timeout:420];",
            f'area["{name_key}"="{slice_name}"]["admin_level"="{slice_admin_level}"]->.a;',
            "(",
            *fragments,
            ");",
            "out center tags;",
        ]
    )


def _province_query(scope: dict[str, Any], filters: dict[str, Any]) -> str:
    province_query_name = str(scope.get("province_query_name") or scope.get("province_name") or "").strip()
    province_admin_level = str(scope.get("province_admin_level") or "4").strip() or "4"
    fragments = _overpass_union_fragments(filters, "area.a")
    return "\n".join(
        [
            "[out:json][timeout:420];",
            f'area["name:zh"="{province_query_name}"]["admin_level"="{province_admin_level}"]->.a;',
            "(",
            *fragments,
            ");",
            "out center tags;",
        ]
    )


def _probe_area(scope: dict[str, Any], slice_name: str) -> int:
    name_key = str(scope.get("slice_name_key") or "name:zh").strip() or "name:zh"
    slice_admin_level = str(scope.get("slice_admin_level") or "5").strip() or "5"
    query = "\n".join(
        [
            "[out:json][timeout:60];",
            f'area["{name_key}"="{slice_name}"]["admin_level"="{slice_admin_level}"];',
            "out ids;",
        ]
    )
    try:
        data = _http_overpass(query, retries=2)
    except RuntimeError:
        return -1
    return len(data.get("elements") or [])


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _has_cjk(value: str) -> bool:
    return bool(_CJK_RE.search(str(value or "")))


def _clean_display_name(name: str, naming_rules: dict[str, Any]) -> str:
    s = str(name or "").strip()
    for wrapper in naming_rules.get("strip_wrappers") or []:
        w = str(wrapper)
        s = s.strip(w)
    return _canonicalize_catalog_name(s.strip())


def _canonicalize_catalog_name(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    suffixes = (
        "国家级风景名胜区",
        "风景名胜区",
        "风景旅游区",
        "旅游景区",
        "旅游区",
        "风景区",
        "景区",
        "国家公园",
        "旅游度假区",
        "文旅度假区",
    )
    for suffix in suffixes:
        if text.endswith(suffix) and len(text) > len(suffix):
            base = text[: -len(suffix)]
            while len(base) >= 2 and base[-1] == base[-2]:
                base = base[:-1]
            return base + suffix
    return text


def _extract_name(tags: dict[str, Any], naming_rules: dict[str, Any]) -> tuple[str, str]:
    prefer_zh = bool(naming_rules.get("prefer_name_zh", True))
    zh = str(tags.get("name:zh") or "").strip()
    raw = str(tags.get("name") or "").strip()
    en = str(tags.get("name:en") or "").strip()
    chosen = zh if prefer_zh and zh else raw or zh or en
    return _clean_display_name(chosen, naming_rules), (zh or raw or en)


def _is_symbolic_name(name: str) -> bool:
    stripped = str(name or "").strip()
    if not stripped:
        return True
    return not any(ch.isalnum() or _has_cjk(ch) for ch in stripped)


def _name_reject_reason(name: str, tags: dict[str, Any], naming_rules: dict[str, Any]) -> str:
    stripped = str(name or "").strip()
    if len(stripped) < 2:
        return "short_name"
    if _is_symbolic_name(stripped):
        return "symbolic_name"
    for banned in naming_rules.get("banned_exact") or []:
        if stripped == str(banned):
            return "banned_exact"
    banned_regex = naming_rules.get("banned_regex") or {}
    for label, pattern in banned_regex.items():
        if re.search(str(pattern), stripped, flags=re.I):
            return str(label)
    require_cjk = bool(naming_rules.get("require_cjk", True))
    allow_english_fallback = bool(naming_rules.get("allow_english_fallback", False))
    if require_cjk and not _has_cjk(stripped) and not allow_english_fallback:
        return "non_cjk_name"
    if stripped in {"卐", "卍"}:
        return "banned_symbol"

    artwork_type = str(tags.get("artwork_type") or "").strip().lower()
    memorial = str(tags.get("memorial") or "").strip().lower()
    attraction = str(tags.get("attraction") or "").strip().lower()
    allowed_statue_hints = tuple(str(x).strip() for x in naming_rules.get("allow_statue_name_hints") or [] if str(x).strip())
    scenic_hints = tuple(str(x).strip() for x in naming_rules.get("generic_scenic_suffix_hints") or [] if str(x).strip())
    rejected_suffixes = tuple(str(x).strip() for x in naming_rules.get("rejected_suffixes") or [] if str(x).strip())

    if memorial == "statue":
        return "memorial_statue"
    if artwork_type == "statue" and not any(hint in stripped for hint in allowed_statue_hints):
        return "artwork_statue"
    if attraction == "artwork" and not any(hint in stripped for hint in scenic_hints):
        return "artwork_without_place_hint"
    if rejected_suffixes and stripped.endswith(rejected_suffixes):
        return "rejected_suffix"
    return ""


def _passes_merge_filters(tags: dict[str, Any], filters: dict[str, Any]) -> bool:
    tourism = str(tags.get("tourism") or "").strip()
    historic = str(tags.get("historic") or "").strip()
    amenity = str(tags.get("amenity") or "").strip()
    if tourism in {str(x).strip() for x in filters.get("tourism_allowed") or [] if str(x).strip()}:
        return True
    if amenity in {str(x).strip() for x in filters.get("amenity_allowed") or [] if str(x).strip()}:
        return True
    if historic in {str(x).strip() for x in filters.get("historic_allowed") or [] if str(x).strip()}:
        return True
    return False


def _admin_from_is_in_blob(raw: str, province_name: str) -> tuple[str, str, str]:
    text = str(raw or "").strip()
    if not text:
        return "", "", ""
    parts = [p.strip() for p in re.split(r"[;,，]", text) if p.strip()]
    parts = [p for p in parts if p not in {"中国", "中华人民共和国"}]
    province = ""
    for p in parts:
        if province_name and province_name.replace("省", "") in p:
            province = province_name
            break
        if p.endswith("省"):
            province = p
            break

    rest = [p for p in parts if p != province and p not in {province_name, province_name.replace("省", "")}]
    prefecture = ""
    district = ""
    if any("自治州" in p for p in rest):
        prefecture = next(p for p in rest if "自治州" in p)
        tail = [p for p in rest if p != prefecture]
        for p in reversed(tail):
            if p.endswith(("县", "区", "市")):
                district = p
                break
        return province, prefecture, district

    for i, p in enumerate(rest):
        if p.endswith("市"):
            prefecture = p
            for q in rest[i + 1 :]:
                if q.endswith(("县", "区", "市")):
                    district = q
            break
        if p.endswith(("县", "区")):
            district = p
    return province, prefecture, district


def _extract_admin(tags: dict[str, Any], scope: dict[str, Any], pref_hint: str = "") -> tuple[str, str, str]:
    province_name = str(scope.get("province_name") or "").strip()
    province = str(tags.get("addr:province") or tags.get("is_in:province") or tags.get("addr:state") or "").strip()
    prefecture = str(tags.get("addr:city") or tags.get("is_in:city") or tags.get("addr:region") or "").strip()
    district = str(tags.get("addr:district") or tags.get("addr:county") or tags.get("is_in:municipality") or "").strip()

    if not province and province_name:
        province = province_name

    if not prefecture and pref_hint:
        prefecture = pref_hint

    if not prefecture and not district:
        blob = str(tags.get("is_in") or tags.get("is_in:china") or "").strip()
        if blob:
            ip, iq, idt = _admin_from_is_in_blob(blob, province_name)
            province = province or ip or province_name
            prefecture = prefecture or iq
            district = district or idt
    return province, prefecture, district


def _dedupe_preserve(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        t = str(item).strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _match_band(prefecture: str, district: str, name: str, band_rules: dict[str, Any]) -> tuple[list[str], list[str]]:
    expected_keywords: list[str] = []
    tag_refs: list[str] = []
    blob = "".join([prefecture or "", district or "", name or ""])
    bands = band_rules.get("bands") or {}
    for band_name, band_payload in bands.items():
        if not isinstance(band_payload, dict):
            continue
        pref_substr = [str(x).strip() for x in band_payload.get("prefecture_substrings") or [] if str(x).strip()]
        place_substr = [str(x).strip() for x in band_payload.get("place_substrings") or [] if str(x).strip()]
        if any(x in blob for x in pref_substr) or any(x in blob for x in place_substr):
            expected_keywords.append(str(band_name).strip())
            for kw in band_payload.get("expected_keywords") or []:
                s = str(kw).strip()
                if s:
                    expected_keywords.append(s)
            for ref in band_payload.get("tag_refs") or []:
                s = str(ref).strip()
                if s:
                    tag_refs.append(s)
    return _dedupe_preserve(expected_keywords), _dedupe_preserve(tag_refs)


def _entity_type_fields(tags: dict[str, Any], name: str, naming_rules: dict[str, Any]) -> tuple[str, str]:
    for rule in naming_rules.get("entity_type_rules") or []:
        if not isinstance(rule, dict):
            continue
        any_match = rule.get("any_match") or {}
        matched = False
        for key, values in any_match.items():
            current = str(tags.get(str(key)) or "").strip()
            allowed = {str(x).strip() for x in values or [] if str(x).strip()}
            if current and current in allowed:
                matched = True
                break
        if matched:
            return (
                str(rule.get("entity_type") or "scenic_spot").strip(),
                str(rule.get("entity_type_label_zh") or "名胜风景区").strip(),
            )

    for rule in naming_rules.get("fallback_name_rules") or []:
        if not isinstance(rule, dict):
            continue
        hints = [str(x).strip() for x in rule.get("hint_substrings") or [] if str(x).strip()]
        if any(hint in name for hint in hints):
            return (
                str(rule.get("entity_type") or "scenic_spot").strip(),
                str(rule.get("entity_type_label_zh") or "名胜风景区").strip(),
            )

    fallback = naming_rules.get("default_entity_type") or {}
    return (
        str(fallback.get("entity_type") or "scenic_spot").strip(),
        str(fallback.get("entity_type_label_zh") or "名胜风景区").strip(),
    )


def _type_rank(t: str) -> int:
    return {"node": 0, "way": 1, "relation": 2}.get(t, 9)


def _strip_scene_suffix(name: str) -> str:
    scene_suffix_re = re.compile(
        r"(国家级风景名胜区|风景名胜区|风景旅游区|旅游景区|旅游区|风景区|景区|国家公园|旅游度假区|文旅度假区)$"
    )
    s = _canonicalize_catalog_name(str(name or "").strip())
    if not s:
        return ""
    changed = True
    while changed:
        changed = False
        m = scene_suffix_re.search(s)
        if m and len(s) > len(m.group(1)):
            s = s[: -len(m.group(1))].strip()
            changed = True
    return s or str(name or "").strip()


def _norm_name_key(name: str) -> str:
    return re.sub(r"\s+", "", _strip_scene_suffix(name))


def _name_dedupe_key(row: dict[str, Any]) -> str:
    pref = str(row.get("prefecture") or "").strip()
    dist = str(row.get("district") or "").strip()
    nk = _norm_name_key(str(row.get("name") or ""))
    return hashlib.sha256(f"{nk}|{pref}|{dist}".encode("utf-8")).hexdigest()[:24]


def _pick_better_row(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    sa = a.get("_source") or {}
    sb = b.get("_source") or {}
    ra = _type_rank(str(sa.get("type") or ""))
    rb = _type_rank(str(sb.get("type") or ""))
    if ra != rb:
        return a if ra <= rb else b
    ia = int(sa.get("id") or 0)
    ib = int(sb.get("id") or 0)
    base = a if ia <= ib else b
    other = b if base is a else a

    def score(r: dict[str, Any]) -> int:
        return (
            (1 if str(r.get("prefecture") or "").strip() else 0) * 4
            + (1 if str(r.get("district") or "").strip() else 0) * 2
            + (1 if len(r.get("expected_region_keywords") or []) > 2 else 0)
        )

    return base if score(base) >= score(other) else other


def _classify_element(
    el: dict[str, Any],
    *,
    pref_hint: str,
    scope: dict[str, Any],
    filters: dict[str, Any],
    naming_rules: dict[str, Any],
    naming_policy: dict[str, Any],
    band_rules: dict[str, Any],
    topic_prefix: str,
) -> tuple[dict[str, Any] | None, str]:
    from semantic_entity_resolution import _canonicalize_name  # noqa: PLC2701

    tags = el.get("tags") or {}
    if not isinstance(tags, dict):
        return None, "non_dict_tags"
    if not _passes_merge_filters(tags, filters):
        return None, "unwanted_osm_tags"

    name, raw_name = _extract_name(tags, naming_policy)
    if not name:
        return None, "empty_name"

    reject = _name_reject_reason(name, tags, naming_policy)
    if reject:
        return None, reject

    el_type = str(el.get("type") or "x").strip()
    el_id = el.get("id")
    if el_id is None:
        return None, "missing_id"

    province, prefecture, district = _extract_admin(tags, scope, pref_hint=pref_hint)
    topic_id = f"{topic_prefix}_{el_type}_{el_id}"
    label_en = str(tags.get("name:en") or "").strip()
    entity_type, entity_type_label = _entity_type_fields(tags, name, naming_rules)
    region_label = str(scope.get("region_label") or province or "").strip()
    default_tag_refs = _dedupe_preserve([str(x).strip() for x in band_rules.get("default_tag_refs") or [] if str(x).strip()])
    band_keywords, band_tag_refs = _match_band(prefecture, district, name, band_rules)
    center_lat, center_lon = _element_center(el)
    ordinal, parent_name_hint, cluster_hints = _cluster_hints(name)
    normalized_name = _canonicalize_name(name) or name

    geo_hints = _dedupe_preserve([province, prefecture, district, *band_keywords])
    pref_short = (
        prefecture.replace("藏族羌族自治州", "")
        .replace("彝族自治州", "")
        .replace("壮族苗族自治州", "")
        .replace("市", "")
        .strip()
    )
    dist_short = district.replace("市", "").replace("县", "").replace("区", "").strip()
    core_tokens = _dedupe_preserve([pref_short, dist_short, *band_keywords])[:16]
    display_locale = "zh" if _has_cjk(name) else "en"
    label_zh = normalized_name if _has_cjk(normalized_name) else ""
    if not label_en and display_locale == "en":
        label_en = normalized_name

    row: dict[str, Any] = {
        "topic_id": topic_id,
        "name": normalized_name,
        "raw_name": raw_name,
        "normalized_name": normalized_name,
        "label_zh": label_zh,
        "label_en": label_en,
        "display_locale": display_locale,
        "entity_type": entity_type,
        "entity_type_label_zh": entity_type_label,
        "wiki_title": normalized_name,
        "baike_item": normalized_name,
        "aliases": [],
        "core_tokens": core_tokens,
        "region": region_label,
        "province": province,
        "prefecture": prefecture,
        "district": district,
        "expected_region_keywords": geo_hints[:12],
        "tagRefs": _dedupe_preserve(default_tag_refs + band_tag_refs),
        "authority_status": "pending_check",
        "source_type": el_type,
        "source_id": str(el_id),
        "center_lat": center_lat,
        "center_lon": center_lon,
        "ordinal": ordinal,
        "parent_name_hint": parent_name_hint,
        "cluster_hints": cluster_hints,
        "_source": {"kind": "osm", "type": el_type, "id": el_id},
    }
    return row, ""


def _element_center(el: dict[str, Any]) -> tuple[float | None, float | None]:
    if isinstance(el.get("lat"), (int, float)) and isinstance(el.get("lon"), (int, float)):
        return float(el["lat"]), float(el["lon"])
    center = el.get("center") or {}
    if isinstance(center, dict) and isinstance(center.get("lat"), (int, float)) and isinstance(center.get("lon"), (int, float)):
        return float(center["lat"]), float(center["lon"])
    return None, None


def _cluster_hints(name: str) -> tuple[str, str, list[str]]:
    numbered = re.match(r"^(?P<base>.+?)(?P<ordinal>[0-9一二三四五六七八九十百]+)号(?P<role>观景台|别墅|公馆|院落|冰川观景台)$", name)
    if numbered:
        return numbered.group("ordinal"), numbered.group("base").strip(), ["numbered_member", numbered.group("role")]
    paren = re.match(r"^(?P<lemma>.+?)[(（](?P<inner>[^()（）]+)[)）]$", name)
    if paren:
        inner = str(paren.group("inner")).strip()
        lemma = str(paren.group("lemma")).strip()
        if inner.endswith("观景台"):
            parent = lemma.split("之", 1)[0].strip() or lemma
            ordinal = ""
            numbered_inner = re.match(r"^(?P<ordinal>[0-9一二三四五六七八九十百]+)号", inner)
            if numbered_inner:
                ordinal = numbered_inner.group("ordinal")
            return ordinal, parent, ["paren_viewpoint_member", inner]
    if name.endswith("关楼"):
        return "", name[: -len("关楼")].strip(), ["gate_tower_member"]
    return "", "", []


def _build_rows_with_report(
    pairs: list[tuple[dict[str, Any], str, str]],
    *,
    scope: dict[str, Any],
    filters: dict[str, Any],
    naming_rules: dict[str, Any],
    naming_policy: dict[str, Any],
    band_rules: dict[str, Any],
    topic_prefix: str,
    name_dedupe: bool,
    report_meta: list[dict[str, Any]],
    config_path: Path,
    output_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    per_slice: dict[str, dict[str, Any]] = {}
    for item in report_meta:
        per_slice[str(item["sliceName"])] = dict(item)
        per_slice[str(item["sliceName"])]["rejectCounts"] = {}
        per_slice[str(item["sliceName"])]["keptPreDedupe"] = 0

    for el, pref_hint, slice_name in pairs:
        row, reject = _classify_element(
            el,
            pref_hint=pref_hint,
            scope=scope,
            filters=filters,
            naming_rules=naming_rules,
            naming_policy=naming_policy,
            band_rules=band_rules,
            topic_prefix=topic_prefix,
        )
        slice_report = per_slice.setdefault(
            slice_name,
            {
                "sliceName": slice_name,
                "rawCount": 0,
                "areaProbeCount": -1,
                "rejectCounts": {},
                "keptPreDedupe": 0,
            },
        )
        if row:
            rows.append(row)
            slice_report["keptPreDedupe"] += 1
        else:
            slice_report["rejectCounts"][reject] = int(slice_report["rejectCounts"].get(reject) or 0) + 1

    pre_dedupe = len(rows)
    if name_dedupe:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            buckets.setdefault(_name_dedupe_key(row), []).append(row)
        merged: list[dict[str, Any]] = []
        for group in buckets.values():
            best = group[0]
            for extra in group[1:]:
                best = _pick_better_row(best, extra)
            merged.append(best)
        rows = merged

    rows = sorted(
        rows,
        key=lambda r: (
            str(r.get("prefecture") or ""),
            str(r.get("district") or ""),
            str(r.get("name") or ""),
            str(r.get("topic_id") or ""),
        ),
    )
    for row in rows:
        row.pop("_source", None)

    report = {
        "schemaVersion": SLICE_REPORT_SCHEMA_VERSION,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "configPath": str(config_path),
        "outputPath": str(output_path),
        "scopeName": str(scope.get("region_label") or scope.get("province_name") or config_path.stem),
        "rawCount": len(pairs),
        "keptCount": len(rows),
        "nameDedupedCount": max(0, pre_dedupe - len(rows)),
        "slices": list(per_slice.values()),
    }
    return rows, report


def _fetch_pairs_by_slices(
    scope: dict[str, Any],
    filters: dict[str, Any],
    *,
    output_path: Path,
) -> tuple[list[tuple[dict[str, Any], str, str]], list[dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], str, str]] = []
    report_meta: list[dict[str, Any]] = []
    slices = [str(x).strip() for x in scope.get("slices") or [] if str(x).strip()]
    seen_uid: set[str] = set()
    cache_dir = _slice_cache_dir(output_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for index, slice_name in enumerate(slices, start=1):
        print(f"[build_geo_catalog] slice {index}/{len(slices)} {slice_name} …", file=sys.stderr)
        cache_path = _slice_cache_path(output_path, index=index, slice_name=slice_name)
        if cache_path.exists():
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            query = _slice_query(scope, filters, slice_name)
            data = _http_overpass(query)
            cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        elements = [el for el in (data.get("elements") or []) if isinstance(el, dict)]
        report_meta.append(
            {
                "sliceName": slice_name,
                "rawCount": len(elements),
                "areaProbeCount": _probe_area(scope, slice_name),
            }
        )
        for el in elements:
            et = str(el.get("type") or "x").strip()
            eid = el.get("id")
            if eid is None:
                continue
            uid = f"{et}:{eid}"
            if uid in seen_uid:
                continue
            seen_uid.add(uid)
            pairs.append((el, slice_name, slice_name))
        time.sleep(0.35)
    return pairs, report_meta


def build_catalog_rows(
    *,
    config: dict[str, Any],
    config_path: Path,
    output_path: Path,
    input_paths: list[Path],
    no_fetch: bool,
    no_name_dedupe: bool,
    province_wide_query: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scope = dict(config.get("scope") or {})
    filters = dict(config.get("filters") or {})
    topic_prefix = str(config.get("topic_id_prefix") or "poi").strip() or "poi"

    base_dir = config_path.parent
    naming_rules = _load_yaml(_resolve_path(base_dir, str(config.get("naming_rules_path") or "entity_naming_rules.yaml")))
    naming_policy = dict(naming_rules.get("naming") or {})
    band_rules = _load_yaml(_resolve_path(base_dir, str(config.get("geo_band_rules_path") or "geo_band_rules.yaml")))

    pairs: list[tuple[dict[str, Any], str, str]] = []
    report_meta: list[dict[str, Any]] = []
    if input_paths:
        elements = _load_json_inputs(input_paths)
        pairs = [(el, "", "__inputs__") for el in elements]
        report_meta = [{"sliceName": "__inputs__", "rawCount": len(elements), "areaProbeCount": -1}]
    elif not no_fetch:
        if province_wide_query:
            print("[build_geo_catalog] fetching Overpass (province-wide) …", file=sys.stderr)
            data = _http_overpass(_province_query(scope, filters))
            elements = [el for el in (data.get("elements") or []) if isinstance(el, dict)]
            pairs = [(el, "", str(scope.get("province_name") or scope.get("region_label") or "__province__")) for el in elements]
            report_meta = [
                {
                    "sliceName": str(scope.get("province_name") or scope.get("region_label") or "__province__"),
                    "rawCount": len(elements),
                    "areaProbeCount": 1,
                }
            ]
        else:
            print("[build_geo_catalog] fetching Overpass (slice mode) …", file=sys.stderr)
            pairs, report_meta = _fetch_pairs_by_slices(scope, filters, output_path=output_path)

    if not pairs:
        raise RuntimeError("无可用 elements")

    return _build_rows_with_report(
        pairs,
        scope=scope,
        filters=filters,
        naming_rules=naming_rules,
        naming_policy=naming_policy,
        band_rules=band_rules,
        topic_prefix=topic_prefix,
        name_dedupe=not no_name_dedupe,
        report_meta=report_meta,
        config_path=config_path,
        output_path=output_path,
    )


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_paths()
    from common import write_json, write_ndjson  # noqa: E402

    parser = argparse.ArgumentParser(description="通用地理 POI 目录构建器（配置驱动）")
    parser.add_argument("--config", required=True, help="配置 YAML 路径")
    parser.add_argument("--output", required=True, help="输出 NDJSON 路径")
    parser.add_argument("--report-out", default="", help="slice 报告 JSON 路径；省略则按 config.output_defaults 计算")
    parser.add_argument("--inputs", nargs="*", default=[], help="Overpass JSON（含 elements）；省略则在线查询")
    parser.add_argument("--no-fetch", action="store_true", help="仅使用 --inputs，不访问 Overpass")
    parser.add_argument("--no-name-dedupe", action="store_true", help="关闭名称级去重")
    parser.add_argument("--province-wide-query", action="store_true", help="按省级一次性查询（仅在 config 支持时使用）")
    args = parser.parse_args(argv)

    config_path = _resolve_path(REPO_ROOT, str(args.config))
    config = _load_yaml(config_path)

    output_path = _resolve_path(REPO_ROOT, str(args.output))
    report_out = str(args.report_out or "").strip()
    if report_out:
        report_path = _resolve_path(REPO_ROOT, report_out)
    else:
        defaults = dict(config.get("output_defaults") or {})
        report_ref = str(defaults.get("slice_report_ref") or "")
        report_path = (RUNTIME_ROOT / report_ref).resolve() if report_ref else output_path.with_suffix(".slice_report.json")

    input_paths = [_resolve_path(REPO_ROOT, str(item)) for item in (args.inputs or [])]

    rows, report = build_catalog_rows(
        config=config,
        config_path=config_path,
        output_path=output_path,
        input_paths=input_paths,
        no_fetch=bool(args.no_fetch),
        no_name_dedupe=bool(args.no_name_dedupe),
        province_wide_query=bool(args.province_wide_query),
    )

    write_ndjson(output_path, rows)
    write_json(report_path, report)
    print(
        f"[build_geo_catalog] OK: rows={len(rows)} report={report_path} -> {output_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
