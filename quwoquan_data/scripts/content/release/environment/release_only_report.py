"""Derived release-only report used by task release orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import write_json
from core.schema import assert_valid
from core.paths import execution_root, release_ref


def write_release_only_ship_report(
    *,
    execution_id: str | None = None,
    output_path: Path | None = None,
    release_id: str,
    summary: Mapping[str, Any],
) -> Path:
    """Write a release-only report without mutating canonical publish."""

    if output_path is None:
        if not execution_id:
            raise ValueError("execution_id or output_path required")
        output_path = execution_root(execution_id) / "_shared" / "ship_report.json"
    document = {
            "schema": "quwoquan_data.ship_report",
            "closureType": "release_only",
            "sourceReleaseId": release_id,
            "releaseRef": release_ref(release_id),
            "summary": dict(summary),
            "importRequested": False,
            "importReports": [],
        }
    assert_valid(document, "release", "ship_report", label=str(output_path))
    write_json(output_path, document)
    return output_path


__all__ = ["write_release_only_ship_report"]
