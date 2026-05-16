"""一键生成全部 v5 示例数据。

用法:
  python3 scripts/sample_data/build_all.py
  python3 scripts/sample_data/build_all.py --dry-run
  python3 scripts/sample_data/build_all.py --clean  # 先清理再生成
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common.paths import RUNTIME_ROOT  # noqa: E402

from sample_data import europe_v5, sichuan_v5, thailand_v5  # noqa: E402


def clean_old_tasks():
    """清理旧版本 task 数据。"""
    tasks_root = RUNTIME_ROOT / "tasks"
    old_patterns = ["四川省全域_v4", "四川省全域_v5"]
    for pattern in old_patterns:
        old_dir = tasks_root / pattern
        if old_dir.exists():
            shutil.rmtree(old_dir)
            print(f"  已清理: {old_dir}")


def reset_task_posts_entities(task_id: str) -> None:
    """去掉上一轮生成的 posts/entities，避免遗留 seq>1 等目录导致死 tagRef。"""
    root = RUNTIME_ROOT / "tasks" / task_id
    for sub in ("posts", "entities"):
        p = root / sub
        if not p.exists() or p.is_symlink():
            continue
        shutil.rmtree(p)


def main():
    parser = argparse.ArgumentParser(description="一键生成 v5 示例数据")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clean", action="store_true", help="先清理旧数据")
    args = parser.parse_args()

    if args.clean:
        print("清理旧数据...")
        clean_old_tasks()

    print("=" * 50)
    print("生成 v5 示例数据")
    print("=" * 50)

    total_entities = 0
    total_posts = 0

    for name, mod in [
        ("四川旅行_v5", sichuan_v5),
        ("泰国旅行_v5", thailand_v5),
        ("欧洲旅行_v5", europe_v5),
    ]:
        print(f"\n--- {name} ---")
        if not args.dry_run:
            reset_task_posts_entities(mod.TASK_ID)
        ec, pc = mod.build(dry_run=args.dry_run)
        total_entities += ec
        total_posts += pc
        print(f"  实体: {ec}, Posts: {pc}")

    print(f"\n合计: {total_entities} 实体, {total_posts} posts")
    if args.dry_run:
        print("[dry-run 模式，未写盘]")


if __name__ == "__main__":
    main()
