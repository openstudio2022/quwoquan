"""qwq-data vertical — 垂类规模化治理入口。"""
from __future__ import annotations

import argparse
import json

from download.fetch import SUPPORTED_TEXT_EXTRACTORS
from vertical.benchmark import evaluate_benchmark, render_benchmark, write_benchmark_report
from vertical.coverage import evaluate_registry, list_verticals, render_report
from vertical.governance import verify_vertical_script_governance
from vertical.maturity import evaluate_maturity, render_maturity
from vertical.quality import verify_vertical_quality
from vertical.source_registry import verify_travel_source_registry


def handle_campus_bootstrap(args: argparse.Namespace) -> None:
    from verticals.campus.scripts import bootstrap_school_entities, bootstrap_school_posts

    forwarded: list[str] = []
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.resume:
        forwarded.append("--resume")
    if args.province:
        forwarded.extend(["--province", args.province])
    if args.city:
        forwarded.extend(["--city", args.city])
    if args.etype:
        forwarded.extend(["--etype", args.etype])
    if args.target in ("entities", "all"):
        bootstrap_school_entities.main(forwarded)
    post_args: list[str] = []
    if args.dry_run:
        post_args.append("--dry-run")
    if args.resume:
        post_args.append("--resume")
    if args.skip_reindex:
        post_args.append("--skip-reindex")
    if args.target in ("posts", "all"):
        bootstrap_school_posts.main(post_args)


def handle_coverage(args: argparse.Namespace) -> None:
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
    from _common.coverage_master_list import master_list_stats

    stats = master_list_stats(provinces=_provinces_arg(args) or None)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def handle_master_list_probe(args: argparse.Namespace) -> None:
    from vertical.master_list_probe import probe_master_list_sources

    provinces = _provinces_arg(args)
    if not provinces:
        print("[vertical master-list-probe] ERROR: 需要 --provinces 省份列表（逗号分隔）")
        raise SystemExit(2)
    report = probe_master_list_sources(
        provinces=provinces,
        limit=int(getattr(args, "limit", 0) or 0),
        sleep_seconds=float(getattr(args, "sleep_seconds", 0.5) or 0.0),
        recheck=bool(getattr(args, "recheck", False)),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_governance(args: argparse.Namespace) -> None:
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


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("vertical", help="垂类规模化治理：coverage / scripts / maturity")
    sub = p.add_subparsers(dest="vertical_command")

    pc = sub.add_parser("coverage", help="输出旅行/摄影/校园 coverage 缺口")
    pc.add_argument("--vertical", choices=["travel", "photography", "campus"])
    pc.add_argument("--json", action="store_true")
    pc.add_argument("--strict", action="store_true", help="存在 gap 时失败")
    pc.set_defaults(handler=handle_coverage)

    pms = sub.add_parser("master-list-stats", help="全国地点主清单统计（规模/类型/源就绪/跨省）")
    pms.add_argument("--provinces", help="省份列表（逗号分隔）；缺省=全部")
    pms.set_defaults(handler=handle_master_list_stats)

    pmp = sub.add_parser(
        "master-list-probe-sources",
        help="源可用性预筛：轻量探测百科主源有无并回填 sourceReadiness（节流+断点续跑）",
    )
    pmp.add_argument("--provinces", required=True, help="省份列表（逗号分隔，如 四川省,浙江省）")
    pmp.add_argument("--limit", type=int, default=0, help="本次最多探测叶子数（0=不限，配合断点续跑）")
    pmp.add_argument("--sleep-seconds", dest="sleep_seconds", type=float, default=0.5, help="请求间节流秒数")
    pmp.add_argument("--recheck", action="store_true", help="重探已 ready/no_primary_source 的叶子")
    pmp.set_defaults(handler=handle_master_list_probe)

    pg = sub.add_parser("governance", help="校验垂类/任务脚本未在公共 scripts 平铺")
    pg.set_defaults(handler=handle_governance)

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

    pcb = sub.add_parser("campus-bootstrap", help="校园垂类批量生成实体/posts")
    pcb.add_argument("--target", choices=["entities", "posts", "all"], default="all")
    pcb.add_argument("--dry-run", action="store_true")
    pcb.add_argument("--resume", action="store_true")
    pcb.add_argument("--province")
    pcb.add_argument("--city")
    pcb.add_argument("--etype")
    pcb.add_argument("--skip-reindex", action="store_true")
    pcb.set_defaults(handler=handle_campus_bootstrap)

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "vertical_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)
