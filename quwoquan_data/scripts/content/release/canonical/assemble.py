"""Assemble release package from content truth sources."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from core.entity_object import collect_execution_entity_objects
from core.paths import release_root
from core.io import read_json, write_json
from content.review.publish_filter import apply_publish_filter
from content.execution.workspace import execution_root, load_frozen_target_set

_RELEASE_EVIDENCE = ("attestation.json", "evidence_index.json")


def _execution_is_homepage_only(execution_id: str) -> bool:
    """homepage-only 任务：仅主页配额，实体主页即发布面（无 posts 篇目）。"""
    from content.execution import store
    from core.execution_branch import is_homepage_only_spec

    return is_homepage_only_spec(store.load_spec(execution_id))


def assemble_release(execution_id: str, release_id: str) -> Path:
    """Build one immutable release from exactly one execution work package.

    发布链直接消费 execution 的 entities/posts；不再读取 task/batch 镜像或
    任何历史运行目录。
    """
    final_root = release_root(release_id)
    if final_root.exists():
        raise FileExistsError(f"release is create-once and already exists: {final_root}")
    final_root.parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=f".{release_id}.assembling-", dir=final_root.parent))

    try:
        # release 只保留最终对象 + compact attestation/evidence index。
        posts_dst = root / "posts"
        posts_dst.mkdir()
        post_pairs: list[tuple[Path, Path]] = []
        execution_dir = execution_root(execution_id)
        src = execution_dir / "posts"
        if src.is_dir():
            for manifest_path in sorted(src.rglob("manifest.json")):
                leaf = manifest_path.parent
                manifest = read_json(manifest_path)
                if not isinstance(manifest, dict):
                    continue
                if not _is_asset_only_manifest(manifest) and not (leaf / "article.md").exists():
                    continue
                dst_leaf = posts_dst / leaf.relative_to(src)
                _copy_post_surface(leaf, dst_leaf, manifest=manifest)
                post_pairs.append((leaf, dst_leaf))

        _copy_release_entities(
            execution_id,
            root,
            allowed_entity_rels=(
                _target_entity_rels_from_execution(execution_id)
                if _execution_is_homepage_only(execution_id)
                else _primary_entity_rels_from_posts(posts_dst)
            ),
        )
        for runtime_post, release_post in post_pairs:
            verdict = apply_publish_filter(
                runtime_post,
                root,
                entity_homepage_root=root / "entities",
            )
            if not verdict.publishable:
                raise ValueError(
                    f"release candidate is not publishable: {runtime_post}: {verdict.reasons}"
                )
            verdict.write_into(release_post)

        write_json(root / "release_manifest.json", {
            "schema": "quwoquan_data.release_manifest",
            "releaseId": release_id,
            "executionId": execution_id,
            "status": "assembled",
        })
        write_json(
            root / "evidence_index.json",
            {
                "schema": "quwoquan_data.release_evidence_index",
                "releaseId": release_id,
                "executionId": execution_id,
                "executionRef": f"data/tasks/{execution_id}",
                "note": (
                    "All process stages remain in the execution work package; release carries "
                    "final surfaces plus compact attestation/evidence indexes only."
                ),
            },
        )
        root.replace(final_root)
        return final_root
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


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
    _copy_compact_evidence(src_dir / "5.review", dst_dir)


def _copy_compact_evidence(src: Path, dst: Path) -> None:
    for name in _RELEASE_EVIDENCE:
        path = src / name
        if not path.is_file():
            raise FileNotFoundError(f"approved object missing compact release evidence: {path}")
        shutil.copy2(path, dst / name)


def _is_image_manifest(manifest: dict) -> bool:
    return str(manifest.get("contentType") or "") == "image" or str(
        manifest.get("carrier") or ""
    ) == "image"


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
        # Image packages retain the canonical structured image surface.
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
    _copy_compact_evidence(src / "5.review", dst)


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


def _target_entity_rels_from_execution(execution_id: str) -> set[str]:
    target_set = load_frozen_target_set(execution_id)
    refs = target_set.get("targetRefs")
    if not isinstance(refs, list) or not refs:
        raise ValueError(f"execution frozen target set has no targetRefs: {execution_id}")
    allowed: set[str] = set()
    for raw in refs:
        parts = Path(str(raw or "").strip().strip("/")).parts
        if len(parts) < 3 or any(part in {"", ".", ".."} for part in parts):
            raise ValueError(
                f"execution frozen target set contains an invalid entity ref: {execution_id}"
            )
        allowed.add((Path("entities") / Path(*parts)).as_posix())
    return allowed


def _copy_release_entities(
    execution_id: str,
    release_dir: Path,
    *,
    allowed_entity_rels: set[str],
) -> None:
    entities_dst = release_dir / "entities"
    rows = collect_execution_entity_objects(
        execution_id=execution_id,
        approved_only=True,
        enforce_type_consistency=True,
    )
    for row in rows:
        src_dir = Path(row["entityDir"])
        rel = Path(str(row["entityRel"]))
        if rel.as_posix() not in allowed_entity_rels:
            continue
        dst_dir = release_dir / rel
        _copy_entity_surface(src_dir, dst_dir)
