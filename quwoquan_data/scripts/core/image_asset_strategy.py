"""Image asset strategy contract for separated source_discovery tasks."""
from __future__ import annotations

from typing import Any, Mapping

DEFAULT_IMAGE_ASSET_STRATEGY = "open_license_publish"

OPEN_LICENSE_PUBLISH = "open_license_publish"
LICENSED_PROVIDER_PUBLISH = "licensed_provider_publish"
AI_GENERATED_ORIGINAL = "ai_generated_original"
ATTRIBUTION_AUDITED_PUBLISH = "attribution_audited_publish"
REFERENCE_ONLY_NO_IMAGE_RELEASE = "reference_only_no_image_release"

IMAGE_ASSET_STRATEGIES = {
    OPEN_LICENSE_PUBLISH,
    LICENSED_PROVIDER_PUBLISH,
    AI_GENERATED_ORIGINAL,
    ATTRIBUTION_AUDITED_PUBLISH,
    REFERENCE_ONLY_NO_IMAGE_RELEASE,
}

IMAGE_COUNT_POLICY_SCORE_BONUS = "score_bonus"
IMAGE_COUNT_POLICY_HARD_QUOTA = "hard_quota"
IMAGE_COUNT_POLICIES = {
    IMAGE_COUNT_POLICY_SCORE_BONUS,
    IMAGE_COUNT_POLICY_HARD_QUOTA,
}

BATCH_SCALE_TARGET_THRESHOLD = 100


def _source_discovery(spec: Mapping[str, Any]) -> Mapping[str, Any]:
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    if "research" in content or content.get("modalityContract") == "separated_research":
        raise ValueError("DATA.CONTRACT.RETIRED: content source discovery contract")
    return content.get("sourceDiscovery") if isinstance(content.get("sourceDiscovery"), Mapping) else {}


def image_asset_strategy(spec: Mapping[str, Any]) -> str:
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    source_discovery = _source_discovery(spec)
    raw = (
        source_discovery.get("imageAssetStrategy")
        or content.get("imageAssetStrategy")
        or DEFAULT_IMAGE_ASSET_STRATEGY
    )
    strategy = str(raw or "").strip()
    return strategy or DEFAULT_IMAGE_ASSET_STRATEGY


def image_count_policy(spec: Mapping[str, Any]) -> str:
    """Return whether image count is a hard quota or a score bonus.

    ``imageWorksPerTarget`` expresses the desired saturation point by default:
    fewer rights-cleared images lower the score, but do not make an otherwise
    usable entity ineligible. Tasks that truly need an exact image object quota
    can opt into ``hard_quota`` explicitly.
    """

    source_discovery = _source_discovery(spec)
    raw = str(source_discovery.get("imageCountPolicy") or IMAGE_COUNT_POLICY_SCORE_BONUS).strip()
    return raw or IMAGE_COUNT_POLICY_SCORE_BONUS


def image_count_is_hard_quota(spec: Mapping[str, Any]) -> bool:
    return image_count_policy(spec) == IMAGE_COUNT_POLICY_HARD_QUOTA


def minimum_publishable_images_per_target(spec: Mapping[str, Any]) -> int:
    source_discovery = _source_discovery(spec)
    for key in ("minimumPublishableImagesPerTarget", "minPublishableImagesPerTarget"):
        if key not in source_discovery:
            continue
        try:
            return max(0, int(source_discovery.get(key) or 0))
        except (TypeError, ValueError):
            return 0
    return 0


def image_strategy_allows_ai_generated(spec: Mapping[str, Any]) -> bool:
    return image_asset_strategy(spec) == AI_GENERATED_ORIGINAL


def image_strategy_requires_publishable_images(spec: Mapping[str, Any]) -> bool:
    return image_asset_strategy(spec) != REFERENCE_ONLY_NO_IMAGE_RELEASE


def image_strategy_release_allowed(spec: Mapping[str, Any]) -> bool:
    return image_asset_strategy(spec) != REFERENCE_ONLY_NO_IMAGE_RELEASE


