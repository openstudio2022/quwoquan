from dataclasses import replace
from datetime import datetime, timezone

import pytest

from internal.recommendation.recommendation_exposure_fact.application.appender import (
    Appender,
    ExposureFact,
    canonical_snapshot_digest,
)


class _Store:
    def __init__(self) -> None:
        self.facts = {}

    def append_if_absent(self, fact):
        existing = self.facts.get(fact.exposure_id)
        if existing:
            return existing, False
        self.facts[fact.exposure_id] = fact
        return fact, True

    def find_by_attribution(self, feed_request_id, target_id):
        return next(
            (
                fact
                for fact in self.facts.values()
                if fact.feed_request_id == feed_request_id and fact.target_id == target_id
            ),
            None,
        )


class _Closures:
    def __init__(self, *closed) -> None:
        self.closed = set(closed)

    def exists(self, account_id):
        return account_id in self.closed


def _fact(*, ordinal: int = 0, subject_id: str = "account-001") -> ExposureFact:
    now = datetime.now(timezone.utc)
    user_snapshot = {"travelAffinity": 0.8}
    item_snapshot = {"qualityScore": 0.9}
    return ExposureFact(
        exposure_id="exposure-001",
        source_event_id="delivery-event-001",
        delivery_page_id="page-001",
        feed_request_id="request-001",
        window_id="window-001",
        subject_id=subject_id,
        persona_id="persona-001",
        scenario="content_feed",
        target_type="post",
        target_id="post-001",
        ordinal=ordinal,
        model_bucket="model",
        model_channel="champion",
        model_release_id="release-001",
        feature_snapshot_at=now,
        feature_snapshot_digest=canonical_snapshot_digest(user_snapshot, item_snapshot),
        ranking_snapshot_digest="a" * 64,
        user_feature_snapshot=user_snapshot,
        item_feature_snapshot=item_snapshot,
        exposed_at=now,
        recorded_at=now,
    )


def test_exposure_fact_is_idempotent_by_delivery_identity() -> None:
    store = _Store()
    appender = Appender(store, _Closures())
    fact = _fact()
    assert appender.append(fact)[1] is True
    assert appender.append(fact)[1] is False
    assert appender.find_by_attribution("request-001", "post-001") == fact


def test_exposure_fact_rejects_negative_ordinal_and_closed_subject() -> None:
    with pytest.raises(ValueError):
        Appender(_Store(), _Closures()).append(_fact(ordinal=-1))
    with pytest.raises(PermissionError):
        Appender(_Store(), _Closures("account-001")).append(_fact())


def test_exposure_fact_rejects_snapshot_digest_drift() -> None:
    fact = _fact()
    drifted = replace(fact, feature_snapshot_digest="0" * 64)
    with pytest.raises(ValueError, match="digest"):
        Appender(_Store(), _Closures()).append(drifted)
