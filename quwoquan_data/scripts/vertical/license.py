"""摄影素材授权策略。"""
from __future__ import annotations

from pathlib import Path
import re
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
    # Platforms are discovery signals only. Publishability is decided by the
    # concrete asset rights below: license, credit, terms, authorization,
    # usage scope, model release and safety gates.
    for field in policy.get("requiredImageFields") or []:
        if not str(spec.get(field) or "").strip():
            issues.append(f"imageRights: missing required field {field}")
    license_value = str(spec.get("license") or "").strip()
    normalized_allowed = {
        re.sub(r"\s+", " ", str(item).strip()).casefold()
        for item in (policy.get("allowedLicenseKinds") or [])
    }
    normalized_license = re.sub(r"\s+", " ", license_value).casefold()
    if license_value and normalized_license not in normalized_allowed:
        issues.append(f"imageRights: unsupported license {license_value}")
    if normalized_license == "ai generated original".casefold():
        for field in ("generationModel", "generationPromptHash", "generatedAt"):
            if not str(spec.get(field) or "").strip():
                issues.append(f"imageRights: AI generated asset missing {field}")
        disclosure = str(spec.get("syntheticDisclosure") or "").strip().casefold()
        if disclosure not in {"true", "1", "yes"}:
            issues.append("imageRights: AI generated asset requires syntheticDisclosure=true")
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
        "generationModel",
        "generationPromptHash",
        "generatedAt",
        "syntheticDisclosure",
    ]
    return {key: spec.get(key, "") for key in keys if spec.get(key, "") != ""}
