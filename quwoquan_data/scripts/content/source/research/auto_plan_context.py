"""Frozen scale-pool and external-media context for auto research planning."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ExternalMediaPlanContext:
    """Indexes and exact object scope derived once from frozen acquisition input."""

    professional_image_bound: bool
    image_work_units: Mapping[str, tuple[dict[str, Any], ...]]
    video_work_units: Mapping[str, tuple[dict[str, Any], ...]]
    exact_media_work_units: bool
    professional_image_index: Any | None
    video_receipt_refs: list[str]
    video_acquisition_root: Any
    professional_video_index: Any | None


def initialize_auto_plan_report(
    *, execution_id: str, vertical: str, selected_lanes: set[str]
) -> dict[str, Any]:
    """Return the shared append-only report envelope for one plan run."""
    return {
        "schema": "quwoquan.content.source.auto_research_plan",
        "executionId": execution_id,
        "vertical": vertical,
        "selectedLanes": sorted(selected_lanes),
        "updated": [],
        "issues": [],
        "candidates": [],
        "imageCollections": [],
        "homepageMediaCollections": [],
        "sourceUnavailable": [],
        "rescueEvents": [],
    }


def coverage_targets_by_name(
    strategy_spec: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Index the frozen coverage targets without changing their rows."""
    return {
        str(row.get("name") or "").strip(): row
        for row in ((strategy_spec.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    }


def article_topic_terms(
    strategy_spec: Mapping[str, Any], target_source: Mapping[str, Any]
) -> list[str]:
    """Collect only explicit intent and target topic terms."""
    declared_topics = (
        target_source.get("topics")
        if isinstance(target_source.get("topics"), list)
        else []
    )
    return [
        str(value).strip()
        for value in (
            strategy_spec.get("intentLabel"),
            target_source.get("topic"),
            target_source.get("theme"),
            *declared_topics,
        )
        if str(value or "").strip()
    ]


def frozen_scale_source_pool_report(
    execution_id: str,
    entity_ids: list[str],
    *,
    selected_lanes: set[str],
    vertical: str,
    write_shared_report: bool,
) -> dict[str, Any] | None:
    """Materialize the already-frozen single-lane pool when one is bound."""
    if len(selected_lanes) != 1:
        return None
    from content.source.research.auto_plan_report import _write_auto_report_artifacts
    from content.source.research.scale_source_pool_runtime import (
        write_frozen_scale_source_pool_plans,
    )

    report = write_frozen_scale_source_pool_plans(
        execution_id, entity_ids, carrier=next(iter(selected_lanes))
    )
    if report is None:
        return None
    report["vertical"] = vertical
    if write_shared_report:
        _write_auto_report_artifacts(execution_id, report)
    return report


def build_external_media_plan_context(
    *,
    strategy_spec: Mapping[str, Any],
    selected_lanes: set[str],
    external_input_context: Any | None,
) -> ExternalMediaPlanContext:
    """Verify frozen receipts once and expose their immutable indexes."""
    from content.execution.planning.media_work_units import work_units_by_target
    from content.source.external_acquisition_inputs import (
        professional_image_context_enabled,
        professional_video_context_binding,
    )

    professional_image_bound = professional_image_context_enabled(
        external_input_context,
        selected_lanes,
    )
    image_work_units = work_units_by_target(strategy_spec, carrier="image")
    video_work_units = work_units_by_target(strategy_spec, carrier="video")
    exact_media_work_units = bool(
        ((strategy_spec.get("content") or {}).get("workUnits") or [])
    )
    professional_image_index = None
    if professional_image_bound:
        from content.execution.campaign.external_inputs import (
            PROFESSIONAL_IMAGE_ACQUISITION_KIND,
        )
        from content.source.professional_image_acquisition_index import (
            build_acquired_image_spec_index,
        )

        assert external_input_context is not None
        professional_image_index = build_acquired_image_spec_index(
            external_input_context.receipt_refs(PROFESSIONAL_IMAGE_ACQUISITION_KIND),
            root=external_input_context.acquisition_root(
                PROFESSIONAL_IMAGE_ACQUISITION_KIND
            ),
            descriptors=external_input_context.descriptors(
                PROFESSIONAL_IMAGE_ACQUISITION_KIND
            ),
        )
    video_receipt_refs, video_acquisition_root = (
        professional_video_context_binding(external_input_context)
    )
    professional_video_index = None
    if video_receipt_refs:
        from content.source.professional_video_spec_index import (
            build_acquired_video_spec_index,
        )

        professional_video_index = build_acquired_video_spec_index(
            video_receipt_refs,
            root=video_acquisition_root,
        )
    return ExternalMediaPlanContext(
        professional_image_bound=professional_image_bound,
        image_work_units=image_work_units,
        video_work_units=video_work_units,
        exact_media_work_units=exact_media_work_units,
        professional_image_index=professional_image_index,
        video_receipt_refs=video_receipt_refs,
        video_acquisition_root=video_acquisition_root,
        professional_video_index=professional_video_index,
    )
