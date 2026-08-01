#!/usr/bin/env python3
# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-001
# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003
# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-005
"""验证真实对象存储、媒体处理和原子发布的 Gamma/Beta 用户旅程。"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import ipaddress
import json
import os
import subprocess
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Callable

from report_feedback_probe_support import (
    LOCAL_TARGETS,
    REPO_ROOT,
    ProbeClient,
    ProbeFailure,
    media_viewer_session as build_media_viewer_session,
    moderation_operator_session as build_moderation_operator_session,
    put_presigned_object,
    reporter_session as build_reporter_session,
)


SCHEMA = "content-media-publication-lifecycle-probe-report"
SCENARIO = "content.media_publication.lifecycle"
_PNG_PAYLOAD = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
    "iZk9HQAAAABJRU5ErkJggg=="
)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _data(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    nested = payload.get("data")
    return nested if isinstance(nested, dict) else payload


def _required_text(payload: dict[str, Any] | None, *keys: str) -> str:
    source = _data(payload)
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    raise ProbeFailure(
        "contract_mismatch",
        f"response is missing one of required fields: {', '.join(keys)}",
    )


def _error_code(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates: list[dict[str, Any]] = [payload, _data(payload)]
    nested_error = payload.get("error")
    if isinstance(nested_error, dict):
        candidates.append(nested_error)
    for candidate in candidates:
        for key in ("code", "errorCode", "error_code"):
            value = str(candidate.get(key) or "").strip()
            if value:
                return value
    return ""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("beta", "gamma", "prod"), required=True)
    parser.add_argument(
        "--target-name",
        default="",
        help="拓扑 target；仅 prod-sim 可使用受控本地 canary 会话。",
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--moderation-base-url",
        default="",
        help="仅本地 lifecycle 使用的 content-service loopback origin。",
    )
    parser.add_argument(
        "--mode",
        choices=("read-only", "lifecycle"),
        default="read-only",
    )
    parser.add_argument(
        "--scenario",
        choices=("all", "photo", "video", "recovery"),
        default="all",
    )
    parser.add_argument(
        "--auth-token-env",
        default="PROD_ACCEPTANCE_AUTH_TOKEN",
    )
    parser.add_argument("--processing-timeout-seconds", type=float, default=120.0)
    parser.add_argument(
        "--report",
        default=".qwq_output/env/repo/runs/content-media-publication/report.json",
    )
    args = parser.parse_args()
    if args.mode == "lifecycle":
        parsed = urllib.parse.urlparse(args.moderation_base_url)
        host = parsed.hostname or ""
        loopback = host == "localhost"
        if host and not loopback:
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = False
        if (
            parsed.scheme != "http"
            or not loopback
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            parser.error(
                "--moderation-base-url must be an origin-only loopback HTTP URL "
                "for lifecycle mode"
            )
    return args


def _render_probe_video() -> bytes:
    """使用 FFmpeg 合成最小真实 H.264/AAC 上传源，避免 fixture 字节绕过处理器。"""

    with tempfile.TemporaryDirectory(prefix="qwq-media-probe-") as directory:
        output = Path(directory) / "source.mp4"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=navy:s=320x180:r=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=44100",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProbeFailure(
                "ffmpeg_missing",
                "media lifecycle probe requires ffmpeg on the verification runner",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProbeFailure(
                "ffmpeg_timeout",
                "media lifecycle probe source generation timed out",
            ) from exc
        if result.returncode != 0 or not output.is_file():
            raise ProbeFailure(
                "ffmpeg_failed",
                "media lifecycle probe could not create a H.264/AAC source",
            )
        return output.read_bytes()


def _init_upload(
    client: ProbeClient,
    *,
    media_type: str,
    content_type: str,
    payload: bytes,
    idempotency_key: str,
) -> dict[str, Any]:
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    body = {
        "mediaType": media_type,
        "mimeType": content_type,
        "fileSize": len(payload),
        "expectedSha256": digest,
    }
    _, initialized = _request_with_transport_retry(
        client,
        "POST",
        "/content/media/uploads:init",
        operation_id="InitMediaUpload",
        body=body,
        idempotency_key=idempotency_key,
    )
    _, replayed = _request_with_transport_retry(
        client,
        "POST",
        "/content/media/uploads:init",
        operation_id="InitMediaUpload",
        body=body,
        idempotency_key=idempotency_key,
    )
    session_id = _required_text(initialized, "sessionId")
    if _required_text(replayed, "sessionId") != session_id:
        raise ProbeFailure(
            "idempotency_drift",
            "InitMediaUpload replay returned a different upload session",
        )
    return {
        "sessionId": session_id,
        "uploadUrl": _required_text(initialized, "uploadUrl", "presignUrl"),
        "sha256": digest,
    }


def _request_with_transport_retry(
    client: ProbeClient,
    method: str,
    path: str,
    *,
    operation_id: str,
    expected_statuses: frozenset[int] = frozenset({200}),
    body: dict[str, Any] | None = None,
    idempotency_key: str = "",
    max_attempts: int = 3,
) -> tuple[int, dict[str, Any] | None]:
    retryable_statuses = frozenset({502, 503, 504})
    attempts = max(1, max_attempts)
    last_status = 0
    for attempt in range(1, attempts + 1):
        status, response = client.request(
            method,
            path,
            operation_id=operation_id,
            expected_statuses=expected_statuses | retryable_statuses,
            allow_non_json_statuses=retryable_statuses,
            body=body,
            idempotency_key=idempotency_key,
        )
        if status in expected_statuses:
            return status, response
        last_status = status
        if attempt < attempts:
            time.sleep(1.0)
    raise ProbeFailure(
        "gateway_unavailable",
        f"{method} {path} remained HTTP {last_status} after {attempts} attempts",
    )


def _upload_complete_and_wait(
    client: ProbeClient,
    *,
    media_type: str,
    content_type: str,
    payload: bytes,
    idempotency_prefix: str,
    access_policy: str,
) -> tuple[str, dict[str, Any]]:
    initialized = _init_upload(
        client,
        media_type=media_type,
        content_type=content_type,
        payload=payload,
        idempotency_key=f"{idempotency_prefix}-init",
    )
    put_presigned_object(
        upload_url=initialized["uploadUrl"],
        payload=payload,
        content_type=content_type,
        sha256_digest=initialized["sha256"],
    )
    complete_path = (
        f"/content/media/uploads/{urllib.parse.quote(initialized['sessionId'])}:complete"
    )
    _, completed = _request_with_transport_retry(
        client,
        "POST",
        complete_path,
        operation_id="CompleteMediaUpload",
        body={"accessPolicy": access_policy},
        idempotency_key=f"{idempotency_prefix}-complete",
    )
    _, replayed = _request_with_transport_retry(
        client,
        "POST",
        complete_path,
        operation_id="CompleteMediaUpload",
        body={"accessPolicy": access_policy},
        idempotency_key=f"{idempotency_prefix}-complete",
    )
    asset_id = _required_text(completed, "assetId", "mediaId")
    if _required_text(replayed, "assetId", "mediaId") != asset_id:
        raise ProbeFailure(
            "idempotency_drift",
            "CompleteMediaUpload replay returned a different MediaAsset",
        )
    # owner-only MediaAsset 不得通过 public/internal 旁路轮询 processing 状态；
    # 后续 PublishIntent 会按 metadata 的 media_not_ready recovery.action 重试。
    return asset_id, _data(completed)


def _upload_complete_lost_response_and_wait(
    client: ProbeClient,
    *,
    media_type: str,
    content_type: str,
    payload: bytes,
    idempotency_prefix: str,
    access_policy: str,
) -> tuple[str, dict[str, Any]]:
    """丢弃 complete 响应后只按权威 session 状态恢复，不重做上传。"""
    initialized = _init_upload(
        client,
        media_type=media_type,
        content_type=content_type,
        payload=payload,
        idempotency_key=f"{idempotency_prefix}-init",
    )
    put_presigned_object(
        upload_url=initialized["uploadUrl"],
        payload=payload,
        content_type=content_type,
        sha256_digest=initialized["sha256"],
    )
    complete_path = (
        f"/content/media/uploads/{urllib.parse.quote(initialized['sessionId'])}:complete"
    )
    # 模拟客户端在服务端已提交后丢失响应：请求确实完成，但调用方故意不用其 body。
    first_status, _ = client.request(
        "POST",
        complete_path,
        operation_id="CompleteMediaUpload",
        expected_statuses=frozenset({200, 502, 503, 504}),
        allow_non_json_statuses=frozenset({502, 503, 504}),
        body={"accessPolicy": access_policy},
        idempotency_key=f"{idempotency_prefix}-complete",
    )
    _, authoritative = _request_with_transport_retry(
        client,
        "GET",
        f"/content/media/uploads/{urllib.parse.quote(initialized['sessionId'])}",
        operation_id="GetMediaUploadSession",
    )
    session = _data(authoritative)
    if str(session.get("status") or "").strip() != "completed":
        if first_status == 200:
            raise ProbeFailure(
                "complete_reconciliation_failed",
                "successful complete response did not commit the upload session",
            )
        _request_with_transport_retry(
            client,
            "POST",
            complete_path,
            operation_id="CompleteMediaUpload",
            body={"accessPolicy": access_policy},
            idempotency_key=f"{idempotency_prefix}-complete",
        )
        _, authoritative = _request_with_transport_retry(
            client,
            "GET",
            f"/content/media/uploads/{urllib.parse.quote(initialized['sessionId'])}",
            operation_id="GetMediaUploadSession",
        )
        session = _data(authoritative)
    if str(session.get("status") or "").strip() != "completed":
        raise ProbeFailure(
            "complete_reconciliation_failed",
            "authoritative upload session did not reach completed after lost response",
        )
    asset_id = _required_text(session, "assetId", "mediaId")
    return asset_id, session


def _discard_unreferenced_asset(
    client: ProbeClient,
    *,
    owner_query_client: ProbeClient,
    asset_id: str,
    idempotency_key: str,
) -> None:
    path = f"/content/media/{urllib.parse.quote(asset_id)}"
    _, discarded = client.request(
        "DELETE",
        path,
        operation_id="DiscardMediaAsset",
        idempotency_key=idempotency_key,
    )
    result = _data(discarded)
    if (
        _required_text(result, "mediaId") != asset_id
        or _required_text(result, "status") != "deleted"
        or bool(result.get("replayed"))
    ):
        raise ProbeFailure(
            "media_discard_failed",
            "first unreferenced MediaAsset discard did not return deleted",
        )
    _, replayed = client.request(
        "DELETE",
        path,
        operation_id="DiscardMediaAsset",
        idempotency_key=idempotency_key,
    )
    replay = _data(replayed)
    if (
        _required_text(replay, "mediaId") != asset_id
        or _required_text(replay, "status") != "deleted"
        or not bool(replay.get("replayed"))
    ):
        raise ProbeFailure(
            "media_discard_replay_failed",
            "MediaAsset discard did not replay its durable receipt",
        )
    status, payload = owner_query_client.request(
        "GET",
        f"/internal/content/media/{urllib.parse.quote(asset_id)}",
        operation_id="GetOwnedMediaAsset",
        expected_statuses=frozenset({404}),
    )
    if status != 404 or _error_code(payload) != "CONTENT.USER.media_not_found":
        raise ProbeFailure(
            "media_discard_readback_failed",
            "discarded MediaAsset remained owner-readable",
        )


def _select_auto_video_cover(
    client: ProbeClient,
    *,
    asset_id: str,
    idempotency_key: str,
    processing_timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + processing_timeout_seconds
    while time.monotonic() < deadline:
        status, payload = client.request(
            "POST",
            f"/content/media/{urllib.parse.quote(asset_id)}/cover:auto",
            operation_id="SelectAutoVideoCover",
            expected_statuses=frozenset({200, 400, 409}),
            body={},
            idempotency_key=idempotency_key,
        )
        if status in {400, 409}:
            if _error_code(payload) not in {
                "CONTENT.USER.media_not_ready",
                "CONTENT.USER.version_conflict",
            }:
                raise ProbeFailure(
                    "cover_selection_failed",
                    "automatic cover was rejected for a non-retryable reason",
                )
            time.sleep(1.0)
            continue
        selection = _data(payload)
        if (
            _required_text(selection, "mediaId") != asset_id
            or _required_text(selection, "coverStrategy") != "first_frame"
            or not _required_text(selection, "coverUrl", "thumbnailUrl")
        ):
            raise ProbeFailure(
                "cover_selection_failed",
                "automatic video cover selection did not return the ready asset cover",
            )
        return
    raise ProbeFailure(
        "processing_timeout",
        f"video asset {asset_id} did not become cover-selectable within "
        f"{processing_timeout_seconds}s",
    )


def _verify_original_access_denial(
    viewer_client: ProbeClient,
    *,
    image_asset_id: str,
    idempotency_prefix: str,
) -> None:
    """验证 referenced_post 策略对不可见 private Post 稳定返回 403。"""

    denied_status, denied = viewer_client.request(
        "POST",
        f"/content/media/{urllib.parse.quote(image_asset_id)}/original:access",
        operation_id="RequestOriginalImageAccess",
        expected_statuses=frozenset({403}),
        body={"purpose": "view"},
        idempotency_key=f"{idempotency_prefix}-denied",
    )
    denied_code = _error_code(denied)
    if denied_status != 403 or denied_code != "CONTENT.USER.original_access_denied":
        raise ProbeFailure(
            "original_access_denial_contract_failed",
            "image original access must be rejected with "
            f"CONTENT.USER.original_access_denied, got {denied_code or '<missing-code>'}",
        )


def _verify_original_access_grant_and_rate_limit(
    viewer_client: ProbeClient,
    *,
    image_asset_id: str,
    idempotency_prefix: str,
) -> None:
    """验证 public Post 可见后签发短时 grant，且第七次请求稳定 429。"""

    for index in range(6):
        _, granted = viewer_client.request(
            "POST",
            f"/content/media/{urllib.parse.quote(image_asset_id)}/original:access",
            operation_id="RequestOriginalImageAccess",
            body={"purpose": "view"},
            idempotency_key=f"{idempotency_prefix}-grant-{index}",
        )
        grant = _data(granted)
        if (
            _required_text(grant, "status") != "granted"
            or not _required_text(grant, "originalUrl")
            or _required_text(grant, "auditId") == ""
        ):
            raise ProbeFailure(
                "original_access_grant_contract_failed",
                "authorized original access must return only a short-lived grant",
            )
    limited_status, limited = viewer_client.request(
        "POST",
        f"/content/media/{urllib.parse.quote(image_asset_id)}/original:access",
        operation_id="RequestOriginalImageAccess",
        expected_statuses=frozenset({429}),
        body={"purpose": "view"},
        idempotency_key=f"{idempotency_prefix}-limited",
    )
    limited_code = _error_code(limited)
    if (
        limited_status != 429
        or limited_code != "CONTENT.USER.original_access_rate_limited"
    ):
        raise ProbeFailure(
            "original_access_rate_limit_contract_failed",
            "seventh original access grant must return "
            "CONTENT.USER.original_access_rate_limited, got "
            f"{limited_code or '<missing-code>'}",
        )


def _publish_and_readback(
    client: ProbeClient,
    *,
    media_type: str,
    asset_id: str,
    run_id: str,
    processing_timeout_seconds: float,
    visibility: str = "public",
    on_post_created: Callable[[str], None] | None = None,
) -> str:
    publish_intent_id = (
        f"media-publication-probe-{media_type}-{visibility}-{run_id}"
    )
    body: dict[str, Any] = {
        "publishIntentId": publish_intent_id,
        "localDraftId": (
            f"media-publication-probe-draft-{media_type}-{visibility}-{run_id}"
        ),
        "contentType": media_type,
        "body": (
            f"media-publication-probe:{media_type}:{visibility}:{run_id[:12]}"
        ),
        "visibility": visibility,
        "mediaAssetIds": [asset_id],
        "mediaItems": [{"kind": media_type, "mediaId": asset_id}],
    }
    if media_type == "video":
        body["coverStrategy"] = "first_frame"
    deadline = time.monotonic() + processing_timeout_seconds
    receipt: dict[str, Any] | None = None
    retryable_transport_statuses = frozenset({502, 503, 504})
    while time.monotonic() < deadline:
        status, candidate = client.request(
            "POST",
            "/content/posts:publish",
            operation_id="SubmitPostPublication",
            expected_statuses=frozenset({200, 202, 400})
            | retryable_transport_statuses,
            allow_non_json_statuses=retryable_transport_statuses,
            body=body,
            idempotency_key=publish_intent_id,
        )
        if status in {200, 202}:
            receipt = candidate
            break
        if status in retryable_transport_statuses:
            time.sleep(1.0)
            continue
        if _error_code(candidate) != "CONTENT.USER.media_not_ready":
            raise ProbeFailure(
                "publication_admission_failed",
                "publication was rejected for a reason other than media_not_ready",
            )
        time.sleep(1.0)
    if receipt is None:
        raise ProbeFailure(
            "processing_timeout",
            f"media asset {asset_id} did not become publishable within "
            f"{processing_timeout_seconds}s",
        )
    _, replayed = client.request(
        "POST",
        "/content/posts:publish",
        operation_id="SubmitPostPublication",
        expected_statuses=frozenset({200, 202}),
        body=body,
        idempotency_key=publish_intent_id,
    )
    post_id = _required_text(receipt, "postId")
    if on_post_created is not None:
        on_post_created(post_id)
    if _required_text(replayed, "postId") != post_id:
        raise ProbeFailure(
            "idempotency_drift",
            "SubmitPostPublication replay returned a different Post",
        )
    receipt_state = _required_text(receipt, "state")
    if _required_text(replayed, "state") != receipt_state:
        raise ProbeFailure(
            "idempotency_drift",
            "SubmitPostPublication replay returned a different publication state",
        )
    if receipt_state not in {"pending_review", "published"}:
        raise ProbeFailure(
            "publication_state_contract_failed",
            f"publication entered unsupported state {receipt_state}",
        )
    _, post_payload = client.request(
        "GET",
        f"/content/posts/{urllib.parse.quote(post_id)}",
        operation_id="GetPost",
    )
    post = _data(post_payload)
    if str(post.get("id") or post.get("postId") or "").strip() != post_id:
        raise ProbeFailure("readback_missing", "published post is not readable")
    if str(post.get("status") or "").strip() != receipt_state:
        raise ProbeFailure(
            "publication_state_contract_failed",
            "Post readback does not match the publication receipt state",
        )
    media_items = post.get("mediaItems")
    if not isinstance(media_items, list) or not media_items:
        raise ProbeFailure(
            "readback_missing",
            "published post does not expose canonical processed media items",
        )
    media_item = media_items[0]
    if not isinstance(media_item, dict):
        raise ProbeFailure(
            "readback_missing",
            "published post media item is not a canonical object",
        )
    if str(media_item.get("kind") or "").strip() != media_type:
        raise ProbeFailure(
            "readback_missing",
            "published post media item kind does not match the uploaded asset",
        )
    if media_type == "image":
        media_urls = post.get("mediaUrls")
        if (
            not isinstance(media_urls, list)
            or not media_urls
            or not str(media_urls[0] or "").strip()
            or not str(post.get("coverUrl") or "").strip()
        ):
            raise ProbeFailure(
                "readback_missing",
                "published image post is missing its processed public slice",
            )
    elif (
        not str(post.get("videoUrl") or "").strip()
        or not str(post.get("thumbnailUrl") or "").strip()
    ):
        raise ProbeFailure(
            "readback_missing",
            "published video post is missing normalized video or selected cover",
        )
    return post_id


def _delete_published_post(
    client: ProbeClient,
    *,
    post_id: str,
    idempotency_key: str,
) -> None:
    client.request(
        "DELETE",
        f"/content/posts/{urllib.parse.quote(post_id)}",
        operation_id="DeletePost",
        expected_statuses=frozenset({200, 204}),
        idempotency_key=idempotency_key,
    )


def _load_post(client: ProbeClient, post_id: str) -> dict[str, Any]:
    _, payload = client.request(
        "GET",
        f"/content/posts/{urllib.parse.quote(post_id)}",
        operation_id="GetPost",
    )
    post = _data(payload)
    if str(post.get("id") or post.get("postId") or "").strip() != post_id:
        raise ProbeFailure("readback_missing", "Post readback identity drifted")
    return post


def _approve_post_for_publication(
    publisher_client: ProbeClient,
    operator_client: ProbeClient,
    *,
    post_id: str,
    idempotency_prefix: str,
    timeout_seconds: float,
) -> bool:
    """经 PostModerationCase review/decide/outbox 走完真实人工审核主线。"""

    post = _load_post(publisher_client, post_id)
    status = str(post.get("status") or "").strip()
    if status == "published":
        return False
    if status != "pending_review":
        raise ProbeFailure(
            "publication_state_contract_failed",
            "Post must be pending_review before manual moderation",
        )

    deadline = time.monotonic() + timeout_seconds
    case: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        case_status, payload = operator_client.request(
            "GET",
            f"/internal/content/posts/{urllib.parse.quote(post_id)}/moderation-case",
            operation_id="GetCurrentPostModerationCase",
            expected_statuses=frozenset({200, 404}),
        )
        if case_status == 200:
            case = _data(payload)
            break
        if _error_code(payload) != "CONTENT.USER.moderation_case_not_found":
            raise ProbeFailure(
                "moderation_case_contract_failed",
                "pending_review Post returned a non-canonical moderation Case failure",
            )
        time.sleep(0.5)
    if case is None:
        raise ProbeFailure(
            "processing_timeout",
            f"moderation Case for Post {post_id} was not opened within {timeout_seconds}s",
        )

    case_id = _required_text(case, "id")
    case_state = _required_text(case, "status")
    if case_state == "pending":
        operator_client.request(
            "POST",
            f"/internal/content/posts/{urllib.parse.quote(post_id)}:review-moderation",
            operation_id="ReviewPostModerationCase",
            body={"caseId": case_id},
            idempotency_key=f"{idempotency_prefix}-review",
        )
        case_state = "reviewed"
    if case_state == "reviewed":
        operator_client.request(
            "POST",
            f"/internal/content/posts/{urllib.parse.quote(post_id)}:moderate",
            operation_id="DecidePostModeration",
            body={
                "caseId": case_id,
                "decision": "approved",
                "decisionReason": "local_acceptance_safe_media_publication",
            },
            idempotency_key=f"{idempotency_prefix}-decide",
        )
    elif case_state != "approved":
        raise ProbeFailure(
            "moderation_case_contract_failed",
            f"moderation Case entered unsupported state {case_state}",
        )

    while time.monotonic() < deadline:
        post = _load_post(publisher_client, post_id)
        status = str(post.get("status") or "").strip()
        if status == "published":
            return True
        if status != "pending_review":
            raise ProbeFailure(
                "publication_state_contract_failed",
                "approved moderation Case projected an invalid Post state",
            )
        time.sleep(0.5)
    raise ProbeFailure(
        "processing_timeout",
        f"approved moderation Case did not publish Post {post_id} within {timeout_seconds}s",
    )


def _verify_public_post_readback(
    viewer_client: ProbeClient,
    *,
    post_id: str,
) -> None:
    post = _load_post(viewer_client, post_id)
    if (
        str(post.get("status") or "").strip() != "published"
        or str(post.get("visibility") or "").strip() != "public"
    ):
        raise ProbeFailure(
            "public_readback_contract_failed",
            "approved public Post is not visible to an isolated viewer",
        )


def _verify_abort_cleanup(
    client: ProbeClient,
    *,
    idempotency_prefix: str,
) -> str:
    initialized = _init_upload(
        client,
        media_type="image",
        content_type="image/png",
        payload=_PNG_PAYLOAD,
        idempotency_key=f"{idempotency_prefix}-abort-init",
    )
    put_presigned_object(
        upload_url=initialized["uploadUrl"],
        payload=_PNG_PAYLOAD,
        content_type="image/png",
        sha256_digest=initialized["sha256"],
    )
    abort_path = (
        f"/content/media/uploads/{urllib.parse.quote(initialized['sessionId'])}:abort"
    )
    _, aborted = client.request(
        "POST",
        abort_path,
        operation_id="AbortMediaUpload",
        body={},
        idempotency_key=f"{idempotency_prefix}-abort",
    )
    if str(_data(aborted).get("status") or "").strip() != "aborted":
        raise ProbeFailure("abort_not_persisted", "AbortMediaUpload did not persist aborted")
    _, authoritative = client.request(
        "GET",
        f"/content/media/uploads/{urllib.parse.quote(initialized['sessionId'])}",
        operation_id="GetMediaUploadSession",
    )
    if str(_data(authoritative).get("status") or "").strip() != "aborted":
        raise ProbeFailure(
            "abort_not_persisted",
            "authoritative upload session did not remain aborted after cancellation",
        )
    return initialized["sessionId"]


def _write_report(path: Path, report: dict[str, Any]) -> Path:
    target = path if path.is_absolute() else REPO_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    args = _parse_args()
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "scenario": SCENARIO,
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "startedAt": _utc_now(),
        "endedAt": "",
        "environment": {
            "env": args.env,
            "targetName": args.target_name,
            "runtimeKind": args.target_name
            or (LOCAL_TARGETS.get(args.env, "") if args.env != "prod" else "prod-hosted"),
            "gatewayBaseUrl": args.base_url.rstrip("/"),
            "commitSha": os.environ.get("GITHUB_SHA", ""),
        },
        "mode": args.mode,
        "steps": [],
        "journeyEvidence": {},
    }
    return_code = 1
    client: ProbeClient | None = None
    viewer_client: ProbeClient | None = None
    operator_client: ProbeClient | None = None
    owner_query_client: ProbeClient | None = None
    published_posts: list[tuple[str, str]] = []
    moderation_case_approvals = 0
    try:
        if (
            args.env == "prod"
            and args.target_name != "prod-sim"
            and args.mode != "read-only"
        ):
            raise ProbeFailure(
                "unsafe_mode",
                "prod-hosted media publication probe is read-only",
            )
        session = build_reporter_session(
            environment=args.env,
            base_url=args.base_url,
            hosted_token_env=args.auth_token_env,
            target_name=args.target_name,
        )
        client = ProbeClient(args.base_url, session)
        client.request("GET", "/healthz", operation_id="Health")
        report["steps"].append({"name": "healthz", "status": "passed"})
        if args.mode == "read-only":
            report["status"] = "passed"
            return_code = 0
        else:
            run_id = uuid.uuid4().hex
            viewer = build_media_viewer_session(
                environment=args.env,
                base_url=args.base_url,
                target_name=args.target_name,
            )
            viewer_client = ProbeClient(
                args.base_url,
                viewer,
            )
            operator = build_moderation_operator_session(
                environment=args.env,
                base_url=args.base_url,
                target_name=args.target_name,
            )
            operator_client = ProbeClient(
                args.moderation_base_url,
                operator,
            )
            owner_query_client = ProbeClient(
                args.moderation_base_url,
                session,
            )
            image_asset_id = ""
            video_asset_id = ""
            if args.scenario in {"all", "photo", "recovery"}:
                image_asset_id, _image_session = _upload_complete_lost_response_and_wait(
                    client,
                    media_type="image",
                    content_type="image/png",
                    payload=_PNG_PAYLOAD,
                    idempotency_prefix=f"media-publication-probe-image-lost-response-{run_id}",
                    access_policy="referenced_post",
                )
                report["steps"].append(
                    {
                        "name": "image_complete_lost_response_reconciled_processing_pending",
                        "status": "passed",
                    }
                )
                disposable_asset_id, _ = _upload_complete_and_wait(
                    client,
                    media_type="image",
                    content_type="image/png",
                    payload=_PNG_PAYLOAD,
                    idempotency_prefix=(
                        f"media-publication-probe-image-discard-{run_id}"
                    ),
                    access_policy="owner_only",
                )
                _discard_unreferenced_asset(
                    client,
                    owner_query_client=owner_query_client,
                    asset_id=disposable_asset_id,
                    idempotency_key=(
                        f"media-publication-probe-image-discard-command-{run_id}"
                    ),
                )
                report["steps"].append(
                    {
                        "name": "unreferenced_media_discarded_and_replayed",
                        "status": "passed",
                    }
                )
            if args.scenario in {"all", "video"}:
                video_asset_id, _video_completion = _upload_complete_and_wait(
                    client,
                    media_type="video",
                    content_type="video/mp4",
                    payload=_render_probe_video(),
                    idempotency_prefix=f"media-publication-probe-video-{run_id}",
                    access_policy="owner_only",
                )
                report["steps"].append(
                    {"name": "video_upload_complete_processing_pending", "status": "passed"}
                )
            if args.scenario == "all":
                private_image_post_id = _publish_and_readback(
                    client,
                    media_type="image",
                    asset_id=image_asset_id,
                    run_id=run_id,
                    processing_timeout_seconds=args.processing_timeout_seconds,
                    visibility="private",
                    on_post_created=lambda post_id: published_posts.append(
                        ("image-private", post_id)
                    ),
                )
                if operator_client is None or viewer_client is None:
                    raise ProbeFailure(
                        "auth_missing",
                        "private visibility check requires viewer and moderation sessions",
                    )
                moderation_case_approvals += int(_approve_post_for_publication(
                    client,
                    operator_client,
                    post_id=private_image_post_id,
                    idempotency_prefix=(
                        f"media-publication-probe-private-moderation-{run_id}"
                    ),
                    timeout_seconds=args.processing_timeout_seconds,
                ))
                _verify_original_access_denial(
                    viewer_client,
                    image_asset_id=image_asset_id,
                    idempotency_prefix=(
                        f"media-publication-probe-original-private-{run_id}"
                    ),
                )
                report["steps"].append(
                    {
                        "name": "private_image_original_access_denied",
                        "status": "passed",
                    }
                )
            if args.scenario in {"all", "photo", "recovery"}:
                image_post_id = _publish_and_readback(
                    client,
                    media_type="image",
                    asset_id=image_asset_id,
                    run_id=run_id,
                    processing_timeout_seconds=args.processing_timeout_seconds,
                    on_post_created=lambda post_id: published_posts.append(
                        ("image-public", post_id)
                    ),
                )
                if operator_client is None or viewer_client is None:
                    raise ProbeFailure(
                        "auth_missing",
                        "public image verification requires viewer and moderation sessions",
                    )
                moderation_case_approvals += int(_approve_post_for_publication(
                    client,
                    operator_client,
                    post_id=image_post_id,
                    idempotency_prefix=(
                        f"media-publication-probe-image-moderation-{run_id}"
                    ),
                    timeout_seconds=args.processing_timeout_seconds,
                ))
                _verify_public_post_readback(
                    viewer_client,
                    post_id=image_post_id,
                )
                report["steps"].append(
                    {"name": "image_publish_idempotent_readback", "status": "passed"}
                )
            if args.scenario in {"all", "video"}:
                _select_auto_video_cover(
                    client,
                    asset_id=video_asset_id,
                    idempotency_key=f"media-publication-probe-video-cover-{run_id}",
                    processing_timeout_seconds=args.processing_timeout_seconds,
                )
                report["steps"].append(
                    {"name": "video_auto_cover_selected", "status": "passed"}
                )
                video_post_id = _publish_and_readback(
                    client,
                    media_type="video",
                    asset_id=video_asset_id,
                    run_id=run_id,
                    processing_timeout_seconds=args.processing_timeout_seconds,
                    on_post_created=lambda post_id: published_posts.append(
                        ("video", post_id)
                    ),
                )
                if operator_client is None or viewer_client is None:
                    raise ProbeFailure(
                        "auth_missing",
                        "public video verification requires viewer and moderation sessions",
                    )
                moderation_case_approvals += int(_approve_post_for_publication(
                    client,
                    operator_client,
                    post_id=video_post_id,
                    idempotency_prefix=(
                        f"media-publication-probe-video-moderation-{run_id}"
                    ),
                    timeout_seconds=args.processing_timeout_seconds,
                ))
                _verify_public_post_readback(
                    viewer_client,
                    post_id=video_post_id,
                )
                report["steps"].append(
                    {"name": "video_publish_idempotent_readback", "status": "passed"}
                )
            if args.scenario == "all":
                if viewer_client is None:
                    raise ProbeFailure(
                        "auth_missing",
                        "original access rate-limit check requires an isolated viewer",
                    )
                _verify_original_access_grant_and_rate_limit(
                    viewer_client,
                    image_asset_id=image_asset_id,
                    idempotency_prefix=(
                        f"media-publication-probe-original-public-{run_id}"
                    ),
                )
                report["steps"].append(
                    {
                        "name": "public_image_original_access_granted_and_rate_limited",
                        "status": "passed",
                    }
                )
            aborted_session_id = ""
            if args.scenario in {"all", "recovery"}:
                aborted_session_id = _verify_abort_cleanup(
                    client,
                    idempotency_prefix=f"media-publication-probe-{run_id}",
                )
                report["steps"].append(
                    {"name": "uploaded_temporary_object_abort", "status": "passed"}
                )
            report["journeyEvidence"].update(
                {
                    "scenario": args.scenario,
                    "imageAssetIdHash": _stable_hash(image_asset_id)
                    if image_asset_id
                    else "",
                    "videoAssetIdHash": _stable_hash(video_asset_id)
                    if video_asset_id
                    else "",
                    "imageProcessingResolvedByPublicationAdmission": bool(
                        image_asset_id
                    ),
                    "videoProcessingResolvedByPublicationAdmission": bool(
                        video_asset_id
                    ),
                    "completeLostResponseReconciled": bool(image_asset_id),
                    "videoAutoCoverSelected": bool(video_asset_id),
                    "moderationCaseApprovedCount": moderation_case_approvals,
                    "originalAccessDenied403": args.scenario == "all",
                    "originalAccessGrantedAfterPublicVisibility": args.scenario
                    == "all",
                    "originalAccessRateLimited429": args.scenario == "all",
                    "temporaryUploadAbort": bool(aborted_session_id),
                }
            )
            report["status"] = "passed"
            return_code = 0
    except ProbeFailure as exc:
        report["status"] = "failed"
        report["failureCategory"] = exc.category
        report["blockingReason"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["failureCategory"] = "unexpected_error"
        report["blockingReason"] = type(exc).__name__
    finally:
        if client is not None:
            for media_type, post_id in published_posts:
                try:
                    _delete_published_post(
                        client,
                        post_id=post_id,
                        idempotency_key=f"media-publication-probe-delete-{media_type}-{post_id}",
                    )
                except Exception:  # noqa: BLE001
                    if report["status"] == "passed":
                        report["status"] = "failed"
                        report["failureCategory"] = "probe_cleanup_failed"
                        report["blockingReason"] = (
                            "published media probe post could not be deleted"
                        )
                        return_code = 1
                    continue
            if published_posts and report["status"] == "passed":
                report["steps"].append(
                    {"name": "publication_probe_posts_deleted", "status": "passed"}
                )
        report["endedAt"] = _utc_now()
        target = _write_report(Path(args.report), report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "scenario": SCENARIO,
                    "report": str(target),
                    "failureCategory": report["failureCategory"],
                },
                ensure_ascii=False,
            )
        )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
