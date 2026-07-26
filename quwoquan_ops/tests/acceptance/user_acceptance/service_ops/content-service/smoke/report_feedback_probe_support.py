from __future__ import annotations

import base64
import contextlib
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as xml
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (
            candidate / "quwoquan_service"
        ).is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")


REPO_ROOT = _find_repo_root()
sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.local_environment_auth import (  # noqa: E402
    LocalAcceptanceSession,
    open_local_acceptance_session,
)


LOCAL_TARGETS = {"beta": "beta-local", "gamma": "gamma-local"}
_LOCAL_CANARY_TARGETS = {"prod": "prod-sim"}


class ProbeFailure(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def reporter_session(
    *,
    environment: str,
    base_url: str,
    resolve_host: str,
    hosted_token_env: str,
    target_name: str = "",
) -> LocalAcceptanceSession:
    local_target = LOCAL_TARGETS.get(environment)
    if environment == "prod" and target_name == _LOCAL_CANARY_TARGETS["prod"]:
        local_target = _LOCAL_CANARY_TARGETS["prod"]
    # prod 只有显式 prod-sim 才能使用本地受控 canary 凭据；prod-hosted 保持
    # hosted bearer-token 路径，绝不能降级为本地签发令牌。
    use_local_target = local_target is not None and (
        environment != "prod" or target_name == _LOCAL_CANARY_TARGETS["prod"]
    )
    if use_local_target:
        return open_local_acceptance_session(
            base_url,
            environment=environment,
            target_name=local_target,
            resolve_host=resolve_host,
        )
    return _hosted_session(hosted_token_env, "reporter")


def media_viewer_session(
    *,
    environment: str,
    base_url: str,
    resolve_host: str,
    target_name: str,
    subject: str,
) -> LocalAcceptanceSession:
    """创建与发布者隔离的本地 viewer，用真实 Post 可见性验证原图授权。"""

    local_target = LOCAL_TARGETS.get(environment)
    if environment == "prod" and target_name == _LOCAL_CANARY_TARGETS["prod"]:
        local_target = _LOCAL_CANARY_TARGETS["prod"]
    if local_target is None:
        raise ProbeFailure(
            "unsafe_mode",
            "media viewer session is only available to local lifecycle targets",
        )
    return open_local_acceptance_session(
        base_url,
        environment=environment,
        target_name=local_target,
        subject=subject,
        resolve_host=resolve_host,
    )


def moderation_operator_session(
    *,
    environment: str,
    base_url: str,
    resolve_host: str,
    target_name: str,
) -> LocalAcceptanceSession:
    """签发仅能审核 Post 的本地 operator，用于走完真实人工审核状态机。"""

    local_target = LOCAL_TARGETS.get(environment)
    if environment == "prod" and target_name == _LOCAL_CANARY_TARGETS["prod"]:
        local_target = _LOCAL_CANARY_TARGETS["prod"]
    if local_target is None:
        raise ProbeFailure(
            "unsafe_mode",
            "moderation operator session is only available to local lifecycle targets",
        )
    return open_local_acceptance_session(
        base_url,
        environment=environment,
        target_name=local_target,
        profile="content-moderation-operator",
        subject="fixture_content_moderation_operator",
        resolve_host=resolve_host,
    )


def operator_session(
    *,
    environment: str,
    base_url: str,
    resolve_host: str,
    hosted_token_env: str,
) -> LocalAcceptanceSession:
    if environment in LOCAL_TARGETS:
        return open_local_acceptance_session(
            base_url,
            environment=environment,
            target_name=LOCAL_TARGETS[environment],
            profile="content-report-operator",
            subject="fixture_content_report_operator",
            resolve_host=resolve_host,
        )
    return _hosted_session(hosted_token_env, "report-operator")


def _hosted_session(token_env: str, actor: str) -> LocalAcceptanceSession:
    token = os.environ.get(token_env, "").strip()
    if not token:
        raise ProbeFailure(
            "auth_missing",
            f"{actor} probe requires bearer token in environment variable {token_env}",
        )
    return LocalAcceptanceSession(
        owner_id=f"hosted-{actor}",
        persona_id=f"hosted-{actor}",
        access_token=token,
    )


@contextlib.contextmanager
def _temporary_host_resolution(url: str, resolve_host: str):
    expected_host = urllib.parse.urlparse(url).hostname or ""
    if not resolve_host or not expected_host:
        yield
        return
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host: str | bytes | None, *args: Any, **kwargs: Any) -> Any:
        if host == expected_host:
            return original_getaddrinfo(resolve_host, *args, **kwargs)
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


