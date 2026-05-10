from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import batch
from common import (
    CRAWL_SPEC_ROOT,
    RUNTIME_ROOT,
    TOPIC_ASSET_MANIFEST_SCHEMA_VERSION,
    TREES_ROOT,
    crawl_spec_path_from_arg,
    ensure_runtime_layout,
    entity_payload_for_ref,
    list_yaml_files,
    now_iso,
    read_json,
    read_ndjson,
    read_text,
    read_yaml,
    runtime_rel_ref,
    tag_id_for_ref,
    tag_label_for_ref,
    write_json,
    write_ndjson,
    write_text,
    write_yaml,
)
from crawl_runtime_contract import (
    AUTHORITY_PROFILE_SCHEMA_VERSION,
    FEEDBACK_CANDIDATE_SCHEMA_VERSION,
    PUBLISH_STATUS_SCHEMA_VERSION,
    build_entity_row,
    build_feedback_candidate_row,
    build_instruction_profile,
    build_post_candidate_row,
    build_relation_row,
    build_tag_row,
    entities_catalog_path,
    entity_authority_pool_path,
    entity_authority_profile_path,
    entity_content_page_dir,
    entity_content_pool_path,
    entity_run_dir,
    feedback_candidate_path,
    graph_relation_path,
    instruction_profile_path,
    load_entities_catalog,
    load_instruction_profile,
    load_tags_catalog,
    publish_status_path,
    selected_entities_path,
    selected_tags_path,
    stable_entity_id,
    stable_tag_id,
    tags_catalog_path,
    update_entity_authority_profile_ref,
    upsert_ndjson_rows,
    write_instruction_profile,
)
from crawl_topic_pool import build_article_row, default_enrichment_row
from native_fetch import NativeFetchError, download_binary, fetch_html_page
from source_registry import (
    authority_source_url,
    authority_sources,
    content_sources,
    content_source_url,
    load_source_registry,
    prioritized_content_sources,
    source_fetch_policy,
)


def _csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _load_spec(spec_arg: str) -> tuple[dict[str, Any], Path]:
    spec_path = crawl_spec_path_from_arg(spec_arg)
    if not spec_path.exists():
        raise FileNotFoundError(f"spec 不存在 {spec_path}")
    return read_yaml(spec_path), spec_path


def _spec_id_from_args(args) -> str:
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    spec_id = str(getattr(args, "spec_id", "") or "").strip()
    if spec_arg:
        spec, _ = _load_spec(spec_arg)
        return str(spec.get("spec_id", "")).strip()
    if spec_id:
        return spec_id
    raise ValueError("需要 --spec 或 --spec-id")


def _maybe_spec(args) -> tuple[dict[str, Any], Path | None]:
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    if not spec_arg:
        return {}, None
    spec, path = _load_spec(spec_arg)
    return spec, path


def _default_platform_priority(verticals: list[str], registry: dict[str, Any]) -> list[str]:
    rows = prioritized_content_sources(
        registry,
        target_verticals=verticals or ["travel"],
        media_modes=["article", "image"],
        platform_priority=[],
    )
    return [str(row.get("sourceId", "")).strip() for row in rows[:10] if str(row.get("sourceId", "")).strip()]


def _default_tag_catalog_path() -> Path:
    return tags_catalog_path()


def _default_entity_catalog_path() -> Path:
    return entities_catalog_path()


def _extract_query_suffix(profile: dict[str, Any], media_type: str) -> str:
    verticals = set(_csv(profile.get("targetVerticals")))
    intent = str(profile.get("intent", "")).strip()
    if "travel" in verticals:
        return "图片" if media_type == "image" else (intent or "攻略 游记")
    if "auto" in verticals:
        return "图片" if media_type == "image" else (intent or "测评 体验")
    return "图片" if media_type == "image" else (intent or "文章")


def _entity_tokens(entity_row: dict[str, Any]) -> list[str]:
    tokens = [str(entity_row.get("canonicalName", "")).strip()]
    tokens.extend(_csv(entity_row.get("aliases")))
    ext = entity_row.get("extensions") or {}
    if isinstance(ext, dict):
        tokens.extend(_csv(ext.get("coreTokens")))
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        token = token.strip()
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _pick_excerpt(text: str, needle: str) -> str:
    index = text.find(needle)
    if index < 0:
        return text[:160]
    start = max(0, index - 30)
    end = min(len(text), index + len(needle) + 80)
    return text[start:end]


def _tag_type_from_path(path: Path) -> str:
    rel = path.relative_to(TREES_ROOT / "tags")
    return rel.parts[0] if rel.parts else "tag"


def _entity_type_from_path(path: Path) -> str:
    rel = path.relative_to(TREES_ROOT / "entities")
    return rel.parts[0] if rel.parts else "entity"


def _load_tag_catalog_by_label() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = load_tags_catalog()
    label_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        label_map[str(row.get("label", "")).strip()] = row
        for alias in _csv(row.get("aliases")):
            label_map[alias] = row
    return rows, label_map


def _load_entity_catalog_by_name() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = load_entities_catalog()
    name_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        canonical = str(row.get("canonicalName", "")).strip()
        if canonical:
            name_map[canonical] = row
        for alias in _csv(row.get("aliases")):
            name_map[alias] = row
    return rows, name_map


def _topic_catalog_slice_path(spec_id: str) -> Path:
    return entities_catalog_path(f"{spec_id}_topics.ndjson")


def _entity_rows_for_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    spec_id = str(spec.get("spec_id", "")).strip()
    if spec_id and selected_entities_path(spec_id).exists():
        return read_ndjson(selected_entities_path(spec_id))
    return load_entities_catalog()


def handle_instruction_build(args) -> int:
    ensure_runtime_layout()
    registry = load_source_registry()
    spec, _ = _maybe_spec(args)
    spec_id = str(spec.get("spec_id", "")).strip() or _spec_id_from_args(args)
    raw_instruction = str(getattr(args, "instruction", "") or spec.get("query", "") or "").strip()
    verticals = _csv(getattr(args, "verticals", "")) or ["travel"]
    tag_refs = _csv(getattr(args, "tag_refs", "")) or _csv(spec.get("tag_refs", []))
    platform_priority = _csv(getattr(args, "platform_priority", "")) or _default_platform_priority(verticals, registry)
    coverage = str(getattr(args, "coverage", "") or "wide").strip() or "wide"
    content_modes = _csv(getattr(args, "content_modes", "")) or ["article", "image"]
    rewrite_preferences = {
        "style": str(getattr(args, "style", "") or "balanced").strip() or "balanced",
        "chapterPreference": str(getattr(args, "chapter_preference", "") or "grounded").strip() or "grounded",
    }
    feedback_policy = {
        "autoExtract": True,
        "autoVerifyKnown": True,
        "unknownCandidateMode": "queue",
    }
    profile = build_instruction_profile(
        spec_id=spec_id,
        raw_instruction=raw_instruction,
        intent=str(getattr(args, "intent", "") or "discover_and_publish").strip() or "discover_and_publish",
        target_verticals=verticals,
        tag_refs=tag_refs,
        platform_priority=platform_priority,
        coverage_preference=coverage,
        content_modes=content_modes,
        rewrite_preferences=rewrite_preferences,
        feedback_policy=feedback_policy,
        extensions={
            "regionHints": _csv(getattr(args, "regions", "")),
        },
    )
    path = write_instruction_profile(spec_id, profile)
    print(json.dumps({"ok": True, "specId": spec_id, "instructionProfile": runtime_rel_ref(path)}, ensure_ascii=False))
    return 0


