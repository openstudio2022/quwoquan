#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BUNDLE = ROOT / "deploy" / "shared" / "gamma_curated_media_bundle.json"
DEFAULT_REPORT = ROOT / "artifacts" / "local-gamma" / "gamma_curated_media_routes.json"
PRIORITY_KEYS = [
    "media/avatar/user/fixture_user_current/v1/avatar.png",
    "media/avatar/group/fixture_conv_group/v1/composite.png",
    "media/avatar/circle/fixture_circle_photo/v1/avatar.png",
    "media/image/circle/fixture_circle_photo/v1/cover.png",
    "media/image/post/fixture_photo_001/v1/cover.png",
    "media/image/post/fixture_article_001/v1/cover.png",
    "media/image/post/fixture_video_001/v1/cover.png",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--sample-size", type=int, default=12)
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


def request_status(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=8, context=ctx) as response:
        return {
            "status": "passed" if 200 <= int(response.status) < 300 else "failed",
            "httpStatus": int(response.status),
            "bytes": len(response.read()),
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

    for object_key in sampled:
        url = f"{base_url}/{object_key}"
        entry = {
            "objectKey": object_key,
            "url": url,
        }
        try:
            entry.update(request_status(url))
        except urllib.error.HTTPError as exc:
            entry["status"] = "failed"
            entry["httpStatus"] = int(exc.code)
            entry["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            entry["status"] = "failed"
            entry["error"] = str(exc)
        if entry["status"] != "passed":
            failures = True
        checks.append(entry)

    report = {
        "status": "failed" if failures else "passed",
        "baseUrl": base_url,
        "bundle": str(bundle_path.relative_to(ROOT)),
        "sampleSize": len(sampled),
        "checks": checks,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[gamma-curated-media] report: {report_path}")
    print(f"[gamma-curated-media] status: {report['status']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
