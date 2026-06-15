"""Download-stage diagnostics shared by workflow repair and scale gates."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.io import read_json


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


def classify_download_issue(text: str) -> str:
    lowered = str(text or "").casefold()
    if "imagepixels" in lowered or "尺寸过小" in text or "长边过短" in text:
        return "pixel_too_small"
    if "imagesafety" in lowered or "watermark" in lowered or "unsafe" in lowered:
        return "safety_or_watermark"
    if "license" in lowered or "rights" in lowered or "授权" in text:
        return "rights"
    if "dedupe" in lowered or "near-duplicate" in lowered:
        return "duplicate"
    if "imagefetch" in lowered or "下载失败" in text or "非图片" in text:
        return "fetch_or_non_image"
    return "other"


def entity_download_diagnostics(root: Path, entity_id: str) -> dict[str, Any]:
    fetch_path = root / "task_download" / "results" / "image_fetch_gate" / f"{entity_id}.json"
    rights_path = root / "task_download" / "results" / "image_rights_gate" / f"{entity_id}.json"
    source_plan_path = root / "task_download" / "results" / "source_plan_gate" / f"{entity_id}.json"
    fetch_report = _load_json_if_exists(fetch_path)
    payload = fetch_report.get("payload") if isinstance(fetch_report.get("payload"), Mapping) else {}
    evidence = payload.get("evidenceSummary") if isinstance(payload.get("evidenceSummary"), Mapping) else {}
    rejected = [str(item) for item in evidence.get("rejectedForQuality") or []]
    categories = {
        "fetch_or_non_image": 0,
        "pixel_too_small": 0,
        "safety_or_watermark": 0,
        "rights": 0,
        "duplicate": 0,
        "other": 0,
    }
    for item in rejected:
        categories[classify_download_issue(item)] += 1

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
    fetch_root = root / "task_download" / "results" / "image_fetch_gate"
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
