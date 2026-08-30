"""Physical, digest-bound safety evidence for professional media acquisition."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.image_decode import probe_image_bytes
from core.io import read_json
from core.schema import assert_valid

_REVIEW_FIELDS = (
    "status",
    "entityMatch",
    "privacyRisk",
    "minorRisk",
    "maliciousMediaRisk",
    "watermarkStatus",
    "reviewedAt",
    "reviewer",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def bytes_sha256(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _safe_file(root: Path, relative_ref: object, *, label: str) -> Path:
    relative = Path(str(relative_ref or "").strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} must be a safe relative path")
    resolved_root = root.expanduser().resolve()
    candidate = resolved_root / relative
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} must not traverse a symlink")
    resolved = candidate.resolve()
    if resolved_root not in resolved.parents or not resolved.is_file():
        raise ValueError(f"{label} is missing or escapes its declared root")
    return resolved


def _assert_review_binding(
    evidence: Mapping[str, Any],
    item: Mapping[str, Any],
) -> None:
    safety = item["safetyReview"]
    drift = [field for field in _REVIEW_FIELDS if evidence.get(field) != safety.get(field)]
    expected = {
        "assetId": item.get("assetId"),
        "entityId": item.get("entityId"),
        "observedEntityId": item.get("observedEntityId"),
    }
    drift.extend(field for field, value in expected.items() if evidence.get(field) != value)
    if drift:
        raise ValueError(
            "professional safety evidence identity/review drift: "
            + ", ".join(sorted(set(drift)))
        )


def load_bound_safety_evidence(
    item: Mapping[str, Any],
    *,
    evidence_root: Path,
    kind: str,
    manual_root: Path | None = None,
    source_review_identity: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Load one exact evidence file and verify every pre-payload binding."""
    if kind not in {"image", "video"}:
        raise ValueError(f"unsupported professional safety evidence kind: {kind}")
    safety = item["safetyReview"]
    path = _safe_file(
        evidence_root,
        safety.get("evidenceRef"),
        label=f"{item.get('assetId')}.safetyReview.evidenceRef",
    )
    expected_file_sha = str(safety.get("safetyEvidenceFileSha256") or "")
    if file_sha256(path) != expected_file_sha:
        raise ValueError(
            f"{item.get('assetId')}: safety evidence file SHA-256 drift"
        )
    evidence = read_json(path)
    if not isinstance(evidence, dict):
        raise TypeError("professional safety evidence must be an object")
    assert_valid(
        evidence,
        "source",
        f"professional_{kind}_safety_evidence",
        label=f"professional {kind} safety evidence:{path}",
    )
    _assert_review_binding(evidence, item)
    source_field = "sourceUrl" if kind == "image" else "sourcePageUrl"
    if evidence.get(source_field) != item.get("sourceUrl"):
        raise ValueError(
            f"{item.get('assetId')}: safety evidence source URL drift"
        )
    if kind == "video":
        _validate_video_physical_refs(
            evidence,
            item,
            evidence_root=evidence_root,
            manual_root=manual_root,
            source_review_identity=source_review_identity,
        )
    return evidence


