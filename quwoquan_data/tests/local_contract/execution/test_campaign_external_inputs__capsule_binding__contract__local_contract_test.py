# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from content.execution.campaign import request_envelope as campaign_request_envelope
from content.execution.campaign import (
    request_envelope_build as campaign_request_envelope_build,
)
from content.execution.campaign import submission as campaign_submission
from content.execution.campaign.external_input_runtime import (
    ExternalInputRuntimeContext,
    freeze_execution_external_input_envelope,
    resolve_runtime_external_input_context,
)
from content.execution.campaign.external_inputs import (
    CampaignExternalInputError,
    bind_external_input_refs,
    content_source_revision,
    external_inputs_digest,
    materialize_external_input_bundle,
    payload_digest,
    verify_external_input_refs,
)
from content.execution.campaign.submission import write_submission
from content.execution.campaign.workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
    SourceCapsule,
)
from content.execution.request import RuntimeExecutionRequest
from content.source import source_inputs
from content.source.contracts import (
    HomepageAuthorityProvider,
    QualifiedHomepageSource,
)
from content.source.external_acquisition_inputs import (
    professional_image_context_binding,
)
from content.source.professional_image_acquisition import acquire_professional_images
from content.source.professional_image_discovery import (
    create_professional_image_discovery_plan,
)
from content.source.research import auto_plan_homepage
from content.source.research.auto_plan_homepage import (
    HomepageResearchInput,
    write_homepage_lane,
)
from content.source.research.auto_plan_lanes import write_image_lane
from core.control_types import TargetSelector
from core.io import read_json, write_json
from PIL import Image
from support.semantic_preflight_fixture import ready_semantic_preflight

ROOT_ID = "20260805--travel-homepage-m100--china--scale-101"
EXECUTION_IDS = {
    "homepage": ROOT_ID,
    "article": "20260805--travel-article-m100--china--scale-101",
    "image": "20260805--travel-image-m100--china--scale-101",
    "video": "20260805--travel-video-m100--china--scale-101",
}
SOURCE_DIGEST = "sha256:" + ("a" * 64)
CATALOG_DIGEST = "sha256:" + ("b" * 64)
SOURCE_REVISION = content_source_revision(
    source_digest=SOURCE_DIGEST,
    entity_catalog_digest=CATALOG_DIGEST,
)


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
    monkeypatch.setattr(
        "content.execution.controller.execute.pre_acquisition_handoff.bind_pre_acquisition_handoff",
        lambda *_args, **_kwargs: (
            {
                "carrierRequirements": {
                    "image": {
                        "requiredExternalInputKinds": [
                            "professional_image_acquisition"
                        ]
                    }
                }
            },
            {
                "handoffId": "test-handoff",
                "handoffRevision": 1,
                "handoffRef": (
                    "data/local/workspace/content-pre-acquisition-handoffs/"
                    "test-handoff/revision-001.json"
                ),
                "handoffDigest": "sha256:" + "9" * 64,
                "handoffFileDigest": "sha256:" + "8" * 64,
            },
        ),
    )


class _FrozenSourceDigest:
    def __init__(self, document: dict[str, object]) -> None:
        self._document = document

    def to_document(self) -> dict[str, object]:
        return self._document


def test_campaign_submission_accepts_stable_dirty_source_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    document: dict[str, object] = {
        "algorithm": "sha256",
        "digest": SOURCE_DIGEST,
        "inputs": ["quwoquan_data/scripts"],
    }
    monkeypatch.setattr(
        campaign_submission,
        "current_source_digest",
        lambda **_kwargs: _FrozenSourceDigest(document),
    )

    campaign_submission._require_stable_source_inputs(document, repo_root=tmp_path)


def test_campaign_submission_rejects_source_digest_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    frozen: dict[str, object] = {
        "algorithm": "sha256",
        "digest": SOURCE_DIGEST,
        "inputs": ["quwoquan_data/scripts"],
    }
    observed = {**frozen, "digest": "sha256:" + ("f" * 64)}
    monkeypatch.setattr(
        campaign_submission,
        "current_source_digest",
        lambda **_kwargs: _FrozenSourceDigest(observed),
    )

    with pytest.raises(ValueError, match="changed during freeze"):
        campaign_submission._require_stable_source_inputs(frozen, repo_root=tmp_path)


