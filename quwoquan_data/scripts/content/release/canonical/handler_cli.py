"""Argparse composition for canonical immutable release commands."""
from __future__ import annotations

import argparse



def register_parser(subparsers: argparse._SubParsersAction) -> None:
    from content.release.canonical import handler as owner
    parser = subparsers.add_parser("release", help="构建不可变的通用内容发布包")
    commands = parser.add_subparsers(dest="release_command", required=True)

    finalize = commands.add_parser(
        "finalize",
        help="一次完成 pool-build、release-integrity 与 create-once producer handoff",
    )
    finalize.add_argument("--release-id", required=True)
    finalize.add_argument("--cohort-file", required=True)
    finalize.add_argument(
        "--milestone",
        choices=("M1", "M10", "M100", "M1000", "M10000"),
        required=True,
    )
    finalize.add_argument("--producer-baseline-revision", required=True)
    finalize.add_argument("--publish-root")
    finalize.add_argument("--release-root")
    finalize.add_argument(
        "--reference-root",
        help="cohort/handoff 版本化副本根（缺省 quwoquan_data/reference/releases）；只是耐久备份，handoff-verify 不读它",
    )
    finalize.set_defaults(handler=owner.handle_release_finalize)

    handoff_verify = commands.add_parser(
        "handoff-verify",
        help="只读重放 producer handoff 内嵌事实并逐项比对 sealed release",
    )
    handoff_verify.add_argument("--release-id", required=True)
    handoff_verify.add_argument("--release-root")
    handoff_verify.set_defaults(handler=owner.handle_handoff_verify)

    pool_query = commands.add_parser(
        "pool-query",
        help="只读列出 canonical publish 池中可入 cohort 的对象与排除原因（不做选择）",
    )
    pool_query.add_argument("--publish-root")
    pool_query.add_argument("--json", dest="json_output", help="把完整结果写到该路径；stdout 只打印计数")
    pool_query.set_defaults(handler=owner.handle_pool_query)

    acceptance_lease = commands.add_parser(
        "acceptance-lease",
        help="管理 Data-owned 环境验收 lease 的 append-only acquire/revoke 事件",
    )
    lease_actions = acceptance_lease.add_subparsers(
        dest="acceptance_lease_action",
        required=True,
    )
    lease_acquire = lease_actions.add_parser("acquire")
    lease_acquire.add_argument("--env", required=True)
    lease_acquire.add_argument("--release-id", required=True)
    lease_acquire.add_argument("--lease-id", required=True)
    lease_acquire.add_argument("--import-run-id", required=True)
    lease_acquire.add_argument("--verify-run-id", required=True)
    lease_acquire.add_argument("--ttl-seconds", type=int, default=3600)
    lease_acquire.add_argument("--event-id", default="")
    lease_acquire.set_defaults(handler=_load_acceptance_lease)
    lease_revoke = lease_actions.add_parser("revoke")
    lease_revoke.add_argument("--env", required=True)
    lease_revoke.add_argument("--release-id", required=True)
    lease_revoke.add_argument("--lease-id", required=True)
    lease_revoke.add_argument("--acquire-event-ref", required=True)
    lease_revoke.add_argument("--event-id", default="")
    lease_revoke.set_defaults(handler=_load_acceptance_lease)

    lifecycle_exit = commands.add_parser(
        "lifecycle-exit",
        help="从 exact activate/verify/rollback/replay 结果签发 canonical Exit",
    )
    lifecycle_exit.add_argument("--env", required=True)
    lifecycle_exit.add_argument("--original-release-id", required=True)
    lifecycle_exit.add_argument(
        "--original-import-run-id", required=True,
        help="original 成功 activate run；由其 importRunId 重验 prepared apply",
    )
    lifecycle_exit.add_argument("--original-verify-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-to-release-id", required=True)
    lifecycle_exit.add_argument("--rollback-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-verify-run-id", required=True)
    lifecycle_exit.add_argument(
        "--replay-import-run-id", required=True,
        help="same-digest replay 成功 activate run，不接受 prepared apply run",
    )
    lifecycle_exit.add_argument("--replay-verify-run-id", required=True)
    lifecycle_exit.add_argument("--run-id", required=True)
    lifecycle_exit.set_defaults(handler=_load_lifecycle_exit)

    publish_object = commands.add_parser(
        "publish-object",
        help="对一个 approved 对象执行唯一一次原子 canonical 事务（已发布则 exact replay）",
    )
    publish_object.add_argument("--execution-id", required=True)
    publish_object.add_argument("--target-ref", required=True)
    publish_object.set_defaults(handler=owner.handle_publish_object)

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
        handler=_load_object_transaction_rollback
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
        handler=_load_object_transaction_replay_package
    )

    build_lookups = commands.add_parser(
        "build-lookups",
        help="为 immutable release 生成 create-once first-consumer lookup indexes",
    )
    build_lookups.add_argument("--release-id", required=True)
    build_lookups.add_argument("--publish-root")
    build_lookups.add_argument("--release-root")
    build_lookups.add_argument("--taxonomy-root")
    build_lookups.set_defaults(handler=_load_build_lookup_indexes)

    reset_canonical = commands.add_parser(
        "reset-canonical",
        help="在空基线 full-sync 回执后清空 canonical publish 输出",
    )
    reset_canonical.add_argument("--empty-baseline-release", required=True)
    reset_canonical.add_argument(
        "--env", required=True, help="已应用空基线的目标环境，逗号分隔"
    )
    reset_canonical.set_defaults(handler=_load_reset_canonical)


def _load_object_transaction_rollback(args: argparse.Namespace) -> None:
    from content.release.canonical.handler_consumers import (
        handle_object_transaction_rollback,
    )

    handle_object_transaction_rollback(args)


def _load_object_transaction_replay_package(args: argparse.Namespace) -> None:
    from content.release.canonical.handler_consumers import (
        handle_object_transaction_replay_package,
    )

    handle_object_transaction_replay_package(args)


def _load_build_lookup_indexes(args: argparse.Namespace) -> None:
    from content.release.canonical.handler_consumers import handle_build_lookup_indexes

    handle_build_lookup_indexes(args)


def _load_reset_canonical(args: argparse.Namespace) -> None:
    from content.release.canonical.reset import handle_reset_canonical

    handle_reset_canonical(args)


def _load_acceptance_lease(args: argparse.Namespace) -> None:
    from content.release.canonical.acceptance_lease import handle_acceptance_lease

    handle_acceptance_lease(args)


def _load_lifecycle_exit(args: argparse.Namespace) -> None:
    from content.release.canonical.lifecycle_exit import handle_lifecycle_exit

    handle_lifecycle_exit(args)
