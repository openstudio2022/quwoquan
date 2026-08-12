"""Release-bound public video delivery evidence helpers.

The Data readiness receipt owns immutable release identity and exact feed
readback.  This module binds one premium video from that receipt to the public
media plane and proves the bytes served by the environment are the same bytes
declared by the immutable release.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from quwoquan_ops.cli.lib.media_delivery_manifest import build_media_delivery_url
from quwoquan_ops.cli.lib.output_paths import output_root


DATA_READINESS_SCHEMA = "quwoquan_data.environment_release_readiness"
DELIVERY_EVIDENCE_SCHEMA = "quwoquan_ops.release_video_delivery_evidence"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTENT_RANGE_RE = re.compile(r"^bytes 0-(?P<end>[0-9]+)/(?P<total>[1-9][0-9]*)$")
RANGE_LAST_BYTE = 65_535
PUBLIC_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
PUBLIC_CACHE_KEY_HEADER = "X-QWQ-Media-Cache-Key"


class ReleaseVideoDeliveryError(ValueError):
    """The release or public delivery evidence cannot support readiness."""


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseVideoDeliveryError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseVideoDeliveryError(f"{label} must be a JSON object: {path}")
    return value


def _canonical_checksum(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _evidence_path(raw_ref: object, *, label: str) -> Path:
    ref = str(raw_ref or "").strip()
    root = output_root().expanduser().resolve()
    candidate = Path(ref).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ReleaseVideoDeliveryError(
            f"{label} must stay below QWQ_OUTPUT_ROOT"
        ) from exc
    if not candidate.is_file():
        raise ReleaseVideoDeliveryError(f"{label} is missing: {ref or '<empty>'}")
    return candidate


def resolve_readiness_path(raw_value: str) -> Path:
    """Resolve a CLI receipt ref without allowing evidence-root escape."""

    raw = str(raw_value or "").strip()
    if not raw:
        raise ReleaseVideoDeliveryError(
            "DATA_RELEASE_READINESS_RECEIPT is required for a release video canary"
        )
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return _evidence_path(candidate, label="Data readiness receipt")
    if candidate.parts and candidate.parts[0] == ".qwq_output":
        candidate = Path(__file__).resolve().parents[3] / candidate
        return _evidence_path(candidate, label="Data readiness receipt")
    return _evidence_path(candidate, label="Data readiness receipt")


def _string_set(value: object, *, label: str) -> set[str]:
    if not isinstance(value, list):
        raise ReleaseVideoDeliveryError(f"{label} must be an array")
    values = [str(item).strip() for item in value]
    if not values or any(not item for item in values) or len(values) != len(set(values)):
        raise ReleaseVideoDeliveryError(
            f"{label} must contain unique non-empty strings"
        )
    return set(values)


def _query_by_name(receipt: Mapping[str, Any], name: str) -> dict[str, Any]:
    queries = receipt.get("feedQueries")
    if not isinstance(queries, list):
        raise ReleaseVideoDeliveryError("Data readiness feedQueries must be an array")
    matches = [
        dict(item)
        for item in queries
        if isinstance(item, Mapping) and item.get("name") == name
    ]
    if len(matches) != 1:
        raise ReleaseVideoDeliveryError(
            f"Data readiness must contain exactly one {name} query"
        )
    query = matches[0]
    if (
        query.get("path") != "/content/feed"
        or query.get("status") != 200
        or query.get("releaseBound") is not True
    ):
        raise ReleaseVideoDeliveryError(f"Data readiness {name} is not release-bound")
    return query


def _owner_matches_post(owner_ref: object, post_ref: str) -> bool:
    owner = str(owner_ref or "").strip().strip("/")
    normalized_post = post_ref.strip().strip("/")
    return owner == normalized_post or owner == f"posts/{normalized_post}"


def load_release_content_identity(
    readiness_path: Path,
    *,
    expected_environment: str,
) -> dict[str, Any]:
    """Load the canonical Data receipt and its exact import/media authorities.

    All environment probes use this function instead of accepting parallel
    release, post, creator or media identities from environment variables.
    """

    root = output_root().expanduser().resolve()
    receipt_path = readiness_path.expanduser().resolve()
    try:
        receipt_ref = receipt_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ReleaseVideoDeliveryError(
            "Data readiness receipt must stay below QWQ_OUTPUT_ROOT"
        ) from exc
    receipt = _json_object(receipt_path, label="Data readiness receipt")
    release_id = str(receipt.get("releaseId") or "").strip()
    verify_run_id = str(receipt.get("verifyRunId") or "").strip()
    import_run_id = str(receipt.get("importRunId") or "").strip()
    expected_ref = (
        Path("env")
        / expected_environment
        / "runs"
        / "data-release"
        / release_id
        / verify_run_id
        / "release-readiness.json"
    ).as_posix()
    if receipt_ref != expected_ref:
        raise ReleaseVideoDeliveryError(
            f"Data readiness receipt path must be canonical: {expected_ref}"
        )
    required_values = {
        "schema": DATA_READINESS_SCHEMA,
        "environment": expected_environment,
        "releaseKind": "content",
        "sourceOwner": "qwq_data",
        "passed": True,
    }
    for field, expected in required_values.items():
        if receipt.get(field) != expected:
            raise ReleaseVideoDeliveryError(
                f"Data readiness {field}={receipt.get(field)!r}, expected {expected!r}"
            )
    if not release_id or not import_run_id or not verify_run_id:
        raise ReleaseVideoDeliveryError(
            "Data readiness release/import/verify identity is incomplete"
        )
    for field in ("manifestDigest", "mediaManifestDigest"):
        if SHA256_RE.fullmatch(str(receipt.get(field) or "")) is None:
            raise ReleaseVideoDeliveryError(f"Data readiness {field} is not canonical")
    checksum_document = dict(receipt)
    declared_checksum = str(checksum_document.pop("verificationChecksum", ""))
    if declared_checksum != _canonical_checksum(checksum_document):
        raise ReleaseVideoDeliveryError(
            "Data readiness verificationChecksum does not match the receipt"
        )

    release_post_ids = _string_set(receipt.get("postIds"), label="postIds")
    release_asset_ids = _string_set(
        receipt.get("mediaAssetIds"),
        label="mediaAssetIds",
    )
    creator_ids = _string_set(receipt.get("creatorIds"), label="creatorIds")
    tag_refs = _string_set(receipt.get("tagRefs"), label="tagRefs")

    attestation_path = (
        root / "data" / "releases" / release_id / "attestations" / "release.json"
    ).resolve()
    attestation = _json_object(attestation_path, label="release attestation")
    if any(
        (
            attestation.get("schema") != "quwoquan_data.release_attestation",
            attestation.get("releaseId") != release_id,
            attestation.get("releaseKind") != "content",
            attestation.get("sourceOwner") != "qwq_data",
            attestation.get("payloadSha256") != receipt.get("manifestDigest"),
        )
    ):
        raise ReleaseVideoDeliveryError("release attestation identity drift")

    import_path = _evidence_path(
        receipt.get("contentImportReportRef"),
        label="content import report",
    )
    import_report = _json_object(import_path, label="content import report")
    if any(
        (
            import_report.get("schema") != "quwoquan.content_import_report",
            import_report.get("status") != "imported",
            import_report.get("environment") != expected_environment,
            import_report.get("releaseId") != release_id,
            import_report.get("sourceOwner") != "qwq_data",
            import_report.get("manifestDigest") != receipt.get("manifestDigest"),
        )
    ):
        raise ReleaseVideoDeliveryError("content import report identity drift")
    raw_bindings = import_report.get("postBindings")
    if not isinstance(raw_bindings, list):
        raise ReleaseVideoDeliveryError(
            "content import report postBindings must be an array"
        )
    post_bindings: list[dict[str, Any]] = []
    observed_post_ids: set[str] = set()
    for index, raw_binding in enumerate(raw_bindings):
        if not isinstance(raw_binding, Mapping):
            raise ReleaseVideoDeliveryError(
                f"content import postBindings[{index}] must be an object"
            )
        binding = dict(raw_binding)
        post_id = str(binding.get("postId") or "").strip()
        post_ref = str(binding.get("postRef") or "").strip().strip("/")
        content_type = str(binding.get("contentType") or "").strip()
        author_id = str(binding.get("authorId") or "").strip()
        if (
            not post_id
            or not post_ref
            or content_type not in {"article", "image", "video"}
            or not author_id
            or post_id in observed_post_ids
        ):
            raise ReleaseVideoDeliveryError(
                f"content import postBindings[{index}] has invalid release identity"
            )
        observed_post_ids.add(post_id)
        post_bindings.append(binding)
    if observed_post_ids != release_post_ids:
        raise ReleaseVideoDeliveryError(
            "content import postBindings drift from Data readiness postIds"
        )

    expected_media_ref = (
        Path("data") / "releases" / release_id / "payload" / "media_manifest.json"
    ).as_posix()
    if receipt.get("mediaManifestRef") != expected_media_ref:
        raise ReleaseVideoDeliveryError(
            "Data readiness mediaManifestRef is not the canonical release payload"
        )
    media_path = _evidence_path(
        expected_media_ref,
        label="release media manifest",
    )
    media_bytes = media_path.read_bytes()
    observed_media_digest = f"sha256:{hashlib.sha256(media_bytes).hexdigest()}"
    if observed_media_digest != receipt.get("mediaManifestDigest"):
        raise ReleaseVideoDeliveryError(
            "release media manifest bytes do not match mediaManifestDigest"
        )
    media_manifest = _json_object(media_path, label="release media manifest")
    if any(
        (
            media_manifest.get("schema")
            != "quwoquan_data.release_media_manifest",
            media_manifest.get("releaseId") != release_id,
            media_manifest.get("sourceOwner") != "qwq_data",
        )
    ):
        raise ReleaseVideoDeliveryError("release media manifest identity drift")
    raw_assets = media_manifest.get("assets")
    if not isinstance(raw_assets, list):
        raise ReleaseVideoDeliveryError(
            "release media manifest assets must be an array"
        )
    assets: list[dict[str, Any]] = []
    observed_asset_ids: set[str] = set()
    for index, raw_asset in enumerate(raw_assets):
        if not isinstance(raw_asset, Mapping):
            raise ReleaseVideoDeliveryError(
                f"release media assets[{index}] must be an object"
            )
        asset = dict(raw_asset)
        asset_id = str(asset.get("assetId") or "").strip()
        if not asset_id or asset_id in observed_asset_ids:
            raise ReleaseVideoDeliveryError(
                f"release media assets[{index}] has invalid assetId"
            )
        observed_asset_ids.add(asset_id)
        assets.append(asset)
    if observed_asset_ids != release_asset_ids:
        raise ReleaseVideoDeliveryError(
            "release media manifest assets drift from Data readiness mediaAssetIds"
        )

    post_tag_refs: dict[str, set[str]] = {}
    payload_root = media_path.parent.resolve()
    for binding in post_bindings:
        post_ref = str(binding["postRef"]).strip().strip("/")
        tag_path = (payload_root / "objects" / "posts" / post_ref / "tag.refs.json").resolve()
        try:
            tag_path.relative_to(payload_root)
        except ValueError as exc:
            raise ReleaseVideoDeliveryError(
                f"release post tag refs escape canonical payload: {post_ref}"
            ) from exc
        tag_document = _json_object(tag_path, label="release post tag refs")
        raw_post_tags = tag_document.get("tagRefs")
        if not isinstance(raw_post_tags, list):
            raise ReleaseVideoDeliveryError(
                f"post {post_ref} tagRefs must be an array"
            )
        post_tag_values = [str(value).strip() for value in raw_post_tags]
        if any(not value for value in post_tag_values) or len(post_tag_values) != len(
            set(post_tag_values)
        ):
            raise ReleaseVideoDeliveryError(
                f"post {post_ref} tagRefs must contain unique non-empty strings"
            )
        post_tags = set(post_tag_values)
        if not post_tags.issubset(tag_refs):
            raise ReleaseVideoDeliveryError(
                f"release post {post_ref} tagRefs drift from Data readiness"
            )
        post_tag_refs[str(binding["postId"])] = post_tags

    return {
        "readinessReceiptPath": receipt_path,
        "readinessReceiptRef": receipt_ref,
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "manifestDigest": str(receipt["manifestDigest"]),
        "mediaManifestDigest": str(receipt["mediaManifestDigest"]),
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "receipt": receipt,
        "postIds": release_post_ids,
        "creatorIds": creator_ids,
        "tagRefs": tag_refs,
        "mediaAssetIds": release_asset_ids,
        "postBindings": post_bindings,
        "postTagRefs": post_tag_refs,
        "mediaAssets": assets,
        "contentImportReportPath": import_path,
        "mediaManifestPath": media_path,
        "releaseAttestationPath": attestation_path,
    }


def load_release_video_binding(
    readiness_path: Path,
    *,
    expected_environment: str,
    requested_work_id: str = "",
    requested_asset_id: str = "",
) -> dict[str, Any]:
    """Bind one premium video post and asset to the canonical Data receipt."""

    identity = load_release_content_identity(
        readiness_path,
        expected_environment=expected_environment,
    )
    receipt = identity["receipt"]
    release_id = str(identity["releaseId"])
    verify_run_id = str(identity["verifyRunId"])
    receipt_ref = str(identity["readinessReceiptRef"])
    release_post_ids = set(identity["postIds"])
    release_asset_ids = set(identity["mediaAssetIds"])
    typed_video = _query_by_name(receipt, "typed_video")
    premium = _query_by_name(receipt, "premium_stream")
    if re.fullmatch(
        r"identity=work&type=video&limit=[1-9][0-9]*",
        str(typed_video.get("query") or ""),
    ) is None:
        raise ReleaseVideoDeliveryError("typed_video exact query is not canonical")
    if re.fullmatch(
        r"sort=recommend&channelId=premium_stream&limit=[1-9][0-9]*",
        str(premium.get("query") or ""),
    ) is None:
        raise ReleaseVideoDeliveryError("premium_stream exact query is not canonical")
    candidate_post_ids = (
        _string_set(typed_video.get("matchedPostIds"), label="typed_video.matchedPostIds")
        & _string_set(premium.get("matchedPostIds"), label="premium_stream.matchedPostIds")
        & release_post_ids
    )
    requested_work = str(requested_work_id or "").strip()
    if requested_work:
        if requested_work not in candidate_post_ids:
            raise ReleaseVideoDeliveryError(
                "configured video workId is not in the release-bound video/premium intersection"
            )
        post_id = requested_work
    elif not candidate_post_ids:
        raise ReleaseVideoDeliveryError(
            "release must expose at least one premium video for playback canary"
        )
    else:
        # Multi-video releases pick a deterministic canary; operators may still
        # pin VIDEO_PLAYBACK_CANARY_WORK_ID / --video-work-id for a specific work.
        post_id = sorted(candidate_post_ids)[0]

    post_bindings = identity["postBindings"]
    matching_posts = [
        dict(item)
        for item in post_bindings
        if isinstance(item, Mapping)
        and item.get("postId") == post_id
        and item.get("contentType") == "video"
    ]
    if len(matching_posts) != 1:
        raise ReleaseVideoDeliveryError(
            "release video post must have exactly one canonical import binding"
        )
    post_ref = str(matching_posts[0].get("postRef") or "").strip()
    if not post_ref:
        raise ReleaseVideoDeliveryError("release video postRef is missing")

    assets = identity["mediaAssets"]
    candidates = [
        dict(item)
        for item in assets
        if isinstance(item, Mapping)
        and item.get("kind") == "video"
        and str(item.get("assetId") or "") in release_asset_ids
        and any(_owner_matches_post(owner, post_ref) for owner in item.get("ownerRefs") or [])
    ]
    requested_asset = str(requested_asset_id or "").strip()
    if requested_asset:
        candidates = [item for item in candidates if item.get("assetId") == requested_asset]
    if len(candidates) != 1:
        raise ReleaseVideoDeliveryError(
            "release video post must bind exactly one canonical video asset"
        )
    asset = candidates[0]
    asset_id = str(asset.get("assetId") or "").strip()
    public_slice_key = str(asset.get("publicSliceKey") or "").strip().lstrip("/")
    content_type = str(asset.get("contentType") or "").strip().lower()
    expected_hash = str(asset.get("sha256") or "").strip().lower()
    expected_bytes = asset.get("bytes")
    version = asset.get("version")
    if (
        not asset_id
        or not public_slice_key.startswith("media/video/s/")
        or not content_type.startswith("video/")
        or SHA256_RE.fullmatch(expected_hash) is None
        or not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes <= 0
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version <= 0
    ):
        raise ReleaseVideoDeliveryError("release video asset contract is invalid")

    return {
        "readinessReceiptRef": receipt_ref,
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "manifestDigest": str(receipt["manifestDigest"]),
        "mediaManifestDigest": str(receipt["mediaManifestDigest"]),
        "importRunId": str(receipt["importRunId"]),
        "verifyRunId": verify_run_id,
        "workId": post_id,
        "postId": post_id,
        "postRef": post_ref,
        "assetId": asset_id,
        "assetVersion": version,
        "publicSliceKey": public_slice_key,
        "expectedMimeType": content_type,
        "expectedBytes": expected_bytes,
        "expectedHash": expected_hash,
    }


def build_release_video_url(
    public_bases: dict[str, Any],
    binding: Mapping[str, Any],
) -> str:
    return build_media_delivery_url(
        public_bases,
        {
            "mediaType": "video",
            "publicSliceKey": binding["publicSliceKey"],
            "version": binding["assetVersion"],
        },
    )


def _normalized_mime(value: object) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def probe_https_video(
    url: str,
    *,
    expected_bytes: int,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Prove bytes, Range, CORS and one canonical public cache identity."""

    parsed_url = urlsplit(url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ReleaseVideoDeliveryError("public video probe requires an HTTPS URL")

    digest = hashlib.sha256()
    observed_bytes = 0
    full_request = urllib.request.Request(
        url,
        headers={"Accept": "video/*", "Connection": "close"},
    )
    with urllib.request.urlopen(full_request, timeout=max(1, timeout_seconds)) as response:
        full_status = int(response.status)
        full_headers = response.headers
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            observed_bytes += len(chunk)
            if observed_bytes > expected_bytes:
                raise ReleaseVideoDeliveryError(
                    "public video body exceeds immutable release bytes"
                )
            digest.update(chunk)
    full_content_length = str(full_headers.get("Content-Length") or "").strip()
    try:
        content_length = int(full_content_length)
    except ValueError as exc:
        raise ReleaseVideoDeliveryError(
            "public video full response lacks a valid Content-Length"
        ) from exc
    full_etag = str(full_headers.get("ETag") or "").strip()
    full_mime = _normalized_mime(full_headers.get("Content-Type"))
    full_cache_control = str(full_headers.get("Cache-Control") or "").strip()
    full_cors = str(full_headers.get("Access-Control-Allow-Origin") or "").strip()
    full_cache_key = str(full_headers.get(PUBLIC_CACHE_KEY_HEADER) or "").strip()

    range_request = urllib.request.Request(
        url,
        headers={
            "Accept": "video/*",
            "Connection": "close",
            "Range": f"bytes=0-{RANGE_LAST_BYTE}",
        },
    )
    with urllib.request.urlopen(range_request, timeout=max(1, timeout_seconds)) as response:
        range_status = int(response.status)
        range_headers = response.headers
        range_body = response.read(RANGE_LAST_BYTE + 2)
    range_etag = str(range_headers.get("ETag") or "").strip()
    content_range = str(range_headers.get("Content-Range") or "").strip()
    range_mime = _normalized_mime(range_headers.get("Content-Type"))
    range_cache_control = str(range_headers.get("Cache-Control") or "").strip()
    range_cors = str(range_headers.get("Access-Control-Allow-Origin") or "").strip()
    range_cache_key = str(range_headers.get(PUBLIC_CACHE_KEY_HEADER) or "").strip()

    signed_query = list(parse_qsl(parsed_url.query, keep_blank_values=True))
    signed_query.append(("sign", "qwq-invalid-readback-signature"))
    signed_url = urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            urlencode(signed_query),
            "",
        )
    )
    signed_request = urllib.request.Request(
        signed_url,
        headers={"Accept": "video/*", "Connection": "close"},
        method="HEAD",
    )
    try:
        with urllib.request.urlopen(
            signed_request,
            timeout=max(1, timeout_seconds),
        ) as response:
            signed_status = int(response.status)
            signed_headers = response.headers
    except urllib.error.HTTPError as exc:
        signed_status = int(exc.code)
        signed_headers = exc.headers or {}
    return {
        "tlsSystemTrust": True,
        "requestPath": parsed_url.path,
        "requestQuery": parsed_url.query,
        "fullStatus": full_status,
        "rangeStatus": range_status,
        "mimeType": full_mime,
        "rangeMimeType": range_mime,
        "contentLength": content_length,
        "observedBytes": observed_bytes,
        "contentRange": content_range,
        "rangeBytes": len(range_body),
        "etag": full_etag,
        "rangeEtag": range_etag,
        "observedHash": f"sha256:{digest.hexdigest()}",
        "rangeSha256": f"sha256:{hashlib.sha256(range_body).hexdigest()}",
        "cacheControl": full_cache_control,
        "rangeCacheControl": range_cache_control,
        "corsAllowOrigin": full_cors,
        "rangeCorsAllowOrigin": range_cors,
        "cacheKey": full_cache_key,
        "rangeCacheKey": range_cache_key,
        "signedQueryStatus": signed_status,
        "signedQueryCacheControl": str(
            signed_headers.get("Cache-Control") or ""
        ).strip(),
        "signedQueryCacheKey": str(
            signed_headers.get(PUBLIC_CACHE_KEY_HEADER) or ""
        ).strip(),
    }


