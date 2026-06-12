"""摄影素材授权策略。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

_VERTICALS_ROOT = Path(__file__).resolve().parents[2] / "verticals"

_POLICY_PATHS = {
    "photography": _VERTICALS_ROOT / "photography" / "rights" / "license_policy.yaml",
    "travel": _VERTICALS_ROOT / "travel" / "rights" / "license_policy.yaml",
}


def load_photography_license_policy() -> dict[str, Any]:
    return load_vertical_license_policy("photography")


def load_travel_license_policy() -> dict[str, Any]:
    return load_vertical_license_policy("travel")


def load_vertical_license_policy(vertical: str) -> dict[str, Any]:
    path = _POLICY_PATHS.get(vertical)
    if path is None:
        raise ValueError(f"unsupported license policy vertical: {vertical}")
    if not path.is_file():
        raise FileNotFoundError(f"missing {vertical} license policy: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    expected = {
        "photography": "quwoquan.photography_license_policy.v1",
        "travel": "quwoquan.travel_license_policy.v1",
    }[vertical]
    if data.get("schemaVersion") != expected:
        raise ValueError(f"{path}: invalid schemaVersion")
    if data.get("vertical") != vertical:
        raise ValueError(f"{path}: vertical mismatch")
    return data


def validate_image_rights(spec: Mapping[str, Any], *, vertical: str) -> list[str]:
    if vertical not in _POLICY_PATHS:
        return []
    policy = load_vertical_license_policy(vertical)
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
