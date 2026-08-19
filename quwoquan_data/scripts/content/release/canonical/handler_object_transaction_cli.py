"""Argparse bindings for canonical object transaction operations."""

from __future__ import annotations

import argparse


def register_object_transaction_parser(
    commands: argparse._SubParsersAction,
    *,
    owner: object,
) -> None:
    object_transaction = commands.add_parser(
        "object-transaction",
        help="按审计 delta 与 canonical Merkle 管理单一对象事务",
    )
    actions = object_transaction.add_subparsers(
        dest="object_transaction_action",
        required=True,
    )
    adoption = actions.add_parser(
        "adopt-post-metadata",
        help="从已审核 source transaction package 前向创建 Post metadata successor",
    )
    adoption.add_argument("--adoption-id", required=True)
    adoption.add_argument("--source-execution-root", required=True)
    adoption.add_argument("--source-package-root", required=True)
    adoption.add_argument("--output-root")
    adoption.add_argument("--publish-root")
    adoption.add_argument(
        "--apply",
        action="store_true",
        help="显式执行 audit/apply；省略时只准备并验证 successor package",
    )
    adoption.set_defaults(handler=owner.handle_post_metadata_adoption)

    replay = actions.add_parser(
        "replay-package",
        help="从显式 media-library holdings 精确重放已审核 object transaction package",
    )
    replay.add_argument("--replay-id", required=True)
    replay.add_argument("--source-package-root", required=True)
    replay.add_argument("--media-library-root", required=True)
    replay.add_argument("--output-root")
    replay.add_argument("--publish-root")
    replay.set_defaults(handler=owner.handle_object_transaction_package_replay)

    rollback = actions.add_parser(
        "rollback",
        help="按精确 inverse delta 回滚一笔已应用对象事务并保留回执",
    )
    rollback.add_argument("--transaction-id", required=True)
    rollback.add_argument("--output-root")
    rollback.add_argument("--publish-root")
    rollback.set_defaults(handler=owner.handle_object_transaction_rollback)


__all__ = ["register_object_transaction_parser"]
