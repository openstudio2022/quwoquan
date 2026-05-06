#!/usr/bin/env python3
"""Run black-box assistant protocol smoke and write unified evidence report."""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
SCENARIO_FIXTURE = (
    REPO_ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "assistant"
    / "test_fixtures"
    / "scenarios"
    / "assistant_scenarios.json"
)
BAD_ANSWER_TOKENS = (
    "ASSISTANT.MIDDLEWARE",
    "tool_unavailable",
    "alpha mock",
    "工具观察",
    "工具结果",
)


class ProbeFailure(RuntimeError):
    def __init__(self, category: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        default=os.environ.get("API_CONTRACT_ENV")
        or os.environ.get("APP_RUNTIME_ENV")
        or "gamma-pr",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("GAMMA_BASE_URL", "http://127.0.0.1:18080"),
    )
    parser.add_argument(
        "--test-auth-token",
        default=os.environ.get("GAMMA_TEST_AUTH_TOKEN")
        or os.environ.get("TEST_AUTH_TOKEN")
        or "",
    )
    parser.add_argument("--scenario-id", default="travel_journey_basic")
    parser.add_argument("--user-id", default="assistant_pr_smoke_user")
    parser.add_argument(
        "--report",
        default="artifacts/assistant-runtime-smoke/gamma-pr/assistant_runtime_smoke.json",
    )
    parser.add_argument("--timeout-seconds", type=int, default=75)
    parser.add_argument("--stall-timeout-seconds", type=int, default=12)
    parser.add_argument("--request-timeout-seconds", type=int, default=12)
    return parser.parse_args()


def normalize_env(raw: str) -> str:
    text = (raw or "").strip()
    if text in ("cloud-gamma", "cloud-gamma-pre", "gamma-pr"):
        return "gamma"
    return text or "gamma"


def add_step(report: Dict[str, Any], name: str, status: str, **extra: Any) -> None:
    item = {"name": name, "status": status, "at": utc_now()}
    item.update(extra)
    report["steps"].append(item)


def read_scenario(scenario_id: str) -> Dict[str, Any]:
    payload = json.loads(SCENARIO_FIXTURE.read_text(encoding="utf-8"))
    for scenario in payload.get("scenarios", []):
        if str(scenario.get("id", "")).strip() == scenario_id:
            return scenario
    raise ProbeFailure(
        "scenario_not_found",
        "assistant scenario not found: {0}".format(scenario_id),
    )


def request_headers(user_id: str, test_auth_token: str, with_json: bool = False) -> Dict[str, str]:
    headers = {
        "Accept": "application/json",
        "X-Client-User-Id": user_id,
        "X-Test-Local-Gamma": "true",
    }
    if test_auth_token:
        headers["Authorization"] = "Bearer " + test_auth_token
        headers["X-Test-Auth-Token"] = test_auth_token
    if with_json:
        headers["Content-Type"] = "application/json"
    return headers


def request_json(
    base_url: str,
    path: str,
    *,
    method: str,
    user_id: str,
    test_auth_token: str,
    body: Optional[Dict[str, Any]] = None,
    timeout_seconds: int,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + path
    raw_body = None
    if body is not None:
        raw_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw_body,
        headers=request_headers(user_id, test_auth_token, with_json=body is not None),
        method=method,
    )
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds, context=ctx) as resp:
            payload = resp.read()
            if not payload:
                return {}
            return json.loads(payload.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        category = "auth_failed" if exc.code in (401, 403) else "http_error"
        raise ProbeFailure(
            category,
            "request {0} {1} failed with http {2}: {3}".format(
                method, path, exc.code, body_text[:400]
            ),
            retryable=exc.code >= 500,
        )
    except urllib.error.URLError as exc:
        raise ProbeFailure(
            "gateway_unreachable",
            "request {0} {1} failed: {2}".format(method, path, exc),
            retryable=True,
        )


def healthz_ok(base_url: str, test_auth_token: str, timeout_seconds: int) -> bool:
    url = base_url.rstrip("/") + "/healthz"
    req = urllib.request.Request(
        url,
        headers=request_headers("assistant_pr_smoke_health", test_auth_token),
        method="GET",
    )
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds, context=ctx) as resp:
            return 200 <= int(resp.status) < 300
    except Exception:  # noqa: BLE001
        return False


