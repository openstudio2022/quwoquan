#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BUNDLE = ROOT / "quwoquan_ops" / "environments" / "gamma_curated_media_bundle.json"
DEFAULT_REPORT = ROOT / ".qwq_output" / "env" / "gamma" / "runs" / "local-gamma" / "gamma_curated_media_routes.json"
RETRY_MARKERS = (
    "timed out",
    "Remote end closed connection without response",
    "Connection reset",
    "Connection closed",
)
PRIORITY_KEYS = [
    "media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png",
    "media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png",
    "media/avatar/s/archived-avatar/circle/fixture_circle_photo/v1/avatar.png",
    "media/image/s/archived-image/circle/fixture_circle_photo/v1/cover.png",
    "media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
    "media/image/s/archived-image/post/fixture_article_001/v1/cover.png",
    "media/image/s/archived-image/post/fixture_video_001/v1/cover.png",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--sample-size", type=int, default=12)
    parser.add_argument("--request-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument("--max-workers", type=int, default=4)
    return parser.parse_args()


def stable_sample(object_keys: list[str], sample_size: int) -> list[str]:
    selected: list[str] = []
    for key in PRIORITY_KEYS:
        if key in object_keys and key not in selected:
            selected.append(key)
    remaining = [
        key for key in object_keys
        if key not in selected
    ]
    remaining.sort(key=lambda item: hashlib.sha256(item.encode("utf-8")).hexdigest())
    selected.extend(remaining[: max(0, sample_size - len(selected))])
    return selected[:sample_size]


def request_status(
    url: str,
    *,
    timeout: float,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    total_attempts = max(1, retry_attempts)
    last_error = "unknown"
    for attempt in range(1, total_attempts + 1):
        for method, headers in (
            ("HEAD", {}),
            ("GET", {"Range": "bytes=0-0"}),
        ):
            request = urllib.request.Request(url, method=method, headers=headers)
            ctx = ssl._create_unverified_context()
            try:
                with urllib.request.urlopen(request, timeout=timeout, context=ctx) as response:
                    bytes_count = 0
                    if method == "GET":
                        bytes_count = len(response.read(1))
                    return {
                        "status": "passed" if 200 <= int(response.status) < 300 else "failed",
                        "httpStatus": int(response.status),
                        "bytes": bytes_count,
                        "method": method,
                    }
            except urllib.error.HTTPError as exc:
                if method == "HEAD" and int(exc.code) in {400, 405, 501}:
                    continue
                return {
                    "status": "failed",
                    "httpStatus": int(exc.code),
                    "error": str(exc),
                    "method": method,
                }
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                break
        lowered = last_error.lower()
        if attempt >= total_attempts or not any(marker.lower() in lowered for marker in RETRY_MARKERS):
            return {
                "status": "failed",
                "error": last_error,
            }
        time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return {
        "status": "failed",
        "error": last_error,
    }


def main() -> int:
    args = parse_args()
    bundle_path = Path(args.bundle)
    if not bundle_path.is_absolute():
        bundle_path = ROOT / bundle_path
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path

    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    object_keys = [str(item.get("objectKey") or "") for item in payload.get("mediaObjects") or [] if str(item.get("objectKey") or "").strip()]
    sampled = stable_sample(object_keys, max(1, args.sample_size))
    checks: list[dict[str, Any]] = []
    failures = False
    base_url = args.base_url.rstrip("/")

    timeout_seconds = max(1.0, float(args.request_timeout_seconds))
    retry_attempts = max(1, int(args.retry_attempts))
    retry_sleep_seconds = max(0.0, float(args.retry_sleep_seconds))
    max_workers = max(1, int(args.max_workers))

    def check_one(object_key: str) -> dict[str, Any]:
        url = f"{base_url}/{object_key}"
        entry = {
            "objectKey": object_key,
            "url": url,
        }
        entry.update(
            request_status(
                url,
                timeout=timeout_seconds,
                retry_attempts=retry_attempts,
                retry_sleep_seconds=retry_sleep_seconds,
            )
        )
        return entry

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(check_one, sampled))

    for entry in results:
        if entry["status"] != "passed":
            failures = True
        checks.append(entry)

    report = {
        "status": "failed" if failures else "passed",
        "baseUrl": base_url,
        "bundle": str(bundle_path.relative_to(ROOT)),
        "sampleSize": len(sampled),
        "requestTimeoutSeconds": timeout_seconds,
        "retryAttempts": retry_attempts,
        "retrySleepSeconds": retry_sleep_seconds,
        "maxWorkers": max_workers,
        "checks": checks,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[gamma-curated-media] report: {report_path}")
    print(f"[gamma-curated-media] status: {report['status']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
