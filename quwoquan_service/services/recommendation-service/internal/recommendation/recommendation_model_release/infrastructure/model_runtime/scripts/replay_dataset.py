#!/usr/bin/env python3
"""Fixed replay dataset management (W13/B20).

冻结一份可复现的评估样本集（rec_replay_datasets），使跨模型版本的 replay
对比在同一数据上进行（滚动 test 切片每次运行数据不同，无法作为版本间
NDCG/AUC 对比的证据）。

Usage:
    # 冻结当前 test 切片为固定 replay dataset
    python3 replay_dataset.py freeze --scenario content_feed [--dataset-id rds_2026w29]

    # 列出已冻结的 dataset
    python3 replay_dataset.py list --scenario content_feed

evaluate.py 消费：--replay-dataset <datasetId> 时从物化快照集合
（rec_replay_samples）取完整样本文档，输出的 metrics 附带 datasetId，
进入 replay 周报证据链。

N0-5：freeze 物化完整样本文档（不再只存 sampleIds）。sample_joiner --clean
会 drop 场景样本，若只存 ids 冻结集会被物理摧毁；物化快照独立于
rec_training_samples 生命周期，保证跨周可复现。
"""
import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone

from privacy_guard import closed_subject_ids, reject_closed_documents

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

REPLAY_DATASET_COLLECTION = "rec_replay_datasets"
REPLAY_SAMPLE_COLLECTION = "rec_replay_samples"


def _default_dataset_id(now: datetime) -> str:
    iso = now.isocalendar()
    return f"rds_{iso.year}w{iso.week:02d}"