def probe_duration_ms(url: str, *, timeout_seconds: int = 30) -> int:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ReleaseVideoDeliveryError("ffprobe is required for release video duration evidence")
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                url,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=max(1, timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        raise ReleaseVideoDeliveryError("ffprobe duration probe timed out") from exc
    if result.returncode != 0:
        raise ReleaseVideoDeliveryError(
            "ffprobe duration probe failed: " + (result.stderr or result.stdout).strip()
        )
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ReleaseVideoDeliveryError("ffprobe returned an invalid duration") from exc
    duration_ms = round(duration * 1000)
    if duration_ms <= 0:
        raise ReleaseVideoDeliveryError("release video duration must be positive")
    return duration_ms


def probe_first_frame(url: str, *, timeout_seconds: int = 30) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ReleaseVideoDeliveryError("ffmpeg is required for decoded first-frame evidence")
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-i",
                url,
                "-frames:v",
                "1",
                "-f",
                "null",
                "-",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=max(1, timeout_seconds),
        )
    except subprocess.TimeoutExpired as exc:
        raise ReleaseVideoDeliveryError("decoded first-frame probe timed out") from exc
    if result.returncode != 0:
        raise ReleaseVideoDeliveryError(
            "decoded first-frame probe failed: " + (result.stderr or result.stdout).strip()
        )
    return True