def handle_tag_catalog_build(args) -> int:
    ensure_runtime_layout()
    rows: list[dict[str, Any]] = []
    for path in list_yaml_files(TREES_ROOT / "tags"):
        payload = read_yaml(path)
        if not isinstance(payload, dict):
            continue
        tag_ref = runtime_rel_ref(path)
        tag_id = str(payload.get("tag_id") or stable_tag_id(str(payload.get("label", "")), _tag_type_from_path(path))).strip()
        rows.append(
            build_tag_row(
                tag_id=tag_id,
                label=str(payload.get("label", path.stem)).strip(),
                tag_type=_tag_type_from_path(path),
                tag_ref=tag_ref,
                aliases=_csv(payload.get("aliases")),
                extensions={"summary": str(payload.get("summary", "")).strip()},
            )
        )
    path = _default_tag_catalog_path()
    write_ndjson(path, rows)
    print(json.dumps({"ok": True, "count": len(rows), "path": runtime_rel_ref(path)}, ensure_ascii=False))
    return 0


def handle_entity_catalog_build(args) -> int:
    ensure_runtime_layout()
    rows: list[dict[str, Any]] = []
    for path in list_yaml_files(TREES_ROOT / "entities"):
        payload = read_yaml(path)
        if not isinstance(payload, dict):
            continue
        entity_ref = runtime_rel_ref(path)
        scene_refs = _csv(payload.get("scene_tag_refs"))
        category_refs = _csv(payload.get("category_tag_refs"))
        entity_type = str(payload.get("kind") or _entity_type_from_path(path)).strip() or _entity_type_from_path(path)
        rows.append(
            build_entity_row(
                entity_id=str(payload.get("entity_id") or stable_entity_id(str(payload.get("name", path.stem)), entity_type)).strip(),
                canonical_name=str(payload.get("name", path.stem)).strip(),
                entity_type=entity_type,
                aliases=_csv(payload.get("aliases")),
                entity_ref=entity_ref,
                tag_refs=scene_refs + category_refs,
                source="tree",
                extensions={
                    "city": str(payload.get("city", "")).strip(),
                    "addressText": str(payload.get("address_text", "")).strip(),
                    "sceneTagRefs": scene_refs,
                    "categoryTagRefs": category_refs,
                    "coreTokens": _csv(payload.get("search_terms"))[:8],
                },
            )
        )
    catalog_arg = str(getattr(args, "catalog", "") or "").strip()
    if catalog_arg:
        cpath = Path(catalog_arg)
        if not cpath.is_absolute():
            cpath = (Path.cwd() / cpath).resolve()
        else:
            cpath = cpath.resolve()
        if cpath.is_file():
            if cpath.suffix.lower() == ".ndjson":
                external_rows = read_ndjson(cpath)
            else:
                payload = read_yaml(cpath)
                external_rows = payload.get("attractions", []) if isinstance(payload, dict) else []
            for row in external_rows:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("canonicalName") or row.get("name") or "").strip()
                if not name:
                    continue
                entity_type = str(row.get("entityType") or row.get("entity_type") or "place").strip() or "place"
                entity_id = str(row.get("entityId") or row.get("entity_id") or stable_entity_id(name, entity_type)).strip()
                rows.append(
                    build_entity_row(
                        entity_id=entity_id,
                        canonical_name=name,
                        entity_type=entity_type,
                        aliases=_csv(row.get("aliases")),
                        entity_ref=str(row.get("entityRef", "")).strip(),
                        tag_refs=_csv(row.get("tagRefs")),
                        topic_id=str(row.get("topic_id") or row.get("topicId") or "").strip(),
                        source="catalog",
                        extensions={
                            "coreTokens": _csv(row.get("core_tokens") or row.get("coreTokens")),
                            "wikiTitle": str(row.get("wiki_title") or row.get("wikiTitle") or name).strip(),
                            "baikeItem": str(row.get("baike_item") or row.get("baikeItem") or name).strip(),
                        },
                    )
                )
    path = _default_entity_catalog_path()
    upsert_ndjson_rows(path, rows, key_fields=["entityId"])
    result = read_ndjson(path)
    print(json.dumps({"ok": True, "count": len(result), "path": runtime_rel_ref(path)}, ensure_ascii=False))
    return 0


def handle_entities_by_tag(args) -> int:
    ensure_runtime_layout()
    spec, _ = _maybe_spec(args)
    spec_id = str(spec.get("spec_id", "")).strip() or str(getattr(args, "spec_id", "") or "").strip()
    entities = load_entities_catalog()
    tags, tag_by_label = _load_tag_catalog_by_label()
    requested_refs = _csv(getattr(args, "tag_refs", "")) or _csv(spec.get("tag_refs", []))
    requested_labels = _csv(getattr(args, "tag_labels", ""))
    requested_ids = _csv(getattr(args, "tag_ids", ""))
    if not requested_refs and not requested_labels and not requested_ids:
        print("[crawl entities-by-tag] FAIL: 需要 tag_refs/tag_labels/tag_ids 或 --spec", file=sys.stderr)
        return 1
    for label in requested_labels:
        row = tag_by_label.get(label)
        if row:
            requested_ids.append(str(row.get("tagId", "")).strip())
            if str(row.get("tagRef", "")).strip():
                requested_refs.append(str(row.get("tagRef", "")).strip())
    requested_refs = [item for item in requested_refs if item]
    requested_ids.extend([tag_id_for_ref(ref) for ref in requested_refs if ref])
    requested_id_set = {item for item in requested_ids if item}
    selected = []
    for row in entities:
        row_tag_refs = set(_csv(row.get("tagRefs")))
        row_tag_ids = {tag_id_for_ref(ref) for ref in row_tag_refs if ref}
        if row_tag_ids & requested_id_set:
            selected.append(row)
            continue
        if row_tag_refs & set(requested_refs):
            selected.append(row)
            continue
        ext = row.get("extensions") or {}
        ext_refs = set(_csv(ext.get("sceneTagRefs")) + _csv(ext.get("categoryTagRefs")))
        ext_ids = {tag_id_for_ref(ref) for ref in ext_refs if ref}
        if ext_ids & requested_id_set:
            selected.append(row)
            continue
        if ext_refs & set(requested_refs):
            selected.append(row)
            continue
    deduped: dict[str, dict[str, Any]] = {str(row.get("entityId", "")).strip(): row for row in selected if str(row.get("entityId", "")).strip()}
    selected = list(deduped.values())
    if spec_id:
        write_ndjson(selected_entities_path(spec_id), selected)
        tag_rows = []
        seen_tag = set()
        for tag in tags:
            tag_id = str(tag.get("tagId", "")).strip()
            tag_ref = str(tag.get("tagRef", "")).strip()
            if tag_id in requested_id_set or tag_ref in requested_refs:
                key = tag_id or tag_ref
                if key and key not in seen_tag:
                    seen_tag.add(key)
                    tag_rows.append(tag)
        write_ndjson(selected_tags_path(spec_id), tag_rows)
    print(json.dumps({"ok": True, "count": len(selected), "entities": [row.get("entityId", "") for row in selected]}, ensure_ascii=False))
    return 0


