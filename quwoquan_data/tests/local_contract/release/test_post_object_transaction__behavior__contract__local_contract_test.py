"""Approved posts and first-use creators enter canonical in one transaction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from content.release.canonical.application import apply_object_transaction
from content.release.canonical.object_transaction_audit import (
    audit_object_transaction,
    validate_canonical_publish,
)
from content.release.canonical.post_transaction import (
    build_post_object_transaction_package,
)
from core.tree_integrity import tree_integrity_stats


EXECUTION_ID = "20260718--travel-image-cold-start--cn-zhejiang--m3-901"
POST_REF = "image/西湖/光影"
CREATOR_REF = "qwq_creator_landscape_photographer_001"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    execution = tmp_path / "tasks" / EXECUTION_ID
    post = execution / "posts" / POST_REF
    source_asset = post / "assets/cover.jpg"
    source_asset.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 720), color=(30, 80, 140)).save(source_asset)
    digest = "sha256:" + hashlib.sha256(source_asset.read_bytes()).hexdigest()
    transaction_id = (
        f"{EXECUTION_ID}--post-"
        f"{hashlib.sha256(POST_REF.encode('utf-8')).hexdigest()[:12]}"
    )
    _write_json(
        execution / "execution_manifest.json",
        {"executionId": EXECUTION_ID, "createdAt": "2026-07-18T04:00:00Z"},
    )
    _write_json(
        execution / "sources/commons/assets/index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "west-lake-cover",
                    "url": "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
                    "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "platform": "Wikimedia Commons",
                    "fetchedAt": "2026-07-18T04:00:00Z",
                    "modelReleaseStatus": "not_required",
                }
            ]
        },
    )
    _write_json(
        post / "manifest.json",
        {
            "schema": "quwoquan_data.post_manifest",
            "topicId": "西湖__image_1",
            "contentType": "image",
            "carrier": "image",
            "title": "西湖光影",
            "caption": "湖岸与长桥的光影",
            "creatorProfileId": CREATOR_REF,
            "sourceUrls": ["https://commons.wikimedia.org/wiki/File:Example.jpg"],
            "entityRefs": ["/entity/地点/景区/西湖"],
            "tagRefs": ["Topic/旅行/玩法/摄影旅拍"],
            "assets": [
                {
                    "assetId": "west-lake-cover",
                    "fileName": "assets/cover.jpg",
                    "sourceAssetId": "west-lake-cover",
                    "caption": "西湖光影",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
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
    publish = tmp_path / "publish"
    for relative in ("creators", "entities", "posts", "tags", "media/objects"):
        (publish / relative).mkdir(parents=True, exist_ok=True)
    package = execution / "evidence/object-transactions" / transaction_id
    output = tmp_path / "output"
    return execution, package, publish, transaction_id


def test_post_transaction_atomically_projects_creator_and_post(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    output = tmp_path / "output"
    audit = audit_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package,
        transaction_id=transaction_id,
        expected_canonical_merkle=tree_integrity_stats(publish)["merkleRoot"],
    )
    apply_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package,
        transaction_id=transaction_id,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )

    assert (publish / "posts" / POST_REF / "manifest.json").is_file()
    assert (publish / "creators" / CREATOR_REF / "_creator.json").is_file()
    assert validate_canonical_publish(publish)["status"] == "passed"


def test_video_transaction_closes_poster_cas_and_path_bound_source_rights(
    tmp_path: Path,
) -> None:
    execution_id = "20260718--travel-video-cold-start--cn-zhejiang--m3-902"
    post_ref = "video/西湖/光影短片"
    execution = tmp_path / "tasks" / execution_id
    post = execution / "posts" / post_ref
    source_dir = execution / "sources/wiki/assets"
    source_dir.mkdir(parents=True)
    frame = source_dir / "frame-1.jpg"
    Image.new("RGB", (1280, 720), color=(35, 90, 150)).save(frame)
    _write_json(
        source_dir / "index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "001_001",
                    "fileName": frame.name,
                    "url": "https://upload.wikimedia.org/wikipedia/commons/frame-1.jpg",
                    "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Frame-1.jpg",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Frame-1.jpg",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "platform": "Wikimedia Commons",
                    "fetchedAt": "2026-07-18T04:00:00Z",
                    "modelReleaseStatus": "not_required",
                }
            ]
        },
    )
    assets = post / "assets"
    assets.mkdir(parents=True)
    video = assets / "video.mp4"
    video.write_bytes(b"fixture-video-payload")
    poster = assets / "poster.webp"
    Image.new("RGB", (1080, 1920), color=(25, 75, 125)).save(poster, format="WEBP")
    frame_ref = frame.relative_to(execution).as_posix()
    video_id = "west-lake-video"
    poster_id = "west-lake-video-cover"
    _write_json(
        execution / "execution_manifest.json",
        {"executionId": execution_id, "createdAt": "2026-07-18T04:00:00Z"},
    )
    _write_json(
        post / "manifest.json",
        {
            "schema": "quwoquan_data.post_manifest",
            "topicId": "西湖__video_1",
            "contentType": "video",
            "carrier": "video",
            "title": "西湖光影短片",
            "caption": "湖岸与长桥的光影",
            "creatorProfileId": CREATOR_REF,
            "sourceUrls": ["https://commons.wikimedia.org/wiki/File:Frame-1.jpg"],
            "entityRefs": ["/entity/地点/景区/西湖"],
            "tagRefs": ["Topic/旅行/玩法/摄影旅拍"],
            "generator": "agent",
            "createdAt": "2026-07-18T04:00:00Z",
            "updatedAt": "2026-07-18T04:00:00Z",
            "assets": [
                {
                    "assetId": video_id,
                    "fileName": "assets/video.mp4",
                    "kind": "video",
                    "posterAssetId": poster_id,
                    "sourceAssetRefs": [frame_ref],
                    "sha256": "sha256:" + hashlib.sha256(video.read_bytes()).hexdigest(),
                    "mimeType": "video/mp4",
                    "width": 1080,
                    "height": 1920,
                },
                {
                    "assetId": poster_id,
                    "fileName": "assets/poster.webp",
                    "kind": "image",
                    "role": "cover",
                    "sourceAssetRefs": [frame_ref],
                    "sha256": "sha256:" + hashlib.sha256(poster.read_bytes()).hexdigest(),
                    "mimeType": "image/webp",
                },
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
    transaction_id = (
        f"{execution_id}--post-"
        f"{hashlib.sha256(post_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    package_root = execution / "evidence/object-transactions" / transaction_id

    package = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=post_ref,
        transaction_id=transaction_id,
        package_root=package_root,
    )

    assert len(package["closure"]["casRefs"]) == 2
    rights = json.loads((package_root / "object/rights.json").read_text(encoding="utf-8"))
    assert {row["assetId"] for row in rights["assets"]} == {video_id, poster_id}
    assert all(row["source"] == "https://commons.wikimedia.org/wiki/File:Frame-1.jpg" for row in rights["assets"])
    manifest = json.loads((package_root / "object/manifest.json").read_text(encoding="utf-8"))
    canonical_assets = {row["assetId"]: row for row in manifest["assets"]}
    assert canonical_assets[video_id]["posterAssetId"] == poster_id
    assert canonical_assets[poster_id]["role"] == "cover"

    publish = tmp_path / "publish-video"
    for relative in ("creators", "entities", "posts", "tags", "media/objects"):
        (publish / relative).mkdir(parents=True, exist_ok=True)
    output = tmp_path / "output-video"
    audit = audit_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package_root,
        transaction_id=transaction_id,
        expected_canonical_merkle=tree_integrity_stats(publish)["merkleRoot"],
    )
    apply_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package_root,
        transaction_id=transaction_id,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )
    assert validate_canonical_publish(publish)["status"] == "passed"