def _image_bytes() -> bytes:
    body = bytes((index * 31 + 17) % 256 for index in range(800 * 640 * 3))
    image = Image.frombytes("RGB", (800, 640), body)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _acquisition(tmp_path: Path) -> tuple[Path, list[dict[str, object]]]:
    acquisition_root = tmp_path / "output/data/local/workspace/source-acquisition"
    manifest_path = acquisition_root / "manifests/image.json"
    discovery_plan, discovery_plan_path = create_professional_image_discovery_plan(
        entities=["九寨沟"],
        category="风光",
        season="秋季",
        style="纪实",
        viewpoint="广角",
        popularity="热门",
        output_root=acquisition_root / "discovery-plans",
    )
    discovery_candidate = next(
        row for row in discovery_plan["candidates"] if row["provider"] == "pinterest"
    )
    manual_root = tmp_path / "manual"
    manual_root.mkdir(parents=True)
    (manual_root / "photo.jpg").write_bytes(_image_bytes())
    manifest = {
        "schema": "quwoquan_data.professional_image_acquisition_manifest",
        "manifestId": "campaign-image-input",
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "discoveryPlanRef": discovery_plan_path.relative_to(
            acquisition_root
        ).as_posix(),
        "discoveryPlanDigest": discovery_plan["planDigest"],
        "items": [
            {
                "assetId": "pinterest-photo-1",
                "entityId": "九寨沟",
                "observedEntityId": "九寨沟",
                "entityAliases": ["九寨沟风景名胜区", "Jiuzhaigou"],
                "sourceId": "pinterest",
                "displayName": "九寨沟专业摄影候选",
                "discoveryCandidateId": discovery_candidate["candidateId"],
                "discoveryUrl": discovery_candidate["discoveryUrl"],
                "acquisitionPath": "manual_file",
                "sourceUrl": "https://www.pinterest.example/pin/1",
                "assetUrl": "",
                "manualFile": "photo.jpg",
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
                "rightsStatus": "verified",
                "license": "CC BY 4.0",
                "licenseSnapshot": "CC BY 4.0 captured before acquisition",
                "usageScope": "app_publish",
                "modelReleaseStatus": "not_required",
                "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                "authorizationProof": "https://www.pinterest.example/pin/1",
                "rightsIssues": [],
                "caption": "九寨沟五花海清晨摄影作品",
                "relevance": "主体为九寨沟五花海",
                "safetyReview": {
                    "status": "passed",
                    "entityMatch": "matched",
                    "privacyRisk": "none",
                    "minorRisk": "none",
                    "maliciousMediaRisk": "none",
                    "watermarkStatus": "absent",
                    "reviewedAt": "2026-08-05T00:05:00Z",
                    "reviewer": "local-contract-reviewer",
                    "evidenceRef": "evidence/pinterest-photo-1.json",
                    "safetyEvidenceFileSha256": "sha256:" + "f" * 64,
                },
                "sourceAttribution": {
                    "isOriginal": False,
                    "originalCreatorId": None,
                    "originalCreatorName": "摄影师甲",
                    "originalCreatorProfileUrl": None,
                    "platform": "Pinterest",
                    "sourcePostUrl": "https://www.pinterest.example/pin/1",
                    "originalAssetUrl": "https://www.pinterest.example/pin/1",
                    "attributionText": "摄影师甲 / CC BY 4.0 / Pinterest",
                    "rightsBasis": "CC BY 4.0",
                    "commercialAuthorizationStatus": "verified",
                    "publicationAdmission": "commercial_release",
                    "authorizationProofUrl": "https://www.pinterest.example/pin/1",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "riskAcceptanceId": None,
                    "watermarkStatus": "absent",
                    "audioRightsStatus": "no_audio",
                    "modelReleaseStatus": "not_required",
                    "propertyReleaseStatus": "not_required",
                    "collectedAt": "2026-08-05T00:00:00Z",
                    "takedownPolicy": "quwoquan_standard_notice_and_takedown",
                },
            }
        ],
    }
    write_json(manifest_path, manifest)
    _, receipt_path = acquire_professional_images(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=acquisition_root,
    )
    declarations = [
        {
            "kind": "professional_image_acquisition",
            "manifestRef": manifest_path.relative_to(acquisition_root).as_posix(),
            "receiptRef": receipt_path.relative_to(acquisition_root).as_posix(),
        }
    ]
    refs = bind_external_input_refs(
        "image",
        declarations,
        acquisition_root=acquisition_root,
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=CATALOG_DIGEST,
    )
    return acquisition_root, refs


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    output = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=output,
        publish_root=tmp_path / "publish",
        campaigns_root=output / "data/local/workspace/content-campaign-submissions",
        workspaces_root=output / "data/local/cache/content-campaign-workspaces",
    )


