"""记录资产真实权利事实；取得媒体不代表商用授权。

`DistributionDecision` 是 canonical 字节中的逐资产记录，不选择 release 类别。
保持冻结的 research/commercial 权利词汇；取得成功不等于授权，合法限制不阻断发布。
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from core.schema import assert_valid

POLICY_PATH = (
    Path(__file__).resolve().parents[3]
    / "control_plane/_shared/content_distribution.policy.yaml"
)


class AcquisitionStatus(StrEnum):
    ACQUIRED = "acquired"
    FAILED = "failed"
    BLOCKED = "blocked"


class RightsStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class DistributionDecision(StrEnum):
    RESEARCH_ALLOWED = "research_allowed"
    COMMERCIAL_ALLOWED = "commercial_allowed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ContentDistributionPolicy:
    policy_id: str
    image_generation_allowed: bool
    video_generation_allowed: bool
    illustrated_rate_target: float
    text_only_rate_target: float
    m1_targets: tuple[tuple[str, int], ...]
    m10_targets: tuple[tuple[str, int], ...]
    m100_targets: tuple[tuple[str, int], ...]
    m1000_targets: tuple[tuple[str, int], ...]
    m10000_targets: tuple[tuple[str, int], ...]
    require_m100_promotion_before_m1000: bool
    require_m1000_promotion_before_m10000: bool
    milestone_attainment_required: bool
    attainment_counting_mode: str
    image_provider_priority: tuple[str, ...]
    video_popularity_signals: tuple[str, ...]
    video_popularity_statistical: bool
    video_popularity_non_blocking: bool
    # 采集代码无法核实、只能按政策统一申明的资产级记录常量；采集与投影只搬运。
    asset_record_defaults: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.image_provider_priority or self.image_provider_priority[0] != "pinterest":
            raise ValueError("source image provider priority must start with pinterest")
        if self.image_generation_allowed or self.video_generation_allowed:
            raise ValueError("governed image/video generation must remain disabled")
        if (
            self.require_m100_promotion_before_m1000
            or self.require_m1000_promotion_before_m10000
            or not self.milestone_attainment_required
        ):
            raise ValueError(
                "scale targets remain measurable without predecessor promotion gates"
            )
        if self.attainment_counting_mode != "cumulative_unique_finalized_objects":
            raise ValueError("milestone attainment must count cumulative unique finalized objects")
        if not self.video_popularity_non_blocking or not self.video_popularity_statistical:
            raise ValueError("video popularity must remain non-blocking statistics")
        target_rows = (
            dict(self.m1_targets),
            dict(self.m10_targets),
            dict(self.m100_targets),
            dict(self.m1000_targets),
            dict(self.m10000_targets),
        )
        for carrier in ("homepage", "article", "image", "video"):
            if not (
                target_rows[0][carrier]
                < target_rows[1][carrier]
                < target_rows[2][carrier]
                < target_rows[3][carrier]
                < target_rows[4][carrier]
            ):
                raise ValueError(f"scale targets must increase monotonically: {carrier}")

    def milestone_targets(self) -> dict[str, dict[str, int]]:
        """Per-carrier targets for every governed milestone.

        This is the only place the milestone numbers exist. Callers that need a
        milestone table read it from here rather than restating the constants,
        so raising a milestone stays a control-plane edit.
        """
        return {
            "M1": dict(self.m1_targets),
            "M10": dict(self.m10_targets),
            "M100": dict(self.m100_targets),
            "M1000": dict(self.m1000_targets),
            "M10000": dict(self.m10000_targets),
        }

    def governed_scales(self) -> tuple[str, ...]:
        return tuple(self.milestone_targets())

    def scale_target(self, scale: str, carrier: str) -> int:
        targets = self.milestone_targets().get(scale)
        if targets is None:
            raise ValueError(f"unsupported governed scale: {scale}")
        if carrier not in targets:
            raise ValueError(f"unsupported scale carrier: {carrier}")
        return targets[carrier]


def load_content_distribution_policy(
    *, policy_path: Path = POLICY_PATH
) -> ContentDistributionPolicy:
    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"content distribution policy is unreadable: {policy_path}") from exc
    if not isinstance(raw, dict):
        raise TypeError("content distribution policy must be an object")
    assert_valid(
        raw,
        "governance",
        "content_distribution_policy",
        label="content_distribution_policy",
    )
    acquisition = raw["acquisition"]
    if any(bool(value) for value in acquisition.values()):
        raise ValueError("content acquisition bypass controls must remain disabled")
    media_generation = raw["mediaGeneration"]
    source_discovery = raw["sourceDiscovery"]
    article_media = raw["articleMedia"]
    scale_milestones = raw["scaleMilestones"]
    video_popularity = source_discovery["videoPopularity"]
    return ContentDistributionPolicy(
        policy_id=str(raw["policyId"]),
        image_generation_allowed=bool(media_generation["imageAllowed"]),
        video_generation_allowed=bool(media_generation["videoAllowed"]),
        illustrated_rate_target=float(article_media["illustratedRateTarget"]),
        text_only_rate_target=float(article_media["textOnlyRateTarget"]),
        m1_targets=tuple(
            (carrier, int(scale_milestones["m1Targets"][carrier]))
            for carrier in ("homepage", "article", "image", "video")
        ),
        m10_targets=tuple(
            (carrier, int(scale_milestones["m10Targets"][carrier]))
            for carrier in ("homepage", "article", "image", "video")
        ),
        m100_targets=tuple(
            (carrier, int(scale_milestones["m100Targets"][carrier]))
            for carrier in ("homepage", "article", "image", "video")
        ),
        m1000_targets=tuple(
            (carrier, int(scale_milestones["m1000Targets"][carrier]))
            for carrier in ("homepage", "article", "image", "video")
        ),
        m10000_targets=tuple(
            (carrier, int(scale_milestones["m10000Targets"][carrier]))
            for carrier in ("homepage", "article", "image", "video")
        ),
        require_m100_promotion_before_m1000=bool(
            scale_milestones["requireM100PromotionBeforeM1000"]
        ),
        require_m1000_promotion_before_m10000=bool(
            scale_milestones["requireM1000PromotionBeforeM10000"]
        ),
        milestone_attainment_required=bool(
            scale_milestones["milestoneAttainmentRequired"]
        ),
        attainment_counting_mode=str(scale_milestones["attainmentCountingMode"]),
        image_provider_priority=tuple(source_discovery["imageProviderPriority"]),
        video_popularity_signals=tuple(video_popularity["signals"]),
        video_popularity_statistical=bool(video_popularity["statistical"]),
        video_popularity_non_blocking=bool(video_popularity["nonBlocking"]),
        asset_record_defaults=tuple(
            sorted((str(key), str(value)) for key, value in raw["assetRecordDefaults"].items())
        ),
    )


def distribution_decision(
    *,
    acquisition_status: AcquisitionStatus,
    rights_status: RightsStatus,
    authorization_proof: str,
) -> DistributionDecision:
    if acquisition_status is not AcquisitionStatus.ACQUIRED:
        return DistributionDecision.BLOCKED
    # 保留原对象权利记录语义；下游发布不以此记录选择类别或拒绝对象。
    if rights_status is RightsStatus.RESTRICTED:
        return DistributionDecision.BLOCKED
    if rights_status is RightsStatus.VERIFIED and authorization_proof.strip():
        return DistributionDecision.COMMERCIAL_ALLOWED
    return DistributionDecision.RESEARCH_ALLOWED


def image_distribution_decision(
    *,
    acquisition_status: AcquisitionStatus,
    rights_status: RightsStatus,
    authorization_proof: str,
    usage_scope: str,
    model_release_status: str,
) -> DistributionDecision:
    """按实际使用范围保守记录权利，不决定 release 准入。"""

    base = distribution_decision(
        acquisition_status=acquisition_status,
        rights_status=rights_status,
        authorization_proof=authorization_proof,
    )
    if base is DistributionDecision.BLOCKED:
        return base
    normalized_scope = usage_scope.strip()
    normalized_release = model_release_status.strip()
    if normalized_scope not in {"internal_reference", "app_publish", "editorial"}:
        return DistributionDecision.BLOCKED
    if normalized_release not in {"not_required", "obtained", "editorial_only", "verified", "unverified"}:
        return DistributionDecision.BLOCKED
    if normalized_scope != "app_publish" or normalized_release in {"editorial_only", "unverified"}:
        return DistributionDecision.RESEARCH_ALLOWED
    return base


def asset_contract_missing_fields(asset: Mapping[str, Any]) -> list[str]:
    """Return missing/invalid fields from the lifecycle-neutral asset contract."""
    missing: list[str] = []
    acquisition_status = str(asset.get("acquisitionStatus") or "").strip()
    rights_status = str(
        asset.get("rightsStatus") or asset.get("rightsAuditStatus") or ""
    ).strip()
    decision = str(asset.get("distributionDecision") or "").strip()
    content_sha256 = str(
        asset.get("contentSha256") or asset.get("sha256") or ""
    ).strip()
    rights_issues = asset.get("rightsIssues")
    if rights_issues is None:
        rights_issues = asset.get("rightsAuditIssues")
    if acquisition_status != AcquisitionStatus.ACQUIRED.value:
        missing.append("acquisitionStatus")
    if rights_status not in {status.value for status in RightsStatus}:
        missing.append("rightsStatus")
    if decision not in {item.value for item in DistributionDecision}:
        missing.append("distributionDecision")
    if not str(asset.get("sourceUrl") or "").startswith("https://"):
        missing.append("sourceUrl")
    for field, value in (
        ("platform", asset.get("platform")),
        ("creator", asset.get("creator") or asset.get("credit")),
        ("capturedAt", asset.get("capturedAt")),
        ("contentSha256", content_sha256 if content_sha256.startswith("sha256:") else ""),
        ("license", asset.get("license")),
    ):
        if not str(value or "").strip():
            missing.append(field)
    if "termsUrl" not in asset:
        missing.append("termsUrl")
    if "authorizationProof" not in asset:
        missing.append("authorizationProof")
    if not isinstance(asset.get("authorizationRequired"), bool):
        missing.append("authorizationRequired")
    if not isinstance(rights_issues, list) or (
        rights_status != RightsStatus.VERIFIED.value
        and not [str(issue).strip() for issue in rights_issues if str(issue).strip()]
    ):
        missing.append("rightsIssues")
    return sorted(set(missing))


def project_asset_admission(
    asset: Mapping[str, Any],
    *,
    object_ref: str,
) -> dict[str, Any]:
    if "distributionDecision" in asset:
        declared = str(asset["distributionDecision"])
        if declared not in {item.value for item in DistributionDecision}:
            raise ValueError(f"{object_ref}: invalid distributionDecision: {declared!r}")
    raw_rights_status = str(
        asset.get("rightsStatus") or asset.get("rightsAuditStatus") or "unknown"
    ).strip()
    try:
        rights_status = RightsStatus(raw_rights_status)
    except ValueError as exc:
        raise ValueError(
            f"{object_ref}: asset rightsStatus is invalid: {raw_rights_status!r}"
        ) from exc
    physical = asset.get("asset")
    acquired = (
        isinstance(physical, Mapping)
        and str(physical.get("sha256") or "").startswith("sha256:")
        and int(physical.get("bytes") or 0) > 0
    )
    acquisition_status = (
        AcquisitionStatus.ACQUIRED if acquired else AcquisitionStatus.FAILED
    )
    authorization_proof = str(asset.get("authorizationProof") or "").strip()
    physical_mime = str(
        physical.get("mimeType") if isinstance(physical, Mapping) else ""
    ).strip()
    decision = (
        image_distribution_decision(
            acquisition_status=acquisition_status,
            rights_status=rights_status,
            authorization_proof=authorization_proof,
            usage_scope=str(asset.get("usageScope") or ""),
            model_release_status=str(asset.get("modelReleaseStatus") or ""),
        )
        if physical_mime.startswith("image/")
        else distribution_decision(
            acquisition_status=acquisition_status,
            rights_status=rights_status,
            authorization_proof=authorization_proof,
        )
    )
    if "distributionDecision" in asset:
        decision = DistributionDecision(str(asset["distributionDecision"]))
    source_url = str(
        asset.get("sourceUrl")
        or asset.get("originalAssetUrl")
        or asset.get("source")
        or asset.get("canonicalFilePage")
        or ""
    ).strip()
    captured_at = str(asset.get("capturedAt") or asset.get("fetchedAt") or "").strip()
    content_sha256 = str(
        asset.get("contentSha256")
        or (physical.get("sha256") if isinstance(physical, Mapping) else "")
        or ""
    ).strip()
    if not source_url.startswith("https://") or not captured_at or not content_sha256.startswith("sha256:"):
        raise ValueError(
            f"{object_ref}: acquired asset lacks sourceUrl/capturedAt/contentSha256"
        )
    rights_issues = [
        str(item).strip()
        for item in (asset.get("rightsIssues") or asset.get("rightsAuditIssues") or [])
        if str(item).strip()
    ]
    if rights_status is not RightsStatus.VERIFIED and not rights_issues:
        raise ValueError(f"{object_ref}: non-verified asset lacks rightsIssues")
    generated = bool(
        str(asset.get("generationModel") or "").strip()
        or str(asset.get("sourceUseMode") or "") == "self_generated_original"
    )
    return {
        "assetId": str(asset.get("assetId") or "").strip(),
        "objectRef": object_ref,
        "acquisitionStatus": acquisition_status.value,
        "rightsStatus": rights_status.value,
        "authorizationRequired": (
            rights_status is not RightsStatus.VERIFIED or not authorization_proof
        ),
        "distributionDecision": decision.value,
        "sourceUrl": source_url,
        "platform": str(asset.get("platform") or asset.get("sourceKind") or "unknown").strip(),
        "creator": str(asset.get("creator") or asset.get("author") or "unknown").strip(),
        "capturedAt": captured_at,
        "contentSha256": content_sha256,
        "license": str(asset.get("license") or asset.get("licenseName") or "unknown").strip(),
        "termsUrl": str(asset.get("termsUrl") or asset.get("licenseUrl") or "").strip(),
        "authorizationProof": authorization_proof,
        "rightsIssues": rights_issues,
        "generated": generated,
        # 只搬运 AI 申报的水印判定，供运营按资产审核；缺席一律 unknown，不得假定 absent。
        "watermarkStatus": str(asset.get("watermarkStatus") or "unknown").strip(),
        "watermarkKind": str(asset.get("watermarkKind") or "unknown").strip(),
        # 访问政策只搬运；缺席即缺席，不补 open——header 只汇总明确申报为受限的资产。
        **(
            {"accessPolicy": str(asset["accessPolicy"]).strip()}
            if str(asset.get("accessPolicy") or "").strip()
            else {}
        ),
    }


__all__ = [
    "POLICY_PATH",
    "AcquisitionStatus",
    "ContentDistributionPolicy",
    "DistributionDecision",
    "RightsStatus",
    "asset_contract_missing_fields",
    "distribution_decision",
    "image_distribution_decision",
    "load_content_distribution_policy",
    "project_asset_admission",
]
