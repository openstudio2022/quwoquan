"""CLI handlers for generic immutable content releases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.paths import OUTPUT_ROOT, PUBLISH_ROOT
from core.release_layout import attestation_root
from core.io import read_json
from content.release.canonical.aggregate_release import build_aggregate_release
from content.release.canonical.acceptance_lease import handle_acceptance_lease
from content.release.canonical.baseline_release import build_empty_baseline_release
from content.release.canonical.discard import handle_discard
from content.release.canonical.lifecycle_exit import handle_lifecycle_exit
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.release_operation_lock import (
    ReleaseOperationConflict,
    release_operation_guard,
    release_operation_lock_root,
)
from content.release.canonical.reset import handle_reset_canonical
from verify.verify_release_lifecycle import release_lifecycle_issues


def _execution_ids(raw_value: str) -> list[str]:
    execution_ids = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not execution_ids:
        raise SystemExit("[release aggregate] --execution-ids 不能为空")
    return execution_ids


def handle_aggregate_release(args: argparse.Namespace) -> None:
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases"))
    release_id = str(args.release_id)
    try:
        with release_operation_guard(
            lock_root=release_operation_lock_root(release_root),
            release_ids=(release_id,),
            exclusive_releases=True,
        ):
            report = build_aggregate_release(
                publish_root=Path(args.publish_root or PUBLISH_ROOT),
                release_root=release_root,
                release_id=release_id,
                execution_ids=_execution_ids(str(args.execution_ids)),
            )
    except (
        FileNotFoundError,
        ObjectTransactionError,
        ReleaseOperationConflict,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release aggregate] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_baseline_release(args: argparse.Namespace) -> None:
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases"))
    release_id = str(args.release_id)
    try:
        with release_operation_guard(
            lock_root=release_operation_lock_root(release_root),
            release_ids=(release_id,),
            exclusive_releases=True,
        ):
            report = build_empty_baseline_release(
                publish_root=Path(args.publish_root or PUBLISH_ROOT),
                release_root=release_root,
                release_id=release_id,
            )
    except (
        FileNotFoundError,
        ObjectTransactionError,
        ReleaseOperationConflict,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release baseline] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_attest_release(args: argparse.Namespace) -> None:
    release_root = Path(args.release_root or (OUTPUT_ROOT / "data/releases"))
    release_id = str(args.release_id)
    issues = release_lifecycle_issues(release_id, release_root=release_root)
    if issues:
        print(json.dumps({"releaseId": release_id, "attested": False, "issues": issues}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    aggregate = read_json(attestation_root(release_root / release_id) / "release.json")
    print(json.dumps({"releaseId": release_id, "attested": True, "attestation": aggregate}, ensure_ascii=False, indent=2))


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("release", help="构建不可变的通用内容发布包")
    commands = parser.add_subparsers(dest="release_command", required=True)

    aggregate = commands.add_parser(
        "aggregate", help="从 execution 闭包和 canonical publish 聚合发布包"
    )
    aggregate.add_argument("--release-id", required=True)
    aggregate.add_argument("--execution-ids", required=True, help="逗号分隔 executionId")
    aggregate.add_argument("--publish-root")
    aggregate.add_argument("--release-root")
    aggregate.set_defaults(handler=handle_aggregate_release)

    baseline = commands.add_parser(
        "baseline", help="创建仅用于 full-sync rollback 的空 desired-state 发布包"
    )
    baseline.add_argument("--release-id", required=True)
    baseline.add_argument("--publish-root")
    baseline.add_argument("--release-root")
    baseline.set_defaults(handler=handle_baseline_release)

    discard = commands.add_parser(
        "discard", help="删除无活跃写入的可重跑 release 输出及其环境证据"
    )
    discard.add_argument("--release-id", required=True)
    discard.set_defaults(handler=handle_discard)

    lifecycle_exit = commands.add_parser(
        "lifecycle-exit",
        help="从既有 original/rollback/replay run 写入 create-once Exit receipt",
    )
    lifecycle_exit.add_argument("--env", required=True, choices=("alpha", "beta", "gamma", "prod"))
    lifecycle_exit.add_argument("--original-release-id", required=True)
    lifecycle_exit.add_argument("--original-import-run-id", required=True)
    lifecycle_exit.add_argument("--original-verify-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-to-release-id", required=True)
    lifecycle_exit.add_argument("--rollback-run-id", required=True)
    lifecycle_exit.add_argument("--rollback-verify-run-id", required=True)
    lifecycle_exit.add_argument("--replay-import-run-id", required=True)
    lifecycle_exit.add_argument("--replay-verify-run-id", required=True)
    lifecycle_exit.add_argument("--run-id", required=True, help="append-only Exit run id")
    lifecycle_exit.set_defaults(handler=handle_lifecycle_exit)

    acceptance_lease = commands.add_parser(
        "acceptance-lease",
        help="为真实 UAT 写入 append-only acquire/revoke lease event",
    )
    lease_actions = acceptance_lease.add_subparsers(
        dest="acceptance_lease_action",
        required=True,
    )
    acquire = lease_actions.add_parser("acquire")
    acquire.add_argument("--env", required=True, choices=("alpha", "beta", "gamma", "prod"))
    acquire.add_argument("--release-id", required=True)
    acquire.add_argument("--import-run-id", required=True)
    acquire.add_argument("--verify-run-id", required=True)
    acquire.add_argument("--lease-id", required=True)
    acquire.add_argument("--event-id", default="")
    acquire.set_defaults(handler=handle_acceptance_lease)
    revoke = lease_actions.add_parser("revoke")
    revoke.add_argument("--env", required=True, choices=("alpha", "beta", "gamma", "prod"))
    revoke.add_argument("--release-id", required=True)
    revoke.add_argument("--lease-id", required=True)
    revoke.add_argument("--acquire-event-ref", required=True)
    revoke.add_argument("--event-id", default="")
    revoke.set_defaults(handler=handle_acceptance_lease)

    reset_canonical = commands.add_parser(
        "reset-canonical",
        help="在空基线 full-sync 回执后清空 canonical publish 输出",
    )
    reset_canonical.add_argument("--empty-baseline-release", required=True)
    reset_canonical.add_argument("--env", required=True, help="已应用空基线的目标环境，逗号分隔")
    reset_canonical.set_defaults(handler=handle_reset_canonical)

    attest = commands.add_parser("attest", help="校验 immutable release 的唯一 aggregate attestation")
    attest.add_argument("--release-id", required=True)
    attest.add_argument("--release-root")
    attest.set_defaults(handler=handle_attest_release)
