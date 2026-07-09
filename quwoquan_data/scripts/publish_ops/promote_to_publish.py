#!/usr/bin/env python3
"""Promote gated release or batch/posts into the single publish mainline.

Only run after review approval + publish gate. Does not write from bootstrap/sample shortcuts.

发布门（review_ledger 驱动）：
- 文章 item 必须 publishable；
- discard 图片从发布 manifest/正文引用一并剔除；
- 进入 entityRefs 的实体必须有主页（entities/{d}/{t}/{name}/page.md），否则该 entityRef 被过滤；
- 任一 hard 条件不满足则跳过该 post 并报告（不静默 BLOCK 全量）。

用法:
  python3 scripts/publish_ops/promote_to_publish.py --release-id 校园冷启动_r1
  python3 scripts/publish_ops/promote_to_publish.py --task <task> --batch <batch>
  python3 scripts/publish_ops/promote_to_publish.py --release-id 校园冷启动_r1 --dry-run
"""
from __future__ import annotations


import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common.article_package import infer_format_angle  # noqa: E402
from _common.entity_object import collect_task_entity_objects
from _common.paths import (  # noqa: E402
    PUBLISH_ROOT,
    batch_root,
    now_iso,
    publish_data,
    publish_meta_path,
    release_root,
    task_root,
)
from _common.publish_quality import (  # noqa: E402
    collect_entity_quality_evidence,
    quality_rank_key,
    read_published_entity_quality,
    should_replace_published_entity,
    write_entity_quality_into_manifest,
)

