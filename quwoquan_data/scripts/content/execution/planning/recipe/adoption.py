"""Reviewed-closure adoption adapter for the task execute facade."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.execution.closure.adoption import adopt_reviewed_closure
from content.execution.planning.capacity_calibration import CapacityCalibrationError


def handle_adopt_reviewed_closure(args: argparse.Namespace) -> None:
    try:
        result = adopt_reviewed_closure(
            adoption_id=str(args.adoption_id),
            source_release_id=str(args.source_release_id),
            identity_incident_path=Path(args.identity_incident).expanduser(),
            execution_ids={
                "homepage": str(args.execution_id),
                "article": str(args.article_execution_id),
                "image": str(args.image_execution_id),
                "video": str(args.video_execution_id),
            },
            region_ref=str(args.region_ref),
            capacity_calibration_receipt=Path(args.capacity_calibration_receipt),
        )
    except (
        CapacityCalibrationError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK reviewed closure adoption: {exc}"
        ) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


__all__ = ["handle_adopt_reviewed_closure"]
