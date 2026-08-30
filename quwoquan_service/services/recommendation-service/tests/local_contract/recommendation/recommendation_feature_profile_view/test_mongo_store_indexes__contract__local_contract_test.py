from __future__ import annotations

from typing import Any

from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import (
    MongoFeatureProfileStore,
)


class _RecordingCollection:
    def __init__(self) -> None:
        self.indexes: list[tuple[tuple[tuple[str, int], ...], dict[str, Any]]] = []

    def create_index(self, keys, **options):
        self.indexes.append((tuple(keys), dict(options)))
        return options.get("name", "")


class _RecordingDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, _RecordingCollection] = {}

    def __getitem__(self, name: str) -> _RecordingCollection:
        return self.collections.setdefault(name, _RecordingCollection())


def test_intersection_indexes_are_created_on_their_exact_owned_collections() -> None:
    database = _RecordingDatabase()
    store = MongoFeatureProfileStore(database)

    store.ensure_indexes()

    expected = {
        (
            "recommendation_intersection_gathering_participations",
            "idx_recommendation_intersection_gathering_participation_persona",
        ): (("personaId", 1), ("active", 1), ("gatheringId", 1)),
        (
            "recommendation_intersection_gathering_participations",
            "idx_recommendation_intersection_gathering_participation_gathering",
        ): (("gatheringId", 1), ("active", 1), ("personaId", 1)),
        (
            "recommendation_intersection_gathering_recaps",
            "idx_recommendation_intersection_gathering_recap_persona",
        ): (("personaId", 1), ("active", 1), ("gatheringId", 1)),
        (
            "recommendation_intersection_facilitations",
            "idx_recommendation_intersection_facilitation_occurred",
        ): (("occurredAt", -1),),
    }
    actual = {
        (collection_name, str(options.get("name") or "")): keys
        for collection_name, collection in database.collections.items()
        for keys, options in collection.indexes
        if str(options.get("name") or "")
        in {index_name for _, index_name in expected}
    }

    assert actual == expected