def handle_spec_build(args) -> int:
    ensure_runtime_layout()
    spec_id = _spec_id_from_args(args)
    profile = load_instruction_profile(spec_id)
    if not profile:
        print(f"[crawl spec-build] FAIL: 缺少 instruction_profile {spec_id}", file=sys.stderr)
        return 1
    selected_entities = read_ndjson(selected_entities_path(spec_id))
    selected_tags = read_ndjson(selected_tags_path(spec_id))
    if not selected_entities:
        print(f"[crawl spec-build] FAIL: 缺少 selected_entities {spec_id}", file=sys.stderr)
        return 1
    slice_rows: list[dict[str, Any]] = []
    entity_refs: list[str] = []
    for row in selected_entities:
        entity_ref = str(row.get("entityRef", "")).strip()
        if entity_ref:
            entity_refs.append(entity_ref)
        extensions = row.get("extensions") or {}
        core_tokens = _csv(extensions.get("coreTokens"))
        topic_id = str(row.get("topicId", "")).strip() or f"topic_{str(row.get('entityId', '')).strip()}"
        slice_rows.append(
            {
                "topic_id": topic_id,
                "entityId": str(row.get("entityId", "")).strip(),
                "name": str(row.get("canonicalName", "")).strip(),
                "aliases": _csv(row.get("aliases")),
                "wiki_title": str(extensions.get("wikiTitle") or row.get("canonicalName") or "").strip(),
                "baike_item": str(extensions.get("baikeItem") or row.get("canonicalName") or "").strip(),
                "core_tokens": core_tokens,
            }
        )
    slice_path = _topic_catalog_slice_path(spec_id)
    write_ndjson(slice_path, slice_rows)
    spec_payload = {
        "spec_id": spec_id,
        "query": str(profile.get("rawInstruction", "")).strip() or str(profile.get("intent", "")).strip(),
        "search_provider": "native_fetch",
        "article_topic_catalog_ref": runtime_rel_ref(slice_path),
        "entity_refs": [ref for ref in entity_refs if ref],
        "tag_refs": [str(row.get("tagRef", "")).strip() for row in selected_tags if str(row.get("tagRef", "")).strip()],
        "target_envs": ["alpha", "gamma"],
        "creator_refs": {
            "article": ["fixture_user_travel", "fixture_user_article"],
            "image": ["fixture_user_photo"],
        },
        "publish_policy": {"visibility": "public", "assistant_use_policy": "inherit"},
        "discovery_policy": {
            "min_article_topics": max(1, min(20, len(slice_rows))),
            "min_image_topics": 1,
            "min_candidate_sources_per_task": 20,
            "min_article_publish_topics": min(6, max(1, len(slice_rows))),
            "min_image_publish_topics": 0,
        },
        "article_lane": {"allow_domains": []},
        "image_lane": {"allow_domains": []},
        "sample_topics": {"article": [], "image": [f"{spec_id}_image_sample_001"]},
    }
    registry = load_source_registry()
    spec_payload["article_lane"]["allow_domains"] = [str(row.get("domain", "")).strip() for row in content_sources(registry) if str(row.get("domain", "")).strip()]
    spec_payload["image_lane"]["allow_domains"] = [str(row.get("domain", "")).strip() for row in content_sources(registry) if "image" in _csv(row.get("mediaTypes")) and str(row.get("domain", "")).strip()]
    output_arg = str(getattr(args, "output", "") or "").strip()
    if output_arg:
        output_path = Path(output_arg)
        if not output_path.is_absolute():
            output_path = (Path.cwd() / output_arg).resolve()
        else:
            output_path = output_path.resolve()
    else:
        output_path = CRAWL_SPEC_ROOT / f"{spec_id}.yaml"
    write_yaml(output_path, spec_payload)
    print(json.dumps({"ok": True, "spec": runtime_rel_ref(output_path), "topicCatalog": runtime_rel_ref(slice_path)}, ensure_ascii=False))
    return 0


def _selected_entities_for_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    spec_id = str(spec.get("spec_id", "")).strip()
    if spec_id and selected_entities_path(spec_id).exists():
        return read_ndjson(selected_entities_path(spec_id))
    rows = load_entities_catalog()
    entity_refs = set(_csv(spec.get("entity_refs")))
    if entity_refs:
        rows = [row for row in rows if str(row.get("entityRef", "")).strip() in entity_refs]
    return rows


def handle_authority_sync(args) -> int:
    ensure_runtime_layout()
    spec, _ = _maybe_spec(args)
    spec_id = str(spec.get("spec_id", "")).strip() or _spec_id_from_args(args)
    registry = load_source_registry()
    rows = _selected_entities_for_spec(spec) if spec else load_entities_catalog()
    authority_rows = authority_sources(registry)
    if not rows:
        print("[crawl authority-sync] FAIL: 没有实体可同步", file=sys.stderr)
        return 1
    for entity in rows:
        entity_id = str(entity.get("entityId", "")).strip()
        name = str(entity.get("canonicalName", "")).strip()
        topic_id = str(entity.get("topicId", "")).strip()
        pool: list[dict[str, Any]] = []
        for source in authority_rows:
            url = authority_source_url(source, name)
            if not url:
                continue
            pool.append(
                {
                    "schemaVersion": AUTHORITY_PROFILE_SCHEMA_VERSION,
                    "entityId": entity_id,
                    "topicId": topic_id,
                    "sourceId": str(source.get("sourceId", "")).strip(),
                    "domain": str(source.get("domain", "")).strip(),
                    "sourceRole": "authority_definition",
                    "fetchPolicy": source_fetch_policy(source),
                    "sourceType": "authority",
                    "sourceUrl": url,
                    "titleHint": name,
                    "status": "discovered",
                }
            )
        path = entity_authority_pool_path(spec_id, entity_id)
        upsert_ndjson_rows(path, pool, key_fields=["entityId", "sourceId", "sourceUrl"])
    print(json.dumps({"ok": True, "specId": spec_id, "entityCount": len(rows)}, ensure_ascii=False))
    return 0


def _first_meaningful_paragraph(paragraphs: list[str]) -> str:
    for item in paragraphs:
        text = str(item).strip()
        if len(text) >= 40:
            return text
    return paragraphs[0].strip() if paragraphs else ""


def handle_authority_review(args) -> int:
    ensure_runtime_layout()
    spec, _ = _maybe_spec(args)
    spec_id = str(spec.get("spec_id", "")).strip() or _spec_id_from_args(args)
    entities = _selected_entities_for_spec(spec) if spec else load_entities_catalog()
    updated_rows: list[dict[str, Any]] = []
    for entity in entities:
        entity_id = str(entity.get("entityId", "")).strip()
        pool = read_ndjson(entity_authority_pool_path(spec_id, entity_id))
        best_profile: dict[str, Any] = {}
        best_weight = -1
        for row in pool:
            if str(row.get("fetchPolicy", "")).strip() not in {"open_html", "api_only"}:
                continue
            url = str(row.get("sourceUrl", "")).strip()
            if not url:
                continue
            try:
                page = fetch_html_page(url, timeout_seconds=20)
            except NativeFetchError:
                continue
            definition = _first_meaningful_paragraph(page.paragraphs)
            if not definition:
                continue
            source_id = str(row.get("sourceId", "")).strip()
            weight = 0
            if source_id in {"wikipedia_zh", "baidu_baike"}:
                weight = 100
            elif source_id == "sogou_baike":
                weight = 90
            else:
                weight = 80
            if weight > best_weight:
                best_weight = weight
                best_profile = {
                    "schemaVersion": AUTHORITY_PROFILE_SCHEMA_VERSION,
                    "generatedAt": now_iso(),
                    "entityId": entity_id,
                    "canonicalName": str(entity.get("canonicalName", "")).strip(),
                    "aliases": _csv(entity.get("aliases")),
                    "definition": definition,
                    "definitionSourceUrl": page.final_url,
                    "authoritySourceType": source_id,
                    "externalIds": {source_id: page.final_url},
                    "status": "verified",
                }
        if best_profile:
            profile_path = entity_authority_profile_path(spec_id, entity_id)
            write_json(profile_path, best_profile)
            updated_rows.append(update_entity_authority_profile_ref(entity, profile_path))
        else:
            updated_rows.append(entity)
    upsert_ndjson_rows(entities_catalog_path(), updated_rows, key_fields=["entityId"])
    print(json.dumps({"ok": True, "specId": spec_id, "verified": len([row for row in updated_rows if str(row.get('authorityProfileRef', '')).strip()])}, ensure_ascii=False))
    return 0


