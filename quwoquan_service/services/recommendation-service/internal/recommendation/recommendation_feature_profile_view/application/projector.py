from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Mapping, Protocol


class FeatureProfileStore(Protocol):
    def apply_behavior_if_absent(self, mutation: "BehaviorFeatureMutation") -> bool: ...

    def apply_exposure_if_absent(self, mutation: "ExposureFeatureMutation") -> bool: ...

    def apply_tag_feedback_if_absent(self, mutation: "TagFeedbackMutation") -> bool: ...

    def apply_search_signal_if_absent(self, mutation: "SearchSignalMutation") -> bool: ...


@dataclass(frozen=True, slots=True)
class ExposureFeatureMutation:
    exposure_fact_id: str
    subject_id: str
    target_id: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class BehaviorFeatureMutation:
    event_id: str
    source_sequence: int
    subject_id: str
    author_id: str | None
    target_id: str
    content_type: str | None
    impact_help_type: str | None
    intersection_dimension: str | None
    intersection_tag_refs: tuple[str, ...]
    feedback_fact_id: str
    exposure_fact_id: str
    action: str
    state: str | None
    sparse_increments: Mapping[str, float]
    collaborative_signal: float
    intersection_increments: Mapping[str, float]
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class TagFeedbackMutation:
    event_id: str
    subject_id: str
    actor_kind: str
    tag_ref: str
    action: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class SearchSignalMutation:
    """搜推联动短期意图（search.RecommendationSignalFact 归并结果）。

    terms 是 normalizedQuery 与 relatedTerms 的合并去重集合；隐私约束要求
    这些词只进入特征投影，绝不进入日志、DLQ 或错误信息。
    """

    signal_id: str
    subject_id: str
    signal_type: str
    terms: tuple[str, ...]
    created_at: datetime


