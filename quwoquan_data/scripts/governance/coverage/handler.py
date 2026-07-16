"""qwq-data vertical — 垂类规模化治理入口。"""
from __future__ import annotations

import argparse
import json

from content.source.fetch_text import SUPPORTED_TEXT_EXTRACTORS
from governance.coverage.benchmark import evaluate_benchmark, render_benchmark, write_benchmark_report
from governance.coverage.coverage import evaluate_registry, list_verticals, render_report
from governance.coverage.governance import verify_vertical_script_governance
from governance.coverage.maturity import evaluate_maturity, render_maturity
from governance.coverage.quality import verify_vertical_quality
from governance.coverage.source_registry import verify_travel_source_registry
from core.runtime_policy import active_runtime_policy


def handle_coverage_inventory(args: argparse.Namespace) -> None:
    verticals = [args.vertical] if args.vertical else list_verticals()
    reports = [evaluate_registry(v) for v in verticals]
    for report in reports:
        print(render_report(report))
    if args.json:
        print(json.dumps({"reports": reports}, ensure_ascii=False, indent=2))
    if args.strict and any(r["status"] != "passed" for r in reports):
        raise SystemExit(1)


def _provinces_arg(args: argparse.Namespace) -> list[str]:
    return [p.strip() for p in str(getattr(args, "provinces", "") or "").split(",") if p.strip()]


def handle_master_list_stats(args: argparse.Namespace) -> None:
    from governance.coverage.master_list import master_list_stats

    stats = master_list_stats(provinces=_provinces_arg(args) or None)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def handle_coverage_discover(args: argparse.Namespace) -> None:
    from governance.coverage.coverage_matrix import (
        CoverageMatrixGuardrails,
        prepare_coverage_matrix,
    )

    provinces = _provinces_arg(args)
    if not provinces:
        print("[vertical coverage-discover] ERROR: 需要 --provinces 省份列表（逗号分隔）")
        raise SystemExit(2)
    sources = [
        s.strip()
        for s in str(
            args.sources
            or "wiki_category,wikidata_geo,osm_poi,baidu_baike_search,"
            "sogou_baike_search,toutiao_baike_search"
        ).split(",")
        if s.strip()
    ]
    cities = [c.strip() for c in str(getattr(args, "cities", "") or "").split(",") if c.strip()]
    guardrails = CoverageMatrixGuardrails.from_runtime_policy(
        active_runtime_policy(),
        safe_pool_minimum=int(args.limit),
        until_saturated=bool(args.until_saturated),
    )
    matrix_report = prepare_coverage_matrix(
        run_id=str(args.run_id),
        provinces=provinces,
        cities=cities or None,
        sources=sources,
        resume=bool(args.resume),
        guardrails=guardrails,
    )
    if args.prepare_only:
        print(json.dumps(matrix_report, ensure_ascii=False, indent=2))
        return
    raise SystemExit(
        "[vertical coverage-discover] GATE_BLOCK: 市州矩阵/checkpoint 已准备；"
        "两省 coverage 长跑仍按计划暂停，未发网络请求"
    )


