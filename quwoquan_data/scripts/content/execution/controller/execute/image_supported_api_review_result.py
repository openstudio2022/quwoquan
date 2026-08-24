"""Result projection for one fresh supported-API image review."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.controller.execute.image_supported_api_review_storage import (
    portable_review_ref,
)
from content.source.professional_safety_evidence import file_sha256


def image_review_passed(judgment: Mapping[str, Any]) -> bool:
    return all(
        (
            judgment.get("status") == "passed",
            judgment.get("entityMatch") == "matched",
            judgment.get("privacyRisk") == "none",
            judgment.get("minorRisk") == "none",
            judgment.get("maliciousMediaRisk") == "none",
            judgment.get("watermarkStatus") == "absent",
            judgment.get("qualityStatus") == "passed",
        )
    )


def image_review_summary(
    result: Mapping[str, Any],
    path: Path,
    *,
    output_root: Path,
) -> dict[str, Any]:
    return {
        "candidateId": str(result["candidateId"]),
        "status": str(result["judgment"]["status"]),
        "runId": str(result["runId"]),
        "resultRef": portable_review_ref(path, output_root=output_root),
        "resultSha256": file_sha256(path),
    }


def image_review_judgment(text: str) -> dict[str, Any] | None:
    """从 agent 回复中取出恰好含全部判定字段的 JSON；取不到即缺席。"""
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    expected = {
        "status", "entityMatch", "privacyRisk", "minorRisk",
        "maliciousMediaRisk", "watermarkStatus", "qualityStatus", "findings",
    }
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and set(parsed) == expected:
            return parsed
    return None


__all__ = [
    "image_review_judgment",
    "image_review_passed",
    "image_review_summary",
]