# 内容对象根的过程阶段目录（证据链）不进发布包，只拷成品。
_PROCESS_STAGE_DIRS = {"1.download", "2.quality", "3.compose", "3.brief", "3.build", "4.draft", "5.review"}
from _common.publish_filter import apply_publish_filter  # noqa: E402
from publish_ops.build_publish_lookup_indexes import build_publish_lookup_indexes  # noqa: E402


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
    """拷成品到发布面：排除内容对象根的过程阶段目录（证据链不进发布包）。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=lambda _dir, names: [n for n in names if n in _PROCESS_STAGE_DIRS],
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest_published_at(manifest_path: Path) -> str | None:
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = str(manifest.get("publishedAt") or "").strip()
    return value or None


def _load_existing_published_at(
    pd_root: Path,
    content_type: str,
    angle: str,
    title: str,
    seq: int,
) -> str | None:
    direct = _manifest_published_at(_publish_post_dir(pd_root, content_type, angle, title, seq) / "manifest.json")
    if direct:
        return direct
    type_root = pd_root / "posts" / content_type
    if not type_root.is_dir():
        return None
    for angle_dir in type_root.iterdir():
        if not angle_dir.is_dir():
            continue
        published_at = _manifest_published_at(angle_dir / title / str(seq) / "manifest.json")
        if published_at:
            return published_at
    return None


def _resolve_publish_target(manifest: dict, src_name: str) -> tuple[str, str, str, int]:
    layout = manifest.get("publishLayout", "travel")
    angle = manifest.get("publishAngle") or infer_format_angle(manifest.get("tagRefs", []))
    title = manifest.get("publishTitle") or src_name
    seq = int(manifest.get("publishSeq", 1))
    manifest_type = str(manifest.get("contentType") or manifest.get("carrier") or "").strip()

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

    if manifest_type in ("image", "gallery"):
        return "image", angle, title, seq

    if not manifest.get("publishTitle"):
        entity_refs = manifest.get("entityRefs", [])
        if entity_refs:
            entity_name = entity_refs[0].strip("/").split("/")[-1]
            title = f"{entity_name}{angle}指南"
    return "article", angle, title, seq


def _is_promotable_post_package(topic_dir: Path, manifest: dict) -> bool:
    if (topic_dir / "article.md").exists() or (topic_dir / "gallery.md").exists():
        return True
    return str(manifest.get("contentType") or manifest.get("carrier") or "") in ("image", "gallery")


def promote_from_posts_root(posts_root: Path, dry_run: bool) -> tuple[int, int]:
    if not posts_root.exists():
        print(f"[promote] No posts at {posts_root}")
        return 0, 0

    pd = publish_data()
    count = 0
    skipped = 0
    # 以 manifest.json 为锚定位 post 包：只接受对象树下的真实 post 包。
    for manifest_path in sorted(posts_root.rglob("manifest.json")):
        topic_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # 只接受真正的 post 包（含正文），排除 review/ 等 sidecar 子目录。
        if not _is_promotable_post_package(topic_dir, manifest):
            continue
        rel = topic_dir.relative_to(posts_root)
        content_type = rel.parts[0] if rel.parts else "article"
        if manifest.get("reviewDecision") not in (None, "approved"):
            print(f"[promote] SKIP (not approved): {rel}")
            skipped += 1
            continue

        # 发布门：账本发布态 + 实体主页存在性。返回过滤后的 post 内容或 None（不可发布）。
        verdict = apply_publish_filter(topic_dir, pd.root)
        if not verdict.publishable:
            print(f"[promote] SKIP (publish gate): {rel} :: {verdict.reasons}")
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
            published_at = _load_existing_published_at(
                pd.root,
                resolved_type or content_type,
                angle,
                title,
                seq,
            ) or _now_iso()
            _remove_stale_publish_post(pd.root, resolved_type or content_type, title, seq, angle)
            _copy_post_tree(topic_dir, dst)
            verdict.manifest["publishedAt"] = published_at
            verdict.write_into(dst)
        count += 1

    return count, skipped


# 一次 promote 运行内累计的对比门判定，收尾统一落盘 publish_compare 证据。
_COMPARE_DECISIONS: list[dict] = []


def _copy_entity_into_publish(entity_dir: Path, target: Path, quality: dict) -> None:
    """拷贝实体成品进 publish 并沉淀 quality 节（对比门放行之后调用）。"""
    target.mkdir(parents=True, exist_ok=True)
    for fname in ("_entity.json", "page.md", "manifest.json"):
        src_f = entity_dir / fname
        if src_f.exists():
            shutil.copy2(src_f, target / fname)
    src_assets = entity_dir / "assets"
    dst_assets = target / "assets"
    if src_assets.is_dir():
        if dst_assets.exists():
            shutil.rmtree(dst_assets)
        shutil.copytree(src_assets, dst_assets)
    elif dst_assets.exists():
        shutil.rmtree(dst_assets)
    write_entity_quality_into_manifest(target, quality)


def _entity_compare_verdict(entity_rel: str, target: Path, new_quality: dict) -> tuple[bool, dict]:
    """对比替换门：目标已发布时，新版不劣才覆盖（mandatory 同一通道，无旁路）。"""
    existing_published = (target / "page.md").is_file() or (target / "_entity.json").is_file()
    old_quality = read_published_entity_quality(target) if existing_published else None
    replace = True if not existing_published else should_replace_published_entity(new_quality, old_quality)
    record = {
        "entity": entity_rel,
        "decision": ("new" if not existing_published else ("replace" if replace else "skip_inferior")),
        "newQualityKey": list(quality_rank_key(new_quality)),
        "oldQualityKey": list(quality_rank_key(old_quality)) if existing_published else None,
        "newQuality": new_quality,
        "oldQuality": old_quality,
    }
    _COMPARE_DECISIONS.append(record)
    return replace, record


def _flush_compare_report(source_label: str) -> Path | None:
    if not _COMPARE_DECISIONS:
        return None
    out_dir = PUBLISH_ROOT / "publish_compare"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{stamp}_{source_label}.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "quwoquan_data.publish_compare_report/1",
                "source": source_label,
                "generatedAt": _now_iso(),
                "decisions": _COMPARE_DECISIONS,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _promote_entities_from_root(entities_root: Path, dry_run: bool) -> int:
    if not entities_root.is_dir():
        return 0
    dst = publish_data().entities_dir()
    count = 0
    seen: set[Path] = set()
    for marker in ("_entity.json", "page.md"):
        for marker_path in sorted(entities_root.rglob(marker)):
            entity_dir = marker_path.parent
            if entity_dir in seen:
                continue
            seen.add(entity_dir)
            rel = entity_dir.relative_to(entities_root)
            target = dst / rel
            new_quality = collect_entity_quality_evidence(entity_dir)
            replace, record = _entity_compare_verdict(rel.as_posix(), target, new_quality)
            if not replace:
                print(
                    f"[promote] SKIP (publish compare: inferior to published): entities/{rel.as_posix()} "
                    f"new={record['newQualityKey']} old={record['oldQualityKey']}"
                )
                continue
            if dry_run:
                print(f"[promote] would copy release entity entities/{rel.as_posix()}")
            else:
                _copy_entity_into_publish(entity_dir, target, new_quality)
            count += 1
    return count


def promote_release(release_id: str, dry_run: bool) -> tuple[int, int, int]:
    """返回 (post_count, skipped, entity_count)。

    homepage-only release 包只有 entities 没有 posts；entity_count 必须回传给
    调用方计入有效晋升，否则 ship 会把实体主页发布误判为 nothing promoted。
    """
    root = release_root(release_id)
    print(f"[promote] From release: {root}")
    entity_count = _promote_entities_from_root(root / "entities", dry_run)
    if entity_count:
        print(f"[promote] release entities={entity_count}")
    post_count, skipped = promote_from_posts_root(root / "posts", dry_run)
    return post_count, skipped, entity_count


def promote_task_batch(task_id: str, batch_id: str, dry_run: bool) -> tuple[int, int]:
    posts = batch_root(task_id, batch_id) / "posts"
    print(f"[promote] From task batch: {posts}")
    return promote_from_posts_root(posts, dry_run)


def _dedup_ledger_task_id(task_id: str) -> str:
    """跨批去重账本维度：优先 spec.sourceTaskId（跨生产 task 全局），退回 task_id。"""
    try:
        from task import store

        source_task = str(store.load_spec(task_id).get("sourceTaskId") or "").strip()
        if source_task:
            return source_task
    except Exception:  # noqa: BLE001 - 账本回写不阻断 promote 主流程。
        pass
    return task_id


def promote_task_entities(task_id: str, dry_run: bool) -> int:
    """Copy batch entity objects into the publish mainline.

    batch object 是主页真相源；task/entities 仅作兼容镜像，不得优先于 batch。
    采纳成功的实体回写 dedup_ledger.completedEntities（select-targets 跨批防重复消费）。
    """
    from _common.batch_manifest import load_batch_manifest
    from _common.dedup import mark_entity_done

    dst = publish_data().entities_dir()
    ledger_task_id = _dedup_ledger_task_id(task_id)
    count = 0
    for row in collect_task_entity_objects(
        task_id,
        include_task_mirror_fallback=True,
        approved_only=True,
        enforce_type_consistency=True,
    ):
        src_dir = Path(row["entityDir"])
        rel = Path(str(row["entityRel"]))
        target = dst / rel.relative_to("entities")
        batch_id = str(row.get("batchId") or "")
        generated_at = ""
        if batch_id:
            generated_at = str(load_batch_manifest(task_id, batch_id).get("createdAt") or "")
        new_quality = collect_entity_quality_evidence(
            src_dir,
            source_task_id=task_id,
            source_batch_id=batch_id,
            generated_at=generated_at,
        )
        replace, record = _entity_compare_verdict(
            rel.relative_to("entities").as_posix(), target, new_quality
        )
        entity_name = rel.name.strip()
        if not replace:
            print(
                f"[promote] SKIP (publish compare: inferior to published): {rel} "
                f"new={record['newQualityKey']} old={record['oldQualityKey']}"
            )
            # 已生产完成但劣于已发布版本：仍记 dedup done，防止重复生产同一实体。
            if not dry_run and entity_name:
                mark_entity_done(ledger_task_id, entity_name)
            continue
        if dry_run:
            print(f"[promote] would copy entity {rel}")
        else:
            new_quality["promotedAt"] = _now_iso()
            _copy_entity_into_publish(src_dir, target, new_quality)
            if entity_name:
                mark_entity_done(ledger_task_id, entity_name)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote release/task posts to the publish mainline")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--release-id", help="Assembled release id under release/")
    src.add_argument("--task", help="Task id under local/data-runtime/tasks/")
    parser.add_argument("--batch", help="Batch id (required with --task)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--copy-entities", action="store_true", help="With --task, also copy entities/")
    args = parser.parse_args()

    if args.task and not args.batch:
        parser.error("--batch is required when using --task")

    PUBLISH_ROOT.mkdir(parents=True, exist_ok=True)

    if args.release_id:
        post_count, skipped, _entity_count = promote_release(args.release_id, args.dry_run)
    else:
        post_count, skipped = promote_task_batch(args.task, args.batch, args.dry_run)
        if args.copy_entities:
            promote_task_entities(args.task, args.dry_run)

    print(f"[promote] Posts promoted: {post_count} (skipped: {skipped})")

    if not args.dry_run:
        report_path = _flush_compare_report(
            args.release_id or f"{args.task}__{args.batch}".replace("/", "_")
        )
        if report_path:
            print(f"[promote] publish compare report: {report_path}")

    if post_count == 0:
        sys.exit(1)

    if args.dry_run:
        return

    meta = {
        "schemaVersion": "quwoquan.publish.meta",
        "publishedAt": now_iso(),
        "lastPromote": now_iso(),
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
