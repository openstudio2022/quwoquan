from __future__ import annotations

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from content.release.canonical.asset_review_adoption import (
    adopt_independent_asset_review,
    validate_frozen_asset_review_binding,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from content.source.independent_asset_review import (
    IndependentAssetReviewError,
    assert_asset_review_accepted,
    load_independent_asset_review_receipt,
    write_independent_asset_review_receipt,
)
from content.source.independent_asset_review_contract import canonical_digest
from content.source.professional_image_acquisition import acquire_professional_images
from content.source.professional_image_admission import (
    admit_independently_reviewed_image,
)
from content.source.professional_image_discovery import (
    create_professional_image_discovery_plan,
)
from core.io import read_json, write_json
from core.source_digest import content_source_revision
from PIL import Image

EXECUTION_ID = "20260805--travel-image-m100--china--scale-010"
OBJECT_REF = "posts/image/九寨沟清晨"


def _digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _image_bytes() -> bytes:
    body = bytes((index * 31 + 7) % 256 for index in range(800 * 640 * 3))
    image = Image.frombytes("RGB", (800, 640), body)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _acquisition_item(*, rights_status: str) -> dict[str, object]:
    return {
        "assetId": "pin-independent-1",
        "entityId": "九寨沟",
        "observedEntityId": "九寨沟",
        "entityAliases": ["九寨沟风景名胜区", "Jiuzhaigou"],
        "sourceId": "pinterest",
        "displayName": "九寨沟专业摄影候选",
        "acquisitionPath": "manual_file",
        "sourceUrl": "https://www.pinterest.com/pin/independent-1/",
        "assetUrl": "",
        "manualFile": "pinterest.jpg",
        "apiEvidence": "",
        "accessEvidence": {
            "anonymousAssetAccess": False,
            "loginRequired": False,
            "captchaRequired": False,
            "paywallRequired": False,
            "drmProtected": False,
            "accessControlBypass": False,
        },
        "creator": "摄影师甲",
        "capturedAt": "2026-08-05T00:00:00Z",
        "rightsStatus": rights_status,
        "license": "unknown",
        "licenseSnapshot": "source license captured before acquisition",
        "usageScope": "internal_reference",
        "modelReleaseStatus": "not_required",
        "termsUrl": "https://policy.pinterest.com/terms-of-service",
        "authorizationProof": "",
        "rightsIssues": ["distribution authorization has not been verified"],
        "caption": "九寨沟五花海清晨摄影作品",
        "relevance": "画面主体为九寨沟五花海",
        "safetyReview": {
            "status": "passed",
            "entityMatch": "matched",
            "privacyRisk": "none",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
            "reviewedAt": "2026-08-05T00:05:00Z",
            "reviewer": "acquisition-writer-self-report",
            "evidenceRef": "evidence/pin-independent-1.json",
        },
    }


def _acquisition(
    output_root: Path,
    *,
    rights_status: str = "unverified",
) -> tuple[dict, Path]:
    acquisition_root = output_root / "data/local/workspace/source-acquisition/image"
    plan, plan_path = create_professional_image_discovery_plan(
        entities=["九寨沟"],
        category="风光",
        season="秋季",
        style="纪实",
        viewpoint="广角",
        popularity="热门",
        output_root=acquisition_root / "discovery-plans",
    )
    candidate = next(row for row in plan["candidates"] if row["provider"] == "pinterest")
    item = _acquisition_item(rights_status=rights_status)
    item["discoveryCandidateId"] = candidate["candidateId"]
    item["discoveryUrl"] = candidate["discoveryUrl"]
    manual_root = output_root / "manual"
    manual_root.mkdir(parents=True, exist_ok=True)
    (manual_root / "pinterest.jpg").write_bytes(_image_bytes())
    source_digest = _digest("source")
    entity_catalog_digest = _digest("entities")
    manifest = {
        "schema": "quwoquan_data.professional_image_acquisition_manifest",
        "manifestId": f"pinterest-independent-{rights_status}",
        "sourceRevision": content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        ),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "discoveryPlanRef": plan_path.relative_to(acquisition_root).as_posix(),
        "discoveryPlanDigest": plan["planDigest"],
        "items": [item],
    }
    manifest_path = output_root / "inputs/image-acquisition.json"
    write_json(manifest_path, manifest)
    return acquire_professional_images(
        manifest_path,
        manual_root=manual_root,
        output_root=acquisition_root,
    )


