"""CLI registration for release environment operations."""

from __future__ import annotations

import argparse
import re

from content.release.environment.handler import VALID_ENVS, handle_ship
from core.control_types import ReleaseRunKind
from verify.release_publishability import READINESS_PHASES

_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _manifest_digest(value: str) -> str:
    if not _SHA256_DIGEST.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "must match sha256:<64 lowercase hexadecimal characters>"
        )
    return value


def _add_release_admission_arguments(parser: argparse.ArgumentParser) -> None:
    admission = parser.add_mutually_exclusive_group(required=True)
    admission.add_argument(
        "--handoff-ref",
        help=(
            "authoritative handoff-ref-v1；authority artifacts 必须恰好定位一个 "
            "ProducerReleaseHandoff portable artifact"
        ),
    )
    admission.add_argument(
        "--system-attestation-ref",
        help=(
            "empty_baseline 的 canonical system attestation；必须与 "
            "--system-attestation-digest 成对"
        ),
    )
    parser.add_argument(
        "--system-attestation-digest",
        type=_manifest_digest,
        help="empty baseline system attestation exact bytes 的 sha256 摘要",
    )


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "ship",
        help="只读 immutable release 并写 append-only 环境执行证据",
    )
    commands = parser.add_subparsers(dest="ship_command", required=True)
    apply = commands.add_parser(
        ReleaseRunKind.APPLY,
        help="执行已存在 release；禁止 promote/index/sample/canonical 写入",
    )
    _add_release_admission_arguments(apply)
    apply.add_argument(
        "--env",
        required=True,
        choices=sorted(VALID_ENVS),
        help="单一目标环境；alpha、beta、gamma 或 prod",
    )
    apply.add_argument("--run-id", help="append-only run id（默认 UTC 时间）")
    apply.add_argument("--import", dest="import_to_db", action="store_true")
    apply.add_argument(
        "--full-sync",
        action="store_true",
        help="按 release desired state tombstone 缺失对象；所有 immutable release 必须使用",
    )
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument("--confirm-prod-apply", action="store_true")
    apply.set_defaults(handler=handle_ship)

    activate = commands.add_parser(
        ReleaseRunKind.ACTIVATE,
        help="消费 prepared apply 的候选证明并执行 Content CAS 激活",
    )
    _add_release_admission_arguments(activate)
    activate.add_argument("--env", required=True, choices=sorted(VALID_ENVS))
    activate.add_argument("--import-run-id", required=True)
    activate.add_argument("--run-id")
    activate.add_argument("--confirm-prod-apply", action="store_true")
    activate.set_defaults(handler=handle_ship)

    rollback = commands.add_parser(
        ReleaseRunKind.ROLLBACK, help="按 immutable release desired state 重放回滚"
    )
    _add_release_admission_arguments(rollback)
    rollback.add_argument("--from-release-id", required=True)
    rollback.add_argument(
        "--from-manifest-digest",
        required=True,
        type=_manifest_digest,
        help="当前 Content active pointer 的 manifest 摘要；仅作为对查询结果的 asserted intent",
    )
    rollback.add_argument("--env", required=True, choices=sorted(VALID_ENVS))
    rollback.add_argument("--run-id")
    rollback.add_argument("--import", dest="import_to_db", action="store_true")
    rollback.add_argument("--dry-run", action="store_true")
    rollback.add_argument("--confirm-prod-apply", action="store_true")
    rollback.set_defaults(handler=handle_ship)

    verify = commands.add_parser(
        ReleaseRunKind.VERIFY,
        help="从环境导入回执逐主页及逐帖子验证公开消费 API",
    )
    _add_release_admission_arguments(verify)
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
