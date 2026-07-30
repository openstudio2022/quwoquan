#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.media_delivery_manifest import build_media_delivery_url
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


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


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
    parser.add_argument("--test-auth-token", default="")
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
        "--expected-discovery-post-id",
        action="append",
        default=[],
        help=(
            "Release-bound postId accepted by the identity=work readback; repeatable. "
            "At least one returned item must match."
        ),
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
        "--mode",
        choices=("readonly", "post-deploy"),
        default="readonly",
    )
    args = parser.parse_args()
    args.test_auth_token = _resolve_test_auth_token(args.env, args.test_auth_token)
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


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 12,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 2.0,
) -> tuple[bool, int | None, str]:
    retry_markers = (
        "timed out",
        "Remote end closed connection without response",
        "Connection reset",
        "Connection closed",
    )
    total_attempts = max(1, retry_attempts)
    for attempt in range(1, total_attempts + 1):
        req = urllib.request.Request(
            url, headers=headers or {}, data=body, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
                return True, int(response.status), payload
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return False, int(exc.code), payload
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if attempt >= total_attempts or not any(
                marker in message for marker in retry_markers
            ):
                return False, None, message
            time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return False, None, "unknown request failure"


def _common_headers(test_auth_token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
    }
    token = test_auth_token.strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def _json_headers(test_auth_token: str) -> dict[str, str]:
    headers = _common_headers(test_auth_token)
    headers["Content-Type"] = "application/json"
    return headers


def _public_headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def _owner_matches_post(owner_ref: object, post_ref: str) -> bool:
    owner = str(owner_ref or "").strip().strip("/")
    post = str(post_ref or "").strip().strip("/")
    return owner == post or owner == f"posts/{post}"


def _release_probe_identity(args: argparse.Namespace) -> dict[str, Any]:
    raw_receipt = str(getattr(args, "release_readiness", "") or "").strip()
    if not raw_receipt:
        raise ReleaseVideoDeliveryError(
            "DATA_RELEASE_READINESS_RECEIPT is required for the media integration probe"
        )
    identity = load_release_content_identity(
        resolve_readiness_path(raw_receipt),
        expected_environment=args.env,
    )
    image_posts = {
        str(binding["postRef"]).strip().strip("/")
        for binding in identity["postBindings"]
        if binding.get("contentType") == "image"
    }
    candidates = sorted(
        (
            dict(asset)
            for asset in identity["mediaAssets"]
            if asset.get("kind") == "image"
            and str(asset.get("contentType") or "").lower().startswith("image/")
            and str(asset.get("publicSliceKey") or "").startswith("media/image/s/")
            and any(
                _owner_matches_post(owner, post_ref)
                for owner in asset.get("ownerRefs") or []
                for post_ref in image_posts
            )
        ),
        key=lambda asset: (
            str(asset.get("assetId") or ""),
            str(asset.get("publicSliceKey") or ""),
        ),
    )
    if not candidates:
        raise ReleaseVideoDeliveryError(
            "canonical Data readiness/import receipt has no release-bound image asset"
        )
    media = candidates[0]
    version = media.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
        raise ReleaseVideoDeliveryError(
            "release-bound image asset version must be a positive integer"
        )
    return {
        "releaseId": identity["releaseId"],
        "manifestDigest": identity["manifestDigest"],
        "importRunId": identity["importRunId"],
        "verifyRunId": identity["verifyRunId"],
        "readinessReceiptRef": identity["readinessReceiptRef"],
        "media": {
            "assetId": str(media["assetId"]),
            "version": version,
            "publicSliceKey": str(media["publicSliceKey"]),
            "sha256": str(media.get("sha256") or ""),
            "contentType": str(media["contentType"]),
        },
    }


def build_checks(
    args: argparse.Namespace,
    *,
    release_identity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    base = args.base_url.rstrip("/")
    require_non_empty_content_feed = bool(
        getattr(args, "require_non_empty_content_feed", False)
    )
    media_image_base_url = str(
        getattr(
            args,
            "media_image_base_url",
            getattr(args, "media_base_url", ""),
        )
        or ""
    )
    public_headers = (
        _public_headers()
        if args.env == "prod"
        else _common_headers(args.test_auth_token)
    )
    checks: list[dict[str, Any]] = [
        {
            "name": "gateway_healthz",
            "method": "GET",
            "url": f"{base}/healthz",
            "headers": public_headers,
            "expected_statuses": [200],
        },
        {
            "name": "app_config",
            "method": "GET",
            "url": f"{base}/config/app",
            "headers": public_headers,
            "expected_statuses": [200],
        },
        {
            "name": "content_feed",
            "method": "GET",
            "url": f"{base}/content/feed?identity=work&sort=recommend&limit=1",
            "headers": public_headers,
            "expected_statuses": [200],
        },
        {
            "name": "entity_homepage_search",
            "method": "GET",
            "url": f"{base}/homepages/search?query=%E8%A5%BF%E6%B9%96&limit=1",
            "headers": _common_headers(args.test_auth_token),
            "expected_statuses": [200],
        },
        {
            "name": "global_search",
            "method": "POST",
            "url": f"{base}/search",
            "headers": _json_headers(args.test_auth_token),
            "body": json.dumps(
                {"query": "西湖", "mode": "result", "limit": 1},
                ensure_ascii=False,
            ).encode("utf-8"),
            "expected_statuses": [200],
        },
    ]
    if require_non_empty_content_feed:
        checks.extend(
            [
                {
                    "name": "video_book_feed",
                    "method": "GET",
                    "url": (
                        f"{base}/content/feed?identity=work&type=video"
                        "&sort=recommend&limit=1"
                    ),
                    "headers": public_headers,
                    "expected_statuses": [200],
                },
                {
                    "name": "premium_feed",
                    "method": "GET",
                    "url": f"{base}/content/feed?channelId=premium_stream&limit=1",
                    "headers": public_headers,
                    "expected_statuses": [200],
                },
            ]
        )
    if args.test_auth_token:
        checks.append(
            {
                "name": "user_sync",
                "method": "POST",
                "url": f"{base}/user/sync",
                "headers": _json_headers(args.test_auth_token),
                "body": json.dumps(
                    {"afterSeq": 0, "limit": 1}, ensure_ascii=False
                ).encode("utf-8"),
                "expected_statuses": [200],
            }
        )
    product_ops = args.product_ops_base_url.rstrip("/")
    if product_ops:
        checks.append(
            {
                "name": "product_ops_healthz",
                "method": "GET",
                "url": f"{product_ops}/healthz",
                "headers": public_headers,
                "expected_statuses": [200],
            }
        )
    media_base = media_image_base_url.rstrip("/")
    media = (
        release_identity.get("media")
        if isinstance(release_identity, dict)
        else None
    )
    if media_base and isinstance(media, dict):
        checks.append(
            {
                "name": "media_sample",
                "method": "GET",
                "url": build_media_delivery_url(
                    {"mediaImage": media_base},
                    {
                        "mediaType": "image",
                        "publicSliceKey": media["publicSliceKey"],
                        "version": media["version"],
                    },
                ),
                "headers": public_headers,
                "expected_statuses": [200],
            }
        )
    return checks


def _content_feed_semantic_issue(payload: str) -> tuple[str | None, int | None]:
    issue, count, _post_ids = _content_feed_semantic_result(payload)
    return issue, count


def _content_feed_semantic_result(
    payload: str,
    *,
    expected_post_ids: set[str] | None = None,
) -> tuple[str | None, int | None, set[str]]:
    body = payload.strip()
    if not body:
        return "response body is empty", 0, set()
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", None, set()
    if decoded in ([], {}):
        return "response payload is empty", 0, set()
    items: list[Any] | None = None
    if isinstance(decoded, dict):
        candidate_items = decoded.get("items")
        if isinstance(candidate_items, list):
            items = candidate_items
    elif isinstance(decoded, list):
        items = decoded
    if items is None:
        return None, None, set()
    if not items:
        return 'response payload has empty "items"', 0, set()
    returned_post_ids = {
        str(item.get("postId") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("postId") or "").strip()
    }
    expected = {
        str(item).strip() for item in (expected_post_ids or set()) if str(item).strip()
    }
    if expected and not returned_post_ids.intersection(expected):
        return (
            "response has no postId bound to the expected immutable release",
            len(items),
            returned_post_ids,
        )
    return None, len(items), returned_post_ids


def _expected_release_post_ids(args: argparse.Namespace, check_name: str) -> set[str]:
    argument_names = {
        "content_feed": "expected_discovery_post_id",
        "video_book_feed": "expected_video_post_id",
        "premium_feed": "expected_premium_video_post_id",
    }
    argument_name = argument_names.get(check_name)
    if argument_name is None:
        return set()
    return {
        str(item).strip()
        for item in getattr(args, argument_name, [])
        if str(item).strip()
    }


def _search_semantic_issue(payload: str) -> tuple[str | None, int | None]:
    body = payload.strip()
    if not body:
        return "response body is empty", None
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", None
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", None
    request_id = decoded.get("requestId")
    if not isinstance(request_id, str) or not request_id.strip():
        return 'response payload is missing non-empty "requestId"', None
    hits = decoded.get("hits")
    if not isinstance(hits, list):
        return 'response payload is missing array "hits"', None
    return None, len(hits)


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
    for check in selected_checks:
        ok, status_code, payload = request(
            check["method"],
            check["url"],
            headers=check.get("headers"),
            body=check.get("body"),
            timeout=max(1, request_timeout_seconds),
            retry_attempts=max(1, retry_attempts),
            retry_sleep_seconds=max(0.0, retry_sleep_seconds),
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
        if (
            matched
            and require_non_empty_content_feed
            and check["name"] in {"content_feed", "video_book_feed", "premium_feed"}
        ):
            semantic_issue, item_count, returned_post_ids = (
                _content_feed_semantic_result(
                    payload,
                    expected_post_ids=_expected_release_post_ids(
                        args,
                        check["name"],
                    ),
                )
            )
            if item_count is not None:
                entry["contentItemCount"] = item_count
            if returned_post_ids:
                entry["returnedPostIds"] = sorted(returned_post_ids)
            if semantic_issue:
                matched = False
                entry["ok"] = False
                entry["semanticError"] = semantic_issue
        if matched and check["name"] == "global_search":
            semantic_issue, hit_count = _search_semantic_issue(payload)
            if hit_count is not None:
                entry["searchHitCount"] = hit_count
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
    return {
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
        "requireNonEmptyContentFeed": require_non_empty_content_feed,
        "checks": results,
        "findings": findings,
    }


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
