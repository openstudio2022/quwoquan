"""CLI registration for release environment operations."""
from __future__ import annotations

import argparse

from content.release.environment.handler import VALID_ENVS, handle_ship
from core.control_types import ReleaseRunKind
from verify.release_publishability import READINESS_PHASES


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "ship",
        help="只读 immutable release 并写 append-only 环境执行证据",
    )
    commands = parser.add_subparsers(dest="ship_command", required=True)
    apply = commands.add_parser(
        ReleaseRunKind.APPLY,
        help="单环境 import-only：只写 Content 候选与 additive 引用对象，不切 active pointer",
    )
    apply.add_argument("--release-id", required=True)
    apply.add_argument("--env", required=True, choices=sorted(VALID_ENVS))
    apply.add_argument("--run-id", help="append-only run id（默认 UTC 时间）")
    apply.add_argument("--import", dest="import_to_db", action="store_true")
    apply.add_argument(
        "--full-sync",
        action="store_true",
        help="按 release desired state tombstone 缺失对象；删除/下线只在 activate 成功后执行",
    )
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument("--confirm-prod-apply", action="store_true")
    apply.set_defaults(handler=handle_ship)

    activate = commands.add_parser(
        ReleaseRunKind.ACTIVATE,
        help="绑定 stage + 候选 verify 的同一 candidateRevision，单事务切换 Content active pointer",
    )
    activate.add_argument("--release-id", required=True)
    activate.add_argument("--env", required=True, choices=sorted(VALID_ENVS))
    activate.add_argument("--import-run-id", required=True, help="已完成的 stage run")
    activate.add_argument("--verify-run-id", required=True, help="已通过的候选 verify run")
    activate.add_argument("--run-id")
    activate.add_argument(
        "--expected-revision",
        type=int,
        required=True,
        help="调用方观测到的 Content active pointer revision；首次激活为 0",
    )
    activate.add_argument("--confirm-prod-apply", action="store_true")
    activate.set_defaults(handler=handle_ship)

    rollback = commands.add_parser(ReleaseRunKind.ROLLBACK, help="按 immutable release desired state 重放回滚")
    rollback.add_argument("--to-release", required=True)
    rollback.add_argument("--from-release-id", required=True)
    rollback.add_argument("--env", required=True, choices=sorted(VALID_ENVS))
    rollback.add_argument("--run-id")
    rollback.add_argument("--import", dest="import_to_db", action="store_true")
    rollback.add_argument("--dry-run", action="store_true")
    rollback.add_argument(
        "--expected-revision",
        type=int,
        default=0,
        help="回滚前调用方观测到的 Content active pointer revision；显式历史切换必须传当前值",
    )
    rollback.add_argument("--confirm-prod-apply", action="store_true")
    rollback.set_defaults(handler=handle_ship)

    verify = commands.add_parser(
        ReleaseRunKind.VERIFY,
        help=(
            "--import-run-id 指向 stage run 时读回受保护候选闭包；指向 activate run "
            "时逐主页及逐帖子验证公开消费 API"
        ),
    )
    verify.add_argument("--release-id", required=True)
    verify.add_argument("--env", required=True, choices=sorted(VALID_ENVS))
    verify.add_argument("--import-run-id", required=True)
    verify.add_argument("--run-id")
    verify.add_argument(
        "--previous-environment-readiness",
        default="",
        help=(
            "Beta/Gamma/Prod milestone Research activation 必需的前一环境 "
            "release-readiness.json（相对 QWQ_OUTPUT_ROOT）"
        ),
    )
    verify.add_argument(
        "--readiness-phase",
        choices=sorted(READINESS_PHASES),
        default="commercial",
        help=(
            "research 只接受受保护内部身份与私有短签媒体证据；consumer "
            "验证首页/载体/媒体；commercial 额外要求 product-ops premium_stream"
        ),
    )
    verify.add_argument(
        "--lifecycle-exit-ref",
        default="",
        help=(
            "commercial phase 必需的 canonical rollback/replay lifecycle Exit "
            "ref（相对 QWQ_OUTPUT_ROOT）"
        ),
    )
    verify.set_defaults(handler=handle_ship)
