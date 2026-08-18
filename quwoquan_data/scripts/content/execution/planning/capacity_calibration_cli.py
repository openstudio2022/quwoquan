"""CLI binding for one governed capacity calibration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.execution.model_contract import SEMANTIC_SELECTION_IDS
from content.execution.planning.capacity_calibration_writer import (
    CapacityCalibrationRunError,
    run_capacity_calibration,
)
from core.paths import CONTROL_PLANE_SHARED_ROOT, REPO_ROOT


def handle_calibrate_capacity(args: argparse.Namespace) -> None:
    calibration_id = str(args.calibration_id or "").strip()
    output_dir = (
        CONTROL_PLANE_SHARED_ROOT / "capacity_calibration" / calibration_id
    )
    try:
        receipt, path = run_capacity_calibration(
            calibration_id=calibration_id,
            semantic_selection_id=str(args.semantic_selection_id),
            fleet_report_paths=tuple(
                Path(value).expanduser().resolve()
                for value in args.fleet_report
            ),
            execution_state_paths=tuple(
                Path(value).expanduser().resolve()
                for value in args.execution_state
            ),
            output_dir=output_dir,
            supersedes_calibration_id=(
                str(args.supersedes_calibration_id).strip()
                if args.supersedes_calibration_id
                else None
            ),
            provider_evidence_dir=(
                CONTROL_PLANE_SHARED_ROOT
                / "capacity_calibration"
                / str(args.provider_evidence_calibration_id).strip()
                if args.provider_evidence_calibration_id
                else None
            ),
            provider_evidence_calibration_id=(
                str(args.provider_evidence_calibration_id).strip()
                if args.provider_evidence_calibration_id
                else None
            ),
        )
    except (OSError, TypeError, ValueError, CapacityCalibrationRunError) as exc:
        raise SystemExit(
            f"[task calibrate-capacity] GATE_BLOCK {exc}"
        ) from exc
    print(
        json.dumps(
            {
                **receipt,
                "receiptRef": path.relative_to(REPO_ROOT).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_calibrate_capacity_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "calibrate-capacity",
        help=(
            "以 100 次真实 Provider probe、资源采样与既有 fleet/object 回执"
            "冻结容量 receipt"
        ),
    )
    parser.add_argument("--calibration-id", required=True)
    parser.add_argument(
        "--semantic-selection-id",
        choices=SEMANTIC_SELECTION_IDS,
        required=True,
    )
    parser.add_argument(
        "--fleet-report",
        action="append",
        required=True,
        help="真实 passed ReliableTask fleet report；可重复",
    )
    parser.add_argument(
        "--execution-state",
        action="append",
        required=True,
        help="含逐对象 timing 的真实 execution_state.json；可重复",
    )
    parser.add_argument("--supersedes-calibration-id")
    parser.add_argument(
        "--provider-evidence-calibration-id",
        help="复用既有 100 次 Provider probe 的 calibrationId；原始字节会复制进新 closure",
    )
    parser.set_defaults(handler=handle_calibrate_capacity)


__all__ = [
    "handle_calibrate_capacity",
    "register_calibrate_capacity_parser",
]
