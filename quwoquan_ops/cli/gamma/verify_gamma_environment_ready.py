#!/usr/bin/env python3
"""Wait until gamma environment is healthy enough for hosted smoke."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTING_SCRIPT = REPO_ROOT / "quwoquan_ops" / "cli" / "gamma" / "verify_gamma_public_gateway_routing.py"
RETRY_MARKERS = (
    "timed out",
    "Remote end closed connection without response",
    "Connection reset",
    "Connection closed",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "GAMMA_BASE_URL",
            "https://gamma-api.quwoquan-env.test:19000",
        ),
    )
    parser.add_argument(
        "--product-ops-base-url",
        default=os.environ.get("GAMMA_PRODUCT_OPS_BASE_URL", "").strip(),
    )
    parser.add_argument(
        "--report",
        default=".qwq_output/runs/gamma-readiness/report.json",
    )
    parser.add_argument("--wait-seconds", type=int, default=90)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument("--route-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--route-retry-attempts", type=int, default=3)
    parser.add_argument("--route-retry-sleep-seconds", type=float, default=2.0)
    return parser.parse_args()


def _is_retryable(message: str) -> bool:
    lowered = message.lower()
    return any(marker.lower() in lowered for marker in RETRY_MARKERS)


def request_ok(
    url: str,
    *,
    timeout: float,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> Tuple[bool, str]:
    total_attempts = max(1, retry_attempts)
    last_error = "unknown"
    for attempt in range(1, total_attempts + 1):
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if 200 <= int(resp.status) < 300:
                    return True, body[:200]
                return False, "http {0}: {1}".format(resp.status, body[:200])
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return False, "http {0}: {1}".format(exc.code, body[:200])
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt >= total_attempts or not _is_retryable(last_error):
                return False, last_error
            time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return False, last_error


def routing_ok(args: argparse.Namespace) -> Tuple[bool, str]:
    base_url = args.base_url.rstrip("/")
    argv = [
        sys.executable,
        str(ROUTING_SCRIPT),
        "--base-url",
        base_url,
        "--request-timeout-seconds",
        str(max(1.0, float(args.route_timeout_seconds))),
        "--retry-attempts",
        str(max(1, int(args.route_retry_attempts))),
        "--retry-sleep-seconds",
        str(max(0.0, float(args.route_retry_sleep_seconds))),
    ]
    route_timeout_budget = max(
        30.0,
        float(args.route_timeout_seconds)
        * max(1, int(args.route_retry_attempts))
        * 4.0,
    )
    result = subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=route_timeout_budget,
    )
    output = (result.stdout or "").strip()
    if result.returncode == 0:
        return True, output[-400:]
    return False, output[-800:]


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "startedAt": utc_now(),
        "endedAt": "",
        "environment": {
            "baseUrl": args.base_url.rstrip("/"),
            "productOpsBaseUrl": args.product_ops_base_url.rstrip("/"),
            "commitSha": os.environ.get("GITHUB_SHA", ""),
            "githubRunId": os.environ.get("GITHUB_RUN_ID", ""),
        },
        "attempts": [],
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    report = build_report(args)
    deadline = time.monotonic() + max(args.wait_seconds, 1)
    exit_code = 1
    last_reason = "unknown"

    while True:
        attempt: Dict[str, Any] = {
            "at": utc_now(),
            "baseHealth": {"status": "running", "detail": ""},
            "productOpsHealth": {"status": "skipped", "detail": ""},
            "routing": {"status": "running", "detail": ""},
        }
        base_ok, base_detail = request_ok(
            args.base_url.rstrip("/") + "/healthz",
            timeout=max(1.0, float(args.request_timeout_seconds)),
            retry_attempts=max(1, int(args.retry_attempts)),
            retry_sleep_seconds=max(0.0, float(args.retry_sleep_seconds)),
        )
        attempt["baseHealth"] = {
            "status": "passed" if base_ok else "failed",
            "detail": base_detail,
        }
        product_ok = True
        if args.product_ops_base_url.strip():
            product_ok, product_detail = request_ok(
                args.product_ops_base_url.rstrip("/") + "/healthz",
                timeout=max(1.0, float(args.request_timeout_seconds)),
                retry_attempts=max(1, int(args.retry_attempts)),
                retry_sleep_seconds=max(0.0, float(args.retry_sleep_seconds)),
            )
            attempt["productOpsHealth"] = {
                "status": "passed" if product_ok else "failed",
                "detail": product_detail,
            }
        try:
            routing_is_ok, routing_detail = routing_ok(args)
        except subprocess.TimeoutExpired:
            routing_is_ok = False
            routing_detail = "routing probe timed out"
        attempt["routing"] = {
            "status": "passed" if routing_is_ok else "failed",
            "detail": routing_detail,
        }
        report["attempts"].append(attempt)
        if base_ok and product_ok and routing_is_ok:
            report["status"] = "passed"
            exit_code = 0
            break

        if not base_ok:
            report["failureCategory"] = "gateway_healthz_not_ready"
            last_reason = "gateway /healthz not ready: {0}".format(base_detail)
        elif not product_ok:
            report["failureCategory"] = "product_ops_not_ready"
            last_reason = "product-ops /healthz not ready: {0}".format(product_detail)
        else:
            report["failureCategory"] = "gamma_routing_not_ready"
            last_reason = "gamma route probe failed: {0}".format(routing_detail[-300:])
        report["blockingReason"] = last_reason

        if time.monotonic() >= deadline:
            break
        time.sleep(max(args.poll_interval_seconds, 0.5))

    report["endedAt"] = utc_now()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if exit_code == 0:
        print("[gamma-readiness] PASS {0}".format(args.base_url.rstrip("/")))
    else:
        print("[gamma-readiness] FAIL {0}".format(last_reason), file=sys.stderr)
    print("[gamma-readiness] report: {0}".format(report_path))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
