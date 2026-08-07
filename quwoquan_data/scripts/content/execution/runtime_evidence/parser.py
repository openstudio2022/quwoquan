"""Argument registration for the runtime-evidence task facade."""
from __future__ import annotations

import argparse
from collections.abc import Callable

from content.execution.runtime_evidence.contract import CARRIERS

RuntimeEvidenceHandler = Callable[[argparse.Namespace], None]


def register_runtime_evidence_action_parsers(
    subparsers: argparse._SubParsersAction,
    *,
    create_session_handler: RuntimeEvidenceHandler,
    sample_handler: RuntimeEvidenceHandler,
    worker_termination_handler: RuntimeEvidenceHandler,
    lease_expiry_handler: RuntimeEvidenceHandler,
    redis_restart_handler: RuntimeEvidenceHandler,
    mongo_reconnect_handler: RuntimeEvidenceHandler,
    provider_timeout_handler: RuntimeEvidenceHandler,
    provider_rate_limit_handler: RuntimeEvidenceHandler,
    finalize_handler: RuntimeEvidenceHandler,
) -> None:
    """Register the fixed, selector-free runtime-evidence action tree."""
    parser = subparsers.add_parser(
        "runtime-evidence",
        help="从当前 fenced campaign 采集 create-once runtime evidence",
    )
    actions = parser.add_subparsers(dest="runtime_evidence_action", required=True)

    create = actions.add_parser(
        "create-session",
        help="冻结当前 controller、四 lane、queue 与内置故障 adapter",
    )
    _add_session_identity(create)
    create.set_defaults(handler=create_session_handler)

    sample = actions.add_parser(
        "sample",
        help="从固定 OS、queue 与 workspace observer 采样",
    )
    _add_session_identity(sample)
    sample.add_argument("--sample-id", required=True)
    sample.set_defaults(handler=sample_handler)

    inject = actions.add_parser(
        "inject-worker-termination",
        help="仅终止 session 已冻结的一条 worker process group",
    )
    _add_fault_target(inject)
    inject.add_argument(
        "--confirm-active-worker-termination",
        action="store_true",
        required=True,
        help="确认对当前 fenced worker 执行受治理的 process-group 终止",
    )
    inject.set_defaults(handler=worker_termination_handler)

    fixed_fault_actions = (
        ("inject-lease-expiry", lease_expiry_handler),
        ("inject-redis-restart", redis_restart_handler),
        ("inject-mongo-reconnect", mongo_reconnect_handler),
        ("inject-provider-timeout", provider_timeout_handler),
        ("inject-provider-rate-limit", provider_rate_limit_handler),
    )
    for name, handler in fixed_fault_actions:
        fixed = actions.add_parser(
            name,
            help=f"创建固定 {name.removeprefix('inject-')} typed fault request",
        )
        _add_fault_target(fixed)
        fixed.add_argument(
            "--confirm-governed-fault-request",
            action="store_true",
            required=True,
            help="确认创建受治理 fault intent；无 owner callback 时 fail closed",
        )
        fixed.set_defaults(handler=handler)

    finalize = actions.add_parser(
        "finalize",
        help="在 campaign 终态后投影 resource/fault raw evidence",
    )
    _add_session_identity(finalize)
    finalize.set_defaults(handler=finalize_handler)


def _add_session_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-root-execution-id", required=True)
    parser.add_argument("--session-id", required=True)


def _add_fault_target(parser: argparse.ArgumentParser) -> None:
    _add_session_identity(parser)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--carrier", required=True, choices=CARRIERS)
    parser.add_argument("--job-id", required=True)
