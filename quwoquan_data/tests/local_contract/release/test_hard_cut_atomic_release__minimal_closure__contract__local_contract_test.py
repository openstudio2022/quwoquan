# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t7
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t9
from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.source import independent_asset_review
from content.release.canonical.publish_object import _review_approved, _target_object
from core.schema import assert_valid
from core.stage_artifact_contract import required_stage_artifacts
from verify import stage_artifacts

EXECUTION_ID = "20260903--travel-video-hard-cut--test-region-a--pilot-001"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _target_set(refs: list[str]) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.target_set",
        "executionId": EXECUTION_ID,
        "carrier": "video",
        "selectionPolicy": "frozen",
        "entityCatalogDigest": "sha256:" + "a" * 64,
        "candidateBinding": {
            "scope": "output", "ref": "data/local/candidates.json",
            "digest": "sha256:" + "b" * 64, "candidateCount": len(refs),
        },
        "targetCount": len(refs),
        "targetRefs": refs,
        "targets": [{"name": f"target-{index}", "entityType": "地点/景区"} for index, _ in enumerate(refs)],
    }


def test_stage_contract_uses_ai_written_target_artifacts() -> None:
    assert required_stage_artifacts("video")["4.draft"] == (
        "draft_meta.json", "author_self_check.json", "agent_result_envelope.json", "video_script.json"
    )
    assert required_stage_artifacts("image")["4.draft"][-1] == "image_work.json"
    assert required_stage_artifacts("article")["5.review"] == (
        "rubric_review.json", "reviewer_result.json", "media_ref_review.json", "attestation.json"
    )


def test_stage_verifier_schema_map_matches_minimal_stage_contract() -> None:
    retired = {
        "4.draft/author_job_packet.json",
        "4.draft/prompt_snapshot.json",
        "5.review/deterministic_gate.json",
        "5.review/finalization_report.json",
        "5.review/evidence_index.json",
    }
    assert retired.isdisjoint(stage_artifacts._SCHEMA_FILES)


def test_review_attestation_schema_accepts_minimal_four_file_closure() -> None:
    document = {
        "schema": "quwoquan_data.review_attestation",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "executionBinding": "frozen",
        "objectRef": "posts/video/angle/title/1",
        "decision": "approved",
        "deterministicGate": {"status": "passed", "issues": []},
        "independentReviewer": {
            "status": "passed",
            "actor": {
                "host": "cursor",
                "sessionId": "review-session-1",
                "modelFamily": "composer",
                "invocation": {
                    "provider": "cursor-host",
                    "model": "composer-2.5",
                    "runId": "review-run-1",
                },
            },
        },
        "mediaRefReview": {"status": "passed", "issues": []},
        "repair": {"status": "not_required"},
    }
    assert_valid(document, "content", "review_attestation")
    same_family = json.loads(json.dumps(document))
    same_family["independentReviewer"]["actor"]["modelFamily"] = "gpt"
    assert_valid(same_family, "content", "review_attestation")
    for missing in ("sessionId", "invocation"):
        invalid_actor = json.loads(json.dumps(document))
        invalid_actor["independentReviewer"]["actor"].pop(missing)
        with pytest.raises(ValueError, match=missing):
            assert_valid(invalid_actor, "content", "review_attestation")
    for field in ("modelFamily", "provider", "model"):
        invalid_actor = json.loads(json.dumps(document))
        target = invalid_actor["independentReviewer"]["actor"]
        if field in ("provider", "model"):
            target = target["invocation"]
        target[field] = "auto"
        with pytest.raises(ValueError, match="not"):
            assert_valid(invalid_actor, "content", "review_attestation")
    for field in ("deterministicGate", "independentReviewer", "mediaRefReview"):
        invalid = dict(document)
        invalid.pop(field)
        with pytest.raises(ValueError, match=field):
            assert_valid(invalid, "content", "review_attestation")


def test_writing_pack_schema_declares_host_ai_producer() -> None:
    from core.schema import load_schema

    description = load_schema("content", "writing_pack")["description"]
    assert "宿主 AI" in description
    assert "CLI prepare" not in description


