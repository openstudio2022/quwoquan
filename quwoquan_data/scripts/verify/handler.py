"""data verify — scoped post-package quality verification (CLI)。

`qwq-data verify [--execution-id E] [--release R] [--scope current|all]`

收紧扫描范围：默认 current（仅当前 schema 的 posts 根），可指定 execution 或 release。
逻辑全部沉到 verify.post_verify，旧 verify_*.py 仅作薄壳委托本命令。
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from pathlib import Path

from content.release.environment.consistency import (
    report_to_text,
    scan_release_file,
    write_consistency_report,
)
from core import paths
from verify.gate import gate_verify
from verify.verify_execution_readiness import READINESS_MODES
from verify.legacy_runtime_zero_evidence import (
    register_legacy_runtime_zero_evidence_parser,
)


_HOMEPAGE_MEDIA_HELP = {
    "homepage-media-completeness": "校验实体主页图片枚举、下载与角色闭环（决策+兑现合并口径）",
    "homepage-media-decision": "1.download 判据：每张下载图的处置已冻结且合法，不读 manifest",
    "homepage-media-fulfillment": "物化后判据：manifest 与冻结处置双向对账",
}
_HOMEPAGE_MEDIA_VIEWS = {
    "homepage-media-completeness": "combined",
    "homepage-media-decision": "decision",
    "homepage-media-fulfillment": "fulfillment",
}


# 无参 verify 门的统一转发表：cmd -> verify 模块名（模块必须暴露 main() -> int）。
_NO_ARG_VERIFIER_MODULES = {
    "single-contract-source": "verify_single_contract_source",
    "works-classification": "verify_works_classification",
    "output-root-isolation": "verify_output_root_isolation",
    "runtime-input-ownership": "verify_runtime_input_ownership",
    "reusable-data-contract": "verify_reusable_data_contract",
    "publish-purity": "verify_publish_purity",
    "publish-closure": "verify_publish_closure",
    "cli-first": "verify_cli_first",
    "script-architecture": "verify_script_architecture",
    "python-symbols": "verify_python_symbols",
    "control-literals": "verify_control_literals",
    "scale-parameterization": "verify_scale_parameterization",
    "object-size-budget": "verify_object_size_budget",
    "execution-identity-purity": "verify_execution_identity_purity",
    "cursor-credential-contract": "verify_cursor_credential_contract",
    "active-runtime-preflight": "verify_no_active_data_runtime",
    "data-layout": "verify_data_layout",
    "coverage-static-identity": "verify_coverage_static_identity",
    "media-release-contract": "verify_media_release_contract",
}


def handle_verify(args: argparse.Namespace) -> None:
    cmd = getattr(args, "verify_command", None)
    if cmd in _NO_ARG_VERIFIER_MODULES:
        from importlib import import_module

        raise SystemExit(import_module(f"verify.{_NO_ARG_VERIFIER_MODULES[cmd]}").main())
    if cmd == "all":
        output = getattr(args, "verify_all_output", None)
        if output:
            from verify.verify_all_receipt import (
                VerifyAllReceiptError,
                run_with_receipt,
            )

            try:
                run_with_receipt(output=Path(output), run=handle_all)
            except (OSError, TypeError, VerifyAllReceiptError) as exc:
                raise SystemExit(
                    f"[verify all] GATE_BLOCK DATA.VERIFY_ALL.RECEIPT_WRITE_FAILED: {exc}"
                ) from exc
        else:
            handle_all()
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
    if cmd == "task-init-contract":
        from verify.verify_task_init_contract import main as task_init_contract_main

        raise SystemExit(
            task_init_contract_main(["--execution-id", str(args.execution_id)])
        )
    if cmd == "content-execution-layout":
        from verify.verify_content_execution_layout import main as execution_layout_main

        argv = []
        if getattr(args, "execution_id", None):
            argv = ["--execution-id", str(args.execution_id)]
        raise SystemExit(execution_layout_main(argv))
    if cmd == "execution-readiness":
        from verify.verify_execution_readiness import main as execution_readiness_main

        argv = ["--execution-id", str(args.execution_id)]
        if bool(getattr(args, "require_reviewed", False)):
            argv.append("--require-reviewed")
        argv.extend(["--mode", str(args.mode)])
        raise SystemExit(execution_readiness_main(argv))
    if cmd == "source-digest":
        from verify.verify_source_digest import main as source_digest_main

        argv = ["--scope", str(args.scope)]
        if getattr(args, "source_execution_id", None):
            argv.extend(["--execution-id", str(args.source_execution_id)])
        raise SystemExit(source_digest_main(argv))
    if cmd == "release-publishability":
        from verify.release_publishability import main as release_publishability_main

        raise SystemExit(release_publishability_main(["--receipt", str(args.publishability_receipt)]))
    if cmd == "release-lifecycle":
        from verify.verify_release_lifecycle import main as release_lifecycle_main

        argv = ["--release", str(args.lifecycle_release)]
        for option, value in (
            ("--environment", args.environment),
            ("--import-run", args.import_run),
            ("--verify-run", args.verify_run),
            ("--rollback-from-release", args.rollback_from_release),
        ):
            if value:
                argv.extend((option, str(value)))
        argv.extend(("--prod-mode", str(args.prod_mode)))
        raise SystemExit(release_lifecycle_main(argv))
    if cmd == "release-lifecycle-exit":
        from verify.release_lifecycle_exit import main as release_lifecycle_exit_main

        raise SystemExit(
            release_lifecycle_exit_main(
                [
                    "--environment",
                    str(args.environment),
                    "--original-release",
                    str(args.original_release),
                    "--exit-run",
                    str(args.exit_run),
                ]
            )
        )
    if cmd in _HOMEPAGE_MEDIA_VIEWS:
        from verify.verify_homepage_media_completeness import main as homepage_media_main

        raise SystemExit(
            homepage_media_main(
                ["--execution", str(args.execution), "--view", _HOMEPAGE_MEDIA_VIEWS[cmd]]
            )
        )
    if cmd == "homepage-draft":
        from verify.verify_homepage_draft import main as homepage_draft_main

        raise SystemExit(
            homepage_draft_main(
                ["--execution", str(args.execution), "--entity", str(args.entity)]
            )
        )
    if cmd == "stage-artifacts":
        from verify.stage_artifacts import verify_stage_artifacts

        report = verify_stage_artifacts(
            execution_id=str(args.execution_id),
            publish_root=Path(args.publish_root) if args.publish_root else paths.PUBLISH_ROOT,
            release_root=Path(args.release_root) if args.release_root else paths.RELEASE_ROOT,
            commercial=not bool(args.trial),
            through=args.through,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["passed"]:
            raise SystemExit(1)
        return
    if cmd == "release-integrity":
        from content.release.canonical.integrity import scan_release_integrity

        report = scan_release_integrity(args.release)
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

    execution_id = getattr(args, "execution_id", None)
    explicit = bool(execution_id or getattr(args, "release", None))
    roots, issues = gate_verify(
        execution_id=execution_id,
        release=getattr(args, "release", None),
        scope=args.scope,
    )
    if not roots and not explicit:
        print(f"[verify] No in-scope post packages found (scope={args.scope}).")
        return
    if not roots and explicit:
        # 显式 execution：即使没有 post 包，也要跑并上报目录与资产证据链门。
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


def _run_filter_catalog_gate() -> int:
    from content.filter_catalog.artifact import validate_repository

    report = validate_repository(paths.REPO_ROOT)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


def _admit_carried_media_holdings() -> int:
    from content.release.canonical.rehydrate_media_holdings import main as rehydrate_main

    return int(rehydrate_main() or 0)


def _run_static_gate(name: str, run: Callable[[], int | None]) -> tuple[str, int]:
    try:
        result = run()
    except SystemExit as exc:
        result = int(exc.code or 0)
    except Exception as exc:  # noqa: BLE001 - a verifier crash is a failed gate.
        print(f"[verify all] {name} crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
        result = 2
    return name, int(result or 0)


def handle_all() -> list[str]:
    """Run the repository-owned static Data gate through the one public CLI.

    Environment import/API/UAT proofs are intentionally not hidden here: they
    remain explicit `ship` and `verify release-lifecycle` commands
    because they require a concrete release and a live environment.
    """
    from verify import verify_cli_first
    from verify import verify_content_execution_layout
    from verify import verify_cursor_credential_contract
    from verify import verify_runtime_input_ownership
    from verify import verify_reusable_data_contract
    from verify import verify_data_layout
    from verify import verify_execution_identity_purity
    from verify import verify_output_root_isolation
    from verify import verify_publish_closure
    from verify import verify_public_cli_live_import_zero
    from verify import verify_script_architecture
    from verify import verify_python_symbols
    from verify import verify_control_literals
    from verify import verify_scale_parameterization
    from verify import verify_prompt_templates
    from verify import verify_no_flat_roots
    from verify import verify_no_runtime_draft_kit
    from verify import verify_tag_tree
    from verify import verify_source_digest
    from verify import verify_single_contract_source
    from verify import verify_works_classification
    from verify import verify_coverage_static_identity
    from verify import verify_media_release_contract
    from verify import verify_object_size_budget

    # 闭包类门禁问的是内容库而不是这棵树，而库按设计在仓外，一份新检出手里
    # 一个字节都没有。先把仓内携带的媒体字节入库，这些门禁才是在判内容对错，
    # 而不是在判这台机器上有没有跑过别的流程。已入库时这一步是空转。
    if _admit_carried_media_holdings() != 0:
        raise SystemExit(1)

    gates = (
        ("cli-first", verify_cli_first.main),
        ("public-cli-live-import-zero", lambda: verify_public_cli_live_import_zero.main([])),
        ("data-layout", verify_data_layout.main),
        ("script-architecture", verify_script_architecture.main),
        ("python-symbols", verify_python_symbols.main),
        ("control-literals", verify_control_literals.main),
        ("scale-parameterization", verify_scale_parameterization.main),
        ("prompt-templates", verify_prompt_templates.main),
        ("no-flat-roots", verify_no_flat_roots.main),
        ("no-runtime-draft-kit", verify_no_runtime_draft_kit.main),
        ("tag-tree", lambda: verify_tag_tree.main([])),
        ("source-digest", lambda: verify_source_digest.main([])),
        ("execution-identity-purity", verify_execution_identity_purity.main),
        ("content-execution-layout", lambda: verify_content_execution_layout.main([])),
        ("reusable-data-contract", verify_reusable_data_contract.main),
        ("runtime-input-ownership", verify_runtime_input_ownership.main),
        ("cursor-credential-contract", verify_cursor_credential_contract.main),
        ("output-root-isolation", verify_output_root_isolation.main),
        ("coverage-static-identity", verify_coverage_static_identity.main),
        ("media-release-contract", verify_media_release_contract.main),
        ("object-size-budget", verify_object_size_budget.main),
        ("filter-catalog", _run_filter_catalog_gate),
        ("publish-closure", verify_publish_closure.main),
        ("single-contract-source", verify_single_contract_source.main),
        ("works-classification", verify_works_classification.main),
    )
    results: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(gates))) as executor:
        futures = {
            executor.submit(_run_static_gate, name, run): name
            for name, run in gates
        }
        for future in as_completed(futures):
            name, result = future.result()
            results[name] = result
    failed = [name for name, _run in gates if results.get(name, 2) != 0]
    if failed:
        raise SystemExit(f"[verify all] FAIL: {', '.join(failed)}")
    print("[verify all] OK")
    return [name for name, _run in gates]


def handle_rubric(args: argparse.Namespace) -> None:
    """I：校验一份 rubric_review.json 满足 LLM-as-judge 严格性（判官元数据/族分离/二元+理由/偏差/jury）。"""
    from core import rubric_judge as rj

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


def _collect_execution_samples(execution_id: str, fraction: float) -> list[dict]:
    """K：从 execution 产出抽样 article.md/draft.article.md（确定性 stride 抽样）。"""
    from core.paths import execution_root

    root = execution_root(execution_id)
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
    from core import content_drift as cd

    samples: list[dict]
    if getattr(args, "samples_file", None):
        samples = json.loads(Path(args.samples_file).read_text(encoding="utf-8")).get("samples", [])
    else:
        if not getattr(args, "execution_id", None):
            raise SystemExit("[verify sample-drift] --execution-id is required without --samples-file")
        samples = _collect_execution_samples(args.execution_id, args.fraction)
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
    from core import content_drift as cd

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
    all_parser = sub.add_parser(
        "all", help="运行唯一的仓内 Data 静态门禁；环境闭环另行显式验证"
    )
    all_parser.add_argument(
        "--output",
        dest="verify_all_output",
        help=(
            "可选 create-once PASS receipt；必须位于 "
            ".qwq_output/data/local/runs/**"
        ),
    )
    p.add_argument("--execution-id", help="Execution ID (verify one runtime work package)")
    p.add_argument("--release", help="Release ID under release/")
    p.add_argument("--data-release-file", help="Verify immutable release <releaseId>/desired_state.json consistency")
    p.add_argument("--publish-root", help="Publish root for data release consistency")
    p.add_argument("--metadata-root", help="Metadata root for fixture user consistency")
    p.add_argument("--phase", choices=["preflight", "post-write-pre-activation", "post-activation"], default="preflight")
    p.add_argument("--report", help="Optional data release consistency report output path")
    p.add_argument(
        "--scope",
        choices=["current", "all"],
        default="current",
        help="聚合审计针对 release/ 交付面：current=默认视图; all=全量视图。runtime 工作包用 --execution-id 显式校验。",
    )
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
    pd.add_argument("--execution-id", help="Execution ID（工作包扫描）")
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

    sub.add_parser("single-contract-source", help="校验内容供给生产契约只有一个无版本真源")
    sub.add_parser("works-classification", help="校验作品 vs 随记判定 schema/config/registry 一致性 + 判定 smoke")
    sub.add_parser("output-root-isolation", help="仓外输出根隔离门：repo allowlist/阶段树/批次轴/摘要索引")
    task_init_contract = sub.add_parser(
        "task-init-contract", help="校验 task init 的三文件 current work-package 合同"
    )
    task_init_contract.add_argument("--execution-id", required=True)
    cel = sub.add_parser("content-execution-layout", help="校验历史 execution 工作包与对象阶段目录")
    cel.add_argument("--execution-id", help="只校验一个显式命名的 execution 工作包")
    per = sub.add_parser("execution-readiness", help="校验单个 execution 工作包的准出证据")
    per.add_argument("--execution-id", required=True)
    per.add_argument("--require-reviewed", action="store_true")
    per.add_argument(
        "--mode",
        choices=READINESS_MODES,
        required=True,
    )
    sub.add_parser("reusable-data-contract", help="校验静态数据资产只表达可复用能力")
    sub.add_parser("runtime-input-ownership", help="校验区域、数量和目标集只归运行工作包 0.plan")
    sub.add_parser("publish-purity", help="校验 publish 只含 approved 最终对象")
    sub.add_parser("publish-closure", help="校验 canonical publish 无孤立 creator/media 或悬空引用")
    sub.add_parser("cli-first", help="校验业务能力只经 Data CLI 入口暴露")
    sub.add_parser("script-architecture", help="校验脚本目录职责、模块尺寸与 core 依赖方向")
    register_legacy_runtime_zero_evidence_parser(sub)
    sub.add_parser("python-symbols", help="校验 Data Python 运行时符号均有明确所有者")
    sub.add_parser("control-literals", help="校验双省链路控制字面量只有一个真相源")
    sub.add_parser(
        "scale-parameterization",
        help="校验里程碑目标只有 control-plane 一个真相源且各消费者一致",
    )
    sub.add_parser(
        "object-size-budget",
        help="校验单对象闭包体积不超过图文 10MiB / 视频 50MiB 预算",
    )
    source_digest = sub.add_parser(
        "source-digest",
        help=(
            "current 精确校验显式 candidate/现行 release 视图；"
            "all 审计全部历史 source identity"
        ),
    )
    source_digest.add_argument(
        "--execution-id",
        dest="source_execution_id",
        help="显式选择 current execution candidate；省略时不从 tasks 历史推断",
    )
    sub.add_parser("execution-identity-purity", help="校验 active code 已删除旧运行身份与旧路径")
    prp = sub.add_parser("release-publishability", help="唯一「可发布」谓词：判定一份环境 readiness 收据是否可发布")
    prp.add_argument("--receipt", dest="publishability_receipt", required=True, help="release-readiness.json 收据路径")
    release_lifecycle = sub.add_parser("release-lifecycle", help="校验 immutable release 的闭环证据")
    release_lifecycle.add_argument("--release", dest="lifecycle_release", required=True)
    release_lifecycle.add_argument("--environment", choices=("alpha", "beta", "gamma", "prod"))
    release_lifecycle.add_argument("--import-run")
    release_lifecycle.add_argument("--verify-run")
    release_lifecycle.add_argument("--rollback-from-release")
    release_lifecycle.add_argument(
        "--prod-mode",
        choices=("activated", "dry-run", "prepared"),
        default="activated",
    )
    lifecycle_exit = sub.add_parser(
        "release-lifecycle-exit",
        help="重算验证 original→rollback→same-digest replay Exit receipt",
    )
    lifecycle_exit.add_argument(
        "--environment",
        required=True,
        choices=("alpha", "beta", "gamma", "prod"),
    )
    lifecycle_exit.add_argument("--original-release", required=True)
    lifecycle_exit.add_argument("--exit-run", required=True)
    sub.add_parser("cursor-credential-contract", help="校验只使用仓外受限 key file 且无旧 alias/secret")
    for name, help_text in _HOMEPAGE_MEDIA_HELP.items():
        sub.add_parser(name, help=help_text).add_argument("--execution", required=True)
    phd = sub.add_parser("homepage-draft", help="校验单个 Agent 主页草稿的结构与底稿贴合度")
    phd.add_argument("--execution", required=True)
    phd.add_argument("--entity", required=True)
    sub.add_parser("active-runtime-preflight", help="校验 data execution 工作区已静默，无活跃 execute/workflow 进程")
    sub.add_parser("data-layout", help="校验数据工程源码目录归一化与退休路径")
    sub.add_parser("coverage-static-identity", help="全国地点静态覆盖身份门：目录/schema/类型/行政区/coverageKey 全局唯一")
    sub.add_parser("media-release-contract", help="校验 release-bound CAS、视频 poster 与环境 URL 投影合同")
    psa = sub.add_parser(
        "stage-artifacts",
        help="校验四 lane 五阶段、immutable execution identity 与 runtime/runs/release/env/publish 边界",
    )
    psa.add_argument("--execution-id", required=True)
    psa.add_argument("--publish-root")
    psa.add_argument("--release-root")
    psa.add_argument("--trial", action="store_true", help="trial 允许 independent reviewer 尚未通过")
    psa.add_argument(
        "--through",
        choices=paths.OBJECT_STAGES,
        help="进行式校验：只要求到该阶段为止的产物齐全；缺省为完成型全量校验",
    )
    pri = sub.add_parser("release-integrity", help="校验 release 级证据链、一稿一用与跨作品资产溯源完整性")
    pri.add_argument("--release", required=True, help="Release ID under release/")
    p.set_defaults(handler=handle_verify)