class Projector:
    def __init__(self, store: FeatureProfileStore) -> None:
        self._store = store

    def project_exposure(
        self,
        *,
        exposure_fact_id: str,
        subject_id: str,
        target_id: str,
        occurred_at: datetime,
    ) -> bool:
        if (
            not exposure_fact_id.strip()
            or not subject_id.strip()
            or not target_id.strip()
            or occurred_at.tzinfo is None
        ):
            raise ValueError("exposure feature projection input is incomplete")
        return self._store.apply_exposure_if_absent(
            ExposureFeatureMutation(
                exposure_fact_id=exposure_fact_id.strip(),
                subject_id=subject_id.strip(),
                target_id=target_id.strip(),
                occurred_at=occurred_at,
            )
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
        normalized_event = event_id.strip()
        normalized_subject = subject_id.strip()
        target_id = str(payload.get("contentId") or "").strip()
        action = str(payload.get("action") or "").strip()
        state = str(payload.get("state") or "").strip() or None
        if (
            not normalized_event
            or source_sequence <= 0
            or not normalized_subject
            or not target_id
            or not action
            or not feedback_fact_id.strip()
            or not exposure_fact_id.strip()
            or occurred_at.tzinfo is None
        ):
            raise ValueError("behavior feature projection input is incomplete")
        if len(action) > 64 or not action.replace("_", "").isalnum():
            raise ValueError("behavior feature action is outside the canonical identifier grammar")
        allowed_states = {
            "served",
            "visible",
            "impressed",
            "click",
            "dwell",
            "interaction",
            "negative",
        }
        if state is not None and state not in allowed_states:
            raise ValueError("behavior feature state is outside the canonical closed set")
        duration = float(payload.get("duration") or 0.0)
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("behavior feature duration must be finite and non-negative")
        sparse: dict[str, float] = {f"action:{action}": 1.0}
        if state is not None:
            sparse[f"state:{state}"] = 1.0
        if duration > 0:
            sparse["durationSeconds"] = duration
        for tag_ref in _bounded_strings(payload.get("tagRefs"), maximum=50):
            sparse[f"tag:{tag_ref}"] = 1.0
        for entity_ref in _bounded_strings(payload.get("entityRefs"), maximum=50):
            sparse[f"entity:{entity_ref}"] = 1.0

        intersection: dict[str, float] = {}
        for name in ("intersectionDimension", "intersectionClass", "intersectionSourceRef"):
            value = str(payload.get(name) or "").strip()
            if value:
                intersection[f"{name}:{value}"] = 1.0
        for tag_ref in _bounded_strings(payload.get("intersectionTagRefs"), maximum=50):
            intersection[f"tag:{tag_ref}"] = 1.0

        collaborative_signal = 0.0
        if state in {"impressed", "click", "dwell", "interaction"}:
            collaborative_signal = 1.0
        elif state == "negative":
            collaborative_signal = -1.0
        impact_help_type = str(payload.get("impactHelpType") or "").strip() or None
        if impact_help_type is not None and (
            len(impact_help_type) > 64
            or not impact_help_type.replace("_", "").isalnum()
        ):
            raise ValueError("behavior impact help type is outside the canonical identifier grammar")
        return self._store.apply_behavior_if_absent(
            BehaviorFeatureMutation(
                event_id=normalized_event,
                source_sequence=source_sequence,
                subject_id=normalized_subject,
                author_id=str(payload.get("authorId") or "").strip() or None,
                target_id=target_id,
                content_type=str(payload.get("contentType") or "").strip() or None,
                impact_help_type=impact_help_type,
                intersection_dimension=(
                    str(payload.get("intersectionDimension") or "").strip() or None
                ),
                intersection_tag_refs=_bounded_strings(
                    payload.get("intersectionTagRefs"),
                    maximum=50,
                ),
                feedback_fact_id=feedback_fact_id.strip(),
                exposure_fact_id=exposure_fact_id.strip(),
                action=action,
                state=state,
                sparse_increments=sparse,
                collaborative_signal=collaborative_signal,
                intersection_increments=intersection,
                occurred_at=occurred_at,
            )
        )

    def project_search_signal(
        self,
        *,
        signal_id: str,
        subject_id: str,
        signal_type: str,
        terms: tuple[str, ...],
        created_at: datetime,
    ) -> bool:
        normalized_signal = signal_id.strip()
        normalized_subject = subject_id.strip()
        normalized_type = signal_type.strip()
        normalized_terms = tuple(
            dict.fromkeys(term.strip() for term in terms if term.strip())
        )
        if (
            not normalized_signal
            or not normalized_subject
            or normalized_type not in {"query", "click"}
            or created_at.tzinfo is None
        ):
            raise ValueError("search signal feature projection input is invalid")
        if normalized_type == "query" and not normalized_terms:
            raise ValueError("search query signal requires at least one term")
        return self._store.apply_search_signal_if_absent(
            SearchSignalMutation(
                signal_id=normalized_signal,
                subject_id=normalized_subject,
                signal_type=normalized_type,
                terms=normalized_terms,
                created_at=created_at,
            )
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
        normalized_event = event_id.strip()
        normalized_subject = subject_id.strip()
        normalized_actor_kind = actor_kind.strip()
        normalized_tag = tag_ref.strip()
        normalized_action = action.strip()
        if (
            not normalized_event
            or not normalized_subject
            or normalized_actor_kind not in {"persona", "device"}
            or not normalized_tag
            or normalized_action not in {"click", "dislike", "ignore", "correct"}
            or recorded_at.tzinfo is None
        ):
            raise ValueError("tag feedback feature projection input is invalid")
        return self._store.apply_tag_feedback_if_absent(
            TagFeedbackMutation(
                event_id=normalized_event,
                subject_id=normalized_subject,
                actor_kind=normalized_actor_kind,
                tag_ref=normalized_tag,
                action=normalized_action,
                recorded_at=recorded_at,
            )
        )


def _bounded_strings(raw: Any, *, maximum: int) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) > maximum:
        raise ValueError("behavior feature references exceed the canonical bound")
    normalized = tuple(str(value).strip() for value in raw)
    if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError("behavior feature references must be non-empty and unique")
    return normalized