def test_publish_review_accepts_only_minimal_four_file_closure(tmp_path: Path) -> None:
    review = tmp_path / "object/5.review"
    object_ref = "posts/video/angle/title/1"
    _write(
        review / "rubric_review.json",
        {
            "schema": "quwoquan_data.rubric_review",
            "ref": object_ref,
            "dimensions": [{"name": "readability", "scores": [9], "verdict": "pass", "rationale": "clear"}],
            "decision": "approved",
        },
    )
    reviewer = {
        "schema": "quwoquan_data.reviewer_result",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": object_ref,
        "actor": {
            "host": "cursor",
            "sessionId": "review-session-1",
            "modelFamily": "composer",
            "invocation": {
                "provider": "cursor-host",
                "model": "composer-2.5",
                "runId": "review-run-1",
            },
        },
        "verdict": "passed",
        "issues": [],
        "resultHash": "sha256:" + "c" * 64,
    }
    _write(review / "reviewer_result.json", reviewer)
    _write(
        review / "media_ref_review.json",
        {
            "schema": "quwoquan_data.media_ref_review",
            "stage": "5.review",
            "executionId": EXECUTION_ID,
            "objectRef": object_ref,
            "passed": True,
            "mediaIssues": [],
            "referenceIssues": [],
            "rightsReviews": [],
        },
    )
    attestation = {
        "schema": "quwoquan_data.review_attestation",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "executionBinding": "frozen",
        "objectRef": object_ref,
        "decision": "approved",
        "deterministicGate": {"status": "passed", "issues": []},
        "independentReviewer": {
            "status": "passed",
            "actor": {
                "host": "cursor",
                "sessionId": "review-session-1",
                "modelFamily": "composer",
                "invocation": {
                    "provider": "cursor-host",
                    "model": "composer-2.5",
                    "runId": "review-run-1",
                },
            },
        },
        "mediaRefReview": {"status": "passed", "issues": []},
        "repair": {"status": "not_required"},
    }
    _write(review / "attestation.json", attestation)

    _review_approved(review.parent)
    reviewer["verdict"] = "failed"
    _write(review / "reviewer_result.json", reviewer)
    with pytest.raises(ObjectTransactionError, match="independent reviewer"):
        _review_approved(review.parent)


def test_independent_asset_review_accepts_only_current_reviewer_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "output"
    object_ref = "posts/image/angle/title/1"
    source_digest = "sha256:" + "1" * 64
    judgment = {
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
        "safetyStatus": "passed",
        "entityMatch": "matched",
        "qualityStatus": "passed",
        "privacyRisk": "none",
        "minorRisk": "none",
        "maliciousMediaRisk": "none",
        "watermarkStatus": "absent",
        "findings": ["independent review passed"],
    }
    receipt = {
        "manifestId": "image-acquisition-1",
        "sourceRevision": "source-revision-1",
        "sourceDigest": source_digest,
        "entityCatalogDigest": "sha256:" + "2" * 64,
        "receiptDigest": "sha256:" + "3" * 64,
        "assets": [
            {
                "assetId": "image-1",
                "entityId": "entity-1",
                "observedEntityId": "entity-1",
                "contentSha256": "sha256:" + "4" * 64,
                "assetRef": "cas/image-1.jpg",
                "sourceUrl": "https://example.com/image-1.jpg",
                "platform": "example",
                "creator": "creator",
                "capturedAt": "2026-09-03T00:00:00Z",
                "license": "unknown",
                "termsUrl": "https://example.com/terms",
                "authorizationProof": "",
                "rightsIssues": ["commercial authorization missing"],
                "acquisitionStatus": "acquired",
                "rightsStatus": "unverified",
                "authorizationRequired": True,
                "distributionDecision": "research_allowed",
                "safetyReview": {
                    "status": "passed",
                    "entityMatch": "matched",
                    "privacyRisk": "none",
                    "minorRisk": "none",
                    "maliciousMediaRisk": "none",
                    "watermarkStatus": "absent",
                },
            }
        ],
    }
    manifest = {
        "executionId": EXECUTION_ID,
        "sourceDigest": {"digest": source_digest},
    }
    author = {
        "executionId": EXECUTION_ID,
        "ref": object_ref,
        "stage": "author",
        "agent": {
            "provider": "cursor-host",
            "model": "composer-2.5",
            "runId": "author-run-1",
            "promptSha256": "sha256:" + "5" * 64,
        },
        "files": [],
        "gates": [],
    }

    monkeypatch.setattr(
        independent_asset_review,
        "_load_acquisition",
        lambda *_args, **_kwargs: (
            receipt,
            "acquisition/receipts/image-acquisition-1.json",
            "sha256:" + "6" * 64,
        ),
    )

    def load_document(_path: Path, *, schema_name: str, **_kwargs: object):
        if schema_name == "content_execution_manifest":
            return manifest, "tasks/execution_manifest.json", "sha256:" + "7" * 64
        return author, "tasks/author.json", "sha256:" + "8" * 64

    monkeypatch.setattr(independent_asset_review, "load_document", load_document)
    reviewer_path = output_root / "tasks/reviewer.json"
    reviewer = {
        "schema": "quwoquan_data.reviewer_result",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": object_ref,
        "actor": {
            "host": "cursor",
            "sessionId": "review-session-1",
            "modelFamily": "composer",
            "invocation": {
                "provider": "cursor-host",
                "model": "composer-2.5",
                "runId": "review-run-1",
            },
        },
        "verdict": "passed",
        "issues": [],
        "findings": judgment["findings"],
        "resultHash": independent_asset_review.canonical_digest(judgment),
    }
    _write(reviewer_path, reviewer)

    stable = independent_asset_review._prepare_stable(
        output_root=output_root,
        acquisition_receipt_path=output_root / "acquisition.json",
        asset_kind="image",
        asset_id="image-1",
        execution_manifest_path=output_root / "execution_manifest.json",
        author_evidence_path=output_root / "author.json",
        reviewer_evidence_path=reviewer_path,
        object_ref=object_ref,
        judgment=judgment,
    )

    assert stable["reviewerExecution"] == {
        "executionId": "host-review:review-session-1",
        "objectRef": object_ref,
        "provider": "cursor-host",
        "model": "composer-2.5",
        "modelFamily": "composer",
        "runId": "review-run-1",
        "resultHash": reviewer["resultHash"],
        "evidenceRef": "tasks/reviewer.json",
        "evidenceSha256": independent_asset_review.file_digest(reviewer_path),
    }

    _write(
        reviewer_path,
        {
            "schema": "quwoquan_data.host_source_review_result",
            "actor": {"sessionId": "legacy-session"},
            "resultDigest": reviewer["resultHash"],
        },
    )
    with pytest.raises(
        independent_asset_review.IndependentAssetReviewError,
        match="asset independent reviewer evidence",
    ):
        independent_asset_review._prepare_stable(
            output_root=output_root,
            acquisition_receipt_path=output_root / "acquisition.json",
            asset_kind="image",
            asset_id="image-1",
            execution_manifest_path=output_root / "execution_manifest.json",
            author_evidence_path=output_root / "author.json",
            reviewer_evidence_path=reviewer_path,
            object_ref=object_ref,
            judgment=judgment,
        )


