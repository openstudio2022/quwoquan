"""Typed public API adapter shared by environment release verification."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import ssl
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from core.runtime_policy import active_runtime_policy


class PublicApiClientError(ValueError):
    """A public environment API request could not produce a JSON response."""


def _public_url_evidence(url: str) -> str:
    """Return bounded origin/query-free evidence for a public media URL."""

    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        host_class = "dns" if hostname else "missing"
    else:
        host_class = "ip"
    path_hash = hashlib.sha256(parsed.path.encode("utf-8")).hexdigest()
    return f"hostClass={host_class},pathHash=sha256:{path_hash}"


@dataclass(frozen=True)
class PublicApiRequestIdentity:
    """One logical operation identity shared by its bounded physical attempts."""

    page_id: str
    request_id: str
    trace_id: str

    def __post_init__(self) -> None:
        for label, value in (
            ("pageId", self.page_id),
            ("requestId", self.request_id),
            ("traceId", self.trace_id),
        ):
            if (
                not value.strip()
                or len(value) > 256
                or not all(
                    character.isascii()
                    and (character.isalnum() or character in "._:-")
                    for character in value
                )
            ):
                raise PublicApiClientError(
                    f"public API logical {label} is invalid"
                )


@dataclass(frozen=True)
class PublicApiOperationEvidence:
    path: str
    page_id: str
    status: int
    request_id: str
    trace_id: str
    started_at: str
    ended_at: str
    duration_ms: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "pageId": self.page_id,
            "status": self.status,
            "requestId": self.request_id,
            "traceId": self.trace_id,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "durationMs": self.duration_ms,
        }


@dataclass(frozen=True)
class PublicApiResponse:
    status: int
    payload: Mapping[str, Any]
    operation: PublicApiOperationEvidence | None = None
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class PublicGuestSession:
    access_token: str = field(repr=False)
    guest_actor_hash: str
    device_actor_id: str = field(repr=False)
    login_operation: PublicApiOperationEvidence


@dataclass(frozen=True)
class PublicBinaryResponse:
    status: int
    content_type: str
    content_range: str
    body: bytes
    content_length: int = 0
    etag: str = ""


@dataclass(frozen=True)
class PublicApiClient:
    base_url: str
    bearer_token: str = field(default="", repr=False)
    device_actor_id: str = field(default="", repr=False)
    session_id: str = field(
        default_factory=lambda: f"readiness-{uuid.uuid4().hex}",
        repr=False,
    )
    platform: str = "android"
    app_version: str = "release-readiness"
    # Local-managed environments (alpha/beta/gamma-local) present a private CA.
    # Production public CAs leave this empty and use the process trust store.
    ssl_cafile: str = ""

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise PublicApiClientError("public API base URL must be HTTPS")
        if not self.session_id.strip():
            raise PublicApiClientError("public API sessionId must not be empty")
        if not self.platform.strip() or not self.app_version.strip():
            raise PublicApiClientError("public API client platform/appVersion must not be empty")
        if self.ssl_cafile and not Path(self.ssl_cafile).is_file():
            raise PublicApiClientError(
                f"public API ssl_cafile is missing: {self.ssl_cafile}"
            )

    def _opener(self):
        handlers: list[Any] = [ProxyHandler({})]
        if self.ssl_cafile:
            context = ssl.create_default_context(cafile=self.ssl_cafile)
            handlers.append(HTTPSHandler(context=context))
        return build_opener(*handlers)

    @staticmethod
    def _utc_now() -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def new_request_identity(self, *, page_id: str) -> PublicApiRequestIdentity:
        """Mint one logical identity; callers may reuse it for bounded retries."""
        if not page_id.strip():
            raise PublicApiClientError("public API pageId must not be empty")
        nonce = uuid.uuid4().hex
        return PublicApiRequestIdentity(
            page_id=page_id,
            request_id=f"DATA.{page_id}.{nonce}",
            trace_id=f"DATA.{self.session_id}.{page_id}.{nonce}",
        )

    def _request_headers(
        self,
        *,
        page_id: str,
        started_at: str,
        request_id: str,
        trace_id: str,
        content_type: str = "",
        session_header_name: str = "X-Client-Session-Id",
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        if not page_id.strip():
            raise PublicApiClientError("public API pageId must not be empty")
        if session_header_name not in {
            "X-Client-Session-Id",
            "X-Session-Id",
        }:
            raise PublicApiClientError("public API session header name is invalid")
        reserved_headers = {
            "x-client-session-id",
            "x-session-id",
            "x-request-id",
            "x-trace-id",
        }
        if extra_headers and any(
            key.lower() in reserved_headers for key in extra_headers
        ):
            raise PublicApiClientError(
                "public API identity headers must use typed request options"
            )
        headers = {
            "Accept": "application/json",
            "X-Client-Page-Id": page_id,
            session_header_name: self.session_id,
            "X-Client-Sent-At": started_at,
            "X-Client-Device-Platform": self.platform,
            "X-Client-App-Version": self.app_version,
            "X-Trace-Id": trace_id,
            "X-Request-Id": request_id,
        }
        if self.device_actor_id:
            headers["X-Client-Device-Actor-Id"] = self.device_actor_id
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if content_type:
            headers["Content-Type"] = content_type
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        page_id: str,
        query: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        session_header_name: str = "X-Client-Session-Id",
        extra_headers: Mapping[str, str] | None = None,
        request_identity: PublicApiRequestIdentity | None = None,
        timeout_seconds: float | None = None,
    ) -> PublicApiResponse:
        normalized_path = f"/{path.lstrip('/')}"
        url = f"{self.base_url.rstrip('/')}{normalized_path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        encoded_body = None
        if body is not None:
            encoded_body = json.dumps(
                dict(body),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        identity = request_identity or self.new_request_identity(page_id=page_id)
        if identity.page_id != page_id:
            raise PublicApiClientError(
                "public API logical request identity pageId mismatch"
            )
        request_id = identity.request_id
        trace_id = identity.trace_id
        runtime_timeout_seconds = float(
            active_runtime_policy().api_request_timeout_seconds
        )
        try:
            effective_timeout_seconds = (
                runtime_timeout_seconds
                if timeout_seconds is None
                else float(timeout_seconds)
            )
        except (TypeError, ValueError) as exc:
            raise PublicApiClientError(
                "public API request timeout must be a finite number"
            ) from exc
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(effective_timeout_seconds)
            or effective_timeout_seconds <= 0
            or effective_timeout_seconds > runtime_timeout_seconds
        ):
            raise PublicApiClientError(
                "public API request timeout must be positive and within runtime budget"
            )
        started_at = self._utc_now()
        started_monotonic = time.monotonic_ns()
        request = Request(
            url,
            data=encoded_body,
            headers=self._request_headers(
                page_id=page_id,
                started_at=started_at,
                request_id=request_id,
                trace_id=trace_id,
                content_type="application/json" if body is not None else "",
                session_header_name=session_header_name,
                extra_headers=extra_headers,
            ),
            method=method,
        )
        opener = self._opener()
        try:
            with opener.open(
                request,
                timeout=effective_timeout_seconds,
            ) as response:  # noqa: S310
                status = int(response.status)
                raw = response.read()
                raw_headers = getattr(response, "headers", {}) or {}
                response_headers = {
                    str(key): str(value) for key, value in raw_headers.items()
                }
        except HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
            raw_headers = getattr(exc, "headers", {}) or {}
            response_headers = {
                str(key): str(value) for key, value in raw_headers.items()
            }
        except (URLError, OSError) as exc:
            raise PublicApiClientError(
                "public API request failed: "
                "status=transport_error canonicalErrorCode=none "
                f"requestId={request_id} traceId={trace_id} "
                "requestSummary="
                f"method={method},path={normalized_path},pageId={page_id} "
                f"cause={type(exc).__name__}"
            ) from exc
        ended_at = self._utc_now()
        duration_ms = max(0, int((time.monotonic_ns() - started_monotonic) / 1_000_000))
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PublicApiClientError(
                "public API returned invalid JSON: "
                f"status={status} canonicalErrorCode=none "
                f"requestId={request_id} traceId={trace_id} "
                "requestSummary="
                f"method={method},path={normalized_path},pageId={page_id}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise PublicApiClientError(
                "public API returned non-object JSON: "
                f"status={status} canonicalErrorCode=none "
                f"requestId={request_id} traceId={trace_id} "
                "requestSummary="
                f"method={method},path={normalized_path},pageId={page_id}"
            )
        return PublicApiResponse(
            status=status,
            payload=payload,
            operation=PublicApiOperationEvidence(
                path=normalized_path,
                page_id=page_id,
                status=status,
                request_id=request_id,
                trace_id=trace_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
            ),
            headers=response_headers,
        )

    def login_fresh_guest(self) -> PublicGuestSession:
        """Create one run-scoped anonymous actor through the canonical operation."""

        install_id = f"readiness-{uuid.uuid4().hex}"
        fingerprint = hashlib.sha256(
            f"qwq-anonymous-device-v1:{install_id}".encode("utf-8")
        ).hexdigest()
        command = {
            "installId": install_id,
            "deviceFingerprintHash": fingerprint,
            "platform": self.platform,
            "appVersion": self.app_version,
        }
        idempotency_digest = hashlib.sha256(
            json.dumps(
                command,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        response = self._request_json(
            "POST",
            "auth/login/anonymous",
            page_id="user.login.anonymous",
            body=command,
            extra_headers={"Idempotency-Key": f"login-anonymous-{idempotency_digest}"},
        )
        access_token = str(response.payload.get("accessToken") or "").strip()
        owner_id = str(response.payload.get("ownerId") or "").strip()
        active_persona = response.payload.get("activePersona")
        raw_persona_id = (
            active_persona.get("personaId")
            if isinstance(active_persona, Mapping)
            else None
        )
        persona_id = (
            raw_persona_id.strip()
            if isinstance(raw_persona_id, str)
            else ""
        )
        if (
            response.status != 200
            or not access_token
            or not owner_id
            or not isinstance(active_persona, Mapping)
            or not persona_id
            or response.payload.get("accountState") != "anonymous"
            or response.payload.get("identityOrigin") != "anonymous_device"
        ):
            raise PublicApiClientError(
                "LoginAnonymous did not return a canonical anonymous session"
            )
        guest_actor_hash = "sha256:" + hashlib.sha256(
            (
                "qwq-readiness-guest-v1:"
                f"{owner_id}:{persona_id}"
            ).encode("utf-8")
        ).hexdigest()
        device_actor_id = hashlib.sha256(
            f"qwq-device-actor-v1:{install_id}".encode("utf-8")
        ).hexdigest()[:32]
        return PublicGuestSession(
            access_token=access_token,
            guest_actor_hash=guest_actor_hash,
            device_actor_id=device_actor_id,
            login_operation=response.operation,
        )

    def for_guest(self, session: PublicGuestSession) -> "PublicApiClient":
        return replace(
            self,
            bearer_token=session.access_token,
            device_actor_id=session.device_actor_id,
        )

    def get_json(
        self,
        path: str,
        *,
        page_id: str,
        query: Mapping[str, str] | None = None,
    ) -> PublicApiResponse:
        return self._request_json("GET", path, page_id=page_id, query=query)

    def post_json(
        self,
        path: str,
        *,
        page_id: str,
        body: Mapping[str, Any],
        session_header_name: str = "X-Client-Session-Id",
        extra_headers: Mapping[str, str] | None = None,
        request_identity: PublicApiRequestIdentity | None = None,
        timeout_seconds: float | None = None,
    ) -> PublicApiResponse:
        return self._request_json(
            "POST",
            path,
            page_id=page_id,
            body=body,
            session_header_name=session_header_name,
            extra_headers=extra_headers,
            request_identity=request_identity,
            timeout_seconds=timeout_seconds,
        )

    def get_bytes(
        self,
        url: str,
        *,
        byte_range: str = "bytes=0-65535",
        max_bytes: int = 65536,
    ) -> PublicBinaryResponse:
        if not url.startswith("https://"):
            raise PublicApiClientError("public media URL must be HTTPS")
        if max_bytes <= 0:
            raise PublicApiClientError("public media max_bytes must be positive")
        headers = {"Accept": "*/*"}
        if byte_range:
            headers["Range"] = byte_range
        request = Request(
            url,
            headers=headers,
            method="GET",
        )
        opener = self._opener()
        try:
            with opener.open(
                request,
                timeout=active_runtime_policy().api_request_timeout_seconds,
            ) as response:  # noqa: S310
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise PublicApiClientError(
                        "public media GET exceeded declared byte budget: "
                        + _public_url_evidence(url)
                    )
                return PublicBinaryResponse(
                    status=int(response.status),
                    content_type=str(response.headers.get("Content-Type") or ""),
                    content_range=str(response.headers.get("Content-Range") or ""),
                    body=body,
                    content_length=int(response.headers.get("Content-Length") or 0),
                    etag=str(response.headers.get("ETag") or "").strip(),
                )
        except HTTPError as exc:
            body = exc.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise PublicApiClientError(
                    "public media GET exceeded declared byte budget: "
                    + _public_url_evidence(url)
                ) from exc
            return PublicBinaryResponse(
                status=int(exc.code),
                content_type=str(exc.headers.get("Content-Type") or ""),
                content_range=str(exc.headers.get("Content-Range") or ""),
                body=body,
                content_length=int(exc.headers.get("Content-Length") or 0),
                etag=str(exc.headers.get("ETag") or "").strip(),
            )
        except (URLError, OSError) as exc:
            raise PublicApiClientError(
                "public media GET failed: "
                f"{_public_url_evidence(url)},cause={type(exc).__name__}"
            ) from exc


__all__ = [
    "PublicApiClient",
    "PublicApiClientError",
    "PublicApiOperationEvidence",
    "PublicApiRequestIdentity",
    "PublicApiResponse",
    "PublicBinaryResponse",
    "PublicGuestSession",
]
