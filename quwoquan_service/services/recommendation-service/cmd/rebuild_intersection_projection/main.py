"""Rebuild RecommendationFeatureProfileView intersections from typed evidence.

Usage is intentionally two phase. `--inspect` is read-only and returns the
source identity digest. `--execute` requires that exact digest through the
protected environment, so a changed evidence baseline fails before mutation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from pymongo import MongoClient

from internal.recommendation.recommendation_feature_profile_view.application.intersection_materializer import (
    Materializer,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_projector import (
    Projector,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_rebuild import (
    IntersectionRebuilder,
)
from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import (
    MongoFeatureProfileStore,
)
from internal.recommendation.recommendation_subject_closure_fact.infrastructure.mongo_store import (
    MongoSubjectClosureStore,
)


EXPECTED_DIGEST_ENV = "RECOMMENDATION_INTERSECTION_REBUILD_SOURCE_DIGEST"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--execute", action="store_true")
    return parser.parse_args()


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> None:
    arguments = _arguments()
    mongo_uri = _required_environment("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE", "quwoquan_recommendation").strip()
    if database_name != "quwoquan_recommendation":
        raise RuntimeError("MONGODB_DATABASE must be quwoquan_recommendation")
    client = MongoClient(mongo_uri)
    try:
        client.admin.command("ping")
        database = client[database_name]
        store = MongoFeatureProfileStore(database)
        closures = MongoSubjectClosureStore(database)
        store.ensure_indexes()
        closures.ensure_indexes()
        rebuilder = IntersectionRebuilder(
            store=store,
            materializer=Materializer(
                evidence=store,
                projector=Projector(store),
            ),
            subject_closures=closures,
        )
        if arguments.inspect:
            payload = {"mode": "inspect", **rebuilder.plan().public_summary()}
        else:
            report = rebuilder.rebuild(_required_environment(EXPECTED_DIGEST_ENV))
            payload = {"mode": "execute", **report.as_dict()}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    finally:
        client.close()


if __name__ == "__main__":
    main()
