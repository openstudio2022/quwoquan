"""Append-only environment coverage receipt for one immutable release run."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.environment.run_evidence import write_release_evidence
from core.io import read_json
from core.release_layout import payload_file


class EnvironmentCoverageReceiptError(ValueError):
    """Raised when an importer report cannot prove release coverage."""


def write_environment_coverage_receipt(
    *,
    environment: str,
    release_id: str,
    run_id: str,
    release_root: Path,
    run_root: Path,
    importer_report: Mapping[str, Any],
    api_base_url: str,
) -> Path:
    """Write environment-only homepage coverage without mutating release data."""
    desired_path = payload_file(release_root, "desired_state.json")
    if not desired_path.is_file():
        raise EnvironmentCoverageReceiptError(
            f"release desired_state missing: {desired_path}"
        )
    desired = read_json(desired_path)
    desired_entities = sorted(
        {
            str(value)
            for value in (
                (desired.get("desiredRefs") or {}).get("entities") or []
            )
            if str(value).strip()
        }
    )
    report_environment = str(
        importer_report.get("environment")
        or importer_report.get("env")
        or ""
    )
    if report_environment != environment:
        raise EnvironmentCoverageReceiptError(
            "homepage importer environment does not match release run"
        )
    dry_run = bool(importer_report.get("dryRun"))
    mapping = importer_report.get("entityRefToHomepageId") or {}
    if not isinstance(mapping, Mapping):
        raise EnvironmentCoverageReceiptError(
            "entityRefToHomepageId must be an object"
        )

    rows: list[dict[str, Any]] = []
    for entity_ref in desired_entities:
        homepage_id = str(mapping.get(entity_ref) or "")
        row: dict[str, Any] = {
            "entityRef": entity_ref,
            "imported": not dry_run,
        }
        if homepage_id:
            row["homepageId"] = homepage_id
            row["introductionUrl"] = (
                f"{api_base_url.rstrip('/')}/homepages/"
                f"{homepage_id}/introduction"
            )
        rows.append(row)

    output = run_root / "coverage-receipt.json"
    write_release_evidence(
        output,
        {
            "schema": "quwoquan_data.environment_coverage_receipt",
            "environment": environment,
            "releaseId": release_id,
            "runId": run_id,
            "dryRun": dry_run,
            "rows": rows,
        },
        "environment_coverage_receipt",
    )
    return output
