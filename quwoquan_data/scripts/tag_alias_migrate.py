"""标签别名迁移：旧标签路径 → 新标签路径

当标签改名/合并/层级调整时，需要：
1. 将所有 entity/post 中引用旧路径的 tagRef 更新为新路径
2. 将旧标签的 aliases 合并到新标签
3. 记录迁移日志到 tag_runtime/legacy_aliases.ndjson

用法:
  python3 tag_alias_migrate.py --from "Topic/场景/温泉" --to "Topic/场景/生活场景/温泉泡汤"
  python3 tag_alias_migrate.py --batch tag_runtime/migration_batch.json
  python3 tag_alias_migrate.py --dry-run --from "old/path" --to "new/path"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, RUNTIME_ROOT, NOW_ISO

V1_ROOT = PUBLISH_ROOT / "v1"
TAGS_ROOT = V1_ROOT / "tags"
RUNTIME_TAG_DIR = RUNTIME_ROOT / "tag_runtime"
ALIASES_LOG = RUNTIME_TAG_DIR / "legacy_aliases.ndjson"


def migrate_refs_in_file(filepath: Path, old_ref: str, new_ref: str, dry_run: bool) -> int:
    """替换 JSON 文件中 tagRefs/geoTagRef 里的旧路径。返回替换次数。"""
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except Exception:
        return 0

    count = 0
    changed = False

    if "tagRefs" in data and isinstance(data["tagRefs"], list):
        new_refs = []
        for ref in data["tagRefs"]:
            if ref == old_ref:
                new_refs.append(new_ref)
                count += 1
                changed = True
            else:
                new_refs.append(ref)
        data["tagRefs"] = new_refs

    if data.get("geoTagRef") == old_ref:
        data["geoTagRef"] = new_ref
        count += 1
        changed = True

    if changed and not dry_run:
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

    return count


def migrate_single(old_ref: str, new_ref: str, dry_run: bool) -> dict:
    """执行单对迁移，返回统计。"""
    stats = {"old": old_ref, "new": new_ref, "files_changed": 0, "refs_changed": 0}

    old_def = TAGS_ROOT / old_ref / "_definition.json"
    new_def = TAGS_ROOT / new_ref / "_definition.json"

    if not new_def.exists():
        print(f"  警告: 目标标签不存在 {new_ref}，跳过")
        return stats

    # 合并 aliases
    if old_def.exists() and not dry_run:
        old_data = json.loads(old_def.read_text(encoding="utf-8"))
        new_data = json.loads(new_def.read_text(encoding="utf-8"))
        old_aliases = set(old_data.get("aliases", []))
        old_aliases.add(old_data.get("label", ""))
        new_aliases = set(new_data.get("aliases", []))
        new_aliases.update(old_aliases)
        new_aliases.discard(new_data.get("label", ""))
        new_data["aliases"] = sorted(new_aliases)
        new_data["updatedAt"] = NOW_ISO
        new_def.write_text(
            json.dumps(new_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

    # 扫描并替换所有引用
    for pattern in ["manifest.json", "_entity.json"]:
        for f in V1_ROOT.rglob(pattern):
            n = migrate_refs_in_file(f, old_ref, new_ref, dry_run)
            if n > 0:
                stats["files_changed"] += 1
                stats["refs_changed"] += n

    return stats


def main():
    parser = argparse.ArgumentParser(description="标签别名迁移")
    parser.add_argument("--from", dest="from_ref", help="旧标签路径")
    parser.add_argument("--to", dest="to_ref", help="新标签路径")
    parser.add_argument("--batch", help="批量迁移文件（JSON 数组 [{from, to}]）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pairs: list[tuple[str, str]] = []
    if args.batch:
        batch_data = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        for item in batch_data:
            pairs.append((item["from"], item["to"]))
    elif args.from_ref and args.to_ref:
        pairs.append((args.from_ref, args.to_ref))
    else:
        print("必须指定 --from/--to 或 --batch")
        sys.exit(1)

    all_stats: list[dict] = []
    for old_ref, new_ref in pairs:
        print(f"迁移: {old_ref} → {new_ref}")
        stats = migrate_single(old_ref, new_ref, args.dry_run)
        all_stats.append(stats)
        print(f"  替换 {stats['refs_changed']} 处引用，涉及 {stats['files_changed']} 个文件")

    if not args.dry_run and all_stats:
        RUNTIME_TAG_DIR.mkdir(parents=True, exist_ok=True)
        with open(ALIASES_LOG, "a", encoding="utf-8") as f:
            for s in all_stats:
                s["migratedAt"] = NOW_ISO
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"迁移日志已追加到: {ALIASES_LOG}")

    if args.dry_run:
        print("[dry-run 模式]")

    total = sum(s["refs_changed"] for s in all_stats)
    print(f"\n总计: {len(pairs)} 对迁移, {total} 处引用替换")


if __name__ == "__main__":
    main()