def _validate_video_physical_refs(
    evidence: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    evidence_root: Path,
    manual_root: Path | None,
    source_review_identity: Mapping[str, str] | None,
) -> None:
    contact_sheet = _safe_file(
        evidence_root,
        evidence.get("contactSheetRef"),
        label=f"{item.get('assetId')}.contactSheetRef",
    )
    if file_sha256(contact_sheet) != evidence.get("contactSheetSha256"):
        raise ValueError(
            f"{item.get('assetId')}: safety contact-sheet SHA-256 drift"
        )
    contact_probe = probe_image_bytes(contact_sheet.read_bytes())
    if not contact_probe.succeeded:
        raise ValueError(
            f"{item.get('assetId')}: safety contact sheet is not a decodable image"
        )
    file_ref = str(evidence.get("fileRef") or "")
    if item.get("acquisitionPath") != "manual_file" or item.get("frozenAsset") is not None:
        if file_ref:
            raise ValueError(
                f"{item.get('assetId')}: non-manual safety evidence forbids fileRef"
            )
        _validate_video_source_attribution(evidence, item)
        _validate_source_review_evidence(
            evidence,
            evidence_root=evidence_root,
            source_review_identity=source_review_identity,
        )
        return
    if manual_root is None:
        raise ValueError("manual_root is required by manual_file safety evidence")
    if file_ref != str(item.get("manualFile") or ""):
        raise ValueError(f"{item.get('assetId')}: safety evidence fileRef drift")
    media_file = _safe_file(
        manual_root,
        file_ref,
        label=f"{item.get('assetId')}.fileRef",
    )
    if (
        file_sha256(media_file) != evidence.get("fileSha256")
        or media_file.stat().st_size != evidence.get("bytes")
    ):
        raise ValueError(
            f"{item.get('assetId')}: safety evidence physical video drift"
        )
    _validate_video_source_attribution(evidence, item)
    _validate_source_review_evidence(
        evidence,
        evidence_root=evidence_root,
        source_review_identity=source_review_identity,
    )


def _validate_video_source_attribution(
    evidence: Mapping[str, Any],
    item: Mapping[str, Any],
) -> None:
    attribution = evidence.get("sourceAttribution")
    if attribution is None:
        return
    if not isinstance(attribution, Mapping):
        raise TypeError(
            f"{item.get('assetId')}: video safety source attribution is invalid"
        )
    expected = {
        "provider": item.get("provider"),
        "sourcePostUrl": item.get("sourceUrl"),
        "originalAssetUrl": item.get("assetUrl"),
        "creator": item.get("creator"),
        "license": item.get("license"),
        "termsUrl": item.get("termsUrl"),
        "authorizationProof": item.get("authorizationProof"),
    }
    drift = [
        field
        for field, value in expected.items()
        if attribution.get(field) != value
    ]
    if drift:
        raise ValueError(
            f"{item.get('assetId')}: video safety source/rights drift: "
            + ", ".join(drift)
        )


def _validate_source_review_evidence(
    evidence: Mapping[str, Any],
    *,
    evidence_root: Path,
    source_review_identity: Mapping[str, str] | None,
) -> None:
    from content.source.host_source_review import read_host_source_review_result

    review = evidence.get("reviewEvidence")
    if review is None:
        return
    if not isinstance(review, Mapping):
        raise TypeError("video source review evidence is invalid")
    result = read_host_source_review_result(
        evidence_root=evidence_root,
        request_ref=str(review.get("requestRef") or ""),
        result_ref=str(review.get("resultRef") or ""),
    )
    if result.get("resultDigest") != review.get("resultDigest"):
        raise ValueError("video host source review result digest drift")
    if source_review_identity is not None:
        observed = result.get("sourceIdentity")
        if not isinstance(observed, Mapping) or any(
            observed.get(field) != value
            for field, value in source_review_identity.items()
        ):
            raise ValueError("video source review identity differs from current handoff")


def validate_image_safety_payload(
    evidence: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    body: bytes,
    width: int,
    height: int,
) -> None:
    expected = {
        "contentSha256": bytes_sha256(body),
        "bytes": len(body),
        "dimensions": {"width": width, "height": height},
    }
    drift = [field for field, value in expected.items() if evidence.get(field) != value]
    if drift:
        raise ValueError(
            f"{item.get('assetId')}: image safety evidence payload drift: "
            + ", ".join(drift)
        )


def validate_video_safety_payload(
    evidence: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    content_sha256: str,
    size_bytes: int,
    media_probe: Mapping[str, Any],
) -> None:
    expected = {
        "fileSha256": content_sha256,
        "bytes": size_bytes,
        "mediaProbe": dict(media_probe),
    }
    drift = [field for field, value in expected.items() if evidence.get(field) != value]
    if drift:
        raise ValueError(
            f"{item.get('assetId')}: video safety evidence payload drift: "
            + ", ".join(drift)
        )


__all__ = [
    "bytes_sha256",
    "file_sha256",
    "load_bound_safety_evidence",
    "validate_image_safety_payload",
    "validate_video_safety_payload",
]
