"""垂类专项质量门。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.paths import _REPO_DATA_ROOT
from core.source_catalog import known_category_ids
from content.source.fetch_text import SUPPORTED_TEXT_EXTRACTORS
from governance.coverage.vertical_inventory import list_verticals, load_vertical_inventory
from governance.coverage.license import load_photography_license_policy, load_travel_license_policy
from governance.coverage.source_registry import verify_travel_source_registry


def _samples_path(vertical: str) -> Path:
    return _REPO_DATA_ROOT / "tests" / "support" / "vertical_quality" / f"{vertical}.yaml"


def verify_vertical_quality() -> list[str]:
    issues: list[str] = []
    categories = known_category_ids()
    for vertical in list_verticals():
        inventory = load_vertical_inventory(vertical)
        carriers = inventory.get("carriers") or []
        if not carriers:
            issues.append(f"{vertical}: content policy has no carriers")
        samples_path = _samples_path(vertical)
        if not samples_path.is_file():
            issues.append(f"{vertical}: missing reusable quality sample fixture")
            continue
        data: dict[str, Any] = yaml.safe_load(samples_path.read_text(encoding="utf-8")) or {}
        if data.get("schema") != "quwoquan.vertical_quality_samples":
            issues.append(f"{vertical}: invalid golden sample schema")
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
