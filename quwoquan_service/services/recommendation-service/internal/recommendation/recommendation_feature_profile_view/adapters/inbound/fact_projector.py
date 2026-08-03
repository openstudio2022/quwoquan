from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from ...application.projector import Projector


class FactProjectionAdapter:
    """Typed inbound port for authoritative exposure and feedback facts."""

    def __init__(self, projector: Projector) -> None:
        if projector is None:
            raise ValueError("RecommendationFeatureProfileView projector is required")
        self._projector = projector

    def project_exposure(
        self,
        *,
        exposure_fact_id: str,
        subject_id: str,
        target_id: str,
        occurred_at: datetime,
    ) -> bool:
        return self._projector.project_exposure(
            exposure_fact_id=exposure_fact_id,
            subject_id=subject_id,
            target_id=target_id,
            occurred_at=occurred_at,
        )

    def project_behavior(
        self,
        *,
        event_id: str,
        source_sequence: int,
        subject_id: str,
        payload: Mapping[str, Any],
        feedback_fact_id: str,
        exposure_fact_id: str,
        occurred_at: datetime,
    ) -> bool:
        return self._projector.project_behavior(
            event_id=event_id,
            source_sequence=source_sequence,
            subject_id=subject_id,
            payload=payload,
            feedback_fact_id=feedback_fact_id,
            exposure_fact_id=exposure_fact_id,
            occurred_at=occurred_at,
        )

    def project_tag_feedback(
        self,
        *,
        event_id: str,
        subject_id: str,
        actor_kind: str,
        tag_ref: str,
        action: str,
        recorded_at: datetime,
    ) -> bool:
        return self._projector.project_tag_feedback(
            event_id=event_id,
            subject_id=subject_id,
            actor_kind=actor_kind,
            tag_ref=tag_ref,
            action=action,
            recorded_at=recorded_at,
        )
