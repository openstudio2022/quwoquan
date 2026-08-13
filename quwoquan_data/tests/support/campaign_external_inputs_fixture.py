# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""campaign external inputs 测试的共享常量、采集治理 fixture 与素材构造。

autouse fixture `_governed_acquisition_handoff` 需要在各测试模块中显式 import
以保持原有的按模块 autouse 语义。
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from content.execution.campaign.external_inputs import (
    bind_external_input_refs,
    content_source_revision,
)
from content.source.professional_image_acquisition import acquire_professional_images
from content.source.professional_image_discovery import (
    create_professional_image_discovery_plan,
)
from core.io import write_json
from PIL import Image

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