def _external_context(
    root: Path,
    refs: list[dict[str, object]],
    *,
    execution_id: str,
    carrier: str,
) -> ExternalInputRuntimeContext:
    blobs = {
        str(blob["contentSha256"]): (
            Path(str(row["acquisitionRootRef"])) / str(blob["blobRef"])
        ).as_posix()
        for row in refs
        for blob in row["blobRefs"]
    }
    return ExternalInputRuntimeContext(
        root=root,
        envelope={"executionId": execution_id, "carrier": carrier},
        refs=tuple(dict(row) for row in refs),
        blob_refs_by_digest=blobs,
    )


def _submission(
    carrier: str,
    refs: list[dict[str, object]],
    *,
    semantic_preflight_binding: dict[str, str],
    scale_source_pool: dict[str, object],
    source_pool_evidence_root_ref: str,
    source_pool_selection: dict[str, object],
) -> dict[str, object]:
    stable: dict[str, object] = {
        "schema": "quwoquan_data.content_execution_submission",
        "scale": "M100",
        "rootExecutionId": ROOT_ID,
        "executionId": EXECUTION_IDS[carrier],
        "operation": f"{carrier}.generate",
        "carrier": carrier,
        "familyRef": f"content/travel/{carrier}/{carrier}",
        "regionRef": "china",
        "selector": "source-ready-priority"
        if carrier in {"homepage", "video"}
        else "priority",
        "quota": 100,
        "count": 150,
        "requiredWorkers": 1,
        "partitionCount": 16,
        "capacityPlanDigest": "sha256:" + "6" * 64,
        "workerHostSetBinding": None,
        "topic": None,
        "targetNames": [],
        "sourceProviders": [],
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": semantic_preflight_binding,
        "scaleSourcePool": scale_source_pool,
        "sourcePoolEvidenceRootRef": source_pool_evidence_root_ref,
        "sourcePoolSelection": source_pool_selection,
        "retryOf": None,
        "gitBranch": "dev1.0",
        "gitCommitSha": "c" * 40,
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": SOURCE_DIGEST,
            "inputs": ["quwoquan_data/schema"],
        },
        "entityCatalogDigest": CATALOG_DIGEST,
        "externalInputRefs": refs,
        "externalInputsDigest": external_inputs_digest(refs),
    }
    return {
        **stable,
        "requestDigest": payload_digest(stable),
        "submittedAt": "2026-08-05T00:00:00Z",
    }


def _scale_source_pool(
    runtime: CampaignRuntimePaths,
) -> tuple[dict[str, object], str, dict[str, dict[str, object]]]:
    pool_stable: dict[str, object] = {
        "schema": "quwoquan_data.scale_source_pool",
        "poolId": "external-input-m100-pool",
        "targetScale": "M100",
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "candidates": [
            {
                "candidateId": f"{carrier}-candidate-001",
                "carrier": carrier,
                "objectRef": f"{carrier}/candidate-001",
            }
            for carrier in EXECUTION_IDS
        ],
    }
    pool = {**pool_stable, "planDigest": payload_digest(pool_stable)}
    pool_path = runtime.output_root / "data/local/workspace/scale-source-pool/plan.json"
    write_json(pool_path, pool)
    evidence_root = runtime.output_root / "data/local/workspace/scale-source-pool/evidence"
    evidence_root.mkdir(parents=True)
    binding = {
        "poolId": pool["poolId"],
        "targetScale": pool["targetScale"],
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "planRef": pool_path.relative_to(runtime.output_root).as_posix(),
        "planDigest": pool["planDigest"],
        "planFileSha256": "sha256:" + hashlib.sha256(pool_path.read_bytes()).hexdigest(),
    }
    selections: dict[str, dict[str, object]] = {}
    for carrier in EXECUTION_IDS:
        stable = {
            "carrier": carrier,
            "candidateIds": [f"{carrier}-candidate-001"],
            "candidateCount": 1,
        }
        selections[carrier] = {**stable, "selectionDigest": payload_digest(stable)}
    return binding, evidence_root.relative_to(runtime.output_root).as_posix(), selections


