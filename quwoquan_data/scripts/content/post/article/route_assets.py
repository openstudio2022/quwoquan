"""Route image asset selection and asset metadata construction."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.image_safety import STATUS_UNSAFE, assess_image, is_near_duplicate

from content.execution.asset_registry import (
    ExecutionAssetRegistry,
    allocate_post_asset_id,
    load_execution_asset_registry,
)
from content.execution.runtime_state import load_execution_runtime_state
from content.post.article.route_core import _article_without_assets_allowed


def _entity_image_candidates(
    execution_id: str, name: str, entity_ref: str = ""
) -> list[dict[str, Any]]:
    """实体可选图候选（新布局：来源单元 assets/）。

    每项 {path, sourceRef, sourceAssetRef}（后两者为相对 batch 根路径，构成证据链）。
    """
    from content.source.source_assets import object_image_candidates
    from content.source.source_unit import (
        find_entity_object_dirs,
        resolve_entity_object_dir,
    )

    cands: list[dict[str, Any]] = []
    if entity_ref:
        cands = object_image_candidates(
            resolve_entity_object_dir(execution_id, entity_ref), execution_id
        )
    if not cands and not entity_ref:
        for obj in find_entity_object_dirs(execution_id, name):
            cands.extend(object_image_candidates(obj, execution_id))
    if cands:
        return cands
    return []


def _pick_safe_image(candidates: Sequence[Mapping[str, Any]], chosen: Sequence[Path]):
    """挑出 safe（非 unsafe）且与已选不近重复的第一张，杜绝同源复用。返回 (candidate, verdict)。"""
    fallback = None
    for cand in candidates:
        path = cand["path"]
        if any(is_near_duplicate(path, picked) for picked in chosen):
            continue
        verdict = assess_image(path)
        if verdict.status == STATUS_UNSAFE:
            continue
        if fallback is None:
            fallback = (cand, verdict)
        if verdict.status != "needs_review":
            return cand, verdict
    return fallback


def _image_plan_layouts(image_plan: Sequence[Mapping[str, Any]]) -> list[str]:
    layouts: list[str] = []
    for slot in image_plan:
        if slot.get("gallery"):
            layouts.append("gallery")
        else:
            layouts.append(str(slot.get("imageLayout") or "wrapRight"))
    return layouts


def _node_layout(layouts: Sequence[str], position: int) -> str:
    """节点版面职责：优先取 imagePlan 非首槽，缺失时 wrapRight/wrapLeft/gallery 交替，避免统一降级。"""
    non_cover = layouts[1:] if len(layouts) > 1 else []
    if non_cover:
        return non_cover[position % len(non_cover)]
    return ("wrapRight", "wrapLeft", "gallery")[position % 3]


def _make_asset(
    ref: str,
    *,
    role: str,
    candidate: Mapping[str, Any],
    layout: str,
    caption: str,
    entity_name: str,
    execution_sequence: int,
    asset_registry: ExecutionAssetRegistry,
    verdict=None,
) -> dict[str, Any]:
    path = candidate["path"]
    # 成品资产文件名即 assetId（可由 article.md 的 asset:// 直查文件，无需翻 manifest）。
    # owner ref 必须精确到单张源图：同一 post 内同实体同角色多图（gallery）
    # 若共享 owner key 会复用同一 assetId 导致文件互相覆盖。
    asset_id = allocate_post_asset_id(
        entity_name=entity_name,
        role=role,
        ref=f"{ref}#{candidate.get('sourceAssetRef') or path.name}",
        execution_sequence=execution_sequence,
        registry=asset_registry,
        caption=caption,
        ordinal=1,
    )
    ext = path.suffix.lower() or ".jpg"
    asset = {
        "assetId": asset_id,
        "fileName": f"{asset_id}{ext}",
        "caption": caption,
        "kind": "image",
        "scope": "cold_start",
        "role": role,
        "entityName": entity_name,
        "objectKey": "",
        "sourcePath": str(path),
        # 证据链：source 原图 + 原文（相对 batch 根；materialize 直接写入 manifest）。
        "sourceAssetRef": str(candidate.get("sourceAssetRef") or ""),
        "sourceRef": str(candidate.get("sourceRef") or ""),
        "alignmentEvidence": str(candidate.get("relevance") or caption or candidate.get("caption") or ""),
        "imageLayout": layout,
    }
    for field in (
        "researchLane",
        "sourceCollectionId",
        "creator",
        "collectionPageUrl",
        "license",
        "termsUrl",
        "licenseSnapshot",
        "authorizationProof",
        "usageScope",
        "rightsAuditStatus",
        "rightsAuditIssues",
    ):
        value = candidate.get(field)
        if value not in (None, ""):
            asset[field] = value
    if verdict is not None:
        asset["imageStatus"] = verdict.status
        asset["textAreaRatio"] = round(verdict.text_area_ratio, 4)
        asset["isTextHeavy"] = bool(verdict.is_text_heavy)
    return asset


def _specific_asset_caption(candidate: Mapping[str, Any], entity_name: str, fallback: str = "") -> str:
    """Build a publishable article image caption from source evidence.

    A bare entity name is not enough for article image-text alignment. Prefer
    the source/page title when the downloaded image metadata only says the
    entity name.
    """
    entity = str(entity_name or "").strip()
    raw_caption = str(candidate.get("caption") or "").strip()
    relevance = str(candidate.get("relevance") or "").strip()
    source_title = str(candidate.get("sourceTitle") or "").strip()
    fallback = str(fallback or "").strip()
    generic = {entity, f"{entity}·回望", ""}

    if raw_caption not in generic:
        return raw_caption
    if relevance and relevance not in generic:
        return relevance[:80]
    if source_title and source_title not in generic:
        return f"{entity}：{source_title}" if entity and entity not in source_title else source_title
    if fallback and fallback not in generic:
        return fallback
    return f"{entity}：来源图像" if entity else "来源图像"


def _build_route_assets(
    execution_id: str,
    ref: str,
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """选图：cover/node/closing 三类职责。

    article 图 100% 同源——全部从唯一 baseSourceRef 底稿来源自身 assets
    汇聚的单一 base_pool 去重取图（去实体键控），node 数以 routeNodes 长度 bound、池耗尽即止。
    image carrier：一源一作品（单一 sourceCollectionId）。
    """
    image_plan = list(brief.get("imagePlan") or [])
    manifest = load_execution_runtime_state(execution_id)
    execution_sequence = int(
        brief.get("executionSequence")
        or (manifest.execution_sequence if manifest is not None else 0)
    )
    if execution_sequence <= 0:
        raise RuntimeError(f"missing executionSequence for execution={execution_id}")
    asset_registry = load_execution_asset_registry(execution_id, execution_sequence)
    layouts = _image_plan_layouts(image_plan)
    route_nodes = [node for node in (evidence_bundle.get("routeNodes") or []) if node.get("entityName")]
    entity_names = [str(node["entityName"]) for node in route_nodes]
    if not entity_names:
        return []
    ref_by_name = {str(node["entityName"]): str(node.get("entityRef") or "") for node in route_nodes}

    per_entity = {
        name: _entity_image_candidates(execution_id, name, ref_by_name.get(name, ""))
        for name in dict.fromkeys(entity_names)
    }

    assets: list[dict[str, Any]] = []
    chosen: list[Path] = []

    declared_carrier = str(brief.get("carrier") or "").lower()
    base_source_ref = ""
    if declared_carrier != "image":
        base_source_ref = str(brief.get("baseSourceRef") or "").strip()
        if not base_source_ref:
            raise RuntimeError(f"{ref}: article requires exactly one baseSourceRef")
        if _article_without_assets_allowed(brief):
            return []
    if declared_carrier == "image":
        collection_id = str(brief.get("sourceCollectionId") or "").strip()
        declared_refs = {
            str(ref).strip()
            for ref in (brief.get("assetRefs") or [])
            if str(ref).strip()
        }
        candidates = [
            candidate
            for rows in per_entity.values()
            for candidate in rows
            if str(candidate.get("researchLane") or "") == "image"
            and (
                not collection_id
                or str(candidate.get("sourceCollectionId") or "") == collection_id
            )
            and (
                not declared_refs
                or str(candidate.get("sourceAssetRef") or "") in declared_refs
            )
        ]
        candidates.sort(key=lambda row: str(row.get("sourceAssetRef") or row.get("path") or ""))
        if declared_refs:
            matched_refs = {str(candidate.get("sourceAssetRef") or "") for candidate in candidates}
            missing_refs = sorted(declared_refs - matched_refs)
            if missing_refs:
                raise RuntimeError(
                    f"{ref}: image assetRefs missing source assets {len(missing_refs)}/{len(declared_refs)}: "
                    f"{missing_refs[:3]}"
                )
        blocked_by_safety: list[str] = []
        for position, candidate in enumerate(candidates[:20]):
            verdict = assess_image(candidate["path"])
            if verdict.status == STATUS_UNSAFE:
                blocked_by_safety.append(
                    f"{candidate.get('sourceAssetRef') or candidate.get('path')}:"
                    f"{'/'.join(verdict.reasons) or verdict.status}"
                )
                continue
            chosen.append(candidate["path"])
            assets.append(
                _make_asset(
                    ref,
                    role="cover" if position == 0 else "node",
                    candidate=candidate,
                    layout="gallery",
                    caption=str(candidate.get("caption") or ""),
                    entity_name=entity_names[0],
                    execution_sequence=execution_sequence,
                    asset_registry=asset_registry,
                    verdict=verdict,
                )
            )
        if declared_refs and len(assets) != len(declared_refs):
            if blocked_by_safety:
                raise RuntimeError(
                    f"{ref}: image assetRefs blocked by image safety gate "
                    f"{len(blocked_by_safety)}/{len(declared_refs)}: {blocked_by_safety[:3]}"
                )
            raise RuntimeError(
                f"{ref}: image assetRefs resolved {len(assets)}/{len(declared_refs)}"
            )
        if not assets:
            raise RuntimeError(f"{ref}: no safe image assets for collection {collection_id!r}")
        collection_ids = {
            str(asset.get("sourceCollectionId") or "") for asset in assets
        }
        if len(collection_ids) != 1 or "" in collection_ids:
            raise RuntimeError(f"{ref}: image work must resolve exactly one sourceCollectionId")
        return assets
    # RC1/RC4 去实体键控：文章配图 100% 同源——只用 baseSourceRef 指向的底稿来源自身
    # assets，汇聚成单一 base_pool；不再按 routeNodes 实体位置(entity_names[0]/[-1])
    # 键控选 cover/closing，避免 base 源不在首/末节点时漏图，也杜绝跨源替代图。
    base_pool = sorted(
        (
            candidate
            for rows in per_entity.values()
            for candidate in rows
            if str(candidate.get("researchLane") or "") != "image"
            and str(candidate.get("sourceRef") or "") == base_source_ref
            and str(candidate.get("sourceAssetRef") or "").startswith(
                base_source_ref.rsplit("/", 1)[0] + "/assets/"
            )
        ),
        key=lambda row: str(row.get("sourceAssetRef") or row.get("path") or ""),
    )
    if not base_pool:
        raise RuntimeError(f"{ref}: article base draft source has no usable source images")
    primary_entity = entity_names[0]

    cover_layout = layouts[0] if layouts else "fullWidth"
    cover = _pick_safe_image(base_pool, chosen)
    if cover is not None:
        chosen.append(cover[0]["path"])
        assets.append(
            _make_asset(
                ref,
                role="cover",
                candidate=cover[0],
                layout=cover_layout,
                caption=_specific_asset_caption(cover[0], primary_entity),
                entity_name=primary_entity,
                execution_sequence=execution_sequence,
                asset_registry=asset_registry,
                verdict=cover[1],
            )
        )

    # node 数仍以 routeNodes 长度 bound（保留线路推进感），但全部从同一 base_pool
    # 去重取图（同源）；池耗尽即止，不再 per-entity 键控。
    for position, name in enumerate(entity_names):
        node_image = _pick_safe_image(base_pool, chosen)
        if node_image is None:
            break
        chosen.append(node_image[0]["path"])
        assets.append(
            _make_asset(
                ref,
                role="node",
                candidate=node_image[0],
                layout=_node_layout(layouts, position),
                caption=_specific_asset_caption(node_image[0], name),
                entity_name=name,
                execution_sequence=execution_sequence,
                asset_registry=asset_registry,
                verdict=node_image[1],
            )
        )

    closing = _pick_safe_image(base_pool, chosen)
    if closing is not None:
        chosen.append(closing[0]["path"])
        assets.append(
            _make_asset(
                ref,
                role="closing",
                candidate=closing[0],
                layout="fullWidth",
                caption=_specific_asset_caption(closing[0], entity_names[-1], f"{entity_names[-1]}·回望"),
                entity_name=entity_names[-1],
                execution_sequence=execution_sequence,
                asset_registry=asset_registry,
                verdict=closing[1],
            )
        )

    return assets

__all__ = [name for name in globals() if not name.startswith("__")]
