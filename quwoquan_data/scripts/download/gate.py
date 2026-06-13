"""Exit gate for download command."""
from __future__ import annotations

from pathlib import Path

from _common.paths import batch_root
from _common.io import read_json

LEGACY_MIN_SOURCES = 2
SCALED_MIN_SOURCES = 4
SCALED_MIN_IMAGES = 10


def download_requirements(task_id: str) -> dict[str, int]:
    """按任务配额决定下载充分性；旧任务保持兼容，规模化任务启用 4 源/10 图硬门。"""
    try:
        from task import store

        spec = store.load_spec(task_id)
    except Exception:  # noqa: BLE001
        spec = {}
    quotas = ((spec.get("content") or {}).get("quotas") or {})
    scaled = bool(
        int(quotas.get("entityArticlesPerTarget") or 0)
        or int(quotas.get("galleryPostsPerTarget") or 0)
        or int(quotas.get("entityHomepagesPerTarget") or 0)
    )
    return {
        "minSources": SCALED_MIN_SOURCES if scaled else LEGACY_MIN_SOURCES,
        "minImages": SCALED_MIN_IMAGES if scaled else 2,
    }


def _source_roots(task_id: str, batch_id: str) -> tuple[Path, list[Path]]:
    object_root = batch_root(task_id, batch_id) / "entities"
    if object_root.is_dir():
        object_sources = [p for p in object_root.rglob("1.download/sources") if p.is_dir()]
        if object_sources:
            return object_root, sorted(object_sources)

    return object_root, []


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
    for sources_dir in sources_dirs:
        source_units = [d for d in sources_dir.iterdir() if d.is_dir()]
        md_count = sum(1 for sd in source_units if (sd / "source.md").exists())
        retained_count = 0
        image_hashes: set[str] = set()
        image_rights_issues: list[str] = []
        for sd in source_units:
            quality_path = sd / "source.quality.json"
            if not quality_path.is_file():
                continue
            try:
                payload = read_json(quality_path)
            except Exception:  # noqa: BLE001
                continue
            if str(payload.get("quality") or "") != "Reject":
                retained_count += 1
            index_path = sd / "assets" / "index.json"
            if index_path.is_file():
                try:
                    assets = read_json(index_path).get("assets") or []
                except Exception:  # noqa: BLE001
                    assets = []
                for asset in assets:
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
        issues.extend(f"{rel}: {issue}" for issue in image_rights_issues)

    return issues
