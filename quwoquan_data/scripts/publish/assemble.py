"""Assemble release package from task truth sources."""
from __future__ import annotations

import shutil
from pathlib import Path

from _common.entity_object import collect_task_entity_objects
from _common.paths import release_root, task_root
from _common.io import write_json

_REVIEW_SIDECARS = {
    "review.json",
    "review_gate.json",
    "ref_review_gate.json",
    "media_check.json",
    "media_check_gate.json",
    "review_ledger.json",
    "review_entities.json",
    "provenance.json",
    "finalization_report.json",
}


def assemble_release(task_id: str, release_id: str, *, batch_id: str = "") -> Path:
    """Merge all task outputs into a release directory.

    发布链直接消费 task/entities 与 batch/posts 真相源；不再依赖 runtime task 根
    的 entity_pages/graph 等历史镜像目录。
    """
    root = release_root(release_id)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    _copy_release_entities(task_id, root, batch_id=batch_id)

    # Posts from all batches（对象优先：成品落 batch/posts 对象根）。
    # release 包保留 5.review 侧车，供 publish_filter / ship 读取；其余过程阶段不进 release。
    posts_dst = root / "posts"
    posts_dst.mkdir(exist_ok=True)
    batches_dir = task_root(task_id) / "batches"
    if batches_dir.exists():
        batch_dirs = [batches_dir / batch_id] if batch_id else sorted(batches_dir.iterdir())
        for batch_dir in batch_dirs:
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
                _copy_post_surface(leaf, dst_leaf)

    # Release manifest
    write_json(root / "release_manifest.json", {
        "schemaVersion": "quwoquan_data.release_manifest",
        "releaseId": release_id,
        "sourceTaskId": task_id,
        "sourceBatchId": batch_id,
        "status": "assembled",
    })

    return root


def _copy_entity_surface(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.parent.mkdir(parents=True, exist_ok=True)
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in ("_entity.json", "page.md", "manifest.json"):
        src = src_dir / name
        if src.is_file():
            shutil.copy2(src, dst_dir / name)
    src_assets = src_dir / "assets"
    if src_assets.is_dir():
        shutil.copytree(src_assets, dst_dir / "assets")
    _copy_review_sidecars(src_dir / "5.review", dst_dir / "5.review")


def _copy_review_sidecars(src: Path, dst: Path) -> None:
    if not src.is_dir():
        return
    for name in sorted(_REVIEW_SIDECARS):
        path = src / name
        if not path.is_file():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst / name)


def _copy_post_surface(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("article.md", "gallery.md", "manifest.json"):
        path = src / name
        if path.is_file():
            shutil.copy2(path, dst / name)
    assets = src / "assets"
    if assets.is_dir():
        shutil.copytree(assets, dst / "assets")
    _copy_review_sidecars(src / "5.review", dst / "5.review")


def _copy_release_entities(task_id: str, release_dir: Path, *, batch_id: str = "") -> None:
    entities_dst = release_dir / "entities"
    rows = collect_task_entity_objects(
        task_id,
        batch_id=batch_id,
        include_task_mirror_fallback=True,
        approved_only=True,
        enforce_type_consistency=True,
    )
    for row in rows:
        src_dir = Path(row["entityDir"])
        rel = Path(str(row["entityRel"]))
        dst_dir = release_dir / rel
        _copy_entity_surface(src_dir, dst_dir)
