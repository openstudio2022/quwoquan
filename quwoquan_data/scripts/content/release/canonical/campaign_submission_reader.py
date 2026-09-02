"""Read-only neutral boundary for immutable campaign submissions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.planning.carrier_policy import carrier_operation


def campaign_root(root_execution_id: str, *, root: Path) -> Path:
    return root / validate_execution_id(root_execution_id)


def load_submissions(
    root_execution_id: str, *, root: Path
) -> dict[str, dict[str, Any]]:
    normalized_root = validate_execution_id(root_execution_id)
    submissions_dir = campaign_root(normalized_root, root=root) / "submissions"
    submissions: dict[str, dict[str, Any]] = {}
    for path in sorted(submissions_dir.glob("*.json")) if submissions_dir.is_dir() else ():
        payload = read_json(path)
        assert_valid(
            payload,
            "execution",
            "content_execution_submission",
            label=f"campaign submission:{path.name}",
        )
        execution_id = validate_execution_id(str(payload.get("executionId") or ""))
        identity = parse_execution_id(execution_id)
        carrier = str(payload.get("carrier") or "")
        operation = str(payload.get("operation") or "")
        if (
            str(payload.get("rootExecutionId") or "") != normalized_root
            or path.stem != execution_id
            or carrier != identity.content_type.value
            or not operation
        ):
            raise ValueError(f"campaign submission identity collision: {path}")
        if "reviewedClosureAdoption" not in payload and operation != carrier_operation(carrier):
            raise ValueError(f"campaign submission operation drift: {path}")
        if carrier in submissions:
            raise ValueError(f"campaign has duplicate {carrier} submissions")
        submissions[carrier] = payload
    return submissions


__all__ = ["campaign_root", "load_submissions"]
