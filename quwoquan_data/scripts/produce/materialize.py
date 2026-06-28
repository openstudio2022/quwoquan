"""Materialize approved compose results into post packages."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from pathlib import Path
import shutil
from typing import Any, Mapping

from _common.article_package import (
    MARKDOWN_VERSION,
    compute_asset_manifest_sha256,
    compute_document_sha256,
    copy_asset_files,
)
from _common.batch_asset_registry import allocate_post_asset_id, load_batch_asset_registry
from _common.batch_manifest import load_batch_manifest
from _common.paths import DATA_ROOT, RUNTIME_ROOT, batch_root, relative_batch_ref
from _common.io import read_json, write_json
from _common.review_ledger import entities_path
from _common.draft_io import is_placeholder, read_draft_article, read_draft_meta, read_writing_pack
from _common.post_evidence_chain import (
    SOURCE_REFS_SCHEMA,
    build_finalization_report,
    build_source_refs_snapshot,
)
from _common.provenance import build_provenance
from _common.intersection_signal import build_intersection_hints
from _common.entity_annotation import annotate_inline, normalize_link_ref
from produce.materialize_residue_cleanup import prune_unregistered_post_residue


def _resolve_semantic_mentions(
    task_id: str,
    batch_id: str,
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
        sidecar_path: Path | None = entities_path(task_id, batch_id, ref)
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
    task_id: str,
    batch_id: str,
    entity_refs: list[str],
) -> Path | None:
    from _common.source_unit import find_entity_object_dirs, iter_source_units

    for ref in entity_refs:
        if not str(ref).strip():
            continue
        for obj in find_entity_object_dirs(task_id, batch_id, str(ref).strip()):
            for unit in iter_source_units(obj):
                assets_dir = unit / "assets"
                if assets_dir.is_dir():
                    return assets_dir
    return None


def _relativize_ref(value: str, task_id: str, batch_id: str) -> str:
    """batch 内绝对路径 → 相对 batch 根；batch 外或已相对则原样返回（禁绝对路径进发布契约）。"""

    s = str(value or "")
    if not s:
        return s
    base = batch_root(task_id, batch_id).resolve()
    # 顶层批次目录名 = {intentLabel}-{taskHash}__{batch_id}（取自真实 batch 根，含任务消歧哈希）。
    batch_dir = base.name
    batch_prefix = f"batches/{batch_dir}/"
    if s.startswith(batch_prefix):
        return s[len(batch_prefix) :]
    marker = f"/batches/{batch_dir}/"
    normalized_full = s.replace("\\", "/")
    if marker in normalized_full:
        return normalized_full.split(marker, 1)[1]
    p = Path(s)
    if not p.is_absolute():
        runtime_candidates = []
        normalized = s.lstrip("./")
        if normalized.startswith("quwoquan_data/runtime/"):
            runtime_candidates.append(DATA_ROOT.parent / normalized)
        runtime_candidates.append(RUNTIME_ROOT / normalized)
        for candidate in runtime_candidates:
            try:
                candidate_resolved = candidate.resolve()
                candidate_resolved.relative_to(base)
            except (ValueError, OSError):
                continue
            return relative_batch_ref(candidate_resolved, task_id, batch_id)
        return s
    try:
        p.resolve().relative_to(base)
    except (ValueError, OSError):
        return s
    return relative_batch_ref(p, task_id, batch_id)


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
    task_id: str,
    batch_id: str,
) -> tuple[str, str]:
    source_asset_ref = _relativize_ref(
        str(asset.get("sourceAssetRef") or asset.get("sourcePath") or ""),
        task_id,
        batch_id,
    )
    source_ref = _relativize_ref(str(asset.get("sourceRef") or ""), task_id, batch_id)
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


def _manifest_time_fact(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    text = str(value or "").strip()
    return text or None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _materialized_manifest_times(
    compose_payload: dict[str, Any],
    review_payload: dict[str, Any],
    batch_manifest: Mapping[str, Any],
) -> tuple[str, str]:
    created_at = (
        _manifest_time_fact(compose_payload, "createdAt")
        or _manifest_time_fact(review_payload, "createdAt")
        or str(batch_manifest.get("createdAt") or "").strip()
        or _now_iso()
    )
    updated_at = (
        _manifest_time_fact(compose_payload, "updatedAt")
        or _manifest_time_fact(review_payload, "updatedAt")
        or str(batch_manifest.get("updatedAt") or "").strip()
        or created_at
    )
    return created_at, updated_at


_IMAGE_SOURCE_ALIASES = {
    "sourceCollectionId": ("sourceCollectionId", "collectionId", "sourceId"),
    "creator": ("creator", "credit"),
    "collectionPageUrl": (
        "collectionPageUrl",
        "page",
        "sourcePage",
        "sourcePageUrl",
        "sourceUrl",
        "url",
        "sourceRef",
    ),
    "license": ("license",),
    "termsUrl": ("termsUrl",),
    "authorizationProof": ("authorizationProof", "licenseProof", "licenseSnapshot"),
}


def _source_fact(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return value
    return None


def _source_fact_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _aliased_source_fact(payload: Mapping[str, Any], field: str) -> Any:
    for alias in _IMAGE_SOURCE_ALIASES[field]:
        value = _source_fact(payload.get(alias))
        if value not in (None, "", {}):
            return value
    legacy_proof = payload.get("licenseProof")
    if isinstance(legacy_proof, Mapping):
        legacy_key = {
            "license": "license",
            "termsUrl": "termsUrl",
            "authorizationProof": "proofUrl",
        }.get(field)
        if legacy_key:
            value = _source_fact(legacy_proof.get(legacy_key))
            if value not in (None, "", {}):
                return value
    return None


def _image_source_contract(
    compose_payload: Mapping[str, Any],
    assets: list[dict[str, Any]],
    *,
    ref: str,
) -> dict[str, Any]:
    """Resolve one work-level source identity and reject mixed-source image sets."""
    resolved: dict[str, Any] = {}
    required_fields = {"sourceCollectionId", "creator", "collectionPageUrl", "license"}
    for field in _IMAGE_SOURCE_ALIASES:
        work_value = _aliased_source_fact(compose_payload, field)
        per_asset_values = [_aliased_source_fact(asset, field) for asset in assets]
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

    work_has_proof = _aliased_source_fact(
        compose_payload, "termsUrl"
    ) is not None or _aliased_source_fact(compose_payload, "authorizationProof") is not None
    if not work_has_proof:
        proof_keys: set[str] = set()
        for asset in assets:
            terms = _aliased_source_fact(asset, "termsUrl")
            authorization = _aliased_source_fact(asset, "authorizationProof")
            if terms is None and authorization is None:
                raise RuntimeError(f"{ref}: every image asset must declare license proof")
            proof_keys.add(_source_fact_key({"termsUrl": terms, "authorizationProof": authorization}))
        if len(proof_keys) > 1:
            raise RuntimeError(f"{ref}: image assets must share one license proof")

    if "collectionPageUrl" not in resolved:
        urls = [str(url).strip() for url in (compose_payload.get("sourceUrls") or []) if str(url).strip()]
        if len(set(urls)) == 1:
            resolved["collectionPageUrl"] = urls[0]
    if "sourceCollectionId" not in resolved and resolved.get("collectionPageUrl") is not None:
        page_key = _source_fact_key(resolved["collectionPageUrl"])
        digest = hashlib.sha256(page_key.encode("utf-8")).hexdigest()[:16]
        resolved["sourceCollectionId"] = f"legacy:{digest}"

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


def _image_source_import_aliases(image_source: Mapping[str, Any]) -> dict[str, Any]:
    """Write the same rights facts under publish-gate and service-importer keys."""

    page = image_source.get("collectionPageUrl")
    terms_url = image_source.get("termsUrl")
    proof_url = image_source.get("authorizationProof")
    license_value = image_source.get("license")
    aliases: dict[str, Any] = {}
    if page not in (None, "", {}):
        aliases["page"] = page
        if isinstance(page, str):
            aliases["sourceCollectionUrl"] = page
    proof: dict[str, Any] = {}
    if license_value not in (None, "", {}):
        proof["license"] = license_value
    if terms_url not in (None, "", {}):
        proof["termsUrl"] = terms_url
    if proof_url not in (None, "", {}):
        proof["proofUrl"] = proof_url
    if proof:
        aliases["licenseProof"] = proof
        ref_value = proof_url if proof_url not in (None, "", {}) else terms_url
        if isinstance(ref_value, str) and ref_value.strip():
            aliases["licenseProofRef"] = ref_value.strip()
    return aliases


def _resolve_materialized_article(
    task_id: str,
    batch_id: str,
    ref: str,
    *,
    compose_payload: dict[str, Any],
    entity_refs: list[str],
) -> tuple[str, list[str]]:
    draft_article = read_draft_article(task_id, batch_id, ref)
    if is_placeholder(draft_article):
        raise RuntimeError(
            f"{ref}: approved materialization requires a real 4.draft/draft.article.md; "
            "compose snapshot fallback is blocked to avoid expanding multi-body drift"
        )
    article_md = str(draft_article or "")
    actions: list[str] = []
    if isinstance(entity_refs, list):
        annotated = _annotate_manifest_entities(article_md, entity_refs)
        if annotated != article_md:
            actions.append("entity_annotations_injected")
            article_md = annotated
    if str(compose_payload.get("publishMediaMode") or "").strip() == "text_only":
        stripped = _strip_text_only_asset_markup(article_md)
        if stripped != article_md:
            actions.append("text_only_asset_markup_removed")
            article_md = stripped
    return article_md, actions


def _strip_text_only_asset_markup(article_md: str) -> str:
    """Remove draft image markup when release downgraded an article to text-only."""
    text = str(article_md or "")
    text = re.sub(r"(?ms)^:::figure\b.*?^:::\s*", "", text)
    text = re.sub(r"(?m)^coverImage:\s*asset://[^\n]+\n?", "", text)
    text = re.sub(r"(?m)^!\[[^\]]*\]\(asset://[^)]+\)\s*$\n?", "", text)
    text = re.sub(r"(?m)^asset://[^\s]+\s*$\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + ("\n" if text.strip() else "")


MATERIALIZED_FINAL_ENTRIES = (
    "article.md",
    "gallery.md",
    "manifest.json",
    "_object.json",
    "assets",
)


def prune_materialized_refs(task_id: str, batch_id: str, refs: list[str] | set[str] | tuple[str, ...]) -> list[Path]:
    """Remove publish-facing files for refs that are no longer active.

    Process evidence under stage directories is intentionally retained for
    audit. Only final package files are removed so release/gates cannot consume
    a stale half-product after an object is abandoned.
    """
    from _common import content_object

    removed: list[Path] = []
    for ref in sorted({str(item) for item in refs if str(item).strip()}):
        try:
            post_dir = content_object.content_object_dir(task_id, batch_id, ref)
        except KeyError:
            continue
        for name in MATERIALIZED_FINAL_ENTRIES:
            path = post_dir / name
            if path.is_dir():
                shutil.rmtree(path)
                removed.append(path)
            elif path.is_file():
                path.unlink()
                removed.append(path)
        if post_dir.exists():
            content_object.write_content_object_index(task_id, batch_id, ref)
    return removed


def _materialized_source_refs_snapshot(
    task_id: str,
    batch_id: str,
    *,
    base_source_ref: str,
    is_image: bool,
) -> dict[str, Any]:
    """构造成品 `1.download/source_refs.json`（单底稿零参考 v2）。

    文章/主页/图片作品都只登记唯一底稿来源单元（`sources` 长度恒为 1），不再镜像全文、
    不再携带 cited/sourcePaths 多源索引。底稿来源单元缺失（图片外链集合无 source.md，
    或多实体线路类无单一底稿）时降级为最小快照（sources 留空并记原因），保证 1.download 闭环。
    """
    if not str(base_source_ref or "").strip():
        return {
            "schemaVersion": SOURCE_REFS_SCHEMA,
            "baseSourceRef": None,
            "sources": [],
            "note": "no single base source unit (multi-entity route or external image collection)",
        }
    try:
        return build_source_refs_snapshot(
            task_id,
            batch_id,
            base_source_ref=base_source_ref,
        )
    except FileNotFoundError as exc:
        if not is_image:
            raise
        return {
            "schemaVersion": SOURCE_REFS_SCHEMA,
            "baseSourceRef": None,
            "sources": [],
            "note": f"image evidence ref unresolved, indexed without mirror: {exc}",
        }


def materialize_posts(
    task_id: str,
    batch_id: str,
    content_type: str,
    *,
    refs: list[str] | set[str] | tuple[str, ...] | None = None,
) -> list[Path]:
    """把 approved+agent 的 compose/review 成品落到**内容对象根**（§2.4）。

    成品（article.md/manifest.json/assets/ + _object.json）与过程
    阶段（2.quality/3.compose/4.draft/5.review）同处对象根 `posts/{type}/{angle}/{title}/{seq}/`；
    对象坐标（angle/title/seq）以 `_shared/content_object_index.json` 路由为唯一真相，不再自算序号。
    """
    from _common import content_object
    from _common.stage_reports import iter_stage_envelopes, read_stage_envelope

    materialized: list[Path] = []
    batch_manifest = load_batch_manifest(task_id, batch_id)

    allowed_refs = {str(ref) for ref in refs or []}
    review_envelopes = iter_stage_envelopes(task_id, batch_id, "produce", "review")
    if not review_envelopes:
        return materialized

    for ref, review in review_envelopes:
        if allowed_refs and ref not in allowed_refs:
            continue
        payload = review.get("payload", review)
        if payload.get("decision") != "approved":
            continue

        coords = content_object.content_coords(task_id, batch_id, ref)
        if not coords or coords.get("contentType") != content_type:
            continue

        compose = read_stage_envelope(task_id, batch_id, "produce", "compose", ref)
        if compose is None:
            continue

        compose_payload = compose.get("payload", compose)

        is_image = content_type == "image"
        # 出处门：文章正文必须由 generator=agent 创作；图片作品不生成正文，
        # 只接受结构化 sourceCollection/assets/caption 证据包。
        generator = str(compose_payload.get("generator") or "")
        if (is_image and generator != "image_evidence_pack") or (
            not is_image and generator != "agent"
        ):
            continue

        writing_pack = read_writing_pack(task_id, batch_id, ref) or {}
        raw_title = compose_payload.get("title")
        title = str(raw_title if raw_title is not None else ("" if is_image else ref))
        caption = str(compose_payload.get("caption") or compose_payload.get("summary") or "")
        if is_image and len(title) > 80:
            raise RuntimeError(f"{ref}: image title exceeds 80 characters")
        if is_image and len(caption) > 300:
            raise RuntimeError(f"{ref}: image caption exceeds 300 characters")
        template = compose_payload.get("template") or "journal"
        # 对象坐标（angle/title/seq）= 路由真相，与 promote/publish 发布面同名。
        angle = str(coords.get("angle") or "")
        publish_title = str(coords.get("title") or compose_payload.get("publishTitle") or title)
        seq = int(coords.get("seq") or 1)
        post_dir = content_object.content_object_dir(task_id, batch_id, ref)
        from _common.paths import STAGE_REVIEW, ensure_object_stages

        ensure_object_stages(post_dir, through_stage=STAGE_REVIEW)
        post_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = post_dir / "assets"
        # 成品 assets 全量重建（仅清成品，过程阶段证据保留）。
        if assets_dir.exists():
            shutil.rmtree(assets_dir)
        entity_refs = compose_payload.get("entityRefs", [])
        normalized_entity_refs = (
            _normalized_runtime_entity_refs(entity_refs)
            if isinstance(entity_refs, list)
            else []
        )
        tag_refs = compose_payload.get("tagRefs", [])
        source_urls = compose_payload.get("sourceUrls", [])
        source_paths = compose_payload.get("sourcePaths", [])
        semantic_mentions = _ensure_published_manifest_mentions(
            _resolve_semantic_mentions(task_id, batch_id, ref, compose_payload),
            ref,
            entity_refs=entity_refs if isinstance(entity_refs, list) else [],
            tag_refs=tag_refs if isinstance(tag_refs, list) else [],
        )
        article_md = ""
        normalization_actions: list[str] = []
        if not is_image:
            article_md, normalization_actions = _resolve_materialized_article(
                task_id,
                batch_id,
                ref,
                compose_payload=compose_payload,
                entity_refs=entity_refs if isinstance(entity_refs, list) else [],
            )

        raw_assets = compose_payload.get("assets") or []
        if not raw_assets and compose_payload.get("coverAssetRef"):
            global_batch_seq = int(batch_manifest.get("globalBatchSeq") or 0)
            if global_batch_seq <= 0:
                raise RuntimeError(f"missing globalBatchSeq for task={task_id} batch={batch_id}")
            asset_registry = load_batch_asset_registry(task_id, batch_id, global_batch_seq)
            first_entity = ""
            if isinstance(entity_refs, list) and entity_refs:
                first_entity = str(entity_refs[0]).strip("/").split("/")[-1]
            cover_id = allocate_post_asset_id(
                entity_name=first_entity or ref,
                role="cover",
                ref=ref,
                global_batch_seq=global_batch_seq,
                registry=asset_registry,
            )
            raw_assets = [
                {
                    "assetId": cover_id,
                    "fileName": f"{cover_id}.jpg",
                    # 冷启动封面 caption 以原文为基础：实体名 > 文章标题，禁止「封面」占位。
                    "caption": str(first_entity or title or "").strip(),
                    "kind": "image",
                    "scope": "cold_start",
                    "objectKey": compose_payload.get("coverObjectKey", ""),
                }
            ]

        if is_image and not 1 <= len(raw_assets) <= 20:
            raise RuntimeError(f"{ref}: image work requires 1..20 assets, got {len(raw_assets)}")
        image_source = (
            _image_source_contract(compose_payload, raw_assets, ref=ref)
            if is_image
            else {}
        )

        download_images = _resolve_entity_download_dir(task_id, batch_id, entity_refs)
        assets = copy_asset_files(raw_assets, assets_dir, download_images)

        article_path = post_dir / "article.md"
        gallery_path = post_dir / "gallery.md"
        if gallery_path.exists():
            gallery_path.unlink()
        if is_image:
            if article_path.exists():
                article_path.unlink()
        else:
            had_frontmatter = article_md.lstrip().startswith("---")
            if article_md and "articleMarkdownVersion" not in article_md[:200]:
                if not article_md.lstrip().startswith("---"):
                    front = (
                        f"---\n"
                        f"title: {title}\n"
                        f"template: {template}\n"
                        f"articleMarkdownVersion: {MARKDOWN_VERSION}\n"
                    )
                    if assets:
                        front += f"coverImage: asset://{assets[0]['assetId']}\n"
                    front += "---\n\n"
                    article_md = front + article_md
            if not had_frontmatter and article_md.lstrip().startswith("---"):
                normalization_actions.append("frontmatter_injected")
            article_path.write_text(article_md, encoding="utf-8")

        render_profile = compose_payload.get("articleRenderProfile") or {
            "template": template,
            "fontPreset": "clean",
            "layoutPolicy": {
                "wrapDowngrade": "compactWidthToFullWidth",
                "galleryDowngrade": "singleColumn",
            },
        }
        creator_payload = compose_payload.get("creator") if isinstance(compose_payload.get("creator"), dict) else {}
        # 最小发布契约：只保留发布/渲染/出处必需字段。
        manifest = {
            "schemaVersion": "quwoquan_data.post_manifest",
            "topicId": ref,
            "contentType": content_type,
            "entityRefs": entity_refs,
            "normalizedEntityRefs": normalized_entity_refs,
            "tagRefs": tag_refs,
            "semanticMentions": semantic_mentions,
            "publishMediaMode": compose_payload.get("publishMediaMode"),
            "authorId": compose_payload.get("authorId") or creator_payload.get("authorId"),
            "creatorProfileId": compose_payload.get("creatorProfileId") or creator_payload.get("creatorProfileId"),
            "creatorArchetype": compose_payload.get("creatorArchetype") or creator_payload.get("creatorArchetype"),
            "creatorProfileVersion": compose_payload.get("creatorProfileVersion")
            or creator_payload.get("creatorProfileVersion"),
            "creatorDisclosure": compose_payload.get("creatorDisclosure") or creator_payload.get("creatorDisclosure"),
            "experienceClaimMode": compose_payload.get("experienceClaimMode")
            or creator_payload.get("experienceClaimMode"),
            "authorQualitySignals": compose_payload.get("authorQualitySignals")
            or creator_payload.get("authorQualitySignals"),
            "sourceUrls": source_urls,
            "assets": [
                {
                    "assetId": a["assetId"],
                    "fileName": a.get("fileName", ""),
                    "caption": a.get("caption", ""),
                    "imageLayout": a.get("imageLayout", "fullWidth"),
                    "sha256": a.get("sha256", ""),
                    # 资产证据链（相对 batch 根）：source 原图 + 原文，禁绝对路径。
                    "sourceAssetRef": _materialized_asset_refs(a, task_id=task_id, batch_id=batch_id)[1],
                    "sourceRef": _materialized_asset_refs(a, task_id=task_id, batch_id=batch_id)[0],
                    "alignmentEvidence": _materialized_alignment_evidence(a),
                    "sourceCollectionId": a.get("sourceCollectionId", ""),
                    "creator": a.get("creator", ""),
                    "collectionPageUrl": a.get("collectionPageUrl", ""),
                    "license": a.get("license", ""),
                    "termsUrl": a.get("termsUrl", ""),
                    "licenseSnapshot": a.get("licenseSnapshot", ""),
                    "authorizationProof": a.get("authorizationProof", ""),
                    "usageScope": a.get("usageScope", ""),
                }
                for a in assets
            ],
            "template": template,
            "carrier": "image" if is_image else compose_payload.get("carrier", "article"),
            "generator": compose_payload.get("generator", "agent"),
            "generatorModel": compose_payload.get("generatorModel"),
            "citedSourceRefs": [
                _relativize_ref(r, task_id, batch_id)
                for r in (compose_payload.get("citedSourceRefs") or source_paths)
            ],
            "reviewDecision": "approved",
            "publishLayout": compose_payload.get("publishLayout", "travel"),
            "publishAngle": angle,
            "publishTitle": publish_title,
            "publishSeq": seq,
            # 叙事骨架：发布门 storySpine 真相源。优先 compose 显式 storySpine，
            # 回退到 progression（叙事主线）/ sectionIntents（章节意图），保证发布契约闭合。
            "storySpine": _publication_story_spine(compose_payload),
            # 溯源：内容来自哪个任务/批次（task trace/hydrate、推荐归因消费）
            "sourceTaskId": task_id,
            "sourceBatchId": batch_id,
        }
        if is_image:
            manifest.update(
                {
                    "title": title,
                    "caption": caption,
                    **image_source,
                    **_image_source_import_aliases(image_source),
                }
            )
        else:
            manifest.update(
                {
                    "articleMarkdownVersion": MARKDOWN_VERSION,
                    "articleRenderProfile": render_profile,
                }
            )
        created_at, updated_at = _materialized_manifest_times(
            compose_payload,
            payload,
            batch_manifest,
        )
        manifest["createdAt"] = created_at
        manifest["updatedAt"] = updated_at
        for optional_creator_key in (
            "authorId",
            "creatorProfileId",
            "creatorArchetype",
            "creatorProfileVersion",
            "creatorDisclosure",
            "experienceClaimMode",
            "authorQualitySignals",
        ):
            if manifest.get(optional_creator_key) in (None, "", {}):
                manifest.pop(optional_creator_key, None)
        # 「明」：预生成内容侧交集锚点（对齐 IntersectionReason 闭集口径），runtime 据此 + 用户补全文案。
        manifest["intersectionHints"] = build_intersection_hints(manifest)
        write_json(post_dir / "manifest.json", manifest)
        from verify.verify_content_quality import asset_closure_issues

        closure_issues = asset_closure_issues(post_dir, manifest)
        if closure_issues:
            raise RuntimeError("post asset closure failed:\n  - " + "\n  - ".join(closure_issues))

        # 结构化出处：只保留发布追责必需字段，取代分散的 produce_trace.json。
        # 出处路径全部相对 batch 根（禁绝对路径进发布契约）。
        final_digest = (
            compute_asset_manifest_sha256(manifest["assets"])
            if is_image
            else compute_document_sha256(article_md)
        )
        provenance_compose = {
            **compose_payload,
            **image_source,
            "sourcePaths": [_relativize_ref(p, task_id, batch_id) for p in source_paths],
            "citedSourceRefs": manifest["citedSourceRefs"],
            (
                "assetManifestDigest" if is_image else "articleMarkdownDigest"
            ): final_digest,
        }
        draft_meta = read_draft_meta(task_id, batch_id, ref) or {}
        draft_meta = {
            **draft_meta,
            "citedSourcePaths": [
                _relativize_ref(p, task_id, batch_id)
                for p in (draft_meta.get("citedSourcePaths") or [])
            ],
        }
        provenance = build_provenance(
            ref,
            writing_pack=writing_pack,
            draft_meta=draft_meta,
            review_payload=payload,
            compose_payload=provenance_compose,
            manifest=manifest,
        )
        review_dir = post_dir / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "provenance.json", provenance)
        # 所有成品（含图片作品）都必须自持 `1.download/source_refs.json`，
        # 否则图片作品永远缺 1.download，阶段树不完整、无法回查来源。
        download_dir = post_dir / "1.download"
        download_dir.mkdir(parents=True, exist_ok=True)
        # 单底稿零参考：成品来源索引只认唯一底稿来源单元。
        # 文章用 writing_pack.baseSourceRef；图片作品的底稿来源单元 = 资产所属同一 source unit。
        if is_image:
            image_base_ref = next(
                (
                    str(asset.get("sourceRef") or "")
                    for asset in manifest["assets"]
                    if str(asset.get("sourceRef") or "")
                ),
                "",
            )
            source_refs_base = image_base_ref
        else:
            source_refs_base = str(writing_pack.get("baseSourceRef") or "")
        write_json(
            download_dir / "source_refs.json",
            _materialized_source_refs_snapshot(
                task_id,
                batch_id,
                base_source_ref=source_refs_base,
                is_image=is_image,
            ),
        )
        if not is_image:
            write_json(
                review_dir / "finalization_report.json",
                build_finalization_report(
                    ref,
                    draft_markdown=str(read_draft_article(task_id, batch_id, ref) or ""),
                    final_markdown=article_md,
                    normalization_actions=normalization_actions,
                    article_source="4.draft/draft.article.md",
                    compose_snapshot_markdown=compose_payload.get("articleMarkdown"),
                ),
            )
        else:
            # 图片作品没有 draft->final 文章差异，finalization_report 仅适用于文章/主页。
            finalization_path = review_dir / "finalization_report.json"
            if finalization_path.exists():
                finalization_path.unlink()

        # 对象索引：publish 目标相对路径 + 成品相对路径 + 各阶段状态（§14.3）。
        content_object.write_content_object_index(task_id, batch_id, ref)

        materialized.append(post_dir)

    return materialized
