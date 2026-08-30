#!/usr/bin/env python3
"""环境集成探针的 HTTP 传输层：请求发起、重试裁决与请求头构造。

与 `environment_probe_semantics` 的分工是「怎么发」对「怎么判」：本模块只决定
一次请求是否还值得再发一次、以及发出去时带什么头，不解释响应体的业务含义。

重试裁决的唯一依据是服务端自己声明的恢复指令，而不是探针侧对状态码的猜测：
运行时错误契约（`_shared/openapi_common.yaml` 的 nature 闭集与 recovery 指令）
要求服务端标注失败性质，探针据此重试，从而不会把真实失败重试成假通过。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

INTEGRATION_FEED_SESSION_ID = "stackctl-environment-integration-probe"

# 传输层自身的抖动没有响应体可读，只能按错误文本识别；这些是连接级中断，
# 与被判定为业务失败的 HTTP 响应互不重叠。
_TRANSPORT_RETRY_MARKERS = (
    "timed out",
    "Remote end closed connection without response",
    "Connection reset",
    "Connection closed",
)


def declared_transient_retry_delay(payload: str) -> float | None:
    """读取错误响应自带的恢复指令，返回声明的重试等待秒数。

    只有服务端自己判定 `nature=transient` 且 `recovery.action=retry` 时才可重试；
    permanent / requiresPermission / bug 与全部 4xx 一律终态。
    """
    body = payload.strip()
    if not body:
        return None
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    if str(decoded.get("nature") or "") != "transient":
        return None
    recovery = decoded.get("recovery")
    if not isinstance(recovery, dict):
        return None
    if str(recovery.get("action") or "") != "retry":
        return None
    after_seconds = recovery.get("afterSeconds")
    return float(after_seconds) if isinstance(after_seconds, (int, float)) else 0.0


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 12,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 2.0,
    retry_trace: list[dict[str, Any]] | None = None,
) -> tuple[bool, int | None, str]:
    total_attempts = max(1, retry_attempts)
    for attempt in range(1, total_attempts + 1):
        req = urllib.request.Request(
            url, headers=headers or {}, data=body, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
                return True, int(response.status), payload
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            declared_delay = (
                declared_transient_retry_delay(payload)
                if int(exc.code) >= 500
                else None
            )
            if declared_delay is None or attempt >= total_attempts:
                return False, int(exc.code), payload
            if retry_trace is not None:
                retry_trace.append(
                    {
                        "attempt": attempt,
                        "statusCode": int(exc.code),
                        "declaredAfterSeconds": declared_delay,
                    }
                )
            time.sleep(
                max(declared_delay, max(0.0, retry_sleep_seconds)) * attempt
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if attempt >= total_attempts or not any(
                marker in message for marker in _TRANSPORT_RETRY_MARKERS
            ):
                return False, None, message
            if retry_trace is not None:
                retry_trace.append({"attempt": attempt, "transportError": message})
            time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return False, None, "unknown request failure"


def common_headers(test_auth_token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
    }
    token = test_auth_token.strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def json_headers(test_auth_token: str) -> dict[str, str]:
    headers = common_headers(test_auth_token)
    headers["Content-Type"] = "application/json"
    return headers


def public_headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def feed_headers(test_auth_token: str = "") -> dict[str, str]:
    """Ranked recommend feeds require a session id (query or X-Client-Session-Id)."""

    headers = common_headers(test_auth_token)
    headers["X-Client-Session-Id"] = INTEGRATION_FEED_SESSION_ID
    return headers


def feed_url(base: str, query: str) -> str:
    separator = "&" if "?" in query else "?"
    return (
        f"{base.rstrip('/')}/content/feed{query}"
        f"{separator}sessionId={INTEGRATION_FEED_SESSION_ID}"
    )
