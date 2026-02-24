"""
Write model version to rec_model_registry (per _projections/model_registry.yaml).
Model file path can be local or OSS; artifactPath stores the path.
"""
import os
from datetime import datetime
from typing import Any


def write_registry(
    mongo_db,
    scenario: str,
    version: str,
    metrics: dict[str, Any],
    artifact_path: str,
    production: bool = False,
):
    coll = mongo_db["rec_model_registry"]
    now = datetime.utcnow()
    # Unset production on other versions for this scenario
    if production:
        coll.update_many({"scenario": scenario, "production": True}, {"$set": {"production": False}})
    doc = {
        "scenario": scenario,
        "version": version,
        "metrics": metrics,
        "artifactPath": artifact_path,
        "production": production,
        "createdAt": now,
        "updatedAt": now,
    }
    coll.insert_one(doc)
