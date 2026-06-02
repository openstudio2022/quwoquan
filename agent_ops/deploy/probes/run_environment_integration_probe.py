#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT = (
    REPO_ROOT / "artifacts" / "stackctl" / "integration-probe" / "report.json"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run readonly integration probes for beta/gamma/prod environments.",
    )
    parser.add_argument("--env", required=True, choices=("beta", "gamma", "prod"))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--test-auth-token", default="")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument(
        "--mode",
        choices=("readonly", "post-deploy"),
        default="readonly",
    )
    return parser.parse_args()


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 12,
) -> tuple[bool, int | None, str]:
    req = urllib.request.Request(url, headers=headers or {}, data=body, method=method)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return True, int(response.status), payload[:1200]
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, int(exc.code), payload[:1200]
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)


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


def build_checks(args: argparse.Namespace) -> list[dict[str, Any]]:
    base = args.base_url.rstrip("/")
    checks: list[dict[str, Any]] = [
        {
            "name": "gateway_healthz",
            "method": "GET",
            "url": f"{base}/healthz",
            "headers": _common_headers(args.test_auth_token),
            "expected_statuses": [200],
        },
        {
            "name": "app_config",
            "method": "GET",
            "url": f"{base}/v1/config/app",
            "headers": _common_headers(args.test_auth_token),
            "expected_statuses": [200],
        },
        {
            "name": "content_feed",
            "method": "GET",
            "url": f"{base}/v1/content/feed?limit=1",
            "headers": _common_headers(args.test_auth_token),
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
            "headers": _json_headers(args.test_auth_token),
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
                "headers": _common_headers(args.test_auth_token),
                "expected_statuses": [200],
            }
        )
    return checks


def run_checks(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now()
    findings: list[str] = []
    results: list[dict[str, Any]] = []
    for check in build_checks(args):
        ok, status_code, preview = request(
            check["method"],
            check["url"],
            headers=check.get("headers"),
            body=check.get("body"),
        )
        expected_statuses = list(check.get("expected_statuses") or [])
        matched = ok and status_code in expected_statuses
        entry = {
            "name": check["name"],
            "method": check["method"],
            "url": check["url"],
            "statusCode": status_code,
            "ok": matched,
            "bodyPreview": preview,
        }
        results.append(entry)
        if not matched:
            findings.append(
                f"{check['name']} failed: {status_code or 'ERR'} {check['url']}"
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
