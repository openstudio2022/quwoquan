"""Commercial scale readiness gate for managed content batches.

The gate is intentionally conservative: a batch that cannot prove source
sufficiency, token/cost accounting, queue backend, release, and import evidence
is a No-Go for scale even when some early lane checks passed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.download_diagnostics import download_diagnostics
from _common.image_asset_strategy import (
    OPEN_LICENSE_PUBLISH,
    REFERENCE_ONLY_NO_IMAGE_RELEASE,
    image_asset_strategy,
    image_strategy_release_allowed,
    image_strategy_requires_publishable_images,
)
from _common.io import read_json, write_json
from _common.paths import batch_root, release_root
from _common.release_integrity import scan_runtime_batch_integrity


SCHEMA = "quwoquan_data.scale_readiness"
DEFAULT_DAILY_TARGET = 10_000
MIN_SOURCE_SUFFICIENCY = 0.98
MIN_FIRST_PASS_RATE = 0.70
MAX_TRIAL_ABANDONED_CONTENT_RATIO = 0.05
STRUCTURAL_IMAGE_SHORTAGE_MIN_COUNT = 5
STRUCTURAL_IMAGE_SHORTAGE_RATIO = 0.30


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


def _expected_objects(spec: Mapping[str, Any], audit: Mapping[str, Any]) -> dict[str, int]:
    count = _target_count(spec, audit)
    quotas = _quotas(spec)
    return {
        "homepage": count * quotas["homepage"],
        "article": count * quotas["article"],
        "image": count * quotas["image"],
        "routeArticle": quotas["routeArticle"],
        "total": count * (quotas["homepage"] + quotas["article"] + quotas["image"]) + quotas["routeArticle"],
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
        elif "article sources" in lowered or "article research needs" in lowered:
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
        content_type = str(coords.get("contentType") or "")
        if not content_type:
            content_type = "image" if ref.endswith("_image") else "article"
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


def _token_ledger_paths(root: Path) -> list[str]:
    names = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if "token" in lowered and "ledger" in lowered and path.suffix == ".json":
            names.append(str(path))
    return names


def _release_exists(release_id: str | None) -> bool:
    if not release_id:
        return False
    return (release_root(release_id) / "release_manifest.json").is_file()


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


def build_scale_readiness_report(
    task_id: str,
    batch_id: str,
    *,
    daily_target: int = DEFAULT_DAILY_TARGET,
    release_id: str | None = None,
    require_import: bool = True,
    mode: str = "commercial",
) -> dict[str, Any]:
    from task import store
    from task.target_selection import audit_managed_batch

    spec = store.load_spec(task_id)
    root = batch_root(task_id, batch_id)
    audit = audit_managed_batch(task_id, batch_id)
    state = _load_json_if_exists(root / "_shared" / "task_workflow_state.json")
    env_report = _load_json_if_exists(root / "_shared" / "env_ready_report.json")
    release_id = _infer_release_id(release_id, state=state, root=root)
    mode = "trial" if str(mode or "").strip() == "trial" else "commercial"
    expected = _expected_objects(spec, audit)
    targets = _target_count(spec, audit)
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
    quality_coverage = _content_quality_coverage(root)
    token_ledgers = _token_ledger_paths(root)
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
    status = str(state.get("status") or "")
    if status != "succeeded":
        blockers.append(f"workflow status must be succeeded for scale; got {status or 'missing'}")
    waiting = str(state.get("waitingCheckpoint") or "")
    if waiting:
        blockers.append(f"workflow still waits at checkpoint: {waiting}")
    failed_count = _safe_int(audit.get("failedLaneCount"))
    if failed_count and not allow_partial:
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
        abandoned_content_count / expected["total"]
        if expected["total"]
        else 0.0
    )
    if abandoned_content_count and mode == "commercial" and not allow_partial:
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
    article_shortfall_closed = (
        mode == "trial"
        and actual_articles + _safe_int(abandoned_content_by_type.get("article")) >= expected["article"]
    )
    image_shortfall_closed = (
        mode == "trial"
        and actual_images + _safe_int(abandoned_content_by_type.get("image")) >= expected["image"]
    )
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
    if expected["total"] and actual_posts <= 0:
        blockers.append("materialized publishable post count is zero")
    # 作品判定纯净性：随记/弃稿不得进入发布（不受 partial 放行影响）。
    if quality_coverage["nonWorkMaterializedCount"]:
        blockers.append(
            "works classifier purity violated: "
            f"{quality_coverage['nonWorkMaterializedCount']} materialized objects are not 'work' "
            f"(samples={quality_coverage['nonWorkMaterialized']}); 随记/弃稿禁止进入发布"
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
    if not token_ledgers:
        blockers.append("TokenLedger evidence missing; cannot project unit token/cost or cache hit rate")
    if not release_id or not _release_exists(release_id):
        blockers.append("isolated release evidence missing; release verify cannot be proven")
    if not ship_paths:
        warnings.append("ship evidence missing; release/import closure should be captured by ship_report.json")
    if require_import and not import_paths:
        blockers.append("staging/gamma import evidence missing")
    required_throughput_per_hour = int(daily_target) / 24
    measured_throughput = state.get("throughput") if isinstance(state.get("throughput"), Mapping) else None
    if not measured_throughput:
        blockers.append("measured throughput evidence missing; cannot project daily capacity")
    else:
        try:
            objects_per_hour = float(measured_throughput.get("objectsPerHour") or 0)
        except (TypeError, ValueError):
            objects_per_hour = 0.0
        if objects_per_hour < required_throughput_per_hour:
            blockers.append(
                f"measured throughput {objects_per_hour:.4f} objects/hour "
                f"< required {required_throughput_per_hour:.4f} objects/hour"
            )
    if expected["total"] <= 0:
        blockers.append("expected content object count is zero")
    if expected["total"] and daily_target / max(expected["total"], 1) > 1000:
        warnings.append("trial sample is too small to extrapolate linearly to requested daily target")

    # When workflow is successful, first-pass rate should come from review/import
    # counters.  Without it, keep scale blocked above via throughput/token/release
    # and record the missing value explicitly.
    first_pass_rate = None
    quality = state.get("quality") if isinstance(state.get("quality"), Mapping) else {}
    if isinstance(quality, Mapping) and "firstPassRate" in quality:
        try:
            first_pass_rate = float(quality.get("firstPassRate"))
        except (TypeError, ValueError):
            first_pass_rate = None
    if first_pass_rate is not None and first_pass_rate < MIN_FIRST_PASS_RATE:
        blockers.append(f"firstPassRate {first_pass_rate:.2%} < {MIN_FIRST_PASS_RATE:.0%}")
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
                "posts": actual_posts,
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
        },
        "contentQualityCoverage": quality_coverage,
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
            "releaseId": release_id or "",
            "releaseManifestExists": _release_exists(release_id),
            "shipEvidencePaths": ship_paths,
            "importEvidencePaths": import_paths,
            "requiredThroughputPerHour": round(required_throughput_per_hour, 4),
            "requiredThroughputPerMinute": round(int(daily_target) / 1440, 4),
            "measuredThroughput": measured_throughput,
            "firstPassRate": first_pass_rate,
        },
        "envReady": {
            "ready": bool(env_report.get("ready")),
            "reportPath": str(root / "_shared" / "env_ready_report.json") if env_report else "",
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