def _execution_manifest(output_root: Path, *, source_digest: str) -> Path:
    root = output_root / "data/tasks" / EXECUTION_ID
    target_set = {
        "executionId": EXECUTION_ID,
        "selectionPolicy": "frozen",
        "sourceRef": "quwoquan_data/reference/travel/entities/china",
        "entityCatalogDigest": _digest("entities"),
        "targetCount": 1,
        "targetRefs": ["地点/景区/九寨沟"],
        "targets": [{"name": "九寨沟", "entityType": "地点/景区"}],
    }
    write_json(root / "0.plan/target_set.json", target_set)
    path = root / "execution_manifest.json"
    write_json(
        path,
        {
            "executionId": EXECUTION_ID,
            "familyRef": {"ref": "content/travel/image", "sha256": "a" * 64},
            "sourceDigest": {
                "algorithm": "sha256",
                "digest": source_digest,
                "inputs": ["quwoquan_data/control_plane"],
            },
            "modelBinding": {
                "provider": "codex_sdk",
                "authorModel": "gpt-5.6-terra",
                "authorModelFamily": "gpt",
                "authorModelParameters": [],
                "reviewerModel": "gpt-5.6-terra",
                "reviewerModelFamily": "gpt",
                "reviewerModelParameters": [],
            },
            "runtimeProfileId": "semantic-runtime-v1",
            "runtimeProfileDigest": _digest("runtime"),
            "semanticSelectionId": "default",
            "semanticRuntime": "local",
            "requestRef": "0.plan/request.json",
            "targetSetRef": "0.plan/target_set.json",
            "targetSetDigest": canonical_digest(target_set).removeprefix("sha256:"),
            "retryOf": None,
        },
    )
    return path


def _semantic_evidence(
    output_root: Path,
    *,
    judgment: dict[str, object],
    reviewer_run_id: str = "review-run-001",
) -> tuple[Path, Path]:
    evidence_root = output_root / "data/tasks" / EXECUTION_ID / "evidence/asset-review"
    authored = evidence_root / "authored.json"
    write_json(authored, {"objectRef": OBJECT_REF, "title": "九寨沟清晨"})
    author = evidence_root / "author.json"
    write_json(
        author,
        {
            "schema": "quwoquan.agent_result_envelope",
            "executionId": EXECUTION_ID,
            "jobId": "asset-author-job-001",
            "ref": OBJECT_REF,
            "stage": "author",
            "agent": {
                "provider": "codex_sdk",
                "model": "gpt-5.6-terra",
                "runId": "author-run-001",
                "promptSha256": _digest("author-prompt"),
            },
            "files": [
                {
                    "path": authored.name,
                    "sha256": "sha256:" + hashlib.sha256(authored.read_bytes()).hexdigest(),
                    "role": "authored_object",
                }
            ],
            "gates": [
                {
                    "schema": "quwoquan.gate_verdict",
                    "gateId": "author_output",
                    "decision": "passed",
                    "final": True,
                    "inputHash": _digest("author-input"),
                    "outputHash": _digest("author-output"),
                    "issues": [],
                }
            ],
        },
    )
    accepted = judgment["distributionDecision"] != "blocked"
    findings = list(judgment["findings"])
    reviewer = evidence_root / "reviewer.json"
    write_json(
        reviewer,
        {
            "schema": "quwoquan_data.reviewer_result",
            "stage": "5.review",
            "executionId": EXECUTION_ID,
            "objectRef": OBJECT_REF,
            "provider": "codex_sdk",
            "model": "gpt-5.6-terra",
            "modelFamily": "gpt",
            "runId": reviewer_run_id,
            "verdict": "passed" if accepted else "failed",
            "issues": [] if accepted else findings,
            "findings": findings,
            "resultHash": canonical_digest(judgment),
        },
    )
    return author, reviewer