def _load_seed_rows_by_entity(path: Path) -> dict[str, list[dict[str, Any]]]:
    mapping: dict[str, list[dict[str, Any]]] = {}
    if not path.exists():
        return mapping
    for row in read_ndjson(path):
        if not isinstance(row, dict):
            continue
        entity_id = str(row.get("entityId", "")).strip()
        topic_id = str(row.get("topicId", "")).strip()
        key = entity_id or topic_id
        if not key:
            continue
        mapping.setdefault(key, []).append(row)
    return mapping


def _discovery_query_for(entity: dict[str, Any], profile: dict[str, Any], media_type: str) -> str:
    name = str(entity.get("canonicalName", "")).strip()
    suffix = _extract_query_suffix(profile, media_type)
    return f"{name} {suffix}".strip()


def handle_content_discover(args) -> int:
    ensure_runtime_layout()
    spec, _ = _maybe_spec(args)
    spec_id = str(spec.get("spec_id", "")).strip() or _spec_id_from_args(args)
    profile = load_instruction_profile(spec_id)
    if not profile:
        print(f"[crawl content-discover] FAIL: 缺少 instruction_profile {spec_id}", file=sys.stderr)
        return 1
    entities = _selected_entities_for_spec(spec) if spec else load_entities_catalog()
    registry = load_source_registry()
    prioritized = prioritized_content_sources(
        registry,
        target_verticals=_csv(profile.get("targetVerticals")) or ["travel"],
        media_modes=_csv(profile.get("contentModes")) or ["article", "image"],
        platform_priority=_csv(profile.get("platformPriority")),
    )
    seed_arg = str(getattr(args, "seed", "") or "").strip()
    seed_rows_by: dict[str, list[dict[str, Any]]] = {}
    if seed_arg:
        seed_path = Path(seed_arg)
        if not seed_path.is_absolute():
            seed_path = (Path.cwd() / seed_arg).resolve()
        else:
            seed_path = seed_path.resolve()
        seed_rows_by = _load_seed_rows_by_entity(seed_path)
    total = 0
    for entity in entities:
        entity_id = str(entity.get("entityId", "")).strip()
        topic_id = str(entity.get("topicId", "")).strip()
        pool_rows: list[dict[str, Any]] = []
        for source in prioritized:
            media_types = _csv(source.get("mediaTypes"))
            for media_type in media_types:
                query = _discovery_query_for(entity, profile, media_type)
                url = content_source_url(source, query=query, entity_name=str(entity.get("canonicalName", "")).strip())
                if not url:
                    continue
                fetch_policy = source_fetch_policy(source)
                pool_rows.append(
                    build_post_candidate_row(
                        post_id=f"{entity_id}_{source.get('sourceId', '')}_{media_type}",
                        entity_id=entity_id,
                        topic_id=topic_id,
                        source_url=url,
                        source_type=str(source.get("sourceId", "")).strip(),
                        media_type=media_type,
                        source_role="discovery_only",
                        fetch_policy=fetch_policy,
                        title=str(entity.get("canonicalName", "")).strip(),
                        snippet=f"内容发现入口：{query}",
                        publish_status="discovered",
                        platform=str(source.get("domain", "")).strip(),
                        discovery_query=query,
                        extensions={
                            "discoveryMode": str(source.get("discoveryMode", "search_entry")).strip(),
                            "verticals": _csv(source.get("verticals")),
                        },
                    )
                )
        for seed_row in seed_rows_by.get(entity_id, []) + seed_rows_by.get(topic_id, []):
            media_type = str(seed_row.get("mediaType", "")).strip() or "article"
            source_url = str(seed_row.get("sourceUrl") or seed_row.get("url") or "").strip()
            if not source_url:
                continue
            source_type = str(seed_row.get("sourceType") or seed_row.get("platform") or "manual_seed").strip() or "manual_seed"
            pool_rows.append(
                build_post_candidate_row(
                    post_id=str(seed_row.get("postId") or f"{entity_id}_{source_type}_{len(pool_rows) + 1}").strip(),
                    entity_id=entity_id,
                    topic_id=topic_id,
                    source_url=source_url,
                    source_type=source_type,
                    media_type=media_type,
                    source_role="content_image" if media_type == "image" else "content_post",
                    fetch_policy=str(seed_row.get("fetchPolicy") or "open_html").strip() or "open_html",
                    title=str(seed_row.get("title", "")).strip(),
                    snippet=str(seed_row.get("snippet", "")).strip(),
                    publish_status="discovered",
                    platform=str(urlparse(source_url).netloc).strip(),
                    discovery_query=str(seed_row.get("query", "")).strip(),
                    extensions={
                        "likes": int(seed_row.get("likes") or 0),
                        "shares": int(seed_row.get("shares") or 0),
                        "comments": int(seed_row.get("comments") or 0),
                        "rightsStatus": str(seed_row.get("rightsStatus") or "clear").strip(),
                        "watermarkStatus": str(seed_row.get("watermarkStatus") or "clean").strip(),
                    },
                )
            )
        upsert_ndjson_rows(entity_content_pool_path(spec_id, entity_id), pool_rows, key_fields=["postId", "sourceUrl"])
        total += len(pool_rows)
    print(json.dumps({"ok": True, "specId": spec_id, "candidateCount": total}, ensure_ascii=False))
    return 0


