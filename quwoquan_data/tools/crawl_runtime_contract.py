from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from common import (
    ENTITY_CATALOG_ROOT,
    GRAPH_ROOT,
    RUNS_ROOT,
    TAG_CATALOG_ROOT,
    ensure_directory,
    ensure_runtime_layout,
    now_iso,
    read_json,
    read_ndjson,
    runtime_rel_ref,
    write_json,
    write_ndjson,
)

INSTRUCTION_PROFILE_SCHEMA_VERSION = "quwoquan_data.instruction_profile"
ENTITY_CATALOG_SCHEMA_VERSION = "quwoquan_data.entity_catalog"
TAG_CATALOG_SCHEMA_VERSION = "quwoquan_data.tag_catalog"
RELATION_SCHEMA_VERSION = "quwoquan_data.relation"
AUTHORITY_PROFILE_SCHEMA_VERSION = "quwoquan_data.authority_profile"
POST_CANDIDATE_SCHEMA_VERSION = "quwoquan_data.post_candidate"
PUBLISH_STATUS_SCHEMA_VERSION = "quwoquan_data.publish_status"
ENTITY_SELECTION_SCHEMA_VERSION = "quwoquan_data.entity_selection"
FEEDBACK_CANDIDATE_SCHEMA_VERSION = "quwoquan_data.feedback_candidate"


def ensure_dual_source_layout() -> None:
    ensure_runtime_layout()
    for path in (
        ENTITY_CATALOG_ROOT,
        TAG_CATALOG_ROOT,
        GRAPH_ROOT,
    ):
        ensure_directory(path)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    if normalized:
        return normalized[:64]
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return f"item_{digest[:16]}"


