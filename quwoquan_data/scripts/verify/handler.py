"""data verify — scoped post-package quality verification (CLI)。

`qwq-data verify [--task T --batch B] [--release R] [--scope current|all]`

收紧扫描范围：默认 current（仅当前 schema 的 posts 根），可指定 task/batch 或 release。
逻辑全部沉到 _common.post_verify，旧 verify_*.py 仅作薄壳委托本命令。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from verify.gate import gate_verify
from verify.verify_batch_stability_compare import compare_batches, write_report, write_snapshot
from ship.consistency import report_to_text, scan_release_file, write_consistency_report


def handle_verify(args: argparse.Namespace) -> None:
    cmd = getattr(args, "verify_command", None)
    if cmd == "batch-stability":
        handle_batch_stability(args)
        return
    if cmd == "rubric":
        handle_rubric(args)
        return
    if cmd == "goldenset":
        handle_goldenset(args)
        return
    if cmd == "sample-drift":
        handle_sample_drift(args)
        return
    if cmd == "promote-golden":
        handle_promote_golden(args)
        return
    if cmd == "data-role-gate":
        from verify.verify_data_role_gate_inventory import main as role_gate_main

        raise SystemExit(role_gate_main())
    if cmd == "single-contract-source":
        from verify.verify_single_contract_source import main as single_contract_source_main

        raise SystemExit(single_contract_source_main())
    if cmd == "content-supply-production":
        from verify.verify_content_supply_production import main as content_supply_gate_main

        content_supply_gate_main()
        return
    if cmd == "works-classification":
        from verify.verify_works_classification import main as works_classification_main

        raise SystemExit(works_classification_main())
    if cmd == "release-integrity":
        from _common.release_integrity import scan_release_integrity

        report = scan_release_integrity(args.release)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report.get("passed"):
            raise SystemExit(1)
        return
    if cmd == "scale-readiness":
        from verify.scale_readiness import build_scale_readiness_report, write_scale_readiness_report

        if not args.task or not args.batch:
            print("[verify scale-readiness] --task and --batch are required", file=sys.stderr)
            raise SystemExit(2)
        report = build_scale_readiness_report(
            args.task,
            args.batch,
            daily_target=int(args.daily_target),
            target_goal=int(getattr(args, "target", 0) or 0) or None,
            min_pass_rate=float(getattr(args, "min_pass_rate", 0.0) or 0.0),
            source_ready_goal=int(getattr(args, "source_ready_goal", 0) or 0) or None,
            release_id=getattr(args, "release", None),
            require_import=not bool(getattr(args, "allow_missing_import", False)),
            mode=str(getattr(args, "mode", "commercial") or "commercial"),
        )
        if getattr(args, "report_out", None):
            write_scale_readiness_report(Path(args.report_out), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report.get("passed"):
            raise SystemExit(1)
        return
    if cmd == "creator-scale-readiness":
        from governance.creator_pool.readiness import (
            build_creator_readiness_report,
            write_creator_readiness_report,
        )

        if not args.batch:
            print("[verify creator-scale-readiness] --batch is required", file=sys.stderr)
            raise SystemExit(2)
        report = build_creator_readiness_report(
            vertical=str(getattr(args, "vertical", "travel") or "travel"),
            batch_id=str(args.batch),
            target=int(getattr(args, "target", 10) or 10),
            mode=str(getattr(args, "mode", "trial") or "trial"),
            min_pass_rate=float(getattr(args, "min_pass_rate", 1.0) or 1.0),
        )
        if getattr(args, "report_out", None):
            write_creator_readiness_report(Path(args.report_out), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report.get("passed"):
            raise SystemExit(1)
        return
    if cmd == "prefab-user-readiness":
        import subprocess

        repo_root = Path(__file__).resolve().parents[3]
        mode = str(getattr(args, "mode", "four_env") or "four_env")
        script = (
            repo_root / "quwoquan_data/scripts/verify/emit_creator_prefab_user_t2_stability_report.py"
            if mode == "t2"
            else repo_root / "quwoquan_data/scripts/verify/emit_creator_prefab_user_four_env_readiness.py"
        )
        cmd_args = ["python3", str(script)]
        if getattr(args, "report_out", None):
            cmd_args.extend(["--report-out", str(args.report_out)])
        result = subprocess.run(cmd_args, cwd=repo_root, check=False)
        raise SystemExit(result.returncode)
    if cmd == "site-scale-readiness":
        from verify.site_scale_readiness import build_site_scale_readiness_report, write_site_scale_readiness_report

        report = build_site_scale_readiness_report(
            vertical=str(args.vertical),
            batch_id=str(args.batch),
            batch_ids=[str(x).strip() for x in str(getattr(args, "batches", "") or "").split(",") if str(x).strip()] or None,
            site_id=getattr(args, "site_id", None),
            daily_target=int(args.daily_target),
            require_import=not bool(getattr(args, "allow_missing_import", False)),
            mode=str(getattr(args, "mode", "commercial") or "commercial"),
            min_lane_counts={
                "article": int(getattr(args, "min_article_count", 0) or 0),
                "image": int(getattr(args, "min_image_count", 0) or 0),
                "video": int(getattr(args, "min_video_count", 0) or 0),
            },
        )
        if getattr(args, "report_out", None):
            write_site_scale_readiness_report(Path(args.report_out), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report.get("passed"):
            raise SystemExit(1)
        return
    if getattr(args, "data_release_file", None):
        report = scan_release_file(
            Path(args.data_release_file),
            publish_root=Path(args.publish_root) if getattr(args, "publish_root", None) else None,
            metadata_root=Path(args.metadata_root) if getattr(args, "metadata_root", None) else None,
            phase=getattr(args, "phase", "preflight"),
        )
        if getattr(args, "report", None):
            write_consistency_report(report, Path(args.report))
        print(report_to_text(report))
        if report["status"] != "passed":
            raise SystemExit(1)
        return

    explicit = bool((getattr(args, "task", None) and getattr(args, "batch", None)) or getattr(args, "release", None))
    roots, issues = gate_verify(
        task=getattr(args, "task", None),
        batch=getattr(args, "batch", None),
        release=getattr(args, "release", None),
        scope=args.scope,
    )
    if not roots and not explicit:
        print(f"[verify] No in-scope post packages found (scope={args.scope}).")
        return
    if not roots and explicit:
        # 显式 --task/--batch：即使没有 post 包，也要跑并上报目录与资产证据链门。
        print(f"[verify] no post packages; running directory/asset evidence-chain gate only.")
    if roots:
        print(f"[verify] scope={args.scope} roots={len(roots)}")
        for root in roots:
            print(f"[verify]   - {root}")
    if issues:
        print(f"[verify] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues[:200]:
            print(f"  - {issue}", file=sys.stderr)
        raise SystemExit(1)
    print("[verify] PASSED")


def handle_batch_stability(args: argparse.Namespace) -> None:
    baseline, candidate, issues = compare_batches(args.task, args.baseline, args.candidate)
    report = {
        "schemaVersion": "quwoquan_data.batch_stability_compare/1",
        "taskId": args.task,
        "baseline": baseline,
        "candidate": candidate,
        "issues": issues,
        "passed": not issues,
    }
    if getattr(args, "baseline_snapshot_out", None):
        write_snapshot(Path(args.baseline_snapshot_out), baseline)
    if getattr(args, "report_out", None):
        write_report(Path(args.report_out), report)
    if issues:
        print(f"[verify] batch-stability FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues[:200]:
            print(f"  - {issue}", file=sys.stderr)
        raise SystemExit(1)
    print("[verify] batch-stability PASSED")


def handle_rubric(args: argparse.Namespace) -> None:
    """I：校验一份 rubric_review.json 满足 LLM-as-judge 严格性（判官元数据/族分离/二元+理由/偏差/jury）。"""
    from _common import rubric_judge as rj

    review = json.loads(Path(args.file).read_text(encoding="utf-8"))
    issues = rj.review_rigor_issues(
        review,
        generation_model_family=getattr(args, "generation_family", None),
        require_jury=bool(getattr(args, "require_jury", False)),
    )
    if issues:
        print(f"[verify rubric] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for i in issues:
            print(f"  - {i}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[verify rubric] PASSED ({Path(args.file).name})")


def handle_goldenset(args: argparse.Namespace) -> None:
    """J：golden set 门标定 + 判官校准（kappa/agreement + 地板 + 回归漂移）。"""
    from verify.measure_gate_goldenset import calibration_gate_issues, evaluate_goldenset

    report = evaluate_goldenset()
    baseline = None
    if getattr(args, "baseline", None) and Path(args.baseline).is_file():
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    if getattr(args, "report_out", None):
        Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    issues = calibration_gate_issues(report, baseline)
    cal = report["calibration"]
    print(f"[verify goldenset] intercept={report['interceptRate']} fp={report['falsePositiveRate']} "
          f"kappa={cal['cohenKappa']} agreement={cal['agreement']}")
    if issues:
        print(f"[verify goldenset] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for i in issues:
            print(f"  - {i}", file=sys.stderr)
        raise SystemExit(1)
    print("[verify goldenset] PASSED")


def _collect_batch_samples(task: str, batch: str, fraction: float) -> list[dict]:
    """K：从批次产出抽样 article.md/draft.article.md（确定性 stride 抽样）。"""
    from _common.paths import batch_root

    root = batch_root(task, batch)
    found: list[Path] = []
    if root.is_dir():
        for name in ("article.md", "draft.article.md"):
            found.extend(sorted(root.rglob(name)))
    if not found:
        return []
    frac = max(0.0, min(1.0, float(fraction)))
    want = max(1, int(round(len(found) * frac))) if frac > 0 else len(found)
    stride = max(1, len(found) // want)
    sampled = found[::stride][:want]
    return [{"ref": str(p.parent.relative_to(root)), "article": p.read_text(encoding="utf-8"), "meta": {}} for p in sampled]


def handle_sample_drift(args: argparse.Namespace) -> None:
    from _common import content_drift as cd

    samples: list[dict]
    if getattr(args, "samples_file", None):
        samples = json.loads(Path(args.samples_file).read_text(encoding="utf-8")).get("samples", [])
    else:
        samples = _collect_batch_samples(args.task, args.batch, args.fraction)
    baseline = None
    if getattr(args, "baseline", None) and Path(args.baseline).is_file():
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    report = cd.drift_report(samples, baseline)
    if getattr(args, "report_out", None):
        Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["drifted"]:
        print(f"[verify sample-drift] DRIFT ({len(report['alerts'])} alert(s))", file=sys.stderr)
        raise SystemExit(1)
    print(f"[verify sample-drift] PASSED (sampled={report['sampled']})")


def handle_promote_golden(args: argparse.Namespace) -> None:
    from _common import content_drift as cd

    article = Path(args.article_file).read_text(encoding="utf-8")
    meta = json.loads(args.meta) if getattr(args, "meta", None) else {}
    res = cd.promote_to_golden(
        Path(args.golden_dir),
        file_name=args.file_name,
        article=article,
        label=args.label,
        meta=meta,
        expect_gates=(args.expect_gates.split(",") if getattr(args, "expect_gates", None) else None),
        confirmed=bool(args.confirm),
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if not res.get("promoted") and not args.confirm:
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("verify", help="Verify post packages (scoped)")
    sub = p.add_subparsers(dest="verify_command")
    p.add_argument("--task", help="Task ID (verify a produced batch)")
    p.add_argument("--batch", help="Batch ID")
    p.add_argument("--release", help="Release ID under release/")
    p.add_argument("--data-release-file", help="Verify publish/env_releases/<releaseId>/<env>.json consistency")
    p.add_argument("--publish-root", help="Publish root for data release consistency")
    p.add_argument("--metadata-root", help="Metadata root for fixture user consistency")
    p.add_argument("--phase", choices=["preflight", "post-write-pre-activation", "post-activation"], default="preflight")
    p.add_argument("--report", help="Optional data release consistency report output path")
    p.add_argument(
        "--scope",
        choices=["current", "all"],
        default="current",
        help="批量审计针对 release/ 交付面：current=默认视图; all=全量视图。runtime 中间批次用 --task/--batch 显式校验。",
    )
    bs = sub.add_parser("batch-stability", help="Compare two batches for structural and quality stability")
    bs.add_argument("--task", required=True, help="Task ID")
    bs.add_argument("--baseline", required=True, help="Baseline batch ID")
    bs.add_argument("--candidate", required=True, help="Candidate batch ID")
    bs.add_argument("--baseline-snapshot-out", help="Optional baseline snapshot path")
    bs.add_argument("--report-out", help="Optional report path")

    # I：LLM-as-judge 严格性门
    pr = sub.add_parser("rubric", help="校验 rubric_review.json 的 judge 严格性（元数据/族分离/二元+理由/偏差/jury）")
    pr.add_argument("--file", required=True, help="rubric_review.json 路径")
    pr.add_argument("--generation-family", help="生成正文模型族（强制 judge ≠ generator）")
    pr.add_argument("--require-jury", action="store_true", help="高风险：要求 >= 3 判官多数表决")

    # J：判官校准 CI 门
    pg = sub.add_parser("goldenset", help="golden set 门标定 + 判官校准（kappa/agreement + 地板 + 回归漂移）")
    pg.add_argument("--baseline", help="可选 baseline 报告 JSON，用于回归漂移比对")
    pg.add_argument("--report-out", help="可选：把本次报告写出（供下次作 baseline）")

    # K：漂移检测
    pd = sub.add_parser("sample-drift", help="抽样已产出复跑 rule 门，检测线上质量漂移")
    pd.add_argument("--task", help="Task ID（批次扫描）")
    pd.add_argument("--batch", help="Batch ID（批次扫描）")
    pd.add_argument("--fraction", type=float, default=0.1, help="抽样比例（默认 0.1=10%%）")
    pd.add_argument("--samples-file", help="可选：显式 samples JSON（{samples:[{ref,article,meta}]}）")
    pd.add_argument("--baseline", help="可选 baseline drift 报告，用于触发率漂移比对")
    pd.add_argument("--report-out", help="可选报告输出路径")

    # K：失败回灌闭环
    pp = sub.add_parser("promote-golden", help="把人工确认的失败 trace 晋级 golden set（闭环自增长）")
    pp.add_argument("--golden-dir", required=True, help="golden set 目录")
    pp.add_argument("--file-name", required=True, help="写入 golden 的 md 文件名")
    pp.add_argument("--article-file", required=True, help="失败正文文件路径")
    pp.add_argument("--label", default="bad", help="标签（默认 bad）")
    pp.add_argument("--meta", help="JSON meta（carrier/writingIntent/assets/bannedRegisterTerms）")
    pp.add_argument("--expect-gates", help="逗号分隔的期望触发门")
    pp.add_argument("--confirm", action="store_true", help="人工确认（必须显式传入才入集）")

    sub.add_parser("data-role-gate", help="校验数据工程七角色准出清单与文档/门禁接线")
    sub.add_parser("single-contract-source", help="校验内容供给生产契约只有一个无版本真源")
    sub.add_parser("content-supply-production", help="校验生产级内容供给 current 契约与队列/envelope/账本闭环")
    sub.add_parser("works-classification", help="校验作品 vs 随记判定 schema/config/registry 一致性 + 判定 smoke")
    pri = sub.add_parser("release-integrity", help="校验 release 级证据链、一稿一用与跨作品资产溯源完整性")
    pri.add_argument("--release", required=True, help="Release ID under release/")
    psr = sub.add_parser("scale-readiness", help="校验批次是否具备日产万级/商用放量证据")
    psr.add_argument("--task", required=True, help="Task ID")
    psr.add_argument("--batch", required=True, help="Batch ID")
    psr.add_argument("--daily-target", type=int, default=10000, help="目标日产内容对象数，默认 10000")
    psr.add_argument("--target", type=int, default=0, help="本批目标质量对象数；百级用 100")
    psr.add_argument("--min-pass-rate", type=float, default=0.0, help="本批目标满足率门槛；百级用 0.9")
    psr.add_argument("--source-ready-goal", type=int, default=0, help="source-ready 对象容量门槛；不传时按 target*1.2")
    psr.add_argument("--mode", choices=["trial", "commercial"], default="commercial", help="trial 允许已替补 abandoned；commercial 要求零未替补失败")
    psr.add_argument("--release", help="可选 isolated release ID，用于证明 release verify 入口存在")
    psr.add_argument("--allow-missing-import", action="store_true", help="仅本地试跑时允许缺少 staging/gamma import 证据")
    psr.add_argument("--report-out", help="可选：写出 readiness JSON 报告")
    pcsr = sub.add_parser("creator-scale-readiness", help="校验创作者池 Scale-10/100 放量证据")
    pcsr.add_argument("--vertical", default="travel")
    pcsr.add_argument("--batch", required=True)
    pcsr.add_argument("--target", type=int, default=10)
    pcsr.add_argument("--mode", choices=["trial", "commercial"], default="trial")
    pcsr.add_argument("--min-pass-rate", type=float, default=1.0)
    pcsr.add_argument("--report-out", help="写出 creator readiness JSON")
    pss = sub.add_parser("site-scale-readiness", help="校验网站维度内容供给是否具备日产 10 万级准出证据")
    pss.add_argument("--vertical", default="travel", help="垂类，默认 travel")
    pss.add_argument("--site-id", help="可选：只校验单个 siteId；不传则聚合同垂类该 batch 全部站点")
    pss.add_argument("--batch", required=True, help="site_supply batch ID")
    pss.add_argument("--batches", help="逗号分隔多个 site_supply batchId；用于同垂类多站点真实放量聚合")
    pss.add_argument("--daily-target", type=int, default=100000, help="目标日产内容对象数，默认 100000")
    pss.add_argument("--mode", choices=["trial", "commercial"], default="commercial", help="trial 只验结构/吞吐/账本，commercial 要求 release/import/search/rec 证据")
    pss.add_argument("--allow-missing-import", action="store_true", help="仅本地试跑时允许缺少 import 证据")
    pss.add_argument("--min-article-count", type=int, default=0, help="可选：trial 按 content_plan handoff，commercial 按已 release/import postRefs 统计文章最低数")
    pss.add_argument("--min-image-count", type=int, default=0, help="可选：trial 按 content_plan handoff，commercial 按已 release/import postRefs 统计图片作品最低数")
    pss.add_argument("--min-video-count", type=int, default=0, help="可选：trial 按 content_plan handoff，commercial 按已 release/import postRefs 统计视频作品最低数")
    pss.add_argument("--report-out", help="可选：写出 readiness JSON 报告")

    ppur = sub.add_parser("prefab-user-readiness", help="T4 四环境 prefab user readiness 报告")
    ppur.add_argument("--mode", choices=["four_env", "t2"], default="four_env")
    ppur.add_argument("--report-out", help="可选：覆盖默认 artifact 路径")

    p.set_defaults(handler=handle_verify)
