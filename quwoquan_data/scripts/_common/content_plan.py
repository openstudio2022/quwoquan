"""证据驱动篇目规划包（content_plan_packet）校验。

真相源：batches/{batch}/_shared/content_plan_packet.json
见 content_pipeline_spec.md §1.2.1
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.content_object import BRIEF_FILE, content_object_stage_dir, load_index
from _common.io import read_json
from _common.paths import (
    STAGE_COMPOSE,
    batch_content_plan_packet_path,
    batch_results_dir,
    batch_root,
)
from _common.quality_gates import WRITING_INTENTS, writing_intent_issues

CONTENT_PLAN_SCHEMA = "quwoquan_data.content_plan_packet"


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


def _items(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = packet.get("items") or []
    return [i for i in raw if isinstance(i, dict)]


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


def validate_content_plan(task_id: str, batch_id: str, spec: Mapping[str, Any]) -> list[str]:
    """校验 content_plan 是否满足配额与证据链。"""
    issues: list[str] = []
    packet = load_content_plan_packet(task_id, batch_id)
    if packet is None:
        return ["content_plan_packet.json missing under batch _shared/"]

    items = _items(packet)
    if not items:
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
    targets = [
        str(target.get("name") or "").strip()
        for target in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    ]
    if per_target_articles:
        want_entity = per_target_articles * len(targets)
    if per_target_galleries:
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

    if want_entity or want_route or want_gallery:
        entity_article_n = sum(
            1 for i in items
            if str(i.get("kind") or "") == "entity" and _item_carrier(i) != "image"
        )
        gallery_n = sum(1 for i in items if _item_carrier(i) == "image")
        route_n = sum(1 for i in items if str(i.get("kind") or "") == "route")
        if want_entity and entity_article_n != want_entity:
            issues.append(f"entityArticles quota {want_entity} but packet has {entity_article_n}")
        if want_gallery and gallery_n != want_gallery:
            issues.append(f"imageWorks quota {want_gallery} but packet has {gallery_n}")
        if want_route and route_n != want_route:
            issues.append(f"routeArticles quota {want_route} but packet has {route_n}")

    root = batch_root(task_id, batch_id)
    index = load_index(task_id, batch_id)
    rejected_sources = reject_source_ids(task_id, batch_id)
    seen_refs: set[str] = set()
    per_entity: dict[str, dict[str, list[Mapping[str, Any]]]] = {
        target: {"article": [], "image": []} for target in targets
    }
    base_source_owners: dict[str, str] = {}

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
        image_v2 = carrier == "image" and (raw_carrier == "image" or separated_research)
        if not image_v2 and not title:
            issues.append(f"item[{ref}]: missing title")
        if image_v2:
            if len(title) > 80:
                issues.append(f"item[{ref}]: image title exceeds 80 characters")
            if len(str(item.get("caption") or "")) > 300:
                issues.append(f"item[{ref}]: image caption exceeds 300 characters")
            if str(item.get("researchLane") or "") != "image":
                issues.append(f"item[{ref}]: image work must use researchLane=image")
            collection_id = str(item.get("sourceCollectionId") or "").strip()
            if not collection_id:
                issues.append(f"item[{ref}]: image work missing sourceCollectionId")
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
        if carrier != "image" and base_source_ref:
            meta_path = (root / base_source_ref).parent / "meta.json"
            if meta_path.is_file():
                try:
                    source_meta = read_json(meta_path)
                    actual_mode = str(source_meta.get("sourceUseMode") or "").strip()
                except (OSError, ValueError):
                    source_meta = {}
                    actual_mode = ""
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
            previous = base_source_owners.get(base_source_ref)
            if previous and previous != ref:
                issues.append(
                    f"item[{ref}]: baseSourceRef reused by {previous}; main evidence must be one-source-one-work"
                )
            base_source_owners[base_source_ref] = ref
            asset_rows = _source_asset_rows(root, base_source_ref)
            if strict_rights_mode and not asset_rows:
                issues.append(
                    f"item[{ref}]: article baseSourceRef must be a text+image source unit; "
                    f"no assets found under {base_source_ref}"
                )
            for asset in asset_rows:
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
        if per_target_articles and len(articles) != per_target_articles:
            issues.append(
                f"{target}: entityArticlesPerTarget quota {per_target_articles} but packet has {len(articles)}"
            )
        if per_target_galleries and len(galleries) != per_target_galleries:
            issues.append(
                f"{target}: imageWorksPerTarget quota {per_target_galleries} but packet has {len(galleries)}"
            )
        if per_target_articles == 2:
            intents = sorted(str(item.get("writingIntent") or "") for item in articles)
            expected = sorted(["planning_consultation", "decision_experience"])
            if intents != expected:
                issues.append(
                    f"{target}: two entity articles must split planning_consultation and "
                    f"decision_experience, got {intents}"
                )
        if required_article_intents and per_target_articles == len(required_article_intents):
            intents = sorted(str(item.get("writingIntent") or "") for item in articles)
            expected = sorted(required_article_intents)
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
            "carrier",
            "sourceCollectionId",
            "assetRefs",
        ):
            if item.get(field) not in (None, ""):
                row[field] = item.get(field)
        if row:
            overrides[ref] = row
    return overrides
