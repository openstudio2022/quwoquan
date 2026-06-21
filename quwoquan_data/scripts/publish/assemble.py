"""Assemble release package from task truth sources."""
from __future__ import annotations

import shutil
from pathlib import Path

from _common.entity_object import collect_task_entity_objects
from _common.paths import release_root, task_root
from _common.io import read_json, write_json

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
            for manifest_path in sorted(src.rglob("manifest.json")):
                leaf = manifest_path.parent
                manifest = read_json(manifest_path)
                if not isinstance(manifest, dict):
                    continue
                if not _is_asset_only_manifest(manifest) and not (leaf / "article.md").exists():
                    continue
                dst_leaf = posts_dst / leaf.relative_to(src)
                if dst_leaf.exists():
                    shutil.rmtree(dst_leaf)
                _copy_post_surface(leaf, dst_leaf, manifest=manifest)

    # Entity homepages are publishable only for the primary entities actually
    # present in release posts. Abandoned/replaced candidates may be approved in
    # the batch for audit, but they must not leak into the isolated release.
    _copy_release_entities(
        task_id,
        root,
        batch_id=batch_id,
        allowed_entity_rels=_primary_entity_rels_from_posts(posts_dst),
    )

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


def _is_image_manifest(manifest: dict) -> bool:
    return str(manifest.get("contentType") or "") == "image" or str(
        manifest.get("carrier") or ""
    ) in ("image", "gallery")


def _is_video_manifest(manifest: dict) -> bool:
    return str(manifest.get("contentType") or manifest.get("carrier") or "") == "video"


def _is_asset_only_manifest(manifest: dict) -> bool:
    return _is_image_manifest(manifest) or _is_video_manifest(manifest)


def _copy_post_surface(src: Path, dst: Path, *, manifest: dict) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    release_manifest = dict(manifest)
    if _is_image_manifest(manifest):
        # Legacy gallery packages are upgraded to the structured image surface.
        release_manifest["contentType"] = "image"
    else:
        article = src / "article.md"
        if article.is_file():
            shutil.copy2(article, dst / "article.md")
    if _is_video_manifest(manifest):
        video_md = src / "video.md"
        if video_md.is_file():
            shutil.copy2(video_md, dst / "video.md")
    write_json(dst / "manifest.json", release_manifest)
    assets = src / "assets"
    if assets.is_dir():
        shutil.copytree(assets, dst / "assets")
    _copy_review_sidecars(src / "5.review", dst / "5.review")


def _entity_rel_from_ref(raw: object) -> str:
    text = str(raw or "").strip().strip("/")
    if not text:
        return ""
    if text.startswith("entity/"):
        parts = text.split("/")
        if len(parts) >= 4:
            return (Path("entities") / parts[1] / parts[2] / "/".join(parts[3:])).as_posix()
    if text.startswith("entities/"):
        return text
    return ""


def _primary_entity_rels_from_posts(posts_root: Path) -> set[str]:
    allowed: set[str] = set()
    if not posts_root.is_dir():
        return allowed
    for manifest_path in sorted(posts_root.rglob("manifest.json")):
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict):
            continue
        refs = manifest.get("entityRefs") or []
        if not isinstance(refs, list) or not refs:
            continue
        rel = _entity_rel_from_ref(refs[0])
        if rel:
            allowed.add(rel)
    return allowed


def _copy_release_entities(
    task_id: str,
    release_dir: Path,
    *,
    batch_id: str = "",
    allowed_entity_rels: set[str] | None = None,
) -> None:
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
        if allowed_entity_rels is not None and rel.as_posix() not in allowed_entity_rels:
            continue
        dst_dir = release_dir / rel
        _copy_entity_surface(src_dir, dst_dir)
