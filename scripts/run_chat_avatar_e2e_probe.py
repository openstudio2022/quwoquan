#!/usr/bin/env python3
"""Run black-box chat group avatar E2E probe and write unified evidence report."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "chat.group_avatar.sync_display_e2e"
SCHEMA_VERSION = 1
CONTRACT_PLACEHOLDER_TOKENS = ("契", "contract", "default-contract")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=os.environ.get("API_CONTRACT_ENV", "beta"))
    parser.add_argument("--runtime-kind", default="")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("CHAT_AVATAR_GATEWAY_BASE_URL")
        or os.environ.get("GAMMA_BASE_URL")
        or os.environ.get("LOCAL_GAMMA_GATEWAY_BASE_URL")
        or "http://127.0.0.1:18080",
    )
    parser.add_argument(
        "--media-base-url",
        default=os.environ.get("CHAT_AVATAR_MEDIA_BASE_URL")
        or os.environ.get("MEDIA_AVATAR_CDN_BASE_URL")
        or os.environ.get("LOCAL_GAMMA_MEDIA_BASE_URL")
        or "",
    )
    parser.add_argument(
        "--test-auth-token",
        default=os.environ.get("GAMMA_TEST_AUTH_TOKEN")
        or os.environ.get("LOCAL_GAMMA_TEST_AUTH_TOKEN")
        or os.environ.get("TEST_AUTH_TOKEN")
        or "",
    )
    parser.add_argument("--creator-id", default="user_test_001")
    parser.add_argument("--initial-member-id", action="append", default=[])
    parser.add_argument("--added-member-id", default="user_test_004")
    parser.add_argument("--removed-member-id", default="user_test_004")
    parser.add_argument("--title-prefix", default="avatar-e2e")
    parser.add_argument("--report", default="artifacts/avatar-e2e/beta/avatar_e2e_report.json")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--mongo-uri", default=os.environ.get("CHAT_AVATAR_MONGO_URI", ""))
    parser.add_argument("--mongo-database", default=os.environ.get("CHAT_AVATAR_MONGO_DATABASE", ""))
    parser.add_argument("--compose-mongo", action="store_true")
    parser.add_argument("--skip-media-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def runtime_kind(env_name: str, explicit: str) -> str:
    if explicit:
        return explicit
    if env_name == "local-gamma":
        return "local-gamma-mirror"
    if env_name == "gamma":
        return "cloud-gamma"
    return "local-stack"


def default_members(args: argparse.Namespace) -> list[str]:
    if args.initial_member_id:
        return [item for item in args.initial_member_id if item.strip()]
    return ["user_test_002", "user_test_003"]


def report_template(args: argparse.Namespace, members: list[str]) -> dict[str, Any]:
    env_name = normalize_env(args.env)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "scenario": SCENARIO,
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "retryable": False,
        "startedAt": utc_now(),
        "endedAt": "",
        "environment": {
            "env": env_name,
            "runtimeKind": runtime_kind(env_name, args.runtime_kind),
            "gatewayBaseUrl": args.base_url.rstrip("/"),
            "mediaBaseUrl": args.media_base_url.rstrip("/"),
            "commitSha": os.environ.get("GITHUB_SHA", ""),
            "githubRunId": os.environ.get("GITHUB_RUN_ID", ""),
        },
        "device": {},
        "conversation": {
            "conversationId": "",
            "creatorUserId": args.creator_id,
            "memberIds": [args.creator_id, *members],
            "addedMemberId": args.added_member_id,
            "removedMemberId": args.removed_member_id,
            "initialAvatarUrl": "",
            "finalAvatarUrl": "",
            "groupAvatarVersionBefore": 0,
            "groupAvatarVersionAfterAdd": 0,
            "groupAvatarVersionAfterRemove": 0,
        },
        "serviceEvidence": {
            "taskOutbox": {"status": "not_collected", "records": []},
            "asyncTask": {"status": "not_collected", "records": []},
            "notificationOutbox": {"status": "not_collected", "records": []},
            "deliveryLedger": {"status": "not_collected", "deliveredRecipients": []},
            "syncPatches": [],
        },
        "serviceEndpointEvidence": {
            "healthz": "",
            "chatConversations": "/v1/chat/conversations",
            "userSync": "/v1/user/sync",
            "media": "",
        },
        "uiEvidence": {
            "conversationListAvatarVisible": False,
            "conversationDetailAvatarVisible": False,
            "avatarImageLoaded": False,
            "senderAvatarPreserved": False,
            "screenshots": [],
        },
        "steps": [],
    }


def normalize_env(raw: str) -> str:
    env_name = raw.strip()
    if env_name in {"cloud-gamma", "cloud-gamma-pre", "cloud-gamma-prod-smoke"}:
        return "gamma"
    return env_name or "beta"


def add_step(report: dict[str, Any], name: str, status: str, **extra: Any) -> None:
    item = {"name": name, "status": status, "at": utc_now()}
    item.update(extra)
    report["steps"].append(item)


def request_json(
    args: argparse.Namespace,
    method: str,
    path: str,
    *,
    user_id: str,
    body: dict[str, Any] | None = None,
    timeout: int = 12,
) -> dict[str, Any]:
    url = args.base_url.rstrip("/") + path
    data = None
    headers = {
        "Accept": "application/json",
        "X-Client-User-Id": user_id,
        "X-Test-Local-Gamma": "true",
    }
    if args.test_auth_token:
        headers["Authorization"] = "Bearer " + args.test_auth_token
        headers["X-Test-Auth-Token"] = args.test_auth_token
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))


def request_ok(args: argparse.Namespace, url: str, timeout: int = 8) -> bool:
    headers = {"X-Test-Local-Gamma": "true"}
    if args.test_auth_token:
        headers["Authorization"] = "Bearer " + args.test_auth_token
        headers["X-Test-Auth-Token"] = args.test_auth_token
    req = urllib.request.Request(url, headers=headers, method="GET")
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return 200 <= int(resp.status) < 300


def classify_http_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError) and exc.code in {401, 403}:
        return "auth_failed"
    if isinstance(exc, urllib.error.URLError):
        return "gateway_unreachable"
    return "unknown"


def is_retryable_failure(category: str) -> bool:
    return category in {
        "gateway_unreachable",
        "avatar_task_timeout",
        "notification_not_delivered",
        "media_load_failed",
        "env_not_ready",
        "unknown",
    }


def has_bad_avatar_placeholder(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    return any(token in lowered for token in CONTRACT_PLACEHOLDER_TOKENS)


def parse_version(conversation: dict[str, Any]) -> int:
    raw = conversation.get("groupAvatarVersion") or 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def wait_for_avatar_version(
    args: argparse.Namespace,
    report: dict[str, Any],
    conversation_id: str,
    minimum_version: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + args.timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = request_json(
            args,
            "GET",
            f"/v1/chat/conversations/{urllib.parse.quote(conversation_id)}",
            user_id=report["conversation"]["creatorUserId"],
        )
        avatar_url = str(last.get("avatarUrl") or "").strip()
        if parse_version(last) >= minimum_version and avatar_url:
            return last
        time.sleep(max(0.2, args.poll_interval_seconds))
    add_step(report, "wait_avatar_version", "failed", last=last, minimumVersion=minimum_version)
    raise ProbeFailure("avatar_task_timeout", f"avatar version did not reach {minimum_version}")


def poll_user_sync(
    args: argparse.Namespace,
    user_id: str,
    conversation_id: str,
    timeout_seconds: int,
    minimum_version: int,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_seconds
    last_seq = 0
    while time.monotonic() < deadline:
        resp = request_json(
            args,
            "POST",
            "/v1/user/sync",
            user_id=user_id,
            body={"afterSeq": last_seq, "limit": 200},
        )
        latest = resp.get("latestSyncSeq")
        if isinstance(latest, (int, float)):
            last_seq = max(last_seq, int(latest) - 200)
            if last_seq < 0:
                last_seq = 0
        for patch in resp.get("patches") or []:
            payload = patch.get("payload") or {}
            version = payload.get("groupAvatarVersion") or payload.get("avatarVersion") or 0
            try:
                numeric_version = int(version)
            except (TypeError, ValueError):
                numeric_version = 0
            if (
                patch.get("type") == "conversation.avatar.updated"
                and payload.get("conversationId") == conversation_id
                and numeric_version >= minimum_version
            ):
                return patch
        time.sleep(max(0.2, args.poll_interval_seconds))
    return None


def collect_sync_patches(
    args: argparse.Namespace,
    report: dict[str, Any],
    conversation_id: str,
    user_ids: list[str],
    minimum_version: int,
) -> None:
    patches = []
    missing = []
    for user_id in user_ids:
        try:
            patch = poll_user_sync(args, user_id, conversation_id, args.timeout_seconds, minimum_version)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and args.compose_mongo:
                add_step(
                    report,
                    "sync_patch_blackbox",
                    "skipped",
                    reason="user sync endpoint unavailable; local Mongo notification evidence will be used",
                )
                return
            raise
        if patch is None:
            missing.append(user_id)
            continue
        patches.append(patch)
    report["serviceEvidence"]["syncPatches"].extend(patches)
    report["serviceEvidence"]["deliveryLedger"]["deliveredRecipients"] = sorted(
        {patch.get("userId") for patch in patches if patch.get("userId")}
    )
    if missing:
        raise ProbeFailure("notification_not_delivered", "missing sync patch for " + ",".join(missing))


def verify_media(args: argparse.Namespace, report: dict[str, Any], avatar_url: str) -> None:
    if args.skip_media_check:
        add_step(report, "media_check", "skipped", reason="skip-media-check")
        return
    resolved_url = resolve_media_url(args, avatar_url)
    report["serviceEndpointEvidence"]["media"] = resolved_url
    if not request_ok(args, resolved_url):
        raise ProbeFailure("media_load_failed", f"avatarUrl is not reachable: {resolved_url}")
    report["uiEvidence"]["avatarImageLoaded"] = True
    add_step(report, "media_check", "passed", avatarUrl=avatar_url, resolvedAvatarUrl=resolved_url)


def resolve_media_url(args: argparse.Namespace, avatar_url: str) -> str:
    trimmed = avatar_url.strip()
    if trimmed.startswith(("http://", "https://")):
        return trimmed
    media_base = args.media_base_url.strip().rstrip("/")
    if not media_base:
        raise ProbeFailure(
            "media_load_failed",
            "avatarUrl is relative and --media-base-url is required: " + trimmed,
        )
    return urllib.parse.urljoin(media_base + "/", trimmed.lstrip("/"))


def send_sender_avatar_message(args: argparse.Namespace, report: dict[str, Any], conversation_id: str) -> None:
    expected = f"https://avatar.test/{report['conversation']['creatorUserId']}.png"
    result = request_json(
        args,
        "POST",
        f"/v1/chat/conversations/{urllib.parse.quote(conversation_id)}/messages",
        user_id=report["conversation"]["creatorUserId"],
        body={
            "type": "text",
            "content": "avatar e2e sender snapshot",
            "clientMsgId": "avatar-e2e-" + str(int(time.time() * 1000)),
            "senderAvatarUrlSnapshot": expected,
            "senderDisplayNameSnapshot": "Avatar E2E Creator",
        },
    )
    actual = str(result.get("senderAvatarUrlSnapshot") or "").strip()
    if actual != expected:
        raise ProbeFailure("sender_avatar_regression", f"sender avatar snapshot mismatch: {actual}")
    report["uiEvidence"]["senderAvatarPreserved"] = True
    add_step(report, "sender_avatar_snapshot", "passed", messageId=result.get("id") or result.get("_id"))


def collect_mongo_evidence(args: argparse.Namespace, report: dict[str, Any], conversation_id: str) -> None:
    if not (args.mongo_uri or args.compose_mongo):
        return
    database = args.mongo_database or ("quwoquan_chat" if normalize_env(args.env) in {"gamma", "local-gamma"} else "quwoquan_chat_local")
    js = f"""