def _judgment(*, rights_status: str = "unverified", blocked: bool = False) -> dict[str, object]:
    return {
        "rightsStatus": rights_status,
        "authorizationRequired": rights_status != "verified",
        "distributionDecision": "blocked" if blocked else "research_allowed",
        "safetyStatus": "passed",
        "entityMatch": "matched",
        "qualityStatus": "passed",
        "privacyRisk": "none",
        "minorRisk": "none",
        "maliciousMediaRisk": "none",
        "watermarkStatus": "absent",
        "findings": (
            ["restricted rights block research distribution"]
            if blocked
            else ["independent rights, safety, entity and quality review passed"]
        ),
    }


def _write_review(
    output_root: Path,
    *,
    rights_status: str = "unverified",
    judgment: dict[str, object] | None = None,
    reviewer_run_id: str = "review-run-001",
) -> tuple[dict, Path]:
    acquisition, acquisition_path = _acquisition(
        output_root,
        rights_status=rights_status,
    )
    selected_judgment = judgment or _judgment(rights_status=rights_status)
    manifest_path = _execution_manifest(
        output_root,
        source_digest=acquisition["sourceDigest"],
    )
    author_path, reviewer_path = _semantic_evidence(
        output_root,
        judgment=selected_judgment,
        reviewer_run_id=reviewer_run_id,
    )
    return write_independent_asset_review_receipt(
        acquisition_receipt_path=acquisition_path,
        asset_kind="image",
        asset_id="pin-independent-1",
        execution_manifest_path=manifest_path,
        author_evidence_path=author_path,
        reviewer_evidence_path=reviewer_path,
        object_ref=OBJECT_REF,
        judgment=selected_judgment,
        output_root=output_root,
    )