def validate_image_asset_strategy(spec: Mapping[str, Any]) -> list[str]:
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    source_discovery = content.get("sourceDiscovery") if isinstance(content.get("sourceDiscovery"), Mapping) else {}
    strategy = image_asset_strategy(spec)
    issues: list[str] = []
    if strategy not in IMAGE_ASSET_STRATEGIES:
        issues.append(
            "content.sourceDiscovery.imageAssetStrategy must be one of "
            f"{sorted(IMAGE_ASSET_STRATEGIES)}"
        )
        return issues
    policy = image_count_policy(spec)
    if policy not in IMAGE_COUNT_POLICIES:
        issues.append(
            "content.sourceDiscovery.imageCountPolicy must be one of "
            f"{sorted(IMAGE_COUNT_POLICIES)}"
        )

    allow_ai = bool(source_discovery.get("allowAiImages", False))
    if strategy == AI_GENERATED_ORIGINAL:
        if not allow_ai:
            issues.append(
                "content.sourceDiscovery.allowAiImages must be true when "
                "imageAssetStrategy=ai_generated_original"
            )
        provider = str(
            source_discovery.get("syntheticAssetProvider")
            or source_discovery.get("imageGenerationProvider")
            or ""
        ).strip()
        if not provider:
            issues.append(
                "content.sourceDiscovery.syntheticAssetProvider is required when "
                "imageAssetStrategy=ai_generated_original"
            )
    elif allow_ai:
        issues.append(
            "content.sourceDiscovery.allowAiImages must be false unless "
            "imageAssetStrategy=ai_generated_original"
        )

    if strategy == LICENSED_PROVIDER_PUBLISH:
        provider = str(
            source_discovery.get("licensedImageProvider")
            or source_discovery.get("licensedAssetPool")
            or ""
        ).strip()
        if not provider:
            issues.append(
                "content.sourceDiscovery.licensedImageProvider or licensedAssetPool is "
                "required when imageAssetStrategy=licensed_provider_publish"
            )

    return issues


def image_asset_strategy_scale_issues(
    spec: Mapping[str, Any],
    scale_proof: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return preflight blockers for image strategy at production batch scale.

    Open-license discovery remains valid for small trials and for entities that
    naturally have Commons/Openverse coverage.  At >=100 entities with >=2 image
    works per entity, however, it must be backed by a pre-screened open-license
    pool; otherwise the workflow repeatedly burns download/agent budget before
    discovering the same shortage.
    """

    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    source_discovery = content.get("sourceDiscovery") if isinstance(content.get("sourceDiscovery"), Mapping) else {}
    scope = spec.get("scope") if isinstance(spec.get("scope"), Mapping) else {}
    acceptance = spec.get("acceptance") if isinstance(spec.get("acceptance"), Mapping) else {}
    per_target_images = int(quotas.get("imageWorksPerTarget") or 0)
    declared_targets = scope.get("coverageTargets") if isinstance(scope.get("coverageTargets"), list) else []
    required_targets = max(len(declared_targets), int(acceptance.get("minEntities") or 0))
    strategy = image_asset_strategy(spec)
    count_policy = image_count_policy(spec)
    configured_minimum = minimum_publishable_images_per_target(spec)
    minimum_images_per_target = max(
        configured_minimum,
        (
            per_target_images
            if count_policy == IMAGE_COUNT_POLICY_HARD_QUOTA
            else (1 if per_target_images > 0 else 0)
        ),
    )
    if (
        required_targets < BATCH_SCALE_TARGET_THRESHOLD
        or minimum_images_per_target < 1
    ):
        return []
    required_images = required_targets * minimum_images_per_target
    if strategy == OPEN_LICENSE_PUBLISH:
        proof_file = "_shared/open_license_scale_proof.json"
        entity_count_field = "preScreenedEntityCount"
        required_text = (
            f"execution evidence {proof_file} with "
            "{missing}; otherwise configure licensed_provider_publish with "
            "licensedImageProvider/licensedAssetPool or ai_generated_original with "
            "syntheticAssetProvider"
        )
    elif strategy == LICENSED_PROVIDER_PUBLISH:
        proof_file = "_shared/licensed_provider_scale_proof.json"
        entity_count_field = "licensedEntityCount"
        required_text = (
            f"execution evidence {proof_file} with "
            "{missing}; provider name alone is not sufficient for production image release"
        )
    elif strategy == AI_GENERATED_ORIGINAL:
        proof_file = "_shared/synthetic_scale_proof.json"
        entity_count_field = "generatedEntityCount"
        required_text = (
            f"execution evidence {proof_file} with "
            "{missing}; generation provider name alone is not sufficient for production image release"
        )
    else:
        return []

    proof = scale_proof if isinstance(scale_proof, Mapping) else {}
    pre_screened_entities = int(
        (proof or {}).get(entity_count_field)
        or (proof or {}).get("scoredEntityCount")
        or 0
    )
    publishable_assets = int((proof or {}).get("publishableImageAssets") or 0)
    asset_pool_path = str((proof or {}).get("assetPoolPath") or "").strip()
    verified_at = str((proof or {}).get("verifiedAt") or "").strip()
    missing: list[str] = []
    if pre_screened_entities < required_targets:
        missing.append(f"{entity_count_field}>={required_targets}")
    if required_images and publishable_assets < required_images:
        missing.append(f"publishableImageAssets>={required_images}")
    if not asset_pool_path:
        missing.append("assetPoolPath")
    if not verified_at:
        missing.append("verifiedAt")
    if not missing:
        return []
    return [
        f"content.sourceDiscovery.imageAssetStrategy={strategy} at production scale "
        f"({required_targets} targets x {minimum_images_per_target} required images) requires "
        + required_text.format(missing=", ".join(missing))
    ]
