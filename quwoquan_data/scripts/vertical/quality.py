"""垂类专项质量门。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from _common.paths import DATA_ROOT
from _common.source_catalog import known_category_ids
from download.fetch import SUPPORTED_TEXT_EXTRACTORS
from vertical.coverage import list_verticals, load_registry
from vertical.license import load_photography_license_policy, load_travel_license_policy
from vertical.source_registry import verify_travel_source_registry


def _samples_path(vertical: str) -> Path:
    return DATA_ROOT / "verticals" / vertical / "tests" / "golden_samples.yaml"


def verify_vertical_quality() -> list[str]:
    issues: list[str] = []
    categories = known_category_ids()
    for vertical in list_verticals():
        registry = load_registry(vertical)
        units = registry.get("units") or []
        if not units:
            issues.append(f"{vertical}: coverage registry has no units")
        samples_path = _samples_path(vertical)
        if not samples_path.is_file():
            issues.append(f"{vertical}: missing golden_samples.yaml")
            continue
        data: dict[str, Any] = yaml.safe_load(samples_path.read_text(encoding="utf-8")) or {}
        if data.get("schemaVersion") != "quwoquan.vertical_quality_samples.v1":
            issues.append(f"{vertical}: invalid golden sample schemaVersion")
        samples = data.get("samples") or []
        if len(samples) < 2:
            issues.append(f"{vertical}: at least 2 golden samples required")
        for sample in samples:
            missing_categories = [
                c for c in sample.get("requiredEvidenceCategories") or []
                if c not in categories
            ]
            if missing_categories:
                issues.append(f"{vertical}: sample {sample.get('id')} uses unknown categories {missing_categories}")
            if not sample.get("requiredChecks"):
                issues.append(f"{vertical}: sample {sample.get('id')} has no requiredChecks")
    try:
        policy = load_photography_license_policy()
    except Exception as exc:
        issues.append(f"photography: license policy invalid: {exc}")
    else:
        required = set(policy.get("requiredImageFields") or [])
        for field in ("license", "credit", "sourceUrl", "termsUrl", "usageScope"):
            if field not in required:
                issues.append(f"photography: requiredImageFields missing {field}")
    try:
        travel_policy = load_travel_license_policy()
    except Exception as exc:
        issues.append(f"travel: license policy invalid: {exc}")
    else:
        required = set(travel_policy.get("requiredImageFields") or [])
        for field in ("license", "credit", "sourceUrl", "termsUrl", "usageScope"):
            if field not in required:
                issues.append(f"travel: requiredImageFields missing {field}")
    issues.extend(verify_travel_source_registry(allowed_extractors=set(SUPPORTED_TEXT_EXTRACTORS)))
    return issues
