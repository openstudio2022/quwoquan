"""标签体系统计报告（四分组版）

输出：
  - 四分组（Topic/Audience/Format/Entity）各维度标签数量
  - 最大树深度
  - 叶子/分支比例
  - 分组容量均衡分析

用法:
  python3 tag_stats.py
  python3 tag_stats.py --json           # JSON 格式输出
  python3 tag_stats.py --group Topic    # 只看某个分组
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT

TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags"
GROUPS = ["Topic", "Audience", "Format", "Entity"]


def _node_stats(root: Path) -> dict:
    """递归统计一个目录下的所有 _definition.json 节点。"""
    nodes = list(root.rglob("_definition.json"))
    leaves = 0
    branches = 0
    max_depth = 0
    for f in nodes:
        rel = f.parent.relative_to(root)
        depth = len(rel.parts)
        if depth > max_depth:
            max_depth = depth
        has_children = any(
            c.is_dir() and (c / "_definition.json").exists()
            for c in f.parent.iterdir()
            if c.is_dir()
        )
        if has_children:
            branches += 1
        else:
            leaves += 1
    return {"count": len(nodes), "leaves": leaves, "branches": branches, "max_depth": max_depth}


def collect_stats() -> dict:
    if not TAGS_ROOT.exists():
        return {"groups": {}, "total": 0, "geo": 0, "non_geo": 0,
                "max_depth": 0, "leaves": 0, "branches": 0}

    result: dict = {
        "groups": {},
        "total": 0,
        "geo": 0,
        "non_geo": 0,
        "max_depth": 0,
        "leaves": 0,
        "branches": 0,
    }

    for group_name in GROUPS:
        g_dir = TAGS_ROOT / group_name
        if not g_dir.exists():
            result["groups"][group_name] = {"dims": {}, "count": 0}
            continue

        g_info: dict = {"dims": {}, "count": 0}

        # 维度子目录（含 _dimension.json 的目录）
        dim_dirs = sorted(
            d for d in g_dir.iterdir()
            if d.is_dir() and not d.name.startswith("_")
        )
        for dim_dir in dim_dirs:
            dim_name = dim_dir.name
            stats = _node_stats(dim_dir)
            g_info["dims"][dim_name] = stats
            g_info["count"] += stats["count"]
            result["leaves"] += stats["leaves"]
            result["branches"] += stats["branches"]
            if stats["max_depth"] > result["max_depth"]:
                result["max_depth"] = stats["max_depth"]

        result["groups"][group_name] = g_info
        result["total"] += g_info["count"]

    # 地理 vs 非地理（Topic/地理 下所有）
    geo_root = TAGS_ROOT / "Topic" / "地理"
    result["geo"] = sum(1 for _ in geo_root.rglob("_definition.json")) if geo_root.exists() else 0
    result["non_geo"] = result["total"] - result["geo"]
    return result


def print_text(stats: dict, group_filter: str | None = None):
    print("=" * 65)
    print("标签体系统计报告  (Topic / Audience / Format / Entity)")
    print("=" * 65)
    print(f"\n总标签数: {stats['total']}")
    print(f"  地理维度（Topic/地理）: {stats['geo']}")
    print(f"  非地理标签: {stats['non_geo']}")
    print(f"最大树深度: {stats['max_depth']}")
    print(f"叶子节点: {stats['leaves']}, 分支节点: {stats['branches']}")

    print("\n各分组明细:")
    print("-" * 65)
    for g_name in GROUPS:
        if group_filter and g_name != group_filter:
            continue
        g_info = stats["groups"].get(g_name, {"dims": {}, "count": 0})
        g_count = g_info["count"]
        dims = g_info["dims"]
        bar_pct = int(g_count / max(stats["total"], 1) * 40)
        bar = "█" * bar_pct
        print(f"\n{g_name}  {g_count} 标签  |{bar}|")
        sorted_dims = sorted(dims.items(), key=lambda x: -x[1]["count"])
        for dim_name, dim_data in sorted_dims:
            leaf_pct = (
                f"叶{dim_data['leaves']}/"
                f"分支{dim_data['branches']}"
            )
            print(f"  {dim_name:<18} {dim_data['count']:>5} 标签  "
                  f"深度≤{dim_data['max_depth']}  {leaf_pct}")

    # 分组均衡分析
    print("\n分组容量均衡分析:")
    print("-" * 65)
    for g_name in GROUPS:
        g_info = stats["groups"].get(g_name, {"dims": {}, "count": 0})
        g_count = g_info["count"]
        dim_count = len(g_info["dims"])
        pct = g_count / max(stats["total"], 1) * 100
        status = ""
        if pct < 10:
            status = "⚠ 偏少"
        elif pct > 60:
            status = "⚠ 偏多"
        else:
            status = "✓"
        print(f"  {g_name:<10} {g_count:>5} 标签 ({pct:5.1f}%)  "
              f"{dim_count} 维度  {status}")

    # Topic/旅行 七子维度详情
    travel_dims = stats["groups"].get("Topic", {}).get("dims", {}).get("旅行", None)
    if travel_dims:
        print("\nTopic/旅行 子维度详情:")
        print("-" * 65)
        travel_root = TAGS_ROOT / "Topic" / "旅行"
        if travel_root.exists():
            for sub in sorted(travel_root.iterdir()):
                if not sub.is_dir() or sub.name.startswith("_"):
                    continue
                sub_stats = _node_stats(sub)
                print(f"  {sub.name:<14} {sub_stats['count']:>4} 标签  "
                      f"叶{sub_stats['leaves']}/分支{sub_stats['branches']}")


def main():
    parser = argparse.ArgumentParser(description="标签统计（四分组版）")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--group", choices=GROUPS, help="只统计指定分组")
    args = parser.parse_args()

    stats = collect_stats()

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print_text(stats, group_filter=args.group)


if __name__ == "__main__":
    main()