def _frozen_documents(
    runtime: CampaignRuntimePaths,
    image_refs: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    _preflight_path, semantic_preflight_binding = ready_semantic_preflight(
        "default",
        output_root=runtime.output_root,
    )
    pool_binding, pool_evidence_ref, pool_selections = _scale_source_pool(runtime)
    submissions = {
        carrier: _submission(
            carrier,
            image_refs if carrier == "image" else [],
            semantic_preflight_binding=semantic_preflight_binding,
            scale_source_pool=pool_binding,
            source_pool_evidence_root_ref=pool_evidence_ref,
            source_pool_selection=pool_selections[carrier],
        )
        for carrier in EXECUTION_IDS
    }
    submissions_root = runtime.campaigns_root / ROOT_ID / "submissions"
    for document in submissions.values():
        write_json(submissions_root / f"{document['executionId']}.json", document)
    lane_external = {
        carrier: {
            "executionId": EXECUTION_IDS[carrier],
            "externalInputRefs": list(document["externalInputRefs"]),
            "externalInputsDigest": document["externalInputsDigest"],
        }
        for carrier, document in submissions.items()
    }
    stable: dict[str, object] = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": ROOT_ID,
        "executionMode": "central",
        "scale": "M100",
        "gitBranch": "dev1.0",
        "gitCommitSha": "c" * 40,
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": semantic_preflight_binding,
        "scaleSourcePool": pool_binding,
        "sourcePoolEvidenceRootRef": pool_evidence_ref,
        "laneSourcePoolSelections": pool_selections,
        "laneExternalInputs": lane_external,
        "externalInputsDigest": payload_digest(
            {
                "schema": "quwoquan_data.campaign_external_input_lanes",
                "lanes": lane_external,
            }
        ),
        "submissionDigests": {
            carrier: document["requestDigest"]
            for carrier, document in submissions.items()
        },
        "executionIds": EXECUTION_IDS,
        "frozenAt": "2026-08-05T00:00:00Z",
    }
    plan = {**stable, "planDigest": payload_digest(stable)}
    write_json(runtime.campaigns_root / ROOT_ID / "campaign_plan.json", plan)
    return plan, submissions


def _capsule(
    runtime: CampaignRuntimePaths,
    plan: dict[str, object],
    image_refs: list[dict[str, object]],
) -> SourceCapsule:
    capsule_path = runtime.workspaces_root / "content-addressed-capsules/test"
    lane_payload: dict[str, dict[str, object]] = {}
    for carrier in EXECUTION_IDS:
        refs = image_refs if carrier == "image" else []
        root_ref = f"external-inputs/{carrier}"
        materialize_external_input_bundle(
            capsule_path / root_ref,
            refs,
            acquisition_root=runtime.acquisition_root,
            carrier=carrier,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )
        lane_payload[carrier] = {
            "rootRef": root_ref,
            "externalInputRefs": refs,
            "externalInputsDigest": external_inputs_digest(refs),
        }
    pool_plan = read_json(
        runtime.output_root / str(plan["scaleSourcePool"]["planRef"])
    )
    selected_ids = {
        str(candidate_id)
        for selection in plan["laneSourcePoolSelections"].values()
        for candidate_id in selection["candidateIds"]
    }
    selected_candidates = sorted(
        (
            dict(row)
            for row in pool_plan["candidates"]
            if row["candidateId"] in selected_ids
        ),
        key=lambda row: (str(row["carrier"]), str(row["candidateId"])),
    )
    snapshot_stable = {
        "schema": "quwoquan_data.scale_source_pool_snapshot",
        "planDigest": pool_plan["planDigest"],
        "laneSourcePoolSelections": plan["laneSourcePoolSelections"],
        "selectedCandidates": selected_candidates,
    }
    snapshot_digest = payload_digest(snapshot_stable)
    stable = {
        "schema": "quwoquan_data.content_campaign_source_capsule",
        "format": "source-capsule-v2",
        "gitBranch": str(plan["gitBranch"]),
        "gitCommitSha": "c" * 40,
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "f" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": CATALOG_DIGEST,
        "roots": ["quwoquan_data"],
        "laneExternalInputs": lane_payload,
        "externalInputsDigest": plan["externalInputsDigest"],
        "scaleSourcePool": plan["scaleSourcePool"],
        "sourcePoolSnapshotRootRef": "scale-source-pool",
        "sourcePoolSnapshotDigest": snapshot_digest,
        "laneSourcePoolSelections": plan["laneSourcePoolSelections"],
    }
    write_json(
        capsule_path / "scale-source-pool/plan.json",
        pool_plan,
    )
    write_json(
        capsule_path / "scale-source-pool/selected.json",
        {**snapshot_stable, "snapshotDigest": snapshot_digest},
    )
    capsule_digest = payload_digest(stable)
    write_json(
        capsule_path / ".qwq_campaign_capsule.json",
        {
            **stable,
            "capsuleDigest": capsule_digest,
            "treeDigest": "sha256:" + ("d" * 64),
        },
    )
    return SourceCapsule(
        path=capsule_path,
        ref=capsule_path.relative_to(runtime.output_root).as_posix(),
        capsule_digest=capsule_digest,
        git_branch=str(plan["gitBranch"]),
        commit_sha="c" * 40,
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        execution_bundle_digest="sha256:" + "f" * 64,
        entity_catalog_digest=CATALOG_DIGEST,
        external_inputs_digest=str(plan["externalInputsDigest"]),
        lane_external_inputs=lane_payload,
        roots=("quwoquan_data",),
        read_only=True,
        scale_source_pool=dict(plan["scaleSourcePool"]),
        lane_source_pool_selections={
            carrier: dict(selection)
            for carrier, selection in plan["laneSourcePoolSelections"].items()
        },
        source_pool_snapshot_root_ref="scale-source-pool",
    )


