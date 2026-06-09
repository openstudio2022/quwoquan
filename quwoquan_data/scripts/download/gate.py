"""Exit gate for download command."""
from __future__ import annotations

from pathlib import Path

from _common.paths import batch_root


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

    for sources_dir in sources_dirs:
        source_units = [d for d in sources_dir.iterdir() if d.is_dir()]
        md_count = sum(1 for sd in source_units if (sd / "source.md").exists())
        rel = sources_dir.relative_to(root).as_posix() if sources_dir.is_relative_to(root) else sources_dir.name
        if md_count < 2:
            issues.append(f"{rel}: only {md_count} sources (need >= 2)")

    return issues
