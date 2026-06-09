"""Assemble release package from task truth sources."""
from __future__ import annotations

import shutil
from pathlib import Path

from _common.paths import release_root, task_root, task_data
from _common.io import write_json


def assemble_release(task_id: str, release_id: str) -> Path:
    """Merge all task outputs into a release directory.

    发布链直接消费 task/entities 与 batch/posts 真相源；不再依赖 runtime task 根
    的 entity_pages/graph 等历史镜像目录。
    """
    root = release_root(release_id)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    _copy_release_entities(task_id, root)

    # Posts from all batches（对象优先：成品落 batch/posts 对象根）。
    # release 包保留 5.review 侧车，供 publish_filter / ship 读取；其余过程阶段不进 release。
    _process_dirs = {"1.download", "2.quality", "3.compose", "3.brief", "3.build", "4.draft"}
    posts_dst = root / "posts"
    posts_dst.mkdir(exist_ok=True)
    batches_dir = task_root(task_id) / "batches"
    if batches_dir.exists():
        for batch_dir in sorted(batches_dir.iterdir()):
            src = batch_dir / "posts"
            if not src.is_dir():
                continue
            for manifest in sorted(src.rglob("manifest.json")):
                leaf = manifest.parent
                if not ((leaf / "article.md").exists() or (leaf / "gallery.md").exists()):
                    continue
                dst_leaf = posts_dst / leaf.relative_to(src)
                if dst_leaf.exists():
                    shutil.rmtree(dst_leaf)
                dst_leaf.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(
                    leaf, dst_leaf,
                    ignore=lambda _d, names: [n for n in names if n in _process_dirs],
                )

    # Release manifest
    write_json(root / "release_manifest.json", {
        "schemaVersion": "quwoquan_data.release_manifest",
        "releaseId": release_id,
        "sourceTaskId": task_id,
        "status": "assembled",
    })

    return root


def _copy_release_entities(task_id: str, release_dir: Path) -> None:
    entities_dst = release_dir / "entities"
    entities_dir = task_data(task_id).entities_dir()
    if entities_dir.is_dir():
        shutil.copytree(entities_dir, entities_dst)