def test_external_inputs_reject_path_escape_and_content_replacement(
    tmp_path: Path,
) -> None:
    acquisition_root, refs = _acquisition(tmp_path)
    with pytest.raises(CampaignExternalInputError, match="PATH_ESCAPE"):
        bind_external_input_refs(
            "image",
            [
                {
                    "kind": "professional_image_acquisition",
                    "manifestRef": "../manifest.json",
                    "receiptRef": refs[0]["receiptRef"],
                }
            ],
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )

    blob = acquisition_root / str(refs[0]["blobRefs"][0]["blobRef"])
    blob.write_bytes(blob.read_bytes() + b"tamper")
    with pytest.raises(
        CampaignExternalInputError, match="DIGEST_DRIFT|digest mismatch"
    ):
        verify_external_input_refs(
            "image",
            refs,
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )


def test_professional_image_input_is_limited_to_homepage_and_image(
    tmp_path: Path,
) -> None:
    acquisition_root, image_refs = _acquisition(tmp_path)
    declaration = {
        "kind": image_refs[0]["kind"],
        "manifestRef": image_refs[0]["manifestRef"],
        "receiptRef": image_refs[0]["receiptRef"],
    }
    homepage_refs = bind_external_input_refs(
        "homepage",
        [declaration],
        acquisition_root=acquisition_root,
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=CATALOG_DIGEST,
    )
    assert homepage_refs[0]["carrier"] == "homepage"
    with pytest.raises(CampaignExternalInputError, match="not admitted for article"):
        bind_external_input_refs(
            "article",
            [declaration],
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )


