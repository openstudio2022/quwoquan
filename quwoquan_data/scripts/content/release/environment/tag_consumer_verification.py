"""Verify active Tag taxonomy receipt against immutable release authority."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.environment.importers import assert_import_report_contract
from content.release.environment.run_evidence import write_release_evidence
from content.release.model import ReleaseKind


def write_tag_consumer_verification(
    *,
    output_root: Path,
    environment: str,
    release_id: str,
    release_kind: ReleaseKind,
    run_id: str,
    release_contract: Mapping[str, Any],
    import_report_path: Path,
    output_path: Path,
) -> Path:
    report = assert_import_report_contract(
        import_report_path,
        expected_release_id=release_id,
    )
    expected = sorted(
        str(item) for item in release_contract.get("desiredRefs", {}).get("tags", []) if str(item).strip()
    )
    if (
        report.get("status") != "active"
        or report.get("environment") != environment
        or report.get("sourceOwner") != "qwq_data"
        or report.get("releaseKind") != release_kind.value
        or report.get("tagRefs") != expected
        or report.get("nodeCount") != len(expected)
    ):
        raise ValueError("Tag consumer receipt differs from immutable release authority")
    write_release_evidence(
        output_path,
        {
            "schema": "quwoquan_data.tag_consumer_verification",
            "environment": environment,
            "releaseId": release_id,
            "runId": run_id,
            "sourceImportReportRef": import_report_path.relative_to(output_root).as_posix(),
            "releaseKind": release_kind.value,
            "nodeCount": len(expected),
            "tagRefs": expected,
            "verifiedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "passed": True,
        },
        "tag_consumer_verification",
    )
    return output_path
