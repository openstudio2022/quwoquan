"""Resolve one entity's immutable fetch plan before downloads start."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from governance.coverage.entity_extract import entity_ref as build_entity_ref

from content.source.handler_fetch_video import fetch_admitted_sourced_videos
from content.source.handler_plan import _curated_sources_for_lanes
from content.source.source_inputs import (
    curated_homepage_media_for_entity,
    curated_images_for_entity,
    curated_sourced_videos_for_entity,
)
from content.source.source_unit import resolve_entity_object_dir


@dataclass(frozen=True)
class EntityFetchPlan:
    object_dir: Path
    target_ref: str
    sources: list[dict[str, Any]]
    image_specs: list[dict[str, Any]]
    sourced_video_candidates: list[dict[str, Any]]
    sourced_video_evidence: list[Path]
    sourced_video_failure: str
    image_lane_selected: bool
    homepage_media_selected: bool


def prepare_entity_fetch_plan(
    *,
    execution_id: str,
    entity_id: str,
    entity_type: str,
    domain: str,
    etype: str,
    selected_lanes: set[str] | None,
    external_input_context: Any | None = None,
) -> EntityFetchPlan:
    image_selected = selected_lanes is None or "image" in selected_lanes
    homepage_selected = selected_lanes is None or "homepage" in selected_lanes
    video_selected = selected_lanes is None or "video" in selected_lanes
    video_candidates = (
        curated_sourced_videos_for_entity(
            execution_id,
            entity_id,
            entity_type,
            external_input_context=external_input_context,
        )
        if video_selected
        else []
    )
    video_evidence: list[Path] = []
    sourced_video_failure = ""
    if video_candidates:
        try:
            professional_acquisition_root = None
            if any(
                str(candidate.get("professionalAcquisitionReceiptRef") or "").strip()
                for candidate in video_candidates
            ):
                from content.execution.campaign_external_inputs import (
                    PROFESSIONAL_VIDEO_ACQUISITION_KIND,
                )

                if external_input_context is None:
                    raise ValueError(
                        "professional video candidates require external input context"
                    )
                professional_acquisition_root = (
                    external_input_context.acquisition_root(
                        PROFESSIONAL_VIDEO_ACQUISITION_KIND
                    )
                )
            video_evidence = fetch_admitted_sourced_videos(
                execution_id=execution_id,
                entity_id=entity_id,
                entity_type=entity_type,
                candidates=video_candidates,
                professional_acquisition_root=professional_acquisition_root,
            )
        except (OSError, TimeoutError, ValueError) as exc:
            # Record the source failure; image assets cannot satisfy video.
            sourced_video_failure = f"{type(exc).__name__}: {exc}"
    homepage_specs = (
        curated_homepage_media_for_entity(execution_id, entity_id, entity_type)
        if homepage_selected
        else []
    )
    image_specs = (
        curated_images_for_entity(
            execution_id,
            entity_id,
            entity_type,
            research_lane=None if selected_lanes is None else "image",
            external_input_context=external_input_context,
        )
        if image_selected
        else []
    )
    return EntityFetchPlan(
        object_dir=resolve_entity_object_dir(
            execution_id,
            entity_id,
            etype_hint=entity_type,
        ),
        target_ref=build_entity_ref(domain, etype, entity_id),
        sources=_curated_sources_for_lanes(
            execution_id,
            entity_id,
            entity_type,
            selected_lanes,
        ),
        image_specs=[*homepage_specs, *image_specs],
        sourced_video_candidates=video_candidates,
        sourced_video_evidence=video_evidence,
        sourced_video_failure=sourced_video_failure,
        image_lane_selected=image_selected,
        homepage_media_selected=homepage_selected,
    )


__all__ = ["EntityFetchPlan", "prepare_entity_fetch_plan"]
