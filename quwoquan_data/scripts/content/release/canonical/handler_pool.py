"""CLI handlers for canonical pool inspection, append, and release build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.release.canonical.aggregate_release import build_pool_release
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.pool_append import append_pool_batch, plan_pool_backfill
from content.release.canonical.pool_attribution_repair import (
    repair_pool_attribution,
)
from content.release.canonical.pool_delivery_intent_inspection import (
    inspect_pool_delivery_intents,
)
from content.release.canonical.pool_inspection import inspect_pool
from content.release.canonical.pool_source_ready_input import (
    load_p10_throughput,
    load_source_ready_input,
)
from content.release.canonical.semantic_wave_dispatch import (
    SemanticWaveDispatchError,
    write_create_once_semantic_wave_dispatch,
)
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT


def handle_pool_release_build(args: argparse.Namespace) -> None:
    output_root = Path(OUTPUT_ROOT).resolve()
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
            milestone=(
                str(args.milestone)
                if getattr(args, "milestone", None) is not None
                else None
            ),
            release_class=(
                str(args.release_class)
                if getattr(args, "release_class", None) is not None
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
                milestone=str(getattr(args, "milestone", "M100")),
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
            milestone=str(getattr(args, "milestone", "M100")),
            execution_ids=execution_ids,
            source_ready_backlog=source_ready_backlog,
            p10_per_slot_throughput=p10_throughput,
            source_ready_candidates=source_ready_candidates,
            source_ready_input=source_ready_input,
            throughput_input=throughput_input,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release pool-inspect] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_pool_dispatch(args: argparse.Namespace) -> None:
    """Freeze candidate-backed standalone task requests without executing them."""

    output_root = Path(OUTPUT_ROOT).resolve()
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    try:
        predecessor_execution_ids: dict[str, str] = {}
        for raw in getattr(args, "retry_predecessor", ()) or ():
            slot_id, separator, execution_id = str(raw).partition("=")
            slot_id = slot_id.strip()
            execution_id = execution_id.strip()
            if not separator or not slot_id or not execution_id:
                raise ValueError(
                    "--retry-predecessor must be SLOT_ID=EXECUTION_ID"
                )
            if slot_id in predecessor_execution_ids:
                raise ValueError(
                    f"duplicate --retry-predecessor slotId: {slot_id}"
                )
            predecessor_execution_ids[slot_id] = execution_id
        predecessor_unfinished_refs: dict[str, list[str]] = {}
        for raw in getattr(args, "retry_unfinished_ref", ()) or ():
            slot_id, separator, object_ref = str(raw).partition("=")
            slot_id = slot_id.strip()
            object_ref = object_ref.strip()
            if not separator or not slot_id or not object_ref:
                raise ValueError(
                    "--retry-unfinished-ref must be SLOT_ID=OBJECT_REF"
                )
            rows = predecessor_unfinished_refs.setdefault(slot_id, [])
            if object_ref in rows:
                raise ValueError(
                    f"duplicate --retry-unfinished-ref for {slot_id}: {object_ref}"
                )
            rows.append(object_ref)
        document, path = write_create_once_semantic_wave_dispatch(
            dispatch_id=str(args.dispatch_id),
            pool_inspection_ref=str(args.pool_inspection_ref),
            semantic_preflight_receipt_ref=str(
                args.semantic_preflight_receipt
            ),
            run_date=str(args.run_date),
            scope=str(args.scope),
            region_ref=str(args.region_ref),
            sequence_start=int(args.sequence_start),
            predecessor_dispatch_ref=(
                str(args.predecessor_dispatch_ref).strip()
                if str(args.predecessor_dispatch_ref or "").strip()
                else None
            ),
            predecessor_execution_ids=predecessor_execution_ids or None,
            predecessor_unfinished_refs={
                slot_id: tuple(refs)
                for slot_id, refs in predecessor_unfinished_refs.items()
            } or None,
            required_workers=int(args.required_workers),
            partition_count=int(args.partition_count),
            capacity_plan_digest=str(args.capacity_plan_digest),
            output_root=output_root,
            publish_root=publish_root,
        )
    except (
        FileNotFoundError,
        OSError,
        SemanticWaveDispatchError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release pool-dispatch] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {
                **document,
                "manifestRef": path.relative_to(output_root).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_pool_backfill_plan(args: argparse.Namespace) -> None:
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    try:
        report = plan_pool_backfill(publish_root=publish_root)
    except (
        FileNotFoundError,
        OSError,
        ObjectTransactionError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release pool-backfill plan] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_pool_append(args: argparse.Namespace) -> None:
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    input_path = Path(args.input).expanduser().resolve()
    try:
        if bool(args.apply):
            with canonical_publish_lock(publish_root):
                report = append_pool_batch(
                    input_path=input_path,
                    publish_root=publish_root,
                    apply=True,
                )
        else:
            report = append_pool_batch(
                input_path=input_path,
                publish_root=publish_root,
                apply=False,
            )
    except (
        FileNotFoundError,
        OSError,
        ObjectTransactionError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[release pool-append] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_pool_attribution_repair(args: argparse.Namespace) -> None:
    publish_root = Path(args.publish_root or PUBLISH_ROOT).resolve()
    output_root = Path(OUTPUT_ROOT).resolve()
    bindings_path = Path(args.bindings).expanduser().resolve()
    try:
        if bool(args.apply):
            with canonical_publish_lock(publish_root):
                report = repair_pool_attribution(
                    publish_root=publish_root,
                    output_root=output_root,
                    bindings_path=bindings_path,
                    source_pool_ref=str(args.source_pool_ref),
                    evidence_root_ref=str(args.source_pool_evidence_root_ref),
                    apply=True,
                )
        else:
            report = repair_pool_attribution(
                publish_root=publish_root,
                output_root=output_root,
                bindings_path=bindings_path,
                source_pool_ref=str(args.source_pool_ref),
                evidence_root_ref=str(args.source_pool_evidence_root_ref),
                apply=False,
            )
    except (
        FileNotFoundError,
        OSError,
        ObjectTransactionError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(
            f"[release pool-backfill repair-attribution] GATE_BLOCK {exc}"
        ) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


__all__ = [
    "handle_pool_append",
    "handle_pool_attribution_repair",
    "handle_pool_backfill_plan",
    "handle_pool_dispatch",
    "handle_pool_inspect",
    "handle_pool_release_build",
]
