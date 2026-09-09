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
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from quwoquan_ops.cli.lib.release_video_delivery import (
    SHA256_RE,
    probe_https_video,
    validate_delivery,
)

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


class _PublicMediaClient:
    """为现有 Data 字节判定提供本次探针的超时与重试预算。"""

    def __init__(
        self,
        timeout: int,
        attempts: int,
        sleep_seconds: float,
        trace: list[dict[str, Any]],
    ) -> None:
        self.timeout = timeout
        self.attempts = attempts
        self.sleep_seconds = sleep_seconds
        self.trace = trace

    def get_bytes(self, url: str, *, byte_range: str, max_bytes: int) -> Any:
        if not url.startswith("https://") or max_bytes <= 0:
            raise ValueError("public media requires HTTPS and a positive byte budget")
        headers = {"Accept": "*/*"}
        if byte_range:
            headers["Range"] = byte_range
        ok, status, payload, response_headers = request_bytes(
            url, headers=headers, max_bytes=max_bytes, timeout=self.timeout,
            attempts=self.attempts, sleep_seconds=self.sleep_seconds, trace=self.trace,
        )
        if not ok:
            raise ValueError(f"public media GET failed: {status or 'ERR'} {url}")
        return SimpleNamespace(
            status=status, body=payload,
            content_type=response_headers.get("Content-Type", ""),
            content_range=response_headers.get("Content-Range", ""),
            etag=response_headers.get("ETag", ""),
        )


def request_bytes(
    url: str,
    *,
    headers: dict[str, str],
    max_bytes: int,
    timeout: int,
    attempts: int,
    sleep_seconds: float,
    trace: list[dict[str, Any]],
) -> tuple[bool, int, bytes, Mapping[str, str]]:
    for attempt in range(1, max(1, attempts) + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=max(1, timeout)) as response:
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise ValueError("public media exceeded declared byte budget")
                return True, int(response.status), payload, response.headers
        except urllib.error.HTTPError as exc:
            body = exc.read(65536).decode("utf-8", errors="replace")
            delay = declared_transient_retry_delay(body) if exc.code >= 500 else None
            if delay is None or attempt >= max(1, attempts):
                return False, exc.code, b"", exc.headers
            trace.append({"attempt": attempt, "statusCode": exc.code, "declaredAfterSeconds": delay})
            time.sleep(max(delay, max(0.0, sleep_seconds)) * attempt)
        except (OSError, urllib.error.URLError) as exc:
            if attempt >= max(1, attempts) or not any(
                marker in str(exc) for marker in _TRANSPORT_RETRY_MARKERS
            ):
                raise ValueError(f"public media GET failed: {exc}") from exc
            trace.append({"attempt": attempt, "transportError": str(exc)})
            time.sleep(max(0.0, sleep_seconds) * attempt)
    raise ValueError("public media GET exhausted its attempt budget")


def probe_public_media(
    url: str,
    *,
    kind: str,
    asset: dict[str, Any] | None = None,
    timeout: int = 12,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 2.0,
) -> dict[str, Any]:
    """复用已有公开媒体判定；release 资产按完整字节身份，视频另验 Range。"""
    if asset is not None and (
        not isinstance(asset.get("bytes"), int)
        or isinstance(asset.get("bytes"), bool)
        or asset["bytes"] <= 0
        or SHA256_RE.fullmatch(str(asset.get("sha256") or "")) is None
        or not str(asset.get("contentType") or "").startswith(kind + "/")
    ):
        raise ValueError("public media immutable release identity is invalid")
    if kind == "video" and asset:
        delivery = probe_https_video(url, expected_bytes=asset["bytes"], timeout_seconds=timeout)
        validate_delivery(
            delivery, expected_mime_type=asset["contentType"],
            expected_bytes=asset["bytes"], expected_hash=asset["sha256"],
            expected_public_slice_key=asset["publicSliceKey"],
        )
        return {"publicUrl": url, "hashVerified": True, **delivery}
    data_scripts = str(Path(__file__).resolve().parents[3] / "quwoquan_data" / "scripts")
    if data_scripts not in sys.path:
        sys.path.insert(0, data_scripts)
    from content.release.environment.post_api_media_verification import _verify_binary_media

    trace: list[dict[str, Any]] = []
    client = _PublicMediaClient(timeout, retry_attempts, retry_sleep_seconds, trace)
    evidence = _verify_binary_media(
        client, url, expected_kind=kind,
        expected_bytes=asset["bytes"] if asset else 0,
        expected_sha256=asset["sha256"] if asset else "",
        expected_mime_type=asset["contentType"] if asset else "",
    )
    if trace:
        evidence["retriedAttempts"] = trace
    return evidence


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
