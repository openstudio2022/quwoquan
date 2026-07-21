#!/usr/bin/env python3
"""验证群聊候选源、建群、消息回读与 Inbox 投影，并输出可审计证据。"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")


REPO_ROOT = _find_repo_root()
sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.local_environment_auth import (  # noqa: E402
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
    open_local_acceptance_session,
    request_local_environment_json,
)


SCHEMA = "chat-group-lifecycle-probe-report"
SCENARIO = "chat.group_create.source_to_inbox"
LOCAL_TARGETS = {"beta": "beta-local", "gamma": "gamma-local"}


class ProbeFailure(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("beta", "gamma", "prod"), required=True)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("CHAT_GROUP_GATEWAY_BASE_URL")
        or os.environ.get("GAMMA_BASE_URL")
        or os.environ.get("PROD_GATEWAY_BASE_URL")
        or "http://127.0.0.1:18080",
    )
    parser.add_argument("--resolve-host", default="127.0.0.1")
    parser.add_argument("--auth-token-env", default="PROD_TEST_AUTH_TOKEN")
    parser.add_argument("--mutating", action="store_true")
    parser.add_argument("--require-nonempty-sources", action="store_true")
    parser.add_argument("--expected-group-id", default="")
    parser.add_argument("--expected-circle-group-id", default="")
    parser.add_argument("--expected-circle-id", default="")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument(
        "--report",
        default=".qwq_output/env/gamma/runs/chat-group-lifecycle/report.json",
    )
    return parser.parse_args()


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else ""


def _operation_headers(operation_id: str, idempotency_key: str = "") -> dict[str, str]:
    headers = {"X-Client-Operation-Id": operation_id}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


class ProbeClient:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.session: LocalAcceptanceSession | None = None
        self.token = ""
        if args.env in LOCAL_TARGETS:
            self.session = open_local_acceptance_session(
                args.base_url,
                environment=args.env,
                target_name=LOCAL_TARGETS[args.env],
                resolve_host=args.resolve_host,
            )
        else:
            self.token = os.environ.get(args.auth_token_env, "").strip()
            if not self.token:
                raise ProbeFailure(
                    "auth_missing",
                    f"prod probe requires bearer token in environment variable {args.auth_token_env}",
                )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        operation_id: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        headers = _operation_headers(operation_id, idempotency_key)
        if self.session is not None:
            try:
                return request_local_environment_json(
                    self.args.base_url,
                    path=path,
                    session=self.session,
                    resolve_host=self.args.resolve_host,
                    method=method,
                    body=body,
                    headers=headers,
                    timeout_seconds=12.0,
                )
            except LocalEnvironmentHTTPError as exc:
                category = "auth_failed" if exc.status in {401, 403} else "http_error"
                raise ProbeFailure(
                    category,
                    f"{method} {path} returned HTTP {exc.status}",
                ) from exc
        return self._request_hosted(method, path, body=body, headers=headers)

    def _request_hosted(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request_headers = {
            "Accept": "application/json",
            "Authorization": "Bearer " + self.token,
            **headers,
        }
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.args.base_url.rstrip("/") + path,
            data=payload,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=12,
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ProbeFailure("http_error", f"{method} {path} returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ProbeFailure("gateway_unreachable", f"{method} {path} is unreachable") from exc
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProbeFailure("invalid_response", f"{method} {path} returned non-JSON") from exc
        if not isinstance(parsed, dict):
            raise ProbeFailure("invalid_response", f"{method} {path} returned non-object JSON")
        return parsed


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("data")
    return nested if isinstance(nested, dict) else payload


def _items(payload: dict[str, Any], step: str) -> list[dict[str, Any]]:
    raw = _data(payload).get("items")
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ProbeFailure("contract_mismatch", f"{step} response has no object items")
    return raw


def _require_source_rows(
    rows: list[dict[str, Any]],
    *,
    source: str,
    expected_conversation_id: str,
    expected_circle_id: str,
    require_nonempty: bool,
) -> None:
    if require_nonempty and not rows:
        raise ProbeFailure("source_empty", f"{source} source returned no selectable conversation")
    for row in rows:
        circle_id = str(row.get("circleId") or "").strip()
        if source == "group" and circle_id:
            raise ProbeFailure("source_leak", "group source returned a circle-bound conversation")
        if source == "circle" and not circle_id:
            raise ProbeFailure("source_leak", "circle source returned a private conversation")
        if int(row.get("friendMemberCount") or 0) <= 0:
            raise ProbeFailure("contract_mismatch", f"{source} source returned non-selectable row")
    if expected_conversation_id and not any(
        str(row.get("conversationId") or "") == expected_conversation_id for row in rows
    ):
        raise ProbeFailure("fixture_missing", f"{source} source missed expected conversation")
    if expected_circle_id and not any(
        str(row.get("circleId") or "") == expected_circle_id for row in rows
    ):
        raise ProbeFailure("fixture_missing", "circle source missed expected circle")


def _conversation_id(payload: dict[str, Any]) -> str:
    body = _data(payload)
    value = str(body.get("id") or body.get("conversationId") or "").strip()
    if not value:
        raise ProbeFailure("contract_mismatch", "CreateConversation returned no canonical id")
    return value


def _message_id(payload: dict[str, Any]) -> str:
    body = _data(payload)
    value = str(body.get("messageId") or body.get("id") or "").strip()
    if not value:
        raise ProbeFailure("contract_mismatch", "SendMessage returned no canonical id")
    return value


def _mentioned_message_visible(
    items: list[dict[str, Any]],
    *,
    message_id: str,
    mentioned_user_id: str,
) -> bool:
    for item in items:
        item_id = str(item.get("messageId") or item.get("id") or "").strip()
        if item_id != message_id:
            continue
        mentions = item.get("mentions")
        if not isinstance(mentions, list):
            raise ProbeFailure(
                "contract_mismatch",
                "mentioned message has no mentions array",
            )
        if mentioned_user_id not in {str(value).strip() for value in mentions}:
            raise ProbeFailure(
                "mention_round_trip_failed",
                "mentioned member was not preserved by ListMessages",
            )
        return True
    return False


def _wait_for_mentioned_message(
    client: ProbeClient,
    conversation_id: str,
    *,
    message_id: str,
    mentioned_user_id: str,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        items = _items(
            client.request(
                "GET",
                "/chat/conversations/"
                + urllib.parse.quote(conversation_id)
                + "/messages?limit=100",
                operation_id="ListMessages",
            ),
            "mentioned message list",
        )
        if _mentioned_message_visible(
            items,
            message_id=message_id,
            mentioned_user_id=mentioned_user_id,
        ):
            return
        time.sleep(1.0)
    raise ProbeFailure(
        "mention_round_trip_timeout",
        "mentioned message did not reach ListMessages before timeout",
    )


def _wait_for_inbox(
    client: ProbeClient,
    conversation_id: str,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        rows = _items(
            client.request("GET", "/chat/inbox?limit=100", operation_id="ListInbox"),
            "ListInbox",
        )
        if any(str(item.get("conversationId") or "") == conversation_id for item in rows):
            return
        time.sleep(1.0)
    raise ProbeFailure("projection_timeout", "created conversation did not reach Inbox")


def _write_report(path: Path, report: dict[str, Any]) -> None:
    target = path if path.is_absolute() else REPO_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = _parse_args()
    if args.env == "prod" and args.mutating:
        raise SystemExit("prod probe is read-only; mutation is forbidden")
    if args.env in LOCAL_TARGETS:
        args.expected_group_id = args.expected_group_id or "fixture_conv_group"
        args.expected_circle_group_id = (
            args.expected_circle_group_id or "fixture_conv_photo_group"
        )
        args.expected_circle_id = args.expected_circle_id or "fixture_circle_photo"
        args.require_nonempty_sources = True

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
        "mode": "mutating" if args.mutating else "read-only",
        "sourceEvidence": {},
        "journeyEvidence": {},
        "steps": [],
    }
    report_path = Path(args.report)
    created_id = ""
    client: ProbeClient | None = None
    try:
        client = ProbeClient(args)
        health = client.request("GET", "/healthz", operation_id="Health")
        report["steps"].append({"name": "healthz", "status": "passed"})
        report["environment"]["healthStatus"] = str(_data(health).get("status") or "ok")

        group_rows = _items(
            client.request(
                "GET",
                "/chat/selectable-group-conversations?source=group&limit=100",
                operation_id="ListSelectableGroupConversations",
            ),
            "group source",
        )
        circle_rows = _items(
            client.request(
                "GET",
                "/chat/selectable-group-conversations?source=circle&limit=100",
                operation_id="ListSelectableGroupConversations",
            ),
            "circle source",
        )
        _require_source_rows(
            group_rows,
            source="group",
            expected_conversation_id=args.expected_group_id,
            expected_circle_id="",
            require_nonempty=args.require_nonempty_sources,
        )
        _require_source_rows(
            circle_rows,
            source="circle",
            expected_conversation_id=args.expected_circle_group_id,
            expected_circle_id=args.expected_circle_id,
            require_nonempty=args.require_nonempty_sources,
        )
        report["sourceEvidence"] = {
            "groupCount": len(group_rows),
            "circleCount": len(circle_rows),
            "groupSourceIsolated": True,
            "circleSourceIsolated": True,
        }
        report["steps"].append({"name": "source_split", "status": "passed"})

        source_row = next(iter(circle_rows or group_rows), None)
        members: list[dict[str, Any]] = []
        if source_row is not None:
            source_id = str(source_row.get("conversationId") or "")
            members = _items(
                client.request(
                    "GET",
                    "/chat/selectable-group-conversations/"
                    + urllib.parse.quote(source_id)
                    + "/contact-members?limit=100",
                    operation_id="ListSelectableGroupContactMembers",
                ),
                "contact members",
            )
            if not members or any(
                str(item.get("relationState") or "") != "mutual" for item in members
            ):
                raise ProbeFailure(
                    "relationship_filter_failed",
                    "source member intersection did not return mutual-only candidates",
                )
        report["sourceEvidence"]["mutualMemberCount"] = len(members)
        report["steps"].append({"name": "mutual_member_intersection", "status": "passed"})

        inbox_rows = _items(
            client.request("GET", "/chat/inbox?limit=100", operation_id="ListInbox"),
            "ListInbox",
        )
        report["sourceEvidence"]["inboxCount"] = len(inbox_rows)
        report["steps"].append({"name": "inbox_read", "status": "passed"})

        if args.mutating:
            if not members:
                raise ProbeFailure("candidate_missing", "mutating probe has no eligible member")
            member_id = str(members[0].get("userId") or "").strip()
            if not member_id:
                raise ProbeFailure("contract_mismatch", "candidate row has no userId")
            run_id = uuid.uuid4().hex
            created = client.request(
                "POST",
                "/chat/conversations",
                body={
                    "type": "group",
                    "title": "群聊商业闭环探针-" + run_id[:8],
                    "maxGroupSize": 1000,
                    "initialMemberIds": [member_id],
                },
                operation_id="CreateConversation",
                idempotency_key="chat-group-create-" + run_id,
            )
            created_id = _conversation_id(created)
            client.request(
                "GET",
                "/chat/conversations/" + urllib.parse.quote(created_id),
                operation_id="GetConversation",
            )
            _wait_for_inbox(client, created_id, args.timeout_seconds)
            message = client.request(
                "POST",
                "/chat/conversations/"
                + urllib.parse.quote(created_id)
                + "/messages",
                body={
                    "type": "text",
                    "content": "群聊商业闭环探针",
                    "clientMsgId": "chat-group-probe-" + run_id,
                },
                operation_id="SendMessage",
                idempotency_key="chat-group-send-" + run_id,
            )
            message_id = _message_id(message)
            mentioned_message = client.request(
                "POST",
                "/chat/conversations/"
                + urllib.parse.quote(created_id)
                + "/messages",
                body={
                    "type": "text",
                    "content": "群聊商业闭环提及探针",
                    "clientMsgId": "chat-group-mention-" + run_id,
                    "mentions": [member_id],
                },
                operation_id="SendMessage",
                idempotency_key="chat-group-mention-" + run_id,
            )
            mentioned_message_id = _message_id(mentioned_message)
            _wait_for_mentioned_message(
                client,
                created_id,
                message_id=mentioned_message_id,
                mentioned_user_id=member_id,
                timeout_seconds=args.timeout_seconds,
            )
            report["journeyEvidence"] = {
                "conversationIdHash": _stable_hash(created_id),
                "messageIdHash": _stable_hash(message_id),
                "mentionedMessageIdHash": _stable_hash(mentioned_message_id),
                "mentionedMemberHash": _stable_hash(member_id),
                "conversationReadable": True,
                "inboxProjected": True,
                "messageAccepted": True,
                "mentionRoundTrip": True,
                "cleanup": "pending",
            }
            report["steps"].append({"name": "create_to_inbox", "status": "passed"})
            report["steps"].append({"name": "send_message", "status": "passed"})
            report["steps"].append({"name": "mention_round_trip", "status": "passed"})

        report["status"] = "passed"
        return_code = 0
    except ProbeFailure as exc:
        report["status"] = "failed"
        report["failureCategory"] = exc.category
        report["blockingReason"] = str(exc)
        return_code = 1
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["failureCategory"] = "unexpected_error"
        report["blockingReason"] = type(exc).__name__
        return_code = 1
    finally:
        if created_id and client is not None:
            try:
                client.request(
                    "DELETE",
                    "/chat/conversations/" + urllib.parse.quote(created_id),
                    operation_id="DissolveConversation",
                    idempotency_key="chat-group-cleanup-" + uuid.uuid4().hex,
                )
                report["journeyEvidence"]["cleanup"] = "passed"
                report["steps"].append({"name": "cleanup", "status": "passed"})
            except Exception:  # noqa: BLE001
                report["journeyEvidence"]["cleanup"] = "failed"
                report["status"] = "failed"
                report["failureCategory"] = "cleanup_failed"
                report["blockingReason"] = "created probe conversation could not be dissolved"
                return_code = 1
        report["endedAt"] = _utc_now()
        _write_report(report_path, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "scenario": SCENARIO,
                    "report": str(report_path),
                    "failureCategory": report["failureCategory"],
                },
                ensure_ascii=False,
            )
        )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
