"""Assemble release package from task batches."""
from __future__ import annotations

from pathlib import Path
import shutil

from _common.paths import release_root, task_root, task_entities, task_tags, task_entity_pages, task_graph
from _common.io import write_json


def assemble_release(task_id: str, release_id: str) -> Path:
    """Merge all task outputs into a release directory."""
    root = release_root(release_id)
    root.mkdir(parents=True, exist_ok=True)

    # Entities
    entities_src = task_entities(task_id)
    if entities_src.exists():
        ent_dir = root / "entities"
        ent_dir.mkdir(exist_ok=True)
        shutil.copy2(entities_src, ent_dir / "entities.ndjson")

    # Tags
    tags_src = task_tags(task_id)
    if tags_src.exists():
        tag_dir = root / "tags"
        tag_dir.mkdir(exist_ok=True)
        shutil.copy2(tags_src, tag_dir / "tags.ndjson")

    # Entity pages
    pages_src = task_entity_pages(task_id)
    if pages_src.exists():
        pages_dst = root / "entity_pages"
        if pages_dst.exists():
            shutil.rmtree(pages_dst)
        shutil.copytree(pages_src, pages_dst)

    # Graph
    graph_src = task_graph(task_id) / "relations.ndjson"
    if graph_src.exists():
        graph_dir = root / "graph"
        graph_dir.mkdir(exist_ok=True)
        shutil.copy2(graph_src, graph_dir / "relations.ndjson")

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
