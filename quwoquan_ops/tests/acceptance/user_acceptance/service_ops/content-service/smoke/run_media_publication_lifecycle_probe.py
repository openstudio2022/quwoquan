#!/usr/bin/env python3
"""验证真实对象存储、媒体处理和原子发布的 Gamma/Beta 用户旅程。"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

from report_feedback_probe_support import (
    LOCAL_TARGETS,
    REPO_ROOT,
    ProbeClient,
    ProbeFailure,
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
    parser.add_argument("--resolve-host", default="")
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
    if args.env in LOCAL_TARGETS and not args.resolve_host:
        args.resolve_host = "127.0.0.1"
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
        "contentType": content_type,
        "fileSize": len(payload),
        "expectedSha256": digest,
    }
    _, initialized = client.request(
        "POST",
        "/content/media/uploads:init",
        operation_id="InitMediaUpload",
        body=body,
        idempotency_key=idempotency_key,
    )
    _, replayed = client.request(
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


def _upload_complete_and_wait(
    client: ProbeClient,
    *,
    media_type: str,
    content_type: str,
    payload: bytes,
    idempotency_prefix: str,
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
        resolve_host=client.resolve_host,
    )
    complete_path = (
        f"/content/media/uploads/{urllib.parse.quote(initialized['sessionId'])}:complete"
    )
    _, completed = client.request(
        "POST",
        complete_path,
        operation_id="CompleteMediaUpload",
        body={"accessPolicy": "owner_only"},
        idempotency_key=f"{idempotency_prefix}-complete",
    )
    _, replayed = client.request(
        "POST",
        complete_path,
        operation_id="CompleteMediaUpload",
        body={"accessPolicy": "owner_only"},
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
        resolve_host=client.resolve_host,
    )
    complete_path = (
        f"/content/media/uploads/{urllib.parse.quote(initialized['sessionId'])}:complete"
    )
    # 模拟客户端在服务端已提交后丢失响应：请求确实完成，但调用方故意不用其 body。
    client.request(
        "POST",
        complete_path,
        operation_id="CompleteMediaUpload",
        body={"accessPolicy": "owner_only"},
        idempotency_key=f"{idempotency_prefix}-complete",
    )
    _, authoritative = client.request(
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


def _select_auto_video_cover(
    client: ProbeClient,
    *,
    asset_id: str,
    idempotency_key: str,
) -> None:
    _, payload = client.request(
        "POST",
        f"/content/media/{urllib.parse.quote(asset_id)}/cover:auto",
        operation_id="SelectAutoVideoCover",
        body={},
        idempotency_key=idempotency_key,
    )
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


def _verify_original_access_denial_and_rate_limit(
    client: ProbeClient,
    *,
    image_asset_id: str,
    video_asset_id: str,
    idempotency_prefix: str,
) -> None:
    """验证原图授权的 403 denied 和 metadata policy 的 429 终态。"""
    denied_status, denied = client.request(
        "POST",
        f"/content/media/{urllib.parse.quote(video_asset_id)}/original:access",
        operation_id="RequestOriginalImageAccess",
        expected_statuses=frozenset({403}),
        body={"purpose": "view"},
        idempotency_key=f"{idempotency_prefix}-denied",
    )
    denied_code = _error_code(denied)
    if denied_status != 403 or denied_code != "CONTENT.USER.original_access_denied":
        raise ProbeFailure(
            "original_access_denial_contract_failed",
            "video original access must be rejected with "
            f"CONTENT.USER.original_access_denied, got {denied_code or '<missing-code>'}",
        )
    for index in range(6):
        _, granted = client.request(
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
    limited_status, limited = client.request(
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
) -> str:
    publish_intent_id = f"media-publication-probe-{media_type}-{run_id}"
    body: dict[str, Any] = {
        "publishIntentId": publish_intent_id,
        "localDraftId": f"media-publication-probe-draft-{media_type}-{run_id}",
        "contentType": media_type,
        "body": f"media-publication-probe:{media_type}:{run_id[:12]}",
        "visibility": "public",
        "mediaAssetIds": [asset_id],
        "mediaItems": [{"kind": media_type, "mediaId": asset_id}],
    }
    if media_type == "video":
        body["coverStrategy"] = "first_frame"
    deadline = time.monotonic() + processing_timeout_seconds
    receipt: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status, candidate = client.request(
            "POST",
            "/content/posts:publish",
            operation_id="SubmitPostPublication",
            expected_statuses=frozenset({200, 202, 400}),
            body=body,
            idempotency_key=publish_intent_id,
        )
        if status in {200, 202}:
            receipt = candidate
            break
        if "media_not_ready" not in json.dumps(candidate):
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
    if _required_text(replayed, "postId") != post_id:
        raise ProbeFailure(
            "idempotency_drift",
            "SubmitPostPublication replay returned a different Post",
        )
    _, post_payload = client.request(
        "GET",
        f"/content/posts/{urllib.parse.quote(post_id)}",
        operation_id="GetPost",
    )
    post = _data(post_payload)
    if str(post.get("id") or post.get("postId") or "").strip() != post_id:
        raise ProbeFailure("readback_missing", "published post is not readable")
    media_items = post.get("mediaItems")
    if not isinstance(media_items, list) or not media_items:
        raise ProbeFailure(
            "readback_missing",
            "published post does not expose canonical processed media items",
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
        resolve_host=client.resolve_host,
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
    published_posts: list[tuple[str, str]] = []
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
            resolve_host=args.resolve_host,
            hosted_token_env=args.auth_token_env,
            target_name=args.target_name,
        )
        client = ProbeClient(args.base_url, args.resolve_host, session)
        client.request("GET", "/healthz", operation_id="Health")
        report["steps"].append({"name": "healthz", "status": "passed"})
        if args.mode == "read-only":
            report["status"] = "passed"
            return_code = 0
        else:
            run_id = uuid.uuid4().hex
            image_asset_id = ""
            video_asset_id = ""
            if args.scenario in {"all", "photo", "recovery"}:
                image_asset_id, _image_session = _upload_complete_lost_response_and_wait(
                    client,
                    media_type="image",
                    content_type="image/png",
                    payload=_PNG_PAYLOAD,
                    idempotency_prefix=f"media-publication-probe-image-lost-response-{run_id}",
                )
                report["steps"].append(
                    {
                        "name": "image_complete_lost_response_reconciled_processing_pending",
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
                )
                report["steps"].append(
                    {"name": "video_upload_complete_processing_pending", "status": "passed"}
                )
            if args.scenario in {"all", "photo"}:
                image_post_id = _publish_and_readback(
                    client,
                    media_type="image",
                    asset_id=image_asset_id,
                    run_id=run_id,
                    processing_timeout_seconds=args.processing_timeout_seconds,
                )
                published_posts.append(("image", image_post_id))
                report["steps"].append(
                    {"name": "image_publish_idempotent_readback", "status": "passed"}
                )
            if args.scenario in {"all", "video"}:
                video_post_id = _publish_and_readback(
                    client,
                    media_type="video",
                    asset_id=video_asset_id,
                    run_id=run_id,
                    processing_timeout_seconds=args.processing_timeout_seconds,
                )
                published_posts.append(("video", video_post_id))
                report["steps"].append(
                    {"name": "video_publish_idempotent_readback", "status": "passed"}
                )
                _select_auto_video_cover(
                    client,
                    asset_id=video_asset_id,
                    idempotency_key=f"media-publication-probe-video-cover-{run_id}",
                )
                report["steps"].append(
                    {"name": "video_auto_cover_selected", "status": "passed"}
                )
            if args.scenario == "all":
                _verify_original_access_denial_and_rate_limit(
                    client,
                    image_asset_id=image_asset_id,
                    video_asset_id=video_asset_id,
                    idempotency_prefix=f"media-publication-probe-original-access-{run_id}",
                )
                report["steps"].append(
                    {
                        "name": "original_access_denied_and_rate_limited",
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
                    "originalAccessDenied403": args.scenario == "all",
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