def _dataset_digest(scenario: str, rows: list[dict]) -> str:
    identities = sorted(str(row.get("_id") or "").strip() for row in rows)
    if not identities or any(not identity for identity in identities):
        raise ValueError("replay dataset rows require immutable source identities")
    material = scenario.strip() + "\n" + "\n".join(identities)
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def freeze(args) -> int:
    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    samples_coll = db["rec_training_samples"]
    datasets_coll = db[REPLAY_DATASET_COLLECTION]
    snapshot_coll = db[REPLAY_SAMPLE_COLLECTION]

    datasets_coll.create_index(
        [("datasetDigest", 1)],
        unique=True,
        name="uq_recommendation_replay_dataset_digest",
    )
    snapshot_coll.create_index(
        [("datasetId", 1), ("sourceSampleId", 1)],
        unique=True,
        name="uq_recommendation_replay_sample_identity",
    )

    # 物化快照需要完整样本文档（features/labels/ts），不再只投影 ids。
    rows = list(
        samples_coll.find({"scenario": args.scenario}).sort("ts", 1)
    )
    rows, closed_subjects = reject_closed_documents(db, rows)
    if len(rows) < args.min_samples:
        print(
            f"[replay-dataset] only {len(rows)} open-subject samples "
            f"(< {args.min_samples}, closed_subjects={len(closed_subjects)}), "
            "refuse to freeze",
            file=sys.stderr,
        )
        return 1

    # 与 evaluate.py 的切片语义一致：最后 15% 作为评估集。
    val_end = int(len(rows) * 0.85)
    eval_rows = rows[val_end:]
    now = datetime.now(timezone.utc)
    dataset_id = args.dataset_id or _default_dataset_id(now)
    dataset_digest = _dataset_digest(args.scenario, eval_rows)

    existing = datasets_coll.find_one({"_id": dataset_id})
    if existing:
        privacy_status = existing.get("privacyStatus")
        if privacy_status == "building":
            snapshot_coll.delete_many({"datasetId": dataset_id})
            datasets_coll.delete_one(
                {"_id": dataset_id, "privacyStatus": "building"}
            )
            existing = None
        elif privacy_status == "privacy_invalidated":
            print(
                f"[replay-dataset] {dataset_id} is privacy_invalidated; "
                "dataset ids are immutable and cannot be reused",
                file=sys.stderr,
            )
            return 1
    if existing:
        print(
            f"[replay-dataset] {dataset_id} already frozen at {existing.get('frozenAt')} "
            f"({existing.get('sampleCount', 0)} samples); immutable, not overwritten",
            file=sys.stderr,
        )
        return 0

    datasets_coll.insert_one({
        "_id": dataset_id,
        "scenario": args.scenario,
        "datasetDigest": dataset_digest,
        "frozenAt": now,
        "sampleCount": 0,
        "snapshotCollection": REPLAY_SAMPLE_COLLECTION,
        "privacyStatus": "building",
        "tsRange": {
            "from": None,
            "to": None,
        },
    })
    try:
        eval_rows, newly_closed = reject_closed_documents(db, eval_rows)
        if len(eval_rows) < args.min_samples:
            raise RuntimeError(
                "account closure reduced replay dataset below minimum size "
                f"(closed_subjects={len(newly_closed)})"
            )
        dataset_digest = _dataset_digest(args.scenario, eval_rows)
        snapshot_docs = []
        for row in eval_rows:
            doc = dict(row)
            doc["datasetId"] = dataset_id
            doc["sourceSampleId"] = doc.pop("_id")
            snapshot_docs.append(doc)
        if snapshot_docs:
            snapshot_coll.insert_many(snapshot_docs)
        snapshot_coll.create_index("datasetId")
        snapshot_coll.create_index([("userId", 1), ("datasetId", 1)])

        late_closed = closed_subject_ids(
            db,
            (doc["userId"] for doc in snapshot_docs),
        )
        if late_closed:
            snapshot_coll.delete_many({
                "datasetId": dataset_id,
                "userId": {"$in": list(late_closed)},
            })
            datasets_coll.update_one(
                {"_id": dataset_id},
                {"$set": {
                    "privacyStatus": "privacy_invalidated",
                    "privacyInvalidatedAt": datetime.now(timezone.utc),
                    "privacyInvalidationReason": "account_closed",
                }},
            )
            print(
                "[replay-dataset] concurrent account closure invalidated dataset",
                file=sys.stderr,
            )
            return 1

        activated = datasets_coll.update_one(
            {"_id": dataset_id, "privacyStatus": "building"},
            {"$set": {
                "privacyStatus": "active",
                "datasetDigest": dataset_digest,
                "sampleCount": len(eval_rows),
                "tsRange": {
                    "from": eval_rows[0].get("ts"),
                    "to": eval_rows[-1].get("ts"),
                },
            }},
        )
        if activated.modified_count != 1:
            raise RuntimeError(
                "replay dataset was privacy-invalidated while freezing"
            )
    except Exception:
        snapshot_coll.delete_many({"datasetId": dataset_id})
        datasets_coll.delete_one(
            {"_id": dataset_id, "privacyStatus": "building"}
        )
        raise
    print(
        f"[replay-dataset] frozen {dataset_id}: {len(eval_rows)} samples "
        f"materialized to {REPLAY_SAMPLE_COLLECTION} (scenario={args.scenario})",
        file=sys.stderr,
    )
    print(dataset_id)
    return 0


def list_datasets(args) -> int:
    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    for doc in db[REPLAY_DATASET_COLLECTION].find(
        {"scenario": args.scenario}
    ).sort("frozenAt", -1):
        print(
            f"{doc['_id']}\tfrozenAt={doc.get('frozenAt')}\t"
            f"samples={doc.get('sampleCount', 0)}\t"
            f"privacyStatus={doc.get('privacyStatus')}"
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Fixed replay dataset management")
    p.add_argument("command", choices=["freeze", "list"])
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--dataset-id", default=None)
    p.add_argument("--min-samples", type=int, default=100)
    p.add_argument(
        "--mongodb-uri",
        default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"),
    )
    p.add_argument("--db", default=os.environ.get("DB", "quwoquan_content"))
    args = p.parse_args()
    if args.command == "freeze":
        return freeze(args)
    return list_datasets(args)


if __name__ == "__main__":
    sys.exit(main())
