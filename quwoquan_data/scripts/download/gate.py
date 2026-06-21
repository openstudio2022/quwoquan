"""Exit gate for download command."""
from __future__ import annotations

from pathlib import Path

from _common.paths import batch_root
from _common.io import read_json
from _common.image_asset_strategy import (
    image_count_is_hard_quota,
    image_strategy_requires_publishable_images,
    minimum_publishable_images_per_target,
)

LEGACY_MIN_SOURCES = 2
SCALED_MIN_SOURCES = 4
SCALED_DEFAULT_MIN_IMAGES = 3


def download_requirements(task_id: str) -> dict[str, int]:
    """Return source/image minimums from the current task contract.

    For separated research, imageWorksPerTarget is the desired score
    saturation point by default.  Only hard_quota tasks or explicit
    minimumPublishableImagesPerTarget values become download blockers.
    """
    try:
        from task import store

        spec = store.load_spec(task_id)
    except Exception:  # noqa: BLE001
        spec = {}
    content = spec.get("content") or {}
    quotas = (content.get("quotas") or {})
    separated_research = str(content.get("modalityContract") or "") == "separated_research"
    scaled = bool(
        int(quotas.get("entityArticlesPerTarget") or 0)
        or int(quotas.get("imageWorksPerTarget") or 0)
        or int(quotas.get("entityHomepagesPerTarget") or 0)
        or (
            not separated_research
            and int(quotas.get("galleryPostsPerTarget") or 0)
        )
    )
    if not scaled:
        min_images = 2
        min_article_image_sources = 0
        min_article_base_sources = LEGACY_MIN_SOURCES
        min_homepage_sources = 0
    elif separated_research:
        image_works = int(quotas.get("imageWorksPerTarget") or 0)
        homepage_works = int(quotas.get("entityHomepagesPerTarget") or 0)
        article_works = int(quotas.get("entityArticlesPerTarget") or 0)
        min_article_image_sources = 0
        min_article_base_sources = article_works if article_works > 0 else 0
        min_homepage_sources = 1 if homepage_works > 0 else 0
        # Homepage images belong to homepage evidence, not to the independent
        # image-post lane. A single image work is valid with one rights-cleared
        # high-quality image; do not force cover+detail for every entity.
        if image_works > 0 and image_strategy_requires_publishable_images(spec):
            min_images = (
                max(1, image_works)
                if image_count_is_hard_quota(spec)
                else minimum_publishable_images_per_target(spec)
            )
        else:
            min_images = 0
    else:
        min_images = SCALED_DEFAULT_MIN_IMAGES
        min_article_image_sources = 0
        min_article_base_sources = SCALED_MIN_SOURCES
        min_homepage_sources = 0
    return {
        "minSources": SCALED_MIN_SOURCES if scaled else LEGACY_MIN_SOURCES,
        "minImages": min_images,
        "minArticleImageSources": min_article_image_sources,
        "minArticleBaseSources": min_article_base_sources,
        "minHomepageSources": min_homepage_sources,
    }


def _download_allows_partial_content(task_id: str) -> bool:
    try:
        from task import store

        spec = store.load_spec(task_id)
    except Exception:  # noqa: BLE001
        return False
    policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), dict) else {}
    return bool(policy.get("allowPartialContent"))


def _lane_plan_has_payload(download_dir: Path, lane: str) -> bool:
    path = download_dir / f"{lane}_source_plan.json"
    if not path.is_file():
        return False
    try:
        data = read_json(path)
    except Exception:  # noqa: BLE001
        data = {}
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    sources = data.get("sources") or payload.get("sources") or []
    image_urls = data.get("imageUrls") or payload.get("imageUrls") or []
    collections = data.get("collections") or payload.get("collections") or []
    return any(isinstance(value, list) and value for value in (sources, image_urls, collections))


def _has_lane_contract(sources_dir: Path) -> bool:
    download_dir = sources_dir.parent
    for lane in ("homepage", "article", "image"):
        if _lane_plan_has_payload(download_dir, lane):
            return True
    for meta_path in sources_dir.glob("*/meta.json"):
        try:
            meta = read_json(meta_path)
        except Exception:  # noqa: BLE001
            continue
        if str(meta.get("researchLane") or "") in {"homepage", "article"}:
            return True
    return False


def _source_roots(task_id: str, batch_id: str) -> tuple[Path, list[Path]]:
    object_root = batch_root(task_id, batch_id) / "entities"
    if object_root.is_dir():
        object_sources = [p for p in object_root.rglob("1.download/sources") if p.is_dir()]
        if object_sources:
            return object_root, sorted(object_sources)

    return object_root, []


def _abandoned_entities(task_id: str, batch_id: str) -> set[str]:
    state_path = batch_root(task_id, batch_id) / "_shared" / "task_workflow_state.json"
    if not state_path.is_file():
        return set()
    try:
        state = read_json(state_path)
    except Exception:  # noqa: BLE001
        return set()
    out: set[str] = set()
    for item in state.get("abandonedObjects") or []:
        if isinstance(item, dict):
            entity = str(item.get("entityId") or "").strip()
            if entity:
                out.add(entity)
    return out


