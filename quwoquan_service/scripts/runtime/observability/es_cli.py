#!/usr/bin/env python3
"""本机异常观测 ES 管理、模板初始化、smoke 与查询脚本。"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
COMPOSE_FILE = ROOT / "deploy" / "observability" / "es" / "docker-compose.yml"
ES_URL = os.environ.get("QUWOQUAN_ES_URL", "http://localhost:9200").rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("up")
    sub.add_parser("down")
    sub.add_parser("health")
    sub.add_parser("bootstrap")
    sub.add_parser("smoke")

    query = sub.add_parser("query")
    query.add_argument("--env", default="")
    query.add_argument("--error-code", default="")
    query.add_argument("--trace-id", default="")
    query.add_argument("--request-id", default="")
    query.add_argument("--hours", type=int, default=24)
    query.add_argument("--limit", type=int, default=20)
    query.add_argument("--output", choices=["json", "markdown"], default="json")

    report = sub.add_parser("daily-report")
    report.add_argument("--env", default="")
    report.add_argument("--hours", type=int, default=24)
    report.add_argument("--limit", type=int, default=200)
    report.add_argument("--output", choices=["json", "markdown"], default="markdown")

    trace = sub.add_parser("trace-samples")
    trace.add_argument("--trace-id", required=True)
    trace.add_argument("--hours", type=int, default=24)
    trace.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    if args.command == "up":
        return compose("up", "-d", "--wait")
    if args.command == "down":
        return compose("down")
    if args.command == "health":
        health(require_ready=True)
        print("OK: Elasticsearch is healthy")
        return 0
    if args.command == "bootstrap":
        bootstrap()
        print("OK: Elasticsearch templates bootstrapped")
        return 0
    if args.command == "smoke":
        bootstrap()
        smoke()
        print("OK: Elasticsearch exception smoke passed")
        return 0
    if args.command == "query":
        docs = query_recent(args)
        emit_query_result(docs, args.output)
        return 0
    if args.command == "daily-report":
        docs = query_report_docs(args.env, args.hours, args.limit)
        groups = group_by_fingerprint(docs)
        emit_report(groups, args.output)
        return 0
    if args.command == "trace-samples":
        docs = query_trace_samples(args.trace_id, args.hours, args.limit)
        print(json.dumps({"items": docs}, ensure_ascii=False, indent=2))
        return 0
    raise AssertionError(args.command)


def compose(*args: str) -> int:
    ensure_docker()
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), *args]
    return subprocess.call(cmd, cwd=ROOT)


def ensure_docker() -> None:
    try:
        ok = subprocess.call(
            ["docker", "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise SystemExit("GATE_BLOCK: Docker Compose is required for local ES validation") from exc
    if ok != 0:
        raise SystemExit("GATE_BLOCK: Docker Compose is required for local ES validation")


def health(require_ready: bool = False) -> dict[str, Any]:
    deadline = time.time() + (120 if require_ready else 1)
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            data = request_json("GET", "/_cluster/health?wait_for_status=yellow&timeout=2s")
            if data.get("status") in {"green", "yellow"}:
                return data
        except Exception as exc:  # noqa: BLE001 - health command reports the last transport error.
            last_error = exc
        time.sleep(2)
    raise SystemExit(f"GATE_BLOCK: Elasticsearch is not healthy: {last_error}")


def bootstrap() -> None:
    health(require_ready=True)
    request_json("PUT", "/_index_template/quwoquan-exceptions-template", index_template("quwoquan-exceptions-*"))
    request_json("PUT", "/_index_template/quwoquan-cloud-logs-template", index_template("quwoquan-cloud-logs-*"))


def smoke() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    request_id = "req_es_smoke_app"
    trace_id = "trace_es_smoke"
    docs = [
        exception_doc(
            event_id="app_exception_smoke",
            source="app.exception",
            app_runtime_env="alpha",
            error_code="APP.RUNTIME.uncaught_exception",
            request_id=request_id,
            trace_id=trace_id,
            page_id="global.app.runtime",
            occurred_at=now,
        ),
        exception_doc(
            event_id="cloud_exception_smoke",
            source="cloud.exception",
            app_runtime_env="alpha",
            error_code="OPS.RUNTIME.internal_error",
            request_id="req_es_smoke_cloud",
            trace_id=trace_id,
            page_id="ops.event.report",
            occurred_at=now,
        ),
    ]
    for doc in docs:
        request_json("PUT", f"/quwoquan-exceptions-{now:%Y.%m.%d}/_doc/{doc['eventId']}", doc)
    request_json("POST", "/quwoquan-exceptions-*/_refresh")
    result = search(
        "quwoquan-exceptions-*",
        filters={"requestId": request_id, "traceId": trace_id, "errorCode": "APP.RUNTIME.uncaught_exception"},
        hours=1,
        limit=5,
    )
    hits = result.get("hits", {}).get("hits", [])
    if not hits:
        raise SystemExit("GATE_BLOCK: smoke exception document was not queryable")


def query_recent(args: argparse.Namespace) -> list[dict[str, Any]]:
    filters = {
        "appRuntimeEnv": args.env,
        "errorCode": args.error_code,
        "traceId": args.trace_id,
        "requestId": args.request_id,
    }
    result = search("quwoquan-exceptions-*", filters=filters, hours=args.hours, limit=args.limit)
    return [hit.get("_source", {}) for hit in result.get("hits", {}).get("hits", [])]


def query_report_docs(env: str, hours: int, limit: int) -> list[dict[str, Any]]:
    result = search(
        "quwoquan-exceptions-*",
        filters={"appRuntimeEnv": env},
        hours=hours,
        limit=limit,
    )
    return [hit.get("_source", {}) for hit in result.get("hits", {}).get("hits", [])]


def query_trace_samples(trace_id: str, hours: int, limit: int) -> list[dict[str, Any]]:
    result = search(
        "quwoquan-exceptions-*",
        filters={"traceId": trace_id},
        hours=hours,
        limit=limit,
    )
    return [hit.get("_source", {}) for hit in result.get("hits", {}).get("hits", [])]


def group_by_fingerprint(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for doc in docs:
        key = "|".join(
            [
                str(doc.get("errorCode", "")),
                str(doc.get("failurePoint", "")),
                str(doc.get("stackHash", "")),
                str(doc.get("businessObject", "")),
                str(doc.get("functionModule", "")),
            ]
        )
        group = groups.setdefault(
            key,
            {
                "fingerprint": hashlib.sha256(key.encode()).hexdigest()[:16],
                "errorCode": doc.get("errorCode", ""),
                "failurePoint": doc.get("failurePoint", ""),
                "stackHash": doc.get("stackHash", ""),
                "businessObject": doc.get("businessObject", ""),
                "functionModule": doc.get("functionModule", ""),
                "nature": doc.get("nature", ""),
                "occurrenceCount": 0,
                "firstSeenAt": doc.get("occurredAt", ""),
                "lastSeenAt": doc.get("occurredAt", ""),
                "sampleTraceIds": [],
                "sampleRequestIds": [],
                "reproStatus": "requires_human_review",
            },
        )
        group["occurrenceCount"] += 1
        occurred_at = str(doc.get("occurredAt", ""))
        if occurred_at and (not group["firstSeenAt"] or occurred_at < group["firstSeenAt"]):
            group["firstSeenAt"] = occurred_at
        if occurred_at and occurred_at > group["lastSeenAt"]:
            group["lastSeenAt"] = occurred_at
        append_unique(group["sampleTraceIds"], doc.get("traceId", ""))
        append_unique(group["sampleRequestIds"], doc.get("requestId", ""))
    return sorted(groups.values(), key=lambda item: item["occurrenceCount"], reverse=True)


def append_unique(values: list[str], value: Any, limit: int = 5) -> None:
    text = str(value or "").strip()
    if not text or text in values or len(values) >= limit:
        return
    values.append(text)


def search(index: str, filters: dict[str, str], hours: int, limit: int) -> dict[str, Any]:
    must: list[dict[str, Any]] = [
        {"range": {"occurredAt": {"gte": f"now-{max(hours, 1)}h"}}},
    ]
    for key, value in filters.items():
        if value:
            must.append({"term": {key: value}})
    body = {
        "size": max(limit, 1),
        "sort": [{"occurredAt": {"order": "desc"}}],
        "query": {"bool": {"must": must}},
    }
    return request_json("POST", f"/{index}/_search", body)


def emit_query_result(docs: list[dict[str, Any]], output: str) -> None:
    if output == "json":
        print(json.dumps({"items": docs}, ensure_ascii=False, indent=2))
        return
    print("# 最近异常")
    if not docs:
        print("\n无匹配异常。")
        return
    for doc in docs:
        print(
            f"- `{doc.get('occurredAt', '')}` `{doc.get('errorCode', '')}` "
            f"`{doc.get('requestId', '')}` `{doc.get('pageId') or doc.get('pageName', '')}`"
        )


def emit_report(groups: list[dict[str, Any]], output: str) -> None:
    if output == "json":
        print(json.dumps({"groups": groups}, ensure_ascii=False, indent=2))
        return
    print("# 异常日报")
    if not groups:
        print("\n最近窗口无异常。")
        return
    for group in groups:
        print(
            f"- `{group['fingerprint']}` `{group['errorCode']}` "
            f"count={group['occurrenceCount']} nature=`{group['nature']}` "
            f"module=`{group['businessObject']}/{group['functionModule']}` "
            f"repro=`{group['reproStatus']}`"
        )


def index_template(pattern: str) -> dict[str, Any]:
    return {
        "index_patterns": [pattern],
        "template": {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "dynamic": True,
                "properties": {
                    "eventId": {"type": "keyword"},
                    "eventType": {"type": "keyword"},
                    "eventName": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "appRuntimeEnv": {"type": "keyword"},
                    "appVersion": {"type": "keyword"},
                    "imageVersion": {"type": "keyword"},
                    "platform": {"type": "keyword"},
                    "networkClass": {"type": "keyword"},
                    "traceId": {"type": "keyword"},
                    "requestId": {"type": "keyword"},
                    "sessionId": {"type": "keyword"},
                    "pageVisitId": {"type": "keyword"},
                    "pageId": {"type": "keyword"},
                    "pageName": {"type": "keyword"},
                    "surfaceId": {"type": "keyword"},
                    "routeId": {"type": "keyword"},
                    "operationId": {"type": "keyword"},
                    "errorCode": {"type": "keyword"},
                    "errorModule": {"type": "keyword"},
                    "errorKind": {"type": "keyword"},
                    "errorReason": {"type": "keyword"},
                    "origin": {"type": "keyword"},
                    "nature": {"type": "keyword"},
                    "failurePoint": {"type": "keyword"},
                    "stackHash": {"type": "keyword"},
                    "businessObject": {"type": "keyword"},
                    "functionModule": {"type": "keyword"},
                    "entityType": {"type": "keyword"},
                    "entityId": {"type": "keyword"},
                    "targetType": {"type": "keyword"},
                    "targetKey": {"type": "keyword"},
                    "occurredAt": {"type": "date"},
                    "ingestedAt": {"type": "date"},
                    "payload": {"type": "object", "enabled": True},
                    "metrics": {"type": "object", "enabled": True},
                },
            },
        },
    }


def exception_doc(
    *,
    event_id: str,
    source: str,
    app_runtime_env: str,
    error_code: str,
    request_id: str,
    trace_id: str,
    page_id: str,
    occurred_at: dt.datetime,
) -> dict[str, Any]:
    parts = error_code.split(".", 2)
    stack_hash = hashlib.sha256(f"{error_code}:{source}".encode()).hexdigest()[:16]
    return {
        "eventId": event_id,
        "eventType": "exception",
        "eventName": "runtime_exception",
        "source": source,
        "appRuntimeEnv": app_runtime_env,
        "appVersion": "local-smoke",
        "platform": "local",
        "networkClass": "other",
        "traceId": trace_id,
        "requestId": request_id,
        "sessionId": "sess_es_smoke",
        "pageVisitId": "visit_es_smoke",
        "pageId": page_id,
        "pageName": page_id,
        "surfaceId": page_id,
        "routeId": page_id,
        "operationId": "ops.report_event_batch",
        "errorCode": error_code,
        "errorModule": parts[0] if len(parts) > 0 else "",
        "errorKind": parts[1] if len(parts) > 1 else "",
        "errorReason": parts[2] if len(parts) > 2 else "",
        "origin": "app" if source.startswith("app") else "cloud",
        "nature": "bug",
        "failurePoint": source,
        "stackHash": stack_hash,
        "businessObject": "event_record",
        "functionModule": "observability",
        "occurredAt": occurred_at.isoformat(),
        "ingestedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "payload": {"smoke": True},
    }


def request_json(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        urllib.parse.urljoin(f"{ES_URL}/", path.lstrip("/")),
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="ignore")
        raise SystemExit(f"Elasticsearch request failed: {method} {path}: {exc.code} {detail}") from exc
    return json.loads(raw) if raw else {}


if __name__ == "__main__":
    sys.exit(main())
