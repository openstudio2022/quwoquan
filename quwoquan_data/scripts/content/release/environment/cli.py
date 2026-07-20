"""CLI registration for release environment operations."""
from __future__ import annotations
import argparse
from content.release.environment.handler import VALID_ENVS, handle_ship
from core.control_types import ReleaseRunKind

def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "ship",
        help="只读 immutable release 并写 append-only 环境执行证据",
    )
    commands = parser.add_subparsers(dest="ship_command", required=True)
    apply = commands.add_parser(ReleaseRunKind.APPLY, help="执行已存在 release；禁止 promote/index/sample/canonical 写入")
    apply.add_argument("--release-id", required=True)
    apply.add_argument("--env", required=True, help="alpha,beta,gamma,prod；生产仅 prod")
    apply.add_argument("--run-id", help="append-only run id（默认 UTC 时间）")
    apply.add_argument("--import", dest="import_to_db", action="store_true")
    apply.add_argument(
        "--full-sync",
        action="store_true",
        help="按 release desired state tombstone 缺失对象；baseline/canary/M1/M2/M3/H10K 强制使用",
    )
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument("--confirm-prod-apply", action="store_true")
    apply.set_defaults(handler=handle_ship)

    rollback = commands.add_parser(ReleaseRunKind.ROLLBACK, help="按 immutable release desired state 重放回滚")
    rollback.add_argument("--to-release", required=True)
    rollback.add_argument("--from-release-id", required=True)
    rollback.add_argument("--env", required=True, choices=sorted(VALID_ENVS))
    rollback.add_argument("--run-id")
    rollback.add_argument("--import", dest="import_to_db", action="store_true")
    rollback.add_argument("--dry-run", action="store_true")
    rollback.add_argument("--confirm-prod-apply", action="store_true")
    rollback.set_defaults(handler=handle_ship)

    verify = commands.add_parser(
        ReleaseRunKind.VERIFY,
        help="从环境导入回执逐主页验证 detail/introduction API",
    )
    verify.add_argument("--release-id", required=True)
    verify.add_argument("--env", required=True, choices=sorted(VALID_ENVS))
    verify.add_argument("--import-run-id", required=True)
    verify.add_argument("--run-id")
    verify.set_defaults(handler=handle_ship)
