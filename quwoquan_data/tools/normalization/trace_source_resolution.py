from __future__ import annotations

from pathlib import Path
from typing import Any

from common import write_json
from normalization.io_contracts import (
    TRACE_REPORT_SCHEMA_VERSION,
    entity_resolution_path,
    stage_input_path,
    stage_result_path,
    trace_report_path,
)


def build_trace_report(*, batch_label: str, source_ref: str) -> dict[str, Any]:
    compiled_entities: list[dict[str, Any]] = []
    if entity_resolution_path(batch_label).exists():
        from common import read_ndjson

        for row in read_ndjson(entity_resolution_path(batch_label)):
            if not isinstance(row, dict):
                continue
            if source_ref in [str(item).strip() for item in row.get("sourceRefs") or [] if str(item).strip()]:
                compiled_entities.append(
                    {
                        "canonicalZhHans": str(((row.get("mainEntity") or {}) if isinstance(row.get("mainEntity"), dict) else {}).get("canonicalZhHans") or "").strip(),
                        "entityType": str(((row.get("mainEntity") or {}) if isinstance(row.get("mainEntity"), dict) else {}).get("entityType") or "").strip(),
                    }
                )
    payload: dict[str, Any] = {
        "schemaVersion": TRACE_REPORT_SCHEMA_VERSION,
        "sourceRef": source_ref,
        "sourceUrl": "",
        "sourceTitle": "",
        "catalogTopicId": "",
        "catalogName": "",
        "extractInputPath": str(stage_input_path(batch_label, "extract", source_ref)),
        "extractResultPath": str(stage_result_path(batch_label, "extract", source_ref)),
        "reviewInputPath": str(stage_input_path(batch_label, "review", source_ref)),
        "reviewResultPath": str(stage_result_path(batch_label, "review", source_ref)),
        "authorityInputPath": str(stage_input_path(batch_label, "authority", source_ref)),
        "authorityResultPath": str(stage_result_path(batch_label, "authority", source_ref)),
        "compiledEntityRefs": compiled_entities,
        "compiledImageRefs": [],
        "traceStatus": "ready",
    }
    for candidate_path in (
        stage_result_path(batch_label, "extract", source_ref),
        stage_result_path(batch_label, "review", source_ref),
        stage_result_path(batch_label, "authority", source_ref),
    ):
        if not candidate_path.exists():
            continue
        from common import read_json

        row = read_json(candidate_path)
        if isinstance(row, dict):
            payload["sourceUrl"] = str(payload["sourceUrl"] or row.get("sourceUrl") or "").strip()
            payload["sourceTitle"] = str(payload["sourceTitle"] or row.get("sourceTitle") or "").strip()
            payload["catalogTopicId"] = str(payload["catalogTopicId"] or row.get("catalogTopicId") or "").strip()
            payload["catalogName"] = str(payload["catalogName"] or row.get("catalogName") or "").strip()
    write_json(trace_report_path(batch_label, source_ref), payload)
    return payload