def test_frozen_professional_images_drive_homepage_and_image_plans_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition_root, image_refs = _acquisition(tmp_path)
    declaration = {
        "kind": image_refs[0]["kind"],
        "manifestRef": image_refs[0]["manifestRef"],
        "receiptRef": image_refs[0]["receiptRef"],
    }
    homepage_refs = bind_external_input_refs(
        "homepage",
        [declaration],
        acquisition_root=acquisition_root,
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=CATALOG_DIGEST,
    )
    bundles = {
        "homepage": tmp_path / "capsule/external-inputs/homepage",
        "image": tmp_path / "capsule/external-inputs/image",
    }
    for carrier, refs in (("homepage", homepage_refs), ("image", image_refs)):
        materialize_external_input_bundle(
            bundles[carrier],
            refs,
            acquisition_root=acquisition_root,
            carrier=carrier,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )

    image_context = _external_context(
        bundles["image"],
        image_refs,
        execution_id=EXECUTION_IDS["image"],
        carrier="image",
    )
    receipt_refs, image_specs = professional_image_context_binding(
        execution_id=EXECUTION_IDS["image"],
        entity_id="九寨沟",
        carrier="image",
        external_input_context=image_context,
    )
    assert receipt_refs == [image_refs[0]["receiptRef"]]
    assert len(image_specs) == 1
    wiki_candidate = {
        "url": "https://upload.wikimedia.org/wiki/fallback.jpg",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Fallback.jpg",
        "platform": "Wikimedia Commons",
        "creator": "Fallback Creator",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Fallback.jpg",
        "caption": "九寨沟 fallback",
        "relevance": "九寨沟 fallback",
        "width": 1600,
        "height": 1000,
    }
    image_plan_dir = tmp_path / "image-plan"
    image_report: dict[str, object] = {"sourceUnavailable": []}
    write_image_lane(
        entity_id="九寨沟",
        entity_aliases=["九寨沟风景名胜区"],
        vertical="travel",
        plan_dir=image_plan_dir,
        force=True,
        report=image_report,
        updated=[],
        prior_image_collections=[],
        prior_image_pool=[],
        openverse=[wiki_candidate],
        commons=[wiki_candidate],
        hint_commons=[],
        wikidata_commons=[],
        wiki_page_images=[wiki_candidate],
        voyage_page_images=[],
        open_license_image_pool=[wiki_candidate],
        homepage_image_urls=set(),
        required_publishable_images=1,
        required_article_bases=1,
        desired_image_works=1,
        hard_image_works=1,
        image_bonus_saturation_count=1,
        image_policy="hard_quota",
        image_strategy="downloaded_source_assets",
        requires_publishable_images=True,
        qid="",
        wiki_title="",
        voyage_title="",
        professional_image_specs=image_specs,
        acquisition_receipt_refs=receipt_refs,
    )
    image_plan = read_json(image_plan_dir / "image_source_plan.json")
    image_payload = image_plan["payload"]
    assert image_plan["acquisitionReceiptRefs"] == receipt_refs
    assert "acquisitionReceiptRefs" not in image_payload
    image_collection = image_payload["collections"][0]
    assert image_collection["platform"] == "Pinterest"
    assert image_collection["authorizationProof"].startswith("https://")
    assert image_collection["rightsStatus"] == "verified"
    assert image_collection["authorizationRequired"] is False
    assert image_collection["distributionDecision"] == "commercial_allowed"
    assert image_collection["rightsIssues"] == []
    assert image_collection["images"][0]["authorizationProof"].startswith("https://")
    assert not any(
        image["url"] == wiki_candidate["url"]
        for collection in image_payload["collections"]
        for image in collection["images"]
    )

    homepage_context = _external_context(
        bundles["homepage"],
        homepage_refs,
        execution_id=EXECUTION_IDS["homepage"],
        carrier="homepage",
    )
    homepage_receipt_refs, homepage_specs = professional_image_context_binding(
        execution_id=EXECUTION_IDS["homepage"],
        entity_id="九寨沟",
        carrier="homepage",
        external_input_context=homepage_context,
    )
    monkeypatch.setattr(
        auto_plan_homepage,
        "_candidate_sources",
        lambda _spec: [
            {
                "source_id": "home_wikipedia",
                "sourceKind": "wikipedia",
                "platform": "维基百科",
                "url": "https://zh.wikipedia.org/wiki/九寨沟",
                "category": "encyclopedia",
                "sourceRole": "primary",
                "matchConfidence": 1.0,
                "discoveryProvider": "mediawiki_exact_title",
                "extractor": "wikipedia_api",
                "policyRevision": "encyclopedia-primary",
            }
        ],
    )
    homepage_plan_dir = tmp_path / "homepage-plan"
    write_homepage_lane(
        HomepageResearchInput(
            execution_id=EXECUTION_IDS["homepage"],
            entity_id="九寨沟",
            entity_aliases=("九寨沟风景名胜区",),
            vertical="travel",
            plan_dir=homepage_plan_dir,
            report={"sourceUnavailable": []},
            updated=[],
            qualified_homepage_source=QualifiedHomepageSource(
                provider=HomepageAuthorityProvider.WIKIPEDIA,
                title="九寨沟",
                url="https://zh.wikipedia.org/wiki/九寨沟",
            ),
            wiki_page_images=(wiki_candidate,),
            prior_image_pool=(),
            voyage_page_images=(),
            commons=(wiki_candidate,),
            hint_commons=(),
            wikidata_commons=(),
            openverse=(wiki_candidate,),
            rejected_source_urls=frozenset(),
            force=True,
            professional_image_specs=tuple(homepage_specs),
            acquisition_receipt_refs=tuple(homepage_receipt_refs),
        )
    )
    homepage_plan = read_json(homepage_plan_dir / "homepage_source_plan.json")
    homepage_payload = homepage_plan["payload"]
    assert homepage_plan["acquisitionReceiptRefs"] == homepage_receipt_refs
    assert "acquisitionReceiptRefs" not in homepage_payload
    homepage_collection = homepage_payload["homepageMediaCollections"][0]
    assert homepage_collection["platform"] == "Pinterest"
    assert homepage_collection["authorizationProof"].startswith("https://")
    assert homepage_collection["rightsStatus"] == "verified"
    assert homepage_collection["rightsIssues"] == []
    assert homepage_collection["images"][0]["url"] == homepage_specs[0]["url"]


