#!/usr/bin/env python3
# readiness_case: persisted_query_execution_readiness_ops_env
# spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/multi-domain-result-composition/spec.md#gwt-002
"""Execute canonical SearchPage persisted GraphQL without requiring non-empty content."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[7]
PERSISTED_QUERY = (
    REPO_ROOT
    / "quwoquan_service/services/api-edge/contracts/graphql_read/"
    "persisted_query_execution/persisted_queries/search_page.yaml"
)
SCHEMA = "persisted-query-execution-readiness-report"


class ProbeFailure(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("beta", "gamma"), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--query", default="西湖")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument(
        "--report",
        default=".qwq_output/env/repo/runs/persisted-query-execution-readiness/report.json",
    )
    return parser.parse_args()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _descriptor() -> tuple[str, str]:
    payload = yaml.safe_load(PERSISTED_QUERY.read_text(encoding="utf-8")) or {}
    operation = str(payload.get("operationName") or "").strip()
    digest = str(payload.get("sha256Hash") or "").strip()
    if operation != "SearchPage" or len(digest) != 64:
        raise ProbeFailure("descriptor_invalid", "canonical SearchPage descriptor is invalid")
    return operation, digest


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    operation, digest = _descriptor()
    context = ssl.create_default_context()
    if args.insecure:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    body = {
        "operationName": operation,
        "variables": {"input": {"query": args.query, "first": 1}},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": digest}},
    }
    request = urllib.request.Request(
        args.base_url.rstrip("/") + "/graphql",
        data=json.dumps(body).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15, context=context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProbeFailure("http_error", f"POST /graphql returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ProbeFailure("gateway_unreachable", f"gateway request failed: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ProbeFailure("graphql_error", "SearchPage returned GraphQL errors")
    data = payload.get("data")
    page = data.get("searchPage") if isinstance(data, dict) else None
    if not isinstance(page, dict):
        raise ProbeFailure("contract_mismatch", "SearchPage response root is missing")
    for field in ("items", "facets", "suggestions", "matchedTerms", "degradeSignals"):
        if not isinstance(page.get(field), list):
            raise ProbeFailure("contract_mismatch", f"SearchPage.{field} is not a list")
    request_id = str(page.get("searchRequestId") or "").strip()
    if not request_id:
        raise ProbeFailure("contract_mismatch", "SearchPage.searchRequestId is missing")
    return {"searchRequestId": request_id, "itemCount": len(page["items"]), "descriptorSha256": digest}


def _write(path: str, report: dict[str, Any]) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = REPO_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    args = _args()
    if not args.query.strip():
        raise SystemExit("--query must be non-empty")
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
        report["evidence"] = _execute(args)
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
