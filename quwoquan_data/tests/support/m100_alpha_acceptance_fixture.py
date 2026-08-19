"""One governed M100 Research milestone release, its promotion, and its lineage.

The M100 cohort is environment neutral: the same immutable manifest is what Alpha,
Beta, Gamma and Prod each activate in turn, so nothing here names an environment.
Per-carrier counts come from the governed distribution policy rather than from
literals, because the milestone is defined as exactly the frozen target — a copied
number would let the fixture and the policy disagree about what M100 means.

Every helper either writes a complete payload or raises. Nothing is filled in on a
best-effort basis: a partially written release would let a test pass against a
closure the release itself cannot prove.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.object_source_identity import (
    source_identity_digest,
    source_identity_set,
)
from content.release.canonical.research_scale_promotion import (
    write_research_scale_promotion,
)
from content.release.canonical.research_scale_promotion_release import CARRIERS
from core.source_digest import SourceDefinitionSnapshot, content_source_revision
from governance.coverage.distribution import load_content_distribution_policy

POST_CARRIERS = ("article", "image", "video")
SOURCE_DIGEST = "sha256:" + "a" * 64
ENTITY_CATALOG_DIGEST = "sha256:" + "d" * 64
SOURCE_REVISION = content_source_revision(
    source_digest=SOURCE_DIGEST,
    entity_catalog_digest=ENTITY_CATALOG_DIGEST,
)


def m100_targets() -> dict[str, int]:
    """The governed per-carrier M100 targets, in carrier order."""

    policy = load_content_distribution_policy()
    return {carrier: policy.scale_target("M100", carrier) for carrier in CARRIERS}


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _post_ref(carrier: str, index: int) -> str:
    return f"{carrier}/work-{index:03d}/1"


def _image_assets(count: int) -> list[dict[str, Any]]:
    """Rights-pending professional image assets, one per image object.

    Research admission accepts unverified rights, and the source-mix projection
    needs a real provider per asset, so each row names one.
    """

    providers = ["Pinterest", "图虫", "Wikimedia Commons"]
    return [
        {
            "assetId": f"image-asset-{index:03d}",
            "objectRef": f"posts/{_post_ref('image', index)}",
            "acquisitionStatus": "acquired",
            "rightsStatus": "unverified",
            "authorizationRequired": True,
            "distributionDecision": "research_allowed",
            "sourceUrl": f"https://media.example.test/original/{index:03d}.jpg",
            "platform": providers[index % len(providers)],
            "creator": f"creator-{index:03d}",
            "capturedAt": "2026-08-05T00:00:00Z",
            "contentSha256": "sha256:" + f"{index:064x}",
            "license": "authorization_pending",
            "termsUrl": "https://media.example.test/terms",
            "authorizationProof": "",
            "rightsIssues": ["creator_authorization_pending"],
            "generated": False,
        }
        for index in range(count)
    ]


def write_m100_milestone_release(
    output_root: Path,
    *,
    release_id: str = "research-m100",
    counts: Mapping[str, int] | None = None,
    header_overrides: Mapping[str, Any] | None = None,
    header_removals: Sequence[str] = (),
    admission_overrides: Mapping[str, Any] | None = None,
) -> Path:
    """Write an environment-neutral M100 Research release payload.

    ``counts`` defaults to the governed M100 targets. Passing a different count for
    one carrier is how a test builds a cohort that is short of, or beyond, the
    milestone; the payload stays internally consistent either way, so the only
    thing under test is the attainment rule rather than an unrelated closure defect.
    """

    accepted = dict(counts or m100_targets())
    if set(accepted) != set(CARRIERS):
        raise ValueError(f"M100 counts must cover exactly {CARRIERS}")
    if accepted["image"] < 1:
        raise ValueError("a research cohort needs at least one rights-pending asset")
    release = output_root / "data/releases" / release_id
    execution_ids = [f"{carrier}-execution" for carrier in CARRIERS]
    expanded_identities = [
        {
            "executionId": execution_id,
            "sourceRevision": SOURCE_REVISION,
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
        }
        for execution_id in execution_ids
    ]
    source_identities, source_identity_set_digest = source_identity_set(
        expanded_identities
    )
    identity_digest = source_identity_digest(expanded_identities[0])
    contents = [
        {
            "contentId": f"content-{carrier}-{index:03d}",
            "version": 1,
            "postRef": _post_ref(carrier, index),
            "executionId": f"{carrier}-execution",
            "sourceIdentityDigest": identity_digest,
        }
        for carrier in POST_CARRIERS
        for index in range(accepted[carrier])
    ]
    post_counts = {carrier: accepted[carrier] for carrier in POST_CARRIERS}
    shared_lifecycle = {
        "containsUnverifiedAssets": True,
        "rightsStatusCounts": {
            "verified": 0,
            "unverified": accepted["image"],
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": ["image-asset-000"],
        "researchAcceptedCount": sum(accepted.values()),
        "commercialAcceptedCount": 0,
    }
    header: dict[str, Any] = {
        "schema": "quwoquan_data.release",
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "releaseKind": "content",
        "releaseClass": "research",
        "productLifecycleState": "research",
        **shared_lifecycle,
        "canonicalMerkle": "sha256:" + "2" * 64,
        "executionIds": execution_ids,
        "sourceDigests": [SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()],
        "selectionScope": "milestone",
        "milestone": "M100",
        "milestoneTargets": m100_targets(),
        "releaseMode": "research",
        "poolDigest": "sha256:" + "3" * 64,
        "counts": {**post_counts, "total": sum(post_counts.values())},
        "contents": contents,
        "authors": [],
        "buildResult": "completed",
        "sourceIdentities": source_identities,
        "sourceIdentitySetDigest": source_identity_set_digest,
    }
    header.update(header_overrides or {})
    for field in header_removals:
        del header[field]
    _write(release / "payload/release.json", header)
    _write(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": {
                "entities": [
                    f"entity/work-{index:03d}" for index in range(accepted["homepage"])
                ],
                "posts": [str(item["postRef"]) for item in contents],
                "creators": [],
                "tags": [],
            },
        },
    )
    illustrated = accepted["article"] * 9 // 10
    admission: dict[str, Any] = {
        "schema": "quwoquan_data.release_asset_admission",
        "releaseId": release_id,
        "releaseClass": "research",
        "productLifecycleState": "research",
        **shared_lifecycle,
        "carrierCounts": [
            {
                "carrier": carrier,
                "researchAcceptedCount": accepted[carrier],
                "objectCount": accepted[carrier],
                "assetCount": accepted["image"] if carrier == "image" else 0,
                "commercialAcceptedCount": 0,
            }
            for carrier in CARRIERS
        ],
        "articleMediaCoverage": {
            "articleCount": accepted["article"],
            "illustratedCount": illustrated,
            "textOnlyCount": accepted["article"] - illustrated,
            "illustratedRate": illustrated / accepted["article"],
            "textOnlyRate": (accepted["article"] - illustrated) / accepted["article"],
        },
        "sourceAssetCounts": [],
        "assets": _image_assets(accepted["image"]),
    }
    admission.update(admission_overrides or {})
    _write(release / "payload/asset_admission.json", admission)
    return release


def write_m100_promotion(
    output_root: Path,
    *,
    release_id: str = "research-m100",
    promotion_id: str = "promotion-m100",
) -> tuple[dict[str, Any], Path]:
    """Promote an already written M100 milestone release."""

    return write_research_scale_promotion(
        release_id=release_id,
        promotion_id=promotion_id,
        target_scale="M100",
        release_root=output_root / "data/releases",
        output_root=output_root,
    )


def m100_predecessor_reference(
    promotion_path: Path,
    *,
    output_root: Path,
) -> dict[str, Any]:
    """The exact-byte M100 lineage an M1000 promotion has to prove it consumed."""

    resolved = promotion_path.resolve()
    document = json.loads(resolved.read_text(encoding="utf-8"))
    return {
        "promotionId": str(document["promotionId"]),
        "releaseId": str(document["releaseId"]),
        "manifestDigest": str(document["manifestDigest"]),
        "targetScale": "M100",
        "receiptRef": resolved.relative_to(output_root.resolve()).as_posix(),
        "receiptDigest": "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def _claim_digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def unproven_acceptance_binding(
    *,
    promotion_id: str = "promotion-m100",
    release_id: str = "research-m100",
    promotion_receipt_ref: str,
    readiness_receipt_ref: str,
    app_uat_receipt_ref: str,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """A shape-complete acceptance binding whose digests prove nothing.

    Every digest is derived from the label of the thing it claims, so the document
    is internally coherent and yet stands for no receipt that exists. Tests use it
    to show the validator re-reads the referenced bytes rather than trusting a
    frozen claim; it is deliberately unusable as a stand-in for real evidence.
    """

    binding: dict[str, Any] = {
        "schema": "quwoquan_data.m100_alpha_acceptance_binding",
        "promotionId": promotion_id,
        "promotionReceiptRef": promotion_receipt_ref,
        "promotionReceiptDigest": _claim_digest("promotion receipt"),
        "releaseId": release_id,
        "manifestDigest": _claim_digest("manifest"),
        "appUatEnvelopeDigest": _claim_digest("app uat envelope"),
        "activationEnvelopeDigest": _claim_digest("activation envelope"),
        "exactCounts": {
            **m100_targets(),
            "posts": sum(
                m100_targets()[carrier] for carrier in POST_CARRIERS
            ),
        },
        "readinessReceiptRef": readiness_receipt_ref,
        "readinessReceiptFileSha256": _claim_digest("readiness bytes"),
        "readinessReceiptDigest": _claim_digest("readiness document"),
        "appUatReceiptRef": app_uat_receipt_ref,
        "appUatReceiptFileSha256": _claim_digest("app uat bytes"),
        "appUatReceiptDigest": _claim_digest("app uat document"),
        "appUatPlanDigest": _claim_digest("app uat plan"),
        "executedSampleCount": 100,
        "sampleExecutionDigest": _claim_digest("sample execution"),
    }
    binding.update(overrides or {})
    return binding
