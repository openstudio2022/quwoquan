"""Typed image download contracts and byte-budget enforcement."""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from core.paths import DATA_ROOT
from core.runtime_policy import active_runtime_policy
from content.source.fetch_http import _http_get_bytes
from content.source.fetch_image_candidates import candidate_image_urls
from content.source.image_payload import sniff_image_ext

_RUNTIME_POLICY = active_runtime_policy()
PAGE_IMAGE_FETCH_MAX_ATTEMPTS = _RUNTIME_POLICY.page_image_fetch_max_attempts
PAGE_IMAGE_FETCH_RETRY_BACKOFF_SECONDS = _RUNTIME_POLICY.page_image_fetch_retry_backoff_seconds
PAGE_IMAGE_DOWNLOAD_TIMEOUT_SECONDS = _RUNTIME_POLICY.page_image_download_timeout_seconds


class PageImageFetchFailure(StrEnum):
    """Closed failure vocabulary for an enumerated source-page bitmap."""

    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    HTTP_STATUS = "http_status"
    NETWORK = "network"
    TOO_SMALL = "too_small"
    TOO_LARGE = "too_large"
    NOT_IMAGE = "not_image"
    FILE_ACCESS = "file_access"

    @property
    def retryable(self) -> bool:
        return self in {
            PageImageFetchFailure.RATE_LIMITED,
            PageImageFetchFailure.UPSTREAM_UNAVAILABLE,
            PageImageFetchFailure.NETWORK,
        }


