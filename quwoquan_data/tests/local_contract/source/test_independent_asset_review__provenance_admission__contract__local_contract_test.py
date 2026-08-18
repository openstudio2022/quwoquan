from __future__ import annotations

import hashlib
import io
import json
import shutil
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
from content.source.professional_image_acquisition import (
    ProfessionalImageAcquisitionError,
    acquire_professional_images,
    load_professional_image_acquisition_receipt,
)
from content.source.professional_image_admission import (
    admit_independently_reviewed_image,
)
from content.source.professional_image_discovery import (
    create_professional_image_discovery_plan,
)
from core.io import read_json, write_json
from core.source_digest import content_source_revision, current_execution_bundle_identity
from PIL import Image

EXECUTION_ID = "20260805--travel-image-m100--china--scale-010"
OBJECT_REF = "posts/image/九寨沟清晨"


@pytest.fixture(autouse=True)
def _governed_acquisition_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "content.source.professional_image_acquisition.guard_acquisition_source_identity",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "content.source.professional_image_acquisition.load_bound_safety_evidence",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "content.source.professional_image_acquisition.validate_image_safety_payload",
        lambda *_args, **_kwargs: None,
    )


def _digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _journal_digest(document: dict[str, object]) -> str:
    body = (
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _image_bytes() -> bytes:
    body = bytes((index * 31 + 7) % 256 for index in range(800 * 640 * 3))
    image = Image.frombytes("RGB", (800, 640), body)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _acquisition_item(*, rights_status: str) -> dict[str, object]:
    item: dict[str, object] = {
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
            "safetyEvidenceFileSha256": "sha256:" + "f" * 64,
        },
    }
    item["sourceAttribution"] = {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": "摄影师甲",
        "originalCreatorProfileUrl": None,
        "platform": "Pinterest",
        "sourcePostUrl": item["sourceUrl"],
        "originalAssetUrl": item["sourceUrl"],
        "attributionText": "摄影师甲 / unknown / Pinterest",
        "rightsBasis": "unknown",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": None,
        "termsUrl": "https://policy.pinterest.com/terms-of-service",
        "riskAcceptanceId": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-05T00:00:00Z",
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
    }
    return item


