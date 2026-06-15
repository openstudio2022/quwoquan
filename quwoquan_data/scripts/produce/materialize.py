"""Materialize approved compose results into post packages."""
from __future__ import annotations

import hashlib
import json
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

from _common.article_package import (
    MARKDOWN_VERSION,
    compute_asset_manifest_sha256,
    compute_document_sha256,
    copy_asset_files,
)
from _common.batch_asset_registry import allocate_post_asset_id, load_batch_asset_registry
from _common.batch_manifest import load_batch_manifest
from _common.paths import DATA_ROOT, RUNTIME_ROOT, batch_root, relative_batch_ref
from _common.io import write_json
from _common.draft_io import is_placeholder, read_draft_article, read_draft_meta, read_writing_pack
from _common.post_evidence_chain import build_finalization_report, build_source_refs_snapshot
from _common.provenance import build_provenance
from _common.intersection_signal import build_intersection_hints
from _common.entity_annotation import annotate_inline, normalize_link_ref


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
    batch_prefix = f"batches/{batch_id}/"
    if s.startswith(batch_prefix):
        return s[len(batch_prefix) :]
    marker = f"/batches/{batch_id}/"
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


def _publication_condition_context(raw: object) -> object:
    """发布契约字段投影：保留 entityProfile，同时提供顶层 region/season 授权字段。"""
    if not isinstance(raw, dict):
        return raw
    context = dict(raw)
    top_regions = [str(v) for v in (context.get("regions") or []) if v]
    top_seasons = [str(v) for v in (context.get("seasons") or []) if v]
    if top_regions and not context.get("region"):
        context["region"] = top_regions[0]
    if top_seasons and not context.get("season"):
        context["season"] = top_seasons[0]
    profile = context.get("entityProfile")
    if isinstance(profile, dict):
        regions = [str(v) for v in (profile.get("regions") or []) if v]
        seasons = [str(v) for v in (profile.get("seasons") or []) if v]
        if regions and not context.get("region"):
            context["region"] = regions[0]
        if seasons and not context.get("season"):
            context["season"] = seasons[0]
    return context


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
    return article_md, actions


def materialize_posts(task_id: str, batch_id: str, content_type: str) -> list[Path]:
    """把 approved+agent 的 compose/review 成品落到**内容对象根**（§2.4）。

    成品（article.md/manifest.json/assets/ + _object.json）与过程
    阶段（2.quality/3.compose/4.draft/5.review）同处对象根 `posts/{type}/{angle}/{title}/{seq}/`；
    对象坐标（angle/title/seq）以 `_shared/content_object_index.json` 路由为唯一真相，不再自算序号。
    """
    from _common import content_object
    from _common.stage_reports import iter_stage_envelopes, read_stage_envelope

    materialized: list[Path] = []

    review_envelopes = iter_stage_envelopes(task_id, batch_id, "produce", "review")
    if not review_envelopes:
        return materialized

    for ref, review in review_envelopes:
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

        # 出处门：只有 generator=agent 的正文允许进入交付面，脚本/占位一律拒绝落地。
        if str(compose_payload.get("generator") or "") != "agent":
            continue

        writing_pack = read_writing_pack(task_id, batch_id, ref) or {}
        is_image = content_type == "image"
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
            manifest = load_batch_manifest(task_id, batch_id)
            global_batch_seq = int(manifest.get("globalBatchSeq") or 0)
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
                    "caption": "封面",
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
            "semanticMentions": list(compose_payload.get("semanticMentions") or []),
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
            "conditionContext": _publication_condition_context(compose_payload.get("conditionContext")),
            "sourceUrls": source_urls,
            "assets": [
                {
                    "assetId": a["assetId"],
                    "fileName": a.get("fileName", ""),
                    "caption": a.get("caption", ""),
                    "imageLayout": a.get("imageLayout", "fullWidth"),
                    "sha256": a.get("sha256", ""),
                    # 资产证据链（相对 batch 根）：source 原图 + 原文，禁绝对路径。
                    "sourceAssetRef": _relativize_ref(
                        a.get("sourceAssetRef") or a.get("sourcePath") or "", task_id, batch_id
                    ),
                    "sourceRef": _relativize_ref(a.get("sourceRef") or "", task_id, batch_id),
                    "alignmentEvidence": a.get("alignmentEvidence", ""),
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
                }
            )
        else:
            manifest.update(
                {
                    "articleMarkdownVersion": MARKDOWN_VERSION,
                    "articleRenderProfile": render_profile,
                }
            )
        created_at = _manifest_time_fact(compose_payload, "createdAt")
        updated_at = _manifest_time_fact(compose_payload, "updatedAt")
        if created_at:
            manifest["createdAt"] = created_at
        if updated_at:
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
        if not is_image:
            source_refs = build_source_refs_snapshot(
                task_id,
                batch_id,
                base_source_ref=str(writing_pack.get("baseSourceRef") or ""),
                cited_source_refs=manifest["citedSourceRefs"],
                source_paths=provenance_compose["sourcePaths"],
            )
            download_dir = post_dir / "1.download"
            download_dir.mkdir(parents=True, exist_ok=True)
            write_json(download_dir / "source_refs.json", source_refs)
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
            finalization_path = review_dir / "finalization_report.json"
            if finalization_path.exists():
                finalization_path.unlink()

        # 对象索引：publish 目标相对路径 + 成品相对路径 + 各阶段状态（§14.3）。
        content_object.write_content_object_index(task_id, batch_id, ref)

        materialized.append(post_dir)

    return materialized