def test_request_envelope_freezes_content_addressed_external_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition_root, refs = _acquisition(tmp_path)
    repo = tmp_path / "repo"
    (repo / "quwoquan_data/reference/travel/entities/china").mkdir(parents=True)

    class FrozenSource:
        def to_document(self) -> dict[str, object]:
            return {
                "algorithm": "sha256",
                "digest": SOURCE_DIGEST,
                "inputs": ["quwoquan_data/schema"],
            }

    monkeypatch.setattr(
        campaign_request_envelope,
        "current_source_digest",
        lambda **_kwargs: FrozenSource(),
    )
    monkeypatch.setattr(
        campaign_request_envelope_build,
        "entity_catalog_digest",
        lambda _ref: CATALOG_DIGEST,
    )
    monkeypatch.setattr(
        campaign_request_envelope,
        "_require_stable_source_inputs",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        campaign_request_envelope,
        "_git_branch",
        lambda _repo: "dev1.0",
    )
    monkeypatch.setattr(
        campaign_request_envelope,
        "_git_commit",
        lambda _repo: "c" * 40,
    )
    envelope = campaign_request_envelope.build_envelope(
        quota=1,
        carrier="image",
        region_ref="china",
        repo_root=repo,
        day="20260805",
        external_input_refs=[
            {
                "kind": refs[0]["kind"],
                "manifestRef": refs[0]["manifestRef"],
                "receiptRef": refs[0]["receiptRef"],
            }
        ],
        acquisition_root=acquisition_root,
    )
    assert envelope["sourceRevision"] == SOURCE_REVISION
    assert envelope["externalInputRefs"] == refs
    assert envelope["externalInputsDigest"] == external_inputs_digest(refs)
    path = tmp_path / "image-envelope.json"
    write_json(path, envelope)
    assert campaign_request_envelope.load_campaign_envelope(path) == envelope


def test_fenced_execution_envelope_uses_only_canonical_capsule_and_rejects_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    _, image_refs = _acquisition(tmp_path)
    plan, submissions = _frozen_documents(runtime, image_refs)
    capsule = _capsule(runtime, plan, image_refs)
    execution_root = runtime.output_root / "data/tasks" / EXECUTION_IDS["image"]
    execution_root.mkdir(parents=True)
    workspace = CampaignLaneWorkspace(
        carrier="image",
        capsule=capsule,
        execution_root=execution_root,
    )
    freeze_execution_external_input_envelope(
        runtime=runtime,
        root_execution_id=ROOT_ID,
        plan=plan,
        submission=submissions["image"],
        workspace=workspace,
    )
    video_execution_root = runtime.output_root / "data/tasks" / EXECUTION_IDS["video"]
    video_execution_root.mkdir(parents=True)
    video_workspace = CampaignLaneWorkspace(
        carrier="video",
        capsule=capsule,
        execution_root=video_execution_root,
    )
    freeze_execution_external_input_envelope(
        runtime=runtime,
        root_execution_id=ROOT_ID,
        plan=plan,
        submission=submissions["video"],
        workspace=video_workspace,
    )
    for key in (
        "QWQ_CAMPAIGN_ROOT_EXECUTION_ID",
        "QWQ_CAMPAIGN_CAPSULE_ROOT",
        "QWQ_CAMPAIGN_EXTERNAL_INPUT_ROOT",
        "QWQ_CAMPAIGN_EXTERNAL_INPUT_ENVELOPE",
    ):
        monkeypatch.setenv(key, str(tmp_path / "untrusted-env-value"))
    context = resolve_runtime_external_input_context(
        EXECUTION_IDS["image"],
        "image",
        requested_receipt_refs=[str(image_refs[0]["receiptRef"])],
        requested_kind="professional_image_acquisition",
        runtime_paths=runtime,
    )
    blob_path = context.blob_path(str(image_refs[0]["blobRefs"][0]["contentSha256"]))
    assert blob_path.is_file()
    assert capsule.path in blob_path.parents
    plan_path = tmp_path / "image_source_plan.json"
    write_json(
        plan_path,
        {
            "acquisitionReceiptRefs": [str(image_refs[0]["receiptRef"])],
            "payload": {
                "imageUrls": [
                    {
                        "url": "https://example.invalid/agent-replacement.jpg",
                        "sourceUrl": "https://example.invalid/agent-replacement",
                    }
                ],
            }
        },
    )
    monkeypatch.setattr(
        source_inputs,
        "_source_plan_files",
        lambda *_args, **_kwargs: [("image", plan_path)],
    )
    specs = source_inputs.curated_images_for_entity(
        EXECUTION_IDS["image"],
        "九寨沟",
        "景区",
        research_lane="image",
        external_input_context=context,
    )
    assert len(specs) == 1
    assert Path(specs[0]["url"].removeprefix("file://")) == blob_path
    write_json(plan_path, {"payload": {"acquisitionReceiptRefs": []}})
    with pytest.raises(ValueError, match="canonical top-level field"):
        source_inputs.curated_images_for_entity(
            EXECUTION_IDS["image"],
            "九寨沟",
            "景区",
            research_lane="image",
            external_input_context=context,
        )
    write_json(
        plan_path,
        {"acquisitionReceiptRefs": ["receipts/undeclared.json"]},
    )
    with pytest.raises(CampaignExternalInputError, match="UNDECLARED"):
        source_inputs.curated_images_for_entity(
            EXECUTION_IDS["image"],
            "九寨沟",
            "景区",
            research_lane="image",
            external_input_context=context,
        )

    with pytest.raises(CampaignExternalInputError, match="UNDECLARED"):
        resolve_runtime_external_input_context(
            EXECUTION_IDS["video"],
            "video",
            requested_receipt_refs=[str(image_refs[0]["receiptRef"])],
            requested_kind="professional_video_acquisition",
            runtime_paths=runtime,
        )

    blob_path.write_bytes(blob_path.read_bytes() + b"runtime-replacement")
    with pytest.raises(
        CampaignExternalInputError, match="DIGEST_DRIFT|digest mismatch"
    ):
        resolve_runtime_external_input_context(
            EXECUTION_IDS["image"],
            "image",
            runtime_paths=runtime,
        )