def _acquisition(
    output_root: Path,
    *,
    rights_status: str = "unverified",
) -> tuple[dict, Path]:
    acquisition_root = output_root / "data/local/workspace/source-acquisition"
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
    try:
        return acquire_professional_images(
            manifest_path,
            handoff_ref=output_root / "handoff.json",
            manual_root=manual_root,
            output_root=acquisition_root,
        )
    except ProfessionalImageAcquisitionError as exc:
        receipt_path = acquisition_root / exc.receipt_ref
        return (
            load_professional_image_acquisition_receipt(
                exc.receipt_ref,
                root=acquisition_root,
            ),
            receipt_path,
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
            "executionBundle": current_execution_bundle_identity().to_document(),
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
    acquisition_root = "data/local/workspace/source-acquisition/"
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
    assert binding["receiptRef"] == _path.relative_to(output_root).as_posix()
    assert not (object_root / "asset_reviews").exists()
    rights_asset = {
        "acquisitionReceiptRef": binding["acquisitionReceiptRef"],
        "independentAssetReview": binding,
        "asset": {
            "sha256": receipt["assetSnapshot"]["contentSha256"],
            "bytes": 1,
        },
    }
    assert validate_frozen_asset_review_binding(
        output_root=output_root,
        object_ref=OBJECT_REF,
        rights_asset=rights_asset,
        source_digest=receipt["sourceDigest"],
    ) == binding

    drifted_binding = {**binding, "entityCatalogDigest": _digest("drifted-catalog")}
    with pytest.raises(ObjectTransactionError, match="binding drift"):
        validate_frozen_asset_review_binding(
            output_root=output_root,
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


def test_supported_api_reviewer_keeps_distinct_frozen_execution_identity(
    tmp_path: Path,
) -> None:
    """A prior exact-byte reviewer journal may not be relabelled as the author run."""
    source = Path(__file__).resolve().parents[4] / ".qwq_output"
    author_execution = "20260812--travel-image-author--china--pilot-002"
    author_root = source / "data/tasks" / author_execution
    acquisition_root = source / (
        "data/local/workspace/source-acquisition/openverse-smoke3-20260812/"
        "preparations/professional-image-supported-api-dc7af7dd5436c975"
    )
    required = (
        author_root / "execution_manifest.json",
        acquisition_root
        / "receipts/903bcfd8dc2ed0d38aa23f1d07e57107bec1365920d817f42f2038a7a5b0d393.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        pytest.fail(
            "live frozen Image evidence is required by this contract test; "
            "rebuild the frozen execution work packages before running: "
            + ", ".join(missing)
        )

    # This test exercises only the contract helper against copied, immutable
    # fixture bytes; it must never mutate or trust the real output tree.
    output_root = tmp_path / "output"
    for relative in (
        "data/tasks/20260812--travel-image-author--china--pilot-002",
        "data/tasks/20260812--travel-image-review--china--pilot-001",
        "data/local/workspace/source-acquisition/openverse-smoke3-20260812/"
        "preparations/professional-image-supported-api-dc7af7dd5436c975",
    ):
        shutil.copytree(source / relative, output_root / relative)

    # The copied provider result intentionally keeps its historical reviewer
    # execution/run identity, while the journal fixture is projected onto the
    # current single-track attempt contract.  This is test-data migration only;
    # immutable runtime evidence in `.qwq_output` is never edited.
    reviewer_ref = (
        "data/tasks/20260812--travel-image-review--china--pilot-001/"
        "evidence/source_reviews/results/97f35fc1a0d7db726bd5.json"
    )
    reviewer_path = output_root / reviewer_ref
    reviewer = read_json(reviewer_path)
    attempt_path = output_root / reviewer["semanticTaskAttemptRef"]
    attempt = read_json(attempt_path)
    attempt.pop("capacityReceiptRef", None)
    attempt.pop("capacityReceiptDigest", None)
    attempt.update(
        {
            "started": True,
            "messageSha256": _digest(""),
            "retryAfterSeconds": 0,
            "attempts": 1,
            "warmAttempts": 0,
        }
    )
    attempt["attemptDigest"] = _journal_digest(
        {key: value for key, value in attempt.items() if key != "attemptDigest"}
    )
    write_json(attempt_path, attempt)
    reviewer["semanticTaskAttemptSha256"] = (
        "sha256:" + hashlib.sha256(attempt_path.read_bytes()).hexdigest()
    )
    write_json(reviewer_path, reviewer)

    author_token = "97f35fc1a0d7db726bd5"
    judgment = {
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
        "safetyStatus": "passed",
        "entityMatch": reviewer["judgment"]["entityMatch"],
        "qualityStatus": reviewer["judgment"]["qualityStatus"],
        "privacyRisk": reviewer["judgment"]["privacyRisk"],
        "minorRisk": reviewer["judgment"]["minorRisk"],
        "maliciousMediaRisk": reviewer["judgment"]["maliciousMediaRisk"],
        "watermarkStatus": reviewer["judgment"]["watermarkStatus"],
        "findings": reviewer["judgment"]["findings"],
    }
    receipt, _path = write_independent_asset_review_receipt(
        acquisition_receipt_path=output_root / required[1].relative_to(source),
        asset_kind="image",
        asset_id="openverse:asset:0e8185daea1b63a9",
        execution_manifest_path=output_root / required[0].relative_to(source),
        author_evidence_path=output_root / (
            f"data/tasks/{author_execution}/evidence/source_authors/objects/"
            f"{author_token}/4.draft/agent_result_envelope.json"
        ),
        reviewer_evidence_path=output_root / reviewer_ref,
        object_ref="/professional-image/openverse:asset:0e8185daea1b63a9",
        judgment=judgment,
        output_root=output_root,
    )
    assert receipt["reviewDecision"] == "accepted"
    assert receipt["authorExecution"]["executionId"] == author_execution
    assert receipt["reviewerExecution"]["executionId"] == (
        "20260812--travel-image-review--china--pilot-001"
    )
    assert receipt["authorExecution"]["runId"] != receipt["reviewerExecution"]["runId"]


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


def test_research_review_projects_rights_from_acquisition_without_commercial_upgrade() -> None:
    from content.source.independent_asset_review import _review_decision
    from content.source.independent_asset_review_contract import (
        project_research_judgment_to_acquisition_truth,
    )

    snapshot = {
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
    }
    semantic_judgment = {
        **_judgment(),
        "rightsStatus": "verified",
        "authorizationRequired": False,
        "distributionDecision": "commercial_allowed",
    }
    projected = project_research_judgment_to_acquisition_truth(
        semantic_judgment,
        snapshot=snapshot,
    )

    assert projected["rightsStatus"] == "unverified"
    assert projected["authorizationRequired"] is True
    assert projected["distributionDecision"] == "research_allowed"
    assert _review_decision(
        projected,
        snapshot=snapshot,
        acquisition_safety={
            "status": "passed",
            "entityMatch": "matched",
            "privacyRisk": "none",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
        },
    ) == "accepted"


def test_author_file_tamper_still_fails_independent_asset_review(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    acquisition, acquisition_path = _acquisition(output_root)
    manifest = _execution_manifest(
        output_root,
        source_digest=acquisition["sourceDigest"],
    )
    judgment = _judgment()
    author, reviewer = _semantic_evidence(output_root, judgment=judgment)
    authored = author.parent / "authored.json"
    write_json(authored, {"objectRef": OBJECT_REF, "title": "篡改后的标题"})

    with pytest.raises(IndependentAssetReviewError, match="author file evidence drift"):
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


def test_strict_review_gate_still_rejects_commercial_rights_upgrade() -> None:
    from content.source.independent_asset_review import _review_decision

    snapshot = {
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
    }
    with pytest.raises(
        IndependentAssetReviewError,
        match="rightsStatus cannot upgrade",
    ):
        _review_decision(
            {
                **_judgment(),
                "rightsStatus": "verified",
                "authorizationRequired": False,
                "distributionDecision": "commercial_allowed",
            },
            snapshot=snapshot,
            acquisition_safety={
                "status": "passed",
                "entityMatch": "matched",
                "privacyRisk": "none",
                "minorRisk": "none",
                "maliciousMediaRisk": "none",
                "watermarkStatus": "absent",
            },
        )


def test_review_cannot_upgrade_restricted_rights_to_research_allowed(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    with pytest.raises(IndependentAssetReviewError, match="rightsStatus cannot upgrade"):
        _write_review(
            output_root,
            rights_status="restricted",
            judgment=_judgment(rights_status="unverified"),
        )
