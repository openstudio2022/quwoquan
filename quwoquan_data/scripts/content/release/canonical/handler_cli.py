"""Argparse composition for canonical immutable release commands."""
from __future__ import annotations

import argparse

from content.release.canonical import handler as owner
from content.release.canonical.handler_identity_cli import register_identity_parsers
from content.release.canonical.handler_uat_cli import register_uat_parsers
from core.control_types import PoolObjectRetirementReason


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("release", help="构建不可变的通用内容发布包")
    commands = parser.add_subparsers(dest="release_command", required=True)

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
        "--all-publishable",
        action="store_true",
        help="冻结当前全部 publishable 对象的环境无关日常 release",
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
    pool_build.add_argument(
        "--sampling-authority-artifact-root",
        help="M1000 projected authority exact ref 的只读根；仅 M1000 使用",
    )
    pool_build.add_argument(
        "--sampling-authority-ref",
        help="M1000 projected authority repo/output-relative exact ref",
    )
    pool_build.add_argument(
        "--sampling-authority-digest",
        help="M1000 projected authority exact-byte sha256 digest",
    )
    pool_build.set_defaults(handler=owner.handle_pool_release_build)

    contract_migrate = commands.add_parser(
        "contract-migrate",
        help=(
            "只读预检或从旧不可变 release 的 canonical payload 构建新合同 release；"
            "绝不修改源 release"
        ),
    )
    contract_migrate.add_argument("--source-release-id", required=True)
    contract_migrate.add_argument("--new-release-id", required=True)
    contract_migrate.add_argument("--release-root")
    contract_migrate.add_argument(
        "--apply",
        action="store_true",
        help="显式创建新的 immutable release；省略时只运行 fail-closed precheck",
    )
    contract_migrate.set_defaults(handler=owner.handle_release_contract_migration)

    pool_precheck = commands.add_parser(
        "pool-precheck",
        help="只读复用 pool-build 真实判据链判定可选中集；不写任何 release 产物",
    )
    pool_precheck.add_argument(
        "--milestone",
        choices=("M100", "M1000", "M10000"),
        required=True,
    )
    pool_precheck.add_argument(
        "--release-class",
        choices=("research", "commercial"),
        default="research",
        help="载体判据段的发布类别；milestone 段按契约恒为 research",
    )
    pool_precheck.add_argument(
        "--details",
        action="store_true",
        help="输出逐条可选中 postRef 与全部 typed 排除原因",
    )
    pool_precheck.add_argument("--publish-root")
    pool_precheck.set_defaults(handler=owner.handle_pool_precheck)

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

    publish_execution = commands.add_parser(
        "publish-execution",
        help="receipt 协议 publish 原子链：物化 approved 对象并经单对象事务写 canonical（DEC-027）",
    )
    publish_execution.add_argument("--execution-id", required=True)
    publish_execution.add_argument(
        "--apply",
        action="store_true",
        help="显式执行物化与 canonical 写入；省略时只校验并输出 plan 结果",
    )
    publish_execution.set_defaults(handler=owner.handle_publish_execution)

    pool_object = commands.add_parser(
        "pool-object",
        help="对池内单个对象的逐对象操作",
    )
    pool_object_actions = pool_object.add_subparsers(
        dest="pool_object_action", required=True
    )
    pool_object_retire = pool_object_actions.add_parser(
        "retire",
        help=(
            "为已被 discovery 层判否且无入池事务回执的历史对象写 create-once "
            "退役回执；只写回执，不改写 manifest、generator 与审核回执"
        ),
    )
    pool_object_retire.add_argument(
        "--object-type", choices=("homepage", "content"), required=True
    )
    pool_object_retire.add_argument(
        "--object-ref",
        required=True,
        help="对象在 posts/ 或 entities/ 下的相对 ref",
    )
    pool_object_retire.add_argument(
        "--reason",
        choices=tuple(member.value for member in PoolObjectRetirementReason),
        required=True,
    )
    pool_object_retire.add_argument(
        "--retired-at",
        required=True,
        metavar="YYYY-MM-DDTHH:MM:SSZ",
        help="显式退役时刻；create-once 重入必须复算出同一份回执，故不读进程时钟",
    )
    pool_object_retire.add_argument("--publish-root")
    pool_object_retire.add_argument(
        "--apply",
        action="store_true",
        help="显式写入；省略时只校验判据并输出 plan 结果",
    )
    pool_object_retire.set_defaults(handler=owner.handle_pool_object_retire)

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
    object_transaction_replay = object_transaction_actions.add_parser(
        "replay-package",
        help="用显式内容库持仓精确重放一笔已评审的对象事务包",
    )
    object_transaction_replay.add_argument("--replay-id", required=True)
    object_transaction_replay.add_argument("--source-package-root", required=True)
    object_transaction_replay.add_argument("--media-library-root", required=True)
    object_transaction_replay.add_argument("--output-root")
    object_transaction_replay.add_argument("--publish-root")
    object_transaction_replay.set_defaults(
        handler=owner.handle_object_transaction_replay_package
    )

    register_identity_parsers(commands, owner=owner)

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

    register_uat_parsers(commands, owner=owner)

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
    gc_backfill = gc_actions.add_parser(
        "backfill-tombstones",
        help="为墓碑协议之前已被移除的被引用 execution 补写终态墓碑",
    )
    gc_backfill.add_argument("--backfill-id", required=True)
    gc_backfill.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出无终态的 execution 引用，不写任何墓碑",
    )
    gc_backfill.add_argument("--output-root")
    gc_backfill.add_argument("--publish-root")
    gc_backfill.add_argument("--release-root")
    gc_backfill.set_defaults(handler=owner.handle_gc_backfill_tombstones)
