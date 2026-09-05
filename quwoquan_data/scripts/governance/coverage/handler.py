"""Data 静态 coverage 治理入口；不包含生产编排。"""
from __future__ import annotations

import argparse
import json

from content.source.fetch_text import SUPPORTED_TEXT_EXTRACTORS
from governance.coverage.governance import verify_vertical_script_governance
from governance.coverage.quality import verify_vertical_quality
from governance.coverage.source_registry import verify_travel_source_registry
from governance.coverage.vertical_inventory import (
    evaluate_vertical_inventory,
    list_verticals,
    render_inventory_report,
)


def _provinces_arg(args: argparse.Namespace) -> list[str]:
    return [item.strip() for item in str(getattr(args, "provinces", "") or "").split(",") if item.strip()]


def handle_coverage_inventory(args: argparse.Namespace) -> None:
    verticals = [args.vertical] if args.vertical else list_verticals()
    reports = [evaluate_vertical_inventory(vertical) for vertical in verticals]
    for report in reports:
        print(render_inventory_report(report))
    if args.json:
        print(json.dumps({"reports": reports}, ensure_ascii=False, indent=2))
    if args.strict and any(report["status"] != "passed" for report in reports):
        raise SystemExit(1)


def handle_master_list_stats(args: argparse.Namespace) -> None:
    from governance.coverage.master_list import master_list_stats

    print(json.dumps(master_list_stats(provinces=_provinces_arg(args) or None), ensure_ascii=False, indent=2))


def handle_entity_catalog(args: argparse.Namespace) -> None:
    from governance.coverage.admin_entity_catalog import admin_entity_catalog_report

    report = admin_entity_catalog_report(provinces=_provinces_arg(args) or None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    blocking = {
        "missingTaxonomyPaths": report["missingTaxonomyPaths"],
        "duplicateCanonicalIdentities": report["duplicateCanonicalIdentities"],
        "duplicateCanonicalEntityRefs": report["duplicateCanonicalEntityRefs"],
    }
    if any(blocking.values()):
        raise SystemExit(f"[governance coverage entity-catalog] GATE_BLOCK: 行政实体 catalog 未闭合；{blocking}")


def handle_coverage_governance(_args: argparse.Namespace) -> None:
    issues = verify_vertical_script_governance()
    if issues:
        print("[vertical governance] FAILED")
        for issue in issues:
            print(f"  - {issue}")
        raise SystemExit(1)
    print("[vertical governance] PASSED")


def handle_quality(_args: argparse.Namespace) -> None:
    issues = verify_vertical_quality()
    if issues:
        print("[vertical quality] FAILED")
        for issue in issues:
            print(f"  - {issue}")
        raise SystemExit(1)
    print("[vertical quality] PASSED")


def handle_source_registry(_args: argparse.Namespace) -> None:
    issues = verify_travel_source_registry(allowed_extractors=set(SUPPORTED_TEXT_EXTRACTORS))
    if issues:
        print("[vertical source-registry] FAILED")
        for issue in issues:
            print(f"  - {issue}")
        raise SystemExit(1)
    print("[vertical source-registry] PASSED")


def handle_coverage_command(args: argparse.Namespace) -> None:
    handlers = {
        "inventory": handle_coverage_inventory,
        "master-list-stats": handle_master_list_stats,
        "entity-catalog": handle_entity_catalog,
        "governance": handle_coverage_governance,
        "quality": handle_quality,
        "source-registry": handle_source_registry,
    }
    command = getattr(args, "coverage_command", None)
    if command not in handlers:
        raise SystemExit("[governance coverage] subcommand required")
    handlers[command](args)


def register_coverage_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("coverage", help="Static coverage catalogs and governance checks")
    commands = parser.add_subparsers(dest="coverage_command", required=True)

    inventory = commands.add_parser("inventory", help="输出静态垂类 coverage 缺口")
    inventory.add_argument("--vertical", choices=["travel", "photography", "campus"])
    inventory.add_argument("--json", action="store_true")
    inventory.add_argument("--strict", action="store_true", help="存在 gap 时失败")

    master = commands.add_parser("master-list-stats", help="全国地点静态主清单统计")
    master.add_argument("--provinces", help="省份列表（逗号分隔）；缺省=全部")

    catalog = commands.add_parser("entity-catalog", help="行政实体静态 catalog coverage")
    catalog.add_argument("--provinces", help="省份列表（逗号分隔）；缺省=全国")

    commands.add_parser("governance", help="校验静态垂类脚本治理")
    commands.add_parser("quality", help="校验静态垂类 golden samples 与质量门")
    commands.add_parser("source-registry", help="校验静态 source registry 与 extractor 白名单")
    parser.set_defaults(handler=handle_coverage_command)
