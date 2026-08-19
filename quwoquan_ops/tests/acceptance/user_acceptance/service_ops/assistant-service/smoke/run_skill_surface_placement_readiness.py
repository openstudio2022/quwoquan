#!/usr/bin/env python3
# readiness_case: skill_surface_placement_readiness_ops_env
# spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
"""Read one authoritative SkillSurfacePlacement through the environment gateway."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[7]
SCHEMA = "skill-surface-placement-readiness-report"


class ProbeFailure(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("beta", "gamma"), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--surface-kind", choices=("conversation", "circle"), required=True)
    parser.add_argument("--surface-id", required=True)
    parser.add_argument("--auth-token-env", default="TEST_AUTH_TOKEN")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument(
        "--report",
        default=".qwq_output/env/repo/runs/skill-surface-placement-readiness/report.json",
    )
    return parser.parse_args()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _request(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get(args.auth_token_env, "").strip()
    if not token:
        raise ProbeFailure("auth_missing", f"missing bearer token in {args.auth_token_env}")
    context = ssl.create_default_context()
    if args.insecure:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    path = "/assistant/skill-placements/{}/{}".format(
        urllib.parse.quote(args.surface_kind, safe=""),
        urllib.parse.quote(args.surface_id, safe=""),
    )
    request = urllib.request.Request(
        args.base_url.rstrip("/") + path,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Client-Operation-Id": "GetSkillSurfacePlacement",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15, context=context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProbeFailure("http_error", f"GET placement returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ProbeFailure("gateway_unreachable", f"gateway request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProbeFailure("contract_mismatch", "placement response is not an object")
    nested = payload.get("data")
    return nested if isinstance(nested, dict) else payload


def _validate(payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    required = ("id", "surfaceKind", "surfaceId", "policy", "disabledSkillIds", "status", "revision")
    missing = [field for field in required if field not in payload]
    if missing:
        raise ProbeFailure("contract_mismatch", f"placement fields missing: {missing}")
    if payload["surfaceKind"] != args.surface_kind or payload["surfaceId"] != args.surface_id:
        raise ProbeFailure("identity_drift", "placement surface identity drifted")
    if not isinstance(payload["disabledSkillIds"], list):
        raise ProbeFailure("contract_mismatch", "disabledSkillIds is not a list")
    if not isinstance(payload["revision"], int) or payload["revision"] < 1:
        raise ProbeFailure("contract_mismatch", "revision is not a positive integer")
    return {
        "placementId": str(payload["id"]),
        "surfaceKind": payload["surfaceKind"],
        "surfaceId": payload["surfaceId"],
        "policy": payload["policy"],
        "status": payload["status"],
        "revision": payload["revision"],
        "disabledSkillCount": len(payload["disabledSkillIds"]),
    }


def _write(path: str, report: dict[str, Any]) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = REPO_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    args = _args()
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "running",
        "environment": args.env,
        "gatewayBaseUrl": args.base_url.rstrip("/"),
        "startedAt": _now(),
        "endedAt": "",
        "failureCategory": "",
        "blockingReason": "",
        "evidence": {},
    }
    result = 1
    try:
        report["evidence"] = _validate(_request(args), args)
        report["status"] = "passed"
        result = 0
    except ProbeFailure as exc:
        report["status"] = "failed"
        report["failureCategory"] = exc.category
        report["blockingReason"] = str(exc)
    finally:
        report["endedAt"] = _now()
        target = _write(args.report, report)
        print(json.dumps({"status": report["status"], "report": str(target)}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