def validate_delivery(
    delivery: Mapping[str, Any],
    *,
    expected_mime_type: str,
    expected_bytes: int,
    expected_hash: str,
    expected_public_slice_key: str,
) -> None:
    issues: list[str] = []
    if delivery.get("tlsSystemTrust") is not True:
        issues.append("system TLS trust was not used")
    if delivery.get("fullStatus") != 200:
        issues.append("full video GET must return HTTP 200")
    if delivery.get("rangeStatus") != 206:
        issues.append("video byte-range GET must return HTTP 206")
    expected_mime = _normalized_mime(expected_mime_type)
    if delivery.get("mimeType") != expected_mime:
        issues.append("full video MIME drifts from immutable release")
    if delivery.get("rangeMimeType") != expected_mime:
        issues.append("range video MIME drifts from immutable release")
    if delivery.get("contentLength") != expected_bytes:
        issues.append("Content-Length drifts from immutable release bytes")
    if delivery.get("observedBytes") != expected_bytes:
        issues.append("downloaded video bytes drift from immutable release bytes")
    if delivery.get("observedHash") != expected_hash:
        issues.append("downloaded video sha256 drifts from immutable release")
    etag = str(delivery.get("etag") or "").strip()
    range_etag = str(delivery.get("rangeEtag") or "").strip()
    if not etag or not range_etag:
        issues.append("full and range responses must expose ETag")
    elif etag != range_etag:
        issues.append("full and range response ETag values differ")
    content_range = str(delivery.get("contentRange") or "")
    match = CONTENT_RANGE_RE.fullmatch(content_range)
    if match is None or int(match.group("total")) != expected_bytes:
        issues.append("Content-Range total drifts from immutable release bytes")
    elif delivery.get("rangeBytes") != int(match.group("end")) + 1:
        issues.append("range response body length does not match Content-Range")
    if SHA256_RE.fullmatch(str(delivery.get("rangeSha256") or "")) is None:
        issues.append("range response sha256 evidence is missing")
    expected_path = "/" + str(expected_public_slice_key).strip().lstrip("/")
    if delivery.get("requestPath") != expected_path:
        issues.append("public request path drifts from canonical publicSliceKey")
    if str(delivery.get("requestQuery") or ""):
        issues.append("path-versioned public video URL must not carry a query")
    for field in ("cacheControl", "rangeCacheControl"):
        if not _is_public_immutable_cache_control(delivery.get(field)):
            issues.append(f"{field} must prove one-year public immutable caching")
    for field in ("corsAllowOrigin", "rangeCorsAllowOrigin"):
        if delivery.get(field) != "*":
            issues.append(f"{field} must expose the canonical public CORS policy")
    for field in ("cacheKey", "rangeCacheKey"):
        if delivery.get(field) != expected_path:
            issues.append(f"{field} must equal the path-versioned public cache identity")
    signed_status = delivery.get("signedQueryStatus")
    if (
        not isinstance(signed_status, int)
        or isinstance(signed_status, bool)
        or signed_status < 200
        or signed_status >= 500
    ):
        issues.append("signed-query isolation probe must reach a bounded HTTP terminal status")
    if not _has_cache_directive(
        delivery.get("signedQueryCacheControl"),
        "no-store",
    ):
        issues.append("signed-query response must be no-store")
    if str(delivery.get("signedQueryCacheKey") or ""):
        issues.append("signed-query response must not expose a public cache key")
    if issues:
        raise ReleaseVideoDeliveryError("; ".join(issues))


def _cache_directives(value: object) -> set[str]:
    return {
        directive.strip().lower()
        for directive in str(value or "").split(",")
        if directive.strip()
    }


def _has_cache_directive(value: object, directive: str) -> bool:
    return directive.lower() in _cache_directives(value)


def _is_public_immutable_cache_control(value: object) -> bool:
    directives = _cache_directives(value)
    return (
        "public" in directives
        and "immutable" in directives
        and "max-age=31536000" in directives
        and "no-store" not in directives
    )


__all__ = [
    "DELIVERY_EVIDENCE_SCHEMA",
    "ReleaseVideoDeliveryError",
    "build_release_video_url",
    "load_release_video_binding",
    "probe_duration_ms",
    "probe_first_frame",
    "probe_https_video",
    "resolve_readiness_path",
    "validate_delivery",
]
