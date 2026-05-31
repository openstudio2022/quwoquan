#!/usr/bin/env python3
"""Promote gated release or task produce/posts into the single publish mainline.

Only run after review approval + publish gate. Does not write from bootstrap/sample shortcuts.

发布门（review_ledger 驱动）：
- 文章 item 必须 publishable；
- discard 图片从发布 manifest/articleAssetManifest/正文引用一并剔除；
- 进入 entityRefs 的实体必须有主页（entities/{d}/{t}/{name}/page.md），否则该 entityRef 被过滤；
- 任一 hard 条件不满足则跳过该 post 并报告（不静默 BLOCK 全量）。

用法:
  python3 promote_to_publish.py --release-id 校园冷启动_r1
  python3 promote_to_publish.py --task <task> --batch <batch>
  python3 promote_to_publish.py --release-id 校园冷启动_r1 --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common.article_package import infer_format_angle  # noqa: E402
from _common.paths import (  # noqa: E402
    PUBLISH_ROOT,
    NOW_ISO,
    publish_data,
    publish_meta_path,
    release_root,
    task_root,
)
from _common.publish_filter import apply_publish_filter  # noqa: E402
from build_publish_lookup_indexes import build_publish_lookup_indexes  # noqa: E402


def _publish_post_dir(
    pd_root: Path,
    content_type: str,
    angle: str,
    title: str,
    seq: int,
) -> Path:
    return pd_root / "posts" / content_type / angle / title / str(seq)


def _remove_stale_publish_post(
    pd_root: Path,
    content_type: str,
    title: str,
    seq: int,
    angle: str,
) -> None:
    """Remove same title/seq published under a different angle directory."""
    type_root = pd_root / "posts" / content_type
    if not type_root.is_dir():
        return
    for angle_dir in type_root.iterdir():
        if not angle_dir.is_dir() or angle_dir.name == angle:
            continue
        stale = angle_dir / title / str(seq)
        if stale.is_dir():
            shutil.rmtree(stale)


def _copy_post_tree(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _resolve_publish_target(manifest: dict, src_name: str) -> tuple[str, str, str, int]:
    layout = manifest.get("publishLayout", "travel")
    angle = manifest.get("publishAngle") or infer_format_angle(manifest.get("tagRefs", []))
    title = manifest.get("publishTitle") or src_name
    seq = int(manifest.get("publishSeq", 1))

    if layout == "campus":
        entity_refs = manifest.get("entityRefs", [])
        school = ""
        if entity_refs:
            school = entity_refs[0].strip("/").split("/")[-1]
        if angle in ("", "索引") and school:
            return "article", "索引", school, seq
        if school and not manifest.get("publishTitle"):
            title = school
        return "article", angle, title, seq

    if not manifest.get("publishTitle"):
        entity_refs = manifest.get("entityRefs", [])
        if entity_refs:
            entity_name = entity_refs[0].strip("/").split("/")[-1]
            title = f"{entity_name}{angle}指南"
    return "article", angle, title, seq


def promote_from_posts_root(posts_root: Path, dry_run: bool) -> tuple[int, int]:
    if not posts_root.exists():
        print(f"[promote] No posts at {posts_root}")
        return 0, 0

    pd = publish_data()
    count = 0
    skipped = 0
    for type_dir in sorted(posts_root.iterdir()):
        if not type_dir.is_dir():
            continue
        content_type = type_dir.name
        for topic_dir in sorted(type_dir.iterdir()):
            if not topic_dir.is_dir():
                continue
            manifest_path = topic_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("reviewDecision") not in (None, "approved"):
                print(f"[promote] SKIP (not approved): {topic_dir.name}")
                skipped += 1
                continue

            # 发布门：账本发布态 + 实体主页存在性。返回过滤后的 post 内容或 None（不可发布）。
            verdict = apply_publish_filter(topic_dir, pd.root)
            if not verdict.publishable:
                print(f"[promote] SKIP (publish gate): {topic_dir.name} :: {verdict.reasons}")
                skipped += 1
                continue
            if verdict.filtered_entities:
                print(f"[promote] filtered entityRefs (no homepage): {verdict.filtered_entities}")
            if verdict.discarded_assets:
                print(f"[promote] discarded assets: {verdict.discarded_assets}")

            resolved_type, angle, title, seq = _resolve_publish_target(
                verdict.manifest, topic_dir.name
            )
            dst = _publish_post_dir(pd.root, resolved_type or content_type, angle, title, seq)
            if dry_run:
                print(f"[promote] would copy {topic_dir} -> {dst}")
            else:
                _remove_stale_publish_post(pd.root, resolved_type or content_type, title, seq, angle)
                _copy_post_tree(topic_dir, dst)
                verdict.write_into(dst)
            count += 1

    return count, skipped


def promote_release(release_id: str, dry_run: bool) -> tuple[int, int]:
    root = release_root(release_id)
    posts = root / "posts"
    print(f"[promote] From release: {root}")
    return promote_from_posts_root(posts, dry_run)


def promote_task_batch(task_id: str, batch_id: str, dry_run: bool) -> tuple[int, int]:
    posts = task_root(task_id) / "batches" / batch_id / "produce" / "posts"
    print(f"[promote] From task batch: {posts}")
    return promote_from_posts_root(posts, dry_run)


def promote_task_entities(task_id: str, dry_run: bool) -> int:
    """Copy task entities tree into the publish mainline when present."""
    src_entities = task_root(task_id) / "entities"
    if not src_entities.is_dir():
        return 0
    dst = publish_data().entities_dir()
    count = 0
    for entity_json in src_entities.rglob("_entity.json"):
        rel = entity_json.relative_to(src_entities)
        target = dst / rel.parent
        if dry_run:
            print(f"[promote] would copy entity {rel.parent}")
        else:
            target.mkdir(parents=True, exist_ok=True)
            for fname in ("_entity.json", "page.md"):
                src_f = entity_json.parent / fname
                if src_f.exists():
                    shutil.copy2(src_f, target / fname)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote release/task posts to the publish mainline")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--release-id", help="Assembled release id under release/")
    src.add_argument("--task", help="Task id under runtime/tasks/")
    parser.add_argument("--batch", help="Batch id (required with --task)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--copy-entities", action="store_true", help="With --task, also copy entities/")
    args = parser.parse_args()

    if args.task and not args.batch:
        parser.error("--batch is required when using --task")

    PUBLISH_ROOT.mkdir(parents=True, exist_ok=True)

    if args.release_id:
        post_count, skipped = promote_release(args.release_id, args.dry_run)
    else:
        post_count, skipped = promote_task_batch(args.task, args.batch, args.dry_run)
        if args.copy_entities:
            promote_task_entities(args.task, args.dry_run)

    print(f"[promote] Posts promoted: {post_count} (skipped: {skipped})")

    if post_count == 0:
        sys.exit(1)

    if args.dry_run:
        return

    meta = {
        "schemaVersion": "quwoquan.publish.meta",
        "publishedAt": NOW_ISO,
        "lastPromote": NOW_ISO,
        "lastShip": None,
    }
    if args.release_id:
        meta["lastReleaseId"] = args.release_id
    if args.task:
        meta["lastTaskId"] = args.task
        meta["lastBatchId"] = args.batch
    publish_meta_path().write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if not args.skip_index:
        counts = build_publish_lookup_indexes()
        print(f"[promote] lookup indexes: entities={counts['entities']}, posts={counts['posts']}")


if __name__ == "__main__":
    main()
