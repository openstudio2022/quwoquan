"""Download and admit directly sourced real videos from a frozen video plan."""
from __future__ import annotations

import hashlib
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from core.content_source_registry import load_content_source_registry
from core.io import write_json
from core.paths import execution_shared_dir
from core.runtime_policy import DEFAULT_RUNTIME_PROFILE_ID, load_runtime_policy
from core.video_source_admission import (
    assert_video_acquisition_path_allowed,
    assert_video_distribution_use_allowed,
)

from content.post.video.source_video import distribution_decision_for_admission
from content.source.professional_video_receipt import (
    resolve_professional_video_candidate,
)
from content.source.sourced_video_admission import probe_audio_stream
from content.source.sourced_video_unit import write_admitted_sourced_video_unit

_MAX_SOURCE_VIDEO_BYTES = 512 * 1024 * 1024
_SOURCE_VIDEO_DOWNLOAD_ATTEMPTS = 4


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


class _RecordingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Record only public HTTPS redirects; never attach a cookie jar or credentials."""

    def __init__(self) -> None:
        super().__init__()
        self.redirects: list[dict[str, object]] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        source = str(req.full_url)
        target = str(newurl)
        if (
            urllib.parse.urlparse(source).scheme != "https"
            or urllib.parse.urlparse(target).scheme != "https"
        ):
            raise ValueError("sourced video redirect must remain on HTTPS")
        self.redirects.append(
            {
                "status": int(code),
                "fromUrl": source,
                "toUrl": target,
            }
        )
        return super().redirect_request(req, fp, code, msg, headers, target)


def _download_sourced_video(url: str, destination: Path) -> dict[str, object]:
    """Download a public video and return credential-free access evidence."""

    read_timeout_seconds = load_runtime_policy(
        DEFAULT_RUNTIME_PROFILE_ID
    ).source_video_read_timeout_seconds
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    partial.unlink(missing_ok=True)
    last_error: BaseException | None = None
    redirects = _RecordingRedirectHandler()
    # Deliberately omit HTTPCookieProcessor, HTTPBasicAuthHandler and proxy
    # credential handlers: this downloader only accesses anonymous public media.
    opener = urllib.request.build_opener(redirects)
    try:
        for attempt in range(1, _SOURCE_VIDEO_DOWNLOAD_ATTEMPTS + 1):
            written = partial.stat().st_size if partial.is_file() else 0
            headers = {"User-Agent": "quwoquan-data/1.0"}
            if written:
                headers["Range"] = f"bytes={written}-"
            request = urllib.request.Request(url, headers=headers)
            try:
                with opener.open(
                    request,
                    timeout=read_timeout_seconds,
                ) as response:
                    status = int(response.getcode() or 200)
                    content_type = str(
                        response.headers.get("Content-Type") or ""
                    ).lower()
                    if not (
                        content_type.startswith("video/")
                        or content_type == "application/octet-stream"
                    ):
                        raise ValueError(
                            f"sourced video response is not video: {content_type}"
                        )
                    if written and status != 206:
                        partial.unlink(missing_ok=True)
                        written = 0
                    content_length = int(
                        response.headers.get("Content-Length") or 0
                    )
                    response_headers = {
                        name: str(response.headers.get(name) or "")
                        for name in ("Content-Type", "Content-Length", "ETag", "Last-Modified")
                        if response.headers.get(name)
                    }
                    if written + content_length > _MAX_SOURCE_VIDEO_BYTES:
                        raise ValueError(
                            "sourced video exceeds maximum download size"
                        )
                    with partial.open("ab" if written else "wb") as output:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > _MAX_SOURCE_VIDEO_BYTES:
                                raise ValueError(
                                    "sourced video exceeds maximum download size"
                                )
                            output.write(chunk)
                if written <= 0:
                    raise ValueError("sourced video download is empty")
                partial.replace(destination)
                return {
                    "schema": "quwoquan_data.anonymous_video_download",
                    "anonymousAccess": True,
                    "credentialAssertion": "no_cookie_no_api_key_no_account_session",
                    "requestedUrl": url,
                    "finalUrl": str(response.geturl()),
                    "redirectChain": redirects.redirects,
                    "httpStatus": status,
                    "contentType": content_type,
                    "contentLength": written,
                    "responseHeaders": response_headers,
                    "sha256": _file_sha256(destination),
                }
            except (TimeoutError, OSError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt >= _SOURCE_VIDEO_DOWNLOAD_ATTEMPTS:
                    raise
                time.sleep(min(8, 2 ** (attempt - 1)))
        raise RuntimeError("sourced video download retry loop exhausted") from last_error
    finally:
        if not destination.is_file():
            partial.unlink(missing_ok=True)


def fetch_admitted_sourced_videos(
    *,
    execution_id: str,
    entity_id: str,
    entity_type: str,
    candidates: list[dict[str, Any]],
    professional_acquisition_root: Path | None = None,
) -> list[Path]:
    """Materialize admitted source units for directly downloadable videos."""
    evidence_paths: list[Path] = []
    registry = load_content_source_registry()
    for candidate in candidates:
        assert_video_distribution_use_allowed(
            registry,
            source_id=str(candidate.get("sourceId") or ""),
            source_kind=str(candidate.get("sourceKind") or ""),
            publication_admission=str(
                candidate.get("publicationAdmission") or ""
            ),
        )
        asset_url = str(candidate.get("assetUrl") or "").strip()
        professional = bool(
            str(candidate.get("professionalAcquisitionReceiptRef") or "").strip()
        )
        if not professional:
            assert_video_acquisition_path_allowed(
                registry,
                source_id=str(candidate.get("sourceId") or ""),
                source_kind=str(candidate.get("sourceKind") or ""),
                acquisition_path="public_direct",
            )
        delete_after_admission = not professional
        if professional:
            if professional_acquisition_root is None:
                raise ValueError(
                    "professional video candidate requires the frozen capsule "
                    "professional_acquisition_root"
                )
            download_path = resolve_professional_video_candidate(
                candidate,
                root=professional_acquisition_root,
            )
            suffix = download_path.suffix
            digest = hashlib.sha256(
                str(candidate.get("professionalContentSha256") or "").encode("utf-8")
            ).hexdigest()[:16]
            download_evidence: dict[str, object] = {
                "schema": "quwoquan_data.professional_video_acquisition_consumption",
                "networkRefetchAttempted": False,
                "credentialAssertion": "receipt_bound_local_cas_no_network_refetch",
                "requestedUrl": asset_url,
                "acquisitionReceiptRef": str(
                    candidate.get("professionalAcquisitionReceiptRef") or ""
                ),
                "professionalAssetId": str(candidate.get("professionalAssetId") or ""),
                "sha256": _file_sha256(download_path),
            }
            download_evidence_dir = "professional_video_acquisition_consumption"
        else:
            if not asset_url.startswith("https://"):
                raise ValueError("sourced video assetUrl must use https")
            suffix = Path(urllib.parse.urlparse(asset_url).path).suffix or ".video"
            digest = hashlib.sha256(asset_url.encode("utf-8")).hexdigest()[:16]
            download_path = (
                execution_shared_dir(execution_id)
                / "source_video_downloads"
                / f"{digest}{suffix}"
            )
            download_evidence_dir = "anonymous_video_downloads"
            try:
                download_evidence = _download_sourced_video(asset_url, download_path)
            except (OSError, TimeoutError, ValueError, urllib.error.URLError) as exc:
                write_json(
                    execution_shared_dir(execution_id)
                    / download_evidence_dir
                    / f"{digest}.json",
                    {
                        "schema": "quwoquan_data.anonymous_video_download",
                        "anonymousAccess": True,
                        "credentialAssertion": "no_cookie_no_api_key_no_account_session",
                        "executionId": execution_id,
                        "entityId": entity_id,
                        "sourceId": str(candidate.get("sourceId") or ""),
                        "sourcePostUrl": str(candidate.get("sourcePostUrl") or ""),
                        "requestedUrl": asset_url,
                        "downloadOutcome": "rejected",
                        "rightsStatusBeforeAdmission": str(
                            candidate.get("rightsStatus") or "unverified"
                        ),
                        "rejection": f"{type(exc).__name__}: {exc}",
                    },
                )
                raise
        try:
            audio_probe = probe_audio_stream(download_path)
            has_audio = audio_probe.get("hasAudio") is True
            terms_url = str(candidate.get("termsUrl") or "").strip()
            publication_admission = str(
                candidate.get("publicationAdmission") or ""
            )
            distribution_decision = str(
                candidate.get("distributionDecision") or ""
            ) or distribution_decision_for_admission(publication_admission)
            research_release = distribution_decision == "research_allowed"
            audio_rights_status = str(
                candidate.get("audioRightsStatus")
                or (
                    "unverified"
                    if has_audio and research_release
                    else "licensed"
                    if has_audio
                    else "no_audio"
                )
            )
            audio_proof = str(
                candidate.get("audioAuthorizationProofUrl") or ""
            ).strip() or (
                None if audio_rights_status == "unverified" else terms_url or None
            )
            evidence_paths.append(
                write_admitted_sourced_video_unit(
                    execution_id=execution_id,
                    object_ref=entity_id,
                    source_unit=candidate,
                    source_video_path=download_path,
                    original_creator_name=str(
                        candidate.get("originalCreatorName") or ""
                    ),
                    platform=str(candidate.get("platform") or ""),
                    source_post_url=str(candidate.get("sourcePostUrl") or ""),
                    original_asset_url=str(
                        candidate.get("originalAssetUrl") or asset_url
                    ),
                    attribution_text=str(candidate.get("attributionText") or ""),
                    rights_basis=str(candidate.get("rightsBasis") or ""),
                    commercial_authorization_status=str(
                        candidate.get("commercialAuthorizationStatus") or ""
                    ),
                    distribution_decision=distribution_decision,
                    authorization_proof_url=str(
                        candidate.get("authorizationProofUrl") or ""
                    )
                    or None,
                    terms_url=terms_url or None,
                    audio_rights_status=audio_rights_status,
                    audio_authorization_proof_url=audio_proof,
                    model_release_status=str(
                        candidate.get("modelReleaseStatus") or "not_required"
                    ),
                    property_release_status=str(
                        candidate.get("propertyReleaseStatus") or "not_required"
                    ),
                    takedown_policy=str(
                        candidate.get("takedownPolicy")
                        or "quwoquan_standard_notice_and_takedown"
                    ),
                    entity_type=entity_type,
                )
            )
            write_json(
                execution_shared_dir(execution_id)
                / download_evidence_dir
                / f"{digest}.json",
                {
                    **download_evidence,
                    "executionId": execution_id,
                    "entityId": entity_id,
                    "sourceId": str(candidate.get("sourceId") or ""),
                    "sourcePostUrl": str(candidate.get("sourcePostUrl") or ""),
                    "downloadOutcome": "admitted",
                    "rightsStatusBeforeAdmission": str(
                        candidate.get("rightsStatus") or "unverified"
                    ),
                    "rightsStatusAfterAdmission": str(
                        candidate.get("rightsStatus") or "unverified"
                    )
                    if research_release
                    else "verified",
                },
            )
        finally:
            if delete_after_admission:
                download_path.unlink(missing_ok=True)
    downloads_dir = execution_shared_dir(execution_id) / "source_video_downloads"
    if downloads_dir.is_dir() and not any(downloads_dir.iterdir()):
        shutil.rmtree(downloads_dir)
    return evidence_paths