def stable_entity_id(name: str, entity_type: str = "") -> str:
    prefix = _slugify(entity_type or "entity")
    digest = hashlib.sha1(f"{entity_type}|{name}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def stable_tag_id(label: str, tag_type: str = "") -> str:
    prefix = _slugify(tag_type or "tag")
    digest = hashlib.sha1(f"{tag_type}|{label}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def entities_catalog_path(name: str = "entities.ndjson") -> Path:
    ensure_dual_source_layout()
    return ENTITY_CATALOG_ROOT / name


def tags_catalog_path(name: str = "tags.ndjson") -> Path:
    ensure_dual_source_layout()
    return TAG_CATALOG_ROOT / name


def graph_relation_path(kind: str) -> Path:
    ensure_dual_source_layout()
    mapping = {
        "entity_tag": "entity_tag_relations.ndjson",
        "entity_post": "entity_post_relations.ndjson",
        "tag_post": "tag_post_relations.ndjson",
    }
    filename = mapping.get(kind, f"{_slugify(kind)}.ndjson")
    return GRAPH_ROOT / filename


def instruction_profile_path(spec_id: str) -> Path:
    ensure_dual_source_layout()
    return RUNS_ROOT / spec_id / "instruction_profile.json"


def selected_entities_path(spec_id: str) -> Path:
    ensure_dual_source_layout()
    return RUNS_ROOT / spec_id / "selected_entities.ndjson"


def selected_tags_path(spec_id: str) -> Path:
    ensure_dual_source_layout()
    return RUNS_ROOT / spec_id / "selected_tags.ndjson"


def entity_run_dir(spec_id: str, entity_id: str) -> Path:
    ensure_dual_source_layout()
    return RUNS_ROOT / spec_id / "entities" / entity_id


def entity_authority_pool_path(spec_id: str, entity_id: str) -> Path:
    return entity_run_dir(spec_id, entity_id) / "authority_pool.ndjson"


def entity_content_pool_path(spec_id: str, entity_id: str) -> Path:
    return entity_run_dir(spec_id, entity_id) / "content_pool.ndjson"


def entity_authority_profile_path(spec_id: str, entity_id: str) -> Path:
    return entity_run_dir(spec_id, entity_id) / "authority_profile.json"


def entity_content_page_dir(spec_id: str, entity_id: str, candidate_id: str) -> Path:
    return entity_run_dir(spec_id, entity_id) / "content" / candidate_id


def publish_status_path(spec_id: str, topic_id: str) -> Path:
    return RUNS_ROOT / spec_id / "topics" / topic_id / "publish_status.json"


def feedback_dir(spec_id: str) -> Path:
    path = RUNS_ROOT / spec_id / "feedback"
    ensure_directory(path)
    return path


def feedback_candidate_path(spec_id: str, kind: str) -> Path:
    mapping = {
        "entity": "entity_candidates.ndjson",
        "tag": "tag_candidates.ndjson",
        "relation": "relation_candidates.ndjson",
        "pending_entity": "pending_entity_candidates.ndjson",
        "pending_tag": "pending_tag_candidates.ndjson",
    }
    return feedback_dir(spec_id) / mapping.get(kind, f"{_slugify(kind)}.ndjson")


def build_instruction_profile(
    *,
    spec_id: str,
    raw_instruction: str,
    intent: str,
    target_verticals: list[str],
    tag_refs: list[str],
    platform_priority: list[str],
    coverage_preference: str,
    content_modes: list[str],
    rewrite_preferences: dict[str, Any],
    feedback_policy: dict[str, Any],
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": INSTRUCTION_PROFILE_SCHEMA_VERSION,
        "generatedAt": now_iso(),
        "specId": spec_id,
        "rawInstruction": raw_instruction,
        "intent": intent,
        "targetVerticals": target_verticals,
        "tagRefs": tag_refs,
        "platformPriority": platform_priority,
        "coveragePreference": coverage_preference,
        "contentModes": content_modes,
        "rewritePreferences": rewrite_preferences,
        "feedbackPolicy": feedback_policy,
        "extensions": extensions or {},
    }


def build_entity_row(
    *,
    entity_id: str,
    canonical_name: str,
    entity_type: str,
    authority_profile_ref: str = "",
    aliases: list[str] | None = None,
    entity_ref: str = "",
    tag_refs: list[str] | None = None,
    topic_id: str = "",
    source: str = "",
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": ENTITY_CATALOG_SCHEMA_VERSION,
        "entityId": entity_id,
        "canonicalName": canonical_name,
        "entityType": entity_type,
        "authorityProfileRef": authority_profile_ref,
        "aliases": aliases or [],
        "entityRef": entity_ref,
        "tagRefs": tag_refs or [],
        "topicId": topic_id,
        "source": source,
        "extensions": extensions or {},
    }


def build_tag_row(
    *,
    tag_id: str,
    label: str,
    tag_type: str,
    tag_ref: str = "",
    aliases: list[str] | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": TAG_CATALOG_SCHEMA_VERSION,
        "tagId": tag_id,
        "label": label,
        "tagType": tag_type,
        "tagRef": tag_ref,
        "aliases": aliases or [],
        "extensions": extensions or {},
    }


def build_post_candidate_row(
    *,
    post_id: str,
    entity_id: str,
    source_url: str,
    source_type: str,
    media_type: str,
    source_role: str,
    fetch_policy: str,
    topic_id: str = "",
    title: str = "",
    snippet: str = "",
    rewrite_policy: str = "hold_for_reference",
    publish_status: str = "discovered",
    platform: str = "",
    discovery_query: str = "",
    evidence_refs: list[str] | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": POST_CANDIDATE_SCHEMA_VERSION,
        "postId": post_id,
        "entityId": entity_id,
        "topicId": topic_id,
        "sourceUrl": source_url,
        "sourceType": source_type,
        "mediaType": media_type,
        "sourceRole": source_role,
        "fetchPolicy": fetch_policy,
        "title": title,
        "snippet": snippet,
        "rewritePolicy": rewrite_policy,
        "publishStatus": publish_status,
        "platform": platform,
        "discoveryQuery": discovery_query,
        "evidenceRefs": evidence_refs or [],
        "extensions": extensions or {},
    }


def build_relation_row(
    *,
    from_id: str,
    to_id: str,
    relation_type: str,
    evidence_refs: list[str],
    status: str = "verified",
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": RELATION_SCHEMA_VERSION,
        "fromId": from_id,
        "toId": to_id,
        "relationType": relation_type,
        "status": status,
        "evidenceRefs": evidence_refs,
        "extensions": extensions or {},
    }


def build_feedback_candidate_row(
    *,
    kind: str,
    value: str,
    source_post_id: str,
    source_topic_id: str,
    evidence_excerpt: str,
    status: str = "candidate",
    entity_id: str = "",
    tag_id: str = "",
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": FEEDBACK_CANDIDATE_SCHEMA_VERSION,
        "kind": kind,
        "value": value,
        "sourcePostId": source_post_id,
        "sourceTopicId": source_topic_id,
        "entityId": entity_id,
        "tagId": tag_id,
        "evidenceExcerpt": evidence_excerpt,
        "status": status,
        "extensions": extensions or {},
    }


def upsert_ndjson_rows(path: Path, rows: list[dict[str, Any]], *, key_fields: list[str]) -> list[dict[str, Any]]:
    existing = read_ndjson(path)
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in existing + rows:
        key = tuple(str(row.get(field, "")).strip() for field in key_fields)
        if not any(key):
            continue
        merged[key] = row
    result = list(merged.values())
    write_ndjson(path, result)
    return result


def replace_ndjson_rows(path: Path, rows: list[dict[str, Any]], *, key_fields: list[str]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(str(row.get(field, "")).strip() for field in key_fields)
        if not any(key):
            continue
        merged[key] = row
    result = list(merged.values())
    write_ndjson(path, result)
    return result


def load_instruction_profile(spec_id: str) -> dict[str, Any]:
    path = instruction_profile_path(spec_id)
    return read_json(path) if path.exists() else {}


def write_instruction_profile(spec_id: str, profile: dict[str, Any]) -> Path:
    path = instruction_profile_path(spec_id)
    write_json(path, profile)
    return path


def load_entities_catalog(name: str = "entities.ndjson") -> list[dict[str, Any]]:
    return read_ndjson(entities_catalog_path(name))


def load_tags_catalog(name: str = "tags.ndjson") -> list[dict[str, Any]]:
    return read_ndjson(tags_catalog_path(name))


def update_entity_authority_profile_ref(entity_row: dict[str, Any], profile_path: Path) -> dict[str, Any]:
    updated = dict(entity_row)
    updated["authorityProfileRef"] = runtime_rel_ref(profile_path)
    return updated

