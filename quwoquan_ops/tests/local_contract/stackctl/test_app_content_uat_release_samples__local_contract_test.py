"""Exact release reads consume the projected Data-owned sample rows.

spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-004.t1
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

CARRIERS = ("homepage", "article", "image", "video")
ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
DIGESTS = {
    "manifest": "sha256:" + "1" * 64,
    "pool": "sha256:" + "2" * 64,
    "source": "sha256:" + "3" * 64,
    "merkle": "sha256:" + "4" * 64,
    "contents": "sha256:" + "5" * 64,
    "entities": "sha256:" + "6" * 64,
}


def _digest(document: object) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _contents() -> list[dict[str, object]]:
    return [
        {
            "contentId": f"{carrier}-{index:03d}",
            "version": 1,
            "postRef": f"{carrier}/work-{index:03d}/1",
            "executionId": f"{carrier}-execution",
            "sourceIdentityDigest": DIGESTS["source"],
        }
        for carrier, count in (("article", 100), ("image", 100), ("video", 10))
        for index in range(1, count + 1)
    ]


def _readiness() -> dict[str, object]:
    article_ids = [f"article-{index:03d}" for index in range(1, 101)]
    image_ids = [f"image-{index:03d}" for index in range(1, 101)]
    video_ids = [f"video-{index:03d}" for index in range(1, 11)]
    entity_refs = [f"/entity/place-{index:03d}" for index in range(1, 101)]
    return {
        "releaseId": "release-m100-samples",
        "releaseClass": "research",
        "productLifecycleState": "research",
        "manifestDigest": DIGESTS["manifest"],
        "sourceIdentities": [{"executionId": "execution-a"}],
        "sourceIdentitySetDigest": DIGESTS["source"],
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
        "contentImportReportRef": (
            "env/alpha/runs/data-release/release-m100-samples/import/import.json"
        ),
    }


def _samples() -> list[dict[str, str]]:
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    rows: list[dict[str, str]] = []
    for carrier, count in distribution.items():
        for ordinal in range(1, count + 1):
            rows.append(
                {
                    "sampleId": f"m100-{carrier}-{ordinal:03d}",
                    "carrier": carrier,
                    "objectId": (
                        f"/entity/place-{ordinal:03d}"
                        if carrier == "homepage"
                        else f"{carrier}-{ordinal:03d}"
                    ),
                    "objectRef": (
                        f"objects/entities/place-{ordinal:03d}"
                        if carrier == "homepage"
                        else f"objects/posts/{carrier}/work-{ordinal:03d}/1"
                    ),
                    "objectDigest": _digest(
                        {"carrier": carrier, "ordinal": ordinal}
                    ),
                }
            )
    return rows


def _sample_plan() -> dict[str, object]:
    evidence = {
        "poolDigest": DIGESTS["pool"],
        "sourceIdentitySetDigest": DIGESTS["source"],
        "canonicalMerkle": DIGESTS["merkle"],
        "releaseContentsDigest": DIGESTS["contents"],
        "releaseEntityCohortDigest": DIGESTS["entities"],
    }
    release_digest = _digest(
        {
            "schema": "quwoquan_data.release_uat_sample_plan_identity",
            "releaseId": "release-m100-samples",
            "canonicalMerkle": DIGESTS["merkle"],
            "selectionEvidence": evidence,
        }
    )
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    return {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-m100-samples",
        "releaseDigest": release_digest,
        "milestone": "M100",
        "selectionEvidence": evidence,
        "eligiblePopulationCounts": {
            "homepage": 120,
            "article": 120,
            "image": 140,
            "video": 12,
        },
        "exactCohortCounts": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
        "entryCarrierCells": [
            {
                "entry": entry,
                "carrier": carrier,
                "applicability": "required",
                "specRef": "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-006",
                "runnerClass": f"qwq_app.content_uat.{entry}.{carrier}.v1",
            }
            for entry in ENTRIES
            for carrier in CARRIERS
        ],
        "sampleStrategy": {
            "name": "stratified_exact",
            "version": 1,
            "seedDigest": _digest(
                {
                    "releaseDigest": release_digest,
                    "sampleDistribution": distribution,
                }
            ),
            "carrierOrder": list(CARRIERS),
            "sortKey": "identity",
            "direction": "ascending",
            "objectDigestAlgorithm": "sha256-path-blob-merkle",
            "sampleDistribution": distribution,
        },
        "sampleCount": 100,
        "samples": _samples(),
    }


def _release_header(sample_plan_digest: str) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.release",
        "releaseId": "release-m100-samples",
        "sourceOwner": "qwq_data",
        "releaseKind": "content",
        "releaseClass": "research",
        "productLifecycleState": "research",
        "selectionScope": "milestone",
        "milestone": "M100",
        "milestoneTargets": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
        "poolDigest": DIGESTS["pool"],
        "canonicalMerkle": DIGESTS["merkle"],
        "sourceIdentities": [{"executionId": "execution-a"}],
        "sourceIdentitySetDigest": DIGESTS["source"],
        "contents": _contents(),
        "samplePlanRef": "uat/sample_plan.json",
        "samplePlanDigest": sample_plan_digest,
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
    import_ref = str(readiness["contentImportReportRef"])
    import_report = {
        "schema": "quwoquan.content_import_report",
        "status": "imported",
        "releaseId": readiness["releaseId"],
        "manifestDigest": readiness["manifestDigest"],
        "postBindings": [
            {
                "contentId": row["contentId"],
                "postRef": row["postRef"],
                "postId": f"runtime-{row['contentId']}",
                "contentType": str(row["postRef"]).partition("/")[0],
            }
            for row in _contents()
        ],
    }
    readiness["postIds"] = sorted(
        str(row["postId"]) for row in import_report["postBindings"]
    )
    import_path = root / import_ref
    import_path.parent.mkdir(parents=True)
    import_path.write_text(json.dumps(import_report), encoding="utf-8")
    readiness_path = root / (
        "env/alpha/runs/data-release/release-m100-samples/verify/release-readiness.json"
    )
    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
    return readiness_path, readiness


def _app_plan(readiness: dict[str, object]) -> dict[str, object]:
    sample_plan = _sample_plan()
    digest = _digest(sample_plan)
    return build_app_content_uat_plan(
        readiness,
        release_header=_release_header(digest),
        release_uat_sample_plan=sample_plan,
        release_uat_sample_plan_digest=digest,
        release_payload_sha256=DIGESTS["manifest"],
    )


def _probe_report(resolved: dict[str, object]) -> dict[str, object]:
    checks = []
    for sample in resolved["samples"]:  # type: ignore[index]
        body = json.dumps(
            {
                ("homepageId" if sample["carrier"] == "homepage" else "postId"): sample[
                    "readObjectId"
                ],
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


def test_release_samples__resolve_and_validate_one_hundred_plan_owned_reads__local_contract(
    tmp_path: Path,
) -> None:
    readiness_path, readiness = _write_receipts(tmp_path)
    plan = _app_plan(readiness)
    resolved = resolve_release_sample_requests(
        readiness_path=readiness_path,
        app_uat_plan=plan,
        output_root=tmp_path,
    )

    assert resolved["milestone"] == "M100"
    assert resolved["releaseUatSamplePlanRef"] == "uat/sample_plan.json"
    assert resolved["releaseUatSamplePlanDigest"] == plan["releaseUatSamplePlanDigest"]
    assert len(resolved["samples"]) == 100
    assert resolved["samples"][0]["sourceObjectId"] == "/entity/place-001"
    assert resolved["samples"][0]["readObjectId"] == "homepage-001"
    article = next(row for row in resolved["samples"] if row["carrier"] == "article")
    assert article["sourceObjectId"] == "article-001"
    assert article["readObjectId"] == "runtime-article-001"
    assert "target" not in str(plan["orderedSamples"])
    assert "device" not in str(plan["orderedSamples"])

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
    assert evidence["releaseUatSamplePlanDigest"] == plan["releaseUatSamplePlanDigest"]
    assert len(evidence["samples"]) == 100


def test_release_samples__plan_without_read_evidence_cannot_pass__local_contract(
    tmp_path: Path,
) -> None:
    readiness_path, readiness = _write_receipts(tmp_path)
    plan = _app_plan(readiness)
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