@dataclass(frozen=True, slots=True)
class PageImagePayload:
    """Downloaded bitmap plus the immutable URL normalization evidence."""

    url: str
    requested_url: str
    normalized_from_url: str
    ext: str
    content: bytes
    content_type: str
    sha256: str

    def __post_init__(self) -> None:
        if not self.url.strip() or not self.requested_url.strip() or not self.content:
            raise ValueError("PageImagePayload requires URL, requested URL and image bytes")
        if not self.ext.startswith("."):
            raise ValueError("PageImagePayload.ext must include a leading dot")
        if not self.sha256 or len(self.sha256) != 64:
            raise ValueError("PageImagePayload.sha256 must be a sha256 hex digest")

    def as_asset_mapping(self) -> dict[str, Any]:
        """Single adapter at the legacy asset-writer boundary."""
        return {
            "url": self.url,
            "requestedUrl": self.requested_url,
            "normalizedFromUrl": self.normalized_from_url,
            "ext": self.ext,
            "bytes": self.content,
            "contentType": self.content_type,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class PageImageFetchResult:
    """Typed terminal result for one page-owned image content.source."""

    requested_url: str
    resolved_url: str
    attempt_count: int
    status_code: int
    payload: PageImagePayload | None = None
    failure: PageImageFetchFailure | None = None

    def __post_init__(self) -> None:
        if not self.requested_url.strip() or self.attempt_count < 1:
            raise ValueError("PageImageFetchResult requires requested URL and positive attempt count")
        if (self.payload is None) == (self.failure is None):
            raise ValueError("PageImageFetchResult requires exactly one of payload or failure")

    @property
    def succeeded(self) -> bool:
        return self.payload is not None

    def as_failure_evidence(self, *, source_order: int) -> dict[str, object]:
        if self.succeeded or self.failure is None:
            raise ValueError("success does not have failure evidence")
        return {
            "sourceOrder": source_order,
            "requestedUrl": self.requested_url,
            "resolvedUrl": self.resolved_url,
            "failure": self.failure.value,
            "statusCode": self.status_code,
            "attemptCount": self.attempt_count,
        }

def _fetch_image_payload_once(url: str, *, min_bytes: int = 3000, max_bytes: int = 0) -> dict | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        try:
            path = Path(urllib.parse.unquote(parsed.path)).resolve()
            data_root = DATA_ROOT.resolve()
            if not path.is_relative_to(data_root) or not path.is_file():
                return None
            body = path.read_bytes()
            status = 200
            content_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }.get(path.suffix.lower(), "")
        except Exception:
            return None
    else:
        try:
            status, body, content_type = _http_get_bytes(url, max_bytes=max_bytes)
        except Exception:
            return None
    if status != 200 or len(body) < min_bytes:
        return None
    if int(max_bytes or 0) > 0 and len(body) > int(max_bytes):
        return None
    ext = sniff_image_ext(body, content_type)
    if ext is None:
        return None
    return {
        "url": url,
        "ext": ext,
        "bytes": body,
        "contentType": content_type,
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def fetch_image_payload(url: str, *, min_bytes: int = 3000, max_bytes: int = 0) -> dict | None:
    """下载单张图片但不落盘，返回 {url, ext, bytes, contentType, sha256}。

    供来源单元写入器（write_source_unit）把图片直接落进来源 assets/，
    避免对象级散落 images/。非 200 / 过小 / 非图片 / 网络异常一律返回 None。
    """
    for candidate in candidate_image_urls(url):
        payload = _fetch_image_payload_once(candidate, min_bytes=min_bytes, max_bytes=max_bytes)
        if payload is not None:
            payload["requestedUrl"] = url
            payload["normalizedFromUrl"] = url if candidate != url else ""
            return payload
    return None


def _fetch_page_image_payload_once(
    url: str,
    *,
    requested_url: str,
    normalized_from_url: str,
    min_bytes: int,
    max_bytes: int,
    timeout_seconds: int,
) -> PageImageFetchResult:
    """Fetch one page-owned candidate without collapsing the failure reason."""

    parsed = urllib.parse.urlparse(url)
    status = 0
    content_type = ""
    body = b""
    if parsed.scheme == "file":
        try:
            path = Path(urllib.parse.unquote(parsed.path)).resolve()
            data_root = DATA_ROOT.resolve()
            if not path.is_relative_to(data_root) or not path.is_file():
                return PageImageFetchResult(
                    requested_url=requested_url,
                    resolved_url=url,
                    attempt_count=1,
                    status_code=0,
                    failure=PageImageFetchFailure.FILE_ACCESS,
                )
            body = path.read_bytes()
            status = 200
            content_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }.get(path.suffix.lower(), "")
        except OSError:
            return PageImageFetchResult(
                requested_url=requested_url,
                resolved_url=url,
                attempt_count=1,
                status_code=0,
                failure=PageImageFetchFailure.FILE_ACCESS,
            )
    else:
        try:
            status, body, content_type = _http_get_bytes(
                url,
                timeout=timeout_seconds,
                max_bytes=max_bytes,
            )
        except Exception as exc:  # noqa: BLE001 - mapped to a closed contract below.
            failure = (
                PageImageFetchFailure.TOO_LARGE
                if max_bytes and "curl exit 63" in str(exc).lower()
                else PageImageFetchFailure.NETWORK
            )
            return PageImageFetchResult(
                requested_url=requested_url,
                resolved_url=url,
                attempt_count=1,
                status_code=0,
                failure=failure,
            )

    if status == 429:
        failure = PageImageFetchFailure.RATE_LIMITED
    elif status in {408, 500, 502, 503, 504}:
        failure = PageImageFetchFailure.UPSTREAM_UNAVAILABLE
    elif status != 200:
        failure = PageImageFetchFailure.HTTP_STATUS
    elif max_bytes and not body:
        # Both the HTTP client and curl intentionally suppress an oversized
        # body; this is distinct from a short but otherwise valid response.
        failure = PageImageFetchFailure.TOO_LARGE
    elif len(body) < min_bytes:
        failure = PageImageFetchFailure.TOO_SMALL
    elif max_bytes and len(body) > max_bytes:
        failure = PageImageFetchFailure.TOO_LARGE
    else:
        ext = sniff_image_ext(body, content_type)
        if ext is None:
            failure = PageImageFetchFailure.NOT_IMAGE
        else:
            return PageImageFetchResult(
                requested_url=requested_url,
                resolved_url=url,
                attempt_count=1,
                status_code=status,
                payload=PageImagePayload(
                    url=url,
                    requested_url=requested_url,
                    normalized_from_url=normalized_from_url,
                    ext=ext,
                    content=body,
                    content_type=content_type,
                    sha256=hashlib.sha256(body).hexdigest(),
                ),
            )
    return PageImageFetchResult(
        requested_url=requested_url,
        resolved_url=url,
        attempt_count=1,
        status_code=status,
        failure=failure,
    )


