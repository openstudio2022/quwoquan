"""Download-stage diagnostics shared by workflow repair and scale gates."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.io import read_json


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _download_results_root(execution_dir: Path) -> Path:
    """Return the canonical disposable workspace for download gate reports."""
    return execution_dir / "_shared" / "workspace" / "source" / "results"


def entity_download_diagnostics(root: Path, entity_id: str) -> dict[str, Any]:
    result_root = _download_results_root(root)
    fetch_path = result_root / "image_fetch_gate" / f"{entity_id}.json"
    rights_path = result_root / "image_rights_gate" / f"{entity_id}.json"
    source_plan_path = result_root / "source_plan_gate" / f"{entity_id}.json"
    fetch_report = _load_json_if_exists(fetch_path)
    payload = fetch_report.get("payload") if isinstance(fetch_report.get("payload"), Mapping) else {}
    evidence = payload.get("evidenceSummary") if isinstance(payload.get("evidenceSummary"), Mapping) else {}
    rejected = [str(item) for item in evidence.get("rejectedForQuality") or []]
    categories: dict[str, int] = {
        "fetch_or_non_image": 0,
        "pixel_too_small": 0,
        "safety_or_watermark": 0,
        "rights": 0,
        "duplicate": 0,
        "other": 0,
    }
    raw_categories = evidence.get("rejectedByCategory")
    if isinstance(raw_categories, Mapping):
        for category in categories:
            categories[category] = _safe_int(raw_categories.get(category))

    rights_report = _load_json_if_exists(rights_path)
    rights_payload = rights_report.get("payload") if isinstance(rights_report.get("payload"), Mapping) else {}
    rights_evidence = (
        rights_payload.get("evidenceSummary")
        if isinstance(rights_payload.get("evidenceSummary"), Mapping)
        else {}
    )

    source_report = _load_json_if_exists(source_plan_path)
    source_payload = source_report.get("payload") if isinstance(source_report.get("payload"), Mapping) else {}
    source_evidence = (
        source_payload.get("evidenceSummary")
        if isinstance(source_payload.get("evidenceSummary"), Mapping)
        else {}
    )
    return {
        "entityId": entity_id,
        "plannedImages": _safe_int(evidence.get("plannedImages")),
        "downloadedImages": _safe_int(evidence.get("downloadedImages")),
        "blockedImages": _safe_int(rights_evidence.get("blockedImages")),
        "rejectedImages": len(rejected),
        "rejectedByCategory": categories,
        "sourcePlanCategories": list(source_evidence.get("coveredCategories") or []),
        "sampleRejected": rejected[:5],
    }


def download_diagnostics(root: Path) -> dict[str, Any]:
    fetch_root = _download_results_root(root) / "image_fetch_gate"
    summary = {
        "entitiesWithFetchReports": 0,
        "plannedImages": 0,
        "downloadedImages": 0,
        "blockedImages": 0,
        "rejectedByCategory": {
            "fetch_or_non_image": 0,
            "pixel_too_small": 0,
            "safety_or_watermark": 0,
            "rights": 0,
            "duplicate": 0,
            "other": 0,
        },
        "sourcePlanCategories": {},
        "topEntityIssues": [],
    }
    for path in sorted(fetch_root.glob("*.json")) if fetch_root.is_dir() else []:
        row = entity_download_diagnostics(root, path.stem)
        summary["entitiesWithFetchReports"] += 1
        summary["plannedImages"] += int(row["plannedImages"])
        summary["downloadedImages"] += int(row["downloadedImages"])
        summary["blockedImages"] += int(row["blockedImages"])
        for category, count in (row.get("rejectedByCategory") or {}).items():
            summary["rejectedByCategory"][category] = summary["rejectedByCategory"].get(category, 0) + int(count)
        for category in row.get("sourcePlanCategories") or []:
            key = str(category)
            summary["sourcePlanCategories"][key] = summary["sourcePlanCategories"].get(key, 0) + 1
        if int(row.get("rejectedImages") or 0):
            summary["topEntityIssues"].append(
                {
                    "entity": path.stem,
                    "rejected": int(row["rejectedImages"]),
                    "categories": {
                        key: value
                        for key, value in (row.get("rejectedByCategory") or {}).items()
                        if int(value)
                    },
                }
            )
    summary["topEntityIssues"] = sorted(
        summary["topEntityIssues"],
        key=lambda row: int(row.get("rejected") or 0),
        reverse=True,
    )[:10]
    return summary
