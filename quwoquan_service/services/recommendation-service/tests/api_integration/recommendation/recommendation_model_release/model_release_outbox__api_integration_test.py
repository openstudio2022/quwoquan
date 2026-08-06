from __future__ import annotations

from datetime import datetime

from internal.recommendation.recommendation_model_release.domain.model import (
    ActivateRelease,
    StageRelease,
)
from internal.recommendation.recommendation_model_release.domain.outbox import (
    MODEL_RELEASE_EVENT_PAYLOAD_FIELDS,
    validate_model_release_event_payload,
)
from internal.recommendation.recommendation_model_release.infrastructure.mongo_release_store import (
    MongoRecommendationModelReleaseStore,
)

# spec_ref: specs/feature-tree/recommendation-platform/spec.md#dom-001
# readiness_case: stage-model-release-api
# readiness_case: activate-model-release-api
pytest_plugins = ("tests.support.recommendation_mongo",)


def _stage(release_id: str, digest_character: str) -> StageRelease:
    return StageRelease.create(
        release_id=release_id,
        scenario="content_feed",
        model_digest=digest_character * 64,
        feature_contract_digest="f" * 64,
        artifact_uri=f"s3://quwoquan-models/content-feed/{release_id}/model.bin",
        verification_digest="e" * 64,
        evaluation_metrics={"auc": 0.91},
        idempotency_key=f"stage-{release_id}",
    )


def _activate(
    release_id: str,
    expected_active_release_id: str | None,
) -> ActivateRelease:
    return ActivateRelease.create(
        release_id=release_id,
        scenario="content_feed",
        expected_active_release_id=expected_active_release_id,
        idempotency_key=(
            f"activate-{release_id}-from-{expected_active_release_id or 'none'}"
        ),
    )


def _event(database, event_type: str, aggregate_id: str) -> dict:
    event = database["rec_model_release_outbox"].find_one(
        {"eventType": event_type, "aggregateId": aggregate_id}
    )
    assert event is not None
    return event


def _assert_contract_payload(event: dict) -> dict:
    event_type = event["eventType"]
    payload = event["payloadJson"]
    validate_model_release_event_payload(event_type, payload)
    assert set(payload) == set(MODEL_RELEASE_EVENT_PAYLOAD_FIELDS[event_type])
    assert payload["id"] == event["aggregateId"]
    return payload


def _assert_same_instant(payload_value: str, stored_value: datetime) -> None:
    payload_instant = datetime.fromisoformat(payload_value)
    assert payload_instant.tzinfo is not None
    assert stored_value.tzinfo is not None
    assert abs((payload_instant - stored_value).total_seconds()) < 0.002


def test_stage_activate_and_retire_persist_exact_declared_event_payloads(
    mongo_database,
) -> None:
    store = MongoRecommendationModelReleaseStore(mongo_database)
    store.ensure_indexes()

    assert store.stage(_stage("release-one", "a")).status == "staged"
    assert store.activate(_activate("release-one", None)).status == "active"
    assert store.stage(_stage("release-two", "b")).status == "staged"
    assert (
        store.activate(_activate("release-two", "release-one")).active_release_id
        == "release-two"
    )

    registry = mongo_database["rec_model_registry"]
    release_one = registry.find_one({"_id": "release-one"})
    release_two = registry.find_one({"_id": "release-two"})
    assert release_one is not None
    assert release_two is not None

    staged_one = _assert_contract_payload(
        _event(
            mongo_database,
            "RecommendationModelReleaseStaged",
            "release-one",
        )
    )
    assert staged_one["status"] == "staged"
    _assert_same_instant(staged_one["createdAt"], release_one["createdAt"])

    activated_one = _assert_contract_payload(
        _event(
            mongo_database,
            "RecommendationModelReleaseActivated",
            "release-one",
        )
    )
    assert activated_one["status"] == "active"
    _assert_same_instant(activated_one["activatedAt"], release_one["activatedAt"])

    retired_one = _assert_contract_payload(
        _event(
            mongo_database,
            "RecommendationModelReleaseRetired",
            "release-one",
        )
    )
    assert retired_one == {
        "id": "release-one",
        "scenario": "content_feed",
        "status": "retired",
        "retiredAt": retired_one["retiredAt"],
    }
    _assert_same_instant(retired_one["retiredAt"], release_one["retiredAt"])

    staged_two = _assert_contract_payload(
        _event(
            mongo_database,
            "RecommendationModelReleaseStaged",
            "release-two",
        )
    )
    _assert_same_instant(staged_two["createdAt"], release_two["createdAt"])

    activated_two = _assert_contract_payload(
        _event(
            mongo_database,
            "RecommendationModelReleaseActivated",
            "release-two",
        )
    )
    assert activated_two["status"] == "active"
    _assert_same_instant(activated_two["activatedAt"], release_two["activatedAt"])

    assert mongo_database["rec_model_release_outbox"].count_documents({}) == 5
    forbidden_legacy_fields = {
        "releaseId",
        "previousActiveReleaseId",
        "activatedReleaseId",
        "artifactUri",
        "verificationDigest",
    }
    for event in mongo_database["rec_model_release_outbox"].find({}):
        assert forbidden_legacy_fields.isdisjoint(event["payloadJson"])

    rollback = store.activate(_activate("release-one", "release-two"))
    assert rollback.status == "active"
    assert rollback.active_release_id == "release-one"
    assert registry.find_one({"_id": "release-one"})["status"] == "active"
    assert registry.find_one({"_id": "release-two"})["status"] == "retired"

    activated_one_events = list(
        mongo_database["rec_model_release_outbox"].find(
            {
                "eventType": "RecommendationModelReleaseActivated",
                "aggregateId": "release-one",
            }
        )
    )
    assert len(activated_one_events) == 2
    assert all(
        _assert_contract_payload(event)["status"] == "active"
        for event in activated_one_events
    )
    retired_two = _assert_contract_payload(
        _event(
            mongo_database,
            "RecommendationModelReleaseRetired",
            "release-two",
        )
    )
    assert retired_two["status"] == "retired"
    assert mongo_database["rec_model_release_outbox"].count_documents({}) == 7
