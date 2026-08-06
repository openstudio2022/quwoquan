#!/usr/bin/env python3
"""通过 Product/Platform Ops 控制面查询异常分诊，禁止直连日志存储。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


PRODUCT_OPS_BASE_URL = os.environ.get("PRODUCT_OPS_BASE_URL", "").rstrip("/")
PLATFORM_OPS_BASE_URL = os.environ.get("PLATFORM_OPS_BASE_URL", "").rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    triage = sub.add_parser("triage")
    triage.add_argument("--domain", choices=["product", "platform"], required=True)
    triage.add_argument("--env", default="")
    triage.add_argument("--cluster", default="")
    triage.add_argument("--service", default="")
    triage.add_argument("--page-name", default="")
    triage.add_argument("--surface-id", default="")
    triage.add_argument("--output", choices=["json", "markdown"], default="json")

    args = parser.parse_args()
    payload = query_control_plane_triage(args)
    if payload is None:
        raise SystemExit(
            "GATE_BLOCK: canonical Product/Platform Ops query API is unavailable"
        )
    emit_triage_result(args.domain, payload, args.output)
    return 0


def query_control_plane_triage(args: argparse.Namespace) -> dict[str, Any] | None:
    base_url = PRODUCT_OPS_BASE_URL if args.domain == "product" else PLATFORM_OPS_BASE_URL
    if not base_url:
        return None
    if args.domain == "product":
        path = build_query_path(
            "/control-plane/product/triage/summary",
            {
                "pageName": args.page_name,
                "surfaceId": args.surface_id,
            },
        )
    else:
        path = build_query_path(
            "/control-plane/platform/triage/summary",
            {
                "env": args.env,
                "cluster": args.cluster,
                "service": args.service,
            },
        )
    try:
        return request_json_url(
            "GET",
            urllib.parse.urljoin(f"{base_url}/", path.lstrip("/")),
        )
    except SystemExit:
        return None


def build_query_path(path: str, params: dict[str, str]) -> str:
    filtered = {key: value for key, value in params.items() if str(value or "").strip()}
    if not filtered:
        return path
    return f"{path}?{urllib.parse.urlencode(filtered)}"


def emit_triage_result(domain: str, payload: dict[str, Any], output: str) -> None:
    if output == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"# {domain} triage")
    backlog = payload.get("backlogCandidates") or []
    if not backlog:
        print("\n无 backlogCandidates。")
        return
    for item in backlog:
        print(
            "- `{id}` `{severity}` {title} next=`{next_action}` "
            "runbook={runbook} repair={repair} audit={audit} alert={alert}".format(
                id=item.get("id", ""),
                severity=item.get("severity", ""),
                title=item.get("title", ""),
                next_action=item.get("nextAction", ""),
                runbook=item.get("runbookRoute", ""),
                repair=item.get("repairEntry", ""),
                audit=item.get("auditRoute", ""),
                alert=item.get("alertId", ""),
            )
        )


def request_json_url(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="ignore")
        raise SystemExit(
            f"control-plane request failed: {method} {exc.code} {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit("control-plane request failed") from exc
    return json.loads(raw) if raw else {}


if __name__ == "__main__":
    sys.exit(main())
