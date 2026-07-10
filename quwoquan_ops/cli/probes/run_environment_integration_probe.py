#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT = (
    REPO_ROOT / ".qwq_output" / "env" / "repo" / "runs" / "integration-probe" / "report.json"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run readonly integration probes for alpha/beta/gamma/prod environments.",
    )
    parser.add_argument("--env", required=True, choices=("alpha", "beta", "gamma", "prod"))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-base-url", default="")
    parser.add_argument("--test-auth-token", default="")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--request-timeout-seconds", type=int, default=12)
    parser.add_argument("--retry-attempts", type=int, default=2)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument(
        "--require-non-empty-content-feed",
        action="store_true",
        help="Fail when content_feed returns an empty [] / {} / {\"items\": []} payload.",
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
        "alpha": ("ALPHA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN", "GAMMA_TEST_AUTH_TOKEN"),
        "beta": ("BETA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN", "GAMMA_TEST_AUTH_TOKEN"),
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
        req = urllib.request.Request(url, headers=headers or {}, data=body, method=method)
        ctx = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
                payload = response.read().decode("utf-8", errors="replace")
                return True, int(response.status), payload
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return False, int(exc.code), payload
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if attempt >= total_attempts or not any(marker in message for marker in retry_markers):
                return False, None, message
            time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return False, None, "unknown request failure"


def _common_headers(test_auth_token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "X-Client-User-Id": "fixture_user_current",
        "X-Test-Local-Gamma": "true",
    }
    token = test_auth_token.strip()
    if token:
        headers["Authorization"] = "Bearer " + token
        headers["X-Test-Auth-Token"] = token
    return headers


def _json_headers(test_auth_token: str) -> dict[str, str]:
    headers = _common_headers(test_auth_token)
    headers["Content-Type"] = "application/json"
    return headers


def _public_headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def _readonly_sync_headers() -> dict[str, str]:
    # user_sync readiness只验证 route/handler/data-plane 是否可读。
    # user-service 若收到当前 stage 无法本地验签的 Bearer token，会按安全逻辑清空
    # X-Client-User-Id 并返回 400；这里显式走稳定的 header-only 探针，避免把
    # stage-secret 不一致误判成部署后业务不就绪。
    headers = _common_headers("")
    headers["Content-Type"] = "application/json"
    return headers


def build_checks(args: argparse.Namespace) -> list[dict[str, Any]]:
    base = args.base_url.rstrip("/")
    public_headers = _public_headers() if args.env == "prod" else _common_headers(args.test_auth_token)
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
            "url": f"{base}/v1/config/app",
            "headers": public_headers,
            "expected_statuses": [200],
        },
        {
            "name": "content_feed",
            "method": "GET",
            "url": f"{base}/v1/content/feed?limit=1",
            "headers": public_headers,
            "expected_statuses": [200],
        },
        {
            "name": "chat_inbox",
            "method": "GET",
            "url": f"{base}/v1/chat/inbox?limit=1",
            "headers": _common_headers(args.test_auth_token),
            "expected_statuses": [200],
        },
        {
            "name": "user_sync",
            "method": "POST",
            "url": f"{base}/v1/user/sync",
            "headers": _readonly_sync_headers(),
            "body": json.dumps({"afterSeq": 0, "limit": 1}, ensure_ascii=False).encode(
                "utf-8"
            ),
            "expected_statuses": [200],
        },
    ]
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
    media_base = args.media_base_url.rstrip("/")
    if media_base:
        checks.append(
            {
                "name": "media_sample",
                "method": "GET",
                "url": f"{media_base}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
                "headers": public_headers,
                "expected_statuses": [200],
            }
        )
    return checks


def _content_feed_semantic_issue(payload: str) -> tuple[str | None, int | None]:
    body = payload.strip()
    if not body:
        return "response body is empty", 0
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", None
    if decoded in ([], {}):
        return "response payload is empty", 0
    if isinstance(decoded, dict):
        items = decoded.get("items")
        if isinstance(items, list):
            if not items:
                return 'response payload has empty "items"', 0
            return None, len(items)
    if isinstance(decoded, list):
        return None, len(decoded)
    return None, None


def run_checks(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now()
    findings: list[str] = []
    results: list[dict[str, Any]] = []
    for check in build_checks(args):
        ok, status_code, payload = request(
            check["method"],
            check["url"],
            headers=check.get("headers"),
            body=check.get("body"),
            timeout=max(1, int(args.request_timeout_seconds)),
            retry_attempts=max(1, int(args.retry_attempts)),
            retry_sleep_seconds=max(0.0, float(args.retry_sleep_seconds)),
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
            and args.require_non_empty_content_feed
            and check["name"] == "content_feed"
        ):
            semantic_issue, item_count = _content_feed_semantic_issue(payload)
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
                f"{check['name']} failed: {status_code or 'ERR'} {check['url']}"
                + (f" ({detail})" if detail else "")
            )
    return {
        "schemaVersion": 1,
        "status": "passed" if not findings else "failed",
        "env": args.env,
        "mode": args.mode,
        "startedAt": started_at,
        "endedAt": utc_now(),
        "baseUrl": args.base_url.rstrip("/"),
        "productOpsBaseUrl": args.product_ops_base_url.rstrip("/"),
        "mediaBaseUrl": args.media_base_url.rstrip("/"),
        "requestTimeoutSeconds": args.request_timeout_seconds,
        "retryAttempts": args.retry_attempts,
        "retrySleepSeconds": args.retry_sleep_seconds,
        "requireNonEmptyContentFeed": args.require_non_empty_content_feed,
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
