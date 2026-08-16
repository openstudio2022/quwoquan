"""Source-review identity projection for supported-API image review."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _source_review_identity(
    *,
    handoff: Mapping[str, Any],
    request: Mapping[str, Any],
    handoff_ref: Path,
) -> dict[str, str]:
    from content.execution.controller.execute.review_image_supported_api_input import (
        ProfessionalImageSupportedApiReviewError,
        file_sha256,
    )

    source = handoff.get("sourceDigest")
    bundle = handoff.get("executionBundle")
    if not isinstance(source, Mapping) or not isinstance(bundle, Mapping):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_HANDOFF_INVALID: frozen source/bundle identity is missing"
        )
    identity = {
        "sourceRevision": str(handoff.get("sourceRevision") or ""),
        "sourceDigest": str(source.get("digest") or ""),
        "entityCatalogDigest": str(handoff.get("entityCatalogDigest") or ""),
        "executionBundleDigest": str(bundle.get("digest") or ""),
        "handoffDigest": file_sha256(handoff_ref),
        "requestDigest": str(request.get("requestDigest") or ""),
    }
    if any(not value.startswith("sha256:") for value in identity.values()):
        raise ProfessionalImageSupportedApiReviewError(
            "DATA.SOURCE.REVIEW_HANDOFF_INVALID: source review identity is malformed"
        )
    return identity
