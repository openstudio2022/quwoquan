from __future__ import annotations

import contextlib
import json
import os
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
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
    prepare_local_environment_auth,
)


LOCAL_TARGETS = {"beta": "beta-local", "gamma": "gamma-local"}


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
) -> LocalAcceptanceSession:
    if environment in LOCAL_TARGETS:
        return open_local_acceptance_session(
            base_url,
            environment=environment,
            target_name=LOCAL_TARGETS[environment],
            resolve_host=resolve_host,
        )
    return _hosted_session(hosted_token_env, "reporter")


def operator_session(
    *,
    environment: str,
    hosted_token_env: str,
) -> LocalAcceptanceSession:
    if environment in LOCAL_TARGETS:
        return _local_operator_session(
            environment,
            LOCAL_TARGETS[environment],
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


def _local_operator_session(
    environment: str,
    target_name: str,
) -> LocalAcceptanceSession:
    auth = prepare_local_environment_auth(environment, target_name)
    actor_id = "fixture_content_report_operator"
    process_env = os.environ.copy()
    process_env.update(auth.environment)
    process_env.update(
        {
            "APP_ENV": environment,
            "QWQ_LOCAL_ACCEPTANCE_TARGET": target_name,
            "QWQ_ACCEPTANCE_OWNER_ID": actor_id,
            "QWQ_ACCEPTANCE_PERSONA_ID": actor_id,
            "QWQ_ACCEPTANCE_PROFILE": "content-report-operator",
        }
    )
    result = subprocess.run(
        ["go", "run", "./services/user-service/cmd/acceptance-session"],
        cwd=REPO_ROOT / "quwoquan_service",
        env=process_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeFailure(
            "operator_auth_failed",
            "local report operator session issuer failed",
        )
    try:
        payload = json.loads(result.stdout)
        token = str(payload["accessToken"]).strip()
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ProbeFailure(
            "operator_auth_failed",
            "local report operator session issuer returned invalid JSON",
        ) from exc
    if not token:
        raise ProbeFailure(
            "operator_auth_failed",
            "local report operator session issuer returned an empty token",
        )
    return LocalAcceptanceSession(
        owner_id=actor_id,
        persona_id=actor_id,
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
                with urllib.request.urlopen(
                    request,
                    timeout=15,
                    context=ssl._create_unverified_context(),
                ) as response:
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
