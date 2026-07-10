"""qwq-data quality — 数据质量治理入口。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common.io import write_json
from _common.paths import NOW_ISO, RUNTIME_ROOT
from quality.dirty_data import delete_dirty_data, scan_dirty_data, write_dirty_report
from quality.entity_tag_backfill import (
    apply_backfill,
    load_backfill_map,
    plan_backfill,
    plan_summary,
)


def handle_entity_tag_backfill(args: argparse.Namespace) -> None:
    """存量实体标签回填：dry-run 输出计划；--apply 写回并强制重建 lookup 索引。"""
    rows = load_backfill_map(Path(args.map))
    plan = plan_backfill(rows)
    summary = plan_summary(plan)
    if not plan.ok:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(
            f"[quality backfill-entity-tags] dry-run changed={summary['changedCount']} "
            f"unchanged={summary['unchangedCount']}（--apply 写回并重建索引）"
        )
        return
    applied = apply_backfill(plan)
    # 「不许手改后不重建索引」：apply 与索引重建在同一通路内强制串联。
    from publish_ops.build_publish_lookup_indexes import build_publish_lookup_indexes

    index_counts = build_publish_lookup_indexes()
    report_path = Path(args.report or (RUNTIME_ROOT / "reports" / "entity_tag_backfill_report.json"))
    write_json(
        report_path,
        {
            "schemaVersion": "quwoquan_data.entity_tag_backfill_report/1",
            "mapPath": str(args.map),
            "appliedCount": len(applied),
            "unchangedCount": summary["unchangedCount"],
            "applied": applied,
            "indexCounts": index_counts,
            "generatedAt": NOW_ISO,
        },
    )
    print(
        f"[quality backfill-entity-tags] applied={len(applied)} "
        f"index={index_counts} report={report_path}"
    )


def handle_dirty_scan(args: argparse.Namespace) -> None:
    rows = scan_dirty_data()
    deleted = delete_dirty_data(rows) if args.delete else []
    # 运行期报告落仓外输出根（数据输出规范：仓内不再接收生成输出）。
    report_path = Path(args.report or (RUNTIME_ROOT / "reports" / "dirty_data_report.json"))
    write_dirty_report(report_path, rows, deleted)
    print(f"[quality dirty-scan] issues={len(rows)} deleted={len(deleted)} report={report_path}")
    if rows and args.fail_on_issues and not args.delete:
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("quality", help="数据质量治理：dirty-scan / backfill-entity-tags")
    sub = p.add_subparsers(dest="quality_command")

    pd = sub.add_parser("dirty-scan", help="扫描/删除历史脏实体主页和 post 包")
    pd.add_argument("--delete", action="store_true", help="删除脏 page.md/manifest/assets 或 post package")
    pd.add_argument("--report")
    pd.add_argument("--fail-on-issues", action="store_true")
    pd.set_defaults(handler=handle_dirty_scan)

    pb = sub.add_parser(
        "backfill-entity-tags",
        help="存量 publish 实体回填 geoTagRef/类型 tagRefs（apply 强制重建 lookup 索引）",
    )
    pb.add_argument("--map", required=True, help="受版本控制的回填映射 yaml")
    pb.add_argument("--apply", action="store_true", help="写回 _entity.json 并重建索引（缺省 dry-run）")
    pb.add_argument("--report", help="回填报告输出路径（默认 .qwq_output/data/runs/ 下）")
    pb.set_defaults(handler=handle_entity_tag_backfill)

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "quality_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)
