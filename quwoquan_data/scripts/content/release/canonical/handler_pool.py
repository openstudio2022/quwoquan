"""CLI handlers for canonical pool inspection, append, and release build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.release.canonical.aggregate_release import build_pool_release
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.pool_delivery_intent_inspection import (
    inspect_pool_delivery_intents,
)
from content.release.canonical.pool_inspection import inspect_pool
from content.release.canonical.pool_object_retirement import retire_pool_object
from content.release.canonical.pool_precheck import precheck_pool_release
from content.release.canonical.pool_source_ready_input import (
    load_p10_throughput,
    load_source_ready_input,
)
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT
from content.execution.planning.carrier_demand import normalize_workloads


def _workload_targets(values: tuple[str, ...]) -> dict[str, int] | None:
    if not values:
        return None
    result: dict[str, int] = {}
    for raw in values:
        carrier, separator, quota = raw.partition("=")
        carrier = carrier.strip()
        if not separator or carrier in result:
            raise ValueError("--workload must be unique CARRIER=QUOTA values")
        result[carrier] = int(quota.strip())
    return normalize_workloads(result)


def handle_pool_release_build(args: argparse.Namespace) -> None:
    output_root = Path(OUTPUT_ROOT).resolve()
    authority_values = (
        getattr(args, "sampling_authority_artifact_root", None),
        getattr(args, "sampling_authority_ref", None),
        getattr(args, "sampling_authority_digest", None),
    )
    if any(authority_values) and not all(authority_values):
        raise SystemExit(
            "[release pool-build] GATE_BLOCK M1000 sampling authority requires "
            "--sampling-authority-artifact-root, --sampling-authority-ref, and "
            "--sampling-authority-digest together"
        )
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    release_root = Path(
        args.release_root or output_root / "data/releases"
    ).resolve()
    try:
        report = build_pool_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id=str(args.release_id),
            target_environment=(
                str(args.target_environment)
                if getattr(args, "target_environment", None) is not None
                else None
            ),
            all_publishable=bool(getattr(args, "all_publishable", False)),
            milestone=(
                str(args.milestone)
                if getattr(args, "milestone", None) is not None
                else None
            ),
            release_class=str(args.release_class),
            sampling_authority_artifact_root=(
                Path(args.sampling_authority_artifact_root).expanduser().resolve()
                if getattr(args, "sampling_authority_artifact_root", None)
                else None
            ),
            sampling_authority_binding=(
                {
                    "ref": str(args.sampling_authority_ref),
                    "digest": str(args.sampling_authority_digest),
                }
                if (
                    getattr(args, "sampling_authority_ref", None)
                    and getattr(args, "sampling_authority_digest", None)
                )
                else None
            ),
        )
    except (
        FileNotFoundError,
        OSError,
        ObjectTransactionError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release pool-build] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_pool_precheck(args: argparse.Namespace) -> None:
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    try:
        report = precheck_pool_release(
            publish_root=publish_root,
            milestone=str(args.milestone),
            release_class=str(args.release_class),
        )
    except (FileNotFoundError, OSError, ObjectTransactionError, ValueError) as exc:
        raise SystemExit(f"[release pool-precheck] GATE_BLOCK {exc}") from exc
    document = report.as_document(details=bool(getattr(args, "details", False)))
    print(json.dumps(document, ensure_ascii=False, indent=2))
    if report.status != "passed":
        codes = ",".join(sorted({blocker.code for blocker in report.blockers}))
        raise SystemExit(f"[release pool-precheck] GATE_BLOCK {codes}")


def handle_pool_inspect(args: argparse.Namespace) -> None:
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    output_root = Path(OUTPUT_ROOT).resolve()
    by_task = bool(getattr(args, "by_task", False))
    execution_ids = tuple(getattr(args, "execution_id", ()) or ())
    if by_task and not execution_ids:
        raise SystemExit(
            "[release pool-inspect] GATE_BLOCK --by-task requires --execution-id"
        )
    if execution_ids and not by_task:
        raise SystemExit(
            "[release pool-inspect] GATE_BLOCK --execution-id requires --by-task"
        )
    source_pool_ref = str(getattr(args, "source_pool_ref", "") or "").strip()
    evidence_root_ref = str(
        getattr(args, "source_pool_evidence_root_ref", "") or ""
    ).strip()
    if bool(source_pool_ref) != bool(evidence_root_ref):
        raise SystemExit(
            "[release pool-inspect] GATE_BLOCK --source-pool-ref and "
            "--source-pool-evidence-root-ref must be provided together"
        )
    try:
        workloads = _workload_targets(tuple(getattr(args, "workload", ()) or ()))
        source_ready_input = None
        source_ready_candidates = None
        source_ready_backlog = None
        if source_pool_ref:
            consumed_object_refs: frozenset[str] = frozenset()
            if by_task:
                pending_delivery, _pending_issues = inspect_pool_delivery_intents(
                    output_root=output_root,
                    publish_root=publish_root,
                    execution_ids=execution_ids,
                )
                consumed_object_refs = frozenset(
                    str(row["contentObjectDir"]).strip("/")
                    for row in pending_delivery
                )
            source_ready_input, source_ready_candidates = load_source_ready_input(
                output_root=output_root,
                publish_root=publish_root,
                milestone=(
                    str(args.milestone) if args.milestone is not None else None
                ),
                source_pool_ref=source_pool_ref,
                evidence_root_ref=evidence_root_ref,
                consumed_object_refs=consumed_object_refs,
            )
            source_ready_backlog = {
                carrier: len(rows)
                for carrier, rows in source_ready_candidates.items()
            }
        throughput_ref = str(
            getattr(args, "throughput_promotion_ref", "") or ""
        ).strip()
        p10_throughput = None
        throughput_input = None
        if throughput_ref:
            p10_throughput, throughput_input = load_p10_throughput(
                output_root=output_root,
                promotion_ref=throughput_ref,
            )
        report = inspect_pool(
            publish_root=publish_root,
            include_issues=bool(getattr(args, "details", False)),
            include_batches=by_task,
            output_root=(output_root if by_task else None),
            milestone=(
                str(args.milestone) if args.milestone is not None else None
            ),
            execution_ids=execution_ids,
            source_ready_backlog=source_ready_backlog,
            p10_per_slot_throughput=p10_throughput,
            source_ready_candidates=source_ready_candidates,
            source_ready_input=source_ready_input,
            throughput_input=throughput_input,
            workload_targets=workloads,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release pool-inspect] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_pool_object_retire(args: argparse.Namespace) -> None:
    """Write one create-once retirement receipt; never touch original evidence."""

    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    try:
        if bool(args.apply):
            with canonical_publish_lock(publish_root):
                report = retire_pool_object(
                    publish_root=publish_root,
                    object_type=str(args.object_type),
                    object_ref=str(args.object_ref),
                    reason=str(args.reason),
                    retired_at=str(args.retired_at),
                    apply=True,
                )
        else:
            report = retire_pool_object(
                publish_root=publish_root,
                object_type=str(args.object_type),
                object_ref=str(args.object_ref),
                reason=str(args.reason),
                retired_at=str(args.retired_at),
                apply=False,
            )
    except (
        FileNotFoundError,
        OSError,
        ObjectTransactionError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release pool-object retire] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))



__all__ = [
    "handle_pool_inspect",
    "handle_pool_object_retire",
    "handle_pool_release_build",
]