def handle_coverage_merge(args: argparse.Namespace) -> None:
    from pathlib import Path

    from governance.coverage.coverage_merge import merge_candidates

    provinces = _provinces_arg(args)
    if not provinces:
        print("[vertical coverage-merge] ERROR: 需要 --provinces 省份列表（逗号分隔）")
        raise SystemExit(2)
    files = [Path(p.strip()) for p in str(args.candidates or "").split(",") if p.strip()]
    missing = [str(p) for p in files if not p.is_file()]
    if not files or missing:
        print(f"[vertical coverage-merge] ERROR: 候选文件缺失: {missing or '未提供 --candidates'}")
        raise SystemExit(2)
    report = merge_candidates(provinces, candidate_files=files, apply=bool(args.apply))
    summary = {
        k: v
        for k, v in report.items()
        if k not in ("appendedItems", "gapItems", "semanticRejectedItems")
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.apply and report.get("writtenFiles"):
        print("[vertical coverage-merge] 已写回，请跑: qwq-data verify coverage-static-identity")


def handle_coverage_governance(args: argparse.Namespace) -> None:
    issues = verify_vertical_script_governance()
    if issues:
        print("[vertical governance] FAILED")
        for issue in issues:
            print(f"  - {issue}")
        raise SystemExit(1)
    print("[vertical governance] PASSED")


def handle_quality(args: argparse.Namespace) -> None:
    issues = verify_vertical_quality()
    if issues:
        print("[vertical quality] FAILED")
        for issue in issues:
            print(f"  - {issue}")
        raise SystemExit(1)
    print("[vertical quality] PASSED")


def handle_source_registry(args: argparse.Namespace) -> None:
    issues = verify_travel_source_registry(allowed_extractors=set(SUPPORTED_TEXT_EXTRACTORS))
    if issues:
        print("[vertical source-registry] FAILED")
        for issue in issues:
            print(f"  - {issue}")
        raise SystemExit(1)
    print("[vertical source-registry] PASSED")


def handle_maturity(args: argparse.Namespace) -> None:
    reports = [evaluate_registry(v) for v in list_verticals()]
    coverage_status = "passed" if reports and all(r["status"] == "passed" for r in reports) else "gap"
    report = evaluate_maturity(
        coverage_status=coverage_status,
        has_license_policy=args.has_license_policy,
        has_worker_queue=args.has_worker_queue,
        has_post_activation=args.has_post_activation,
    )
    print(render_maturity(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and report["level"] < args.min_level:
        raise SystemExit(1)


def handle_benchmark(args: argparse.Namespace) -> None:
    targets = [int(x.strip()) for x in (args.targets or "").split(",") if x.strip()]
    report = evaluate_benchmark(targets or None)
    print(render_benchmark(report))
    if args.report:
        out = write_benchmark_report(report, name=args.report)
        print(f"[benchmark] report={out}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and any(row["status"] != "passed" for row in report["targets"]):
        raise SystemExit(1)


def handle_coverage_command(args: argparse.Namespace) -> None:
    command = getattr(args, "coverage_command", None)
    if command == "inventory":
        handle_coverage_inventory(args)
        return
    if command == "master-list-stats":
        handle_master_list_stats(args)
        return
    if command == "discover":
        handle_coverage_discover(args)
        return
    if command == "merge":
        handle_coverage_merge(args)
        return
    if command == "governance":
        handle_coverage_governance(args)
        return
    if command == "quality":
        handle_quality(args)
        return
    if command == "source-registry":
        handle_source_registry(args)
        return
    if command == "maturity":
        handle_maturity(args)
        return
    if command == "benchmark":
        handle_benchmark(args)
        return
    raise SystemExit("[governance coverage] subcommand required")


def register_coverage_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("coverage", help="Coverage governance and static catalog operations")
    sub = p.add_subparsers(dest="vertical_command")

    pc = sub.add_parser("inventory", help="输出旅行/摄影/校园 coverage 缺口")
    pc.add_argument("--vertical", choices=["travel", "photography", "campus"])
    pc.add_argument("--json", action="store_true")
    pc.add_argument("--strict", action="store_true", help="存在 gap 时失败")
    pc.set_defaults(handler=handle_coverage_inventory)

    pms = sub.add_parser("master-list-stats", help="全国地点主清单统计（规模/类型/跨省）")
    pms.add_argument("--provinces", help="省份列表（逗号分隔）；缺省=全部")
    pms.set_defaults(handler=handle_master_list_stats)

    pcd = sub.add_parser(
        "discover",
        help="市州分片 coverage 矩阵：区县×10类×六来源 checkpoint（发现只写 runtime）",
    )
    pcd.add_argument("--provinces", required=True, help="省份列表（逗号分隔）")
    pcd.add_argument(
        "--sources",
        default=(
            "wiki_category,wikidata_geo,osm_poi,baidu_baike_search,"
            "sogou_baike_search,toutiao_baike_search"
        ),
        help="来源列表（默认六路 discovery source）",
    )
    pcd.add_argument("--cities", help="市州分片过滤（逗号分隔）")
    pcd.add_argument(
        "--limit",
        type=int,
        required=True,
        help="显式给出每省安全候选池下限；不得在代码中复制 rollout 规模",
    )
    pcd.add_argument("--run-id", required=True, help="矩阵化可恢复运行 ID")
    pcd.add_argument("--resume", action="store_true", help="只继续非终态 cell")
    pcd.add_argument("--prepare-only", action="store_true", help="仅构建矩阵/checkpoint，不发网络请求")
    pcd.add_argument("--until-saturated", action="store_true")
    pcd.set_defaults(handler=handle_coverage_discover)

    pcm = sub.add_parser(
        "merge",
        help="主清单扩容·合并：去重+类型/地理打标+写回市州 YAML（缺省 dry-run，--apply 写回）",
    )
    pcm.add_argument("--provinces", required=True, help="省份列表（逗号分隔）")
    pcm.add_argument("--candidates", required=True, help="候选 NDJSON 文件列表（逗号分隔）")
    pcm.add_argument("--apply", action="store_true", help="写回市州 YAML（缺省只出报告）")
    pcm.set_defaults(handler=handle_coverage_merge)

    pg = sub.add_parser("governance", help="校验垂类/任务脚本未在公共 scripts 平铺")

    pq = sub.add_parser("quality", help="校验垂类 golden samples 与专项质量门")
    pq.set_defaults(handler=handle_quality)

    psr = sub.add_parser("source-registry", help="校验 travel source registry 与 extractor 白名单")
    psr.set_defaults(handler=handle_source_registry)

    pm = sub.add_parser("maturity", help="输出规模化成熟度评估")
    pm.add_argument("--has-license-policy", action="store_true")
    pm.add_argument("--has-worker-queue", action="store_true")
    pm.add_argument("--has-post-activation", action="store_true")
    pm.add_argument("--min-level", type=int, default=4)
    pm.add_argument("--strict", action="store_true")
    pm.add_argument("--json", action="store_true")
    pm.set_defaults(handler=handle_maturity)

    pb = sub.add_parser("benchmark", help="输出 1k/10k/100k 日产成熟度评估报告")
    pb.add_argument("--targets", help="逗号分隔日产目标，默认 1000,10000,100000")
    pb.add_argument("--report", help="写入 runtime/benchmarks/<name>.json")
    pb.add_argument("--strict", action="store_true")
    pb.add_argument("--json", action="store_true")
    pb.set_defaults(handler=handle_benchmark)

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "vertical_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=handle_coverage_command)
