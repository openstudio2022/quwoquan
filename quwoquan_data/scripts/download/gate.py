"""Exit gate for download command."""
from __future__ import annotations

from pathlib import Path

from _common.paths import batch_root
from _common.io import read_json

LEGACY_MIN_SOURCES = 2
SCALED_MIN_SOURCES = 4
SCALED_DEFAULT_MIN_IMAGES = 3


def download_requirements(task_id: str) -> dict[str, int]:
    """Return source/image minimums from the current task contract.

    For separated research, image capacity follows the declared object quota:
    each entity homepage needs at least one sourced image from homepage
    evidence, and each image work needs at least one publishable image from
    its own image collection. Multi-image works are allowed but not required.
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
    elif separated_research:
        image_works = int(quotas.get("imageWorksPerTarget") or 0)
        homepages = int(quotas.get("entityHomepagesPerTarget") or 0)
        min_article_image_sources = int(quotas.get("entityArticlesPerTarget") or 0)
        min_images = max(1, image_works + homepages)
    else:
        min_images = SCALED_DEFAULT_MIN_IMAGES
        min_article_image_sources = 0
    return {
        "minSources": SCALED_MIN_SOURCES if scaled else LEGACY_MIN_SOURCES,
        "minImages": min_images,
        "minArticleImageSources": min_article_image_sources,
    }


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


def _stage_gate_report_issues(task_id: str, batch_id: str, abandoned: set[str]) -> list[str]:
    result_root = batch_root(task_id, batch_id) / "task_download" / "results"
    issues: list[str] = []
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
            raw_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
            if raw_issues:
                issues.extend(f"{ref}: {issue}" for issue in raw_issues)
            else:
                issues.append(f"{ref}: {step} failed")
    return issues


def gate_download(task_id: str, batch_id: str) -> list[str]:
    """Check download exit criteria.

    只检查对象树 `entities/**/1.download/sources/`；每个对象至少需要 2 个可消费来源单元。
    """
    issues: list[str] = []
    root, sources_dirs = _source_roots(task_id, batch_id)
    if not sources_dirs:
        issues.append(f"No sources directory under {root}")
        return issues

    requirements = download_requirements(task_id)
    abandoned = _abandoned_entities(task_id, batch_id)
    for sources_dir in sources_dirs:
        entity = _entity_from_sources_dir(root, sources_dir)
        if entity in abandoned:
            continue
        source_units = [d for d in sources_dir.iterdir() if d.is_dir()]
        md_count = 0
        retained_count = 0
        image_hashes: set[str] = set()
        image_rights_issues: list[str] = []
        article_sources_with_images = 0
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
            quality_path = sd / "source.quality.json"
            if not quality_path.is_file():
                continue
            try:
                payload = read_json(quality_path)
            except Exception:  # noqa: BLE001
                continue
            if str(payload.get("quality") or "") != "Reject" and not is_image_unit:
                retained_count += 1
            index_path = sd / "assets" / "index.json"
            source_assets: list[dict] = []
            if index_path.is_file():
                try:
                    source_assets = read_json(index_path).get("assets") or []
                except Exception:  # noqa: BLE001
                    source_assets = []
                if lane == "article" and source_assets:
                    article_sources_with_images += 1
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
        if md_count < requirements["minSources"]:
            issues.append(f"{rel}: only {md_count} sources (need >= {requirements['minSources']})")
        if retained_count < requirements["minSources"]:
            issues.append(
                f"{rel}: only {retained_count} retained sources "
                f"(need >= {requirements['minSources']}; Reject/manual probe sources do not count)"
            )
        if len(image_hashes) < requirements["minImages"]:
            issues.append(
                f"{rel}: only {len(image_hashes)} unique publishable images "
                f"(need >= {requirements['minImages']})"
            )
        if (
            requirements.get("minArticleImageSources", 0)
            and article_sources_with_images < requirements["minArticleImageSources"]
        ):
            issues.append(
                f"{rel}: only {article_sources_with_images} article source unit(s) with images "
                f"(need >= {requirements['minArticleImageSources']}; article base draft must be text+source images)"
            )
        issues.extend(f"{rel}: {issue}" for issue in image_rights_issues)

    seen = set(str(issue) for issue in issues)
    for issue in _stage_gate_report_issues(task_id, batch_id, abandoned):
        if str(issue) not in seen:
            issues.append(str(issue))
            seen.add(str(issue))
    return issues