const convId = {json.dumps(conversation_id)};
const result = {{}};
const dbh = db.getSiblingDB({json.dumps(database)});
function docs(name, filter) {{
  try {{
    return dbh.getCollection(name).find(filter).limit(20).toArray().map((doc) => {{
      doc._id = String(doc._id);
      return doc;
    }});
  }} catch (e) {{
    return [{{error: String(e)}}];
  }}
}}
result.taskOutbox = docs("reliable_task_outbox", {{aggregateId: convId}});
result.asyncTask = docs("reliable_async_task", {{aggregateId: convId}});
result.notificationOutbox = docs("notification_outbox", {{aggregateId: convId}});
const notificationIds = result.notificationOutbox.map((doc) => doc._id);
result.deliveryLedger = notificationIds.length === 0 ? [] : docs("notification_delivery_ledger", {{notificationId: {{$in: notificationIds}}}});
print(JSON.stringify(result));
"""
    if args.compose_mongo:
        cmd = [
            "docker",
            "compose",
            "-f",
            str(REPO_ROOT / "quwoquan_service/docker-compose.gamma-local.yaml"),
            "exec",
            "-T",
            "mongodb",
            "mongosh",
            "--quiet",
        ]
        run = subprocess.run(
            cmd,
            input=js,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(REPO_ROOT / "quwoquan_service"),
            check=False,
        )
    else:
        run = subprocess.run(
            ["mongosh", "--quiet", args.mongo_uri, "--eval", js],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(REPO_ROOT),
            check=False,
        )
    if run.returncode != 0:
        for key in ("taskOutbox", "asyncTask", "notificationOutbox", "deliveryLedger"):
            report["serviceEvidence"][key] = {"status": "failed", "error": run.stdout[-2000:]}
        return
    try:
        evidence = json.loads((run.stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        for key in ("taskOutbox", "asyncTask", "notificationOutbox", "deliveryLedger"):
            report["serviceEvidence"][key] = {"status": "failed", "error": str(exc), "output": run.stdout[-2000:]}
        return
    report["serviceEvidence"]["taskOutbox"] = {"status": "collected", "records": evidence.get("taskOutbox", [])}
    report["serviceEvidence"]["asyncTask"] = {"status": "collected", "records": evidence.get("asyncTask", [])}
    report["serviceEvidence"]["notificationOutbox"] = {"status": "collected", "records": evidence.get("notificationOutbox", [])}
    delivered = []
    for item in evidence.get("deliveryLedger", []) or []:
        if item.get("status") == "delivered" and item.get("recipientId"):
            delivered.append(item["recipientId"])
    report["serviceEvidence"]["deliveryLedger"] = {
        "status": "collected",
        "records": evidence.get("deliveryLedger", []),
        "deliveredRecipients": sorted(set(delivered)),
    }


class ProbeFailure(Exception):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def run_probe(args: argparse.Namespace, report: dict[str, Any], members: list[str]) -> None:
    add_step(report, "healthz", "running")
    healthz_url = args.base_url.rstrip("/") + "/healthz"
    report["serviceEndpointEvidence"]["healthz"] = healthz_url
    if not request_ok(args, healthz_url, timeout=10):
        raise ProbeFailure("gateway_unreachable", "healthz failed")
    report["steps"][-1]["status"] = "passed"

    title = f"{args.title_prefix}-{normalize_env(args.env)}-{int(time.time())}"
    created = request_json(
        args,
        "POST",
        "/v1/chat/conversations",
        user_id=args.creator_id,
        body={"type": "group", "title": title, "initialMemberIds": members, "maxGroupSize": 100},
    )
    conversation_id = str(created.get("conversationId") or created.get("_id") or created.get("id") or "")
    if not conversation_id:
        raise ProbeFailure("env_not_ready", "create conversation response missing id: " + json.dumps(created, ensure_ascii=False)[:1000])
    initial_avatar = str(created.get("avatarUrl") or "").strip()
    if has_bad_avatar_placeholder(initial_avatar):
        raise ProbeFailure("sender_avatar_regression", f"invalid initial avatarUrl: {initial_avatar}")
    initial_version = parse_version(created)
    report["conversation"]["conversationId"] = conversation_id
    report["conversation"]["initialAvatarUrl"] = initial_avatar
    report["conversation"]["initialAvatarUrlResolved"] = resolve_media_url(args, initial_avatar) if args.media_base_url or initial_avatar.startswith(("http://", "https://")) else initial_avatar
    report["conversation"]["groupAvatarVersionBefore"] = initial_version
    add_step(report, "create_conversation", "passed", conversationId=conversation_id, avatarUrl=initial_avatar)

    request_json(
        args,
        "POST",
        f"/v1/chat/conversations/{urllib.parse.quote(conversation_id)}/members",
        user_id=args.creator_id,
        body={"userIds": [args.added_member_id]},
    )
    after_add = wait_for_avatar_version(args, report, conversation_id, initial_version + 1)
    add_version = parse_version(after_add)
    add_avatar = str(after_add.get("avatarUrl") or "").strip()
    report["conversation"]["groupAvatarVersionAfterAdd"] = add_version
    report["conversation"]["finalAvatarUrl"] = add_avatar
    report["conversation"]["finalAvatarUrlResolved"] = resolve_media_url(args, add_avatar) if args.media_base_url or add_avatar.startswith(("http://", "https://")) else add_avatar
    add_step(report, "add_member_avatar_update", "passed", version=add_version, avatarUrl=add_avatar)
    collect_sync_patches(args, report, conversation_id, [args.creator_id, *members, args.added_member_id], add_version)

    send_sender_avatar_message(args, report, conversation_id)

    if args.removed_member_id:
        request_json(
            args,
            "DELETE",
            f"/v1/chat/conversations/{urllib.parse.quote(conversation_id)}/members/{urllib.parse.quote(args.removed_member_id)}",
            user_id=args.creator_id,
        )
        after_remove = wait_for_avatar_version(args, report, conversation_id, add_version + 1)
        remove_version = parse_version(after_remove)
        remove_avatar = str(after_remove.get("avatarUrl") or "").strip()
        report["conversation"]["groupAvatarVersionAfterRemove"] = remove_version
        report["conversation"]["finalAvatarUrl"] = remove_avatar
        report["conversation"]["finalAvatarUrlResolved"] = resolve_media_url(args, remove_avatar) if args.media_base_url or remove_avatar.startswith(("http://", "https://")) else remove_avatar
        add_step(report, "remove_member_avatar_update", "passed", version=remove_version, avatarUrl=remove_avatar)
        current_members = [args.creator_id, *members]
        current_members = [user_id for user_id in current_members if user_id != args.removed_member_id]
        collect_sync_patches(args, report, conversation_id, current_members, remove_version)

    verify_media(args, report, str(report["conversation"]["finalAvatarUrl"]))
    collect_mongo_evidence(args, report, conversation_id)


def write_report(report: dict[str, Any], path: Path) -> None:
    report["endedAt"] = utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[chat-avatar-e2e] report: {path}")
    print(f"[chat-avatar-e2e] status: {report['status']}")


def main() -> int:
    args = parse_args()
    members = default_members(args)
    report = report_template(args, members)
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    if args.dry_run:
        report["status"] = "passed"
        report["failureCategory"] = ""
        add_step(report, "dry_run", "passed")
        write_report(report, report_path)
        return 0
    try:
        run_probe(args, report, members)
        report["status"] = "passed"
        return_code = 0
    except ProbeFailure as exc:
        report["status"] = "failed"
        report["failureCategory"] = exc.category
        report["blockingReason"] = str(exc)
        report["retryable"] = is_retryable_failure(exc.category)
        add_step(report, "failure", "failed", category=exc.category, error=str(exc))
        return_code = 1
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["failureCategory"] = classify_http_error(exc)
        report["blockingReason"] = str(exc)
        report["retryable"] = is_retryable_failure(report["failureCategory"])
        add_step(report, "failure", "failed", category=report["failureCategory"], error=str(exc))
        return_code = 1
    write_report(report, report_path)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
