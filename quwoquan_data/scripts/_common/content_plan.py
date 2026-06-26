"""证据驱动篇目规划包（content_plan_packet）校验。

真相源：batches/{batch}/_shared/content_plan_packet.json
见 content_pipeline_spec.md §1.2.1
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from _common.base_draft import load_base_draft_text
from _common import ops_governance as og
from _common.content_object import BRIEF_FILE, content_object_stage_dir, load_index
from _common.creator_assignment import creator_assignment_issues, creator_assignment_required
from _common.image_asset_strategy import image_count_is_hard_quota
from _common.io import read_json
from _common.image_safety import assess_image_publish_prefilter
from _common.paths import (
    STAGE_COMPOSE,
    batch_content_plan_packet_path,
    batch_results_dir,
    batch_root,
    relative_batch_ref,
)
from _common.quality_gates import WRITING_INTENTS, writing_intent_issues

CONTENT_PLAN_SCHEMA = "quwoquan_data.content_plan_packet"
ARTICLE_MIN_BASE_DRAFT_CHARS = 600
ARTICLE_BASE_SOURCE_ROLES = {"base"}
ARTICLE_BASE_SOURCE_CATEGORIES = {
    "travelogue",
    "guidebook",
    "travel_guide",
    "wikivoyage",
    "official_article",
    "vertical_professional",
    "ugc_longform",
    "community_post",
    "media_article",
    "platform_article",
    "forum_thread",
    "review_note",
}
ARTICLE_SUPPORTING_ONLY_CATEGORIES = {
    "authoritative_reference",
    "official",
    "government",
    "media",
    "open_license",
    "image_collection",
    "overview_baike",
    "encyclopedia",
}


def reject_source_ids(task_id: str, batch_id: str) -> set[str]:
    """收集 source_screen_gate 判定 reject 的 sourceId，用于证据准入硬阻断。"""
    rejected: set[str] = set()
    results_dir = batch_results_dir(task_id, batch_id, "download", "source_screen")
    if not results_dir.is_dir():
        return rejected
    for path in results_dir.glob("*.json"):
        try:
            data = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and str(data.get("decision") or "").lower() == "reject":
            sid = str(data.get("sourceId") or path.stem).strip()
            if sid:
                rejected.add(sid)
    return rejected


def load_content_plan_packet(task_id: str, batch_id: str) -> dict[str, Any] | None:
    path = batch_content_plan_packet_path(task_id, batch_id)
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def site_supply_dynamic_content_plan(spec: Mapping[str, Any]) -> bool:
    """站点供给线批次由 content_plan_packet 自带对象清单和动态实体集合。"""
    policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    return bool(policy.get("siteSupplyDynamicContentPlan") is True)


def _is_site_supply_packet(packet: Mapping[str, Any]) -> bool:
    return (
        str(packet.get("generatedBy") or "") == "site_supply_content_plan_bridge"
        or isinstance(packet.get("sourceSite"), Mapping)
    )


def _dynamic_targets_from_packet(packet: Mapping[str, Any]) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for item in packet.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("kind") or "") != "entity":
            continue
        for entity_ref in item.get("entityRefs") or []:
            parts = [part for part in str(entity_ref or "").strip("/").split("/") if part]
            if len(parts) < 4 or parts[0] != "entity":
                continue
            name = parts[-1].strip()
            if name and name not in seen:
                seen.add(name)
                targets.append(name)
    return targets


def _abandoned_content_refs(task_id: str, batch_id: str) -> set[str]:
    path = batch_root(task_id, batch_id) / "_shared" / "task_workflow_state.json"
    if not path.is_file():
        return set()
    try:
        state = read_json(path)
    except (OSError, ValueError, TypeError):
        return set()
    refs: set[str] = set()
    for item in state.get("abandonedContentObjects") or []:
        if isinstance(item, dict):
            status = str(item.get("status") or "").strip()
            if status and status != "abandoned":
                continue
            ref = str(item.get("ref") or "").strip()
            if ref:
                refs.add(ref)
    return refs


def _is_image_ref(ref: str) -> bool:
    return ref.endswith("_image") or "_image_" in ref


def _abandoned_refs_for_target(
    abandoned_refs: set[str], target: str, *, carrier: str
) -> set[str]:
    prefix = f"{target}_"
    out: set[str] = set()
    for ref in abandoned_refs:
        if not ref.startswith(prefix):
            continue
        if carrier == "image" and _is_image_ref(ref):
            out.add(ref)
        elif carrier == "article" and not _is_image_ref(ref):
            out.add(ref)
    return out


def _abandoned_intents_for_target(abandoned_refs: set[str], target: str) -> set[str]:
    prefix = f"{target}_"
    return {
        ref[len(prefix):]
        for ref in _abandoned_refs_for_target(abandoned_refs, target, carrier="article")
    }


def _items(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = packet.get("items") or []
    return [i for i in raw if isinstance(i, dict)]


def allow_partial_content(spec: Mapping[str, Any]) -> bool:
    """Whether entity-level source gaps may be handled by target replacement.

    Default is strict. Scale workflows may opt in explicitly so fast-fail
    objects do not block unrelated production.
    """
    policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    return bool(policy.get("allowPartialContent") is True)


def allow_content_quota_shortfall(spec: Mapping[str, Any]) -> bool:
    """Whether successful content objects may ship when per-target quotas shortfall."""
    policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    return bool(
        policy.get("allowContentQuotaShortfall") is True
        or policy.get("allowPartialContent") is True
    )


def _source_asset_rows(root: Path, source_ref: str) -> list[dict[str, Any]]:
    if not source_ref:
        return []
    source_path = root / source_ref
    index_path = source_path.parent / "assets" / "index.json"
    if not index_path.is_file():
        return []
    try:
        rows = read_json(index_path).get("assets") or []
    except (OSError, ValueError, TypeError):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _source_meta(root: Path, source_ref: str) -> dict[str, Any]:
    if not source_ref:
        return {}
    meta_path = (root / source_ref).parent / "meta.json"
    if not meta_path.is_file():
        return {}
    try:
        data = read_json(meta_path)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _article_source_category(meta: Mapping[str, Any]) -> str:
    return str(
        meta.get("category")
        or meta.get("sourceCategory")
        or meta.get("sourceKind")
        or ""
    ).strip()


def _entity_focus_issues(*, ref: str, carrier: str, source_meta: Mapping[str, Any], item: Mapping[str, Any] | None = None) -> list[str]:
    issues: list[str] = []
    verdict = str(
        (item or {}).get("entityFocusVerdict")
        or source_meta.get("entityFocusVerdict")
        or source_meta.get("focusVerdict")
        or ""
    ).strip().lower()
    if verdict in {"weak", "supporting_only", "mismatch", "off_entity"}:
        issues.append(
            f"item[{ref}]: entity_focus_gate blocked {carrier} primary source "
            f"(verdict={verdict}); weak/off-entity sourceUnit may only be supporting evidence"
        )
    raw_score = (
        (item or {}).get("entityFocusScore")
        if (item or {}).get("entityFocusScore") is not None
        else source_meta.get("entityFocusScore")
    )
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = None
    # 聚焦度阈值的唯一真相源在 _common.entity_focus（与 download/选源/准出口径一致）。
    from _common.entity_focus import ENTITY_FOCUS_STRONG_FLOOR
    if score is not None and score < ENTITY_FOCUS_STRONG_FLOOR:
        issues.append(
            f"item[{ref}]: entity_focus_gate score {score:.2f} < {ENTITY_FOCUS_STRONG_FLOOR:.2f}; "
            "primary source must be about the target entity, not a loose mention"
        )
    return issues


def _source_asset_ref(
    task_id: str, batch_id: str, root: Path, source_ref: str, row: Mapping[str, Any]
) -> str:
    file_name = str(row.get("fileName") or "").strip()
    if not source_ref or not file_name:
        return ""
    return relative_batch_ref((root / source_ref).parent / "assets" / file_name, task_id, batch_id)


def validate_content_plan(task_id: str, batch_id: str, spec: Mapping[str, Any]) -> list[str]:
    """校验 content_plan 是否满足配额与证据链。"""
    issues: list[str] = []
    packet = load_content_plan_packet(task_id, batch_id)
    if packet is None:
        return ["content_plan_packet.json missing under batch _shared/"]

    items = _items(packet)
    if not items:
        if not content_plan_quotas_required(spec):
            return issues
        return ["content_plan_packet.items is empty"]
    if str(packet.get("schemaVersion") or "").strip() != CONTENT_PLAN_SCHEMA:
        issues.append(
            f"content_plan_packet.schemaVersion must be {CONTENT_PLAN_SCHEMA!r}, "
            f"got {packet.get('schemaVersion')!r}"
        )

    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    acceptance = spec.get("acceptance") if isinstance(spec.get("acceptance"), Mapping) else {}
    separated_research = str(content.get("modalityContract") or "") == "separated_research"
    want_entity = int(quotas.get("entityArticles") or 0)
    want_route = int(quotas.get("routeArticles") or 0)
    want_gallery = 0 if separated_research else int(quotas.get("galleryPosts") or 0)
    per_target_articles = int(quotas.get("entityArticlesPerTarget") or 0)
    per_target_galleries = int(quotas.get("imageWorksPerTarget") or 0)
    image_quota_hard = (not separated_research) or image_count_is_hard_quota(spec)
    if separated_research and (
        int(quotas.get("galleryPosts") or 0)
        or int(quotas.get("galleryPostsPerTarget") or 0)
    ):
        issues.append(
            "separated_research uses imageWorksPerTarget; galleryPosts/galleryPostsPerTarget are retired"
        )
    if not separated_research and not per_target_galleries:
        per_target_galleries = int(quotas.get("galleryPostsPerTarget") or 0)
    strict_rights_mode = bool(
        per_target_articles
        or per_target_galleries
        or int(quotas.get("entityHomepagesPerTarget") or 0)
    )
    require_creator_assignment = creator_assignment_required(spec)
    targets = [
        str(target.get("name") or "").strip()
        for target in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    ]
    if site_supply_dynamic_content_plan(spec) and _is_site_supply_packet(packet):
        dynamic_targets = _dynamic_targets_from_packet(packet)
        if dynamic_targets:
            targets = dynamic_targets
        else:
            issues.append("siteSupplyDynamicContentPlan requires entityRefs in site_supply content_plan_packet")
    if per_target_articles:
        want_entity = per_target_articles * len(targets)
    if per_target_galleries and image_quota_hard:
        want_gallery = per_target_galleries * len(targets)
    required_angles = [
        str(angle).strip()
        for angle in (acceptance.get("requiredAngles") or [])
        if str(angle).strip()
    ]
    required_article_intents = [angle for angle in required_angles if angle in WRITING_INTENTS]
    requires_image_angle = any(angle in {"image", "imagePost", "gallery"} for angle in required_angles)
    unknown_angles = [
        angle
        for angle in required_angles
        if angle not in WRITING_INTENTS and angle not in {"image", "imagePost", "gallery"}
    ]
    if unknown_angles:
        issues.append(f"acceptance.requiredAngles contains unknown angle(s): {unknown_angles}")
    if required_article_intents and per_target_articles and len(required_article_intents) > per_target_articles:
        issues.append(
            "acceptance.requiredAngles declares "
            f"{len(required_article_intents)} article intent(s) but "
            f"content.quotas.entityArticlesPerTarget={per_target_articles}"
        )
    if requires_image_angle and per_target_galleries < 1:
        issues.append(
            "acceptance.requiredAngles declares image but "
            "content.quotas.imageWorksPerTarget must be >= 1"
        )

    def _item_carrier(item: Mapping[str, Any]) -> str:
        carrier = str(item.get("carrier") or item.get("contentType") or "article")
        return "image" if carrier == "gallery" else carrier

    abandoned_refs = (
        _abandoned_content_refs(task_id, batch_id)
        if allow_content_quota_shortfall(spec)
        else set()
    )

    if want_entity or want_route or want_gallery:
        entity_article_n = sum(
            1 for i in items
            if str(i.get("kind") or "") == "entity" and _item_carrier(i) != "image"
        )
        gallery_n = sum(1 for i in items if _item_carrier(i) == "image")
        route_n = sum(1 for i in items if str(i.get("kind") or "") == "route")
        abandoned_article_n = sum(1 for ref in abandoned_refs if not _is_image_ref(ref))
        abandoned_image_n = sum(1 for ref in abandoned_refs if _is_image_ref(ref))
        effective_want_entity = max(0, want_entity - abandoned_article_n)
        effective_want_gallery = max(0, want_gallery - abandoned_image_n)
        if want_entity and entity_article_n != effective_want_entity:
            issues.append(
                f"entityArticles quota {want_entity} "
                f"(minus abandoned {abandoned_article_n} => {effective_want_entity}) "
                f"but packet has {entity_article_n}"
            )
        if want_gallery and image_quota_hard and gallery_n != effective_want_gallery:
            issues.append(
                f"imageWorks quota {want_gallery} "
                f"(minus abandoned {abandoned_image_n} => {effective_want_gallery}) "
                f"but packet has {gallery_n}"
            )
        if want_route:
            # 网站角度环线：底稿是"覆盖>=3地点的多地点游记"，其供给天然稀疏。
            # 开启 allowContentQuotaShortfall 时，routeArticles 视为上限而非地板：
            # 有多少合格多地点底稿就成多少篇环线，不足额属正常诚实弃稿，不卡死；
            # 但不得超额（route_n > want_route）。严格模式下仍要求精确达额。
            route_shortfall_ok = allow_content_quota_shortfall(spec)
            if route_n > want_route or (not route_shortfall_ok and route_n != want_route):
                issues.append(
                    f"routeArticles quota {want_route} but packet has {route_n}"
                    + ("" if not route_shortfall_ok else " (ceiling; route shortfall allowed)")
                )

    root = batch_root(task_id, batch_id)
    index = load_index(task_id, batch_id)
    item_refs = {str(item.get("ref") or "").strip() for item in items if str(item.get("ref") or "").strip()}
    extra_index_refs = sorted(set(index) - item_refs - abandoned_refs)
    if extra_index_refs:
        issues.append(
            "content_object_index contains ref(s) outside content_plan_packet: "
            + ", ".join(extra_index_refs[:20])
            + (" ..." if len(extra_index_refs) > 20 else "")
        )
    expected_briefs: set[Path] = set()
    for ref in item_refs:
        if ref not in index:
            continue
        try:
            expected_briefs.add((content_object_stage_dir(task_id, batch_id, ref, STAGE_COMPOSE) / BRIEF_FILE).resolve())
        except (KeyError, OSError, ValueError):
            continue
    for ref in abandoned_refs:
        if ref not in index:
            continue
        try:
            expected_briefs.add((content_object_stage_dir(task_id, batch_id, ref, STAGE_COMPOSE) / BRIEF_FILE).resolve())
        except (KeyError, OSError, ValueError):
            continue
    actual_briefs = {
        path.resolve()
        for path in (root / "posts").glob(f"*/*/*/*/{STAGE_COMPOSE}/{BRIEF_FILE}")
        if path.is_file()
    }
    extra_briefs = sorted(actual_briefs - expected_briefs)
    if extra_briefs:
        rels = [
            path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
            for path in extra_briefs[:20]
        ]
        issues.append(
            "posts contains brief(s) outside content_plan_packet/index: "
            + ", ".join(rels)
            + (" ..." if len(extra_briefs) > 20 else "")
        )
    rejected_sources = reject_source_ids(task_id, batch_id)
    seen_refs: set[str] = set()
    per_entity: dict[str, dict[str, list[Mapping[str, Any]]]] = {
        target: {"article": [], "image": []} for target in targets
    }
    base_source_owners: dict[str, str] = {}
    source_asset_owners: dict[str, str] = {}
    source_asset_sha_owners: dict[str, str] = {}
    source_collection_owners: dict[str, str] = {}

    def _claim_asset(owner_ref: str, asset_ref: str) -> None:
        if not asset_ref:
            return
        previous = source_asset_owners.get(asset_ref)
        if previous and previous != owner_ref:
            issues.append(
                f"item[{owner_ref}]: sourceAssetRef {asset_ref!r} reused by {previous}; "
                "same batch requires one source image asset per work"
            )
        source_asset_owners.setdefault(asset_ref, owner_ref)

    def _claim_asset_sha(owner_ref: str, asset_sha: str) -> None:
        asset_sha = asset_sha.removeprefix("sha256:").strip().lower()
        if not asset_sha:
            return
        previous = source_asset_sha_owners.get(asset_sha)
        if previous and previous != owner_ref:
            issues.append(
                f"item[{owner_ref}]: image sha256 {asset_sha[:16]!r} reused by {previous}; "
                "same batch requires one physical source image per work"
            )
        source_asset_sha_owners.setdefault(asset_sha, owner_ref)

    def _claim_collection(owner_ref: str, collection_id: str) -> None:
        if not collection_id:
            return
        previous = source_collection_owners.get(collection_id)
        if previous and previous != owner_ref:
            issues.append(
                f"item[{owner_ref}]: sourceCollectionId {collection_id!r} reused by {previous}; "
                "same batch requires one image collection per work"
            )
        source_collection_owners.setdefault(collection_id, owner_ref)

    for idx, item in enumerate(items, start=1):
        ref = str(item.get("ref") or "").strip()
        kind = str(item.get("kind") or "").strip()
        title = str(item.get("title") or "").strip()
        if not ref:
            issues.append(f"item[{idx}]: missing ref")
            continue
        if ref in seen_refs:
            issues.append(f"item[{idx}]: duplicate ref {ref!r}")
        seen_refs.add(ref)
        if kind not in ("entity", "route"):
            issues.append(f"item[{ref}]: kind must be entity|route, got {kind!r}")
        carrier = _item_carrier(item)
        raw_carrier = str(item.get("carrier") or item.get("contentType") or "article")
        if require_creator_assignment and carrier in {"article", "image", "video"}:
            for creator_issue in creator_assignment_issues(
                item,
                carrier=carrier,
                prefix=f"item[{ref}].creatorAssignment",
            ):
                issues.append(creator_issue)
        image_work_mode = carrier == "image" and (raw_carrier == "image" or separated_research)
        if not image_work_mode and not title:
            issues.append(f"item[{ref}]: missing title")
        if image_work_mode:
            if len(title) > 80:
                issues.append(f"item[{ref}]: image title exceeds 80 characters")
            if len(str(item.get("caption") or "")) > 300:
                issues.append(f"item[{ref}]: image caption exceeds 300 characters")
            if str(item.get("researchLane") or "") != "image":
                issues.append(f"item[{ref}]: image work must use researchLane=image")
            collection_id = str(item.get("sourceCollectionId") or "").strip()
            if not collection_id:
                issues.append(f"item[{ref}]: image work missing sourceCollectionId")
            else:
                _claim_collection(ref, collection_id)
            asset_refs = item.get("assetRefs") or []
            if not isinstance(asset_refs, list) or not (1 <= len(asset_refs) <= 20):
                issues.append(f"item[{ref}]: image work assetRefs must contain 1..20 items")
            elif len({str(asset) for asset in asset_refs}) != len(asset_refs):
                issues.append(f"item[{ref}]: image work assetRefs contains duplicates")
            else:
                for asset_ref in asset_refs:
                    asset_path = root / str(asset_ref)
                    if not asset_path.is_file():
                        issues.append(f"item[{ref}]: image asset not found: {asset_ref}")
                        continue
                    index_path = asset_path.parent / "index.json"
                    if not index_path.is_file():
                        issues.append(f"item[{ref}]: image asset index missing: {index_path}")
                        continue
                    try:
                        entries = read_json(index_path).get("assets") or []
                    except (OSError, ValueError, TypeError):
                        entries = []
                    entry = next(
                        (
                            row for row in entries
                            if isinstance(row, Mapping)
                            and str(row.get("fileName") or "") == asset_path.name
                        ),
                        None,
                    )
                    if not entry:
                        issues.append(f"item[{ref}]: image asset absent from index: {asset_ref}")
                    elif str(entry.get("sourceCollectionId") or "") != collection_id:
                        issues.append(
                            f"item[{ref}]: asset {asset_ref} crosses sourceCollectionId"
                        )
                    verdict = assess_image_publish_prefilter(asset_path)
                    if verdict.blocks_image_publish:
                        reason = "/".join(verdict.reasons) or verdict.status
                        issues.append(
                            f"item[{ref}]: image asset blocked by image safety gate: "
                            f"{asset_ref}:{reason}"
                        )
                    source_meta_path = asset_path.parent.parent / "meta.json"
                    if not source_meta_path.is_file():
                        issues.append(f"item[{ref}]: image asset source meta missing: {asset_ref}")
                    else:
                        try:
                            source_meta = read_json(source_meta_path)
                        except (OSError, ValueError, TypeError):
                            source_meta = {}
                        for focus_issue in _entity_focus_issues(
                            ref=ref,
                            carrier="image",
                            source_meta=source_meta if isinstance(source_meta, Mapping) else {},
                            item=item,
                        ):
                            issues.append(focus_issue)
                        if str(source_meta.get("researchLane") or "") != "image":
                            issues.append(
                                f"item[{ref}]: image asset must come from researchLane=image: "
                                f"{asset_ref}"
                            )
                    if entry:
                        _claim_asset_sha(ref, str(entry.get("sha256") or ""))
                    _claim_asset(ref, str(asset_ref))
        elif str(item.get("researchLane") or "article") != "article":
            issues.append(f"item[{ref}]: article must use researchLane=article")
        entity_refs = item.get("entityRefs") or []
        if not isinstance(entity_refs, list) or not entity_refs:
            issues.append(f"item[{ref}]: entityRefs required")
        elif kind == "route" and len(entity_refs) < 3:
            issues.append(f"item[{ref}]: route needs entityRefs>=3")
        if kind == "entity" and isinstance(entity_refs, list):
            matched_targets = [
                target
                for target in targets
                if any(str(entity_ref).rstrip("/").endswith("/" + target) for entity_ref in entity_refs)
            ]
            if len(matched_targets) != 1:
                issues.append(
                    f"item[{ref}]: entity item must map to exactly one coverage target, got {matched_targets}"
                )
            else:
                bucket = "image" if carrier == "image" else "article"
                per_entity[matched_targets[0]][bucket].append(item)
        evidence = item.get("evidenceRefs") or []
        if not isinstance(evidence, list) or not evidence:
            issues.append(f"item[{ref}]: evidenceRefs required")
        else:
            for ev in evidence:
                ev_path = root / str(ev)
                if not ev_path.is_file():
                    issues.append(f"item[{ref}]: evidence not found: {ev}")
        # 证据准入硬门：content_plan 不得引用 source_screen_gate=reject 的来源。
        cited = [str(e) for e in (evidence if isinstance(evidence, list) else [])]
        if item.get("baseSourceRef"):
            cited.append(str(item.get("baseSourceRef")))
        for sid in sorted(rejected_sources):
            for c in cited:
                if sid and sid in c:
                    issues.append(
                        f"item[{ref}]: cites rejected source {sid!r} "
                        f"(source_screen_gate=reject 必须 fallback download_fetch，不得进入 content_plan)"
                    )
                    break
        if not str(item.get("rationale") or "").strip():
            issues.append(f"item[{ref}]: missing rationale")
        base_source_ref = str(item.get("baseSourceRef") or "").strip()
        source_use_mode = str(item.get("sourceUseMode") or "").strip()
        if carrier != "image" and strict_rights_mode and source_use_mode not in (
            "licensed_adaptation",
            "factual_reference_only",
        ):
            issues.append(f"item[{ref}]: sourceUseMode required for scaled task")
        if carrier != "image" and strict_rights_mode and not base_source_ref:
            issues.append(f"item[{ref}]: article baseSourceRef required for scaled task")
        if carrier != "image" and base_source_ref:
            source_meta = _source_meta(root, base_source_ref)
            # 单实体聚焦门只约束 kind=entity 文章底稿；kind=route（网站角度环线）
            # 本就用跨多个地点的多地点游记作底稿，由 routeCoverage/entityRefs>=3 把关，
            # 不能用单实体聚焦门拦截，否则环线底稿会被误判 off_entity 而无法成稿。
            if kind != "route":
                for focus_issue in _entity_focus_issues(
                    ref=ref,
                    carrier="article",
                    source_meta=source_meta,
                    item=item,
                ):
                    issues.append(focus_issue)
            actual_mode = str(source_meta.get("sourceUseMode") or "").strip()
            if actual_mode == "blocked":
                issues.append(f"item[{ref}]: baseSourceRef points to blocked source")
            if source_use_mode and actual_mode and source_use_mode != actual_mode:
                issues.append(
                    f"item[{ref}]: sourceUseMode {source_use_mode!r} "
                    f"does not match source meta {actual_mode!r}"
                )
            research_lane = str(source_meta.get("researchLane") or "")
            if research_lane not in ("", "legacy", "article"):
                issues.append(
                    f"item[{ref}]: article baseSourceRef must come from article research, got {research_lane!r}"
                )
            source_role = str(source_meta.get("sourceRole") or "").strip()
            source_id = str(source_meta.get("sourceId") or "").strip()
            if strict_rights_mode and source_role not in ARTICLE_BASE_SOURCE_ROLES:
                issues.append(
                    f"item[{ref}]: article baseSourceRef must point to sourceRole=base, "
                    f"got {source_role or '<missing>'} ({source_id or base_source_ref})"
                )
            unit_name = (root / base_source_ref).parent.name
            if strict_rights_mode and source_role == "supporting":
                issues.append(
                    f"item[{ref}]: supporting source {source_id or unit_name!r} "
                    "cannot be used as article baseSourceRef"
                )
            category = _article_source_category(source_meta)
            if strict_rights_mode and category:
                category_norm = category.lower().replace("-", "_").replace(" ", "_")
                if category_norm in ARTICLE_SUPPORTING_ONLY_CATEGORIES:
                    issues.append(
                        f"item[{ref}]: article baseSourceRef category {category!r} "
                        "is supporting-only and cannot be used as article base"
                    )
                elif category_norm not in ARTICLE_BASE_SOURCE_CATEGORIES and "攻略" not in category and "游记" not in category:
                    issues.append(
                        f"item[{ref}]: article baseSourceRef category {category!r} "
                        "is not an approved article base category"
                    )
            base_text_len = _compact_len(load_base_draft_text(task_id, batch_id, base_source_ref))
            if strict_rights_mode and base_text_len < ARTICLE_MIN_BASE_DRAFT_CHARS:
                issues.append(
                    f"item[{ref}]: baseSourceRef usable text too short "
                    f"({base_text_len} < {ARTICLE_MIN_BASE_DRAFT_CHARS})"
                )
            reuse_policy = str(item.get("baseSourceReusePolicy") or "").strip()
            if strict_rights_mode and reuse_policy:
                issues.append(
                    f"item[{ref}]: baseSourceReusePolicy is not allowed for scaled separated_research; "
                    "article baseSourceRef must be one-source-one-work"
                )
            previous = base_source_owners.get(base_source_ref)
            if previous and previous != ref and (
                strict_rights_mode or reuse_policy != "multi_intent_source_bundle"
            ):
                issues.append(
                    f"item[{ref}]: baseSourceRef reused by {previous}; main evidence must be one-source-one-work"
                )
            base_source_owners.setdefault(base_source_ref, ref)
            asset_rows = _source_asset_rows(root, base_source_ref)
            row_by_asset_ref = {
                _source_asset_ref(task_id, batch_id, root, base_source_ref, asset): asset
                for asset in asset_rows
            }
            declared_asset_refs = [
                str(asset_ref).strip()
                for asset_ref in (item.get("assetRefs") or [])
                if str(asset_ref).strip()
            ]
            if declared_asset_refs and len(set(declared_asset_refs)) != len(declared_asset_refs):
                issues.append(f"item[{ref}]: article assetRefs contains duplicates")
            for atomic_issue in og.source_unit_atomicity_issues(
                base_source_ref=base_source_ref,
                asset_refs=declared_asset_refs,
                supporting_refs=item.get("sourceUnitRefs") or [],
            ):
                issues.append(f"item[{ref}]: {atomic_issue}")
                og.append_conflict(
                    task_id,
                    batch_id,
                    conflict_type="source_unit_atomicity",
                    subject=str(base_source_ref),
                    refs=[str(ref)],
                    reason=atomic_issue,
                )
            for asset_ref in declared_asset_refs:
                asset_path = root / asset_ref
                source_dir = (root / base_source_ref).parent
                if not asset_path.is_file():
                    issues.append(f"item[{ref}]: article asset not found: {asset_ref}")
                    continue
                try:
                    asset_path.relative_to(source_dir / "assets")
                except ValueError:
                    issues.append(
                        f"item[{ref}]: article assetRefs must belong to baseSourceRef assets: "
                        f"{asset_ref}"
                    )
                    continue
                asset = row_by_asset_ref.get(asset_ref)
                if not isinstance(asset, Mapping):
                    issues.append(f"item[{ref}]: article asset metadata missing: {asset_ref}")
                    continue
                missing_asset_fields = [
                    field
                    for field in ("license", "credit", "sourceUrl", "termsUrl", "usageScope")
                    if not str(asset.get(field) or "").strip()
                ]
                if missing_asset_fields:
                    issues.append(
                        f"item[{ref}]: baseSourceRef asset {asset.get('fileName') or '?'} "
                        f"missing rights fields {missing_asset_fields}"
                    )
                asset_row = row_by_asset_ref.get(asset_ref)
                if not asset_row:
                    issues.append(f"item[{ref}]: article asset absent from base source index: {asset_ref}")
                    continue
                verdict = assess_image_publish_prefilter(asset_path)
                if verdict.blocks_image_publish:
                    reason = "/".join(verdict.reasons) or verdict.status
                    issues.append(
                        f"item[{ref}]: article asset blocked by image safety gate: "
                        f"{asset_ref}:{reason}"
                    )
                _claim_asset(ref, asset_ref)
                _claim_asset_sha(ref, str(asset_row.get("sha256") or ""))
                _claim_collection(ref, str(asset_row.get("sourceCollectionId") or ""))
        if carrier != "image":
            for msg in writing_intent_issues(item.get("writingIntent")):
                issues.append(f"item[{ref}]: {msg}")
        if ref not in index:
            issues.append(f"item[{ref}]: not registered in content_object_index")
        else:
            brief_path = content_object_stage_dir(task_id, batch_id, ref, STAGE_COMPOSE) / BRIEF_FILE
            if not brief_path.is_file():
                issues.append(f"item[{ref}]: missing 3.compose/brief.json")

    for target, buckets in per_entity.items():
        articles = buckets["article"]
        galleries = buckets["image"]
        target_abandoned_articles = _abandoned_refs_for_target(
            abandoned_refs, target, carrier="article"
        )
        target_abandoned_galleries = _abandoned_refs_for_target(
            abandoned_refs, target, carrier="image"
        )
        effective_target_articles = max(0, per_target_articles - len(target_abandoned_articles))
        effective_target_galleries = max(0, per_target_galleries - len(target_abandoned_galleries))
        if per_target_articles and len(articles) != effective_target_articles:
            issues.append(
                f"{target}: entityArticlesPerTarget quota {per_target_articles} "
                f"(minus abandoned {len(target_abandoned_articles)} => {effective_target_articles}) "
                f"but packet has {len(articles)}"
            )
        if per_target_galleries and image_quota_hard and len(galleries) != effective_target_galleries:
            issues.append(
                f"{target}: imageWorksPerTarget quota {per_target_galleries} "
                f"(minus abandoned {len(target_abandoned_galleries)} => {effective_target_galleries}) "
                f"but packet has {len(galleries)}"
            )
        if per_target_articles == 2:
            intents = sorted(str(item.get("writingIntent") or "") for item in articles)
            abandoned_intents = _abandoned_intents_for_target(abandoned_refs, target)
            expected = sorted(
                intent
                for intent in ("planning_consultation", "decision_experience")
                if intent not in abandoned_intents
            )
            if intents != expected:
                issues.append(
                    f"{target}: entity articles must split planning_consultation and "
                    f"decision_experience (minus abandoned {sorted(abandoned_intents)} => {expected}), "
                    f"got {intents}"
                )
        if required_article_intents and per_target_articles == len(required_article_intents):
            intents = sorted(str(item.get("writingIntent") or "") for item in articles)
            abandoned_intents = _abandoned_intents_for_target(abandoned_refs, target)
            expected = sorted(
                intent for intent in required_article_intents if intent not in abandoned_intents
            )
            if intents != expected:
                issues.append(
                    f"{target}: entity articles must match acceptance.requiredAngles "
                    f"{expected}, got {intents}"
                )
        if len(galleries) > 1:
            titles = [str(item.get("title") or "").strip() for item in galleries]
            non_empty_titles = [title for title in titles if title]
            if len(set(non_empty_titles)) != len(non_empty_titles):
                issues.append(f"{target}: titled image works must use distinct visual themes")
            collection_asset_sets: dict[str, set[str]] = {}
            for image_work in galleries:
                collection = str(image_work.get("sourceCollectionId") or "")
                assets = {str(asset) for asset in (image_work.get("assetRefs") or [])}
                previous = collection_asset_sets.setdefault(collection, set())
                if previous & assets:
                    issues.append(
                        f"{target}: image works reuse assets from collection {collection!r}"
                    )
                previous.update(assets)

    return issues


def content_plan_quotas_required(spec: Mapping[str, Any]) -> bool:
    if site_supply_dynamic_content_plan(spec):
        return True
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    return bool(
        int(quotas.get("entityArticles") or 0)
        or int(quotas.get("routeArticles") or 0)
        or int(quotas.get("entityArticlesPerTarget") or 0)
        or int(quotas.get("imageWorksPerTarget") or 0)
        or int(quotas.get("entityHomepagesPerTarget") or 0)
        or (
            str(content.get("modalityContract") or "") != "separated_research"
            and (
                int(quotas.get("galleryPosts") or 0)
                or int(quotas.get("galleryPostsPerTarget") or 0)
            )
        )
    )


def load_writing_intent_overrides(task_id: str, batch_id: str) -> dict[str, dict[str, Any]]:
    """从 content_plan_packet 读取每篇 writingIntent / baseSourceRef，供 compose 注入 brief。

    返回 {ref: {"writingIntent": ..., "baseSourceRef": ...}}（仅含已声明的字段）。
    这是 content_plan(任务层) → brief(写作契约) 的单一贯通点，保证即使 Agent 没把
    writingIntent 写进 brief.json，writing_pack/prompt 仍有正确主线。
    """
    packet = load_content_plan_packet(task_id, batch_id) or {}
    overrides: dict[str, dict[str, Any]] = {}
    for item in _items(packet):
        ref = str(item.get("ref") or "").strip()
        if not ref:
            continue
        row: dict[str, Any] = {}
        for field in (
            "writingIntent",
            "baseSourceRef",
            "baseSourceReusePolicy",
            "carrier",
            "sourceCollectionId",
            "assetRefs",
            "authorId",
            "creatorProfileId",
            "creatorArchetype",
            "creatorProfileVersion",
            "creatorDisclosure",
            "experienceClaimMode",
            "authorQualitySignals",
            "creator",
        ):
            if item.get(field) not in (None, ""):
                row[field] = item.get(field)
        if row:
            overrides[ref] = row
    return overrides