def test_research_unverified_asset_requires_independent_create_once_receipt(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    receipt, path = _write_review(output_root)

    assert path.name == f"{receipt['reviewId']}.json"
    assert path.parent == (
        output_root
        / "data/tasks"
        / EXECUTION_ID
        / "evidence/asset_reviews/receipts"
    )
    assert receipt["reviewDecision"] == "accepted"
    assert receipt["assetSnapshot"]["rightsStatus"] == "unverified"
    assert receipt["assetSnapshot"]["authorizationRequired"] is True
    assert receipt["acquisitionExecution"]["runId"] != receipt["authorExecution"]["runId"]
    assert receipt["authorExecution"]["runId"] != receipt["reviewerExecution"]["runId"]
    assert_asset_review_accepted(
        receipt,
        content_sha256=receipt["assetSnapshot"]["contentSha256"],
        source_digest=receipt["sourceDigest"],
        asset_id="pin-independent-1",
    )
    acquisition_path = output_root / receipt["acquisitionReceiptRef"]
    acquisition = read_json(acquisition_path)
    asset = next(row for row in acquisition["assets"] if row["assetId"] == "pin-independent-1")
    admitted = admit_independently_reviewed_image(asset, receipt)
    assert admitted["independentAssetReviewId"] == receipt["reviewId"]
    with pytest.raises(IndependentAssetReviewError, match="snapshot drift"):
        admit_independently_reviewed_image(
            {**asset, "creator": "acquisition-writer-overwrite"},
            receipt,
        )
    with pytest.raises(IndependentAssetReviewError, match="snapshot drift"):
        admit_independently_reviewed_image(
            {**asset, "usageScope": "app_publish"},
            receipt,
        )

    repeated, repeated_path = _write_review(output_root)
    assert repeated_path == path
    assert repeated == receipt
    loaded = load_independent_asset_review_receipt(
        path.relative_to(output_root).as_posix(),
        output_root=output_root,
    )
    assert loaded == receipt


def test_canonical_adoption_binds_exact_review_bytes_and_source_identity(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    receipt, _path = _write_review(output_root)
    execution_root = output_root / "data/tasks" / EXECUTION_ID
    execution_manifest = read_json(execution_root / "execution_manifest.json")
    acquisition_root = "data/local/workspace/source-acquisition/image/"
    acquisition_ref = str(receipt["acquisitionReceiptRef"])
    assert acquisition_ref.startswith(acquisition_root)
    source = {
        "acquisitionReceiptRef": acquisition_ref.removeprefix(acquisition_root),
        "professionalAssetId": receipt["assetSnapshot"]["assetId"],
        "professionalContentSha256": receipt["assetSnapshot"]["contentSha256"],
    }
    object_root = tmp_path / "canonical-object"
    object_root.mkdir()
    binding = adopt_independent_asset_review(
        raw_asset={},
        related_sources=(source,),
        asset_kind="image",
        asset_id="canonical-image-cover",
        content_sha256=receipt["assetSnapshot"]["contentSha256"],
        object_ref=OBJECT_REF,
        execution_root=execution_root,
        execution_manifest=execution_manifest,
        object_root=object_root,
        source_digest=receipt["sourceDigest"],
    )
    assert binding is not None
    assert binding["sourceRevision"] == receipt["sourceRevision"]
    assert binding["entityCatalogDigest"] == receipt["entityCatalogDigest"]
    assert (object_root / binding["receiptRef"]).read_bytes() == _path.read_bytes()
    rights_asset = {
        "acquisitionReceiptRef": binding["acquisitionReceiptRef"],
        "independentAssetReview": binding,
        "asset": {
            "sha256": receipt["assetSnapshot"]["contentSha256"],
            "bytes": 1,
        },
    }
    assert validate_frozen_asset_review_binding(
        object_root=object_root,
        object_ref=OBJECT_REF,
        rights_asset=rights_asset,
        source_digest=receipt["sourceDigest"],
    ) == binding

    drifted_binding = {**binding, "entityCatalogDigest": _digest("drifted-catalog")}
    with pytest.raises(ObjectTransactionError, match="binding drift"):
        validate_frozen_asset_review_binding(
            object_root=object_root,
            object_ref=OBJECT_REF,
            rights_asset={
                **rights_asset,
                "independentAssetReview": drifted_binding,
            },
            source_digest=receipt["sourceDigest"],
        )
    with pytest.raises(ObjectTransactionError, match="exactly one"):
        adopt_independent_asset_review(
            raw_asset={},
            related_sources=(source,),
            asset_kind="image",
            asset_id="acquisition-only",
            content_sha256=receipt["assetSnapshot"]["contentSha256"],
            object_ref="posts/image/unreviewed",
            execution_root=execution_root,
            execution_manifest=execution_manifest,
            object_root=tmp_path / "unreviewed-object",
            source_digest=receipt["sourceDigest"],
        )


def test_reviewer_cannot_reuse_author_run_or_self_report_result_hash(tmp_path: Path) -> None:
    output_root = tmp_path / "same-run"
    with pytest.raises(IndependentAssetReviewError, match="independent runId"):
        _write_review(output_root, reviewer_run_id="author-run-001")

    output_root = tmp_path / "unbound-result"
    acquisition, acquisition_path = _acquisition(output_root)
    manifest = _execution_manifest(output_root, source_digest=acquisition["sourceDigest"])
    judgment = _judgment()
    author, reviewer = _semantic_evidence(output_root, judgment=judgment)
    payload = read_json(reviewer)
    payload["resultHash"] = _digest("different-judgment")
    write_json(reviewer, payload)
    with pytest.raises(IndependentAssetReviewError, match="resultHash/findings"):
        write_independent_asset_review_receipt(
            acquisition_receipt_path=acquisition_path,
            asset_kind="image",
            asset_id="pin-independent-1",
            execution_manifest_path=manifest,
            author_evidence_path=author,
            reviewer_evidence_path=reviewer,
            object_ref=OBJECT_REF,
            judgment=judgment,
            output_root=output_root,
        )


def test_create_once_is_stable_under_concurrent_identical_writers(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    acquisition, acquisition_path = _acquisition(output_root)
    manifest = _execution_manifest(output_root, source_digest=acquisition["sourceDigest"])
    judgment = _judgment()
    author, reviewer = _semantic_evidence(output_root, judgment=judgment)

    def write_once(_index: int) -> tuple[dict, Path]:
        return write_independent_asset_review_receipt(
            acquisition_receipt_path=acquisition_path,
            asset_kind="image",
            asset_id="pin-independent-1",
            execution_manifest_path=manifest,
            author_evidence_path=author,
            reviewer_evidence_path=reviewer,
            object_ref=OBJECT_REF,
            judgment=judgment,
            output_root=output_root,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(write_once, range(16)))

    assert len({path for _receipt, path in results}) == 1
    assert len({receipt["receiptDigest"] for receipt, _path in results}) == 1


def test_execution_source_digest_drift_is_blocked(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _acquisition_receipt, acquisition_path = _acquisition(output_root)
    manifest = _execution_manifest(output_root, source_digest=_digest("drifted-source"))
    judgment = _judgment()
    author, reviewer = _semantic_evidence(output_root, judgment=judgment)
    with pytest.raises(IndependentAssetReviewError, match="identity drift"):
        write_independent_asset_review_receipt(
            acquisition_receipt_path=acquisition_path,
            asset_kind="image",
            asset_id="pin-independent-1",
            execution_manifest_path=manifest,
            author_evidence_path=author,
            reviewer_evidence_path=reviewer,
            object_ref=OBJECT_REF,
            judgment=judgment,
            output_root=output_root,
        )


def test_identity_or_receipt_evidence_drift_fails_closed(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    receipt, path = _write_review(output_root)
    reviewer_path = output_root / receipt["reviewerExecution"]["evidenceRef"]
    reviewer = read_json(reviewer_path)
    reviewer["runId"] = "review-run-tampered"
    write_json(reviewer_path, reviewer)

    with pytest.raises(IndependentAssetReviewError, match="provenance drift|evidenceSha256"):
        load_independent_asset_review_receipt(
            path.relative_to(output_root).as_posix(),
            output_root=output_root,
        )


def test_restricted_asset_can_only_freeze_a_blocked_review(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    judgment = _judgment(rights_status="restricted", blocked=True)
    receipt, _path = _write_review(
        output_root,
        rights_status="restricted",
        judgment=judgment,
    )
    assert receipt["reviewDecision"] == "blocked"
    with pytest.raises(IndependentAssetReviewError, match="not covered"):
        assert_asset_review_accepted(
            receipt,
            content_sha256=receipt["assetSnapshot"]["contentSha256"],
            source_digest=receipt["sourceDigest"],
            asset_id="pin-independent-1",
        )


def test_unknown_rights_remain_research_admissible_after_independent_review(
    tmp_path: Path,
) -> None:
    receipt, _path = _write_review(
        tmp_path / "output",
        rights_status="unknown",
        judgment=_judgment(rights_status="unknown"),
    )
    assert receipt["reviewDecision"] == "accepted"
    assert receipt["assetSnapshot"]["rightsStatus"] == "unknown"
    assert receipt["assetSnapshot"]["authorizationRequired"] is True


def test_review_cannot_upgrade_restricted_rights_to_research_allowed(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    with pytest.raises(IndependentAssetReviewError, match="rightsStatus cannot upgrade"):
        _write_review(
            output_root,
            rights_status="restricted",
            judgment=_judgment(rights_status="unverified"),
        )
