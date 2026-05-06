#!/usr/bin/env python3
"""验证 gamma curated media 对象能否经部署入口正确访问。"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "deploy" / "shared" / "gamma_curated_media_bundle.json"


def _request(url: str, timeout: float) -> Tuple[int, bytes, Dict[str, str]]:
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(
        url,
        headers={"X-Test-Local-Gamma": "true"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            headers = dict(resp.headers.items())
            return int(resp.status), resp.read(), headers
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        headers = dict(exc.headers.items()) if exc.headers else {}
        return int(exc.code), body, headers
    except urllib.error.URLError as exc:
        body = str(exc).encode("utf-8", errors="replace")
        return 0, body, {}


def _load_bundle(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_object(base_url: str, item: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    object_key = str(item.get("objectKey") or "").strip()
    url = base_url.rstrip("/") + "/" + object_key.lstrip("/")
    expected_size = int(item.get("sizeBytes") or 0)
    expected_mime = str(item.get("mimeType") or "").strip().lower()
    status, body, headers = _request(url, timeout)
    content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
    result = {
        "objectKey": object_key,
        "url": url,
        "httpStatus": status,
        "contentType": content_type,
        "bytes": len(body),
        "status": "passed",
    }  # type: Dict[str, Any]
    if not 200 <= status < 300:
        result["status"] = "failed"
        result["error"] = "http {}".format(status)
        result["bodyPreview"] = body[:160].decode("utf-8", errors="replace")
        return result
    if expected_size and len(body) != expected_size:
        result["status"] = "failed"
        result["error"] = "size mismatch: expected {}, got {}".format(expected_size, len(body))
    if expected_mime and content_type:
        actual_mime = content_type.split(";", 1)[0].strip().lower()
        if actual_mime != expected_mime:
            result["status"] = "failed"
            result["error"] = "mime mismatch: expected {}, got {}".format(expected_mime, actual_mime)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("GAMMA_BASE_URL", "http://127.0.0.1:18080"),
    )
    parser.add_argument(
        "--bundle",
        default=str(DEFAULT_BUNDLE),
        help="Path to gamma_curated_media_bundle.json",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Optional JSON report output path",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=12.0,
        help="Per-request timeout seconds",
    )
    args = parser.parse_args()

    bundle_path = Path(args.bundle)
    if not bundle_path.is_absolute():
        bundle_path = ROOT / bundle_path
    bundle = _load_bundle(bundle_path)
    media_objects = bundle.get("mediaObjects") or []

    report = {
        "status": "passed",
        "baseUrl": args.base_url.rstrip("/"),
        "bundle": str(bundle_path),
        "selectionProfile": bundle.get("selectionProfile"),
        "totalObjectCount": len(media_objects),
        "checks": [],
        "failures": [],
    }  # type: Dict[str, Any]

    failures = []  # type: List[Dict[str, Any]]
    for item in media_objects:
        if not isinstance(item, dict):
            continue
        result = _check_object(args.base_url, item, args.timeout)
        report["checks"].append(result)
        if result.get("status") != "passed":
            failures.append(result)

    if failures:
        report["status"] = "failed"
        report["failures"] = failures

    if args.report.strip():
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = ROOT / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if failures:
        print("[gamma-curated-media-routes] FAIL")
        for failure in failures[:10]:
            print(
                "  - {objectKey}: {error}".format(
                    objectKey=failure.get("objectKey", ""),
                    error=failure.get("error", "unknown error"),
                )
            )
        if len(failures) > 10:
            print("  - ... {} more failures".format(len(failures) - 10))
        return 2

    print(
        "[gamma-curated-media-routes] OK {} objects via {}".format(
            len(report["checks"]),
            args.base_url.rstrip("/"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
