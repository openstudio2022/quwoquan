"""Commercial scale readiness gate for managed content batches.

The gate is intentionally conservative: a batch that cannot prove source
sufficiency, token/cost accounting, queue backend, release, and import evidence
is a No-Go for scale even when some early lane checks passed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from _common.article_commercial_policy import article_commercial_closure_enabled
from _common.base_draft import load_base_draft_text
from _common.draft_io import is_placeholder
from _common.download_diagnostics import download_diagnostics
from _common.image_asset_strategy import (
    OPEN_LICENSE_PUBLISH,
    REFERENCE_ONLY_NO_IMAGE_RELEASE,
    image_asset_strategy,
    image_strategy_release_allowed,
    image_strategy_requires_publishable_images,
)
from _common.io import read_json, write_json
from _common.paths import RUNTIME_ROOT, batch_root, release_root
from _common.release_integrity import scan_release_integrity, scan_runtime_batch_integrity
from _common.source_unit import iter_source_units
from verify.scale_readiness_capacity import (
    creator_load_report as _creator_load_report,
    resolve_agent_active as _resolve_agent_active,
    throughput_projection as _throughput_projection,
    token_ledger_paths as _token_ledger_paths,
)


SCHEMA = "quwoquan_data.scale_readiness"
DEFAULT_DAILY_TARGET = 10_000
MIN_SOURCE_SUFFICIENCY = 0.98
MIN_FIRST_PASS_RATE = 0.70
MAX_TRIAL_ABANDONED_CONTENT_RATIO = 0.05
STRUCTURAL_IMAGE_SHORTAGE_MIN_COUNT = 5
STRUCTURAL_IMAGE_SHORTAGE_RATIO = 0.30
DEFAULT_SCALE_SOURCE_READY_MULTIPLIER = 1.2


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _compact_len(value: str) -> int:
    return len("".join(str(value or "").split()))


def _quotas(spec: Mapping[str, Any]) -> dict[str, int]:
    raw = ((spec.get("content") or {}).get("quotas") or {})
    return {
        "homepage": _safe_int(raw.get("entityHomepagesPerTarget")),
        "article": _safe_int(raw.get("entityArticlesPerTarget") or raw.get("entityArticles")),
        "image": _safe_int(raw.get("imageWorksPerTarget") or raw.get("galleryPostsPerTarget") or raw.get("galleryPosts")),
        "routeArticle": _safe_int(raw.get("routeArticles")),
    }


def _target_count(spec: Mapping[str, Any], audit: Mapping[str, Any]) -> int:
    count = _safe_int(audit.get("targetCount"))
    if count:
        return count
    targets = ((spec.get("scope") or {}).get("coverageTargets") or [])
    return len(targets) if isinstance(targets, list) else 0


def _partial_content_allowed(spec: Mapping[str, Any]) -> bool:
    policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    return bool(policy.get("allowPartialContent", True) is not False)


def _commercial_target_object_count(spec: Mapping[str, Any]) -> int:
    policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    return _safe_int(policy.get("targetObjectCount") if isinstance(policy, Mapping) else 0)


def _expected_objects(spec: Mapping[str, Any], audit: Mapping[str, Any]) -> dict[str, int]:
    count = _target_count(spec, audit)
    quotas = _quotas(spec)
    if article_commercial_closure_enabled(spec):
        target_object_count = _commercial_target_object_count(spec)
        if target_object_count > 0:
            article_ratio = max(0, quotas["article"])
            image_ratio = max(0, quotas["image"])
            total_ratio = article_ratio + image_ratio
            if total_ratio > 0:
                article_expected = int(round(target_object_count * (article_ratio / total_ratio)))
                article_expected = max(0, min(target_object_count, article_expected))
                image_expected = max(0, target_object_count - article_expected)
            else:
                article_expected = 0
                image_expected = 0
            homepage_expected = count * quotas["homepage"]
            return {
                "homepage": homepage_expected,
                "article": article_expected,
                "image": image_expected,
                "routeArticle": quotas["routeArticle"],
                "total": homepage_expected + target_object_count + quotas["routeArticle"],
            }
    return {
        "homepage": count * quotas["homepage"],
        "article": count * quotas["article"],
        "image": count * quotas["image"],
        "routeArticle": quotas["routeArticle"],
        "total": count * (quotas["homepage"] + quotas["article"] + quotas["image"]) + quotas["routeArticle"],
    }


def _active_scale_spec(task_id: str, batch_id: str, spec: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from task.run import _active_spec
        from task.run_context import PipelineContext

        scope = spec.get("scope") if isinstance(spec.get("scope"), Mapping) else {}
        entity_ids = [
            str(target.get("name") or "").strip()
            for target in (scope.get("coverageTargets") or [])
            if isinstance(target, Mapping) and str(target.get("name") or "").strip()
        ]
        active = _active_spec(
            PipelineContext(
                task_id=task_id,
                batch_id=batch_id,
                entity_ids=entity_ids,
                spec=dict(spec),
            )
        )
        active_targets = ((active.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(active_targets, list) and active_targets:
            return active
    except Exception:  # noqa: BLE001 - scale gate must still report other blockers.
        return spec
    return spec


def _content_plan_item_count(root: Path) -> dict[str, int]:
    packet = _load_json_if_exists(root / "_shared" / "content_plan_packet.json")
    items = packet.get("items") if isinstance(packet.get("items"), list) else []
    rows = {"total": len(items), "article": 0, "image": 0, "video": 0, "route": 0}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        carrier = str(item.get("carrier") or item.get("contentType") or "article")
        kind = str(item.get("kind") or "")
        if carrier in {"image", "gallery"}:
            rows["image"] += 1
        elif carrier == "video":
            rows["video"] += 1
        else:
            rows["article"] += 1
        if kind == "route":
            rows["route"] += 1
    return rows


def _authored_object_count(root: Path) -> dict[str, int]:
    rows = {"total": 0, "article": 0}
    posts_root = root / "posts"
    if not posts_root.is_dir():
        return rows
    for draft in sorted(posts_root.rglob("4.draft/draft.article.md")):
        try:
            text = draft.read_text(encoding="utf-8")
        except OSError:
            continue
        if is_placeholder(text):
            continue
        meta = _load_json_if_exists(draft.parent / "draft_meta.json")
        if str(meta.get("generator") or "") != "agent":
            continue
        rows["total"] += 1
        rows["article"] += 1
    return rows


def _homepage_passed_count(root: Path) -> int:
    count = 0
    entities_root = root / "entities"
    if not entities_root.is_dir():
        return 0
    for report_path in sorted(entities_root.rglob("5.review/finalization_report.json")):
        report = _load_json_if_exists(report_path)
        if not report:
            continue
        status = str(report.get("status") or report.get("decision") or "").lower()
        if status in {"passed", "approved", "done", "accepted", "success", "succeeded"} or bool(report.get("passed")):
            count += 1
            continue
        entity_dir = report_path.parent.parent
        if (
            (entity_dir / "_entity.json").is_file()
            and (entity_dir / "page.md").is_file()
            and (entity_dir / "manifest.json").is_file()
            and (entity_dir / "5.review" / "review.json").is_file()
            and (entity_dir / "5.review" / "provenance.json").is_file()
            and str(report.get("draftArticleRef") or "") == "4.draft/page.md"
            and str(report.get("finalArticleRef") or "") == "page.md"
            and str(report.get("draftSha256") or "").strip()
            and str(report.get("finalSha256") or "").strip()
        ):
            count += 1
    return count


def _quality_target_report(root: Path) -> dict[str, Any]:
    return _load_json_if_exists(root / "_shared" / "quality_target_report.json")


def _source_unit_lane(meta: Mapping[str, Any], source_dir: Path) -> str:
    lane = str(meta.get("researchLane") or "").strip().lower()
    if lane in {"homepage", "article", "image", "video"}:
        return lane
    category = str(meta.get("category") or meta.get("sourceCategory") or "").lower()
    source_id = str(meta.get("sourceId") or source_dir.name).lower()
    if "home" in source_id or "baike" in source_id or "official" in source_id or category in {"encyclopedia", "official"}:
        return "homepage"
    if "image" in source_id or "photo" in source_id or category in {"image", "photo"}:
        return "image"
    return "article"


def _source_ref_relative_to_root(source_path: Path, root: Path) -> str:
    try:
        return source_path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        try:
            return source_path.relative_to(root).as_posix()
        except ValueError:
            return ""


def _site_supply_dynamic_image_capacity(
    spec: Mapping[str, Any],
    root: Path,
) -> dict[str, int] | None:
    workflow = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    quotas = _quotas(spec)
    targets = (spec.get("scope") or {}).get("coverageTargets") or []
    if workflow.get("siteSupplyDynamicContentPlan") is not True:
        return None
    if len(targets) != 1:
        return None
    if quotas["homepage"] > 0 or quotas["article"] > 0 or quotas["image"] <= 0:
        return None
    plan = _load_json_if_exists(root / "_shared" / "site_supply_content_plan_report.json")
    if not plan:
        return None
    selected_count = _safe_int(plan.get("selectedCount") or plan.get("itemCount"))
    vertical = str(plan.get("vertical") or "").strip()
    site_id = str(plan.get("siteId") or "").strip()
    site_batch_id = str(plan.get("batchId") or "").strip()
    if not vertical or not site_id or not site_batch_id:
        return {"selectedCount": selected_count, "qualifiedImageWorks": selected_count}
    ingest = _load_json_if_exists(
        RUNTIME_ROOT
        / "site_supply"
        / vertical
        / site_id
        / site_batch_id
        / "_shared"
        / "attributed_asset_ingest_report.json"
    )
    qualified = _safe_int(((ingest.get("funnel") or {}).get("qualifiedImageWorks")))
    return {
        "selectedCount": selected_count,
        "qualifiedImageWorks": max(selected_count, qualified),
    }


def _normalized_source_kind(meta: Mapping[str, Any]) -> str:
    """归一化源站类别（sourceMixBreakdown 用）：优先 sourceKind，退回 platform/url。"""
    kind = str(meta.get("sourceKind") or "").strip().lower()
    if kind:
        return kind
    platform = str(meta.get("platform") or "").strip()
    url = str(meta.get("url") or meta.get("canonicalUrl") or "").lower()
    haystack = f"{platform.lower()} {url}"
    if "wikipedia" in haystack or "维基" in platform:
        return "wikipedia"
    if "baike.baidu" in haystack or "百度百科" in platform:
        return "baidu_baike"
    if "baike.sogou" in haystack or "搜狗百科" in platform:
        return "sogou_baike"
    if "toutiao" in haystack or "头条百科" in platform:
        return "toutiao_baike"
    if "官网" in platform or "official" in haystack:
        return "official"
    return platform.lower() or "unknown"


def _source_admission_report(
    task_id: str,
    batch_id: str,
    spec: Mapping[str, Any],
    root: Path,
) -> dict[str, Any]:
    quotas = _quotas(spec)
    targets = [
        str(target.get("name") or "").strip()
        for target in ((spec.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    ]
    dynamic_image_capacity = _site_supply_dynamic_image_capacity(spec, root)
    per_entity: list[dict[str, Any]] = []
    ready_capacity = 0
    source_ready_entities = 0
    # H100/H1000 准出证据：homepage 主源源站组合分布（wikipedia/baidu_baike/...）。
    source_mix: dict[str, int] = {}
    for name in targets:
        entity_dirs = [
            refs_path.parent.parent
            for refs_path in sorted((root / "entities").glob(f"*/**/{name}/1.download/source_refs.json"))
        ]
        counts = {"homepage": 0, "article": 0, "image": 0, "video": 0}
        focus_blocked = 0
        for object_dir in entity_dirs:
            for source_dir in iter_source_units(object_dir):
                meta = _load_json_if_exists(source_dir / "meta.json")
                focus = str(meta.get("entityFocusVerdict") or meta.get("focusVerdict") or "").lower()
                if focus in {"weak", "supporting_only", "mismatch", "off_entity"}:
                    focus_blocked += 1
                    continue
                lane = _source_unit_lane(meta, source_dir)
                if lane == "homepage":
                    kind = _normalized_source_kind(meta)
                    source_mix[kind] = source_mix.get(kind, 0) + 1
                source_path = source_dir / "source.md"
                source_ref = _source_ref_relative_to_root(source_path, root) if source_path.is_file() else ""
                if lane == "article":
                    # RC6：文章可发布性计数走形态自适应唯一真相源 base_draft_readiness
                    # （长文≥600 或 图文混排正文≥200+足量内联图/图注），不再裸 `>= 600`。
                    from _common.base_draft import base_draft_readiness

                    if source_ref and base_draft_readiness(
                        load_base_draft_text(task_id, batch_id, source_ref)
                    )["ready"]:
                        counts["article"] += 1
                elif lane == "image":
                    index = _load_json_if_exists(source_dir / "assets" / "index.json")
                    assets = index.get("assets") if isinstance(index.get("assets"), list) else []
                    if assets:
                        counts["image"] += 1
                elif lane == "homepage":
                    if source_ref and _compact_len(load_base_draft_text(task_id, batch_id, source_ref)) >= 120:
                        counts["homepage"] += 1
                elif lane == "video":
                    counts["video"] += 1
        if dynamic_image_capacity and len(targets) == 1:
            counts["image"] = max(
                counts["image"],
                _safe_int(dynamic_image_capacity.get("qualifiedImageWorks")),
            )
        needed = {
            "homepage": max(0, quotas["homepage"]),
            "article": max(0, quotas["article"]),
            "image": max(0, quotas["image"]),
        }
        source_ready = all(counts[lane] >= needed[lane] for lane in needed if needed[lane] > 0)
        if source_ready:
            source_ready_entities += 1
        capacity = sum(counts[lane] for lane in needed if needed[lane] > 0)
        ready_capacity += capacity
        per_entity.append(
            {
                "entity": name,
                "sourceReady": source_ready,
                "counts": counts,
                "needed": needed,
                "readyCapacity": capacity,
                "focusBlockedSourceUnits": focus_blocked,
            }
        )
    return {
        "schemaVersion": "quwoquan_data.source_ready_admission/1",
        "targetEntityCount": len(targets),
        "sourceReadyEntityCount": source_ready_entities,
        "sourceReadyObjectCapacity": ready_capacity,
        "requiredPerEntity": {
            "homepage": quotas["homepage"],
            "article": quotas["article"],
            "image": quotas["image"],
        },
        "sourceMixBreakdown": dict(sorted(source_mix.items(), key=lambda kv: kv[1], reverse=True)),
        "perEntity": per_entity,
    }


def _lane_rates(audit: Mapping[str, Any], target_count: int) -> dict[str, dict[str, float | int]]:
    rows: dict[str, dict[str, float | int]] = {}
    passed = audit.get("lanePassed") or {}
    for lane in ("homepage", "article", "image"):
        value = _safe_int(passed.get(lane) if isinstance(passed, Mapping) else 0)
        rows[lane] = {
            "passed": value,
            "targetCount": target_count,
            "rate": round(value / target_count, 4) if target_count else 0.0,
        }
    return rows


def _issue_texts(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    texts: list[str] = []
    for item in items:
        if isinstance(item, Mapping):
            for key in ("reason", "message", "issue"):
                value = str(item.get(key) or "").strip()
                if value:
                    texts.append(value)
            issues = item.get("issues")
            if isinstance(issues, list):
                texts.extend(str(value).strip() for value in issues if str(value).strip())
        else:
            value = str(item or "").strip()
            if value:
                texts.append(value)
    return texts


def _abandonment_reason_summary(audit: Mapping[str, Any]) -> dict[str, Any]:
    texts: list[str] = []
    texts.extend(_issue_texts(audit.get("abandonedObjects")))
    texts.extend(_issue_texts(audit.get("abandonedContentObjects")))
    texts.extend(_issue_texts(audit.get("failedLanes")))

    categories = {
        "imageOpenLicenseShortage": 0,
        "imageRightsOrLicense": 0,
        "imageFetchOrQuality": 0,
        "entityFocusGap": 0,
        "articleSourceShortage": 0,
        "homepageSourceShortage": 0,
        "workflowInterrupted": 0,
        "other": 0,
    }
    samples: dict[str, list[str]] = {key: [] for key in categories}

    def add(category: str, text: str) -> None:
        categories[category] += 1
        if len(samples[category]) < 5:
            samples[category].append(text)

    for text in texts:
        lowered = text.lower()
        if (
            "no rights-compatible open-license" in lowered
            or "openverse/wikimedia" in lowered
            or "single-author/single-file rights-cleared image collection" in lowered
        ):
            add("imageOpenLicenseShortage", text)
        elif "rights" in lowered or "license" in lowered or "copyright" in lowered:
            add("imageRightsOrLicense", text)
        elif (
            "imagefetch" in lowered
            or "non-image" in lowered
            or "pixel" in lowered
            or "watermark" in lowered
            or "duplicate" in lowered
            or "too small" in lowered
        ):
            add("imageFetchOrQuality", text)
        elif "entity_focus_off_topic" in lowered or "entity_focus_gate" in lowered:
            # 诚实弃稿：实体角度无聚焦底稿（多地点环线/跑题），非流水线失败。
            add("entityFocusGap", text)
        elif "article sources" in lowered or "article base sources" in lowered or "article research needs" in lowered:
            add("articleSourceShortage", text)
        elif "homepage" in lowered and ("sources" in lowered or "research needs" in lowered):
            add("homepageSourceShortage", text)
        elif "interrupted" in lowered or "workflow stopped" in lowered:
            add("workflowInterrupted", text)
        else:
            add("other", text)

    ranked = [
        {"category": key, "count": value, "samples": samples[key]}
        for key, value in sorted(categories.items(), key=lambda item: item[1], reverse=True)
        if value
    ]
    return {
        "totalIssueTexts": len(texts),
        "categories": categories,
        "dominantReasons": ranked[:5],
    }


def _abandoned_content_by_type(task_id: str, batch_id: str, audit: Mapping[str, Any]) -> dict[str, int]:
    from _common import content_object

    rows = audit.get("abandonedContentObjects")
    if not isinstance(rows, list):
        return {}
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        ref = str(row.get("ref") or "").strip()
        if not ref:
            continue
        coords = content_object.content_coords(task_id, batch_id, ref) or {}
        content_type = str(row.get("carrier") or row.get("contentType") or coords.get("contentType") or "")
        if not content_type:
            content_type = "image" if ref.endswith("_image") or "_image_" in ref else "article"
        counts[content_type] = counts.get(content_type, 0) + 1
    return counts


def _research_policy(spec: Mapping[str, Any]) -> Mapping[str, Any]:
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    research = content.get("research") if isinstance(content.get("research"), Mapping) else {}
    return research


def _image_strategy_readiness(
    spec: Mapping[str, Any],
    audit: Mapping[str, Any],
    expected: Mapping[str, int],
    reason_summary: Mapping[str, Any],
) -> dict[str, Any]:
    research = _research_policy(spec)
    strategy = image_asset_strategy(spec)
    categories = reason_summary.get("categories") if isinstance(reason_summary.get("categories"), Mapping) else {}
    abandoned_count = _safe_int(audit.get("abandonedCount"))
    shortage_count = _safe_int((categories or {}).get("imageOpenLicenseShortage"))
    threshold = max(
        STRUCTURAL_IMAGE_SHORTAGE_MIN_COUNT,
        int(max(1, abandoned_count) * STRUCTURAL_IMAGE_SHORTAGE_RATIO),
    )
    structural_shortage = bool(
        strategy == OPEN_LICENSE_PUBLISH
        and _safe_int(expected.get("image")) > 0
        and shortage_count >= threshold
    )
    return {
        "strategy": strategy,
        "allowAiImages": bool(research.get("allowAiImages", False)),
        "licensedImageProvider": str(
            research.get("licensedImageProvider")
            or research.get("licensedAssetPool")
            or ""
        ).strip(),
        "syntheticAssetProvider": str(
            research.get("syntheticAssetProvider")
            or research.get("imageGenerationProvider")
            or ""
        ).strip(),
        "requiresPublishableImages": image_strategy_requires_publishable_images(spec),
        "releaseAllowed": image_strategy_release_allowed(spec),
        "expectedImageWorks": _safe_int(expected.get("image")),
        "openLicenseShortageCount": shortage_count,
        "structuralOpenLicenseShortage": structural_shortage,
        "structuralShortageThreshold": threshold,
    }


def _release_exists(release_id: str | None) -> bool:
    if not release_id:
        return False
    return (release_root(release_id) / "release_manifest.json").is_file()


def _release_text_only_article_refs(release_id: str | None, runtime_root: Path) -> list[str]:
    if not release_id:
        return []
    root = release_root(release_id)
    posts_root = root / "posts"
    if not posts_root.is_dir():
        return []
    refs: list[str] = []
    for manifest_path in sorted(posts_root.rglob("manifest.json")):
        manifest = _load_json_if_exists(manifest_path)
        carrier = str(manifest.get("contentType") or manifest.get("carrier") or "")
        if carrier in {"image", "gallery", "video"}:
            continue
        rel = manifest_path.parent.relative_to(root)
        publish_media_mode = str(manifest.get("publishMediaMode") or "").strip()
        if not publish_media_mode and runtime_root.is_dir():
            pack = _load_json_if_exists(runtime_root / rel / "3.compose" / "writing_pack.json")
            publish_media_mode = str(pack.get("publishMediaMode") or "").strip()
        if publish_media_mode != "text_only":
            continue
        refs.append(
            str(manifest.get("topicId") or manifest.get("ref") or rel.as_posix()).strip()
            or rel.as_posix()
        )
    return refs[:50]


def _import_evidence_paths(root: Path) -> list[str]:
    candidates = []
    for path in [
        root / "_shared" / "import_report.json",
        root / "_shared" / "staging_import_report.json",
        root / "_shared" / "gamma_import_report.json",
    ]:
        if path.is_file():
            candidates.append(str(path))
    return candidates


def _ship_evidence_paths(root: Path) -> list[str]:
    path = root / "_shared" / "ship_report.json"
    return [str(path)] if path.is_file() else []


def _review_failed_refs_from_text(text: str) -> set[str]:
    refs: set[str] = set()
    body = str(text or "").strip()
    if not body:
        return refs
    if "release missing planned post ref" in body and ":" in body:
        tail = body.split(":", 1)[1]
        for token in re.split(r"[,，\s]+", tail):
            ref = token.strip(" \t\r\n,，;；.。")
            if "__" in ref:
                refs.add(ref)
    match = re.match(r"^([^:：\s,，]+__[^:：\s,，]+)[:：]\s*review_gate failed", body)
    if match:
        refs.add(match.group(1).strip())
    return refs


def _produce_review_repair_failed_refs(root: Path) -> set[str]:
    report = _load_json_if_exists(root / "task_workflow" / "results" / "repair_report" / "produce_review.json")
    payload = report.get("payload") if isinstance(report.get("payload"), Mapping) else report
    if not isinstance(payload, Mapping):
        return set()
    refs: set[str] = set()
    failed_refs = payload.get("failedRefs")
    if isinstance(failed_refs, list):
        refs.update(str(ref).strip() for ref in failed_refs if str(ref).strip())
    issue_map = payload.get("issueMap")
    if isinstance(issue_map, Mapping):
        refs.update(str(ref).strip() for ref in issue_map.keys() if str(ref).strip())
    issues = payload.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            refs.update(_review_failed_refs_from_text(str(issue or "")))
    return {ref for ref in refs if "__" in ref}


def _state_retry_history_failed_refs(state: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()
    history = state.get("produceReviewRetryHistory")
    if not isinstance(history, list):
        return refs
    for row in history:
        if not isinstance(row, Mapping):
            continue
        failed_refs = row.get("failedRefs")
        if isinstance(failed_refs, list):
            refs.update(str(ref).strip() for ref in failed_refs if str(ref).strip())
        issue_map = row.get("issueMap")
        if isinstance(issue_map, Mapping):
            refs.update(str(ref).strip() for ref in issue_map.keys() if str(ref).strip())
    return {ref for ref in refs if "__" in ref}


def _first_pass_evidence(root: Path, state: Mapping[str, Any], reviewed_default: int) -> dict[str, Any]:
    quality = state.get("quality") if isinstance(state.get("quality"), Mapping) else {}
    reviewed_refs = _safe_int(quality.get("reviewedRefs") if isinstance(quality, Mapping) else None)
    if reviewed_refs <= 0:
        reviewed_refs = max(0, reviewed_default)
    homepage_reviewed_refs = _safe_int(
        quality.get("homepageReviewedRefs") if isinstance(quality, Mapping) else None
    )
    homepage_repaired_refs = _safe_int(
        quality.get("homepageRepairedRefs") if isinstance(quality, Mapping) else None
    )

    history_refs = _state_retry_history_failed_refs(state)
    repair_refs = _produce_review_repair_failed_refs(root)
    failed_refs = history_refs or repair_refs
    if failed_refs and reviewed_refs > 0:
        content_reviewed_refs = max(0, reviewed_refs - homepage_reviewed_refs)
        repaired = min(len(failed_refs), content_reviewed_refs) + homepage_repaired_refs
        repaired = min(repaired, reviewed_refs)
        return {
            "firstPassRate": round((reviewed_refs - repaired) / reviewed_refs, 4),
            "reviewedRefs": reviewed_refs,
            "repairedRefs": repaired,
            "homepageReviewedRefs": homepage_reviewed_refs,
            "homepageRepairedRefs": homepage_repaired_refs,
            "source": (
                "produceReviewRetryHistory_plus_homepage_history"
                if history_refs and homepage_reviewed_refs
                else "produce_review_repair_report_plus_homepage_history"
                if homepage_reviewed_refs
                else "produceReviewRetryHistory"
                if history_refs
                else "produce_review_repair_report"
            ),
            "failedRefs": sorted(failed_refs)[:50],
        }

    rate = None
    if isinstance(quality, Mapping) and "firstPassRate" in quality:
        try:
            rate = float(quality.get("firstPassRate"))
        except (TypeError, ValueError):
            rate = None
    return {
        "firstPassRate": rate,
        "reviewedRefs": reviewed_refs,
        "repairedRefs": _safe_int(quality.get("repairedRefs") if isinstance(quality, Mapping) else None),
        "homepageReviewedRefs": homepage_reviewed_refs,
        "homepageRepairedRefs": homepage_repaired_refs,
        "source": "workflow_state_quality" if rate is not None else "missing",
        "failedRefs": [],
    }


def _infer_release_id(
    provided: str | None,
    *,
    state: Mapping[str, Any],
    root: Path,
) -> str:
    for candidate in (
        provided,
        state.get("releaseId") if isinstance(state, Mapping) else None,
        state.get("lastReleaseId") if isinstance(state, Mapping) else None,
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    ship = _load_json_if_exists(root / "_shared" / "ship_report.json")
    for key in ("dataReleaseId", "sourceReleaseId", "releaseId"):
        text = str(ship.get(key) or "").strip()
        if text:
            return text
    return ""


def _content_quality_coverage(root: Path) -> dict[str, Any]:
    """扫 materialized post：作品判定（WorksClassifier）与 semanticMentions 覆盖。

    规模化质量证据：① 随记/弃稿不得进入发布（works_verdict.decision != work）；
    ② 文章作品应回填 semanticMentions（实体/标签 grounding，端云可点击的源头）。
    与 produce/works_gate.py + materialize semanticMentions 回填闭环对齐。
    """
    from _common.paths import STAGE_COMPOSE

    posts_root = root / "posts"
    post_manifests = sorted(posts_root.rglob("manifest.json")) if posts_root.is_dir() else []
    article_posts = 0
    article_mention_covered = 0
    total_mentions = 0
    works_verdict_present = 0
    non_work_materialized: list[str] = []
    for manifest_path in post_manifests:
        manifest = _load_json_if_exists(manifest_path)
        if not manifest:
            continue
        carrier = str(manifest.get("contentType") or manifest.get("carrier") or "")
        is_image = carrier in {"image", "gallery"}
        is_video = carrier == "video"
        mentions = manifest.get("semanticMentions")
        mention_count = len(mentions) if isinstance(mentions, list) else 0
        total_mentions += mention_count
        if not is_image and not is_video:
            article_posts += 1
            if mention_count > 0:
                article_mention_covered += 1
        verdict = _load_json_if_exists(manifest_path.parent / STAGE_COMPOSE / "works_verdict.json")
        if verdict:
            works_verdict_present += 1
            if str(verdict.get("decision") or "") != "work":
                non_work_materialized.append(manifest_path.parent.relative_to(root).as_posix())
    return {
        "articlePosts": article_posts,
        "articleMentionCoveredPosts": article_mention_covered,
        "articleMentionCoverage": round(article_mention_covered / article_posts, 4) if article_posts else 1.0,
        "totalSemanticMentions": total_mentions,
        "worksVerdictPresent": works_verdict_present,
        "nonWorkMaterialized": non_work_materialized[:20],
        "nonWorkMaterializedCount": len(non_work_materialized),
    }


_SOURCE_REFS_V2 = "quwoquan_data.source_refs/2"
_SOURCE_REFS_MAX_BYTES = 10_240


def _single_base_constitution_issues(root: Path) -> list[str]:
    """单底稿零参考 + 单 source unit 宪法抽检（放量 trial/commercial 硬门）。

    图文混排已放开：实体主页 page.md 允许内联 asset:// figure，引用闭环由
    homepage_validation._asset_closure_issues 校验；此处只守单底稿/单 unit 宪法。
    """
    issues: list[str] = []
    posts_root = root / "posts"
    if posts_root.is_dir():
        for path in sorted(posts_root.rglob("source_refs.json")):
            try:
                payload = read_json(path)
            except (OSError, ValueError, TypeError):
                issues.append(f"{path.relative_to(root)}: source_refs unreadable")
                continue
            if str(payload.get("schemaVersion") or "") != _SOURCE_REFS_V2:
                issues.append(f"{path.relative_to(root)}: source_refs schema must be {_SOURCE_REFS_V2}")
            if path.stat().st_size > _SOURCE_REFS_MAX_BYTES:
                issues.append(f"{path.relative_to(root)}: source_refs exceeds {_SOURCE_REFS_MAX_BYTES} bytes")
            for forbidden in ("citedSourceRefs", "referenceSourceRefs", "sourcePaths"):
                if forbidden in payload:
                    issues.append(f"{path.relative_to(root)}: forbidden field {forbidden}")
            sources = payload.get("sources") or []
            if not isinstance(sources, list) or len(sources) != 1:
                issues.append(f"{path.relative_to(root)}: sources must be length 1")
            elif sources and str((sources[0] or {}).get("role") or "") != "base":
                issues.append(f"{path.relative_to(root)}: sole source role must be base")
    entities_root = root / "entities"
    if entities_root.is_dir():
        # 图文混排：实体主页 page.md 允许内联 asset:// figure（封面/章节配图），
        # 闭环校验交由 homepage_validation._asset_closure_issues；此处只守单底稿单 unit 宪法。
        for manifest_path in sorted(entities_root.rglob("manifest.json")):
            manifest = _load_json_if_exists(manifest_path)
            if not manifest:
                continue
            text_refs = manifest.get("textSourceRefs") or []
            image_refs = manifest.get("imageSourceRefs") or []
            if isinstance(text_refs, list) and len({str(r) for r in text_refs if str(r).strip()}) > 1:
                issues.append(f"{manifest_path.relative_to(root)}: textSourceRefs must be single unit")
            if isinstance(image_refs, list) and len({str(r) for r in image_refs if str(r).strip()}) > 1:
                issues.append(f"{manifest_path.relative_to(root)}: imageSourceRefs must be single unit")
    return issues


def build_scale_readiness_report(
    task_id: str,
    batch_id: str,
    *,
    daily_target: int = DEFAULT_DAILY_TARGET,
    target_goal: int | None = None,
    min_pass_rate: float = 0.0,
    source_ready_goal: int | None = None,
    release_id: str | None = None,
    require_import: bool = True,
    mode: str = "commercial",
    accept_estimated_token_ledger: bool = False,
    accept_text_only_articles: bool = False,
) -> dict[str, Any]:
    from task import store
    from task.target_selection import audit_managed_batch

    spec = store.load_spec(task_id)
    root = batch_root(task_id, batch_id)
    audit = audit_managed_batch(task_id, batch_id)
    active_spec = _active_scale_spec(task_id, batch_id, spec)
    commercial_closure = article_commercial_closure_enabled(active_spec)
    commercial_target_object_goal = (
        _commercial_target_object_count(active_spec)
        if commercial_closure
        else 0
    )
    state = _load_json_if_exists(root / "_shared" / "task_workflow_state.json")
    env_report = _load_json_if_exists(root / "_shared" / "env_ready_report.json")
    release_id = _infer_release_id(release_id, state=state, root=root)
    mode = "trial" if str(mode or "").strip() == "trial" else "commercial"
    strict_commercial_article_gate = commercial_closure and mode == "commercial"
    expected = _expected_objects(active_spec, audit)
    targets = _target_count(active_spec, audit)
    target_goal_value = int(target_goal or 0)
    if target_goal_value < 0:
        target_goal_value = 0
    min_pass_rate_value = float(min_pass_rate or 0.0)
    if min_pass_rate_value < 0:
        min_pass_rate_value = 0.0
    if min_pass_rate_value > 1:
        min_pass_rate_value = min_pass_rate_value / 100.0
    targeted_object_goal = (
        target_goal_value
        or commercial_target_object_goal
        or expected["total"]
    )
    scope = spec.get("scope") or {}
    base_targets = scope.get("coverageTargets") if isinstance(scope.get("coverageTargets"), list) else []
    base_target_count = len(base_targets)
    lanes = _lane_rates(audit, targets)
    abandoned_count = _safe_int(audit.get("abandonedCount"))
    abandoned_content_count = _safe_int(audit.get("abandonedContentCount"))
    abandoned_content_by_type = _abandoned_content_by_type(task_id, batch_id, audit)
    replacement_count = _safe_int(audit.get("replacementCount"))
    acceptance = spec.get("acceptance") if isinstance(spec.get("acceptance"), Mapping) else {}
    required_active_targets = max(base_target_count, _safe_int((acceptance or {}).get("minEntities")))
    replacement_closed = targets >= required_active_targets
    runtime_integrity = scan_runtime_batch_integrity(task_id, batch_id)
    runtime_stats = runtime_integrity.get("stats") if isinstance(runtime_integrity, Mapping) else {}
    release_integrity = (
        scan_release_integrity(release_id)
        if release_id and _release_exists(release_id)
        else {}
    )
    planned_counts = _content_plan_item_count(root)
    authored_counts = _authored_object_count(root)
    homepage_passed = _homepage_passed_count(root)
    release_text_only_articles = (
        _release_text_only_article_refs(release_id, root)
        if commercial_closure
        else []
    )
    source_admission = _source_admission_report(task_id, batch_id, active_spec, root)
    quality_target = _quality_target_report(root)
    quality_coverage = _content_quality_coverage(root)
    creator_load = _creator_load_report(root, spec, target_goal=target_goal_value)
    token_ledgers = _token_ledger_paths(root)
    shared_token_ledger_path = root / "_shared" / "token_ledger.json"
    shared_token_ledger = _load_json_if_exists(shared_token_ledger_path)
    shared_token_measurement_mode = str(shared_token_ledger.get("measurementMode") or "")
    import_paths = _import_evidence_paths(root)
    ship_paths = _ship_evidence_paths(root)
    download_report = download_diagnostics(root)
    reason_summary = _abandonment_reason_summary(audit)
    image_strategy = _image_strategy_readiness(spec, audit, expected, reason_summary)
    content = spec.get("content") or {}
    research = content.get("research") or {}
    queue_backend = (
        (spec.get("queuePolicy") or {}).get("backend")
        or (content.get("queuePolicy") or {}).get("backend")
        or content.get("queueBackend")
        or spec.get("queueBackend")
    )
    max_concurrency = _safe_int(research.get("maxConcurrency") or spec.get("maxConcurrency"))
    allow_partial = _partial_content_allowed(spec)

    blockers: list[str] = []
    warnings: list[str] = []

    if not bool(env_report.get("ready")):
        blockers.append("env ready evidence missing or failed")
    cursor_startup = env_report.get("cursorStartup") if isinstance(env_report.get("cursorStartup"), Mapping) else {}
    if not cursor_startup:
        preflight = env_report.get("preflight") if isinstance(env_report.get("preflight"), Mapping) else {}
        nested = preflight.get("cursorStartup") if isinstance(preflight.get("cursorStartup"), Mapping) else {}
        if nested:
            cursor_startup = nested
    if target_goal_value and not cursor_startup:
        blockers.append("Cursor SDK startup probe missing;百级不得进入 author-runner")
    elif target_goal_value and not bool(cursor_startup.get("checked")):
        blockers.append("Cursor SDK startup probe not checked in batch env_ready_report;百级不得进入 author-runner")
    elif target_goal_value and not bool(cursor_startup.get("ready")):
        blockers.append("Cursor SDK startup probe failed in batch env_ready_report;百级不得进入 author-runner")
    status = str(state.get("status") or "")
    reasoned_reject_trial_complete = (
        mode == "trial"
        and allow_partial
        and target_goal_value > 0
        and status == "completed_with_reasoned_rejects"
    )
    if status != "succeeded" and not reasoned_reject_trial_complete:
        blockers.append(f"workflow status must be succeeded for scale; got {status or 'missing'}")
    elif reasoned_reject_trial_complete:
        warnings.append(
            "workflow completed_with_reasoned_rejects accepted for trial; "
            "all abandoned refs must stay excluded from release/import and quality target must be met"
        )
    waiting = str(state.get("waitingCheckpoint") or "")
    if waiting:
        blockers.append(f"workflow still waits at checkpoint: {waiting}")
    failed_count = _safe_int(audit.get("failedLaneCount"))
    if failed_count and (strict_commercial_article_gate or not allow_partial):
        blockers.append(f"managed batch audit has failedLaneCount={failed_count}")
    elif failed_count:
        warnings.append(
            f"partial delivery accepted failedLaneCount={failed_count}; "
            "failed lanes must stay excluded from release/import"
        )
    if abandoned_count and not replacement_closed and not allow_partial:
        blockers.append(
            f"abandoned entities require replacement closure; abandoned={abandoned_count} "
            f"replacement={replacement_count} activeTargets={targets} "
            f"requiredActiveTargets={required_active_targets}"
        )
    elif abandoned_count:
        warnings.append(
            f"abandoned entities excluded from published entity/tag refs; abandoned={abandoned_count} "
            f"replacement={replacement_count} activeTargets={targets} closed={replacement_closed}"
        )
    abandoned_content_ratio = (
        abandoned_content_count / targeted_object_goal
        if targeted_object_goal
        else 0.0
    )
    if abandoned_content_count and mode == "commercial" and (strict_commercial_article_gate or not allow_partial):
        blockers.append(f"scale readiness requires zero abandoned content objects; got {abandoned_content_count}")
    elif abandoned_content_count:
        if abandoned_content_ratio > MAX_TRIAL_ABANDONED_CONTENT_RATIO and not allow_partial:
            blockers.append(
                f"trial abandoned content ratio {abandoned_content_ratio:.2%} "
                f"> {MAX_TRIAL_ABANDONED_CONTENT_RATIO:.0%}"
            )
        else:
            warnings.append(
                f"trial partial delivery accepted abandonedContent={abandoned_content_count} "
                f"ratio={abandoned_content_ratio:.2%}; abandoned refs must remain excluded from release/import"
            )
    if expected["image"] and not image_strategy["releaseAllowed"] and not allow_partial:
        blockers.append(
            "imageAssetStrategy=reference_only_no_image_release cannot satisfy "
            f"expected publishable image works ({expected['image']})"
        )
    elif expected["image"] and not image_strategy["releaseAllowed"]:
        warnings.append(
            "image lane will partially deliver zero publishable image works under "
            "imageAssetStrategy=reference_only_no_image_release"
        )
    if image_strategy["structuralOpenLicenseShortage"] and not allow_partial:
        blockers.append(
            "imageAssetStrategy=open_license_publish is structurally under-supplied for this batch: "
            f"{image_strategy['openLicenseShortageCount']} open-license image shortages across "
            f"{abandoned_count} abandoned entities; configure licensed_provider_publish with "
            "licensedImageProvider/licensedAssetPool or ai_generated_original with syntheticAssetProvider "
            "before expanding scale"
        )
    elif image_strategy["structuralOpenLicenseShortage"]:
        warnings.append(
            "imageAssetStrategy=open_license_publish is under-supplied for some image works; "
            "publish only rights-cleared image assets and report the shortfall"
        )
    for lane, row in lanes.items():
        rate = float(row["rate"])
        if targets and rate < MIN_SOURCE_SUFFICIENCY and not allow_partial:
            blockers.append(f"{lane} lane source sufficiency {rate:.2%} < {MIN_SOURCE_SUFFICIENCY:.0%}")
        elif targets and rate < MIN_SOURCE_SUFFICIENCY:
            warnings.append(
                f"{lane} lane source sufficiency {rate:.2%} < {MIN_SOURCE_SUFFICIENCY:.0%}; "
                "treat as delivery success-rate evidence, not a release blocker"
            )
    actual_articles = _safe_int((runtime_stats or {}).get("articleCount"))
    actual_images = _safe_int((runtime_stats or {}).get("imageCount"))
    actual_videos = _safe_int((runtime_stats or {}).get("videoCount"))
    actual_posts = _safe_int((runtime_stats or {}).get("postCount"))
    published_total = actual_posts + homepage_passed
    target_passed = _safe_int(
        quality_target.get("qualityPassedObjectCount"),
        actual_posts if commercial_closure else published_total,
    )
    target_rate = round(target_passed / target_goal_value, 4) if target_goal_value else 0.0
    if target_goal_value and target_rate < min_pass_rate_value:
        blockers.append(
            f"quality target satisfaction {target_rate:.2%} < {min_pass_rate_value:.0%} "
            f"({target_passed}/{target_goal_value})"
        )
    computed_source_ready_goal = source_ready_goal
    if computed_source_ready_goal is None:
        if target_goal_value:
            computed_source_ready_goal = int(round(target_goal_value * DEFAULT_SCALE_SOURCE_READY_MULTIPLIER))
        elif commercial_closure and commercial_target_object_goal:
            computed_source_ready_goal = int(
                round(commercial_target_object_goal * DEFAULT_SCALE_SOURCE_READY_MULTIPLIER)
            )
    if computed_source_ready_goal and _safe_int(source_admission.get("sourceReadyObjectCapacity")) < int(computed_source_ready_goal):
        blockers.append(
            "source-ready object capacity "
            f"{source_admission.get('sourceReadyObjectCapacity')} < required {int(computed_source_ready_goal)}"
        )
    article_shortfall_closed = (
        mode == "trial"
        and actual_articles + _safe_int(abandoned_content_by_type.get("article")) >= expected["article"]
    )
    image_shortfall_closed = (
        mode == "trial"
        and actual_images + _safe_int(abandoned_content_by_type.get("image")) >= expected["image"]
    )
    if commercial_closure:
        if _quotas(active_spec)["article"] > 0 and actual_articles <= 0:
            blockers.append("article commercial closure requires materialized article posts")
        if expected["article"] and actual_articles < expected["article"]:
            warnings.append(
                f"shared article pool below desired mix: actual={actual_articles} "
                f"expectedMix={expected['article']}"
            )
        if expected["image"] and actual_images < expected["image"]:
            warnings.append(
                f"shared image pool below desired mix: actual={actual_images} "
                f"expectedMix={expected['image']}"
            )
    else:
        if expected["article"] and actual_articles < expected["article"] and not article_shortfall_closed and not allow_partial:
            blockers.append(f"materialized article count {actual_articles} < expected {expected['article']}")
        elif expected["article"] and actual_articles < expected["article"]:
            warnings.append(
                f"partial article delivery accepted: "
                f"actual={actual_articles} abandoned={_safe_int(abandoned_content_by_type.get('article'))} "
                f"expected={expected['article']}"
            )
        if expected["image"] and actual_images < expected["image"] and not image_shortfall_closed and not allow_partial:
            blockers.append(f"materialized image count {actual_images} < expected {expected['image']}")
        elif expected["image"] and actual_images < expected["image"]:
            warnings.append(
                f"partial image delivery accepted: "
                f"actual={actual_images} abandoned={_safe_int(abandoned_content_by_type.get('image'))} "
                f"expected={expected['image']}"
            )
    if targeted_object_goal and (actual_posts if commercial_closure else published_total) <= 0:
        blockers.append("materialized publishable object count is zero")
    runtime_integrity_issues = list(runtime_integrity.get("issues") or []) if isinstance(runtime_integrity, Mapping) else []
    if commercial_closure and (runtime_integrity_issues or not bool(runtime_integrity.get("passed"))):
        runtime_integrity_summary = "; ".join(str(issue) for issue in runtime_integrity_issues[:8]) or "unknown issue"
        blockers.append(
            "runtime batch integrity failed: "
            + runtime_integrity_summary
            + (" ..." if len(runtime_integrity_issues) > 8 else "")
        )
    release_integrity_issues = list(release_integrity.get("issues") or []) if isinstance(release_integrity, Mapping) else []
    if commercial_closure and release_integrity and (release_integrity_issues or not bool(release_integrity.get("passed"))):
        release_integrity_summary = "; ".join(str(issue) for issue in release_integrity_issues[:8]) or "unknown issue"
        blockers.append(
            "release integrity failed: "
            + release_integrity_summary
            + (" ..." if len(release_integrity_issues) > 8 else "")
        )
    if commercial_closure and release_text_only_articles:
        text_only_message = (
            "release contains text_only article(s): "
            + ", ".join(release_text_only_articles[:8])
            + (" ..." if len(release_text_only_articles) > 8 else "")
        )
        if accept_text_only_articles:
            # 显式接受口径（acceptance GWT3 / R-CS10 收口裁定）：text_only 文章准出，
            # 图文同源列为后续升级；必须由调用方显式传参，禁止静默放宽。
            warnings.append(
                "text_only articles explicitly accepted via --accept-text-only-articles: "
                + text_only_message
            )
        else:
            blockers.append("commercial mixed-layout gate failed: " + text_only_message)
    # 作品判定纯净性：随记/弃稿不得进入发布（不受 partial 放行影响）。
    if quality_coverage["nonWorkMaterializedCount"]:
        blockers.append(
            "works classifier purity violated: "
            f"{quality_coverage['nonWorkMaterializedCount']} materialized objects are not 'work' "
            f"(samples={quality_coverage['nonWorkMaterialized']}); 随记/弃稿禁止进入发布"
        )
    constitution_issues = _single_base_constitution_issues(root)
    if constitution_issues:
        blockers.append(
            "single-base zero-reference constitution violated: "
            + "; ".join(constitution_issues[:8])
            + (" ..." if len(constitution_issues) > 8 else "")
        )
    # semanticMentions 回填覆盖：文章作品应有实体/标签 grounding（端云可点击源头）。
    if quality_coverage["articlePosts"] and quality_coverage["articleMentionCoverage"] < 0.5:
        warnings.append(
            f"semanticMentions coverage {quality_coverage['articleMentionCoverage']:.2%} "
            f"over {quality_coverage['articlePosts']} article posts is low; "
            "实体/标签 mention 回填不足将削弱端侧可点击与推荐 grounding"
        )
    if daily_target >= 10_000 and queue_backend != "reliabletask":
        blockers.append("daily target >=10000 requires queueBackend=reliabletask")
    if daily_target >= 10_000 and max_concurrency < 10:
        blockers.append("daily target >=10000 requires measured maxConcurrency >=10 for trial admission")
    if not shared_token_ledger:
        blockers.append("authoritative TokenLedger missing at _shared/token_ledger.json")
    elif not shared_token_measurement_mode:
        blockers.append("TokenLedger measurementMode missing; cannot prove authoritative accounting")
    elif shared_token_measurement_mode == "estimated_from_artifacts":
        if accept_estimated_token_ledger:
            # 显式接受口径（acceptance GWT2 / 2026-07-06 用户裁定）：本地 cursor_sdk bridge
            # 不回传 usage，H100 允许 estimated 账本准出；authoritative 为后续升级项。
            warnings.append(
                "TokenLedger measurementMode=estimated_from_artifacts explicitly accepted "
                "via --accept-estimated-token-ledger; authoritative usage ledger remains a "
                "follow-up upgrade (backlog R-CS03)"
            )
        else:
            blockers.append("TokenLedger measurementMode must not be estimated_from_artifacts")
    elif not token_ledgers:
        blockers.append("TokenLedger evidence missing; cannot project unit token/cost or cache hit rate")
    if not release_id or not _release_exists(release_id):
        blockers.append("isolated release evidence missing; release verify cannot be proven")
    if not ship_paths:
        warnings.append("ship evidence missing; release/import closure should be captured by ship_report.json")
    if require_import and not import_paths:
        blockers.append("staging/gamma import evidence missing")
    required_throughput_per_hour = int(daily_target) / 24
    measured_throughput = state.get("throughput") if isinstance(state.get("throughput"), Mapping) else None
    resolved_agent_active = _resolve_agent_active(measured_throughput, state)
    throughput_projection = _throughput_projection(
        resolved_agent_active,
        queue_backend=str(queue_backend or ""),
        max_concurrency=max_concurrency,
        required_per_hour=required_throughput_per_hour,
    )
    measured_objects_per_hour = 0.0
    if not measured_throughput:
        blockers.append("measured throughput evidence missing; cannot project daily capacity")
    else:
        try:
            measured_objects_per_hour = float(measured_throughput.get("objectsPerHour") or 0)
        except (TypeError, ValueError):
            measured_objects_per_hour = 0.0
        effective_per_hour = max(measured_objects_per_hour, throughput_projection["projectedObjectsPerHour"])
        if effective_per_hour < required_throughput_per_hour:
            if throughput_projection["available"]:
                blockers.append(
                    f"projected daily capacity {throughput_projection['projectedObjectsPerHour']:.4f} objects/hour "
                    f"(perWorker {throughput_projection['perWorkerObjectsPerHour']:.4f} x committedConcurrency "
                    f"{throughput_projection['committedConcurrency']}) "
                    f"< required {required_throughput_per_hour:.4f} objects/hour"
                )
            else:
                blockers.append(
                    f"measured throughput {measured_objects_per_hour:.4f} objects/hour "
                    f"< required {required_throughput_per_hour:.4f} objects/hour"
                )
        elif throughput_projection["available"] and measured_objects_per_hour < required_throughput_per_hour:
            warnings.append(
                "daily capacity met by per-worker projection "
                f"({throughput_projection['projectedObjectsPerHour']:.2f} obj/h = "
                f"{throughput_projection['perWorkerObjectsPerHour']:.2f} x "
                f"{throughput_projection['committedConcurrency']} committed workers), "
                f"not by trial wall-clock throughput ({measured_objects_per_hour:.2f} obj/h); "
                "linear scaling across the committed reliabletask fleet is an explicit unproven assumption"
            )
    if targeted_object_goal <= 0:
        blockers.append("expected content object count is zero")
    if creator_load["required"] and creator_load["assignmentIssueCount"]:
        blockers.append(
            "creator assignment gate failed: "
            f"{creator_load['assignmentIssueCount']} issue(s); "
            f"samples={creator_load['assignmentIssues'][:5]}"
        )
    if target_goal_value >= 100 and creator_load["overloadedCreatorProfileIds"]:
        creator_overload_message = (
            "creator load exceeds publishCadence.maxDailyPosts=1 for scale: "
            + ", ".join(creator_load["overloadedCreatorProfileIds"][:10])
        )
        if mode == "trial":
            warnings.append(
                "trial " + creator_overload_message
                + "; commercial promotion must expand creator assignment or spread publish cadence first"
            )
        else:
            blockers.append(creator_overload_message)
    if targeted_object_goal and daily_target / max(targeted_object_goal, 1) > 1000:
        warnings.append("trial sample is too small to extrapolate linearly to requested daily target")

    # When workflow is successful, first-pass rate must still preserve repaired
    # review refs.  Older runs may have cleared workflow quality back to 1.0
    # after repair; the repair report/history keeps the honest first-pass signal.
    first_pass = _first_pass_evidence(root, state, actual_posts)
    first_pass_rate = first_pass["firstPassRate"]
    first_pass_threshold = max(
        MIN_FIRST_PASS_RATE,
        float(min_pass_rate_value) if target_goal_value else MIN_FIRST_PASS_RATE,
    )
    if first_pass_rate is not None and first_pass_rate < first_pass_threshold:
        trial_target_met = (
            mode == "trial"
            and target_goal_value
            and target_rate >= min_pass_rate_value
        )
        if trial_target_met:
            warnings.append(
                f"trial firstPassRate {first_pass_rate:.2%} < {first_pass_threshold:.0%}; "
                "quality target already satisfied with honest partial delivery"
            )
        else:
            blockers.append(f"firstPassRate {first_pass_rate:.2%} < {first_pass_threshold:.0%}")
    elif first_pass_rate is None:
        blockers.append("firstPassRate evidence missing")

    return {
        "schemaVersion": SCHEMA,
        "taskId": task_id,
        "batchId": batch_id,
        "mode": mode,
        "dailyTarget": int(daily_target),
        "passed": not blockers,
        "decision": "go" if not blockers else "no_go",
        "expectedObjects": expected,
        "qualityTarget": {
            "targetGoal": target_goal_value,
            "minPassRate": min_pass_rate_value,
            "qualityPassedObjectCount": target_passed,
            "targetSatisfactionRate": target_rate,
            "sourceReadyGoal": int(computed_source_ready_goal or 0),
            "sourceReadyMultiplier": DEFAULT_SCALE_SOURCE_READY_MULTIPLIER,
        },
        "funnel": {
            "targeted": targeted_object_goal,
            "sourceReady": _safe_int(source_admission.get("sourceReadyObjectCapacity")),
            "homepagePassed": homepage_passed,
            "contentPlanned": planned_counts["total"],
            "authored": authored_counts["total"],
            "reviewPassed": actual_posts,
            "published": published_total,
            "byObjectType": {
                "article": {
                    "planned": planned_counts["article"],
                    "authored": authored_counts["article"],
                    "published": actual_articles,
                },
                "image": {
                    "planned": planned_counts["image"],
                    "published": actual_images,
                },
                "video": {
                    "planned": planned_counts["video"],
                    "published": actual_videos,
                },
                "homepage": {
                    "published": homepage_passed,
                },
            },
        },
        "sourceAdmission": source_admission,
        "abandonment": {
            "entityCount": abandoned_count,
            "contentObjectCount": abandoned_content_count,
        },
        "partialDelivery": {
            "mode": mode,
            "allowPartialContent": allow_partial,
            "abandonedContentByType": abandoned_content_by_type,
            "abandonedContentRatio": round(abandoned_content_ratio, 4),
            "maxTrialAbandonedContentRatio": MAX_TRIAL_ABANDONED_CONTENT_RATIO,
            "delivered": {
                "objects": published_total,
                "posts": actual_posts,
                "homepages": homepage_passed,
                "articles": actual_articles,
                "images": actual_images,
                "videos": actual_videos,
            },
            "fulfillment": {
                "article": round(actual_articles / expected["article"], 4) if expected["article"] else 1.0,
                "image": round(actual_images / expected["image"], 4) if expected["image"] else 1.0,
            },
        },
        "replacementClosure": {
            "baseTargetCount": base_target_count,
            "requiredActiveTargets": required_active_targets,
            "activeTargetCount": targets,
            "replacementCount": replacement_count,
            "closed": bool(replacement_closed),
            "objects": audit.get("replacementObjects") or [],
        },
        "runtimeIntegrity": {
            "passed": bool(runtime_integrity.get("passed")),
            "stats": runtime_stats or {},
            "issues": runtime_integrity_issues[:20],
        },
        "releaseIntegrity": {
            "passed": bool(release_integrity.get("passed")) if release_integrity else False,
            "stats": (release_integrity.get("stats") or {}) if isinstance(release_integrity, Mapping) else {},
            "issues": release_integrity_issues[:20],
            "textOnlyArticles": release_text_only_articles,
            "textOnlyArticlesAccepted": bool(accept_text_only_articles),
        },
        "contentQualityCoverage": quality_coverage,
        "creatorLoad": creator_load,
        "sourceSufficiency": lanes,
        "workflowState": {
            key: state.get(key)
            for key in ("status", "waitingCheckpoint", "nextAction", "retryCounts", "infrastructureRetryCounts", "failedObjects")
        },
        "executionReadiness": {
            "queueBackend": queue_backend or "",
            "maxConcurrency": max_concurrency,
            "tokenLedgerCount": len(token_ledgers),
            "tokenLedgerPaths": token_ledgers[:20],
            "authoritativeTokenLedgerPath": str(shared_token_ledger_path) if shared_token_ledger else "",
            "authoritativeTokenLedgerMeasurementMode": shared_token_measurement_mode,
            "authoritativeTokenLedgerReady": bool(
                shared_token_ledger
                and shared_token_measurement_mode
                and shared_token_measurement_mode != "estimated_from_artifacts"
            ),
            "estimatedTokenLedgerAccepted": bool(
                accept_estimated_token_ledger
                and shared_token_measurement_mode == "estimated_from_artifacts"
            ),
            "releaseId": release_id or "",
            "releaseManifestExists": _release_exists(release_id),
            "shipEvidencePaths": ship_paths,
            "importEvidencePaths": import_paths,
            "requiredThroughputPerHour": round(required_throughput_per_hour, 4),
            "requiredThroughputPerMinute": round(int(daily_target) / 1440, 4),
            "measuredThroughput": measured_throughput,
            "throughputProjection": throughput_projection,
            "firstPassRate": first_pass_rate,
            "firstPassThreshold": first_pass_threshold,
            "firstPassEvidence": first_pass,
        },
        "envReady": {
            "ready": bool(env_report.get("ready")),
            "reportPath": str(root / "_shared" / "env_ready_report.json") if env_report else "",
            "cursorStartup": dict(cursor_startup or {}),
            "issues": (
                ((env_report.get("preflight") or {}).get("issues") or env_report.get("issues") or [])[:20]
                if isinstance(env_report, Mapping)
                else []
            ),
        },
        "downloadDiagnostics": download_report,
        "abandonmentDiagnostics": reason_summary,
        "imageAssetStrategy": image_strategy,
        "blockers": blockers,
        "warnings": warnings,
    }


def write_scale_readiness_report(path: Path, report: Mapping[str, Any]) -> None:
    write_json(path, dict(report))
