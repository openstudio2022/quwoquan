from datetime import datetime, timezone

import pytest

from internal.recommendation.recommendation_feature_profile_view.application.projector import (
    Projector,
)


class _Store:
    def __init__(self) -> None:
        self.mutation = None

    def apply_behavior_if_absent(self, mutation) -> bool:
        self.mutation = mutation
        return True

    def apply_exposure_if_absent(self, mutation) -> bool:
        self.exposure_mutation = mutation
        return True

    def apply_tag_feedback_if_absent(self, mutation) -> bool:
        self.tag_feedback_mutation = mutation
        return True

def test_behavior_projection_uses_canonical_state_without_copying_policy_weights() -> None:
    store = _Store()
    projector = Projector(store)
    occurred_at = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)

    assert projector.project_behavior(
        event_id="event-001",
        source_sequence=9,
        subject_id="persona-viewer",
        payload={
            "contentId": "post-001",
            "action": "like",
            "state": "interaction",
            "duration": 0,
            "tagRefs": ["Topic/旅行"],
            "entityRefs": ["地点/景区/色达"],
            "authorId": "persona-author",
            "contentType": "post",
            "impactHelpType": "decision",
            "intersectionDimension": "same_city",
            "intersectionTagRefs": ["Topic/旅行"],
        },
        feedback_fact_id="feedback-001",
        exposure_fact_id="exposure-001",
        occurred_at=occurred_at,
    ) is True
    mutation = store.mutation
    assert mutation.collaborative_signal == 1.0
    assert mutation.sparse_increments == {
        "action:like": 1.0,
        "state:interaction": 1.0,
        "tag:Topic/旅行": 1.0,
        "entity:地点/景区/色达": 1.0,
    }
    assert mutation.intersection_increments == {
        "intersectionDimension:same_city": 1.0,
        "tag:Topic/旅行": 1.0,
    }
    assert mutation.content_type == "post"
    assert mutation.impact_help_type == "decision"
    assert mutation.intersection_dimension == "same_city"
    assert mutation.intersection_tag_refs == ("Topic/旅行",)


def test_behavior_projection_rejects_forged_impact_help_type_grammar() -> None:
    with pytest.raises(ValueError, match="impact help type"):
        Projector(_Store()).project_behavior(
            event_id="event-001",
            source_sequence=9,
            subject_id="persona-viewer",
            payload={
                "contentId": "post-001",
                "action": "like",
                "state": "interaction",
                "impactHelpType": "decision/legacy",
            },
            feedback_fact_id="feedback-001",
            exposure_fact_id="exposure-001",
            occurred_at=datetime.now(timezone.utc),
        )


def test_behavior_projection_rejects_unknown_state() -> None:
    with pytest.raises(ValueError, match="closed set"):
        Projector(_Store()).project_behavior(
            event_id="event-001",
            source_sequence=9,
            subject_id="persona-viewer",
            payload={
                "contentId": "post-001",
                "action": "like",
                "state": "positive",
            },
            feedback_fact_id="feedback-001",
            exposure_fact_id="exposure-001",
            occurred_at=datetime.now(timezone.utc),
        )


def test_exposure_projection_uses_exposure_identity_as_the_single_receipt_key() -> None:
    store = _Store()
    occurred_at = datetime.now(timezone.utc)
    assert Projector(store).project_exposure(
        exposure_fact_id="exposure-001",
        subject_id="persona-viewer",
        target_id="post-001",
        occurred_at=occurred_at,
    ) is True
    assert store.exposure_mutation.exposure_fact_id == "exposure-001"
    assert store.exposure_mutation.occurred_at == occurred_at


@pytest.mark.parametrize("action", ("click", "dislike", "ignore", "correct"))
def test_tag_feedback_projection_uses_the_closed_action_set(action: str) -> None:
    store = _Store()
    recorded_at = datetime.now(timezone.utc)
    assert Projector(store).project_tag_feedback(
        event_id="tag-feedback-001",
        subject_id="persona-viewer",
        actor_kind="persona",
        tag_ref="Topic/旅行",
        action=action,
        recorded_at=recorded_at,
    ) is True
    assert store.tag_feedback_mutation.action == action
    assert store.tag_feedback_mutation.tag_ref == "Topic/旅行"


def test_tag_feedback_projection_rejects_an_unregistered_action() -> None:
    with pytest.raises(ValueError, match="input is invalid"):
        Projector(_Store()).project_tag_feedback(
            event_id="tag-feedback-001",
            subject_id="persona-viewer",
            actor_kind="persona",
            tag_ref="Topic/旅行",
            action="neutral",
            recorded_at=datetime.now(timezone.utc),
        )
