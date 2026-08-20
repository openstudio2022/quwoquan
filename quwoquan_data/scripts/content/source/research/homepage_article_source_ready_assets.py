"""Governed open-image acquisition for source-ready candidates."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.image_rules import pixel_size_issue
from core.image_safety import STATUS_SAFE, assess_image
from core.runtime_policy import active_runtime_policy
from content.source.contracts import MediaProvenance
from content.source.research import network_io
from content.source.research.homepage_article_source_ready_types import (
    PUBLIC_ACCESS,
    AcquiredAsset,
    MediaWikiSourceReadyRejected,
    _sha256,
    _stable_id,
)
from content.source.research.source_quality import (
    license_allows_commercial_distribution,
)
from content.source.research.wiki_common import _canonical_terms_url

_MEDIAWIKI_HTTP_TIMEOUT_SECONDS = (
    active_runtime_policy().provider_timeouts.mediawiki_seconds
)

def _asset_extension(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(mime_type, "")


def acquire_open_image_assets(
    image_rows: list[dict[str, Any]],
    *,
    source_unit_ref: str,
    roles: tuple[str, ...],
    captured_at: str,
    image_assessor: Callable[..., Any] = assess_image,
) -> tuple[AcquiredAsset, ...]:
    acquired: list[AcquiredAsset] = []
    seen_content: set[str] = set()
    for raw in image_rows:
        if len(acquired) >= len(roles):
            break
        original_url = str(raw.get("url") or "").strip()
        license_name = str(raw.get("license") or "")
        terms_url = _canonical_terms_url(
            raw.get("termsUrl"),
            license_name=license_name,
            source_url=raw.get("sourceUrl"),
        )
        if not license_allows_commercial_distribution(license_name, terms_url):
            continue
        response = network_io.fetch_http(
            original_url,
            timeout=_MEDIAWIKI_HTTP_TIMEOUT_SECONDS,
        )
        if not response.ok or not response.body:
            continue
        content_sha = _sha256(response.body)
        if content_sha in seen_content:
            continue
        seen_content.add(content_sha)
        # Reaching this point already proves that the exact license/terms pair
        # is admitted for App publication.  Freeze that decision in the
        # physical source capsule instead of forcing a later execution to
        # infer usage scope from live policy.
        usage_scope = str(raw.get("usageScope") or "app_publish").strip()
        model_release_status = str(
            raw.get("modelReleaseStatus") or "not_required"
        ).strip()
        provenance = MediaProvenance.from_mapping(
            {
                **raw,
                "usageScope": usage_scope,
                "modelReleaseStatus": model_release_status,
            },
            vertical="travel",
        )
        with tempfile.NamedTemporaryFile(suffix=".img") as handle:
            handle.write(response.body)
            handle.flush()
            verdict = image_assessor(Path(handle.name), require_ocr=True)
        if verdict.status != STATUS_SAFE or verdict.faces != 0 or verdict.has_watermark:
            continue
        from core.image_decode import probe_image_bytes

        probe = probe_image_bytes(response.body)
        if not probe.succeeded or pixel_size_issue(
            probe.width, probe.height, asset_id=content_sha[-12:]
        ):
            continue
        extension = _asset_extension(probe.mime_type)
        if not extension:
            continue
        role = roles[len(acquired)]
        platform = str(raw.get("platform") or "Wikimedia Commons").strip()
        provider = "openverse" if platform == "Openverse" else "wikimedia_commons"
        asset_id = _stable_id(provider, content_sha, role)
        asset_ref = f"{source_unit_ref}/assets/{content_sha.removeprefix('sha256:')}{extension}"
        rights_status = provenance.rights_audit_status.value
        rights_issues = list(provenance.rights_audit_issues)
        acquired.append(
            AcquiredAsset(
                body=response.body,
                document={
                    "assetId": asset_id,
                    "role": role,
                    "assetRef": asset_ref,
                    "originalAssetUrl": original_url,
                    "sourcePageUrl": str(raw.get("sourceUrl") or original_url),
                    "platform": platform,
                    "provider": provider,
                    "creator": provenance.creator,
                    "capturedAt": captured_at,
                    "contentSha256": content_sha,
                    "license": provenance.license_name,
                    "termsUrl": terms_url,
                    "authorizationProof": str(raw.get("authorizationProof") or ""),
                    "usageScope": usage_scope,
                    "modelReleaseStatus": model_release_status,
                    "authorizationRequired": rights_status != "verified",
                    "rightsStatus": rights_status,
                    "rightsIssues": rights_issues,
                    "acquisitionStatus": "acquired",
                    "distributionDecision": "research_allowed",
                    "qualityStatus": "passed",
                    "safetyStatus": "passed",
                    "generated": False,
                    "width": probe.width,
                    "height": probe.height,
                    "byteCount": len(response.body),
                    "fileSha256": content_sha,
                    "safetyEvidence": {
                        "status": verdict.status,
                        "faces": verdict.faces,
                        "hasWatermark": verdict.has_watermark,
                        "textAreaRatio": round(verdict.text_area_ratio, 4),
                        "reasons": list(verdict.reasons),
                        "backends": list(verdict.backends),
                    },
                    "accessEvidence": dict(PUBLIC_ACCESS),
                },
            )
        )
    if len(acquired) != len(roles):
        raise MediaWikiSourceReadyRejected(
            f"source page lacks {len(roles)} safe open-license original images"
        )
    return tuple(acquired)

