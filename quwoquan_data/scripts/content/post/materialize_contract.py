"""Post materialization contract normalization and source-reference helpers."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from pathlib import Path
import shutil
from typing import Any, Mapping

from core.article_package import (
    build_markdown_frontmatter,
    compute_asset_manifest_sha256,
    compute_document_sha256,
    copy_asset_files,
)
from content.execution.asset_registry import allocate_post_asset_id, load_execution_asset_registry
from content.execution.runtime_state import load_execution_runtime_state
from core.paths import RUNTIME_ROOT, execution_root, relative_execution_ref
from core.io import read_json, write_json
from content.review.ledger import entities_path
from content.post.article.draft_io import is_placeholder, read_draft_article, read_draft_meta, read_writing_pack
from core.post_evidence_chain import (
    SOURCE_REFS_SCHEMA,
    build_finalization_report,
    build_source_refs_snapshot,
)
from core.provenance import build_provenance
from content.execution.runtime_contract import stage_execution_context
from core.intersection_signal import build_intersection_hints
from content.review.annotation.entity_annotation import annotate_inline, normalize_link_ref


def _resolve_semantic_mentions(
    execution_id: str,
    ref: str,
    compose_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """合并 review 阶段 entities sidecar 的 semanticMentions 与 compose payload 内联 mention。

    sidecar（build_entities_sidecar 产出）是实体/标签 mention 的治理真相源（含 offset/status/
    candidateId/targetRef）；compose payload 内联 mention 作补充。按 mentionId 去重，sidecar 优先。
    manifest 存全量 mention（含 pending_review）；active entityRefs/tagRefs 由端云按
    semanticMentions.published_only 投影，不在此过滤（与服务侧 importer/contract 对齐）。
    """
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _absorb(rows: Any) -> None:
        if not isinstance(rows, (list, tuple)):
            return
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            mention_id = str(row.get("mentionId") or "")
            key = mention_id or json.dumps(row, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(row))

    try:
        sidecar_path: Path | None = entities_path(execution_id, ref)
    except KeyError:
        sidecar_path = None
    if sidecar_path is not None and sidecar_path.is_file():
        try:
            sidecar = read_json(sidecar_path)
        except (OSError, ValueError):
            sidecar = {}
        if isinstance(sidecar, Mapping):
            _absorb(sidecar.get("semanticMentions"))
    _absorb(compose_payload.get("semanticMentions"))
    return merged


def _semantic_mention_id(source_ref: str, kind: str, target_ref: str) -> str:
    digest = hashlib.sha1(f"{source_ref}|{kind}|{target_ref}|manifest".encode("utf-8")).hexdigest()[:24]
    return f"mention_{digest}"


def _semantic_surface_from_ref(target_ref: str) -> str:
    text = str(target_ref or "").strip().strip("/")
    if not text:
        return ""
    if ":" in text and "/" not in text:
        return text.split(":")[-1]
    return text.split("/")[-1]


def _published_semantic_targets(mentions: list[dict[str, Any]], kind: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in mentions:
        if str(row.get("kind") or "") != kind:
            continue
        if str(row.get("status") or "") != "published":
            continue
        target = str(row.get("targetRef") or "").strip()
        if not target or target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out


def _ensure_published_manifest_mentions(
    mentions: list[dict[str, Any]],
    ref: str,
    *,
    entity_refs: list[str],
    tag_refs: list[str],
) -> list[dict[str, Any]]:
    """Active refs are compatibility projections; semanticMentions is the source.

    Some refs come from brief/tag taxonomy rather than inline extraction.  Publish
    them as manifest-level semantic mentions so importer read-only projection
    checks can derive the same active entityRefs/tagRefs without trusting the
    compatibility fields.
    """
    merged = [dict(row) for row in mentions]
    existing = {
        (str(row.get("kind") or ""), str(row.get("status") or ""), str(row.get("targetRef") or ""))
        for row in merged
    }

    def _append(kind: str, target_ref: str) -> None:
        target = str(target_ref or "").strip()
        if not target or (kind, "published", target) in existing:
            return
        existing.add((kind, "published", target))
        merged.append(
            {
                "mentionId": _semantic_mention_id(ref, kind, target),
                "sourceRef": ref,
                "targetRef": target,
                "kind": kind,
                "surface": _semantic_surface_from_ref(target),
                "location": "manifest",
                "occurrence": 0,
                "status": "published",
            }
        )

    for entity_ref in entity_refs:
        _append("entity", normalize_link_ref(str(entity_ref)))
    for tag_ref in tag_refs:
        _append("tag", str(tag_ref))
    return merged


def _resolve_entity_download_dir(
    execution_id: str,
    entity_refs: list[str],
) -> Path | None:
    from content.source.source_unit import find_entity_object_dirs, iter_source_units

    for ref in entity_refs:
        if not str(ref).strip():
            continue
        for obj in find_entity_object_dirs(execution_id, str(ref).strip()):
            for unit in iter_source_units(obj):
                assets_dir = unit / "assets"
                if assets_dir.is_dir():
                    return assets_dir
    return None


def _relativize_ref(value: str, execution_id: str) -> str:
    """执行工作包内路径转为相对引用，避免运行根泄漏进发布契约。"""

    s = str(value or "")
    if not s:
        return s
    base = execution_root(execution_id).resolve()
    execution_id = base.name
    normalized_full = s.replace("\\", "/")
    for prefix in (
        f".qwq_output/data/tasks/{execution_id}/",
        f"data/tasks/{execution_id}/",
        f"tasks/{execution_id}/",
    ):
        if normalized_full.startswith(prefix):
            return normalized_full[len(prefix) :]
    marker = f"/tasks/{execution_id}/"
    if marker in normalized_full:
        return normalized_full.split(marker, 1)[1]
    p = Path(s)
    if not p.is_absolute():
        runtime_candidates = []
        normalized = s.lstrip("./")
        runtime_candidates.append(RUNTIME_ROOT / normalized)
        for candidate in runtime_candidates:
            try:
                candidate_resolved = candidate.resolve()
                candidate_resolved.relative_to(base)
            except (ValueError, OSError):
                continue
            return relative_execution_ref(candidate_resolved, execution_id)
        return s
    try:
        p.resolve().relative_to(base)
    except (ValueError, OSError):
        return s
    return relative_execution_ref(p, execution_id)


def _source_ref_from_asset_ref(source_asset_ref: str) -> str:
    normalized = str(source_asset_ref or "").replace("\\", "/").strip()
    if not normalized or "/assets/" not in normalized:
        return ""
    source_unit = normalized.split("/assets/", 1)[0].rstrip("/")
    if not source_unit:
        return ""
    return f"{source_unit}/source.md"


def _materialized_asset_refs(
    asset: Mapping[str, Any],
    *,
    execution_id: str,
) -> tuple[str, str]:
    source_asset_ref = _relativize_ref(
        str(asset.get("sourceAssetRef") or asset.get("sourcePath") or ""),
        execution_id,
    )
    source_ref = _relativize_ref(str(asset.get("sourceRef") or ""), execution_id)
    if source_ref and "/assets/" in source_ref:
        if not source_asset_ref:
            source_asset_ref = source_ref
        source_ref = ""
    if not source_ref:
        source_ref = _source_ref_from_asset_ref(source_asset_ref)
    return source_ref, source_asset_ref


def _materialized_alignment_evidence(asset: Mapping[str, Any]) -> str:
    for key in ("alignmentEvidence", "imageTextAlignment", "nearbyText", "relevance"):
        value = str(asset.get(key) or "").strip()
        if value:
            return value
    caption = str(asset.get("caption") or "").strip()
    return f"图片说明与正文关联：{caption}" if caption else ""


def _annotate_manifest_entities(article_md: str, entity_refs: list[str]) -> str:
    """Materialized posts must keep article links and manifest.entityRefs closed."""
    dictionary: dict[str, str] = {}
    for raw_ref in entity_refs:
        ref = normalize_link_ref(str(raw_ref))
        name = ref.strip("/").split("/")[-1] if ref else ""
        if name:
            dictionary[name] = ref
    if not dictionary:
        return article_md
    annotated_article, _ = annotate_inline(article_md, dictionary)
    return annotated_article


def _canonical_entity_id_from_publish_ref(ref: str) -> str:
    normalized = normalize_link_ref(str(ref))
    parts = [part for part in normalized.strip("/").split("/") if part]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    if len(parts) < 3:
        return ""
    _, etype, name = parts[0], parts[1], "/".join(parts[2:])
    etype_slug = etype.strip().replace(" ", "_")
    name_slug = name.strip().replace(" ", "_")
    if not etype_slug or not name_slug:
        return ""
    return f"entity:{etype_slug}:{name_slug}"


def _normalized_runtime_entity_refs(entity_refs: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for ref in entity_refs:
        canonical = _canonical_entity_id_from_publish_ref(ref)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out


def _publication_story_spine(compose_payload: dict) -> dict | list:
    """发布包只保留运行需要的叙事摘要，质量证据留在 provenance/review。"""
    raw = (
        compose_payload.get("storySpine")
        or compose_payload.get("progression")
        or compose_payload.get("sectionIntents")
        or []
    )
    if not isinstance(raw, dict):
        return raw
    return {
        key: raw[key]
        for key in (
            "primaryEntity",
            "routeEntities",
            "beats",
            "sourceNote",
            "relatedTopics",
            "mustIncludeFacts",
        )
        if key in raw
    }


_IMAGE_SOURCE_FIELDS = (
    "sourceCollectionId",
    "creator",
    "collectionPageUrl",
    "license",
    "termsUrl",
    "authorizationProof",
)


def _source_fact(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return value
    return None


def _source_fact_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_source_fact(payload: Mapping[str, Any], field: str) -> Any:
    return _source_fact(payload.get(field))


def _image_source_contract(
    compose_payload: Mapping[str, Any],
    assets: list[dict[str, Any]],
    *,
    ref: str,
) -> dict[str, Any]:
    """Resolve one work-level source identity and reject mixed-source image sets."""
    resolved: dict[str, Any] = {}
    required_fields = {"sourceCollectionId", "creator", "collectionPageUrl", "license"}
    for field in _IMAGE_SOURCE_FIELDS:
        work_value = _canonical_source_fact(compose_payload, field)
        per_asset_values = [_canonical_source_fact(asset, field) for asset in assets]
        asset_values = [value for value in per_asset_values if value is not None]
        distinct = {_source_fact_key(value): value for value in asset_values}
        if len(distinct) > 1:
            raise RuntimeError(f"{ref}: image assets must share one {field}")
        if (
            work_value is None
            and field in required_fields
            and asset_values
            and len(asset_values) != len(assets)
        ):
            raise RuntimeError(f"{ref}: every image asset must declare the same {field}")
        if work_value is not None and distinct:
            only_asset_value = next(iter(distinct.values()))
            if _source_fact_key(work_value) != _source_fact_key(only_asset_value):
                raise RuntimeError(f"{ref}: image work {field} conflicts with asset source")
        value = work_value if work_value is not None else next(iter(distinct.values()), None)
        if value is not None:
            resolved[field] = value

    work_has_proof = _canonical_source_fact(
        compose_payload, "termsUrl"
    ) is not None or _canonical_source_fact(compose_payload, "authorizationProof") is not None
    if not work_has_proof:
        proof_keys: set[str] = set()
        for asset in assets:
            terms = _canonical_source_fact(asset, "termsUrl")
            authorization = _canonical_source_fact(asset, "authorizationProof")
            if terms is None and authorization is None:
                raise RuntimeError(f"{ref}: every image asset must declare license proof")
            proof_keys.add(_source_fact_key({"termsUrl": terms, "authorizationProof": authorization}))
        if len(proof_keys) > 1:
            raise RuntimeError(f"{ref}: image assets must share one license proof")

    if "collectionPageUrl" not in resolved:
        urls = [str(url).strip() for url in (compose_payload.get("sourceUrls") or []) if str(url).strip()]
        if len(set(urls)) == 1:
            resolved["collectionPageUrl"] = urls[0]
    missing = [
        field
        for field in ("sourceCollectionId", "creator", "collectionPageUrl", "license")
        if resolved.get(field) in (None, "", {})
    ]
    if not resolved.get("termsUrl") and not resolved.get("authorizationProof"):
        missing.append("license proof (termsUrl or authorizationProof)")
    if missing:
        raise RuntimeError(f"{ref}: image source contract missing {', '.join(missing)}")
    return resolved


def _materialized_source_refs_snapshot(
    execution_id: str,
    *,
    base_source_ref: str,
    is_image: bool,
) -> dict[str, Any]:
    """Build the final object's single-base-source reference snapshot."""
    if not str(base_source_ref or "").strip():
        return {
            "schema": SOURCE_REFS_SCHEMA,
            "baseSourceRef": None,
            "sources": [],
            "note": "no single base source unit (multi-entity route or external image collection)",
        }
    try:
        return build_source_refs_snapshot(
            execution_id,
            base_source_ref=base_source_ref,
        )
    except FileNotFoundError as exc:
        if not is_image:
            raise
        return {
            "schema": SOURCE_REFS_SCHEMA,
            "baseSourceRef": None,
            "sources": [],
            "note": f"image evidence ref unresolved, indexed without mirror: {exc}",
        }