def test_same_execution_cannot_replace_external_inputs_without_new_retry(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    _, image_refs = _acquisition(tmp_path)
    plan, submissions = _frozen_documents(runtime, image_refs)
    capsule = _capsule(runtime, plan, image_refs)
    execution_root = runtime.output_root / "data/tasks" / EXECUTION_IDS["image"]
    execution_root.mkdir(parents=True)
    workspace = CampaignLaneWorkspace("image", capsule, execution_root)
    freeze_execution_external_input_envelope(
        runtime=runtime,
        root_execution_id=ROOT_ID,
        plan=plan,
        submission=submissions["image"],
        workspace=workspace,
    )
    empty_digest = external_inputs_digest([])
    changed_submission = {
        **submissions["image"],
        "externalInputRefs": [],
        "externalInputsDigest": empty_digest,
    }
    changed_lane = {
        "executionId": EXECUTION_IDS["image"],
        "externalInputRefs": [],
        "externalInputsDigest": empty_digest,
    }
    changed_plan = {
        **plan,
        "laneExternalInputs": {
            **plan["laneExternalInputs"],
            "image": changed_lane,
        },
    }
    changed_capsule = SourceCapsule(
        path=capsule.path,
        ref=capsule.ref,
        capsule_digest="sha256:" + ("e" * 64),
        git_branch=capsule.git_branch,
        commit_sha=capsule.commit_sha,
        source_revision=capsule.source_revision,
        source_digest=capsule.source_digest,
        execution_bundle_digest=capsule.execution_bundle_digest,
        entity_catalog_digest=capsule.entity_catalog_digest,
        external_inputs_digest=capsule.external_inputs_digest,
        lane_external_inputs={
            **capsule.lane_external_inputs,
            "image": {
                "rootRef": "external-inputs/image",
                "externalInputRefs": [],
                "externalInputsDigest": empty_digest,
            },
        },
        roots=capsule.roots,
        read_only=True,
    )
    changed_workspace = CampaignLaneWorkspace("image", changed_capsule, execution_root)
    with pytest.raises(
        CampaignExternalInputError, match="new execution sequence with retryOf"
    ):
        freeze_execution_external_input_envelope(
            runtime=runtime,
            root_execution_id=ROOT_ID,
            plan=changed_plan,
            submission=changed_submission,
            workspace=changed_workspace,
        )

    request = RuntimeExecutionRequest(
        family_ref="content/travel/image/image",
        region_ref="china",
        selector=TargetSelector.PRIORITY,
        count=100,
        quota=100,
        required_workers=1,
        partition_count=16,
        capacity_plan_digest="sha256:" + "6" * 64,
        topic=None,
        source_providers=(),
        target_names=(),
    )
    with pytest.raises(ValueError, match="retryOf must reference a different"):
        write_submission(
            root_execution_id=ROOT_ID,
            execution_id=EXECUTION_IDS["image"],
            request=request,
            retry_of=EXECUTION_IDS["image"],
            repo_root=tmp_path,
            root=runtime.campaigns_root,
        )
