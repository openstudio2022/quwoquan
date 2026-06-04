"""摄影素材授权策略。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.paths import DATA_ROOT

POLICY_PATH = DATA_ROOT / "verticals" / "photography" / "rights" / "license_policy.yaml"


def load_photography_license_policy() -> dict[str, Any]:
    if not POLICY_PATH.is_file():
        raise FileNotFoundError(f"missing photography license policy: {POLICY_PATH}")
    data = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}
    if data.get("schemaVersion") != "quwoquan.photography_license_policy.v1":
        raise ValueError(f"{POLICY_PATH}: invalid schemaVersion")
    return data


def validate_image_rights(spec: Mapping[str, Any], *, vertical: str) -> list[str]:
    if vertical != "photography":
        return []
    policy = load_photography_license_policy()
    issues: list[str] = []
    platform = str(spec.get("platform") or spec.get("sourcePlatform") or "")
    if platform in set(policy.get("blockedDiscoveryOnlyPlatforms") or []):
        issues.append("imageRights: Pinterest/发现源只能作为灵感或参考，不得直接下载入库")
    for field in policy.get("requiredImageFields") or []:
        if not str(spec.get(field) or "").strip():
            issues.append(f"imageRights: missing required field {field}")
    license_value = str(spec.get("license") or "").strip()
    if license_value and license_value not in set(policy.get("allowedLicenseKinds") or []):
        issues.append(f"imageRights: unsupported license {license_value}")
    usage_scope = str(spec.get("usageScope") or "").strip()
    if usage_scope and usage_scope not in set(policy.get("usageScopes") or []):
        issues.append(f"imageRights: unsupported usageScope {usage_scope}")
    model_release = str(spec.get("modelReleaseStatus") or "").strip()
    if str(spec.get("modelReleaseRequired") or "").lower() in ("true", "1", "yes") and model_release != "obtained":
        issues.append("imageRights: modelReleaseRequired requires modelReleaseStatus=obtained")
    return issues


def normalize_rights_payload(spec: Mapping[str, Any]) -> dict[str, Any]:
    keys = [
        "license",
        "credit",
        "sourceUrl",
        "termsUrl",
        "licenseSnapshot",
        "usageScope",
        "modelReleaseRequired",
        "modelReleaseStatus",
        "authorizationProof",
    ]
    return {key: spec.get(key, "") for key in keys if spec.get(key, "") != ""}
