"""Argparse composition for canonical immutable release commands."""
from __future__ import annotations

import argparse

from content.release.canonical import handler as owner


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("release", help="构建不可变的通用内容发布包")
    commands = parser.add_subparsers(dest="release_command", required=True)

    pool_build = commands.add_parser(
        "pool-build",
        help="从显式 immutable cohort 构建 Research/Commercial release",
    )
    pool_build.add_argument("--release-id", required=True)
    pool_build.add_argument("--cohort-file", required=True)
    pool_build.add_argument(
        "--release-class",
        choices=("research", "commercial"),
        required=True,
    )
    pool_build.add_argument("--publish-root")
    pool_build.add_argument("--release-root")
    pool_build.set_defaults(handler=owner.handle_pool_release_build)

    handoff = commands.add_parser(
        "handoff",
        help="在 release CLOSE 后 create-once 物化 producer terminal handoff",
    )
    handoff.add_argument("--release-id", required=True)
    handoff.add_argument("--cohort-file", required=True)
    handoff.add_argument(
        "--milestone",
        choices=("M1", "M10", "M100", "M1000", "M10000"),
        required=True,
    )
    handoff.add_argument("--producer-baseline-revision", required=True)
    handoff.add_argument("--publish-root")
    handoff.add_argument("--release-root")
    handoff.set_defaults(handler=owner.handle_producer_release_handoff)

    publish_object = commands.add_parser(
        "publish-object",
        help="校验并原子发布 target_set 中一个明确对象",
    )
    publish_object.add_argument("--execution-id", required=True)
    publish_object.add_argument("--target-ref", required=True)
    publish_object.add_argument("--apply", action="store_true")
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

    build_lookups = commands.add_parser(
        "build-lookups",
        help="为 immutable release 生成 create-once first-consumer lookup indexes",
    )
    build_lookups.add_argument("--release-id", required=True)
    build_lookups.add_argument("--publish-root")
    build_lookups.add_argument("--release-root")
    build_lookups.add_argument("--taxonomy-root")
    build_lookups.set_defaults(handler=owner.handle_build_lookup_indexes)

    reset_canonical = commands.add_parser(
        "reset-canonical",
        help="在空基线 full-sync 回执后清空 canonical publish 输出",
    )
    reset_canonical.add_argument("--empty-baseline-release", required=True)
    reset_canonical.add_argument(
        "--env", required=True, help="已应用空基线的目标环境，逗号分隔"
    )
    reset_canonical.set_defaults(handler=owner.handle_reset_canonical)
