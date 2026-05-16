"""
CLI wrapper for model_registry operations: promote, rollback, list, upload-artifacts.
Used by CI pipeline and manual operations.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from pymongo import MongoClient

import model_registry
import artifact_store


def _connect():
    uri = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true")
    db_name = os.environ.get("DB", os.environ.get("MONGODB_DATABASE", "quwoquan_content"))
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client[db_name]


def cmd_promote(args):
    db = _connect()
    coll = db["rec_model_registry"]
    latest = coll.find_one(
        {"scenario": args.scenario, "production": False},
        sort=[("createdAt", -1)],
    )
    if not latest:
        print(f"[promote] No staged model found for scenario={args.scenario}")
        sys.exit(1)

    version = args.version or latest["version"]
    doc = coll.find_one({"scenario": args.scenario, "version": version})
    if not doc:
        print(f"[promote] Version {version} not found for scenario={args.scenario}")
        sys.exit(1)

    artifact_uri = str(doc.get("artifactUri", "")).strip()
    if not artifact_uri:
        print(f"[promote] Missing artifactUri for scenario={args.scenario}/{version}")
        sys.exit(1)
    if not artifact_store.exists(artifact_uri):
        print(f"[promote] Artifact not accessible: {artifact_uri}")
        sys.exit(1)

    metrics = doc.get("metrics", {})
    passed, reason = model_registry.check_promotion_gate(db, args.scenario, metrics)
    if not passed and not args.force:
        print(f"[promote] GATE BLOCKED: {reason}")
        sys.exit(1)

    from datetime import datetime
    now = datetime.utcnow()
    coll.update_many(
        {"scenario": args.scenario, "production": True},
        {"$set": {"production": False, "updatedAt": now}},
    )
    coll.update_one(
        {"_id": doc["_id"]},
        {"$set": {"production": True, "updatedAt": now, "promotedAt": now}},
    )
    print(f"[promote] {args.scenario}/{version} promoted to PRODUCTION ({reason})")


def cmd_rollback(args):
    db = _connect()
    result = model_registry.rollback_to_previous(db, args.scenario)
    if result:
        print(f"[rollback] Restored {args.scenario}/{result['version']}")
    else:
        print(f"[rollback] No previous version available for {args.scenario}")
        sys.exit(1)


def cmd_list(args):
    db = _connect()
    versions = model_registry.list_versions(db, args.scenario, limit=args.limit)
    for v in versions:
        prod_mark = " [PRODUCTION]" if v.get("production") else ""
        metrics_str = json.dumps(v.get("metrics", {}), ensure_ascii=False)
        print(f"  {v['version']} ({v.get('modelType', '?')}){prod_mark} metrics={metrics_str}")


def cmd_upload_artifacts(args):
    db = _connect()
    coll = db["rec_model_registry"]
    query = {"scenario": args.scenario, "production": True}
    doc = coll.find_one(query, sort=[("createdAt", -1)])
    if not doc:
        print(f"[upload] No production model for scenario={args.scenario}")
        return

    artifact_path = doc.get("artifactPath", "")
    if not artifact_path or not os.path.exists(artifact_path):
        print(f"[upload] Artifact path not found locally: {artifact_path}")
        return

    version = doc["version"]
    path_obj = Path(artifact_path)

    if path_obj.is_file():
        uri = artifact_store.upload(str(path_obj), args.scenario, version)
        coll.update_one({"_id": doc["_id"]}, {"$set": {"artifactUri": uri}})
        print(f"[upload] Updated registry with artifactUri={uri}")

        if path_obj.suffix == ".json":
            try:
                config = json.loads(path_obj.read_text())
                model_files = config.get("model_files", {})
                for obj_name, filename in model_files.items():
                    sub_path = path_obj.parent / filename
                    if sub_path.exists():
                        artifact_store.upload(str(sub_path), args.scenario, version)
            except Exception as e:
                print(f"[upload] WARN: failed to upload sub-models: {e}")
    elif path_obj.is_dir():
        for f in path_obj.iterdir():
            if f.is_file() and f.suffix in (".txt", ".json", ".bin"):
                uri = artifact_store.upload(str(f), args.scenario, version)
        coll.update_one(
            {"_id": doc["_id"]},
            {"$set": {"artifactUri": f"s3://{artifact_store.DEFAULT_BUCKET}/models/{args.scenario}/{version}/"}},
        )


def main():
    parser = argparse.ArgumentParser(description="Model Registry CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_promote = sub.add_parser("promote", help="Promote a model version to production")
    p_promote.add_argument("--scenario", required=True)
    p_promote.add_argument("--version", default="", help="Specific version (default: latest staged)")
    p_promote.add_argument("--force", action="store_true", help="Skip promotion gate")

    p_rollback = sub.add_parser("rollback", help="Rollback to previous production version")
    p_rollback.add_argument("--scenario", required=True)

    p_list = sub.add_parser("list", help="List recent model versions")
    p_list.add_argument("--scenario", required=True)
    p_list.add_argument("--limit", type=int, default=10)

    p_upload = sub.add_parser("upload-artifacts", help="Upload production model artifacts to S3")
    p_upload.add_argument("--scenario", required=True)

    args = parser.parse_args()
    dispatch = {
        "promote": cmd_promote,
        "rollback": cmd_rollback,
        "list": cmd_list,
        "upload-artifacts": cmd_upload_artifacts,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
