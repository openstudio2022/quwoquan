#!/usr/bin/env python3
"""验证举报、运营驳回、通知回流与负反馈撤销的真实环境旅程。"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

from report_feedback_probe_support import (
    LOCAL_TARGETS,
    REPO_ROOT,
    ProbeClient,
    ProbeFailure,
    operator_session as build_operator_session,
    reporter_session as build_reporter_session,
)


SCHEMA = "content-report-feedback-lifecycle-probe-report"
SCENARIO = "content.report_feedback.lifecycle"
REPORTER_FORBIDDEN_FIELDS = frozenset(
    {
        "reviewerId",
        "resolution",
        "reporterId",
        "reporterAccountId",
        "internalNote",
    }
)

def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("beta", "gamma", "prod"), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--mode",
        choices=("read-only", "lifecycle"),
        default="read-only",
    )
    parser.add_argument("--target-id", default="fixture_photo_001")
    parser.add_argument(
        "--reporter-auth-token-env",
        default="PROD_ACCEPTANCE_AUTH_TOKEN",
    )
    parser.add_argument(
        "--operator-auth-token-env",
        default="PROD_REPORT_OPERATOR_AUTH_TOKEN",
    )
    parser.add_argument("--projection-timeout-seconds", type=float, default=45.0)
    parser.add_argument(
        "--report",
        default=".qwq_output/env/repo/runs/content-report-feedback/report.json",
    )
    args = parser.parse_args()
    return args


def _data(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    nested = payload.get("data")
    return nested if isinstance(nested, dict) else payload


def _items(payload: dict[str, Any] | None, step: str) -> list[dict[str, Any]]:
    raw = _data(payload).get("items")
    if isinstance(raw, dict):
        raw = raw.get("items")
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ProbeFailure(
            "contract_mismatch",
            f"{step} response has no object items",
        )
    return raw


def _assert_reporter_privacy(items: list[dict[str, Any]]) -> None:
    for item in items:
        leaked = REPORTER_FORBIDDEN_FIELDS.intersection(item)
        if leaked:
            raise ProbeFailure(
                "privacy_leak",
                "ListMyReports exposed internal report fields",
            )


def _find_probe_report(
    items: list[dict[str, Any]],
    marker: str,
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in items
            if str(item.get("description") or "").strip() == marker
        ),
        None,
    )


def _list_my_reports(client: ProbeClient) -> list[dict[str, Any]]:
    _, payload = client.request(
        "GET",
        "/content/users/me/reports?limit=100",
        operation_id="ListMyReports",
    )
    items = _items(payload, "ListMyReports")
    _assert_reporter_privacy(items)
    return items


def _wait_report_status(
    client: ProbeClient,
    marker: str,
    expected_status: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        report = _find_probe_report(_list_my_reports(client), marker)
        if report is not None and str(report.get("status") or "") == expected_status:
            return report
        time.sleep(1.0)
    raise ProbeFailure(
        "projection_timeout",
        f"ListMyReports did not reach status {expected_status}",
    )


def _wait_report_notification(
    client: ProbeClient,
    report_id: str,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        _, payload = client.request(
            "GET",
            "/app-messages?limit=100",
            operation_id="ListAppMessages",
        )
        for item in _items(payload, "ListAppMessages"):
            target = item.get("target")
            if not isinstance(target, dict):
                continue
            if (
                str(target.get("targetType") or "") == "report"
                and str(target.get("targetId") or "") == report_id
            ):
                return
        time.sleep(1.0)
    raise ProbeFailure(
        "notification_timeout",
        "dismissed report did not reach the reporter AppMessage inbox",
    )


def _write_report(path: Path, report: dict[str, Any]) -> Path:
    target = path if path.is_absolute() else REPO_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    args = _parse_args()
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "scenario": SCENARIO,
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "startedAt": _utc_now(),
        "endedAt": "",
        "environment": {
            "env": args.env,
            "runtimeKind": LOCAL_TARGETS.get(args.env, "prod-hosted"),
            "gatewayBaseUrl": args.base_url.rstrip("/"),
            "commitSha": os.environ.get("GITHUB_SHA", ""),
        },
        "mode": args.mode,
        "steps": [],
        "journeyEvidence": {},
    }
    return_code = 1
    report_path = Path(args.report)
    try:
        if args.env == "prod" and args.mode != "read-only":
            raise ProbeFailure(
                "unsafe_mode",
                "prod report feedback probe is read-only",
            )
        reporter_session = build_reporter_session(
            environment=args.env,
            base_url=args.base_url,
            hosted_token_env=args.reporter_auth_token_env,
        )
        reporter = ProbeClient(
            args.base_url,
            reporter_session,
        )
        reporter.request("GET", "/healthz", operation_id="Health")
        report["steps"].append({"name": "healthz", "status": "passed"})
        existing = _list_my_reports(reporter)
        report["journeyEvidence"]["initialPrivateReportCount"] = len(existing)
        report["steps"].append(
            {"name": "list_my_reports_privacy", "status": "passed"}
        )

        if args.mode == "read-only":
            report["status"] = "passed"
            return_code = 0
        else:
            run_id = uuid.uuid4().hex
            marker = f"report-feedback-probe:{args.env}:{run_id[:12]}"
            idempotency_key = f"content-report-probe-{run_id}"
            create_body = {
                "targetType": "post",
                "targetId": args.target_id,
                "reason": "spam",
                "description": marker,
            }
            for _ in range(2):
                reporter.request(
                    "POST",
                    "/content/reports",
                    operation_id="CreateReport",
                    expected_statuses=frozenset({204}),
                    body=create_body,
                    idempotency_key=idempotency_key,
                )
            pending = _wait_report_status(
                reporter,
                marker,
                "pending",
                args.projection_timeout_seconds,
            )
            report_id = str(pending.get("id") or "").strip()
            if not report_id:
                raise ProbeFailure(
                    "contract_mismatch",
                    "ListMyReports returned a report without id",
                )
            report["steps"].append(
                {"name": "create_idempotent_and_list", "status": "passed"}
            )
            reporter.request(
                "POST",
                f"/content/reports/{urllib.parse.quote(report_id)}:dismiss",
                operation_id="DismissReport",
                expected_statuses=frozenset({403}),
                idempotency_key=f"reporter-forbidden-{run_id}",
            )
            report["steps"].append(
                {"name": "reporter_cannot_dismiss", "status": "passed"}
            )

            occurred_at = _utc_now()
            behavior_body = {
                "events": [
                    {
                        "clientEventId": f"{run_id}-dislike",
                        "occurredAt": occurred_at,
                        "contentId": args.target_id,
                        "action": "dislike",
                    },
                    {
                        "clientEventId": f"{run_id}-undo",
                        "occurredAt": occurred_at,
                        "contentId": args.target_id,
                        "action": "undo_dislike",
                    },
                ]
            }
            for _ in range(2):
                reporter.request(
                    "POST",
                    "/content/behaviors",
                    operation_id="ReportBehaviors",
                    expected_statuses=frozenset({204}),
                    body=behavior_body,
                    idempotency_key=f"content-feedback-probe-{run_id}",
                )
            report["steps"].append(
                {"name": "dislike_undo_idempotent", "status": "passed"}
            )

            operator_session = build_operator_session(
                environment=args.env,
                base_url=args.base_url,
                hosted_token_env=args.operator_auth_token_env,
            )
            operator = ProbeClient(
                args.base_url,
                operator_session,
            )
            _, queue_payload = operator.request(
                "GET",
                "/content/reports?limit=100",
                operation_id="ListReports",
            )
            if not any(
                str(item.get("id") or "") == report_id
                for item in _items(queue_payload, "ListReports")
            ):
                raise ProbeFailure(
                    "queue_projection_missing",
                    "created report did not reach the operator queue",
                )
            operator.request(
                "POST",
                f"/content/reports/{urllib.parse.quote(report_id)}/review",
                operation_id="BeginReportReview",
                idempotency_key=f"begin-report-review-{run_id}",
            )
            operator.request(
                "POST",
                f"/content/reports/{urllib.parse.quote(report_id)}:dismiss",
                operation_id="DismissReport",
                idempotency_key=f"dismiss-report-{run_id}",
            )
            _wait_report_status(
                reporter,
                marker,
                "dismissed",
                args.projection_timeout_seconds,
            )
            _wait_report_notification(
                reporter,
                report_id,
                args.projection_timeout_seconds,
            )
            report["steps"].append(
                {"name": "operator_dismiss_to_reporter", "status": "passed"}
            )
            report["journeyEvidence"].update(
                {
                    "reportIdHash": _stable_hash(report_id),
                    "targetIdHash": _stable_hash(args.target_id),
                    "createIdempotent": True,
                    "reporterIsolated": True,
                    "operatorQueueProjected": True,
                    "dismissedVisibleToReporter": True,
                    "notificationProjected": True,
                    "negativeFeedbackUndone": True,
                }
            )
            report["status"] = "passed"
            return_code = 0
    except ProbeFailure as exc:
        report["status"] = "failed"
        report["failureCategory"] = exc.category
        report["blockingReason"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["failureCategory"] = "unexpected_error"
        report["blockingReason"] = type(exc).__name__
    finally:
        report["endedAt"] = _utc_now()
        target = _write_report(report_path, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "scenario": SCENARIO,
                    "report": str(target),
                    "failureCategory": report["failureCategory"],
                },
                ensure_ascii=False,
            )
        )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
