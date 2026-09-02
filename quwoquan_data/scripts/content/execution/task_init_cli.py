"""CLI adapter for deterministic task initialization."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.execution.task_init import initialize_task
from content.execution.planning.task_init_projection import (
    TaskInitProjectionError,
    project_task_init_inputs,
)
from content.source.research.scale_source_pool_runtime import (
    frozen_scale_source_pool_targets,
    materialize_frozen_scale_source_pool_entity,
)


def handle_task_init(args: argparse.Namespace) -> None:
    try:
        result = initialize_task(
            carrier_demand_path=Path(str(args.carrier_demand)),
            candidate_bindings_path=Path(str(args.candidate_bindings)),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task init] GATE_BLOCK {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def handle_task_init_projection(args: argparse.Namespace) -> None:
    try:
        result = project_task_init_inputs(
            work_request_path=Path(str(args.work_request)),
            output_dir=Path(str(args.output_dir)),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError, TaskInitProjectionError) as exc:
        raise SystemExit(f"[task project-init-inputs] GATE_BLOCK {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))




def _load_materialization_selection(execution_id: str, carrier: str) -> dict[str, object]:
    from content.execution import task_init as _task_init
    from content.execution.planning.request_envelope_io import load_campaign_envelope
    from core.io import read_json
    from core.paths import OUTPUT_ROOT, execution_root

    root = execution_root(execution_id)
    request = read_json(root / "0.plan/request.json")
    if not isinstance(request, dict) or request.get("carrier") != carrier:
        raise ValueError("task-init carrier identity drift")
    demand = request.get("carrierDemand")
    if not isinstance(demand, dict):
        raise ValueError("task-init carrier demand binding is missing")
    demand_path = OUTPUT_ROOT / str(demand.get("ref") or "")
    demand_doc = read_json(demand_path)
    if not isinstance(demand_doc, dict) or _task_init._file_digest(demand_path) != demand.get("digest"):
        raise ValueError("task-init carrier demand exact bytes drift")
    work_request_path = OUTPUT_ROOT / str(demand_doc["workRequestRef"])
    work_request = read_json(work_request_path)
    if not isinstance(work_request, dict):
        raise ValueError("task-init WorkRequest is unreadable")
    from content.execution.planning.work_request_store import _assert_work_request_identity
    if _assert_work_request_identity(work_request) != demand_doc["workRequestDigest"]:
        raise ValueError("task-init WorkRequest identity drift")
    envelope_rows = [
        row for row in work_request.get("carrierEnvelopes") or []
        if isinstance(row, dict) and row.get("carrier") == carrier
    ]
    if len(envelope_rows) != 1:
        raise ValueError("WorkRequest carrier envelope binding is missing")
    envelope = load_campaign_envelope(OUTPUT_ROOT / str(envelope_rows[0]["envelopeRef"]))
    selection = envelope.get("sourcePoolSelection")
    if (
        envelope.get("executionId") != execution_id
        or envelope.get("requestDigest") != envelope_rows[0].get("requestDigest")
        or not isinstance(selection, dict)
        or int(selection.get("candidateCount") or 0) != int(request["workUnitCount"])
    ):
        raise ValueError("task-init source-pool selection drift")
    return {
        "scaleSourcePool": envelope["scaleSourcePool"],
        "sourcePoolEvidenceRootRef": envelope["sourcePoolEvidenceRootRef"],
        "sourcePoolSelection": selection,
    }


def handle_task_materialize_sources(args: argparse.Namespace) -> None:
    try:
        execution_id = str(args.execution_id)
        carrier = str(args.carrier)
        selection = _load_materialization_selection(execution_id, carrier)
        targets = frozen_scale_source_pool_targets(
            execution_id, carrier, direct_selection=selection
        )
        if len(targets) != 1:
            raise ValueError(f"source materialization requires one frozen target, got {len(targets)}")
        target = targets[0]
        from core.io import read_json
        from core.paths import execution_root
        target_set = read_json(execution_root(execution_id) / "0.plan/target_set.json")
        refs = target_set.get("targetRefs") if isinstance(target_set, dict) else None
        if not isinstance(refs, list) or len(refs) != 1:
            raise ValueError("task-init target set must freeze exactly one targetRef")
        object_ref = str(refs[0])
        manifest = materialize_frozen_scale_source_pool_entity(
            execution_id,
            carrier,
            str(target["name"]),
            str(target["entityType"]),
            direct_selection=selection,
        )
        if not isinstance(manifest, dict):
            raise ValueError(f"{carrier} source materializer returned no source unit")
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task materialize-sources] GATE_BLOCK {exc}") from exc
    print(json.dumps({
        "schema": "quwoquan_data.source_materialization_result",
        "executionId": execution_id,
        "carrier": carrier,
        "sourceUnitId": manifest["sourceUnitId"],
        "targetRef": object_ref,
    }, ensure_ascii=False, indent=2))


def register_task_materialize_sources_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "materialize-sources",
        help="从 task-init exact WorkRequest 单轨物化来源单元",
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--carrier", required=True, choices=("homepage", "article", "image", "video"))
    parser.set_defaults(handler=handle_task_materialize_sources)


def register_task_init_projection_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "project-init-inputs",
        help="从 confirmed WorkRequest 确定性冻结各载体 task-init 输入",
    )
    parser.add_argument("--work-request", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.set_defaults(handler=handle_task_init_projection)


def register_task_init_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("init", help="从 confirmed demand 与 immutable candidates 原子创建工作包")
    parser.add_argument("--carrier-demand", required=True)
    parser.add_argument("--candidate-bindings", required=True)
    parser.set_defaults(handler=handle_task_init)


__all__ = [
    "handle_task_init",
    "handle_task_init_projection",
    "register_task_init_parser",
    "register_task_init_projection_parser",
    "register_task_materialize_sources_parser",
]
