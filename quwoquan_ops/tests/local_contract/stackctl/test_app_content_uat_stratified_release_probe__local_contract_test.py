"""stackctl turns the milestone plan into exact HTTP-read evidence.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002.t2
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quwoquan_ops.cli import stackctl


def test_release_probe__receipt_contains_one_hundred_verified_sample_reads(
    monkeypatch,
    tmp_path: Path,
) -> None:
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    samples = []
    for carrier, count in distribution.items():
        for ordinal in range(1, count + 1):
            samples.append(
                {
                    "sampleId": f"m100-{carrier}-{ordinal:03d}",
                    "carrier": carrier,
                    "objectId": f"{carrier}-{ordinal:03d}",
                    "objectRef": (
                        f"objects/entities/{carrier}-ref-{ordinal:03d}"
                        if carrier == "homepage"
                        else f"objects/posts/{carrier}/{carrier}-ref-{ordinal:03d}"
                    ),
                    "objectDigest": "sha256:" + "8" * 64,
                }
            )
    sample_plan_digest = "sha256:" + "1" * 64
    plan = {
        "releaseId": "release-m100",
        "searchCanaries": [
            {
                "kind": kind,
                "query": f"query-{kind}",
                "expectedObjectType": object_type,
                "expectedObjectId": f"id-{kind}",
            }
            for kind, object_type in (
                ("homepage", "entity.homepage"),
                ("article", "content.post"),
                ("image", "content.post"),
                ("video", "content.post"),
            )
        ],
        "videoPagination": {"pageSize": 20, "expectedWorkIds": ["video-001"]},
        "mediaChecks": {
            "automatic": True,
            "homepageRecommendation": {"expectedPostIds": ["runtime-video-001"]},
            "typedVideo": {"expectedPostIds": [f"runtime-video-{i:03d}" for i in range(1, 11)]},
            "premiumVideo": {"expectedPostIds": ["runtime-video-001"]},
        },
        "releasePayloadSha256": "sha256:" + "9" * 64,
        "releaseUatSamplePlanRef": "uat/sample_plan.json",
        "releaseUatSamplePlanDigest": sample_plan_digest,
        "releaseIdentity": {
            "releaseId": "release-m100",
            "milestone": "M100",
        },
        "orderedSamples": samples,
    }
    from quwoquan_ops.tests.support.app_content_preflight_test_support import write_release_readiness
    from quwoquan_ops.tests.support.test_data_verification_test_support import _with_checksum
    readiness_path, _ = write_release_readiness(
        tmp_path, environment="alpha", release_id="release-m100",
        verify_run_id="verify", manifest_digest="sha256:" + "9" * 64,
    )
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    homepage_ref = readiness["homepageApiVerificationRef"]
    import_ref = readiness["contentImportReportRef"]
    readiness["postIds"] = [
        f"runtime-{carrier}-{ordinal:03d}"
        for carrier, count in (("article", 25), ("image", 40), ("video", 10))
        for ordinal in range(1, count + 1)
    ]
    readiness["entityRefs"] = [f"homepage-{ordinal:03d}" for ordinal in range(1, 26)]
    readiness["counts"].update(entities=25, posts=75, discoveryPosts=75, premiumPlayableVideos=10)
    for query in readiness["feedQueries"]:
        query["matchedPostIds"] = (
            ["runtime-video-001"] if query["name"] in {"typed_video", "premium_stream", "homepage_recommend"}
            else readiness["postIds"]
        )
    homepage_path = tmp_path / homepage_ref
    homepage_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.homepage_api_verification",
                "environment": "alpha", "runId": "verify",
                "releaseId": "release-m100",
                "passed": True,
                "issues": [],
                "entities": [
                    {
                        "entityRef": f"homepage-{ordinal:03d}",
                        "homepageId": f"read-homepage-{ordinal:03d}",
                        "detailStatus": 200,
                        "introductionStatus": 200,
                    }
                    for ordinal in range(1, 26)
                ],
            }
        ),
        encoding="utf-8",
    )

    import_path = tmp_path / import_ref
    import_path.parent.mkdir(parents=True, exist_ok=True)
    import_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan.content_import_report",
                "environment": "alpha",
                "releaseId": "release-m100",
                "manifestDigest": "sha256:" + "9" * 64,
                "status": "imported",
                "postBindings": [
                    {
                        "contentId": f"{carrier}-{ordinal:03d}",
                        "postRef": f"{carrier}/{carrier}-ref-{ordinal:03d}",
                        "postId": f"runtime-{carrier}-{ordinal:03d}",
                        "contentType": carrier,
                    }
                    for carrier, count in (("article", 25), ("image", 40), ("video", 10))
                    for ordinal in range(1, count + 1)
                ],
            }
        ),
        encoding="utf-8",
    )

    readiness["activationEnvelope"]["importReportDigest"] = (
        "sha256:" + hashlib.sha256(import_path.read_bytes()).hexdigest()
    )
    readiness["activationEnvelopeDigest"] = stackctl._canonical_document_checksum(readiness["activationEnvelope"])
    readiness_path.write_text(json.dumps(_with_checksum(readiness)), encoding="utf-8")

    def fake_probe(*args, **kwargs):
        assert kwargs["only_checks"] == (
            "content_feed",
            "homepage_recommend",
            "video_book_feed",
            "premium_feed",
            "feed_media_slices",
            "global_search",
            "media_sample",
            "release_sample",
            "author_posts_contract",
        )
        samples = kwargs["release_samples"]
        assert len(samples) == 100
        checks = []
        for sample in samples:
            body = json.dumps(sample, sort_keys=True).encode()
            checks.append(
                {
                    "name": "release_sample",
                    "method": "GET",
                    "url": "https://alpha.example/" + sample["readObjectId"],
                    "statusCode": 200,
                    "ok": True,
                    **sample,
                    "returnedObjectId": sample["readObjectId"],
                    "returnedContentType": sample["expectedContentType"],
                    "responseDigest": "sha256:" + hashlib.sha256(body).hexdigest(),
                    "responseBytes": len(body),
                }
            )
        report_path = args[2] / "integration-probe.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"status": "passed", "checks": checks}), encoding="utf-8"
        )
        return {"ok": True, "reportPath": str(report_path)}, "", []

    monkeypatch.setattr(stackctl, "output_root", lambda: tmp_path)
    monkeypatch.setattr(stackctl, "_run_environment_integration_probe", fake_probe)
    result = stackctl._run_app_content_release_probe(
        target="alpha-local",
        readiness_path=readiness_path,
        app_uat_plan=plan,
        report_dir=tmp_path / "probe",
    )

    assert result["executedSampleCount"] == 100
    assert result["sampleExecution"]["distribution"] == distribution
    assert result["sampleExecution"]["releaseUatSamplePlanDigest"] == sample_plan_digest
    assert len(result["sampleExecution"]["samples"]) == 100
    assert result["sampleExecutionDigest"].startswith("sha256:")
