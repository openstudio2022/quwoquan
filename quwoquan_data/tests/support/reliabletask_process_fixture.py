"""Build a real publish-ready object for Go→Python ReliableTask integration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from PIL import Image


EXECUTION_ID = (
    "20260720--travel-image-reliabletask-publish--"
    "cn-zhejiang--canary-902"
)
QUEUE_REF = "image-reliabletask-source-001"
POST_REL = "posts/image/风光画报/西湖光影/1"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def prepare(output_root: Path, publish_root: Path) -> dict[str, object]:
    os.environ["QWQ_OUTPUT_ROOT"] = str(output_root)
    os.environ["QWQ_PUBLISH_ROOT"] = str(publish_root)
    data_root = next(
        parent
        for parent in Path(__file__).resolve().parents
        if parent.name == "quwoquan_data"
    )
    scripts_root = data_root / "scripts"
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))

    from content.execution.queue.jobs import enqueue_ref_job
    from core.control_types import QueueBackend
    from core.paths import execution_root
    from core.tree_integrity import tree_integrity_stats

    execution = execution_root(EXECUTION_ID)
    post = execution / POST_REL
    source_asset = post / "assets/cover.jpg"
    source_asset.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 720), color=(30, 80, 140)).save(source_asset)
    digest = "sha256:" + hashlib.sha256(source_asset.read_bytes()).hexdigest()
    _write_json(
        execution / "execution_manifest.json",
        {
            "executionId": EXECUTION_ID,
            "createdAt": "2026-07-20T05:00:00Z",
        },
    )
    _write_json(
        execution / "sources/commons/assets/index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "west-lake-cover",
                    "url": (
                        "https://upload.wikimedia.org/wikipedia/"
                        "commons/example.jpg"
                    ),
                    "collectionPageUrl": (
                        "https://commons.wikimedia.org/wiki/File:Example.jpg"
                    ),
                    "authorizationProof": (
                        "https://commons.wikimedia.org/wiki/File:Example.jpg"
                    ),
                    "termsUrl": (
                        "https://creativecommons.org/licenses/by/4.0/"
                    ),
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "platform": "Wikimedia Commons",
                    "fetchedAt": "2026-07-20T05:00:00Z",
                    "modelReleaseStatus": "not_required",
                }
            ]
        },
    )
    _write_json(
        post / "manifest.json",
        {
            "schema": "quwoquan_data.post_manifest",
            "topicId": "西湖__image_reliabletask_1",
            "contentType": "image",
            "carrier": "image",
            "title": "西湖光影",
            "caption": "湖岸与长桥的光影",
            "creatorProfileId": "qwq_creator_landscape_photographer_001",
            "sourceUrls": [
                "https://commons.wikimedia.org/wiki/File:Example.jpg"
            ],
            "entityRefs": ["/entity/地点/景区/西湖"],
            "tagRefs": [],
            "createdAt": "2026-07-20T05:00:00Z",
            "assets": [
                {
                    "assetId": "west-lake-cover",
                    "fileName": "assets/cover.jpg",
                    "sourceAssetId": "west-lake-cover",
                    "caption": "西湖光影",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "termsUrl": (
                        "https://creativecommons.org/licenses/by/4.0/"
                    ),
                    "authorizationProof": (
                        "https://commons.wikimedia.org/wiki/File:Example.jpg"
                    ),
                    "sha256": digest,
                }
            ],
        },
    )
    _write_json(
        post / "5.review/attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    _write_json(post / "5.review/evidence_index.json", {"evidence": []})
    for relative in ("creators", "entities", "posts", "tags", "media/objects"):
        (publish_root / relative).mkdir(parents=True, exist_ok=True)

    job = enqueue_ref_job(
        EXECUTION_ID,
        QUEUE_REF,
        "publish",
        mutex_key="canonical-publish",
        meta={
            "contentType": "image",
            "carrier": "image",
            "entityRef": "/entity/地点/景区/西湖",
            "sourceRevision": str(
                tree_integrity_stats(post)["merkleRoot"]
            ),
            "contentObjectDir": POST_REL,
        },
        queue_backend=QueueBackend.RELIABLE_TASK,
    )
    reliable_ref = job.reliable_task_ref_document()
    if reliable_ref is None or not isinstance(reliable_ref.get("payload"), dict):
        raise RuntimeError("fixture ReliableTask payload missing")
    payload = dict(reliable_ref["payload"])
    return {
        "schema": "quwoquan.reliabletask_process_fixture",
        "job": {
            "entityRef": payload["entityRef"],
            "carrier": payload["carrier"],
            "sourceRevision": payload["sourceRevision"],
            "jobId": payload["jobId"],
            "executionId": payload["executionId"],
            "ref": payload["ref"],
            "stage": payload["stage"],
            "partitionKey": payload["partitionKey"],
        },
        "idempotencyKey": payload["idempotencyKey"],
        "expectedCanonicalRef": POST_REL,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--publish-root", required=True)
    args = parser.parse_args()
    result = prepare(Path(args.output_root), Path(args.publish_root))
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