def _entity_from_sources_dir(root: Path, sources_dir: Path) -> str:
    try:
        rel = sources_dir.relative_to(root)
    except ValueError:
        return ""
    parts = rel.parts
    if "1.download" in parts:
        index = parts.index("1.download")
        if index > 0:
            return parts[index - 1]
    return ""


def _missing_sources_label(root: Path, entity: str) -> str:
    for candidate in root.glob(f"*/*/{entity}"):
        if candidate.is_dir():
            try:
                return (candidate / "1.download" / "sources").relative_to(root).as_posix()
            except ValueError:
                break
    return f"{entity}/1.download/sources"


def _homepage_base_ready(
    task_id: str,
    batch_id: str,
    batch_dir: Path,
    source_dir: Path,
    meta: dict,
    entity: str,
) -> bool:
    if str(meta.get("researchLane") or "") != "homepage":
        return False
    source_path = source_dir / "source.md"
    if not source_path.is_file():
        return False
    try:
        from _common.base_draft import load_base_draft_text

        source_ref = source_path.relative_to(batch_dir).as_posix()
        text = load_base_draft_text(task_id, batch_id, source_ref)
    except Exception:  # noqa: BLE001
        return False
    try:
        from build.homepage import homepage_base_draft_readiness

        verdict = homepage_base_draft_readiness(meta, text, entity_name=entity)
    except Exception:  # noqa: BLE001
        return False
    return bool(verdict.get("ready"))


def _stage_gate_report_issues(
    task_id: str,
    batch_id: str,
    abandoned: set[str],
    *,
    target_entities: set[str] | None = None,
    allow_partial_content: bool = False,
    requirements: dict[str, int] | None = None,
) -> list[str]:
    result_root = batch_root(task_id, batch_id) / "task_download" / "results"
    issues: list[str] = []
    min_images = int((requirements or {}).get("minImages") or 0)
    for step in (
        "source_plan_gate",
        "image_rights_gate",
        "image_fetch_gate",
        "entity_source_bundle_gate",
    ):
        step_dir = result_root / step
        if not step_dir.is_dir():
            continue
        for path in sorted(step_dir.glob("*.json")):
            try:
                data = read_json(path)
            except Exception:  # noqa: BLE001
                continue
            payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
            if not isinstance(payload, dict) or payload.get("passed") is not False:
                continue
            ref = str(payload.get("ref") or path.stem)
            if ref in abandoned:
                continue
            if target_entities is not None and ref not in target_entities:
                continue
            raw_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
            if raw_issues:
                for issue in raw_issues:
                    text = str(issue)
                    if _partial_content_soft_stage_issue(
                        step,
                        text,
                        allow_partial_content=allow_partial_content,
                        min_images=min_images,
                    ):
                        continue
                    issues.append(f"{ref}: {text}")
            else:
                if _partial_content_soft_stage_issue(
                    step,
                    "",
                    allow_partial_content=allow_partial_content,
                    min_images=min_images,
                ):
                    continue
                issues.append(f"{ref}: {step} failed")
    return issues


def _partial_content_soft_stage_issue(
    step: str,
    issue: str,
    *,
    allow_partial_content: bool,
    min_images: int,
) -> bool:
    if not allow_partial_content:
        return False
    text = issue.lower()
    if step == "image_fetch_gate" and min_images <= 0:
        quantity_markers = (
            "imagefetch: 未下到真实图片",
            "imagecount:",
            "only ",
            "unique publishable images",
            "未下到",
            "downloadedimages",
        )
        return not text or any(marker in text for marker in quantity_markers)
    if step == "source_plan_gate":
        source_quantity_markers = (
            "fewer than",
            "sources=",
            "need>=",
            "research needs >=",
            "homepage research needs",
            "sourceplan:",
        )
        return any(marker in text for marker in source_quantity_markers)
    if step == "entity_source_bundle_gate":
        bundle_quantity_markers = (
            "retained sources",
            "baseDraft-ready",
            "only ",
            "sources directory missing",
        )
        return any(marker.lower() in text for marker in bundle_quantity_markers)
    return False


