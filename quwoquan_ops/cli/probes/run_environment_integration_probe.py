#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.parse
from functools import lru_cache
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[3]

# 本探针由 stackctl 以子进程直跑（python3 <script>），子进程的 sys.path 只含
# 脚本目录而不含仓库根；绝对包导入必须先自举仓库根，否则 health/verify 的
# integration-readonly 检查会以 ModuleNotFoundError 假性失败。
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.probes.environment_probe_check_builder import (  # noqa: E402
    _owner_matches_post,
    _release_creator_profiles,
    _release_probe_identity as _build_release_probe_identity,
    _release_samples,
    _release_search_canaries,
    _release_signed_media,
    build_checks as _build_checks,
)

# 响应语义判定家族已迁至 environment_probe_semantics；此处 re-export 保持
# 测试与消费者的 `probe.<符号>` 读取面不变。
from quwoquan_ops.cli.probes.environment_probe_semantics import (  # noqa: E402
    AUTHOR_POSTS_CHECK_NAME,
    CONTENT_POST_PROJECTION_PATH,
    CREATOR_PROFILE_CHECK_NAME,
    FEED_MEDIA_SLICES_CHECK_NAME,
    FEED_MEDIA_SOURCE_CHECK_NAMES,
    _author_posts_semantic_result,
    _content_feed_semantic_issue,
    _content_feed_semantic_result,
    _content_post_projection_fields,
    _expected_release_post_ids,
    _feed_media_slice_urls,
    _media_origin,
    PRIVATE_FEED_CHECK_NAMES,
    _release_creator_profile_semantic_result,
    _release_sample_semantic_result,
    _research_anonymous_convergence_issue,
    _search_semantic_issue,
    SIGNED_MEDIA_CHECK_NAME,
)
# HTTP 传输与重试裁决同样已分家到 environment_probe_transport；沿用同一 re-export
# 约定，让 `probe.request` 一类读取面不因内部拆分而变化。
from quwoquan_ops.cli.probes.environment_probe_transport import (  # noqa: E402
    INTEGRATION_FEED_SESSION_ID as _INTEGRATION_FEED_SESSION_ID,
    common_headers as _common_headers,
    declared_transient_retry_delay as _declared_transient_retry_delay,
    feed_headers as _feed_headers,
    feed_url as _feed_url,
    json_headers as _json_headers,
    public_headers as _public_headers,
    request,
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.release_video_delivery import (
    ReleaseVideoDeliveryError,
    load_release_content_identity,
    resolve_readiness_path,
)

DEFAULT_REPORT = (
    REPO_ROOT
    / ".qwq_output"
    / "env"
    / "repo"
    / "runs"
    / "integration-probe"
    / "report.json"
)
DEFAULT_ENVIRONMENT_SEARCH_QUERY = "西湖"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _redact_sensitive_values(value: Any, secrets: tuple[str, ...]) -> Any:
    """从持久化 report 投影递归移除内存态凭证字节。"""

    if isinstance(value, dict):
        return {
            key: _redact_sensitive_values(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_values(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive_values(item, secrets) for item in value)
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redacted
    return value


@lru_cache(maxsize=1)
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run readonly integration probes for alpha/beta/gamma/prod environments.",
    )
    parser.add_argument(
        "--env", required=True, choices=("alpha", "beta", "gamma", "prod")
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument(
        "--release-readiness",
        default=os.environ.get("DATA_RELEASE_READINESS_RECEIPT", "").strip(),
        help=(
            "Canonical Data release-readiness.json. Required when the media "
            "sample probe is enabled; no fixture/default media identity exists."
        ),
    )
    # 凭证只接受环境变量注入；禁止提供 secret-bearing argv surface。
    parser.set_defaults(test_auth_token="")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--request-timeout-seconds", type=int, default=12)
    parser.add_argument("--retry-attempts", type=int, default=2)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument(
        "--only-check",
        action="append",
        default=[],
        help="Run only the named check; repeat for multiple checks (for example global_search).",
    )
    parser.add_argument(
        "--require-non-empty-content-feed",
        action="store_true",
        help=(
            "Release-readiness mode: require discovery, exact video-book and premium "
            "feed queries to return at least one item."
        ),
    )
    parser.add_argument(
        "--research-anonymous-convergence",
        action="store_true",
        help=(
            "Research-isolation mode: require the anonymous discovery, video-book "
            "and premium feed queries to converge to the empty page with "
            "emptyReason=no_active_release and no release identity echo (DEC-032). "
            "Authenticated research consumption evidence is owned by the Data "
            "post-api verification; this probe proves anonymous isolation."
        ),
    )
    parser.add_argument(
        "--research-consumer-readback",
        action="store_true",
        help=(
            "Research-consumer mode: run the feed checks with the authenticated "
            "research consumer identity (bearer injected via the test auth token "
            "environment variable) instead of the anonymous surface, so that "
            "release-bound non-empty expectations hold for a research release "
            "(DEC-032 capability surface)."
        ),
    )
    parser.add_argument(
        "--expected-discovery-post-id",
        action="append",
        default=[],
        help=(
            "Release-bound postId accepted by the identity=work readback; repeatable. "
            "At least one returned item must match."
        ),
    )
    parser.add_argument(
        "--expected-homepage-recommend-post-id",
        action="append",
        default=[],
        help="Exact release postId expected from homepage recommendation.",
    )
    parser.add_argument(
        "--expected-video-post-id",
        action="append",
        default=[],
        help=(
            "Release-bound video postId accepted by the identity=work&type=video "
            "readback; repeatable."
        ),
    )
    parser.add_argument(
        "--expected-premium-video-post-id",
        action="append",
        default=[],
        help=(
            "Release-bound playable video postId accepted by the premium_stream "
            "readback; repeatable."
        ),
    )
    parser.add_argument(
        "--video-page-size",
        type=int,
        default=1,
        help="Exact video-book page size used by release-bound App UAT.",
    )
    parser.add_argument(
        "--release-search-canary",
        action="append",
        default=[],
        help=(
            "Canonical JSON object containing kind/query/expectedObjectType/"
            "expectedObjectId; repeat for Post, Homepage, and Persona."
        ),
    )
    parser.add_argument(
        "--release-sample",
        action="append",
        default=[],
        help=(
            "Canonical JSON object for one exact release-bound homepage/Post read; "
            "repeat exactly once for every stratified sample."
        ),
    )
    parser.add_argument(
        "--release-creator-profile",
        action="append",
        default=[],
        help="Canonical JSON exact creator/profile/avatar projection.",
    )
    parser.add_argument(
        "--release-signed-media",
        action="append",
        default=[],
        help="Canonical JSON release-bound private media classification.",
    )
    parser.add_argument(
        "--mode",
        choices=("readonly", "post-deploy"),
        default="readonly",
    )
    args = parser.parse_args()
    if args.require_non_empty_content_feed and args.research_anonymous_convergence:
        parser.error(
            "--require-non-empty-content-feed and --research-anonymous-convergence "
            "are mutually exclusive feed semantics"
        )
    if args.research_consumer_readback and args.research_anonymous_convergence:
        parser.error(
            "--research-consumer-readback and --research-anonymous-convergence "
            "are mutually exclusive feed identities"
        )
    args.test_auth_token = _resolve_test_auth_token(args.env, args.test_auth_token)
    args.research_consumer_attestation = os.environ.get(
        "RESEARCH_CONSUMER_ATTESTATION", ""
    ).strip()
    if args.research_consumer_readback and not args.test_auth_token:
        parser.error(
            "--research-consumer-readback requires the research consumer bearer "
            "via the test auth token environment variable"
        )
    if args.research_consumer_readback and not args.research_consumer_attestation:
        parser.error(
            "--research-consumer-readback requires the research attestation "
            "via RESEARCH_CONSUMER_ATTESTATION"
        )
    # research consumer 身份本身即 release-bound 非空语义；调用方无需再维护
    # 第二个 boolean 真相源。exact expected IDs 仍在 run_checks 对选中 feed 逐项要求。
    if args.research_consumer_readback:
        args.require_non_empty_content_feed = True
    return args


def _resolve_test_auth_token(env_name: str, explicit_token: str) -> str:
    token = explicit_token.strip()
    if token:
        return token
    token_envs = {
        "alpha": ("ALPHA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "beta": ("BETA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "gamma": ("GAMMA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "prod": ("PROD_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
    }
    for env_var in token_envs.get(env_name, ("TEST_AUTH_TOKEN",)):
        value = os.environ.get(env_var, "").strip()
        if value:
            return value
    return ""


def _release_probe_identity(args: argparse.Namespace) -> dict[str, Any]:
    return _build_release_probe_identity(
        args,
        load_release_content_identity_fn=load_release_content_identity,
        resolve_readiness_path_fn=resolve_readiness_path,
        release_video_delivery_error=ReleaseVideoDeliveryError,
    )


def build_checks(
    args: argparse.Namespace,
    *,
    release_identity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return _build_checks(
        args,
        release_identity=release_identity,
        default_environment_search_query=DEFAULT_ENVIRONMENT_SEARCH_QUERY,
        common_headers=_common_headers,
        feed_headers=_feed_headers,
        feed_url=_feed_url,
        json_headers=_json_headers,
        public_headers=_public_headers,
        release_search_canaries=_release_search_canaries,
        release_samples=_release_samples,
        release_creator_profiles=_release_creator_profiles,
        release_signed_media=_release_signed_media,
    )


def run_checks(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now()
    findings: list[str] = []
    results: list[dict[str, Any]] = []
    mode = str(getattr(args, "mode", "readonly") or "readonly")
    media_image_base_url = str(
        getattr(
            args,
            "media_image_base_url",
            getattr(args, "media_base_url", ""),
        )
        or ""
    )
    request_timeout_seconds = int(getattr(args, "request_timeout_seconds", 12))
    retry_attempts = int(getattr(args, "retry_attempts", 1))
    retry_sleep_seconds = float(getattr(args, "retry_sleep_seconds", 0.0))
    require_non_empty_content_feed = bool(
        getattr(args, "require_non_empty_content_feed", False)
    )
    research_anonymous_convergence = bool(
        getattr(args, "research_anonymous_convergence", False)
    )
    research_consumer_readback = bool(
        getattr(args, "research_consumer_readback", False)
    )
    require_authenticated_feed = (
        require_non_empty_content_feed or research_consumer_readback
    )
    research_consumer_attestation = str(
        getattr(args, "research_consumer_attestation", "") or ""
    ).strip()
    if research_consumer_readback and not str(args.test_auth_token or "").strip():
        findings.append(
            "GATE_BLOCK: research consumer readback requires a bearer token"
        )
    if research_consumer_readback and not research_consumer_attestation:
        findings.append(
            "GATE_BLOCK: research consumer readback requires an attestation"
        )
    if research_consumer_readback and research_anonymous_convergence:
        findings.append(
            "GATE_BLOCK: research consumer and anonymous convergence identities conflict"
        )
    if mode == "post-deploy" and not args.test_auth_token:
        findings.append(
            "GATE_BLOCK: post-deploy integration requires a valid environment test auth token"
        )
    release_identity: dict[str, Any] | None = None
    if media_image_base_url.rstrip("/"):
        try:
            release_identity = _release_probe_identity(args)
        except (ReleaseVideoDeliveryError, ValueError) as exc:
            findings.append(f"GATE_BLOCK: {exc}")
    available_checks = build_checks(args, release_identity=release_identity)
    only_checks = {
        str(value).strip()
        for value in getattr(args, "only_check", [])
        if str(value).strip()
    }
    available_names = {check["name"] for check in available_checks}
    # author_posts_contract 是 release_sample(post) 的链式派生检查：
    # 从样本详情响应提取 authorId 后请求 ListUserPosts 并做契约白名单校验。
    available_names.add(AUTHOR_POSTS_CHECK_NAME)
    # feed_media_slices 是 feed 检查的链式派生检查：从 feed items 收集全部
    # 公开媒体 slice 并逐个字节读回（items 非空不等于媒体可显示）。
    available_names.add(FEED_MEDIA_SLICES_CHECK_NAME)
    unknown_checks = sorted(only_checks - available_names)
    if unknown_checks:
        findings.append(
            "GATE_BLOCK: unknown integration check(s): " + ", ".join(unknown_checks)
        )
    selected_checks = [
        check
        for check in available_checks
        if not only_checks or check["name"] in only_checks
    ]
    author_persona_id = ""
    feed_media_slices: dict[str, str] = {}
    feed_media_origin = _media_origin(media_image_base_url)
    for check in selected_checks:
        retry_trace: list[dict[str, Any]] = []
        if check["name"] == SIGNED_MEDIA_CHECK_NAME:
            if not getattr(args, "research_consumer_readback", False):
                findings.append(
                    f"{SIGNED_MEDIA_CHECK_NAME} failed: requires research consumer identity"
                )
                continue
            from quwoquan_ops.cli.lib.local_environment_auth import LocalAcceptanceSession
            from quwoquan_ops.cli.lib.research_isolation_runtime_probe import (
                ResearchIsolationProbeError,
                probe_release_bound_signed_media,
            )

            session = LocalAcceptanceSession(
                owner_id="release-preflight",
                persona_id="release-preflight",
                access_token=args.test_auth_token,
            )
            evidence: list[dict[str, Any]] = []
            try:
                for asset in check["assets"]:
                    evidence.append(
                        probe_release_bound_signed_media(
                            api_base_url=args.base_url.rstrip("/"),
                            session=session,
                            asset=asset,
                            attestation_token=research_consumer_attestation,
                            timeout_seconds=max(1, request_timeout_seconds),
                        )
                    )
            except (ResearchIsolationProbeError, ValueError) as exc:
                entry = {
                    "name": SIGNED_MEDIA_CHECK_NAME,
                    "method": "GET",
                    "url": check["url"],
                    "statusCode": 0,
                    "ok": False,
                    "bodyPreview": "",
                    "semanticError": str(exc),
                    "assets": evidence,
                }
                results.append(entry)
                findings.append(f"{SIGNED_MEDIA_CHECK_NAME} failed: {exc}")
                continue
            entry = {
                "name": SIGNED_MEDIA_CHECK_NAME,
                "method": "GET",
                "url": check["url"],
                "statusCode": 200,
                "ok": True,
                "bodyPreview": "",
                "assets": evidence,
                "executedAssetCount": len(evidence),
            }
            results.append(entry)
            continue
        ok, status_code, payload = request(
            check["method"],
            check["url"],
            headers=check.get("headers"),
            body=check.get("body"),
            timeout=max(1, request_timeout_seconds),
            retry_attempts=max(1, retry_attempts),
            retry_sleep_seconds=max(0.0, retry_sleep_seconds),
            retry_trace=retry_trace,
        )
        expected_statuses = list(check.get("expected_statuses") or [])
        matched = ok and status_code in expected_statuses
        preview = payload[:1200]
        entry = {
            "name": check["name"],
            "method": check["method"],
            "url": check["url"],
            "statusCode": status_code,
            "ok": matched,
            "bodyPreview": preview,
        }
        # 瞬时重试必须留痕：环境抖动（如 ES GC 停顿）即使被重试吸收，
        # 也要在回执里可见，否则会静默掩盖容量与稳定性问题。
        if retry_trace:
            entry["retriedAttempts"] = retry_trace
        if (
            matched
            and require_authenticated_feed
            and check["name"] in PRIVATE_FEED_CHECK_NAMES
        ):
            expected_post_ids = _expected_release_post_ids(args, check["name"])
            semantic_issue, item_count, returned_post_ids = (
                _content_feed_semantic_result(
                    payload,
                    expected_post_ids=expected_post_ids,
                )
            )
            if (
                research_consumer_readback
                and not expected_post_ids
                and semantic_issue is None
            ):
                semantic_issue = (
                    "research consumer readback requires exact immutable release "
                    f"post IDs for {check['name']}"
                )
            if item_count is not None:
                entry["contentItemCount"] = item_count
            if returned_post_ids:
                entry["returnedPostIds"] = sorted(returned_post_ids)
            if semantic_issue:
                matched = False
                entry["ok"] = False
                entry["semanticError"] = semantic_issue
        if (
            matched
            and research_anonymous_convergence
            and not research_consumer_readback
            and check["name"] in PRIVATE_FEED_CHECK_NAMES
        ):
            authorization = str((check.get("headers") or {}).get("Authorization") or "")
            if authorization:
                semantic_issue, item_count = (
                    "research anonymous convergence carried a credential",
                    None,
                )
            else:
                semantic_issue, item_count = _research_anonymous_convergence_issue(
                    payload
                )
            if item_count is not None:
                entry["contentItemCount"] = item_count
            if semantic_issue:
                matched = False
                entry["ok"] = False
                entry["semanticError"] = semantic_issue
        if (
            matched
            and feed_media_origin
            and check["name"] in FEED_MEDIA_SOURCE_CHECK_NAMES
        ):
            for slice_url, slice_kind in _feed_media_slice_urls(
                payload, feed_media_origin
            ).items():
                feed_media_slices.setdefault(slice_url, slice_kind)
        if matched and check["name"] == "global_search":
            semantic_issue, hit_count = _search_semantic_issue(
                payload,
                expected_object_type=str(
                    check.get("expectedSearchObjectType") or ""
                ),
                expected_object_id=str(
                    check.get("expectedSearchObjectId") or ""
                ),
            )
            if hit_count is not None:
                entry["searchHitCount"] = hit_count
            entry["searchCanaryKind"] = str(
                check.get("searchCanaryKind") or "generic"
            )
            entry["expectedSearchObjectType"] = str(
                check.get("expectedSearchObjectType") or ""
            )
            entry["expectedSearchObjectId"] = str(
                check.get("expectedSearchObjectId") or ""
            )
            if semantic_issue:
                matched = False
                entry["ok"] = False
                entry["semanticError"] = semantic_issue
        if matched and check["name"] == "release_sample":
            semantic_issue, returned_id, returned_type = _release_sample_semantic_result(
                payload,
                carrier=str(check.get("carrier") or ""),
                read_object_id=str(check.get("readObjectId") or ""),
                expected_content_type=str(check.get("expectedContentType") or ""),
                expected_author_id=str(check.get("expectedAuthorId") or ""),
                expected_author_display_name=str(
                    check.get("expectedAuthorDisplayName") or ""
                ),
                expected_avatar_delivery_ref=str(
                    check.get("expectedAvatarDeliveryRef") or ""
                ),
            )
            for field in (
                "sampleId",
                "carrier",
                "sourceReadback",
                "sourceObjectId",
                "ordinal",
                "readObjectId",
                "expectedContentType",
                "expectedAuthorId",
                "expectedPersonaId",
                "expectedAuthorDisplayName",
                "expectedAvatarAssetId",
                "expectedAvatarDeliveryRef",
            ):
                entry[field] = check.get(field)
            entry["returnedObjectId"] = returned_id
            entry["returnedContentType"] = returned_type
            entry["responseDigest"] = "sha256:" + hashlib.sha256(
                payload.encode("utf-8")
            ).hexdigest()
            entry["responseBytes"] = len(payload.encode("utf-8"))
            if semantic_issue:
                matched = False
                entry["ok"] = False
                entry["semanticError"] = semantic_issue
            if (
                matched
                and not author_persona_id
                and str(check.get("carrier") or "") in {"article", "image", "video"}
            ):
                try:
                    decoded_sample = json.loads(payload)
                except json.JSONDecodeError:
                    decoded_sample = None
                if isinstance(decoded_sample, dict):
                    author_persona_id = str(
                        decoded_sample.get("authorId") or ""
                    ).strip()
        if matched and check["name"] == CREATOR_PROFILE_CHECK_NAME:
            semantic_issue, persona_id, avatar_ref = (
                _release_creator_profile_semantic_result(
                    payload,
                    expected_persona_id=str(check.get("personaId") or ""),
                    expected_display_name=str(check.get("displayName") or ""),
                    expected_avatar_delivery_ref=str(
                        check.get("avatarDeliveryRef") or ""
                    ),
                )
            )
            entry.update(
                {
                    key: check.get(key)
                    for key in (
                        "creatorRef",
                        "authorId",
                        "personaId",
                        "displayName",
                        "avatarAssetId",
                        "avatarDeliveryRef",
                    )
                }
            )
            entry["returnedPersonaId"] = persona_id
            entry["returnedAvatarDeliveryRef"] = avatar_ref
            entry["responseDigest"] = "sha256:" + hashlib.sha256(
                payload.encode("utf-8")
            ).hexdigest()
            entry["responseBytes"] = len(payload.encode("utf-8"))
            if semantic_issue:
                matched = False
                entry["ok"] = False
                entry["semanticError"] = semantic_issue
        results.append(entry)
        if not matched:
            detail = entry.get("semanticError")
            findings.append(
                f"{check['name']} failed: {status_code or 'ERR'} {check['url']}"
                + (f" ({detail})" if detail else "")
            )

    author_posts_selected = (
        not only_checks or AUTHOR_POSTS_CHECK_NAME in only_checks
    )
    if author_posts_selected and (
        author_persona_id or AUTHOR_POSTS_CHECK_NAME in only_checks
    ):
        if not author_persona_id:
            findings.append(
                f"{AUTHOR_POSTS_CHECK_NAME} failed: requires a successful "
                "release_sample post readback in the same run"
            )
        else:
            author_posts_url = (
                f"{args.base_url.rstrip('/')}/content/personas/"
                f"{urllib.parse.quote(author_persona_id, safe='')}/posts?limit=5"
            )
            ok, status_code, payload = request(
                "GET",
                author_posts_url,
                headers=_common_headers(args.test_auth_token),
                timeout=max(1, request_timeout_seconds),
                retry_attempts=max(1, retry_attempts),
                retry_sleep_seconds=max(0.0, retry_sleep_seconds),
            )
            matched = ok and status_code == 200
            entry = {
                "name": AUTHOR_POSTS_CHECK_NAME,
                "method": "GET",
                "url": author_posts_url,
                "statusCode": status_code,
                "ok": matched,
                "bodyPreview": payload[:1200],
                "authorPersonaId": author_persona_id,
            }
            if matched:
                semantic_issue, item_count = _author_posts_semantic_result(payload)
                if item_count is not None:
                    entry["contentItemCount"] = item_count
                if semantic_issue:
                    matched = False
                    entry["ok"] = False
                    entry["semanticError"] = semantic_issue
            results.append(entry)
            if not matched:
                detail = entry.get("semanticError")
                findings.append(
                    f"{AUTHOR_POSTS_CHECK_NAME} failed: "
                    f"{status_code or 'ERR'} {author_posts_url}"
                    + (f" ({detail})" if detail else "")
                )

    feed_media_selected = (
        not only_checks or FEED_MEDIA_SLICES_CHECK_NAME in only_checks
    )
    if feed_media_selected and (
        feed_media_slices or FEED_MEDIA_SLICES_CHECK_NAME in only_checks
    ):
        if not feed_media_origin:
            findings.append(
                f"{FEED_MEDIA_SLICES_CHECK_NAME} failed: requires a media base URL"
            )
        elif not feed_media_slices:
            findings.append(
                f"{FEED_MEDIA_SLICES_CHECK_NAME} failed: requires at least one "
                "successful feed check with media slices in the same run"
            )
        else:
            slice_failures: list[str] = []
            checked = 0
            for slice_url in sorted(feed_media_slices):
                slice_kind = feed_media_slices[slice_url]
                slice_headers = dict(_common_headers(args.test_auth_token))
                expected = [200]
                if slice_kind == "video":
                    # 视频以 Range 读首字节，验证 media-edge 支持分段拉流。
                    slice_headers["Range"] = "bytes=0-1"
                    expected = [200, 206]
                ok, status_code, _payload = request(
                    "GET",
                    slice_url,
                    headers=slice_headers,
                    timeout=max(1, request_timeout_seconds),
                    retry_attempts=max(1, retry_attempts),
                    retry_sleep_seconds=max(0.0, retry_sleep_seconds),
                )
                checked += 1
                if not ok or status_code not in expected:
                    slice_failures.append(
                        f"{status_code or 'ERR'} {slice_kind} {slice_url}"
                    )
            entry = {
                "name": FEED_MEDIA_SLICES_CHECK_NAME,
                "method": "GET",
                "url": feed_media_origin,
                "statusCode": 200 if not slice_failures else 0,
                "ok": not slice_failures,
                "bodyPreview": "",
                "sliceCount": checked,
                "sliceFailures": slice_failures,
            }
            results.append(entry)
            if slice_failures:
                findings.append(
                    f"{FEED_MEDIA_SLICES_CHECK_NAME} failed: "
                    f"{len(slice_failures)}/{checked} feed media slices are "
                    "unreadable: " + "; ".join(slice_failures[:5])
                )
    report = {
        "schema": "environment-integration-probe-report",
        "status": "passed" if not findings else "failed",
        "env": args.env,
        "mode": mode,
        "startedAt": started_at,
        "endedAt": utc_now(),
        "baseUrl": args.base_url.rstrip("/"),
        "productOpsBaseUrl": args.product_ops_base_url.rstrip("/"),
        "mediaImageBaseUrl": media_image_base_url.rstrip("/"),
        "releaseIdentity": release_identity or {},
        "requestTimeoutSeconds": request_timeout_seconds,
        "retryAttempts": retry_attempts,
        "retrySleepSeconds": retry_sleep_seconds,
        "onlyChecks": sorted(only_checks),
        "requireNonEmptyContentFeed": require_authenticated_feed,
        "researchAnonymousConvergence": research_anonymous_convergence,
        "researchConsumerReadback": research_consumer_readback,
        "researchConsumerAttested": bool(research_consumer_attestation),
        "checks": results,
        "findings": findings,
    }
    return _redact_sensitive_values(
        report,
        (
            str(args.test_auth_token or ""),
            research_consumer_attestation,
        ),
    )


def main() -> int:
    args = parse_args()
    report = run_checks(args)
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[environment-integration-probe] report: {report_path}")
    print(f"[environment-integration-probe] status: {report['status']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