def handle_content_hydrate(args) -> int:
    ensure_runtime_layout()
    spec, _ = _maybe_spec(args)
    spec_id = str(spec.get("spec_id", "")).strip() or _spec_id_from_args(args)
    entities = _selected_entities_for_spec(spec) if spec else load_entities_catalog()
    hydrated = 0
    for entity in entities:
        entity_id = str(entity.get("entityId", "")).strip()
        pool = read_ndjson(entity_content_pool_path(spec_id, entity_id))
        changed = False
        for row in pool:
            if str(row.get("sourceRole", "")).strip() == "discovery_only":
                continue
            source_url = str(row.get("sourceUrl", "")).strip()
            if not source_url:
                continue
            candidate_id = str(row.get("postId", "")).strip()
            page_dir = entity_content_page_dir(spec_id, entity_id, candidate_id)
            page_dir.mkdir(parents=True, exist_ok=True)
            try:
                fetched = fetch_html_page(source_url, timeout_seconds=25)
            except NativeFetchError:
                row["publishStatus"] = "hydrate_failed"
                changed = True
                continue
            write_text(page_dir / "page.html", fetched.html)
            markdown_lines = [
                "---",
                f"source_id: {candidate_id}",
                f"url: {source_url}",
                f"fetched_at: {now_iso()}",
                "---",
                "",
                f"# {fetched.title}",
                "",
            ]
            for paragraph in fetched.paragraphs:
                markdown_lines.extend([paragraph, ""])
            write_text(page_dir / "source.md", "\n".join(markdown_lines).strip() + "\n")
            asset_rows: list[dict[str, Any]] = []
            for index, image_url in enumerate(fetched.image_urls[:4], start=1):
                filename = Path(urlparse(image_url).path).name or f"image_{index}.bin"
                target = page_dir / "assets" / filename
                try:
                    asset = download_binary(image_url, target)
                except NativeFetchError:
                    continue
                asset_rows.append(
                    {
                        "assetId": f"{candidate_id}_asset_{index:02d}",
                        "kind": "image",
                        "sourceUrl": asset.source_url,
                        "localPath": runtime_rel_ref(asset.local_path),
                        "mimeType": asset.mime_type,
                        "width": asset.width,
                        "height": asset.height,
                        "sha256": asset.sha256,
                        "downloadStatus": "downloaded",
                        "rightsStatus": str((row.get("extensions") or {}).get("rightsStatus") or "clear"),
                        "watermarkStatus": str((row.get("extensions") or {}).get("watermarkStatus") or "clean"),
                        "publishEligibility": "approved",
                    }
                )
            write_json(
                page_dir / "asset_manifest.json",
                {
                    "schemaVersion": TOPIC_ASSET_MANIFEST_SCHEMA_VERSION,
                    "entityId": entity_id,
                    "candidateId": candidate_id,
                    "assets": asset_rows,
                },
            )
            row["publishStatus"] = "hydrated"
            row["title"] = str(row.get("title") or fetched.title).strip()
            row["snippet"] = str(row.get("snippet") or (fetched.paragraphs[0] if fetched.paragraphs else fetched.title)).strip()
            row.setdefault("extensions", {})
            row["extensions"]["pageDir"] = runtime_rel_ref(page_dir)
            changed = True
            hydrated += 1
        if changed:
            write_ndjson(entity_content_pool_path(spec_id, entity_id), pool)
    print(json.dumps({"ok": True, "specId": spec_id, "hydrated": hydrated}, ensure_ascii=False))
    return 0


def _default_score_weights(profile: dict[str, Any]) -> dict[str, int]:
    raw = profile.get("scoreWeights")
    if isinstance(raw, dict):
        base = {str(k): int(v) for k, v in raw.items() if str(k)}
    else:
        base = {}
    return {
        "entityRelevance": int(base.get("entityRelevance", 28)),
        "authorityGrounding": int(base.get("authorityGrounding", 22)),
        "contentQuality": int(base.get("contentQuality", 25)),
        "engagementUtility": int(base.get("engagementUtility", 10)),
        "rightsCompliance": int(base.get("rightsCompliance", 15)),
    }


def _extract_body_from_markdown(source_markdown: str) -> str:
    text = source_markdown.strip()
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            text = parts[1]
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    return "\n".join(lines)


def _simple_rewrite_policy(total_score: int, entity_score: int, authority_score: int) -> str:
    if total_score >= 82 and entity_score >= 65 and authority_score >= 55:
        return "light_edit"
    if total_score >= 68 and entity_score >= 48:
        return "structured_enrich"
    if total_score >= 45:
        return "multi_source_rewrite"
    return "hold_for_reference"


def _article_breakdown_from_scores(entity_score: int, authority_score: int, quality_score: int, engagement_score: int, rights_score: int) -> tuple[dict[str, Any], dict[str, Any]]:
    quality_breakdown = {
        "contentCompleteness": min(25, max(8, round(quality_score * 0.25))),
        "actionability": min(20, max(6, round(entity_score * 0.2))),
        "sourceCredibility": min(15, max(4, round(authority_score * 0.15))),
        "freshness": min(10, 8),
        "richness": min(10, max(3, round(quality_score * 0.1))),
        "engagementSignal": min(10, max(0, round(engagement_score * 0.1))),
        "cleanliness": min(10, max(4, round(rights_score * 0.1))),
    }
    publishability = {
        "readerValue": min(20, max(6, round(quality_score * 0.2))),
        "routeSpecificity": min(18, max(4, round(entity_score * 0.18))),
        "factDensity": min(16, max(4, round(authority_score * 0.16))),
        "practicality": min(16, max(4, round(entity_score * 0.16))),
        "narrativePotential": min(20, max(4, round(quality_score * 0.2))),
        "encyclopedicPenalty": max(0, 18 - round(authority_score * 0.1)),
    }
    return quality_breakdown, publishability


def _image_breakdown_from_scores(entity_score: int, quality_score: int, rights_score: int, asset_count: int) -> dict[str, Any]:
    return {
        "rightsClarity": min(30, max(10, round(rights_score * 0.3))),
        "watermarkCleanliness": min(20, max(8, round(rights_score * 0.2))),
        "resolution": min(15, 12 if asset_count else 6),
        "composition": min(15, max(5, round(quality_score * 0.15))),
        "relevance": min(10, max(4, round(entity_score * 0.1))),
        "storytelling": min(10, max(2, round(quality_score * 0.1))),
    }


def _materialize_topic_candidate(
    *,
    spec: dict[str, Any],
    entity: dict[str, Any],
    candidate: dict[str, Any],
    entity_score: int,
    authority_score: int,
    quality_score: int,
    engagement_score: int,
    rights_score: int,
    asset_count: int,
) -> None:
    topic_id = str(candidate.get("topicId", "")).strip()
    if not topic_id:
        return
    topic_dir = batch.run_topic_dir(spec["spec_id"], topic_id)
    source_pool_path = topic_dir / "source_pool.ndjson"
    enrichment_path = topic_dir / "enrichment.ndjson"
    media_type = str(candidate.get("mediaType", "")).strip() or "article"
    entity_tokens = _entity_tokens(entity)
    if media_type == "image":
        image_breakdown = _image_breakdown_from_scores(entity_score, quality_score, rights_score, asset_count)
        row = {
            "candidateId": str(candidate.get("postId", "")).strip(),
            "sourceId": str(candidate.get("postId", "")).strip(),
            "taskType": "image",
            "topicTitle": str(entity.get("canonicalName", "")).strip(),
            "query": str(candidate.get("discoveryQuery", "")).strip(),
            "title": str(candidate.get("title", "")).strip() or str(entity.get("canonicalName", "")).strip(),
            "sourceUrl": str(candidate.get("sourceUrl", "")).strip(),
            "domain": _normalize_domain(urlparse(str(candidate.get("sourceUrl", "")).strip()).netloc),
            "platform": str(candidate.get("platform", "")).strip() or _normalize_domain(urlparse(str(candidate.get("sourceUrl", "")).strip()).netloc),
            "snippet": str(candidate.get("snippet", "")).strip(),
            "sourceRole": "publish_candidate",
            "rightsStatus": str((candidate.get("extensions") or {}).get("rightsStatus") or "clear"),
            "watermarkStatus": str((candidate.get("extensions") or {}).get("watermarkStatus") or "clean"),
            "duplicateStatus": "unique",
            "adSignal": False,
            "likes": int((candidate.get("extensions") or {}).get("likes") or 0),
            "shares": int((candidate.get("extensions") or {}).get("shares") or 0),
            "comments": int((candidate.get("extensions") or {}).get("comments") or 0),
            "imageQualityBreakdown": image_breakdown,
            "imageQualityScore": sum(int(value) for value in image_breakdown.values()),
            "relevanceTokens": entity_tokens,
        }
    else:
        quality_breakdown, publishability = _article_breakdown_from_scores(entity_score, authority_score, quality_score, engagement_score, rights_score)
        row = build_article_row(
            topic_title=str(entity.get("canonicalName", "")).strip(),
            spec_query=str(candidate.get("discoveryQuery", "")).strip() or str(spec.get("query", "")).strip(),
            url=str(candidate.get("sourceUrl", "")).strip(),
            page_title=str(candidate.get("title", "")).strip() or str(entity.get("canonicalName", "")).strip(),
            snippet=str(candidate.get("snippet", "")).strip(),
            engagement=int((candidate.get("extensions") or {}).get("likes") or 0),
            relevance_tokens=entity_tokens,
        )
        row["qualityBreakdown"] = quality_breakdown
        row["publishabilityBreakdown"] = publishability
        row["likes"] = int((candidate.get("extensions") or {}).get("likes") or 0)
        row["shares"] = int((candidate.get("extensions") or {}).get("shares") or 0)
        row["comments"] = int((candidate.get("extensions") or {}).get("comments") or 0)
        row["sourceRole"] = "publish_candidate"
        row["rightsStatus"] = str((candidate.get("extensions") or {}).get("rightsStatus") or "clear")
        row["watermarkStatus"] = str((candidate.get("extensions") or {}).get("watermarkStatus") or "clean")
    upsert_ndjson_rows(source_pool_path, [row], key_fields=["sourceId", "sourceUrl"])
    if not enrichment_path.exists():
        enrichment = default_enrichment_row(spec, topic_id, "image" if media_type == "image" else "article", str(entity.get("canonicalName", "")).strip())
        entity_ref = str(entity.get("entityRef", "")).strip()
        if entity_ref:
            enrichment["entityRefs"] = [entity_ref]
        enrichment["tagRefs"] = _csv(entity.get("tagRefs"))
        write_ndjson(enrichment_path, [enrichment])


