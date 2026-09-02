"""video lane frozen candidate source-unit materialization."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import ops_governance as og
from core.io import read_json
from core.paths import execution_post_object_dir

from content.source.media_source_admission import MediaSourceAdmissionQuery
from content.source.research.scale_source_pool_evidence_path import resolve_evidence_file
from content.source.research.scale_source_pool_runtime_blockers import _fail
from content.source.sourced_video_unit import write_admitted_sourced_video_unit


def _derive_audio_rights(
    *,
    source_attribution: Mapping[str, Any] | None,
    plan_video_spec: Mapping[str, Any],
) -> tuple[str, str | None]:
    if source_attribution is not None:
        status = str(source_attribution["audioRightsStatus"])
        proof_url = str(plan_video_spec.get("authorizationProofUrl") or "")
        return status, (proof_url or None) if status == "licensed" else None

    probe = plan_video_spec["mediaProbe"]
    if not isinstance(probe, Mapping):
        raise ValueError("video planVideoSpec lacks mediaProbe")
    has_audio = probe["hasAudio"]
    if has_audio is False:
        return "no_audio", None
    if has_audio is not True:
        raise ValueError("video planVideoSpec mediaProbe hasAudio is invalid")
    proof_url = str(plan_video_spec.get("authorizationProofUrl") or "")
    if (
        plan_video_spec["commercialAuthorizationStatus"] == "verified"
        and proof_url.startswith("https://")
    ):
        return "licensed", proof_url
    return "unverified", None


def _materialize_frozen_video_source_unit(
    *, execution_id: str, object_ref: str, entity_id: str,
    entity_type: str, row: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_root = row.get("sourcePoolEvidenceRoot")
    if not isinstance(evidence_root, Path):
        raise _fail("selected video candidate lacks frozen evidence root")
    try:
        result = MediaSourceAdmissionQuery(evidence_root).require_accepted(str(row["sourceAdmissionRef"]))
        admission = result["receipt"]
        snapshot = admission["assetSnapshot"]
        snapshot_attribution = snapshot.get("sourceAttribution")
        projected_attribution = row.get("sourceAttribution")
        if (
            snapshot_attribution is not None
            and not isinstance(snapshot_attribution, Mapping)
        ):
            raise ValueError("video source admission sourceAttribution is invalid")
        if (
            projected_attribution is not None
            and not isinstance(projected_attribution, Mapping)
        ):
            raise ValueError("video source projection sourceAttribution is invalid")
        has_frozen_attribution = (
            snapshot_attribution is not None and projected_attribution is not None
        )
        if (
            result["receiptDigest"] != row["sourceAdmissionDigest"]
            or admission["assetKind"] != "video"
            or admission["objectRef"] != row["objectRef"]
            or snapshot["contentSha256"] != row["contentSha256"]
            or snapshot["entityId"] != entity_id
            or (
                has_frozen_attribution
                and snapshot_attribution != projected_attribution
            )
        ):
            raise ValueError("video source admission projection drift")
        acquisition = [binding for binding in admission["evidenceBindings"] if binding.get("role") == "acquisition"]
        if len(acquisition) != 1:
            raise ValueError("video source admission lacks one acquisition binding")
        evidence = read_json(resolve_evidence_file(evidence_root, acquisition[0]["ref"], label="video acquisition evidence"))
        assets = [asset for asset in evidence.get("assets") or [] if isinstance(asset, Mapping) and asset.get("assetId") == snapshot["assetId"]] if isinstance(evidence, Mapping) else []
        if len(assets) != 1 or not isinstance(assets[0].get("planVideoSpec"), Mapping):
            raise ValueError("video candidate lacks one frozen planVideoSpec")
        asset = assets[0]
        spec = dict(asset["planVideoSpec"])
        cas_path = resolve_evidence_file(evidence_root, snapshot["assetRef"], label="video acquisition CAS asset")
        if asset.get("contentSha256") != row["contentSha256"]:
            raise ValueError("video acquisition content identity drift")
        audio_rights_status, audio_authorization_proof_url = _derive_audio_rights(
            source_attribution=(
                snapshot_attribution if has_frozen_attribution else None
            ),
            plan_video_spec=spec,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise _fail(f"frozen video acquisition is invalid: {exc}") from exc

    parts = Path(object_ref).parts
    if len(parts) < 3 or parts[:2] != ("posts", "video"):
        raise _fail(f"video target ref is non-canonical: {object_ref}")
    suffix = parts[2:]
    angle, title, sequence = (
        ("/".join(suffix[:-2]), suffix[-2], int(suffix[-1]))
        if len(suffix) >= 3 and suffix[-1].isdigit()
        else (suffix[0], suffix[1], 1)
        if len(suffix) == 2
        else ("体验", suffix[0], 1)
    )
    object_dir = execution_post_object_dir(execution_id, "video", angle, title, sequence)
    frozen_id = og.source_unit_id(canonical_url=str(spec["sourcePostUrl"]), entity_name=entity_id, source_kind=str(spec["sourceKind"]))
    evidence_path = write_admitted_sourced_video_unit(
        execution_id=execution_id, object_ref=object_ref,
        source_unit={
            "sourceId": str(spec["sourceId"]), "sourceKind": str(spec["sourceKind"]),
            "ordinal": int(spec.get("ordinal") or 1), "title": str(spec["title"]),
            "relevance": str(spec["relevance"]), "rightsStatus": str(spec.get("rightsStatus") or "unverified"),
            "rightsIssues": list(spec.get("rightsIssues") or []),
            "professionalAcquisitionReceiptRef": str(spec["professionalAcquisitionReceiptRef"]),
            "professionalAssetId": str(spec["professionalAssetId"]),
            "professionalContentSha256": str(spec["professionalContentSha256"]),
            "premiumPlayableEligible": spec.get("premiumPlayableEligible") is True,
            "mediaProbe": spec.get("mediaProbe"), "popularitySignals": spec.get("popularitySignals"),
        },
        source_video_path=cas_path, original_creator_name=str(spec["originalCreatorName"]),
        platform=str(spec["platform"]), source_post_url=str(spec["sourcePostUrl"]),
        original_asset_url=str(spec["originalAssetUrl"]), attribution_text=str(spec["attributionText"]),
        rights_basis=str(spec["rightsBasis"]), commercial_authorization_status=str(spec["commercialAuthorizationStatus"]),
        distribution_decision=str(spec["distributionDecision"]),
        authorization_proof_url=str(spec.get("authorizationProofUrl") or "") or None,
        terms_url=str(spec.get("termsUrl") or "") or None,
        audio_rights_status=audio_rights_status,
        audio_authorization_proof_url=audio_authorization_proof_url,
        model_release_status=str(spec["modelReleaseStatus"]), property_release_status=str(spec["propertyReleaseStatus"]),
        takedown_policy=str(spec["takedownPolicy"]), object_dir=object_dir, frozen_source_unit_id=frozen_id,
    )
    value = read_json(evidence_path.parent / "meta.json")
    if not isinstance(value, dict):
        raise _fail("materialized video source unit lacks canonical meta")
    return value


__all__ = ["_derive_audio_rights", "_materialize_frozen_video_source_unit"]
