#!/usr/bin/env python3
# readiness_case: media_publication_lifecycle_probe_ops_env
# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-001
# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003
# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003.t3
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
import sys
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Callable

_SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support"
if str(_SUPPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_DIR))


from media_publication_lifecycle_probe_support import (  # noqa: E402
    SCENARIO,
    SCHEMA,
    _PNG_PAYLOAD,
    _approve_post_for_publication,
    _data,
    _delete_published_post,
    _discard_unreferenced_asset,
    _error_code,
    _init_upload,
    _load_post,
    _parse_args,
    _publish_and_readback,
    _render_probe_video,
    _request_with_transport_retry,
    _required_text,
    _select_auto_video_cover,
    _stable_hash,
    _upload_complete_and_wait,
    _upload_complete_lost_response_and_wait,
    _utc_now,
    _verify_abort_cleanup,
    _verify_original_access_denial,
    _verify_original_access_grant_and_rate_limit,
    _verify_public_post_readback,
    _write_report,
)
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