def open_http_connection(
    url: str,
    timeout_seconds: int,
) -> Tuple[http.client.HTTPConnection, str]:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""
    port = parsed.port or (443 if scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = path + "?" + parsed.query
    if scheme == "https":
        connection = http.client.HTTPSConnection(
            host,
            port,
            timeout=timeout_seconds,
            context=ssl._create_unverified_context(),
        )
    else:
        connection = http.client.HTTPConnection(host, port, timeout=timeout_seconds)
    return connection, path


def decode_sse_frame(lines: List[str]) -> Optional[Dict[str, Any]]:
    if not lines:
        return None
    event_name = ""
    data_lines: List[str] = []
    for line in lines:
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    if not data_lines:
        return None
    try:
        payload = json.loads("\n".join(data_lines))
    except ValueError as exc:
        raise ProbeFailure("stream_decode_error", "invalid assistant SSE frame: {0}".format(exc))
    payload["_sseEventName"] = event_name
    return payload


def extract_answer_from_event(payload: Dict[str, Any]) -> str:
    raw_payload = payload.get("payload")
    if isinstance(raw_payload, dict):
        for key in ("text", "answer", "finalText", "content"):
            value = raw_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def stream_assistant_turn(
    *,
    base_url: str,
    turn_id: str,
    user_id: str,
    test_auth_token: str,
    timeout_seconds: int,
    stall_timeout_seconds: int,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/v1/assistant/turns/{0}/stream".format(turn_id)
    connection, path = open_http_connection(url, stall_timeout_seconds)
    body = "{}"
    headers = request_headers(user_id, test_auth_token, with_json=True)
    started = time.monotonic()
    try:
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        if response.status < 200 or response.status >= 300:
            failure_body = response.read().decode("utf-8", errors="replace")
            raise ProbeFailure(
                "http_error",
                "assistant stream failed with http {0}: {1}".format(
                    response.status, failure_body[:400]
                ),
                retryable=response.status >= 500,
            )
        raw_sock = None
        if getattr(response, "fp", None) is not None:
            raw = getattr(response.fp, "raw", None)
            raw_sock = getattr(raw, "_sock", None)
        if raw_sock is not None:
            raw_sock.settimeout(stall_timeout_seconds)

        frames: List[Dict[str, Any]] = []
        buffer = ""
        answer = ""
        while True:
            if time.monotonic() - started > timeout_seconds:
                raise ProbeFailure(
                    "stream_timeout",
                    "assistant stream exceeded {0}s budget".format(timeout_seconds),
                    retryable=True,
                )
            try:
                if hasattr(response.fp, "read1"):
                    chunk = response.fp.read1(4096)
                else:
                    chunk = response.fp.read(4096)
            except socket.timeout:
                raise ProbeFailure(
                    "stream_stalled",
                    "assistant stream made no progress for {0}s".format(
                        stall_timeout_seconds
                    ),
                    retryable=True,
                )
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            buffer = buffer.replace("\r\n", "\n")
            split_index = buffer.find("\n\n")
            while split_index >= 0:
                frame_text = buffer[:split_index]
                buffer = buffer[split_index + 2 :]
                frame = decode_sse_frame(frame_text.splitlines())
                if frame is None:
                    split_index = buffer.find("\n\n")
                    continue
                frames.append(frame)
                answer_text = extract_answer_from_event(frame)
                if answer_text:
                    answer = answer_text
                if str(frame.get("eventType", "")).strip() in ("final_answer", "turn_failed"):
                    return {
                        "events": frames,
                        "answer": answer.strip(),
                        "durationMs": int((time.monotonic() - started) * 1000),
                    }
                split_index = buffer.find("\n\n")
        return {
            "events": frames,
            "answer": answer.strip(),
            "durationMs": int((time.monotonic() - started) * 1000),
        }
    finally:
        connection.close()


def validate_stream_result(
    scenario: Dict[str, Any],
    stream_result: Dict[str, Any],
) -> Dict[str, Any]:
    events = list(stream_result.get("events") or [])
    event_types = [str(event.get("eventType", "")).strip() for event in events]
    answer = str(stream_result.get("answer", "")).strip()
    if any(event.get("runtimeFailure") for event in events):
        failures = [
            event.get("runtimeFailure")
            for event in events
            if isinstance(event.get("runtimeFailure"), dict)
        ]
        raise ProbeFailure(
            "runtime_failure",
            "assistant runtimeFailure emitted: {0}".format(
                json.dumps(failures[:2], ensure_ascii=False)
            ),
        )
    if "turn_started" not in event_types:
        raise ProbeFailure(
            "missing_event",
            "assistant stream missing turn_started: {0}".format(event_types),
        )
    if "final_answer" not in event_types:
        raise ProbeFailure(
            "missing_event",
            "assistant stream missing final_answer: {0}".format(event_types),
            retryable=True,
        )
    if "assistant.model.interaction" not in event_types:
        raise ProbeFailure(
            "missing_event",
            "assistant stream missing assistant.model.interaction: {0}".format(
                event_types
            ),
        )
    if not answer:
        raise ProbeFailure("empty_answer", "assistant answer is empty", retryable=True)
    for token in BAD_ANSWER_TOKENS:
        if token in answer:
            raise ProbeFailure(
                "bad_answer_token",
                "assistant answer contains retired/debug token: {0}".format(token),
            )
    remote_expectations = scenario.get("remoteExpectations") or {}
    expected_fragments = list(remote_expectations.get("answerFragments") or [])
    if expected_fragments and not any(fragment in answer for fragment in expected_fragments):
        raise ProbeFailure(
            "semantic_regression",
            "assistant answer missing expected fragments: {0}".format(
                expected_fragments
            ),
        )
    return {
        "answer": answer,
        "eventTypes": event_types,
        "expectedFragments": expected_fragments,
    }


def report_template(args: argparse.Namespace, scenario: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "scenario": "assistant.runtime.protocol_smoke",
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "retryable": False,
        "startedAt": utc_now(),
        "endedAt": "",
        "environment": {
            "env": normalize_env(args.env),
            "runtimeKind": "cloud-gamma-protocol-smoke",
            "gatewayBaseUrl": args.base_url.rstrip("/"),
            "commitSha": os.environ.get("GITHUB_SHA", ""),
            "githubRunId": os.environ.get("GITHUB_RUN_ID", ""),
        },
        "assistant": {
            "scenarioId": scenario.get("id"),
            "skillId": scenario.get("skillId", ""),
            "domainId": scenario.get("domainId", ""),
            "question": scenario.get("question", ""),
            "conversationId": "",
            "turnId": "",
            "answer": "",
            "eventTypes": [],
        },
        "timings": {
            "healthzMs": 0,
            "createConversationMs": 0,
            "createTurnMs": 0,
            "streamMs": 0,
            "totalMs": 0,
        },
        "steps": [],
    }


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    scenario = read_scenario(args.scenario_id)
    report = report_template(args, scenario)
    started = time.monotonic()
    exit_code = 0

    try:
        add_step(report, "healthz", "running")
        health_started = time.monotonic()
        if not healthz_ok(args.base_url, args.test_auth_token, args.request_timeout_seconds):
            raise ProbeFailure("env_not_ready", "gamma healthz failed", retryable=True)
        report["timings"]["healthzMs"] = int((time.monotonic() - health_started) * 1000)
        add_step(report, "healthz", "passed")

        add_step(report, "create_conversation", "running")
        conversation_started = time.monotonic()
        conversation = request_json(
            args.base_url,
            "/v1/assistant/conversations",
            method="POST",
            user_id=args.user_id,
            test_auth_token=args.test_auth_token,
            body={"summary": "assistant protocol smoke {0}".format(args.scenario_id)},
            timeout_seconds=args.request_timeout_seconds,
        )
        report["timings"]["createConversationMs"] = int(
            (time.monotonic() - conversation_started) * 1000
        )
        conversation_id = str(conversation.get("conversationId", "")).strip()
        if not conversation_id:
            raise ProbeFailure(
                "env_not_ready",
                "assistant create conversation missing conversationId: {0}".format(
                    json.dumps(conversation, ensure_ascii=False)[:400]
                ),
                retryable=True,
            )
        report["assistant"]["conversationId"] = conversation_id
        add_step(report, "create_conversation", "passed", conversationId=conversation_id)

        add_step(report, "create_turn", "running")
        turn_started = time.monotonic()
        turn = request_json(
            args.base_url,
            "/v1/assistant/conversations/{0}/turns".format(conversation_id),
            method="POST",
            user_id=args.user_id,
            test_auth_token=args.test_auth_token,
            body={
                "turnType": "user",
                "skillId": scenario.get("skillId", ""),
                "domainId": scenario.get("domainId", ""),
                "input": {"text": scenario.get("question", "")},
                "trigger": {"type": "user_message"},
            },
            timeout_seconds=args.request_timeout_seconds,
        )
        report["timings"]["createTurnMs"] = int((time.monotonic() - turn_started) * 1000)
        turn_id = str(turn.get("turnId", "")).strip()
        if not turn_id:
            raise ProbeFailure(
                "env_not_ready",
                "assistant create turn missing turnId: {0}".format(
                    json.dumps(turn, ensure_ascii=False)[:400]
                ),
                retryable=True,
            )
        report["assistant"]["turnId"] = turn_id
        add_step(report, "create_turn", "passed", turnId=turn_id)

        add_step(report, "stream_turn", "running")
        stream_result = stream_assistant_turn(
            base_url=args.base_url,
            turn_id=turn_id,
            user_id=args.user_id,
            test_auth_token=args.test_auth_token,
            timeout_seconds=args.timeout_seconds,
            stall_timeout_seconds=args.stall_timeout_seconds,
        )
        report["timings"]["streamMs"] = int(stream_result.get("durationMs", 0))
        validation = validate_stream_result(scenario, stream_result)
        report["assistant"]["answer"] = validation["answer"]
        report["assistant"]["eventTypes"] = validation["eventTypes"]
        add_step(
            report,
            "stream_turn",
            "passed",
            eventTypes=validation["eventTypes"],
        )
        report["status"] = "passed"
    except ProbeFailure as exc:
        report["status"] = "failed"
        report["failureCategory"] = exc.category
        report["blockingReason"] = str(exc)
        report["retryable"] = exc.retryable
        add_step(
            report,
            "failure",
            "failed",
            category=exc.category,
            message=str(exc),
            retryable=exc.retryable,
        )
        exit_code = 1
    finally:
        report["timings"]["totalMs"] = int((time.monotonic() - started) * 1000)
        report["endedAt"] = utc_now()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if report["status"] == "passed":
        print(
            "[assistant-runtime-smoke] PASS scenario={0} turnId={1}".format(
                report["assistant"].get("scenarioId", ""),
                report["assistant"].get("turnId", ""),
            )
        )
    else:
        print(
            "[assistant-runtime-smoke] FAIL category={0} reason={1}".format(
                report.get("failureCategory", ""),
                report.get("blockingReason", ""),
            ),
            file=sys.stderr,
        )
    print("[assistant-runtime-smoke] report: {0}".format(report_path))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
