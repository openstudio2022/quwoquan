"""Assemble release package from task batches."""
from __future__ import annotations

from pathlib import Path
import shutil

from _common.paths import release_root, task_root, task_entities, task_tags, task_entity_pages, task_graph, TASKS_ROOT
from _common.io import read_ndjson, write_ndjson, write_json


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

    # Posts from all batches
    posts_dst = root / "posts"
    posts_dst.mkdir(exist_ok=True)
    task_dir = task_root(task_id)
    batches_dir = task_dir / "batches"
    if batches_dir.exists():
        for batch_dir in sorted(batches_dir.iterdir()):
            produce_posts = batch_dir / "produce" / "posts"
            if produce_posts.exists():
                for type_dir in produce_posts.iterdir():
                    if type_dir.is_dir():
                        dst_type = posts_dst / type_dir.name
                        dst_type.mkdir(exist_ok=True)
                        for topic_dir in type_dir.iterdir():
                            if topic_dir.is_dir():
                                dst_topic = dst_type / topic_dir.name
                                if not dst_topic.exists():
                                    shutil.copytree(topic_dir, dst_topic)

    # Release manifest
    write_json(root / "release_manifest.json", {
        "schemaVersion": "quwoquan_data.release_manifest",
        "releaseId": release_id,
        "sourceTaskId": task_id,
        "status": "assembled",
    })

    return root
