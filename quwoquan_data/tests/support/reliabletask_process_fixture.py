"""Build a real publish-ready object for Go→Python ReliableTask integration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import yaml
from PIL import Image


EXECUTION_ID = (
    "20260720--travel-image-reliabletask-publish--"
    "test-region-a--pilot-902"
)
QUEUE_REF = "image-reliabletask-source-001"
POST_REL = "posts/image/风光画报/西湖光影/1"
_SOURCE_CAPSULE_REL = Path(
    "data/local/workspace/reliabletask-process-fixture/source-capsule"
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _repo_root() -> Path:
    data_root = next(
        parent
        for parent in Path(__file__).resolve().parents
        if parent.name == "quwoquan_data"
    )
    return data_root.parent


def _materialize_source_capsule(output_root: Path) -> tuple[Path, str]:
    """Freeze the governed source closure before building runtime evidence."""
    repo_root = _repo_root()
    scripts_root = repo_root / "quwoquan_data/scripts"
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))

    from content.execution.campaign.source_snapshot import (
        materialize_source_snapshot,
        source_snapshot_roots,
    )
    from content.execution.runtime_evidence.reliabletask_binary_digest import (
        observer_source_digest,
    )
    from core.source_digest import current_source_digest

    source_digest = current_source_digest(repo_root=repo_root).digest
    roots = source_snapshot_roots(repo_root, expected_digest=source_digest)
    capsule_root = output_root / _SOURCE_CAPSULE_REL
    materialize_source_snapshot(
        repo_root,
        capsule_root,
        roots=roots,
        expected_digest=source_digest,
    )

    # Creator avatar bytes are canonical fixture input but intentionally not a
    # sourceDigest root.  Copy only the referenced object into the isolated
    # capsule so the worker never falls back to the shared repository tree.
    creator_profile = yaml.safe_load(
        (
            capsule_root
            / "quwoquan_data/control_plane/governance/creator_pool/profiles"
            / "system_builtin/landscape_photographer.creator.yaml"
        ).read_text(encoding="utf-8")
    )
    avatar_asset = (
        creator_profile.get("avatarAsset")
        if isinstance(creator_profile, dict)
        else None
    )
    avatar_object_key = (
        str(avatar_asset.get("objectKey") or "")
        if isinstance(avatar_asset, dict)
        else ""
    )
    if not avatar_object_key:
        raise RuntimeError("fixture creator avatar CAS object key is missing")
    avatar_source = repo_root / "quwoquan_data/publish" / avatar_object_key
    if not avatar_source.is_file():
        raise RuntimeError("fixture creator avatar CAS bytes are missing")
    avatar_target = capsule_root / "quwoquan_data/publish" / avatar_object_key
    avatar_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(avatar_source, avatar_target)

    # The target-set builder names this test-owned entity catalog explicitly.
    # It is not a production sourceDigest input, but its bytes must still exist
    # inside the isolated repo so entityCatalogDigest can be recomputed rather
    # than inferred from the live checkout.
    fixture_catalog_ref = Path(
        "quwoquan_data/tests/support/execution_manifest_fixture.py"
    )
    fixture_catalog_source = repo_root / fixture_catalog_ref
    fixture_catalog_target = capsule_root / fixture_catalog_ref
    fixture_catalog_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture_catalog_source, fixture_catalog_target)

    # Queue-backend freeze binds a real Service observer binary separately from
    # Data sourceDigest.  Reproduce that exact build closure in the capsule and
    # double-sample its independent digest so no live Service source can leak
    # into the later worker invocation.
    observer_digest = observer_source_digest()
    service_root = repo_root / "quwoquan_service"
    observer_inputs = [service_root / "go.mod", service_root / "go.sum"]
    observer_inputs.extend(
        path
        for path in sorted(service_root.rglob("*.go"))
        if not path.name.endswith("_test.go")
    )
    for source in observer_inputs:
        if not source.is_file() or source.is_symlink():
            raise RuntimeError("fixture observer build input is missing or symbolic")
        target = capsule_root / source.relative_to(repo_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if observer_source_digest() != observer_digest:
        raise RuntimeError("fixture observer build source changed during snapshot")
    return capsule_root, observer_digest


def _exec_in_source_capsule(
    *,
    output_root: Path,
    publish_root: Path,
    capsule_root: Path,
    observer_source_digest: str,
) -> None:
    """Restart once so every production import resolves from the capsule."""
    repo_root = _repo_root()
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(
                (
                    str(capsule_root / "quwoquan_data/scripts"),
                    str(repo_root),
                )
            ),
            "QWQ_OUTPUT_ROOT": str(output_root),
            "QWQ_PUBLISH_ROOT": str(publish_root),
        }
    )
    for name in ("QWQ_DATA_ROOT", "QWQ_FAMILIES_ROOT", "QWQ_SCHEMA_ROOT"):
        environment.pop(name, None)
    os.execve(
        sys.executable,
        [
            sys.executable,
            "-B",
            str(Path(__file__).resolve()),
            "--output-root",
            str(output_root),
            "--publish-root",
            str(publish_root),
            "--source-capsule-root",
            str(capsule_root),
            "--observer-source-digest",
            observer_source_digest,
        ],
        environment,
    )


def prepare(
    output_root: Path,
    publish_root: Path,
    *,
    source_capsule_root: Path,
) -> dict[str, object]:
    os.environ["QWQ_OUTPUT_ROOT"] = str(output_root)
    os.environ["QWQ_PUBLISH_ROOT"] = str(publish_root)
    data_root = source_capsule_root / "quwoquan_data"
    scripts_root = data_root / "scripts"
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))

    creator_profile = yaml.safe_load(
        (
            data_root
            / "control_plane/governance/creator_pool/profiles/system_builtin"
            / "landscape_photographer.creator.yaml"
        ).read_text(encoding="utf-8")
    )
    avatar_asset = (
        creator_profile.get("avatarAsset")
        if isinstance(creator_profile, dict)
        else None
    )
    avatar_object_key = (
        str(avatar_asset.get("objectKey") or "")
        if isinstance(avatar_asset, dict)
        else ""
    )
    if not avatar_object_key:
        raise RuntimeError("fixture creator avatar CAS object key is missing")
    avatar_source = data_root / "publish" / avatar_object_key
    if not avatar_source.is_file():
        raise RuntimeError("fixture creator avatar CAS bytes are missing")
    avatar_target = publish_root / avatar_object_key
    avatar_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(avatar_source, avatar_target)

    from content.execution.queue.jobs import enqueue_ref_job
    from content.execution.queue.partition import partition_count, partition_key
    from content.execution.queue.reliabletask.fleet import build_fleet_request
    from content.execution.closure.post_review import (
        resolve_post_review_closure,
        write_post_review_closure,
    )
    from content.post.object_index import register_content_object
    from core.control_types import QueueBackend, QueueJobStage
    from core.paths import execution_root
    from core.tree_integrity import tree_integrity_stats
    from quwoquan_data.tests.support.execution_manifest_fixture import (
        ExecutionFixtureBuilder,
    )

    ExecutionFixtureBuilder(
        execution_id=EXECUTION_ID,
        targets=({"name": "西湖", "entityType": "地点/景区"},),
    ).build()
    execution = execution_root(EXECUTION_ID)
    post = execution / POST_REL
    source_asset = post / "assets/cover.jpg"
    source_asset.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 720), color=(30, 80, 140)).save(source_asset)
    digest = "sha256:" + hashlib.sha256(source_asset.read_bytes()).hexdigest()
    source_asset_ref = "sources/commons/assets/cover.jpg"
    source_asset_path = execution / source_asset_ref
    source_asset_path.parent.mkdir(parents=True, exist_ok=True)
    source_asset_path.write_bytes(source_asset.read_bytes())
    _write_json(
        execution / "sources/commons/assets/index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "west-lake-cover",
                    "fileName": "cover.jpg",
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
                    "rightsAuditStatus": "verified",
                    "rightsAuditIssues": [],
                    "usageScope": "app_publish",
                    "modelReleaseStatus": "not_required",
                }
            ]
        },
    )
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "licensed_adaptation",
            "researchLane": "image",
        },
    )
    _write_json(
        post / "manifest.json",
        {
            "schema": "quwoquan_data.post_manifest",
            "vertical": "travel",
            "topicId": "西湖__image_reliabletask_1",
            "contentIdentity": "work",
            "contentType": "image",
            "carrier": "image",
            "title": "西湖光影",
            "caption": "湖岸与长桥的光影",
            "creatorProfileId": "qwq_creator_landscape_photographer_001",
            "sourceUrls": [
                "https://commons.wikimedia.org/wiki/File:Example.jpg"
            ],
            "entityRefs": ["/entity/地点/景区/西湖"],
            "tagRefs": ["Topic/旅行/玩法/摄影旅拍"],
            "createdAt": "2026-07-20T05:00:00Z",
            "assets": [
                {
                    "assetId": "west-lake-cover",
                    "fileName": "assets/cover.jpg",
                    "sourceAssetId": "west-lake-cover",
                    "sourceAssetRef": source_asset_ref,
                    "caption": "西湖光影",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "termsUrl": (
                        "https://creativecommons.org/licenses/by/4.0/"
                    ),
                    "authorizationProof": (
                        "https://commons.wikimedia.org/wiki/File:Example.jpg"
                    ),
                    "rightsAuditStatus": "verified",
                    "rightsAuditIssues": [],
                    "usageScope": "app_publish",
                    "modelReleaseStatus": "not_required",
                    "sha256": digest,
                }
            ],
        },
    )
    _write_json(
        post / "1.download/source_refs.json",
        {
            "sources": [
                {
                    "sourceUrl": (
                        "https://commons.wikimedia.org/wiki/File:Example.jpg"
                    ),
                    "sourceAssetRef": source_asset_ref,
                }
            ]
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
    register_content_object(
        EXECUTION_ID,
        QUEUE_REF,
        content_type="image",
        angle="风光画报",
        title="西湖光影",
        seq=1,
    )
    write_post_review_closure(
        resolve_post_review_closure(
            EXECUTION_ID,
            carrier="image",
            object_targets={QUEUE_REF: POST_REL},
            object_issues={},
        )
    )
    for relative in ("creators", "entities", "posts", "tags"):
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
            "partitionKey": partition_key(
                "image",
                QUEUE_REF,
                partition_count(2),
            ),
            "contentObjectDir": POST_REL,
        },
        queue_backend=QueueBackend.RELIABLE_TASK,
    )
    reliable_ref = job.reliable_task_ref_document()
    if reliable_ref is None or not isinstance(reliable_ref.get("payload"), dict):
        raise RuntimeError("fixture ReliableTask payload missing")
    fleet_request = build_fleet_request(
        EXECUTION_ID,
        QueueJobStage.PUBLISH,
    )
    request_jobs = fleet_request.get("jobs")
    if not isinstance(request_jobs, list) or len(request_jobs) != 1:
        raise RuntimeError("fixture frozen ReliableTask job-set is incomplete")
    request_job = request_jobs[0]
    if not isinstance(request_job, dict):
        raise RuntimeError("fixture frozen ReliableTask job is invalid")
    payload = {
        **request_job,
        "executionEnvelopeDigest": fleet_request["executionEnvelopeDigest"],
        "jobSetEnvelopeDigest": fleet_request["jobSetEnvelopeDigest"],
        "jobSetDigest": fleet_request["jobSetDigest"],
        "actualTaskDigest": fleet_request["actualTaskDigest"],
    }
    return {
        "schema": "quwoquan.reliabletask_process_fixture",
        "sourceCapsuleRoot": str(source_capsule_root),
        "job": payload,
        "idempotencyKey": payload["idempotencyKey"],
        "expectedCanonicalRef": POST_REL,
        "fleetRequest": fleet_request,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--publish-root", required=True)
    parser.add_argument("--source-capsule-root")
    parser.add_argument("--observer-source-digest")
    args = parser.parse_args()
    output_root = Path(args.output_root).resolve()
    publish_root = Path(args.publish_root).resolve()
    if args.source_capsule_root is None:
        if args.observer_source_digest is not None:
            raise ValueError("observer source digest requires a source capsule")
        capsule_root, observer_source_digest = _materialize_source_capsule(
            output_root
        )
        _exec_in_source_capsule(
            output_root=output_root,
            publish_root=publish_root,
            capsule_root=capsule_root,
            observer_source_digest=observer_source_digest,
        )
        raise AssertionError("source capsule exec unexpectedly returned")
    capsule_root = Path(args.source_capsule_root).resolve(strict=True)
    expected_capsule_root = (output_root / _SOURCE_CAPSULE_REL).resolve(strict=True)
    if capsule_root != expected_capsule_root:
        raise ValueError("fixture source capsule escapes the test output root")
    from content.execution.runtime_evidence.reliabletask_binary_digest import (
        observer_source_digest,
    )

    if observer_source_digest() != args.observer_source_digest:
        raise ValueError("fixture observer source capsule digest drift")
    result = prepare(
        output_root,
        publish_root,
        source_capsule_root=capsule_root,
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
