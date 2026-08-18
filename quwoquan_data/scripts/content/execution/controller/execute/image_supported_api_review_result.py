"""Result projection for one fresh supported-API image review."""

from __future__ import annotations

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


__all__ = ["image_review_passed", "image_review_summary"]
