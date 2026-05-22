#!/usr/bin/env python3
"""
e2e_learning_loop_verify.py — End-to-end verification of the online learning loop.

Steps verified:
1. Behavior events exist in rec_learning_events (with scenario field)
2. Training samples exist in rec_training_samples
3. A model version exists in rec_model_registry
4. rec-model-service can score a request
5. rec_learning_events contain both impression and engagement types
6. Seed data bootstrap produces expected collections
7. Model registry has valid metrics (non-zero)
8. Feature store has user profiles

Usage:
  python3 e2e_learning_loop_verify.py --mongodb-uri mongodb://localhost:27017
  python3 e2e_learning_loop_verify.py --mongodb-uri mongodb://mongo:27017 --rec-model http://rec-model:8000
  python3 e2e_learning_loop_verify.py --full-pipeline  # runs seed → train → verify
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent


def _dry_run_db_name(db_name: str) -> str:
    if db_name.endswith("_dryrun"):
        return db_name
    return f"{db_name}_dryrun"


def check_learning_events(db, scenario: str) -> tuple[bool, str]:
    coll = db["rec_learning_events"]
    total = coll.count_documents({"scenario": scenario})
    if total == 0:
        return False, f"No learning events with scenario={scenario}"
    impressions = coll.count_documents({"scenario": scenario, "eventType": "rec_impression"})
    engagements = coll.count_documents({"scenario": scenario, "eventType": "rec_engagement"})
    return True, f"events: total={total}, impressions={impressions}, engagements={engagements}"


def check_training_samples(db, scenario: str) -> tuple[bool, str]:
    coll = db["rec_training_samples"]
    total = coll.count_documents({"scenario": scenario})
    if total == 0:
        return False, f"No training samples for scenario={scenario}"
    sample = coll.find_one({"scenario": scenario})
    has_labels = "labels" in (sample or {})
    has_item = "itemFeatures" in (sample or {})
    has_user = "userFeatures" in (sample or {})
    return True, f"samples: total={total}, has_labels={has_labels}, has_item={has_item}, has_user={has_user}"


def check_model_registry(db, scenario: str) -> tuple[bool, str]:
    coll = db["rec_model_registry"]
    total = coll.count_documents({"scenario": scenario})
    if total == 0:
        return False, f"No model versions for scenario={scenario}"
    latest = coll.find_one({"scenario": scenario}, sort=[("createdAt", -1)])
    metrics = latest.get("metrics", {}) if latest else {}
    auc = metrics.get("auc", 0)
    prod = coll.find_one({"scenario": scenario, "production": True})
    prod_info = f"prod={prod['version']}" if prod else "no production model"
    return True, f"registry: total={total}, latest_auc={auc}, {prod_info}"


def check_model_registry_metrics(db, scenario: str) -> tuple[bool, str]:
    """Verify the latest model has non-zero metrics."""
    coll = db["rec_model_registry"]
    latest = coll.find_one({"scenario": scenario}, sort=[("createdAt", -1)])
    if not latest:
        return False, "No model in registry"
    metrics = latest.get("metrics", {})
    auc = metrics.get("auc", 0)
    if auc == 0:
        return False, f"Model has zero AUC: {metrics}"
    return True, f"metrics valid: auc={auc}"


def check_user_feature_store(db) -> tuple[bool, str]:
    """Verify user feature profiles exist in rm_recommend_feature."""
    coll = db["rm_recommend_feature"]
    total = coll.count_documents({})
    if total == 0:
        return False, "No user profiles in rm_recommend_feature"
    sample = coll.find_one({})
    has_features = "userFeatures" in (sample or {})
    return True, f"user profiles: total={total}, has_features={has_features}"


def check_discovery_feed(db) -> tuple[bool, str]:
    """Verify posts exist in rm_discovery_feed."""
    coll = db["rm_discovery_feed"]
    total = coll.count_documents({})
    if total == 0:
        return False, "No posts in rm_discovery_feed"
    types = coll.distinct("contentType")
    return True, f"posts: total={total}, types={types}"


def check_model_service(rec_model_url: str) -> tuple[bool, str]:
    try:
        health_url = f"{rec_model_url}/health"
        req = urllib.request.Request(health_url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("status") != "ok":
            return False, f"health check returned: {data}"
        return True, "rec-model-service healthy"
    except Exception as e:
        return False, f"rec-model-service unreachable: {e}"


def check_score_endpoint(rec_model_url: str) -> tuple[bool, str]:
    try:
        url = f"{rec_model_url}/v1/score"
        body = json.dumps({
            "scenario": "content_feed",
            "sessionId": "e2e_verify_sess",
            "userId": "loop_verify_user",
            "candidates": [{"contentId": "test_1", "features": {"viewCount": 100}}],
            "userFeatures": {},
            "context": {},
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        scores = data.get("scores", [])
        if not scores:
            return False, "score endpoint returned 0 scores"
        return True, f"score endpoint returned {len(scores)} scores"
    except Exception as e:
        return False, f"score endpoint failed: {e}"


def check_model_reload_endpoint(rec_model_url: str) -> tuple[bool, str]:
    try:
        url = f"{rec_model_url}/v1/model/reload"
        req = urllib.request.Request(
            url,
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if data.get("status") != "reloaded":
            return False, f"reload endpoint returned: {data}"
        versions = data.get("versions") or {}
        if not versions:
            return False, "reload endpoint returned no versions"
        return True, f"reload endpoint ok: versions={versions}"
    except Exception as e:
        return False, f"reload endpoint failed: {e}"


def check_model_status_endpoint(rec_model_url: str) -> tuple[bool, str]:
    try:
        url = f"{rec_model_url}/v1/model/status"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        versions = data.get("versions") or {}
        last_reload = data.get("last_reload")
        if not versions:
            return False, f"status endpoint returned no versions: {data}"
        if not last_reload:
            return False, f"status endpoint missing last_reload: {data}"
        return True, f"status endpoint ok: versions={versions}, last_reload={last_reload}"
    except Exception as e:
        return False, f"status endpoint failed: {e}"


def check_seed_train_loop(db, scenario: str) -> tuple[bool, str]:
    """Verify seed data produced enough training samples with correct labels."""
    samples_coll = db["rec_training_samples"]
    total = samples_coll.count_documents({"scenario": scenario})
    if total == 0:
        return False, "No training samples after seed (seed→train loop broken)"
    positive = samples_coll.count_documents({"scenario": scenario, "labels.click": 1.0})
    negative = total - positive
    sample = samples_coll.find_one({"scenario": scenario})
    labels = sample.get("labels", {}) if sample else {}
    expected_keys = {"click", "dwell_s", "like", "favorite", "share", "comment", "follow", "dislike", "engaged"}
    missing = expected_keys - set(labels.keys())
    if missing:
        return False, f"Training sample labels missing keys: {missing}"
    return True, f"seed→train loop ok: {total} samples (positive={positive}, negative={negative})"


def check_model_score_loop(rec_model_url: str) -> tuple[bool, str]:
    """Verify /v1/score returns model-based (non-rule) scores."""
    try:
        url = f"{rec_model_url}/v1/score"
        body = json.dumps({
            "scenario": "content_feed",
            "sessionId": "e2e_model_verify_sess",
            "userId": "loop_verify_user",
            "candidates": [
                {"contentId": "test_1", "features": {"viewCount": 100, "contentType": "photo"}},
                {"contentId": "test_2", "features": {"viewCount": 50, "contentType": "video"}},
            ],
            "userFeatures": {},
            "context": {},
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        scores = data.get("scores", [])
        if not scores:
            return False, "model→score loop: no scores returned"
        first_detail = scores[0].get("detail", {})
        model_field = first_detail.get("model", "")
        if model_field == "rule" or model_field == "":
            return False, f"model→score loop: using rule fallback (model={model_field})"
        return True, f"model→score loop ok: model={model_field}, {len(scores)} candidates scored"
    except Exception as e:
        return False, f"model→score loop failed: {e}"


def run_seed_and_train(mongodb_uri: str, db_name: str, scenario: str) -> tuple[bool, str]:
    """Run seed data generation and training pipeline as a subprocess."""
    pipeline_script = SCRIPT_DIR / "train_pipeline.sh"
    if not pipeline_script.exists():
        return False, f"train_pipeline.sh not found at {pipeline_script}"

    cmd = [
        "bash", str(pipeline_script),
        "--scenario", scenario,
        "--mongodb-uri", mongodb_uri,
        "--db", db_name,
        "--dry-run",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            return False, f"Pipeline failed (exit {result.returncode}): {result.stderr[-500:]}"
        return True, "seed → train → evaluate pipeline completed"
    except subprocess.TimeoutExpired:
        return False, "Pipeline timed out after 300s"
    except Exception as e:
        return False, f"Pipeline execution error: {e}"


def main():
    p = argparse.ArgumentParser(description="E2E learning loop verification")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"))
    p.add_argument("--db", default="quwoquan_content")
    p.add_argument("--rec-model", default="http://localhost:18090")
    p.add_argument("--full-pipeline", action="store_true",
                   help="Run seed → train → verify (requires MongoDB running)")
    p.add_argument("--skip-service", action="store_true",
                   help="Skip rec-model-service health/score checks")
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri)
    db_name = _dry_run_db_name(args.db) if args.full_pipeline else args.db
    db = client[db_name]

    if args.full_pipeline:
        print("=" * 60)
        print(f"Running full pipeline: seed → train → evaluate (db={db_name})")
        print("=" * 60)
        passed, detail = run_seed_and_train(args.mongodb_uri, db_name, args.scenario)
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] Pipeline: {detail}")
        if not passed:
            return 1
        print()

    checks = [
        ("Discovery Feed", lambda: check_discovery_feed(db)),
        ("User Feature Store", lambda: check_user_feature_store(db)),
        ("Learning Events", lambda: check_learning_events(db, args.scenario)),
        ("Training Samples", lambda: check_training_samples(db, args.scenario)),
        ("Seed→Train Loop", lambda: check_seed_train_loop(db, args.scenario)),
        ("Model Registry (single)", lambda: check_model_registry(db, args.scenario)),
        ("Model Registry (multi-obj)", lambda: check_model_registry(db, f"{args.scenario}_multiobjective")),
        ("Model Metrics Valid", lambda: check_model_registry_metrics(db, args.scenario)),
    ]

    if not args.skip_service:
        checks.extend([
            ("Model Service Health", lambda: check_model_service(args.rec_model)),
            ("Score Endpoint", lambda: check_score_endpoint(args.rec_model)),
            ("Model Reload Endpoint", lambda: check_model_reload_endpoint(args.rec_model)),
            ("Model Status Endpoint", lambda: check_model_status_endpoint(args.rec_model)),
            ("Model→Score Loop", lambda: check_model_score_loop(args.rec_model)),
        ])

    print("=" * 60)
    print(f"E2E Learning Loop Verification — scenario={args.scenario}")
    print("=" * 60)

    all_pass = True
    for name, check_fn in checks:
        passed, detail = check_fn()
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {detail}")
        if not passed:
            all_pass = False

    print("=" * 60)
    if all_pass:
        print("LOOP VERIFICATION: ALL CHECKS PASSED")
        return 0
    else:
        print("LOOP VERIFICATION: SOME CHECKS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