def fetch_page_image_payload(
    url: str,
    *,
    min_bytes: int = 3000,
    max_bytes: int = 0,
    max_attempts: int = PAGE_IMAGE_FETCH_MAX_ATTEMPTS,
    timeout_seconds: int = PAGE_IMAGE_DOWNLOAD_TIMEOUT_SECONDS,
) -> PageImageFetchResult:
    """Fetch an enumerated page image with typed, rate-limit-aware outcomes.

    This path is intentionally separate from generic image-work discovery:
    a source-page image is an enumerated part of the page evidence and cannot
    be silently lost. Its transfer budget is intentionally independent from
    the short generic-source timeout: large, rights-cleared Commons originals
    must get a realistic bounded download window. Retry only transient
    transport/upstream outcomes and return the final structured failure to the
    workflow gate.
    """

    requested_url = str(url or "").strip()
    resolved_timeout_seconds = max(3, int(timeout_seconds))
    if not requested_url:
        return PageImageFetchResult(
            requested_url="missing-url",
            resolved_url="",
            attempt_count=1,
            status_code=0,
            failure=PageImageFetchFailure.HTTP_STATUS,
        )
    attempts = 0
    last: PageImageFetchResult | None = None
    for candidate in candidate_image_urls(requested_url):
        normalized_from_url = requested_url if candidate != requested_url else ""
        for retry_index in range(max(1, max_attempts)):
            attempts += 1
            result = _fetch_page_image_payload_once(
                candidate,
                requested_url=requested_url,
                normalized_from_url=normalized_from_url,
                min_bytes=min_bytes,
                max_bytes=max_bytes,
                timeout_seconds=resolved_timeout_seconds,
            )
            result = replace(result, attempt_count=attempts)
            if result.succeeded:
                return result
            last = result
            if result.failure is None or not result.failure.retryable:
                break
            if retry_index + 1 < max(1, max_attempts):
                delay = min(
                    PAGE_IMAGE_FETCH_RETRY_BACKOFF_SECONDS * (2**retry_index),
                    30.0,
                )
                if delay:
                    time.sleep(delay)
    if last is not None:
        return last
    return PageImageFetchResult(
        requested_url=requested_url,
        resolved_url=requested_url,
        attempt_count=max(1, attempts),
        status_code=0,
        failure=PageImageFetchFailure.NETWORK,
    )


def fetch_image(
    url: str,
    images_dir: Path,
    *,
    index: int,
    min_bytes: int = 3000,
    max_bytes: int = 0,
) -> dict | None:
    """下载单张图片到 images_dir/img_<index>.<ext>。

    仅落真实图片二进制（按魔数判定，拒 HTML/错误页）；非 200 / 过小 / 非图片 / 网络异常
    一律返回 None（不抛），由调用方决定是否记账或重试。
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    payload = fetch_image_payload(url, min_bytes=min_bytes, max_bytes=max_bytes)
    if payload is None:
        return None
    body = payload["bytes"]
    content_type = payload.get("contentType") or ""
    ext = payload["ext"]
    status = 200
    file_name = f"img_{index:02d}{ext}"
    (images_dir / file_name).write_bytes(body)
    return {
        "url": payload.get("url") or url,
        "requestedUrl": payload.get("requestedUrl") or url,
        "fileName": file_name,
        "statusCode": status,
        "contentType": content_type,
        "bytes": len(body),
        "sha256": payload.get("sha256") or hashlib.sha256(body).hexdigest(),
    }
