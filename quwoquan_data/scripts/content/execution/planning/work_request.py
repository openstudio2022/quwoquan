"""Public typed ports for compiling intent into existing carrier envelopes."""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.request_envelope import write_scale_envelopes
from content.execution.planning.work_request_contract import (
    _RESULT_SCHEMA,
    _blocked,
    _path,
    _validated_result,
    WorkRequestPreviewQuery,
)
from content.execution.planning.work_request_store import (
    batch_documents_factory,
    compile_lock,
    confirmed_projection,
    find_work_request,
    find_work_request_by_request_digest,
    next_sequence,
)


class WorkRequestCommandWriter:
    def __init__(self, *, output_root: Path | None = None) -> None:
        self._output_root = output_root.resolve() if output_root is not None else None
        self._preview = WorkRequestPreviewQuery()

    def cancel(
        self, intent: Mapping[str, Any], *, preview_digest: str
    ) -> dict[str, Any]:
        preview = self._preview.preview(intent)
        if preview["outcome"] != "preview":
            return preview
        if preview["requestDigest"] != preview_digest:
            return _blocked(
                str(preview["requestDigest"]),
                code="DATA.WORK_REQUEST.PREVIEW_DRIFT",
                message="cancel preview digest no longer matches canonical input",
            )
        return _validated_result(
            {
                "schema": _RESULT_SCHEMA,
                "outcome": "canceled",
                "requestDigest": str(preview["requestDigest"]),
            }
        )

    def confirm(
        self, intent: Mapping[str, Any], *, preview_digest: str
    ) -> dict[str, Any]:
        started = time.perf_counter()
        preview = self._preview.preview(intent)
        if preview["outcome"] != "preview":
            return preview
        if preview["requestDigest"] != preview_digest:
            return _blocked(
                str(preview["requestDigest"]),
                code="DATA.WORK_REQUEST.PREVIEW_DRIFT",
                message="confirm preview digest no longer matches canonical input",
            )
        try:
            with compile_lock(self._output_root):
                current = self._preview.preview(intent)
                if current["outcome"] != "preview":
                    return current
                if current["requestDigest"] != preview_digest:
                    return _blocked(
                        str(current["requestDigest"]),
                        code="DATA.WORK_REQUEST.PREVIEW_DRIFT",
                        message="dependency set changed after preview",
                    )
                existing = find_work_request_by_request_digest(
                    preview_digest, output_root=self._output_root
                )
                if existing is not None:
                    return confirmed_projection(
                        existing, output_root=self._output_root, replayed=True
                    )
                normalized = current["normalizedRequest"]
                day, sequence = next_sequence(
                    normalized, output_root=self._output_root
                )
                envelope_paths = write_scale_envelopes(
                    str(normalized["scale"]),
                    region_ref=str(normalized["regionRef"]),
                    vertical=str(normalized["vertical"]),
                    topic=normalized.get("topic"),
                    target_names=normalized["targetNames"],
                    source_providers=normalized["sourceProviders"],
                    carriers=normalized["activeCarriers"],
                    workloads=normalized["workloads"],
                    output_root=self._output_root,
                    day=day,
                    sequence=sequence,
                    semantic_selection_id=str(normalized["semanticSelectionId"]),
                    semantic_preflight_receipt=(
                        _path(normalized["semanticPreflightReceiptRef"])
                        if normalized["semanticPreflightReceiptRef"]
                        else None
                    ),
                    capacity_calibration_receipt=Path(
                        str(normalized["capacityCalibrationReceiptRef"])
                    ),
                    predecessor_execution_ids_by_carrier=normalized[
                        "predecessorExecutionIdsByCarrier"
                    ],
                    predecessor_reconciliation_receipt=(
                        _path(normalized["predecessorReconciliationReceiptRef"])
                        if normalized["predecessorReconciliationReceiptRef"]
                        else None
                    ),
                    promotion_receipt=(
                        _path(normalized["promotionReceiptRef"])
                        if normalized["promotionReceiptRef"]
                        else None
                    ),
                    pre_acquisition_handoff=_path(
                        normalized["preAcquisitionHandoffRef"]
                    ),
                    external_input_refs_by_carrier=normalized[
                        "externalInputRefsByCarrier"
                    ],
                    acquisition_root=(
                        _path(normalized["acquisitionRootRef"])
                        if normalized["acquisitionRootRef"]
                        else None
                    ),
                    scale_source_pool=_path(normalized["scaleSourcePoolPlanRef"]),
                    source_pool_evidence_root=_path(
                        normalized["sourcePoolEvidenceRootRef"]
                    ),
                    batch_documents_factory=batch_documents_factory(
                        normalized=normalized,
                        preview_digest=preview_digest,
                        output_root=self._output_root,
                        started=started,
                    ),
                )
                work_request_path = (
                    next(iter(envelope_paths.values())).parent / "work-request.json"
                )
                return confirmed_projection(
                    work_request_path,
                    output_root=self._output_root,
                    replayed=False,
                )
        except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
            return _blocked(
                preview_digest,
                code="DATA.WORK_REQUEST.COMPILE_BLOCKED",
                message=str(exc),
                attributes={"exceptionType": type(exc).__name__},
            )


class WorkRequestCompilationQuery:
    def __init__(self, *, output_root: Path | None = None) -> None:
        self._output_root = output_root.resolve() if output_root is not None else None

    def get(self, work_request_digest: str) -> dict[str, Any]:
        try:
            path = find_work_request(
                work_request_digest, output_root=self._output_root
            )
            if path is not None:
                return confirmed_projection(
                    path, output_root=self._output_root, replayed=True
                )
        except (OSError, TypeError, ValueError) as exc:
            return _blocked(
                work_request_digest,
                code="DATA.WORK_REQUEST.COMPILATION_QUERY_BLOCKED",
                message=str(exc),
            )
        if path is None:
            return _blocked(
                work_request_digest,
                code="DATA.WORK_REQUEST.NOT_FOUND",
                message="compiled WorkRequest does not exist",
            )
        raise AssertionError("unreachable WorkRequest query state")


__all__ = [
    "WorkRequestCommandWriter",
    "WorkRequestCompilationQuery",
    "WorkRequestPreviewQuery",
]
