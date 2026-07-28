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

from content.source.sourced_video_admission import probe_audio_stream
from content.source.sourced_video_unit import write_admitted_sourced_video_unit
from core.content_source_registry import load_content_source_registry
from core.paths import execution_shared_dir
from core.runtime_policy import DEFAULT_RUNTIME_PROFILE_ID, load_runtime_policy
from core.video_source_admission import assert_video_source_admitted


_MAX_SOURCE_VIDEO_BYTES = 512 * 1024 * 1024
_SOURCE_VIDEO_DOWNLOAD_ATTEMPTS = 4


def _download_sourced_video(url: str, destination: Path) -> None:
    read_timeout_seconds = load_runtime_policy(
        DEFAULT_RUNTIME_PROFILE_ID
    ).source_video_read_timeout_seconds
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    partial.unlink(missing_ok=True)
    last_error: BaseException | None = None
    try:
        for attempt in range(1, _SOURCE_VIDEO_DOWNLOAD_ATTEMPTS + 1):
            written = partial.stat().st_size if partial.is_file() else 0
            headers = {"User-Agent": "quwoquan-data/1.0"}
            if written:
                headers["Range"] = f"bytes={written}-"
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(
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
                return
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
) -> list[Path]:
    """Materialize admitted source units for directly downloadable videos."""
    evidence_paths: list[Path] = []
    for candidate in candidates:
        assert_video_source_admitted(
            load_content_source_registry(),
            source_id=str(candidate.get("sourceId") or ""),
            source_kind=str(candidate.get("sourceKind") or ""),
            publication_admission=str(
                candidate.get("publicationAdmission") or ""
            ),
        )
        asset_url = str(candidate.get("assetUrl") or "").strip()
        if not asset_url.startswith("https://"):
            raise ValueError("sourced video assetUrl must use https")
        suffix = Path(urllib.parse.urlparse(asset_url).path).suffix or ".video"
        digest = hashlib.sha256(asset_url.encode("utf-8")).hexdigest()[:16]
        download_path = (
            execution_shared_dir(execution_id)
            / "source_video_downloads"
            / f"{digest}{suffix}"
        )
        _download_sourced_video(asset_url, download_path)
        try:
            audio_probe = probe_audio_stream(download_path)
            has_audio = audio_probe.get("hasAudio") is True
            terms_url = str(candidate.get("termsUrl") or "").strip()
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
                    original_asset_url=asset_url,
                    attribution_text=str(candidate.get("attributionText") or ""),
                    rights_basis=str(candidate.get("rightsBasis") or ""),
                    commercial_authorization_status=str(
                        candidate.get("commercialAuthorizationStatus") or ""
                    ),
                    publication_admission=str(
                        candidate.get("publicationAdmission") or ""
                    ),
                    authorization_proof_url=str(
                        candidate.get("authorizationProofUrl") or ""
                    )
                    or None,
                    terms_url=terms_url or None,
                    risk_acceptance_id=None,
                    audio_rights_status="licensed" if has_audio else "no_audio",
                    audio_authorization_proof_url=terms_url if has_audio else None,
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
        finally:
            download_path.unlink(missing_ok=True)
    downloads_dir = execution_shared_dir(execution_id) / "source_video_downloads"
    if downloads_dir.is_dir() and not any(downloads_dir.iterdir()):
        shutil.rmtree(downloads_dir)
    return evidence_paths
