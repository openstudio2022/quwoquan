"""Typed admission evidence for one externally sourced video asset."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from core.media_source_provenance import DerivedModification
from core.source_attribution import derived_modifications_value


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


_ADMISSION_DECISIONS = {
    "commercial_release": "commercial_allowed",
    "research_release": "research_allowed",
    "risk_accepted_attribution_only": "research_allowed",
}


_DECISION_ADMISSIONS = {
    "commercial_allowed": "commercial_release",
    "research_allowed": "research_release",
}


def distribution_decision_for_admission(publication_admission: str) -> str:
    """Project the governed asset-level decision from a publication admission."""
    return _ADMISSION_DECISIONS.get(publication_admission, "")


def publication_admission_for_decision(distribution_decision: str) -> str:
    """Project the release-side admission from a governed distribution decision."""
    return _DECISION_ADMISSIONS.get(distribution_decision, "")


@dataclass(frozen=True, slots=True)
class SourcedVideoEvidence:
    asset_ref: str
    source_ref: str
    rights_ref: str
    media_probe_ref: str
    watermark_evidence_ref: str
    audio_rights_evidence_ref: str
    sha256: str
    is_original: bool
    original_creator_name: str
    platform: str
    source_post_url: str
    original_asset_url: str
    attribution_text: str
    rights_basis: str
    commercial_authorization_status: str
    publication_admission: str
    watermark_status: str
    audio_rights_status: str
    model_release_status: str
    property_release_status: str
    collected_at: str
    takedown_policy: str
    direct_download: bool
    access_control_bypassed: bool
    drm_detected: bool
    original_creator_id: str | None = None
    original_creator_profile_url: str | None = None
    authorization_proof_url: str | None = None
    terms_url: str | None = None
    risk_acceptance_id: str | None = None
    distribution_decision: str = ""

    @property
    def effective_distribution_decision(self) -> str:
        """Resolve the asset decision for publication-admission payloads."""
        return self.distribution_decision or distribution_decision_for_admission(
            self.publication_admission
        )

    @property
    def effective_publication_admission(self) -> str:
        """Resolve the release-side admission for decision-only payloads."""
        return self.publication_admission or publication_admission_for_decision(
            self.distribution_decision
        )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
    ) -> tuple["SourcedVideoEvidence", tuple[str, ...]]:
        evidence = cls(
            asset_ref=_text(payload.get("assetRef")),
            source_ref=_text(payload.get("sourceRef")),
            rights_ref=_text(payload.get("rightsRef")),
            media_probe_ref=_text(payload.get("mediaProbeRef")),
            watermark_evidence_ref=_text(payload.get("watermarkEvidenceRef")),
            audio_rights_evidence_ref=_text(
                payload.get("audioRightsEvidenceRef")
            ),
            sha256=_text(payload.get("sha256")),
            is_original=payload.get("isOriginal") is True,
            original_creator_id=_optional_text(payload.get("originalCreatorId")),
            original_creator_name=_text(payload.get("originalCreatorName")),
            original_creator_profile_url=_optional_text(
                payload.get("originalCreatorProfileUrl")
            ),
            platform=_text(payload.get("platform")),
            source_post_url=_text(payload.get("sourcePostUrl")),
            original_asset_url=_text(payload.get("originalAssetUrl")),
            attribution_text=_text(payload.get("attributionText")),
            rights_basis=_text(payload.get("rightsBasis")),
            commercial_authorization_status=_text(
                payload.get("commercialAuthorizationStatus")
            ),
            publication_admission=_text(payload.get("publicationAdmission")),
            distribution_decision=_text(payload.get("distributionDecision")),
            authorization_proof_url=_optional_text(
                payload.get("authorizationProofUrl")
            ),
            terms_url=_optional_text(payload.get("termsUrl")),
            risk_acceptance_id=_optional_text(payload.get("riskAcceptanceId")),
            watermark_status=_text(payload.get("watermarkStatus")),
            audio_rights_status=_text(payload.get("audioRightsStatus")),
            model_release_status=_text(payload.get("modelReleaseStatus")),
            property_release_status=_text(payload.get("propertyReleaseStatus")),
            collected_at=_text(payload.get("collectedAt")),
            takedown_policy=_text(payload.get("takedownPolicy")),
            direct_download=payload.get("directDownload") is True,
            access_control_bypassed=payload.get("accessControlBypassed") is True,
            drm_detected=payload.get("drmDetected") is True,
        )
        return evidence, evidence.admission_issues()

    def admission_issues(self) -> tuple[str, ...]:
        required = {
            "assetRef": self.asset_ref,
            "sourceRef": self.source_ref,
            "rightsRef": self.rights_ref,
            "mediaProbeRef": self.media_probe_ref,
            "watermarkEvidenceRef": self.watermark_evidence_ref,
            "audioRightsEvidenceRef": self.audio_rights_evidence_ref,
            "sha256": self.sha256,
            "originalCreatorName": self.original_creator_name,
            "platform": self.platform,
            "sourcePostUrl": self.source_post_url,
            "originalAssetUrl": self.original_asset_url,
            "attributionText": self.attribution_text,
            "rightsBasis": self.rights_basis,
            "commercialAuthorizationStatus": self.commercial_authorization_status,
            "watermarkStatus": self.watermark_status,
            "audioRightsStatus": self.audio_rights_status,
            "modelReleaseStatus": self.model_release_status,
            "propertyReleaseStatus": self.property_release_status,
            "collectedAt": self.collected_at,
            "takedownPolicy": self.takedown_policy,
        }
        issues = [
            f"sourceVideo missing {field}"
            for field, value in required.items()
            if not value
        ]
        if not self.direct_download:
            issues.append("sourceVideo must be directly downloadable")
        if self.access_control_bypassed:
            issues.append("sourceVideo must not bypass access control")
        if self.drm_detected:
            issues.append("sourceVideo must not contain DRM")
        if self.watermark_status != "absent":
            issues.append("sourceVideo watermarkStatus must be absent")
        allowed_audio = {
            "licensed",
            "original_authorized",
            "replaced_with_licensed_track",
            "no_audio",
            "unverified",
        }
        if self.audio_rights_status not in allowed_audio:
            issues.append("sourceVideo audioRightsStatus is not publishable")
        if self.commercial_authorization_status not in {"verified", "unverified"}:
            issues.append(
                "sourceVideo commercialAuthorizationStatus is not publishable"
            )
        allowed_admission = {
            "research_release",
            "commercial_release",
            "risk_accepted_attribution_only",
        }
        decision = self.effective_distribution_decision
        if self.distribution_decision:
            if self.distribution_decision not in {
                "research_allowed",
                "commercial_allowed",
            }:
                issues.append("sourceVideo distributionDecision is not publishable")
        elif not self.publication_admission:
            issues.append("sourceVideo missing distributionDecision")
        elif self.publication_admission not in allowed_admission:
            issues.append("sourceVideo publicationAdmission is not publishable")
        if (
            self.commercial_authorization_status == "unverified"
            and decision != "research_allowed"
        ):
            issues.append(
                "sourceVideo unverified authorization requires research_allowed"
            )
        if (
            self.publication_admission == "risk_accepted_attribution_only"
            and not self.risk_acceptance_id
        ):
            issues.append("sourceVideo riskAcceptanceId is required")
        if decision == "commercial_allowed" and (
            self.commercial_authorization_status != "verified"
            or not str(self.authorization_proof_url or "").startswith("https://")
            or not str(self.terms_url or "").startswith("https://")
        ):
            issues.append(
                "sourceVideo commercial_allowed requires verified HTTPS authorization and terms proof"
            )
        if (
            self.audio_rights_status == "unverified"
            and self.effective_publication_admission != "research_release"
        ):
            issues.append(
                "sourceVideo unverified audio is restricted to research_release"
            )
        return tuple(issues)

    def attribution_dict(self) -> dict[str, object]:
        return {
            "isOriginal": self.is_original,
            "originalCreatorId": self.original_creator_id,
            "originalCreatorName": self.original_creator_name,
            "originalCreatorProfileUrl": self.original_creator_profile_url,
            "platform": self.platform,
            "sourcePostUrl": self.source_post_url,
            "originalAssetUrl": self.original_asset_url,
            "attributionText": self.attribution_text,
            "rightsBasis": self.rights_basis,
            "commercialAuthorizationStatus": self.commercial_authorization_status,
            "publicationAdmission": self.effective_publication_admission,
            "distributionDecision": self.effective_distribution_decision,
            "authorizationProofUrl": self.authorization_proof_url,
            "termsUrl": self.terms_url,
            "riskAcceptanceId": self.risk_acceptance_id,
            "watermarkStatus": self.watermark_status,
            "audioRightsStatus": self.audio_rights_status,
            "modelReleaseStatus": self.model_release_status,
            "propertyReleaseStatus": self.property_release_status,
            "collectedAt": self.collected_at,
            "takedownPolicy": self.takedown_policy,
        }

    def post_attribution_dict(
        self,
        *,
        derived_modifications: Iterable[DerivedModification],
    ) -> dict[str, object]:
        """Project attribution for a post manifest, which carries no asset decision.

        衍生修改由调用方按本次交付真实做过的操作传入，并只在这里物化一次。
        ``attribution_dict`` 描述的是未经修改的原始来源，交付副本的修改事实不能
        与它共用一个取值，否则「原样收到」与「转码后发布」在证据上无法区分。
        """
        return {
            field: value
            for field, value in self.attribution_dict().items()
            if field != "distributionDecision"
        } | {
            "derivedModifications": derived_modifications_value(derived_modifications)
        }

    def author_prompt_dict(self) -> dict[str, object]:
        """Expose creative facts without prompt-secret false-positive field names."""
        return {
            "assetRef": self.asset_ref,
            "sourceRef": self.source_ref,
            "originalCreatorName": self.original_creator_name,
            "platform": self.platform,
            "sourcePostUrl": self.source_post_url,
            "attributionText": self.attribution_text,
            "rightsBasis": self.rights_basis,
            "termsUrl": self.terms_url,
            "watermarkStatus": self.watermark_status,
            "audioRightsStatus": self.audio_rights_status,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "assetRef": self.asset_ref,
            "sourceRef": self.source_ref,
            "rightsRef": self.rights_ref,
            "mediaProbeRef": self.media_probe_ref,
            "watermarkEvidenceRef": self.watermark_evidence_ref,
            "audioRightsEvidenceRef": self.audio_rights_evidence_ref,
            "sha256": self.sha256,
            **self.attribution_dict(),
            "directDownload": self.direct_download,
            "accessControlBypassed": self.access_control_bypassed,
            "drmDetected": self.drm_detected,
        }


@dataclass(frozen=True, slots=True)
class SourcedVideoAsset:
    path: Path
    evidence: SourcedVideoEvidence


__all__ = ["SourcedVideoAsset", "SourcedVideoEvidence"]
