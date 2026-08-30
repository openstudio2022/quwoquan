"""Canonical CLI binding for the measurement-only capacity bootstrap."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.execution.planning.capacity_bootstrap import (
    CapacityBootstrapError,
    build_capacity_bootstrap_composition,
)


def _emit(command: str, action) -> None:
    try:
        result = action()
    except (OSError, TypeError, ValueError, CapacityBootstrapError) as exc:
        code = (
            exc.code
            if isinstance(exc, CapacityBootstrapError)
            else "DATA.CAPACITY.BOOTSTRAP_COMMAND_FAILED"
        )
        raise SystemExit(
            f"[task capacity-bootstrap {command}] GATE_BLOCK {code}: {exc}"
        ) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _handle_prepare(args: argparse.Namespace) -> None:
    composition = build_capacity_bootstrap_composition()
    _emit(
        "prepare",
        lambda: composition.command_writer.prepare(
            bootstrap_run_id=str(args.bootstrap_run_id),
            host_class=str(args.host_class),
            provider_tier=str(args.provider_tier),
            semantic_selection_id=str(args.semantic_selection_id),
            workload_digest=str(args.workload_digest),
            retry_of=str(args.retry_of) if args.retry_of else None,
        ),
    )


def _handle_run(args: argparse.Namespace) -> None:
    composition = build_capacity_bootstrap_composition()
    _emit(
        "run",
        lambda: composition.command_writer.run(str(args.bootstrap_run_id)),
    )


def _handle_finalize(args: argparse.Namespace) -> None:
    composition = build_capacity_bootstrap_composition()
    _emit(
        "finalize",
        lambda: composition.command_writer.finalize(
            str(args.bootstrap_run_id),
            evidence_path=Path(args.evidence).expanduser().resolve(),
        ),
    )


def _handle_cancel(args: argparse.Namespace) -> None:
    composition = build_capacity_bootstrap_composition()
    _emit(
        "cancel",
        lambda: composition.command_writer.cancel(
            str(args.bootstrap_run_id), reason=str(args.reason)
        ),
    )


def _handle_status(args: argparse.Namespace) -> None:
    composition = build_capacity_bootstrap_composition()
    _emit(
        "status",
        lambda: composition.status_query.get(str(args.bootstrap_run_id)),
    )


def register_capacity_bootstrap_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "capacity-bootstrap",
        help="以 measurement-only 单 worker process manager 生成容量测量证据",
    )
    commands = parser.add_subparsers(dest="capacity_bootstrap_command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--bootstrap-run-id", required=True)
    prepare.add_argument("--host-class", required=True)
    prepare.add_argument("--provider-tier", required=True)
    prepare.add_argument("--semantic-selection-id", required=True, choices=("cursor_grok",))
    prepare.add_argument("--workload-digest", required=True)
    prepare.add_argument("--retry-of")
    prepare.set_defaults(handler=_handle_prepare)

    run = commands.add_parser("run")
    run.add_argument("--bootstrap-run-id", required=True)
    run.set_defaults(handler=_handle_run)

    finalize = commands.add_parser("finalize")
    finalize.add_argument("--bootstrap-run-id", required=True)
    finalize.add_argument("--evidence", required=True)
    finalize.set_defaults(handler=_handle_finalize)

    cancel = commands.add_parser("cancel")
    cancel.add_argument("--bootstrap-run-id", required=True)
    cancel.add_argument("--reason", required=True)
    cancel.set_defaults(handler=_handle_cancel)

    status = commands.add_parser("status")
    status.add_argument("--bootstrap-run-id", required=True)
    status.set_defaults(handler=_handle_status)


__all__ = ["register_capacity_bootstrap_parser"]
