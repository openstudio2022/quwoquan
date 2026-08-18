"""Argparse composition for canonical immutable release commands."""
from __future__ import annotations

import argparse

from content.release.canonical import handler as owner


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("release", help="构建不可变的通用内容发布包")
    commands = parser.add_subparsers(dest="release_command", required=True)

    aggregate = commands.add_parser(
        "campaign-aggregate",
        help="只从 immutable campaign plan/current retry chain 聚合发布包",
    )
    aggregate.add_argument("--release-id", required=True)
    aggregate.add_argument("--root-execution-id", required=True)
    aggregate.add_argument(
        "--target-environment",
        choices=("alpha", "beta", "gamma", "prod"),
        help=(
            "按同一内容池的稳定前缀构建环境 ReleaseManifest；"
            "alpha/beta/gamma cap 分别为 2.1k/10k/100k"
        ),
    )
    aggregate.add_argument(
        "--release-class",
        choices=("research", "commercial"),
        required=True,
    )
    aggregate.add_argument("--output-root")
    aggregate.set_defaults(handler=owner.handle_campaign_aggregate_release)

    pool_build = commands.add_parser(
        "pool-build",
        help="从同一 canonical 池按显式 Research/Commercial 权限构建 ReleaseManifest",
    )
    pool_build.add_argument("--release-id", required=True)
    selection = pool_build.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--target-environment",
        choices=("alpha", "beta", "gamma", "prod"),
    )
    selection.add_argument(
        "--milestone", choices=("M100", "M1000", "M10000")
    )
    pool_build.add_argument(
        "--release-class",
        choices=("research", "commercial"),
        required=True,
        help="显式发布类别；Research 接受 research/commercial，Commercial 仅接受商用闭包",
    )
    pool_build.add_argument("--publish-root")
    pool_build.add_argument("--release-root")
    pool_build.set_defaults(handler=owner.handle_pool_release_build)

    pool_inspect = commands.add_parser(
        "pool-inspect",
        help="只读审视作者/内容准入、引用闭包、环境容量与 M100 gap",
    )
    pool_inspect.add_argument("--publish-root")
    pool_inspect.add_argument(
        "--milestone",
        choices=("M100", "M1000", "M10000"),
        help="可选 milestone preset；显式 --workload 时省略",
    )
    pool_inspect.add_argument(
        "--details",
        action="store_true",
        help="包含全部逐对象问题；默认只输出首个 typed blocker",
    )
    pool_inspect.add_argument(
        "--by-task",
        action="store_true",
        help="按来源任务批次显示目标、成功、质量、授权与交付统计",
    )
    pool_inspect.add_argument(
        "--execution-id",
        action="append",
        help="与 --by-task 一起重复传入要审计的精确 frozen execution",
    )
    pool_inspect.add_argument(
        "--source-pool-ref",
        help="待调度 current wave 的 exact immutable scale source-pool output ref",
    )
    pool_inspect.add_argument(
        "--source-pool-evidence-root-ref",
        help="与 source-pool 逐字节核验的 exact physical evidence root output ref",
    )
    pool_inspect.add_argument(
        "--throughput-promotion-ref",
        help="可选：含真实 per-slot samples 的 immutable promotion output ref",
    )
    pool_inspect.add_argument(
        "--workload",
        action="append",
        default=[],
        metavar="CARRIER=QUOTA",
        help="显式活动载体及精确调度目标；可重复传入",
    )
    pool_inspect.set_defaults(handler=owner.handle_pool_inspect)

    pool_dispatch = commands.add_parser(
        "pool-dispatch",
        help="从 pool-inspect 的物理 waveInput 冻结 carrier-selective 单 execution 请求",
    )
    pool_dispatch.add_argument("--dispatch-id", required=True)
    pool_dispatch.add_argument("--pool-inspection-ref", required=True)
    pool_dispatch.add_argument(
        "--semantic-preflight-receipt",
        help="可选 preflight 观测 receipt；不参与 dispatch 准入",
    )
    pool_dispatch.add_argument("--run-date", required=True)
    pool_dispatch.add_argument("--scope", required=True)
    pool_dispatch.add_argument("--region-ref", required=True)
    pool_dispatch.add_argument("--sequence-start", type=int, default=1)
    pool_dispatch.add_argument(
        "--workload",
        action="append",
        default=[],
        metavar="CARRIER=QUOTA",
        help="再次显式绑定 inspection 中的活动载体与精确目标",
    )
    pool_dispatch.add_argument(
        "--predecessor-dispatch-ref",
        help="retry wave 的 immutable predecessor dispatch manifest output ref",
    )
    pool_dispatch.add_argument(
        "--retry-predecessor",
        action="append",
        default=[],
        metavar="SLOT_ID=EXECUTION_ID",
        help="逐 slot 显式绑定失败 predecessor；retry wave 只物化这些 exact slots",
    )
    pool_dispatch.add_argument(
        "--retry-unfinished-ref",
        action="append",
        default=[],
        metavar="SLOT_ID=OBJECT_REF",
        help="逐 slot 按 predecessor state 的 exact ordered unfinished ref 缩窄 retry",
    )
    pool_dispatch.add_argument("--publish-root")
    pool_dispatch.set_defaults(handler=owner.handle_pool_dispatch)

    supply_chain_drill = commands.add_parser(
        "supply-chain-drill",
        help="经正式发布、验证与运行时入口演练一个不可变 Release",
    )
    supply_chain_drill.add_argument("--release-id", required=True)
    supply_chain_drill.add_argument(
        "--env",
        required=True,
        choices=("alpha", "beta", "gamma", "prod"),
    )
    supply_chain_drill.add_argument(
        "--profile",
        required=True,
        choices=("inspect", "delivery", "rehearsal"),
    )
    supply_chain_drill.add_argument(
        "--platform",
        choices=("android", "ios-simulator"),
        default="",
    )
    supply_chain_drill.add_argument("--device-id", default="")
    supply_chain_drill.set_defaults(handler=owner.handle_supply_chain_drill)

    pool_append = commands.add_parser(
        "pool-append",
        help="逐对象校验或显式追加作者、实体主页和内容准入记录",
    )
    pool_append.add_argument("--input", required=True)
    pool_append.add_argument("--publish-root")
    pool_append.add_argument(
        "--apply",
        action="store_true",
        help="显式写入；省略时只验证并输出 plan 结果",
    )
    pool_append.set_defaults(handler=owner.handle_pool_append)

    pool_backfill = commands.add_parser(
        "pool-backfill",
        help="从现有 canonical 证据派生只读 backfill 计划",
    )
    pool_backfill_actions = pool_backfill.add_subparsers(
        dest="pool_backfill_action", required=True
    )
    pool_backfill_plan = pool_backfill_actions.add_parser(
        "plan", help="仅输出证据绑定的 pool-append batch；不写 canonical"
    )
    pool_backfill_plan.add_argument("--publish-root")
    pool_backfill_plan.set_defaults(handler=owner.handle_pool_backfill_plan)
    pool_backfill_repair = pool_backfill_actions.add_parser(
        "repair-attribution",
        help="从 exact source-ready candidate 计划或追加显式 attribution pool record",
    )
    pool_backfill_repair.add_argument("--bindings", required=True)
    pool_backfill_repair.add_argument("--source-pool-ref", required=True)
    pool_backfill_repair.add_argument(
        "--source-pool-evidence-root-ref", required=True
    )
    pool_backfill_repair.add_argument("--publish-root")
    pool_backfill_repair.add_argument("--apply", action="store_true")
    pool_backfill_repair.set_defaults(
        handler=owner.handle_pool_attribution_repair
    )

    object_transaction = commands.add_parser(
        "object-transaction",
        help="按审计 delta 与 canonical Merkle 管理单一对象事务",
    )
    object_transaction_actions = object_transaction.add_subparsers(
        dest="object_transaction_action",
        required=True,
    )
    object_transaction_rollback = object_transaction_actions.add_parser(
        "rollback",
        help="按精确 inverse delta 回滚一笔已应用对象事务并保留回执",
    )
    object_transaction_rollback.add_argument("--transaction-id", required=True)
    object_transaction_rollback.add_argument("--output-root")
    object_transaction_rollback.add_argument("--publish-root")
    object_transaction_rollback.set_defaults(
        handler=owner.handle_object_transaction_rollback
    )

    identity_incident = commands.add_parser(
        "identity-incident",
        help="记录同一 releaseId 的冲突 immutable identity；不修改任何 release",
    )
    identity_incident.add_argument("--release-id", required=True)
    identity_incident.add_argument("--incident-id", required=True)
    identity_incident.add_argument(
        "--original-attestation",
        action="append",
        default=[],
        help="原始留存的 release attestation 文件；可重复",
    )
    identity_incident.add_argument(
        "--recovery-provenance",
        action="append",
        default=[],
        help="deterministic_byte_reconstruction 的 create-once provenance；可重复",
    )
    identity_incident.add_argument("--output-root")
    identity_incident.set_defaults(handler=owner.handle_release_identity_incident)

    identity_recovery = commands.add_parser(
        "identity-recovery",
        help="按冻结 JSON 序列化合同写确定性 attestation 恢复物与 provenance",
    )
    identity_recovery.add_argument("--release-id", required=True)
    identity_recovery.add_argument("--recovery-id", required=True)
    identity_recovery.add_argument("--attestation-document", required=True)
    identity_recovery.add_argument("--template-attestation", required=True)
    identity_recovery.add_argument("--target-attestation-sha256", required=True)
    identity_recovery.add_argument("--writer-revision", required=True)
    identity_recovery.add_argument(
        "--writer-source",
        action="append",
        required=True,
        help="历史 writer 闭集，格式 <logicalRef>=<snapshotPath>；必须四项",
    )
    identity_recovery.add_argument("--recovered-recorded-at", required=True)
    identity_recovery.add_argument("--search-start-at", required=True)
    identity_recovery.add_argument("--search-end-at", required=True)
    identity_recovery.add_argument(
        "--evidence",
        action="append",
        required=True,
        help=(
            "独立证据，格式 <role>=<path>；必须各提供 "
            "release_identity 与 execution_closure"
        ),
    )
    identity_recovery.add_argument("--output-root")
    identity_recovery.set_defaults(handler=owner.handle_release_identity_recovery)

    baseline = commands.add_parser(
        "baseline", help="创建仅用于 full-sync rollback 的空 desired-state 发布包"
    )
    baseline.add_argument("--release-id", required=True)
    baseline.add_argument("--publish-root")
    baseline.add_argument("--release-root")
    baseline.add_argument(
        "--release-class",
        choices=("research", "commercial"),
        required=True,
    )
    baseline.set_defaults(handler=owner.handle_baseline_release)

    build_lookups = commands.add_parser(
        "build-lookups",
        help="为 immutable release 生成 create-once first-consumer lookup indexes",
    )
    build_lookups.add_argument("--release-id", required=True)
    build_lookups.add_argument("--publish-root")
    build_lookups.add_argument("--release-root")
    build_lookups.add_argument("--taxonomy-root")
    build_lookups.set_defaults(handler=owner.handle_build_lookup_indexes)

    discard = commands.add_parser(
        "discard", help="删除无活跃写入的可重跑 release 输出及其环境证据"
    )
    discard.add_argument("--release-id", required=True)
    discard.set_defaults(handler=owner.handle_discard)

    lifecycle_exit = commands.add_parser(
        "lifecycle-exit",
        help="从既有 original/rollback/replay run 写入 create-once Exit receipt",
    )
    lifecycle_exit.add_argument(
        "--env", required=True, choices=("alpha", "beta", "gamma", "prod")
    )
    lifecycle_exit.add_argument("--original-release-id", required=True)
    lifecycle_exit.add_argument("--original-import-run-id", required=True)
    lifecycle_exit.add_argument("--original-verify-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-to-release-id", required=True)
    lifecycle_exit.add_argument("--rollback-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-verify-run-id", required=True)
    lifecycle_exit.add_argument("--replay-import-run-id", required=True)
    lifecycle_exit.add_argument("--replay-verify-run-id", required=True)
    lifecycle_exit.add_argument(
        "--run-id", required=True, help="append-only Exit run id"
    )
    lifecycle_exit.set_defaults(handler=owner.handle_lifecycle_exit)

    acceptance_lease = commands.add_parser(
        "acceptance-lease",
        help="为真实 UAT 写入 append-only acquire/revoke lease event",
    )
    lease_actions = acceptance_lease.add_subparsers(
        dest="acceptance_lease_action",
        required=True,
    )
    acquire = lease_actions.add_parser("acquire")
    acquire.add_argument(
        "--env", required=True, choices=("alpha", "beta", "gamma", "prod")
    )
    acquire.add_argument("--release-id", required=True)
    acquire.add_argument("--import-run-id", required=True)
    acquire.add_argument("--verify-run-id", required=True)
    acquire.add_argument("--lease-id", required=True)
    acquire.add_argument("--event-id", default="")
    acquire.set_defaults(handler=owner.handle_acceptance_lease)
    revoke = lease_actions.add_parser("revoke")
    revoke.add_argument(
        "--env", required=True, choices=("alpha", "beta", "gamma", "prod")
    )
    revoke.add_argument("--release-id", required=True)
    revoke.add_argument("--lease-id", required=True)
    revoke.add_argument("--acquire-event-ref", required=True)
    revoke.add_argument("--event-id", default="")
    revoke.set_defaults(handler=owner.handle_acceptance_lease)

    reset_canonical = commands.add_parser(
        "reset-canonical",
        help="在空基线 full-sync 回执后清空 canonical publish 输出",
    )
    reset_canonical.add_argument("--empty-baseline-release", required=True)
    reset_canonical.add_argument(
        "--env", required=True, help="已应用空基线的目标环境，逗号分隔"
    )
    reset_canonical.set_defaults(handler=owner.handle_reset_canonical)

    attest = commands.add_parser(
        "attest", help="校验 immutable release 的唯一 aggregate attestation"
    )
    attest.add_argument("--release-id", required=True)
    attest.add_argument("--release-root")
    attest.set_defaults(handler=owner.handle_attest_release)

    research_promote = commands.add_parser(
        "research-promote-scale",
        help="由累计唯一对象、引用闭包与 milestone 最终门写 create-once promotion receipt",
    )
    research_promote.add_argument("--release-id", required=True)
    research_promote.add_argument("--promotion-id", required=True)
    research_promote.add_argument(
        "--target-scale", required=True, choices=("M100", "M1000", "M10000")
    )
    research_promote.add_argument("--predecessor-promotion")
    research_promote.add_argument(
        "--m100-alpha-acceptance-binding",
        help=(
            "M1000 promotion：由 canonical binder 生成的 exact Alpha M100 "
            "acceptance binding；与两份 receipt 参数互斥"
        ),
    )
    research_promote.add_argument(
        "--m100-alpha-readiness-receipt",
        help=(
            "M1000 promotion：同一 M100 Research release 的 Alpha "
            "activation/readback receipt"
        ),
    )
    research_promote.add_argument(
        "--m100-alpha-app-uat-receipt",
        help="M1000 promotion：同一 M100 Research release 的 100-case App UAT receipt",
    )
    research_promote.add_argument(
        "--campaign-evidence",
        help=(
            "可选 campaign 诊断；缺失、failed 或漂移均不影响 immutable "
            "milestone release 的 promotion 硬门"
        ),
    )
    research_promote.add_argument("--release-root")
    research_promote.add_argument("--output-root")
    research_promote.set_defaults(handler=owner.handle_research_scale_promotion)

    commercial_transition = commands.add_parser(
        "commercial-transition",
        help="从 research/commercial release 与四环境清理回读写逐资产迁移 receipt",
    )
    commercial_transition.add_argument("--research-release-id", required=True)
    commercial_transition.add_argument("--commercial-release-id", required=True)
    commercial_transition.add_argument("--run-id", required=True)
    commercial_transition.add_argument("--cleanup-evidence", required=True)
    commercial_transition.add_argument("--release-root")
    commercial_transition.add_argument("--output-root")
    commercial_transition.set_defaults(handler=owner.handle_commercial_transition)

    gc = commands.add_parser(
        "gc",
        help="按 execution/retry/release/publish 可达性审计并回收派生输出",
    )
    gc_actions = gc.add_subparsers(dest="release_gc_action", required=True)
    gc_plan = gc_actions.add_parser("plan", help="只写 create-once GC 计划，不删除输出")
    gc_plan.add_argument("--plan-id", required=True)
    gc_plan.add_argument("--min-age-hours", type=float, default=168.0)
    gc_plan.add_argument("--output-root")
    gc_plan.add_argument("--publish-root")
    gc_plan.add_argument("--release-root")
    gc_plan.set_defaults(handler=owner.handle_gc_plan)
    gc_apply = gc_actions.add_parser("apply", help="复核可达性并应用指定 plan digest")
    gc_apply.add_argument("--plan-id", required=True)
    gc_apply.add_argument("--plan-digest", required=True)
    gc_apply.add_argument("--output-root")
    gc_apply.add_argument("--publish-root")
    gc_apply.add_argument("--release-root")
    gc_apply.set_defaults(handler=owner.handle_gc_apply)

    scale_evidence = commands.add_parser(
        "campaign-scale-evidence",
        help="从四 lane canonical 真相源派生累计 research scale evidence",
    )
    scale_evidence.add_argument("--evidence-id", required=True)
    scale_evidence.add_argument("--release-id", required=True)
    scale_evidence.add_argument(
        "--target-scale", required=True, choices=("M100", "M1000", "M10000")
    )
    scale_evidence.add_argument("--predecessor-promotion")
    scale_evidence.add_argument("--campaign-plan", required=True)
    scale_evidence.add_argument(
        "--runtime-session",
        help="可选 runtime/resource/fault 诊断 session；缺失或失败不阻断 promotion",
    )
    scale_evidence.add_argument(
        "--calibration-preflight-receipt",
        required=True,
        help="sol_calibration startup receipt；resource soak 另为可选诊断",
    )
    scale_evidence.add_argument("--tasks-root")
    scale_evidence.add_argument("--release-root")
    scale_evidence.add_argument("--output-root")
    scale_evidence.set_defaults(handler=owner.handle_campaign_scale_evidence)
