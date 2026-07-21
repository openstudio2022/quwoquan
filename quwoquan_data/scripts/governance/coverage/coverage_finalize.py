"""Finalize a discovered source into typed coverage-matrix checkpoints."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from governance.coverage.coverage_matrix import _digest, record_cell_page
from governance.coverage.coverage_merge import _candidate_locations, _type_evidence
from governance.coverage.coverage_status import coverage_matrix_status


def finalize_discovery_source_cells(
    *,
    run_dir: Path,
    source: str,
    candidates: list[dict[str, Any]],
    failed_districts: list[str] | None = None,
    blocked_reason: str | None = None,
    province_filter: str | None = None,
    city_filter: str | None = None,
    district_filter: str | None = None,
    retry_only: bool = False,
) -> dict[str, Any]:
    """Archive naturally completed source shards without inferring completion."""
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        if str(candidate.get("source") or "") != source:
            continue
        classified = _type_evidence([candidate], str(candidate.get("name") or ""))
        if classified is None:
            continue
        for province, city, district, _geo_ref in _candidate_locations([candidate], country="中国"):
            grouped.setdefault((province, city, district, classified[0]), []).append(candidate)

    shard_failures: dict[tuple[str, str], str] = {}
    for raw in failed_districts or []:
        shard, _, reason = str(raw).partition(":")
        city, separator, district = shard.partition("/")
        if separator and city and district:
            shard_failures[(city, district)] = reason or "request_failed"

    updated_cells = 0
    retryable_statuses = {"pending", "running", "partial", "failed"}
    for checkpoint_path in sorted(run_dir.glob("checkpoint_*.json")):
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        province = str(checkpoint.get("province") or "")
        city = str(checkpoint.get("city") or "")
        if (province_filter and province != province_filter) or (city_filter and city != city_filter):
            continue
        for cell in checkpoint.get("cells") or []:
            identity = cell.get("identity") if isinstance(cell, dict) else None
            if not isinstance(identity, dict) or identity.get("source") != source:
                continue
            district = str(identity.get("district") or "")
            entity_type = str(identity.get("entityType") or "")
            if district_filter and district != district_filter:
                continue
            if retry_only and str(cell.get("status") or "") not in retryable_statuses:
                continue
            failure_reason = blocked_reason or shard_failures.get((city, district))
            request_failed = bool(failure_reason and "failed_" in failure_reason)
            truncated = bool(
                failure_reason
                and not request_failed
                and (
                    failure_reason.startswith("result_limit_")
                    or failure_reason.startswith("page_limit_")
                    or "truncated_" in failure_reason
                )
            )
            rows = grouped.get((province, city, district, entity_type), [])
            record_cell_page(
                checkpoint_path=checkpoint_path,
                cell_id=str(cell.get("cellId") or ""),
                raw_rows=rows,
                semantic_admitted_count=len(rows),
                semantic_rejected_count=0,
                dedup_unique_count=len(rows),
                dedup_duplicate_count=0,
                semantic_admitted_rows=rows,
                dedup_results=[
                    {
                        "result": "unique",
                        "identityKey": _digest([
                            candidate.get("identityRefs") or {}, candidate.get("name"),
                            province, city, district,
                        ]),
                    }
                    for candidate in rows
                ],
                request_succeeded=failure_reason is None or truncated,
                exhausted=(failure_reason is None or truncated) and not truncated,
                truncated=truncated,
                retry_state={"reason": str(failure_reason)} if failure_reason else None,
            )
            updated_cells += 1
    return {
        "source": source,
        "updatedCells": updated_cells,
        "status": coverage_matrix_status(run_dir=run_dir),
    }
