"""Media and source-attribution checks for public post verification."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from content.release.environment.public_api_client import (
    PublicApiClient,
    _public_url_evidence,
)
from core.control_types import ContentType
from core.io import read_json


class PostApiVerificationError(ValueError):
    """An imported post cannot be consumed through its public API."""


@dataclass(frozen=True)
class ReleaseMediaAssetCase:
    asset_id: str
    kind: str
    # commercial：匿名 CDN 绝对 URL；research：与 delivery_ref 同值的相对
    # CAS key（App 回读比对用同一字段，探测语义由 delivery_ref 是否非空分流）。
    public_url: str
    expected_bytes: int
    expected_sha256: str
    expected_mime_type: str
    # research 私有交付的相对 CAS objectKey（media/objects/sha256/...）。
    delivery_ref: str = ""


@dataclass(frozen=True)
class PostApiCase:
    post_ref: str
    post_id: str
    content_type: ContentType
    author_id: str
    source_attribution: Mapping[str, Any] | None
    media_assets: tuple[ReleaseMediaAssetCase, ...] = ()


def _required_text(payload: Mapping[str, Any], field: str, *, endpoint: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PostApiVerificationError(f"{endpoint} lacks required {field}")
    return value.strip()


def _object(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PostApiVerificationError(f"{label} must be an object")
    return value


def _optional_text(payload: Mapping[str, Any], field: str, *, endpoint: str) -> str:
    value = payload.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise PostApiVerificationError(f"{endpoint} {field} must be a string or null")
    return value.strip()


def _public_media_path(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _source_attribution(
    release_root: Path,
    post_ref: str,
    *,
    content_type: ContentType,
) -> Mapping[str, Any] | None:
    path = (
        release_root
        / "payload"
        / "objects"
        / "posts"
        / post_ref
        / "manifest.json"
    )
    try:
        manifest = _object(read_json(path), label=f"post manifest {post_ref}")
    except (OSError, TypeError, ValueError) as exc:
        raise PostApiVerificationError(
            f"post manifest is unreadable for {post_ref}: {exc}"
        ) from exc
    raw = manifest.get("sourceAttribution")
    if raw is None:
        if content_type is ContentType.VIDEO:
            raise PostApiVerificationError(
                f"video manifest lacks sourceAttribution: {post_ref}"
            )
        return None
    return _object(raw, label=f"sourceAttribution {post_ref}")


def _require_media(
    payload: Mapping[str, Any],
    content_type: ContentType,
) -> tuple[list[str], str, str]:
    if content_type is ContentType.ARTICLE:
        _required_text(payload, "body", endpoint="article detail")
        return [], "", ""
    media_urls = payload.get("mediaUrls")
    urls = [
        str(url).strip()
        for url in media_urls
        if isinstance(url, str) and url.strip()
    ] if isinstance(media_urls, list) else []
    if not urls:
        raise PostApiVerificationError(f"{content_type.value} detail has no media URLs")
    cover_url = _required_text(
        payload,
        "coverUrl",
        endpoint=f"{content_type.value} detail",
    )
    video_url = ""
    if content_type is ContentType.VIDEO:
        video_url = _required_text(payload, "videoUrl", endpoint="video detail")
    return urls, cover_url, video_url


def _verify_binary_media(
    client: PublicApiClient,
    url: str,
    *,
    expected_kind: str,
    expected_bytes: int = 0,
    expected_sha256: str = "",
    expected_mime_type: str = "",
    evidence_policy: Literal["public_url", "private_target"] = "public_url",
) -> dict[str, Any]:
    if evidence_policy not in {"public_url", "private_target"}:
        raise PostApiVerificationError("media evidence policy is unsupported")
    target_evidence = _public_url_evidence(url)
    require_full_identity = expected_bytes > 0 or bool(expected_sha256)
    response = client.get_bytes(
        url,
        byte_range="" if require_full_identity else "bytes=0-65535",
        max_bytes=expected_bytes if require_full_identity else 65536,
    )
    if response.status not in {HTTPStatus.OK, HTTPStatus.PARTIAL_CONTENT}:
        raise PostApiVerificationError(
            f"public {expected_kind} media returned status={response.status}: "
            f"{target_evidence}"
        )
    content_type = response.content_type.split(";", 1)[0].strip().lower()
    if not content_type.startswith(f"{expected_kind}/"):
        raise PostApiVerificationError(
            f"public media MIME mismatch: {target_evidence}"
        )
    if not response.body:
        raise PostApiVerificationError(
            f"public media returned empty bytes: {target_evidence}"
        )
    if expected_mime_type and content_type != expected_mime_type:
        raise PostApiVerificationError(
            "public media MIME differs from release authority: "
            f"{target_evidence}"
        )
    observed_sha256 = f"sha256:{hashlib.sha256(response.body).hexdigest()}"
    if require_full_identity:
        if response.status != HTTPStatus.OK:
            raise PostApiVerificationError(
                "public media full-byte probe returned "
                f"status={response.status}: {target_evidence}"
            )
        if len(response.body) != expected_bytes:
            raise PostApiVerificationError(
                "public media length differs from release authority: "
                f"{target_evidence}"
            )
        if observed_sha256 != expected_sha256:
            raise PostApiVerificationError(
                "public media hash differs from release authority: "
                f"{target_evidence}"
            )
    if expected_kind == "video":
        if response.status != HTTPStatus.PARTIAL_CONTENT or not response.content_range.startswith(
            "bytes "
        ):
            raise PostApiVerificationError(
                f"public video does not honor byte ranges: {target_evidence}"
            )
        if b"ftyp" not in response.body[:64] and not response.body.startswith(
            b"\x1a\x45\xdf\xa3"
        ):
            raise PostApiVerificationError(
                "public video first range is not a playable MP4/WebM header: "
                f"{target_evidence}"
            )
    receipt = {
        "status": response.status,
        "mimeType": content_type,
        "bytes": len(response.body),
        "sha256": observed_sha256 if require_full_identity else "",
        "hashVerified": require_full_identity,
    }
    if evidence_policy == "private_target":
        return {"targetEvidence": target_evidence, **receipt}
    return {
        "publicUrl": url,
        **receipt,
        "etag": str(getattr(response, "etag", "") or ""),
    }


def _verify_research_denied_media(
    client: PublicApiClient,
    *,
    media_origin: str,
    asset: ReleaseMediaAssetCase,
) -> dict[str, Any]:
    """匿名 GET research 私有交付 URL 必须被边缘 401/403 拒绝。"""
    anonymous_url = f"{media_origin}/{asset.delivery_ref}"
    response = client.get_bytes(anonymous_url, byte_range="", max_bytes=65536)
    if response.status not in {
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
    }:
        raise PostApiVerificationError(
            "research private media must deny anonymous access "
            f"(status={response.status}): {_public_url_evidence(anonymous_url)}"
        )
    return {
        "assetId": asset.asset_id,
        "kind": asset.kind,
        "deliveryRef": asset.delivery_ref,
        "anonymousStatus": response.status,
        "expectedBytes": asset.expected_bytes,
        "expectedSha256": asset.expected_sha256,
        "signedProbe": None,
    }


def _verify_source_attribution(
    payload: Mapping[str, Any],
    case: PostApiCase,
) -> bool:
    expected = case.source_attribution
    if expected is None:
        if "sourceAttribution" not in payload or payload.get("sourceAttribution") is None:
            return True
        raise PostApiVerificationError(
            "post detail sourceAttribution drift for "
            f"{case.post_ref}: expected absent/null"
        )
    actual = _object(
        payload.get("sourceAttribution"),
        label=f"post detail sourceAttribution {case.post_ref}",
    )
    fields = (
        "isOriginal",
        "originalCreatorName",
        "platform",
        "sourcePostUrl",
        "attributionText",
        "rightsBasis",
        "commercialAuthorizationStatus",
        "publicationAdmission",
        "watermarkStatus",
        "audioRightsStatus",
    )
    drifted = [
        field
        for field in fields
        if expected.get(field) is not None and actual.get(field) != expected.get(field)
    ]
    if drifted:
        raise PostApiVerificationError(
            f"post detail sourceAttribution drift for {case.post_ref}: {drifted}"
        )
    return True