def test_stage_gate_fails_when_declared_target_directory_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / EXECUTION_ID
    _write(root / "0.plan/target_set.json", _target_set(["posts/video/angle/title/1"]))
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda _execution_id: root)
    report = stage_artifacts.verify_stage_artifacts(
        execution_id=EXECUTION_ID,
        publish_root=tmp_path / "publish",
        release_root=tmp_path / "release",
        commercial=False,
        through="1.download",
    )
    assert not report["passed"]
    assert report["objectCount"] == 1
    assert any("declared target object directory missing" in issue for issue in report["issues"])


def test_release_cohort_schema_requires_exact_four_carrier_counts() -> None:
    cohort = {
        "schema": "quwoquan_data.release_cohort",
        "releaseClass": "research",
        "objectRefs": ["entities/地点/景区/西湖", "posts/article/攻略/西湖/1"],
        "expectedCarrierCounts": {"homepage": 1, "article": 1, "image": 0, "video": 0},
    }
    assert_valid(cohort, "release", "release_cohort")
    cohort["expectedCarrierCounts"].pop("video")
    with pytest.raises(ValueError, match="video"):
        assert_valid(cohort, "release", "release_cohort")


def test_publish_object_rejects_target_outside_target_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / EXECUTION_ID
    _write(root / "0.plan/target_set.json", _target_set(["posts/video/angle/title/1"]))
    monkeypatch.setattr("content.release.canonical.publish_object.execution_root", lambda _execution_id: root)
    with pytest.raises(Exception, match="not declared"):
        _target_object(EXECUTION_ID, "posts/video/angle/other/1")


def test_pool_build_cli_requires_cohort_file() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "quwoquan_data/scripts/cli.py", "release", "pool-build", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "--cohort-file" in result.stdout
    assert "--all-publishable" not in result.stdout
    assert "--milestone" not in result.stdout


def test_publish_object_cli_is_single_target_only() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "quwoquan_data/scripts/cli.py", "release", "publish-object", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "--execution-id" in result.stdout
    assert "--target-ref" in result.stdout
    assert "publish-execution" not in result.stdout
