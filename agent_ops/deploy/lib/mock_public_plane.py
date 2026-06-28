#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[3]


class MockPublicPlaneHandler(BaseHTTPRequestHandler):
    mode: str = "api"
    runtime_env: str = "alpha"
    data_source: str = "mock"
    gateway_base_url: str = ""
    product_ops_base_url: str = ""
    media_base_url: str = ""
    legal_static_root: str = ""
    ops_policy_version: str = "mock-alpha"
    ops_lock = threading.Lock()
    ops_event_ids: set[str] = set()
    ops_events: list[dict[str, object]] = []
    ops_visits: list[dict[str, object]] = []
    ops_experiment_assignments: dict[str, dict[str, dict[str, object]]] = {}

    def do_GET(self) -> None:
        path, query = self._split_path()
        query_params = parse_qs(query, keep_blank_values=True)
        if path == "/healthz":
            self._send_json(
                {
                    "status": "ok",
                    "mode": self.mode,
                    "runtimeEnv": self.runtime_env,
                }
            )
            return
        if self.mode == "api" and path == "/v1/config/app":
            self._send_json(
                {
                    "appRuntimeEnv": self.runtime_env,
                    "dataSource": self.data_source,
                    "gatewayBaseUrl": self.gateway_base_url,
                    "legalBaseUrl": self._legal_base_url(),
                    "productOpsBaseUrl": self.product_ops_base_url,
                    "mediaBaseUrl": self.media_base_url,
                }
            )
            return
        if self.mode == "api" and path.startswith("/media/"):
            self._redirect_to_media(path, query)
            return
        if self.mode == "api" and path.startswith("/legal/"):
            self._handle_legal_static(path, include_body=True)
            return
        if self.mode == "api" and path.startswith("/v1/content/feed"):
            self._send_json({"items": [], "nextCursor": None, "mockBoundary": True})
            return
        if self.mode == "api" and path.startswith("/v1/chat/contacts"):
            self._send_json({"items": [], "nextCursor": None, "mockBoundary": True})
            return
        if self.mode == "api" and path.startswith("/v1/chat/inbox"):
            self._send_json({"items": [], "nextCursor": None, "mockBoundary": True})
            return
        if self.mode == "api" and path.startswith("/v1/chat/conversations"):
            self._send_json({"items": [], "nextCursor": None, "mockBoundary": True})
            return
        if self._supports_ops() and path.startswith("/v1/ops/"):
            if self._handle_ops_get(path, query_params):
                return
        self.send_error(404, f"{self.mode} mock route is not ready")

    def do_HEAD(self) -> None:
        path, _query = self._split_path()
        if self.mode == "api" and path.startswith("/legal/"):
            self._handle_legal_static(path, include_body=False)
            return
        self.send_error(404, f"{self.mode} mock route is not ready")

    def do_POST(self) -> None:
        path, _query = self._split_path()
        if self.mode == "api" and path == "/v1/user/sync":
            self._send_json(
                {
                    "patches": [],
                    "latestSyncSeq": 0,
                    "hasMore": False,
                    "requiresResync": False,
                    "mockBoundary": True,
                }
            )
            return
        if self._supports_ops() and path.startswith("/v1/ops/"):
            if self._handle_ops_post(path):
                return
        self.send_error(404, f"{self.mode} mock route is not ready")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _split_path(self) -> tuple[str, str]:
        parts = urlsplit(self.path)
        return parts.path or "/", parts.query

    def _supports_ops(self) -> bool:
        return self.mode in {"api", "product-ops"}

    def _redirect_to_media(self, path: str, query: str) -> None:
        base = self.media_base_url.rstrip("/")
        if not base:
            self.send_error(404, "media base is not configured")
            return
        target = base + path
        if query:
            target = f"{target}?{query}"
        self.send_response(307)
        self.send_header("Location", target)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _legal_base_url(self) -> str:
        gateway_base = self.gateway_base_url.rstrip("/")
        if not gateway_base:
            return ""
        return f"{gateway_base}/legal"

    def _legal_root(self) -> Path:
        configured = type(self).legal_static_root.strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return (
            ROOT
            / "artifacts"
            / "legal-static-packages"
            / self.runtime_env
            / "current"
            / "public"
        ).resolve()

    def _resolve_legal_static_path(self, path: str) -> Path | None:
        root = self._legal_root()
        if not root.is_dir():
            return None
        normalized = path.strip("/")
        if normalized == "legal":
            normalized = "legal/manifest.json"
        candidate = (root / normalized).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        if candidate.is_file():
            return candidate
        if candidate.suffix:
            return None
        html_candidate = candidate.with_suffix(".html")
        try:
            html_candidate.relative_to(root)
        except ValueError:
            return None
        if html_candidate.is_file():
            return html_candidate
        return None

    def _handle_legal_static(self, path: str, *, include_body: bool) -> None:
        target = self._resolve_legal_static_path(path)
        if target is None:
            root = self._legal_root()
            if root.is_dir():
                self.send_error(404, "legal-static document is not ready")
            else:
                self.send_error(503, "legal-static package is not ready")
            return
        body = target.read_bytes() if include_body else b""
        file_size = target.stat().st_size
        content_type = self._legal_content_type(target)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _legal_content_type(self, path: Path) -> str:
        if path.suffix == ".json":
            return "application/json; charset=utf-8"
        return "text/html; charset=utf-8"

    def _handle_ops_get(
        self,
        path: str,
        query_params: dict[str, list[str]],
    ) -> bool:
        if path == "/v1/ops/events/summary":
            self._send_json(self._build_ops_event_summary(query_params))
            return True
        if path == "/v1/ops/events/drilldown":
            self._send_json(self._build_ops_event_drilldown(query_params))
            return True
        if path == "/v1/ops/visits/stats":
            self._send_json(self._build_ops_visit_stats(query_params))
            return True

        experiment_id = self._match_experiment_path(path, "/bucket")
        if experiment_id is not None:
            self._send_json(
                self._resolve_experiment_assignment(
                    experiment_id,
                    self._query_value(query_params, "subjectKey") or "anonymous",
                )
            )
            return True

        experiment_id = self._match_experiment_path(path, "/stats")
        if experiment_id is not None:
            self._send_json(self._build_experiment_stats(experiment_id))
            return True
        return False

    def _handle_ops_post(self, path: str) -> bool:
        payload = self._read_json_body()
        if path == "/v1/ops/events":
            self._send_json(self._record_ops_events(payload))
            return True
        if path == "/v1/ops/visits":
            self._send_json(self._record_ops_visit(payload))
            return True

        experiment_id = self._match_experiment_path(path, "/assign")
        if experiment_id is not None:
            subject_key = "anonymous"
            if isinstance(payload, dict):
                subject_key = str(payload.get("subjectKey") or "").strip() or "anonymous"
            self._send_json(self._resolve_experiment_assignment(experiment_id, subject_key))
            return True
        return False

    def _read_json_body(self) -> object:
        raw_length = self.headers.get("Content-Length", "0").strip() or "0"
        try:
            content_length = int(raw_length)
        except ValueError:
            content_length = 0
        if content_length <= 0:
            return {}
        raw_body = self.rfile.read(content_length)
        if not raw_body:
            return {}
        try:
            return json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def _record_ops_events(self, payload: object) -> dict[str, object]:
        raw_events = []
        if isinstance(payload, dict):
            candidate = payload.get("events")
            if isinstance(candidate, list):
                raw_events = candidate
        elif isinstance(payload, list):
            raw_events = payload

        accepted_count = 0
        duplicate_count = 0
        handler_cls = type(self)
        with handler_cls.ops_lock:
            for raw_event in raw_events:
                if not isinstance(raw_event, dict):
                    continue
                event_id = str(raw_event.get("eventId") or "").strip()
                if not event_id:
                    event_id = f"mock-event-{len(handler_cls.ops_events) + accepted_count + 1}"
                if event_id in handler_cls.ops_event_ids:
                    duplicate_count += 1
                    continue
                normalized = {
                    "eventId": event_id,
                    "eventType": str(raw_event.get("eventType") or "").strip(),
                    "eventName": str(raw_event.get("eventName") or "").strip(),
                    "occurredAt": str(raw_event.get("occurredAt") or "").strip(),
                    "pageName": str(raw_event.get("pageName") or "").strip(),
                    "surfaceId": str(raw_event.get("surfaceId") or "").strip(),
                    "routeId": str(raw_event.get("routeId") or "").strip(),
                    "targetType": str(raw_event.get("targetType") or "").strip(),
                    "targetKey": str(raw_event.get("targetKey") or "").strip(),
                    "entityType": str(raw_event.get("entityType") or "").strip(),
                    "entityId": str(raw_event.get("entityId") or "").strip(),
                    "experimentBucket": str(raw_event.get("experimentBucket") or "").strip(),
                    "source": str(raw_event.get("source") or "").strip(),
                    "payload": raw_event.get("payload")
                    if isinstance(raw_event.get("payload"), dict)
                    else {},
                    "metrics": raw_event.get("metrics")
                    if isinstance(raw_event.get("metrics"), dict)
                    else {},
                }
                handler_cls.ops_event_ids.add(event_id)
                handler_cls.ops_events.append(normalized)
                accepted_count += 1
        return {
            "acceptedCount": accepted_count,
            "duplicateCount": duplicate_count,
            "mockBoundary": True,
        }

    def _build_ops_event_summary(
        self,
        query_params: dict[str, list[str]],
    ) -> dict[str, object]:
        matched = self._filter_ops_events(query_params)
        dimensions: dict[str, dict[str, int]] = {}
        for event in matched:
            self._add_dimension(dimensions, "pageName", event.get("pageName"))
            self._add_dimension(dimensions, "surfaceId", event.get("surfaceId"))
            self._add_dimension(dimensions, "routeId", event.get("routeId"))
            self._add_dimension(
                dimensions,
                "experimentBucket",
                event.get("experimentBucket"),
            )
            self._add_dimension(dimensions, "targetKey", event.get("targetKey"))
            self._add_dimension(dimensions, "entityId", event.get("entityId"))
            self._add_dimension(dimensions, "source", event.get("source"))
            self._add_dimension(dimensions, "eventName", event.get("eventName"))
        return {
            "totalCount": len(matched),
            "dimensions": dimensions,
            "eventType": self._query_value(query_params, "eventType"),
            "eventName": self._query_value(query_params, "eventName"),
            "latestOccurredAt": str(matched[0].get("occurredAt") or "") if matched else "",
            "mockBoundary": True,
        }

    def _build_ops_event_drilldown(
        self,
        query_params: dict[str, list[str]],
    ) -> dict[str, object]:
        matched = self._filter_ops_events(query_params)
        limit = self._query_int(query_params, "limit", default=20)
        items = matched[:limit]
        return {
            "totalCount": len(matched),
            "items": items,
            "mockBoundary": True,
        }

    def _filter_ops_events(
        self,
        query_params: dict[str, list[str]],
    ) -> list[dict[str, object]]:
        filters = {
            "eventType": self._query_value(query_params, "eventType"),
            "eventName": self._query_value(query_params, "eventName"),
            "pageName": self._query_value(query_params, "pageName"),
            "surfaceId": self._query_value(query_params, "surfaceId"),
            "routeId": self._query_value(query_params, "routeId"),
            "targetType": self._query_value(query_params, "targetType"),
            "targetKey": self._query_value(query_params, "targetKey"),
            "entityType": self._query_value(query_params, "entityType"),
            "entityId": self._query_value(query_params, "entityId"),
            "experimentBucket": self._query_value(query_params, "experimentBucket"),
            "source": self._query_value(query_params, "source"),
        }
        handler_cls = type(self)
        with handler_cls.ops_lock:
            events = list(handler_cls.ops_events)
        matched = []
        for event in events:
            if any(filters[key] and str(event.get(key) or "") != filters[key] for key in filters):
                continue
            matched.append(event)
        matched.sort(
            key=lambda event: str(event.get("occurredAt") or ""),
            reverse=True,
        )
        return matched

    def _record_ops_visit(self, payload: object) -> dict[str, object]:
        record = payload if isinstance(payload, dict) else {}
        normalized = {
            "targetType": str(record.get("targetType") or "").strip(),
            "targetKey": str(record.get("targetKey") or "").strip(),
            "userId": str(record.get("userId") or "").strip(),
            "sessionId": str(record.get("sessionId") or "").strip(),
            "source": str(record.get("source") or "").strip(),
        }
        handler_cls = type(self)
        with handler_cls.ops_lock:
            handler_cls.ops_visits.append(normalized)
            visit_count = sum(
                1
                for item in handler_cls.ops_visits
                if item["targetType"] == normalized["targetType"]
                and item["targetKey"] == normalized["targetKey"]
                and item["userId"] == normalized["userId"]
            )
        return {
            **normalized,
            "visitCount": visit_count,
            "mockBoundary": True,
        }

    def _build_ops_visit_stats(
        self,
        query_params: dict[str, list[str]],
    ) -> dict[str, object]:
        target_type = self._query_value(query_params, "targetType")
        target_key = self._query_value(query_params, "targetKey")
        counts: dict[str, int] = {}
        handler_cls = type(self)
        with handler_cls.ops_lock:
            visits = list(handler_cls.ops_visits)
        for visit in visits:
            if target_type and visit["targetType"] != target_type:
                continue
            if target_key and visit["targetKey"] != target_key:
                continue
            user_id = visit["userId"] or "anonymous"
            counts[user_id] = counts.get(user_id, 0) + 1
        items = [
            {
                "targetType": target_type,
                "targetKey": target_key,
                "userId": user_id,
                "visitCount": visit_count,
            }
            for user_id, visit_count in sorted(counts.items())
        ]
        return {
            "totalVisits": sum(counts.values()),
            "items": items,
            "mockBoundary": True,
        }

    def _resolve_experiment_assignment(
        self,
        experiment_id: str,
        subject_key: str,
    ) -> dict[str, object]:
        normalized_experiment = experiment_id.strip()
        normalized_subject = subject_key.strip() or "anonymous"
        handler_cls = type(self)
        with handler_cls.ops_lock:
            assignments = handler_cls.ops_experiment_assignments.setdefault(
                normalized_experiment,
                {},
            )
            existing = assignments.get(normalized_subject)
            if existing is not None:
                return dict(existing)
            digest = hashlib.sha256(
                f"{normalized_experiment}:{normalized_subject}".encode("utf-8")
            ).hexdigest()
            bucket = "control" if int(digest[:2], 16) % 2 == 0 else "treatment"
            assignment = {
                "experimentId": normalized_experiment,
                "subjectKey": normalized_subject,
                "bucket": bucket,
                "policyVersion": handler_cls.ops_policy_version,
                "assignmentTrace": "mock-hash",
                "mockBoundary": True,
            }
            assignments[normalized_subject] = assignment
            return dict(assignment)

    def _build_experiment_stats(self, experiment_id: str) -> dict[str, object]:
        handler_cls = type(self)
        with handler_cls.ops_lock:
            assignments = dict(
                handler_cls.ops_experiment_assignments.get(experiment_id.strip(), {})
            )
        bucket_stats: dict[str, int] = {}
        for assignment in assignments.values():
            bucket = str(assignment.get("bucket") or "").strip()
            if not bucket:
                continue
            bucket_stats[bucket] = bucket_stats.get(bucket, 0) + 1
        return {
            "experimentId": experiment_id.strip(),
            "policyVersion": handler_cls.ops_policy_version,
            "enabled": True,
            "bucketStats": bucket_stats,
            "assignedSubjects": len(assignments),
            "mockBoundary": True,
        }

    def _match_experiment_path(self, path: str, suffix: str) -> str | None:
        prefix = "/v1/ops/experiments/"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return None
        experiment_id = path[len(prefix) : -len(suffix)].strip("/")
        if not experiment_id or "/" in experiment_id:
            return None
        return experiment_id

    def _query_value(
        self,
        query_params: dict[str, list[str]],
        key: str,
    ) -> str:
        values = query_params.get(key) or []
        if not values:
            return ""
        return str(values[0] or "").strip()

    def _query_int(
        self,
        query_params: dict[str, list[str]],
        key: str,
        *,
        default: int,
    ) -> int:
        raw_value = self._query_value(query_params, key)
        if not raw_value:
            return default
        try:
            return max(0, int(raw_value))
        except ValueError:
            return default

    def _add_dimension(
        self,
        dimensions: dict[str, dict[str, int]],
        dimension_key: str,
        raw_value: object,
    ) -> None:
        value = str(raw_value or "").strip()
        if not value:
            return
        bucket = dimensions.setdefault(dimension_key, {})
        bucket[value] = bucket.get(value, 0) + 1

    def _send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--mode", choices=["api", "product-ops"], default="api")
    parser.add_argument("--runtime-env", default="alpha")
    parser.add_argument("--data-source", default="mock")
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--product-ops-base-url", default="")
    parser.add_argument("--media-base-url", default="")
    parser.add_argument("--legal-static-root", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    MockPublicPlaneHandler.mode = args.mode
    MockPublicPlaneHandler.runtime_env = args.runtime_env
    MockPublicPlaneHandler.data_source = args.data_source
    MockPublicPlaneHandler.gateway_base_url = args.gateway_base_url.rstrip("/")
    MockPublicPlaneHandler.product_ops_base_url = args.product_ops_base_url.rstrip("/")
    MockPublicPlaneHandler.media_base_url = args.media_base_url.rstrip("/")
    MockPublicPlaneHandler.legal_static_root = args.legal_static_root.rstrip("/")
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), MockPublicPlaneHandler)
    print(
        "[mock-public-plane] listening http://{host}:{port} mode={mode}".format(
            host=args.listen_host,
            port=args.listen_port,
            mode=args.mode,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