def _open_direct(request: urllib.request.Request, *, timeout: int):
    """直连受控环境，避免开发机代理绕过本地 target host 解析。"""

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
    )
    return opener.open(request, timeout=timeout)


class ProbeClient:
    def __init__(
        self,
        base_url: str,
        resolve_host: str,
        session: LocalAcceptanceSession,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.resolve_host = resolve_host
        self.session = session

    def request(
        self,
        method: str,
        path: str,
        *,
        operation_id: str,
        expected_statuses: frozenset[int] = frozenset({200}),
        allow_non_json_statuses: frozenset[int] = frozenset(),
        body: dict[str, Any] | None = None,
        idempotency_key: str = "",
    ) -> tuple[int, dict[str, Any] | None]:
        payload = (
            json.dumps(body, ensure_ascii=False).encode("utf-8")
            if body is not None
            else None
        )
        headers = {
            "Accept": "application/json",
            "Authorization": self.session.authorization_header(),
            "X-Client-Operation-Id": operation_id,
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        request = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
            method=method,
        )
        raw = b""
        try:
            with _temporary_host_resolution(url, self.resolve_host):
                with _open_direct(request, timeout=15) as response:
                    status = int(response.status)
                    raw = response.read()
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read() if exc.fp else b""
        except urllib.error.URLError as exc:
            raise ProbeFailure(
                "gateway_unreachable",
                f"{method} {path} is unreachable",
            ) from exc
        if status not in expected_statuses:
            category = "auth_failed" if status in {401, 403} else "http_error"
            raise ProbeFailure(
                category,
                f"{method} {path} returned HTTP {status}",
            )
        if not raw.strip():
            return status, None
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if status in allow_non_json_statuses:
                return status, None
            raise ProbeFailure(
                "contract_mismatch",
                f"{method} {path} returned non-JSON content",
            ) from exc
        if not isinstance(decoded, dict):
            raise ProbeFailure(
                "contract_mismatch",
                f"{method} {path} returned a non-object payload",
            )
        return status, decoded


def put_presigned_object(
    *,
    upload_url: str,
    payload: bytes,
    content_type: str,
    sha256_digest: str,
    resolve_host: str,
) -> None:
    """经服务端签发的 URL 上传二进制对象，不附带业务 Bearer 凭据。"""

    digest = sha256_digest.removeprefix("sha256:").strip().lower()
    try:
        checksum = base64.b64encode(bytes.fromhex(digest)).decode("ascii")
    except ValueError as exc:
        raise ProbeFailure("invalid_probe_input", "invalid SHA-256 digest") from exc
    request = urllib.request.Request(
        upload_url,
        data=payload,
        headers={
            "Content-Type": content_type,
            "X-Amz-Checksum-Sha256": checksum,
            "X-Amz-Meta-Sha256": f"sha256:{digest}",
        },
        method="PUT",
    )
    try:
        with _temporary_host_resolution(upload_url, resolve_host):
            with _open_direct(request, timeout=30) as response:
                if int(response.status) not in {200, 201, 204}:
                    raise ProbeFailure(
                        "object_upload_failed",
                        f"presigned PUT returned HTTP {response.status}",
                    )
    except urllib.error.HTTPError as exc:
        error_code = _object_storage_error_code(exc.read() if exc.fp else b"")
        parsed = urllib.parse.urlparse(upload_url)
        endpoint = (
            f"{parsed.scheme}://{parsed.hostname or '<missing-host>'}"
            f"{f':{parsed.port}' if parsed.port else ''}"
        )
        raise ProbeFailure(
            "object_upload_failed",
            "presigned PUT returned "
            f"HTTP {exc.code}{f' ({error_code})' if error_code else ''}"
            f" at {endpoint}",
        ) from exc
    except urllib.error.URLError as exc:
        raise ProbeFailure(
            "object_storage_unreachable",
            "presigned object storage endpoint is unreachable",
        ) from exc


def _object_storage_error_code(body: bytes) -> str:
    """仅提取 S3 XML 的机器码，避免把 presign URL 或响应全文写入报告。"""
    if not body:
        return ""
    try:
        root = xml.fromstring(body)
    except xml.ParseError:
        return ""
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "Code":
            return (element.text or "").strip()
    return ""