def _normalize_domain(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def handle_content_review(args) -> int:
    ensure_runtime_layout()
    spec, _ = _maybe_spec(args)
    if not spec:
        print("[crawl content-review] FAIL: 需要 --spec 以便桥接到 topic", file=sys.stderr)
        return 1
    spec_id = str(spec.get("spec_id", "")).strip()
    profile = load_instruction_profile(spec_id)
    weights = _default_score_weights(profile)
    entities = _selected_entities_for_spec(spec)
    entity_map = {str(row.get("entityId", "")).strip(): row for row in entities if str(row.get("entityId", "")).strip()}
    approved = 0
    for entity_id, entity in entity_map.items():
        pool_path = entity_content_pool_path(spec_id, entity_id)
        pool = read_ndjson(pool_path)
        if not pool:
            continue
        authority_profile = {}
        profile_path = entity_authority_profile_path(spec_id, entity_id)
        if profile_path.exists():
            authority_profile = read_json(profile_path)
        authority_text = str(authority_profile.get("definition", "")).strip()
        entity_tokens = _entity_tokens(entity)
        changed = False
        for row in pool:
            if str(row.get("publishStatus", "")).strip() != "hydrated":
                continue
            page_dir_rel = str((row.get("extensions") or {}).get("pageDir") or "").strip()
            if not page_dir_rel:
                continue
            page_dir = RUNTIME_ROOT / page_dir_rel
            source_md = read_text(page_dir / "source.md") if (page_dir / "source.md").exists() else ""
            page_html = read_text(page_dir / "page.html") if (page_dir / "page.html").exists() else ""
            body = _extract_body_from_markdown(source_md)
            text_blob = f"{row.get('title', '')} {row.get('snippet', '')} {body} {page_html}"
            entity_hits = sum(1 for token in entity_tokens if token and token in text_blob)
            entity_score = min(100, 20 + entity_hits * 15 + min(len(body) // 80, 20))
            authority_hits = 0
            if authority_text:
                for token in [item for item in re.split(r"[，。；、\s]+", authority_text) if len(item.strip()) >= 2][:12]:
                    if token in text_blob:
                        authority_hits += 1
            authority_score = min(100, 20 + authority_hits * 10)
            paragraph_count = len([chunk for chunk in re.split(r"\n\s*\n", body) if chunk.strip()])
            quality_score = min(100, 20 + min(len(body) // 30, 50) + min(paragraph_count * 4, 20))
            engagement_score = min(
                100,
                int((row.get("extensions") or {}).get("likes") or 0)
                + int((row.get("extensions") or {}).get("shares") or 0)
                + int((row.get("extensions") or {}).get("comments") or 0),
            )
            rights_clear = str((row.get("extensions") or {}).get("rightsStatus") or "clear").strip() == "clear"
            watermark_clean = str((row.get("extensions") or {}).get("watermarkStatus") or "clean").strip() == "clean"
            rights_score = 100 if rights_clear and watermark_clean else 0
            weighted_total = round(
                (
                    entity_score * weights["entityRelevance"]
                    + authority_score * weights["authorityGrounding"]
                    + quality_score * weights["contentQuality"]
                    + engagement_score * weights["engagementUtility"]
                    + rights_score * weights["rightsCompliance"]
                )
                / max(1, sum(weights.values()))
            )
            asset_count = len(read_json(page_dir / "asset_manifest.json").get("assets", [])) if (page_dir / "asset_manifest.json").exists() else 0
            rewrite_policy = _simple_rewrite_policy(weighted_total, entity_score, authority_score)
            review_status = "approved" if weighted_total >= 45 and rights_score > 0 and entity_score >= 35 else "rejected"
            row["scoreBreakdown"] = {
                "entityRelevanceScore": entity_score,
                "authorityGroundingScore": authority_score,
                "contentQualityScore": quality_score,
                "engagementUtilityScore": engagement_score,
                "rightsAndComplianceScore": rights_score,
                "overallScore": weighted_total,
            }
            row["rewritePolicy"] = rewrite_policy
            row["publishStatus"] = "review_approved" if review_status == "approved" else "review_rejected"
            row["reviewStatus"] = review_status
            row.setdefault("evidenceRefs", [])
            row["evidenceRefs"] = sorted(set(_csv(row.get("evidenceRefs")) + [runtime_rel_ref(page_dir / "source.md")]))
            changed = True
            if review_status == "approved":
                _materialize_topic_candidate(
                    spec=spec,
                    entity=entity,
                    candidate=row,
                    entity_score=entity_score,
                    authority_score=authority_score,
                    quality_score=quality_score,
                    engagement_score=engagement_score,
                    rights_score=rights_score,
                    asset_count=asset_count,
                )
                approved += 1
        if changed:
            write_ndjson(pool_path, pool)
    print(json.dumps({"ok": True, "specId": spec_id, "approved": approved}, ensure_ascii=False))
    return 0


def _topics_for_args(spec: dict[str, Any], args) -> list[str]:
    topics_arg = _csv(getattr(args, "topics", ""))
    if topics_arg:
        return topics_arg
    topic_arg = str(getattr(args, "topic", "") or "").strip()
    if topic_arg:
        return [topic_arg]
    topics = batch._sample_topics(spec, "article") + batch._sample_topics(spec, "image")
    seen: set[str] = set()
    out: list[str] = []
    for topic in topics:
        if topic not in seen:
            seen.add(topic)
            out.append(topic)
    return out


def handle_compose_post(args) -> int:
    ensure_runtime_layout()
    spec, _ = _load_spec(str(args.spec))
    targets = _csv(getattr(args, "targets", "")) or _csv(spec.get("target_envs"))
    topics = _topics_for_args(spec, args)
    results = []
    for topic_id in topics:
        errors, warnings, payload = batch._compose_topic_command(spec, topic_id, targets)
        if errors:
            for error in errors:
                print(f"[crawl compose-post] FAIL: {error}", file=sys.stderr)
            return 1
        for warning in warnings[:40]:
            print(f"[crawl compose-post] WARN: {warning}", file=sys.stderr)
        results.append({"topicId": topic_id, "postCount": len(payload["postRows"])})
    print(json.dumps({"ok": True, "topics": results}, ensure_ascii=False))
    return 0


def handle_review_generated(args) -> int:
    ensure_runtime_layout()
    spec, _ = _load_spec(str(args.spec))
    topics = _topics_for_args(spec, args)
    results = []
    for topic_id in topics:
        errors, warnings, payload = batch._audit_topic_command(spec, topic_id)
        if errors:
            for error in errors:
                print(f"[crawl review-generated] FAIL: {error}", file=sys.stderr)
            return 1
        for warning in warnings[:40]:
            print(f"[crawl review-generated] WARN: {warning}", file=sys.stderr)
        results.append(
            {
                "topicId": topic_id,
                "overallStatus": payload["auditSummary"].get("overallStatus"),
                "overallScore": payload["auditSummary"].get("overallScore"),
            }
        )
    print(json.dumps({"ok": True, "topics": results}, ensure_ascii=False))
    return 0


def handle_publish_approved(args) -> int:
    ensure_runtime_layout()
    spec, _ = _load_spec(str(args.spec))
    topics = _topics_for_args(spec, args)
    published = []
    for topic_id in topics:
        summary_path = batch._audit_summary_path(spec["spec_id"], topic_id)
        if not summary_path.exists():
            continue
        summary = read_json(summary_path)
        if str(summary.get("overallStatus", "")).strip() != "approved":
            continue
        path = publish_status_path(spec["spec_id"], topic_id)
        write_json(
            path,
            {
                "schemaVersion": PUBLISH_STATUS_SCHEMA_VERSION,
                "generatedAt": now_iso(),
                "specId": spec["spec_id"],
                "topicId": topic_id,
                "status": "published",
                "auditSummaryPath": runtime_rel_ref(summary_path),
            },
        )
        published.append(topic_id)
    batch._refresh_discovery_artifacts(spec)
    print(json.dumps({"ok": True, "publishedTopics": published}, ensure_ascii=False))
    return 0


def _published_post_dirs(topic_id: str) -> list[Path]:
    root = batch.publish_topic_dir(topic_id) / "posts"
    if not root.exists():
        return []
    return sorted([path for path in root.iterdir() if path.is_dir()])


def handle_feedback_extract(args) -> int:
    ensure_runtime_layout()
    spec, _ = _load_spec(str(args.spec))
    spec_id = str(spec.get("spec_id", "")).strip()
    entity_rows, entity_by_name = _load_entity_catalog_by_name()
    tag_rows, tag_by_label = _load_tag_catalog_by_label()
    entity_candidates: list[dict[str, Any]] = []
    tag_candidates: list[dict[str, Any]] = []
    relation_candidates: list[dict[str, Any]] = []
    candidate_entity_pattern = re.compile(r"[\u4e00-\u9fff]{2,8}(?:景区|古镇|大桥|寺|山|湖|公园|草原|沟|谷|基地|故居|博物馆)")
    topics = _topics_for_args(spec, args)
    for topic_id in topics:
        for post_dir in _published_post_dirs(topic_id):
            post_id = post_dir.name
            article_text = read_text(post_dir / "article.md") if (post_dir / "article.md").exists() else ""
            gallery_text = read_text(post_dir / "gallery.md") if (post_dir / "gallery.md").exists() else ""
            blob = f"{article_text}\n{gallery_text}"
            for row in entity_rows:
                canonical = str(row.get("canonicalName", "")).strip()
                if canonical and canonical in blob:
                    entity_candidates.append(
                        build_feedback_candidate_row(
                            kind="entity",
                            value=canonical,
                            source_post_id=post_id,
                            source_topic_id=topic_id,
                            evidence_excerpt=_pick_excerpt(blob, canonical),
                            entity_id=str(row.get("entityId", "")).strip(),
                        )
                    )
                    relation_candidates.append(
                        build_feedback_candidate_row(
                            kind="relation",
                            value="entity_post",
                            source_post_id=post_id,
                            source_topic_id=topic_id,
                            evidence_excerpt=_pick_excerpt(blob, canonical),
                            entity_id=str(row.get("entityId", "")).strip(),
                        )
                    )
            for row in tag_rows:
                label = str(row.get("label", "")).strip()
                if label and label in blob:
                    tag_candidates.append(
                        build_feedback_candidate_row(
                            kind="tag",
                            value=label,
                            source_post_id=post_id,
                            source_topic_id=topic_id,
                            evidence_excerpt=_pick_excerpt(blob, label),
                            tag_id=str(row.get("tagId", "")).strip(),
                        )
                    )
                    relation_candidates.append(
                        build_feedback_candidate_row(
                            kind="relation",
                            value="tag_post",
                            source_post_id=post_id,
                            source_topic_id=topic_id,
                            evidence_excerpt=_pick_excerpt(blob, label),
                            tag_id=str(row.get("tagId", "")).strip(),
                        )
                    )
            known_values = {str(item.get("value", "")).strip() for item in entity_candidates + tag_candidates}
            for candidate in candidate_entity_pattern.findall(blob):
                if candidate in known_values:
                    continue
                entity_candidates.append(
                    build_feedback_candidate_row(
                        kind="entity",
                        value=candidate,
                        source_post_id=post_id,
                        source_topic_id=topic_id,
                        evidence_excerpt=_pick_excerpt(blob, candidate),
                    )
                )
    write_ndjson(feedback_candidate_path(spec_id, "entity"), entity_candidates)
    write_ndjson(feedback_candidate_path(spec_id, "tag"), tag_candidates)
    write_ndjson(feedback_candidate_path(spec_id, "relation"), relation_candidates)
    print(json.dumps({"ok": True, "entityCandidates": len(entity_candidates), "tagCandidates": len(tag_candidates)}, ensure_ascii=False))
    return 0


def handle_feedback_verify(args) -> int:
    ensure_runtime_layout()
    spec, _ = _load_spec(str(args.spec))
    spec_id = str(spec.get("spec_id", "")).strip()
    entity_rows, entity_by_name = _load_entity_catalog_by_name()
    tag_rows, tag_by_label = _load_tag_catalog_by_label()
    entity_candidates = read_ndjson(feedback_candidate_path(spec_id, "entity"))
    tag_candidates = read_ndjson(feedback_candidate_path(spec_id, "tag"))
    verified_entity_post: list[dict[str, Any]] = []
    verified_tag_post: list[dict[str, Any]] = []
    verified_entity_tag: list[dict[str, Any]] = []
    pending_entities: list[dict[str, Any]] = []
    pending_tags: list[dict[str, Any]] = []
    post_to_entities: dict[str, set[str]] = {}
    post_to_tags: dict[str, set[str]] = {}

    for row in entity_candidates:
        value = str(row.get("value", "")).strip()
        source_post_id = str(row.get("sourcePostId", "")).strip()
        source_topic_id = str(row.get("sourceTopicId", "")).strip()
        entity_id = str(row.get("entityId", "")).strip()
        if not entity_id and value in entity_by_name:
            entity_id = str(entity_by_name[value].get("entityId", "")).strip()
        if entity_id:
            post_to_entities.setdefault(source_post_id, set()).add(entity_id)
            verified_entity_post.append(
                build_relation_row(
                    from_id=entity_id,
                    to_id=source_post_id,
                    relation_type="entity_mentions_post",
                    evidence_refs=[source_topic_id, str(row.get("evidenceExcerpt", "")).strip()],
                )
            )
        else:
            pending_entities.append(dict(row))

    for row in tag_candidates:
        value = str(row.get("value", "")).strip()
        source_post_id = str(row.get("sourcePostId", "")).strip()
        source_topic_id = str(row.get("sourceTopicId", "")).strip()
        tag_id = str(row.get("tagId", "")).strip()
        if not tag_id and value in tag_by_label:
            tag_id = str(tag_by_label[value].get("tagId", "")).strip()
        if tag_id:
            post_to_tags.setdefault(source_post_id, set()).add(tag_id)
            verified_tag_post.append(
                build_relation_row(
                    from_id=tag_id,
                    to_id=source_post_id,
                    relation_type="tag_describes_post",
                    evidence_refs=[source_topic_id, str(row.get("evidenceExcerpt", "")).strip()],
                )
            )
        else:
            pending_tags.append(dict(row))

    for post_id, entity_ids in post_to_entities.items():
        for entity_id in entity_ids:
            for tag_id in post_to_tags.get(post_id, set()):
                verified_entity_tag.append(
                    build_relation_row(
                        from_id=entity_id,
                        to_id=tag_id,
                        relation_type="entity_related_tag",
                        evidence_refs=[post_id],
                    )
                )

    upsert_ndjson_rows(graph_relation_path("entity_post"), verified_entity_post, key_fields=["fromId", "toId", "relationType"])
    upsert_ndjson_rows(graph_relation_path("tag_post"), verified_tag_post, key_fields=["fromId", "toId", "relationType"])
    upsert_ndjson_rows(graph_relation_path("entity_tag"), verified_entity_tag, key_fields=["fromId", "toId", "relationType"])
    write_ndjson(feedback_candidate_path(spec_id, "pending_entity"), pending_entities)
    write_ndjson(feedback_candidate_path(spec_id, "pending_tag"), pending_tags)
    print(json.dumps({"ok": True, "verifiedEntityPost": len(verified_entity_post), "verifiedTagPost": len(verified_tag_post), "pendingEntities": len(pending_entities), "pendingTags": len(pending_tags)}, ensure_ascii=False))
    return 0


def handle_graph_verify(args) -> int:
    ensure_runtime_layout()
    entities = {str(row.get("entityId", "")).strip() for row in load_entities_catalog() if str(row.get("entityId", "")).strip()}
    tags = {str(row.get("tagId", "")).strip() for row in load_tags_catalog() if str(row.get("tagId", "")).strip()}
    errors: list[str] = []
    for kind in ("entity_tag", "entity_post", "tag_post"):
        for row in read_ndjson(graph_relation_path(kind)):
            from_id = str(row.get("fromId", "")).strip()
            to_id = str(row.get("toId", "")).strip()
            relation_type = str(row.get("relationType", "")).strip()
            evidence_refs = _csv(row.get("evidenceRefs"))
            if not relation_type:
                errors.append(f"{kind} 缺少 relationType")
            if not evidence_refs:
                errors.append(f"{kind} {from_id}->{to_id} 缺少 evidenceRefs")
            if kind == "entity_tag":
                if from_id not in entities:
                    errors.append(f"entity_tag 未知实体 {from_id}")
                if to_id not in tags:
                    errors.append(f"entity_tag 未知标签 {to_id}")
            elif kind == "entity_post":
                if from_id not in entities:
                    errors.append(f"entity_post 未知实体 {from_id}")
            elif kind == "tag_post":
                if from_id not in tags:
                    errors.append(f"tag_post 未知标签 {from_id}")
    if errors:
        for error in errors[:80]:
            print(f"[crawl graph-verify] FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "status": "verified"}, ensure_ascii=False))
    return 0


def handle_auto_run(args) -> int:
    ensure_runtime_layout()
    spec, _ = _load_spec(str(args.spec))
    spec_id = str(spec.get("spec_id", "")).strip()

    def ns(**kwargs):
        return argparse.Namespace(**kwargs)

    if not instruction_profile_path(spec_id).exists():
        instruction_args = ns(
            spec=str(args.spec),
            spec_id="",
            instruction=str(getattr(args, "instruction", "") or spec.get("query", "")),
            verticals=str(getattr(args, "verticals", "") or "travel"),
            tag_refs=",".join(_csv(spec.get("tag_refs"))),
            platform_priority=str(getattr(args, "platform_priority", "")),
            coverage=str(getattr(args, "coverage", "") or "wide"),
            content_modes=str(getattr(args, "content_modes", "") or "article,image"),
            style=str(getattr(args, "style", "") or "balanced"),
            chapter_preference=str(getattr(args, "chapter_preference", "") or "grounded"),
            intent=str(getattr(args, "intent", "") or "discover_and_publish"),
            regions=str(getattr(args, "regions", "") or ""),
        )
        if handle_instruction_build(instruction_args) != 0:
            return 1

    if handle_tag_catalog_build(ns()) != 0:
        return 1
    if handle_entity_catalog_build(ns(catalog=str(getattr(args, "entity_catalog", "") or ""))) != 0:
        return 1
    if handle_entities_by_tag(ns(spec=str(args.spec), spec_id="", tag_refs="", tag_labels="", tag_ids="")) != 0:
        return 1
    if handle_authority_sync(ns(spec=str(args.spec), spec_id="")) != 0:
        return 1
    if handle_authority_review(ns(spec=str(args.spec), spec_id="")) != 0:
        return 1
    if handle_content_discover(ns(spec=str(args.spec), spec_id="", seed=str(getattr(args, "seed", "") or ""))) != 0:
        return 1
    if not bool(getattr(args, "skip_hydrate", False)):
        if handle_content_hydrate(ns(spec=str(args.spec), spec_id="")) != 0:
            return 1
    if handle_content_review(ns(spec=str(args.spec), spec_id="")) != 0:
        return 1
    if handle_compose_post(ns(spec=str(args.spec), topics=str(getattr(args, "topics", "") or ""), topic="", targets=str(getattr(args, "targets", "") or ""))) != 0:
        return 1
    if handle_review_generated(ns(spec=str(args.spec), topics=str(getattr(args, "topics", "") or ""), topic="")) != 0:
        return 1
    if handle_publish_approved(ns(spec=str(args.spec), topics=str(getattr(args, "topics", "") or ""), topic="")) != 0:
        return 1
    if handle_feedback_extract(ns(spec=str(args.spec), topics=str(getattr(args, "topics", "") or ""), topic="")) != 0:
        return 1
    if handle_feedback_verify(ns(spec=str(args.spec))) != 0:
        return 1
    print(json.dumps({"ok": True, "specId": spec_id, "workflow": "completed"}, ensure_ascii=False))
    return 0

