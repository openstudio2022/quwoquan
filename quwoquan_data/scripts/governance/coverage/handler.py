"""qwq-data vertical — 垂类规模化治理入口。"""
from __future__ import annotations

import argparse
import json

from content.source.fetch_text import SUPPORTED_TEXT_EXTRACTORS
from governance.coverage.benchmark import evaluate_benchmark, render_benchmark, write_benchmark_report
from governance.coverage.vertical_inventory import (
    evaluate_vertical_inventory,
    list_verticals,
    render_inventory_report,
)
from governance.coverage.governance import verify_vertical_script_governance
from governance.coverage.maturity import evaluate_maturity, render_maturity
from governance.coverage.quality import verify_vertical_quality
from governance.coverage.source_registry import verify_travel_source_registry
from core.runtime_policy import active_runtime_policy


def handle_coverage_inventory(args: argparse.Namespace) -> None:
    verticals = [args.vertical] if args.vertical else list_verticals()
    reports = [evaluate_vertical_inventory(v) for v in verticals]
    for report in reports:
        print(render_inventory_report(report))
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


def handle_entity_catalog(args: argparse.Namespace) -> None:
    from governance.coverage.admin_entity_catalog import (
        admin_entity_catalog_report,
    )

    report = admin_entity_catalog_report(provinces=_provinces_arg(args) or None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    blocking = {
        "missingTaxonomyPaths": report["missingTaxonomyPaths"],
        "duplicateCanonicalIdentities": report["duplicateCanonicalIdentities"],
        "duplicateCanonicalEntityRefs": report["duplicateCanonicalEntityRefs"],
    }
    if any(blocking.values()):
        raise SystemExit(
            "[governance coverage entity-catalog] GATE_BLOCK: "
            f"行政实体 catalog 未闭合；{blocking}"
        )


def handle_coverage_discover(args: argparse.Namespace) -> None:
    from pathlib import Path

    from governance.coverage.discovery import discover_candidates
    from governance.coverage.coverage_matrix import (
        CoverageMatrixGuardrails,
        completed_discovery_shards,
        coverage_matrix_status,
        prepare_coverage_matrix,
    )
    from governance.coverage.coverage_finalize import finalize_discovery_source_cells

    provinces = _provinces_arg(args)
    if not provinces:
        print("[vertical coverage-discover] ERROR: 需要 --provinces 省份列表（逗号分隔）")
        raise SystemExit(2)
    sources = [
        s.strip()
        for s in str(
            args.sources
            or "wiki_category,wikidata_geo,osm_poi,baidu_baike_search,"
            "toutiao_baike_search"
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
    run_dir = Path(str(matrix_report["runDir"]))
    seed_candidates: list[dict[str, object]] = []
    for candidate_file in sorted(run_dir.glob("candidates_*.ndjson")):
        with candidate_file.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                candidate = row.get("candidate") if isinstance(row, dict) else None
                if isinstance(candidate, dict):
                    seed_candidates.append(candidate)
    skip_shards = (
        completed_discovery_shards(run_dir=run_dir, sources=sources)
        if args.resume
        else set()
    )
    incrementally_finalized_sources: set[str] = (
        {"osm_poi"} & set(sources)
        if args.until_saturated
        else set()
    )

    def record_shard_progress(
        source: str,
        province: str,
        city: str,
        district: str,
        candidates: list[dict[str, object]],
        failure_reason: str | None,
    ) -> None:
        finalize_discovery_source_cells(
            run_dir=run_dir,
            source=source,
            candidates=candidates,
            failed_districts=(
                [f"{city}/{district}:{failure_reason}"]
                if failure_reason
                else None
            ),
            province_filter=province,
            city_filter=city,
            district_filter=district,
            retry_only=bool(args.resume),
        )
    discovery_report = discover_candidates(
        provinces,
        sources=sources,
        cities=cities or None,
        # --limit 是每省安全池下限，不是“来源已耗尽”的上限。只有非饱和
        # 探针可在达到下限后提前停；--until-saturated 必须让 adapter 自然耗尽。
        limit=None if args.until_saturated else int(args.limit),
        out_dir=run_dir / "source-pages",
        seed_candidates=seed_candidates if args.resume else None,
        skip_shards=skip_shards if args.resume else None,
        shard_progress=record_shard_progress if args.until_saturated else None,
    )
    unique_counts = discovery_report.get("uniqueCounts") or {}
    below_minimum = {
        province: {
            "required": int(args.limit),
            "actual": int(unique_counts.get(province) or 0),
        }
        for province in provinces
        if int(unique_counts.get(province) or 0) < int(args.limit)
    }
    source_finalization: list[dict[str, object]] = []
    if args.until_saturated:
        candidates: list[dict[str, object]] = []
        for candidate_file in discovery_report.get("files") or []:
            with Path(str(candidate_file)).open(encoding="utf-8") as fh:
                candidates.extend(
                    json.loads(line)
                    for line in fh
                    if line.strip()
                )
        gaps_by_source: dict[str, list[dict[str, object]]] = {}
        for gap in discovery_report.get("sourceGaps") or []:
            gaps_by_source.setdefault(str(gap.get("source") or ""), []).append(gap)
        for source in sources:
            if source in incrementally_finalized_sources:
                continue
            source_gaps = gaps_by_source.get(source) or []
            failed_districts = [
                str(item)
                for gap in source_gaps
                for item in (gap.get("failedDistricts") or [])
            ]
            non_shard_gap = next(
                (
                    str(gap.get("reason") or "source_driver_blocked")
                    for gap in source_gaps
                    if not gap.get("failedDistricts")
                ),
                None,
            )
            source_finalization.append(
                finalize_discovery_source_cells(
                    run_dir=run_dir,
                    source=source,
                    candidates=candidates,
                    failed_districts=failed_districts,
                    blocked_reason=non_shard_gap,
                )
            )
        matrix_report["status"] = coverage_matrix_status(
            run_dir=run_dir
        )
    report = {
        "schema": "quwoquan_data.coverage_discovery_run",
        "minimumTarget": int(args.limit),
        "minimumTargetReached": not below_minimum,
        "belowMinimum": below_minimum,
        "untilSaturated": bool(args.until_saturated),
        "matrix": matrix_report,
        "discovery": discovery_report,
        "sourceFinalization": source_finalization,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if below_minimum:
        raise SystemExit(
            "[governance coverage discover] GATE_BLOCK: 每省唯一候选安全池未达到 --limit；"
            f"{below_minimum}"
        )
    unresolved_source_gaps = [
        gap
        for gap in (discovery_report.get("sourceGaps") or [])
        if str(gap.get("status") or "") != "typed_blocked"
    ]
    if unresolved_source_gaps:
        raise SystemExit(
            "[governance coverage discover] GATE_BLOCK: 存在未收口或部分失败的来源驱动；"
            "候选已保留，但不得宣称来源矩阵完成；"
            f"{unresolved_source_gaps}"
        )
    if args.until_saturated:
        status = matrix_report.get("status") or {}
        incomplete = {
            province: province_status
            for province, province_status in (status.get("provinces") or {}).items()
            if not bool(province_status.get("allCellsTerminal"))
        }
        if incomplete:
            raise SystemExit(
                "[governance coverage discover] GATE_BLOCK: --until-saturated 的矩阵仍有"
                "非终态 cell；资源运行完成不得冒充来源饱和"
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


def handle_coverage_source_ready(args: argparse.Namespace) -> None:
    from pathlib import Path

    from governance.coverage.source_readiness import (
        SourceReadinessTargetError,
        qualify_source_ready_candidates,
    )

    provinces = _provinces_arg(args)
    if not provinces:
        raise SystemExit(
            "[governance coverage source-ready] GATE_BLOCK: 需要 --provinces"
        )
    candidate_files = [
        Path(item.strip())
        for item in str(args.candidates or "").split(",")
        if item.strip()
    ]
    required_entity_refs = list(
        getattr(args, "required_entity_ref", None) or []
    )
    if (
        not candidate_files
        and not args.include_master_list
        and not required_entity_refs
    ):
        raise SystemExit(
            "[governance coverage source-ready] GATE_BLOCK: "
            "需要 --candidates、--include-master-list 或 --required-entity-ref"
        )
    try:
        report = qualify_source_ready_candidates(
            run_id=str(args.run_id),
            provinces=provinces,
            candidate_files=candidate_files,
            sources=[
                item.strip()
                for item in str(args.sources or "").split(",")
                if item.strip()
            ],
            minimum_per_province=int(args.minimum_per_province),
            max_concurrent_workers=int(args.max_concurrent_workers),
            include_master_list=bool(args.include_master_list),
            exhaust_input=bool(args.exhaust_input),
            resume=bool(args.resume),
            required_entity_refs=required_entity_refs,
        )
    except SourceReadinessTargetError as exc:
        raise SystemExit(
            "[governance coverage source-ready] GATE_BLOCK: " + str(exc)
        ) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("decision") != "GO":
        missing_required = report.get("missingRequiredEntityRefs") or []
        if missing_required:
            raise SystemExit(
                "[governance coverage source-ready] GATE_BLOCK: "
                "DATA.SOURCE.POOL_SHORTFALL: exact required refs were not frozen; "
                f"{missing_required}"
            )
        raise SystemExit(
            "[governance coverage source-ready] GATE_BLOCK: "
            f"每省来源就绪下限未满足；{report.get('belowMinimum')}"
        )


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
    reports = [evaluate_vertical_inventory(v) for v in list_verticals()]
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
    if not targets:
        raise SystemExit("[governance benchmark] GATE_BLOCK --targets is required")
    report = evaluate_benchmark(targets)
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
    if command == "entity-catalog":
        handle_entity_catalog(args)
        return
    if command == "discover":
        handle_coverage_discover(args)
        return
    if command == "merge":
        handle_coverage_merge(args)
        return
    if command == "source-ready":
        handle_coverage_source_ready(args)
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

    pec = sub.add_parser(
        "entity-catalog",
        help="全国行政实体 catalog coverage（直接消费 pca + taxonomy）",
    )
    pec.add_argument("--provinces", help="省份列表（逗号分隔）；缺省=全国")
    pec.set_defaults(handler=handle_entity_catalog)

    pcd = sub.add_parser(
        "discover",
        help="市州分片 coverage 矩阵：区县×10类×五来源 checkpoint（发现只写 runtime）",
    )
    pcd.add_argument("--provinces", required=True, help="省份列表（逗号分隔）")
    pcd.add_argument(
        "--sources",
        default=(
            "wiki_category,wikidata_geo,osm_poi,baidu_baike_search,"
            "toutiao_baike_search"
        ),
        help="来源列表（默认五路 discovery source）",
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

    pcs = sub.add_parser(
        "source-ready",
        help="以三百科闭集逐对象预筛来源资格，并按省冻结可恢复证据",
    )
    pcs.add_argument("--provinces", required=True, help="省份列表（逗号分隔）")
    pcs.add_argument("--candidates", help="发现候选 NDJSON 文件列表（逗号分隔）")
    pcs.add_argument(
        "--sources",
        default="wikipedia,toutiao_baike,baidu_baike",
        help="三百科解析顺序（逗号分隔）",
    )
    pcs.add_argument(
        "--minimum-per-province",
        type=int,
        required=True,
        help="每省必须达到的唯一 source-ready 对象数",
    )
    pcs.add_argument(
        "--max-concurrent-workers",
        type=int,
        required=True,
        help="来源预筛任一时刻可同时运行的探测进程数上限（无默认值）",
    )
    pcs.add_argument("--run-id", required=True, help="可恢复来源预筛运行 ID")
    pcs.add_argument(
        "--include-master-list",
        action="store_true",
        help="同时纳入全国行政实体 catalog 与仓内旅游 POI master list",
    )
    pcs.add_argument(
        "--required-entity-ref",
        action="append",
        default=[],
        help=(
            "从 canonical master list 精确选择一个 /entity/<type>/<name>；"
            "可重复，按参数顺序冻结且隐含 --include-master-list/--exhaust-input"
        ),
    )
    pcs.add_argument(
        "--exhaust-input",
        action="store_true",
        help="处理完全部唯一候选后再按区县×类型轮询冻结",
    )
    pcs.add_argument("--resume", action="store_true")
    pcs.set_defaults(handler=handle_coverage_source_ready)

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

    pb = sub.add_parser("benchmark", help="输出显式请求的日产成熟度评估报告")
    pb.add_argument("--targets", required=True, help="逗号分隔的运行期日产目标")
    pb.add_argument("--report", help="写入 runtime/benchmarks/<name>.json")
    pb.add_argument("--strict", action="store_true")
    pb.add_argument("--json", action="store_true")
    pb.set_defaults(handler=handle_benchmark)

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "vertical_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=handle_coverage_command)
