"""Exact release reads behind Alpha milestone App UAT evidence.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002.t2
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.app_content_uat_plan import build_app_content_uat_plan
from quwoquan_ops.cli.lib.app_content_uat_release_samples import (
    document_digest,
    resolve_release_sample_requests,
    validate_release_sample_probe,
)


def _readiness() -> dict[str, object]:
    article_ids = [f"article-{index:03d}" for index in range(1, 101)]
    image_ids = [f"image-{index:03d}" for index in range(1, 101)]
    video_ids = [f"video-{index:03d}" for index in range(1, 11)]
    entity_refs = [f"/entity/place-{index:03d}" for index in range(1, 101)]
    return {
        "releaseId": "release-m100-samples",
        "counts": {
            "entities": 100,
            "posts": 210,
            "premiumPlayableVideos": 10,
        },
        "entityRefs": entity_refs,
        "postIds": [*article_ids, *image_ids, *video_ids],
        "feedQueries": [
            {"name": "typed_article", "matchedPostIds": article_ids},
            {"name": "typed_image", "matchedPostIds": image_ids},
            {"name": "typed_video", "matchedPostIds": video_ids},
            {
                "name": "homepage_recommend",
                "matchedPostIds": [*article_ids, *image_ids, *video_ids],
            },
        ],
        "homepageApiVerificationRef": (
            "env/alpha/runs/data-release/release-m100-samples/verify/homepage.json"
        ),
        "appUatEnvelope": {
            "releaseId": "release-m100-samples",
            "homepageId": "homepage-001",
            "homepageTitle": "示例主页",
            "articleWorkId": article_ids[0],
            "articleTitle": "示例文章",
            "imageWorkId": image_ids[0],
            "imageTitle": "示例图片",
            "videoWorkId": video_ids[0],
            "creatorName": "示例作者",
            "creatorPersonaId": "persona-001",
            "creatorAvatarAssetId": "avatar-001",
        },
    }


def _write_receipts(root: Path) -> tuple[Path, dict[str, object]]:
    readiness = _readiness()
    homepage_ref = str(readiness["homepageApiVerificationRef"])
    homepage_report = {
        "schema": "quwoquan_data.homepage_api_verification",
        "releaseId": readiness["releaseId"],
        "passed": True,
        "issues": [],
        "entities": [
            {
                "entityRef": entity_ref,
                "homepageId": f"homepage-{index:03d}",
                "detailStatus": 200,
                "introductionStatus": 200,
            }
            for index, entity_ref in enumerate(readiness["entityRefs"], start=1)
        ],
    }
    homepage_path = root / homepage_ref
    homepage_path.parent.mkdir(parents=True)
    homepage_path.write_text(json.dumps(homepage_report), encoding="utf-8")
    readiness_path = root / (
        "env/alpha/runs/data-release/release-m100-samples/verify/"
        "release-readiness.json"
    )
    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
    return readiness_path, readiness


def _probe_report(resolved: dict[str, object]) -> dict[str, object]:
    checks = []
    for sample in resolved["samples"]:  # type: ignore[index]
        body = json.dumps(
            {
                (
                    "homepageId"
                    if sample["carrier"] == "homepage"
                    else "postId"
                ): sample["readObjectId"],
                "contentType": sample["expectedContentType"],
            },
            sort_keys=True,
        ).encode()
        checks.append(
            {
                "name": "release_sample",
                "method": "GET",
                "url": "https://alpha.example/" + str(sample["readObjectId"]),
                "statusCode": 200,
                "ok": True,
                **sample,
                "returnedObjectId": sample["readObjectId"],
                "returnedContentType": sample["expectedContentType"],
                "responseDigest": "sha256:" + hashlib.sha256(body).hexdigest(),
                "responseBytes": len(body),
            }
        )
    return {"status": "passed", "checks": checks}


def test_release_samples__resolve_and_validate_one_hundred_real_reads__local_contract(
    tmp_path: Path,
) -> None:
    readiness_path, readiness = _write_receipts(tmp_path)
    plan = build_app_content_uat_plan(readiness)
    resolved = resolve_release_sample_requests(
        readiness_path=readiness_path,
        app_uat_plan=plan,
        output_root=tmp_path,
    )

    assert resolved["milestone"] == "M100"
    assert len(resolved["samples"]) == 100
    assert resolved["samples"][0]["sourceObjectId"] == "/entity/place-001"
    assert resolved["samples"][0]["readObjectId"] == "homepage-001"

    evidence = validate_release_sample_probe(
        report=_probe_report(resolved),
        resolved=resolved,
        app_uat_plan_digest=document_digest(plan),
        readiness_receipt_digest="sha256:" + "1" * 64,
    )
    assert evidence["executedSampleCount"] == 100
    assert evidence["distribution"] == {
        "homepage": 25,
        "article": 25,
        "image": 40,
        "video": 10,
    }
    assert len(evidence["samples"]) == 100


def test_release_samples__plan_without_read_evidence_cannot_pass__local_contract(
    tmp_path: Path,
) -> None:
    readiness_path, readiness = _write_receipts(tmp_path)
    plan = build_app_content_uat_plan(readiness)
    resolved = resolve_release_sample_requests(
        readiness_path=readiness_path,
        app_uat_plan=plan,
        output_root=tmp_path,
    )

    with pytest.raises(ValueError, match="did not execute 100 reads"):
        validate_release_sample_probe(
            report={"status": "passed", "checks": []},
            resolved=resolved,
            app_uat_plan_digest=document_digest(plan),
            readiness_receipt_digest="sha256:" + "1" * 64,
        )
