"""批次对象遍历公共工具。"""
from __future__ import annotations

from pathlib import Path


def _looks_like_materialized_post(parent: Path) -> bool:
    return (
        (parent / "article.md").exists()
        or (parent / "gallery.md").exists()
        or (parent / "_object.json").exists()
        or (parent / "assets").is_dir()
    )


def iter_batch_object_dirs(batch: Path) -> list[Path]:
    """收集批次内所有对象根（实体过程对象 + 成品内容对象）。"""
    objs: list[Path] = []
    ent_root = batch / "entities"
    if ent_root.is_dir():
        for entity_json in ent_root.rglob("_entity.json"):
            objs.append(entity_json.parent)
        for dl in ent_root.rglob("1.download"):
            if dl.parent not in objs:
                objs.append(dl.parent)
    post_root = batch / "posts"
    if post_root.is_dir():
        for manifest in post_root.rglob("manifest.json"):
            parent = manifest.parent
            if _looks_like_materialized_post(parent):
                objs.append(parent)
    return sorted(set(objs))
