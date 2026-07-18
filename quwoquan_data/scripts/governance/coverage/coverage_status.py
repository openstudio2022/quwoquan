"""Read-only coverage-matrix status projection."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from governance.coverage.coverage_matrix import (
    CELL_STATUSES, SATURATED_CELL_STATUSES, TERMINAL_CELL_STATUSES,
)

def coverage_matrix_status(*, run_dir: Path) -> dict[str, Any]:
    checkpoints = sorted(run_dir.glob("checkpoint_*.json"))
    statuses = {status: 0 for status in sorted(CELL_STATUSES)}
    province_totals: dict[str, dict[str, int]] = {}
    district_type_statuses: dict[str, dict[tuple[str, str, str], list[dict[str, Any]]]] = {}
    for path in checkpoints:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        province = str(checkpoint.get("province") or "")
        province_row = province_totals.setdefault(
            province,
            {
                "total": 0,
                "terminal": 0,
                "saturated": 0,
                "failed": 0,
                "driverComplete": 0,
            },
        )
        for cell in checkpoint.get("cells") or []:
            status = str(cell.get("status") or "pending")
            statuses[status] = statuses.get(status, 0) + 1
            province_row["total"] += 1
            if status in TERMINAL_CELL_STATUSES:
                province_row["terminal"] += 1
            if status in SATURATED_CELL_STATUSES:
                province_row["saturated"] += 1
            if status == "failed":
                province_row["failed"] += 1
            if bool((cell.get("saturationEvidence") or {}).get("driverComplete")):
                province_row["driverComplete"] += 1
            identity = cell.get("identity") or {}
            key = (
                str(identity.get("city") or ""),
                str(identity.get("district") or ""),
                str(identity.get("entityType") or ""),
            )
            district_type_statuses.setdefault(province, {}).setdefault(key, []).append(cell)
    provinces: dict[str, Any] = {}
    for province, row in province_totals.items():
        total = int(row["total"])
        failed_ratio = row["failed"] / max(1, total)
        groups = district_type_statuses.get(province, {})
        district_type_complete = sum(
            1
            for cells in groups.values()
            if cells
            and all(
                str(cell.get("status") or "") in TERMINAL_CELL_STATUSES
                and bool((cell.get("saturationEvidence") or {}).get("driverComplete"))
                for cell in cells
            )
        )
        provinces[province] = {
            **row,
            "failedRatio": failed_ratio,
            "allCellsTerminal": bool(total) and row["terminal"] == total,
            "saturated": (
                bool(total)
                and row["saturated"] == total
                and row["driverComplete"] == total
                and failed_ratio < 0.01
            ),
            "coverage": {
                "districtTypeCellsTotal": len(groups),
                "districtTypeCellsCompleted": district_type_complete,
                "sourceDriversTotal": total,
                "sourceDriversCompleted": row["driverComplete"],
            },
        }
    return {
        "checkpointCount": len(checkpoints),
        "cellStatuses": statuses,
        "provinces": provinces,
    }

