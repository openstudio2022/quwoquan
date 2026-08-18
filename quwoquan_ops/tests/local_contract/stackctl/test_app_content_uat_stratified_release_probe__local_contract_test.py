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
    cases = []
    for carrier, count in distribution.items():
        for ordinal in range(1, count + 1):
            cases.append(
                {
                    "sampleId": f"m100-{carrier}-{ordinal:03d}",
                    "carrier": carrier,
                    "sourceReadback": (
                        "entityRefs"
                        if carrier == "homepage"
                        else f"feedQueries.typed_{carrier}"
                    ),
                    "objectId": f"{carrier}-{ordinal:03d}",
                    "ordinal": ordinal,
                }
            )
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
                ("post", "content.post"),
                ("homepage", "entity.homepage"),
                ("persona", "user.profile"),
            )
        ],
        "videoPagination": {"pageSize": 20, "expectedWorkIds": ["video-001"]},
        "mediaChecks": {"automatic": True},
        "stratifiedSamples": {
            "milestone": "M100",
            "selection": "lexicographic_prefix_v1",
            "sampleCount": 100,
            "distribution": distribution,
            "cases": cases,
        },
    }
    homepage_ref = "env/alpha/runs/data-release/release-m100/verify/homepage.json"
    readiness_path = tmp_path / (
        "env/alpha/runs/data-release/release-m100/verify/release-readiness.json"
    )
    readiness_path.parent.mkdir(parents=True)
    readiness_path.write_text(
        json.dumps(
            {
                "releaseId": "release-m100",
                "homepageApiVerificationRef": homepage_ref,
            }
        ),
        encoding="utf-8",
    )
    homepage_path = tmp_path / homepage_ref
    homepage_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.homepage_api_verification",
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

    def fake_probe(*args, **kwargs):
        assert kwargs["only_checks"] == (
            "video_book_feed",
            "premium_feed",
            "feed_media_slices",
            "global_search",
            "media_sample",
            "release_sample",
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
    assert len(result["sampleExecution"]["samples"]) == 100
    assert result["sampleExecutionDigest"].startswith("sha256:")
