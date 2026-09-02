"""Read-only neutral boundary for campaign reconciliation evidence."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid
from content.execution.identity import parse_execution_id


def campaign_root_for_submission(execution_id: str, *, output_root: Path) -> str | None:
    normalized = parse_execution_id(execution_id).execution_id
    matches = sorted(
        (output_root / "data/local/workspace/content-campaign-submissions").glob(
            f"*/submissions/{normalized}.json"
        )
    )
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"execution {normalized} belongs to multiple campaign roots")
    return matches[0].parent.parent.name


def load_reconciliation_reference(
    reference: Mapping[str, Any], *, output_root: Path
) -> tuple[dict[str, Any], Path]:
    assert_valid(
        dict(reference),
        "execution",
        "campaign_submission_reconciliation_ref",
        label="campaign submission reconciliation ref",
    )
    raw_ref = str(reference.get("receiptRef") or "").strip()
    path = (output_root / raw_ref).resolve()
    try:
        path.relative_to(output_root.resolve())
    except ValueError as exc:
        raise ValueError("submission reconciliation receipt ref escapes output root") from exc
    receipt = read_json(path)
    assert_valid(
        receipt,
        "execution",
        "campaign_submission_reconciliation_receipt",
        label="campaign submission reconciliation receipt",
    )
    if (
        reference.get("predecessorRootExecutionId") != receipt.get("rootExecutionId")
        or reference.get("receiptDigest") != receipt.get("receiptDigest")
    ):
        raise ValueError("submission reconciliation ref drift")
    return receipt, path


__all__ = ["campaign_root_for_submission", "load_reconciliation_reference"]
