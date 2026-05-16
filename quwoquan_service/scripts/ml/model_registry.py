"""
Write model version to rec_model_registry.
Includes promotion gate: new model must beat current production by AUC delta.
Supports automatic rollback to previous production version.
"""
from datetime import datetime
from typing import Any


AUC_PROMOTION_DELTA = 0.005


def get_production_metrics(mongo_db, scenario: str) -> dict[str, Any] | None:
    """Fetch current production model metrics."""
    coll = mongo_db["rec_model_registry"]
    doc = coll.find_one({"scenario": scenario, "production": True}, sort=[("createdAt", -1)])
    if doc:
        return doc.get("metrics", {})
    return None


def get_production_version(mongo_db, scenario: str) -> dict[str, Any] | None:
    """Fetch current production model full document."""
    coll = mongo_db["rec_model_registry"]
    return coll.find_one({"scenario": scenario, "production": True}, sort=[("createdAt", -1)])


def check_promotion_gate(
    mongo_db,
    scenario: str,
    new_metrics: dict[str, Any],
) -> tuple[bool, str]:
    """Check if new model passes promotion gate.
    
    Returns (passed, reason).
    """
    current = get_production_metrics(mongo_db, scenario)
    if current is None:
        return True, "no existing production model"

    new_auc = new_metrics.get("auc", 0)
    current_auc = current.get("auc", 0)
    if new_auc < current_auc + AUC_PROMOTION_DELTA:
        return False, f"AUC {new_auc:.4f} < production {current_auc:.4f} + {AUC_PROMOTION_DELTA}"

    new_ndcg = new_metrics.get("ndcg_20", 0)
    current_ndcg = current.get("ndcg_20", 0)
    if new_ndcg < current_ndcg - 0.01:
        return False, f"NDCG@20 {new_ndcg:.4f} dropped below production {current_ndcg:.4f}"

    return True, f"AUC +{new_auc - current_auc:.4f}, NDCG@20 {new_ndcg:.4f} vs {current_ndcg:.4f}"


def rollback_to_previous(mongo_db, scenario: str) -> dict[str, Any] | None:
    """Rollback: demote current production, promote most recent non-production version.
    
    Returns the restored version document or None if no candidate.
    """
    coll = mongo_db["rec_model_registry"]
    now = datetime.utcnow()

    current_prod = coll.find_one({"scenario": scenario, "production": True}, sort=[("createdAt", -1)])
    if current_prod:
        coll.update_one(
            {"_id": current_prod["_id"]},
            {"$set": {"production": False, "updatedAt": now, "rolledBackAt": now}},
        )
        print(f"[model_registry] Demoted {scenario}/{current_prod['version']}")

    previous = coll.find_one(
        {"scenario": scenario, "production": False, "rolledBackAt": {"$exists": False}},
        sort=[("createdAt", -1)],
    )
    if previous is None:
        print(f"[model_registry] No previous version to rollback to for {scenario}")
        return None

    coll.update_one(
        {"_id": previous["_id"]},
        {"$set": {"production": True, "updatedAt": now, "restoredAt": now}},
    )
    print(f"[model_registry] Restored {scenario}/{previous['version']} as PRODUCTION")
    return previous


def list_versions(mongo_db, scenario: str, limit: int = 10) -> list[dict]:
    """List recent model versions for a scenario."""
    coll = mongo_db["rec_model_registry"]
    cursor = coll.find({"scenario": scenario}).sort("createdAt", -1).limit(limit)
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


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

    if production:
        passed, reason = check_promotion_gate(mongo_db, scenario, metrics)
        if not passed:
            print(f"[model_registry] GATE BLOCKED: {reason}")
            production = False
        else:
            print(f"[model_registry] Promotion gate passed: {reason}")
            coll.update_many(
                {"scenario": scenario, "production": True},
                {"$set": {"production": False, "updatedAt": now}},
            )

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
    status = "PRODUCTION" if production else "staged"
    print(f"[model_registry] Registered {scenario}/{version} as {status}")