def gate_download(task_id: str, batch_id: str, *, target_entities: set[str] | None = None) -> list[str]:
    """Check download exit criteria.

    只检查对象树 `entities/**/1.download/sources/`；每个对象至少需要 2 个可消费来源单元。
    """
    issues: list[str] = []
    requirements = download_requirements(task_id)
    allow_partial_content = _download_allows_partial_content(task_id)
    root, sources_dirs = _source_roots(task_id, batch_id)
    if not sources_dirs:
        if allow_partial_content:
            return []
        if target_entities:
            for entity in sorted(target_entities - _abandoned_entities(task_id, batch_id)):
                issues.append(f"{_missing_sources_label(root, entity)}: sources directory missing")
            return issues
        issues.append(f"No sources directory under {root}")
        return issues

    abandoned = _abandoned_entities(task_id, batch_id)
    source_entities = {_entity_from_sources_dir(root, path) for path in sources_dirs}
    if target_entities is not None:
        for entity in sorted(target_entities):
            if entity and entity not in abandoned and entity not in source_entities and not allow_partial_content:
                issues.append(f"{_missing_sources_label(root, entity)}: sources directory missing")
    batch_dir = root.parent
    for sources_dir in sources_dirs:
        entity = _entity_from_sources_dir(root, sources_dir)
        if entity in abandoned:
            continue
        if target_entities is not None and entity not in target_entities:
            continue
        source_units = [d for d in sources_dir.iterdir() if d.is_dir()]
        md_count = 0
        retained_count = 0
        lane_md_count = {"homepage": 0, "article": 0}
        lane_retained_count = {"homepage": 0, "article": 0}
        homepage_base_ready_count = 0
        image_hashes: set[str] = set()
        image_rights_issues: list[str] = []
        lane_contract = _has_lane_contract(sources_dir)
        for sd in source_units:
            meta_path = sd / "meta.json"
            try:
                meta = read_json(meta_path) if meta_path.is_file() else {}
            except Exception:  # noqa: BLE001
                meta = {}
            lane = str(meta.get("researchLane") or "")
            is_image_unit = lane in {"image", "homepage_image"}
            if (sd / "source.md").exists() and not is_image_unit:
                md_count += 1
                if lane in lane_md_count:
                    lane_md_count[lane] += 1
            quality_path = sd / "source.quality.json"
            if not quality_path.is_file():
                continue
            try:
                payload = read_json(quality_path)
            except Exception:  # noqa: BLE001
                continue
            if str(payload.get("quality") or "") != "Reject" and not is_image_unit:
                retained_count += 1
                if lane in lane_retained_count:
                    lane_retained_count[lane] += 1
                if _homepage_base_ready(task_id, batch_id, batch_dir, sd, meta, entity):
                    homepage_base_ready_count += 1
            index_path = sd / "assets" / "index.json"
            source_assets: list[dict] = []
            if index_path.is_file():
                try:
                    source_assets = read_json(index_path).get("assets") or []
                except Exception:  # noqa: BLE001
                    source_assets = []
                for asset in source_assets:
                    if not isinstance(asset, dict):
                        continue
                    digest = str(asset.get("sha256") or asset.get("sourceAssetId") or "")
                    if digest:
                        image_hashes.add(digest)
                    missing = [
                        field for field in ("license", "credit", "sourceUrl", "termsUrl", "usageScope")
                        if not str(asset.get(field) or "").strip()
                    ]
                    if missing:
                        image_rights_issues.append(
                            f"{sd.name}/{asset.get('fileName') or '?'} missing image rights {missing}"
                        )
        rel = sources_dir.relative_to(root).as_posix() if sources_dir.is_relative_to(root) else sources_dir.name
        if not allow_partial_content and md_count < requirements["minSources"]:
            issues.append(f"{rel}: only {md_count} sources (need >= {requirements['minSources']})")
        if not allow_partial_content and retained_count < requirements["minSources"]:
            issues.append(
                f"{rel}: only {retained_count} retained sources "
                f"(need >= {requirements['minSources']}; Reject/manual probe sources do not count)"
            )
        if lane_contract:
            download_dir = sources_dir.parent
            homepage_required = (
                int(requirements.get("minHomepageSources") or 0) > 0
                or _lane_plan_has_payload(download_dir, "homepage")
                or lane_md_count["homepage"] > 0
            )
            if not allow_partial_content and homepage_required and lane_retained_count["homepage"] < 1:
                issues.append(
                    f"{rel}: homepage retained sources={lane_retained_count['homepage']} need>=1 "
                    "(homepage lane must yield a readable encyclopedia/wiki/official source unit)"
                )
            elif not allow_partial_content and homepage_required and homepage_base_ready_count < 1:
                issues.append(
                    f"{rel}: homepage baseDraft-ready sources={homepage_base_ready_count} need>=1 "
                    "(homepage lane must yield an encyclopedia/wiki/official source with >=4 usable facts)"
                )
            min_article_sources = int(requirements.get("minArticleBaseSources") or requirements["minSources"])
            article_required = (
                min_article_sources > 0
                and (
                    _lane_plan_has_payload(download_dir, "article")
                    or lane_md_count["article"] > 0
                )
            )
            if not allow_partial_content and article_required and lane_retained_count["article"] < min_article_sources:
                issues.append(
                    f"{rel}: article retained sources={lane_retained_count['article']} "
                    f"need>={min_article_sources}"
                )
        if len(image_hashes) < requirements["minImages"]:
            issues.append(
                f"{rel}: only {len(image_hashes)} unique publishable images "
                f"(need >= {requirements['minImages']})"
            )
        issues.extend(f"{rel}: {issue}" for issue in image_rights_issues)

    seen = set(str(issue) for issue in issues)
    for issue in _stage_gate_report_issues(
        task_id,
        batch_id,
        abandoned,
        target_entities=target_entities,
        allow_partial_content=allow_partial_content,
        requirements=requirements,
    ):
        if str(issue) not in seen:
            issues.append(str(issue))
            seen.add(str(issue))
    return issues
