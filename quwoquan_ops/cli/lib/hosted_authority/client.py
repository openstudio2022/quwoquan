"""Fail-closed stdlib HTTP client for hosted human authority receipts."""
from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .wire import HostedAuthorityWire

EXTERNAL_BLOCKER_CODE = "GATE_BLOCK[HOSTED_AUTHORITY_EXTERNAL_DEPENDENCY]"
PROTOCOL_BLOCKER_CODE = "GATE_BLOCK[HOSTED_AUTHORITY_EXTERNAL_DEPENDENCY/PROTOCOL_UNAVAILABLE]"
UNKNOWN_OUTCOME_CODE = "GATE_BLOCK[HOSTED_AUTHORITY_EXTERNAL_DEPENDENCY/COMMAND_OUTCOME_UNKNOWN]"
PROVIDER_KIND = "hosted-human-authority"
SIGNATURE_ALGORITHM = "ed25519"
_MAX_BODY_BYTES = 1024 * 1024
_STRONG_ETAG = re.compile(r'^"[^"\x00-\x1f]+"$')


class HostedAuthorityError(RuntimeError):
    """Typed hosted-authority failure; callers must not retry unknown outcomes."""

    def __init__(self, code: str, detail: str, *, retry_allowed: bool = False) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.retry_allowed = retry_allowed

    def as_dict(self) -> dict[str, object]:
        return {
            "result": "typed_blocker",
            "code": self.code,
            "terminal": "blocked",
            "retry_allowed": self.retry_allowed,
            "detail": self.detail,
        }


class ExternalDependencyBlocker(HostedAuthorityError):
    def __init__(self, detail: str) -> None:
        super().__init__(EXTERNAL_BLOCKER_CODE, detail, retry_allowed=False)


class ProtocolUnavailableBlocker(HostedAuthorityError):
    def __init__(self, detail: str) -> None:
        super().__init__(PROTOCOL_BLOCKER_CODE, detail, retry_allowed=False)


class CommandOutcomeUnknown(HostedAuthorityError):
    def __init__(self, *, decision_id: str, idempotency_key: str) -> None:
        super().__init__(
            UNKNOWN_OUTCOME_CODE,
            "mutation outcome is unknown; do not retry the mutation; reconcile by exact receipt readback "
            f"with decisionId={decision_id} and the same idempotency key={idempotency_key}",
            retry_allowed=False,
        )


class AuthorityAbsent(HostedAuthorityError):
    def __init__(self, decision_id: str) -> None:
        super().__init__("HOSTED_AUTHORITY.RECEIPT_ABSENT", decision_id)


@dataclass(frozen=True, slots=True)
class SignatureEnvelope:
    algorithm: str
    key_id: str
    signature_b64: str
    issuer: str
    decision_id: str
    version: str
    provider_version: str
    provider_commit: str
    contract_version: str
    chain_commit: str
    transport_tls: bool

    @property
    def provider_receipt_ref(self) -> str:
        return self.decision_id


@dataclass(frozen=True, slots=True)
class HostedAuthorityResponse:
    exact_body: bytes
    envelope: SignatureEnvelope
    status_code: int

    @property
    def body_sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self.exact_body).hexdigest()


@dataclass(frozen=True, slots=True)
class HostedAuthorityConfig:
    base_url: str
    expected_issuer: str
    wire: HostedAuthorityWire
    timeout_seconds: float = 10.0
    explicit_release_policy: bool = False
    allow_insecure_http_for_tests: bool = False

    def normalized_base_url(self) -> str:
        parsed = urlsplit(self.base_url.strip())
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ExternalDependencyBlocker("hosted authority base URL contains forbidden components")
        if not parsed.hostname:
            raise ExternalDependencyBlocker("hosted authority base URL is missing a host")
        if parsed.scheme == "https":
            pass
        elif not (
            self.allow_insecure_http_for_tests
            and parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        ):
            raise ExternalDependencyBlocker("hosted authority base URL must use HTTPS")
        issuer = urlsplit(self.expected_issuer.strip())
        if (
            issuer.scheme != "https"
            or not issuer.hostname
            or issuer.username
            or issuer.password
            or issuer.query
            or issuer.fragment
            or issuer.path not in {"", "/"}
        ):
            raise ExternalDependencyBlocker("hosted authority expected issuer must be an exact HTTPS origin")
        path = parsed.path.rstrip("/")
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


TokenProvider = Callable[[], str]
UrlOpen = Callable[..., object]


class HostedAuthorityHttpClient:
    """One-attempt HTTP adapter. It never self-signs, downgrades, or retries."""

    def __init__(
        self,
        config: HostedAuthorityConfig,
        *,
        token_provider: TokenProvider,
        opener: UrlOpen = urlopen,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.config = config
        self._base_url = config.normalized_base_url()
        self._token_provider = token_provider
        self._opener = opener
        if ssl_context is not None and urlsplit(self._base_url).scheme != "https":
            raise ExternalDependencyBlocker("custom TLS context requires an HTTPS base URL")
        self._ssl_context = ssl_context or ssl.create_default_context()

    def query(self, decision_id: str) -> HostedAuthorityResponse:
        template = self.config.wire.query_path_template
        if template is None:
            raise ProtocolUnavailableBlocker(
                "canonical operations.yaml does not declare ReadHumanAuthorizationReceipt exact-byte GET"
            )
        return self._request("GET", self._path(template, decision_id), decision_id=decision_id)

    def reconcile(self, decision_id: str, *, idempotency_key: str) -> HostedAuthorityResponse:
        if not idempotency_key.strip():
            raise HostedAuthorityError(
                "HOSTED_AUTHORITY.REQUEST_INVALID", "reconcile idempotency_key is required"
            )
        return self.query(decision_id)

    def consume(
        self,
        decision_id: str,
        *,
        expected_version: str,
        idempotency_key: str,
        fingerprint: str,
        scope: Mapping[str, str],
        action: str,
        command_digest: str,
    ) -> HostedAuthorityResponse:
        values = {"fingerprint": fingerprint, "scope": dict(scope), "action": action, "commandDigest": command_digest}
        if not fingerprint.strip() or not action.strip() or not command_digest.strip() or not scope:
            raise HostedAuthorityError(
                "HOSTED_AUTHORITY.COMMAND_INVALID", "consume fingerprint, scope, action and command digest are required"
            )
        return self._command(
            self.config.wire.consume_path_template,
            decision_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            body=values,
        )

    def revoke(
        self,
        decision_id: str,
        *,
        expected_version: str,
        idempotency_key: str,
        reason: str,
    ) -> HostedAuthorityResponse:
        if not reason.strip():
            raise HostedAuthorityError("HOSTED_AUTHORITY.COMMAND_INVALID", "revoke reason is required")
        return self._command(
            self.config.wire.revoke_path_template,
            decision_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            body={"reason": reason},
        )

    def _command(
        self,
        template: str,
        decision_id: str,
        *,
        expected_version: str,
        idempotency_key: str,
        body: Mapping[str, object],
    ) -> HostedAuthorityResponse:
        if _STRONG_ETAG.fullmatch(expected_version.strip()) is None or not idempotency_key.strip():
            raise HostedAuthorityError(
                "HOSTED_AUTHORITY.COMMAND_INVALID",
                "strong If-Match expected_version and idempotency_key are required",
            )
        exact_body = json.dumps(
            dict(body), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return self._request(
            "POST",
            self._path(template, decision_id),
            decision_id=decision_id,
            body=exact_body,
            extra_headers={"If-Match": expected_version, "Idempotency-Key": idempotency_key},
            mutation_idempotency_key=idempotency_key,
        )

    def _path(self, template: str, decision_id: str) -> str:
        if not decision_id.strip():
            raise HostedAuthorityError("HOSTED_AUTHORITY.REQUEST_INVALID", "decisionId is required")
        try:
            path = template.format(decisionId=quote(decision_id, safe=""))
        except (KeyError, ValueError) as error:
            raise ProtocolUnavailableBlocker("canonical authority route template is invalid") from error
        if not path.startswith("/") or "?" in path or "#" in path or "{" in path or "}" in path:
            raise HostedAuthorityError("HOSTED_AUTHORITY.REQUEST_INVALID", "authority path is invalid")
        return path

    def _request(
        self,
        method: str,
        path: str,
        *,
        decision_id: str,
        body: bytes | None = None,
        extra_headers: Mapping[str, str] | None = None,
        mutation_idempotency_key: str | None = None,
    ) -> HostedAuthorityResponse:
        try:
            token = self._token_provider().strip()
        except Exception as error:
            raise ExternalDependencyBlocker("hosted authority OIDC token provider failed") from error
        if not token:
            raise ExternalDependencyBlocker("hosted authority OIDC token is missing")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "quwoquan-hosted-authority-adapter/1",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra_headers or {})
        request = Request(self._base_url + path, data=body, headers=headers, method=method)
        kwargs: dict[str, object] = {"timeout": self.config.timeout_seconds}
        if request.full_url.startswith("https://"):
            kwargs["context"] = self._ssl_context
        try:
            with self._opener(request, **kwargs) as response:
                status = int(getattr(response, "status", 0))
                exact_body = response.read(_MAX_BODY_BYTES + 1)
                response_headers = response.headers
        except HTTPError as error:
            if error.code == 404 and method == "GET":
                raise AuthorityAbsent(decision_id) from error
            if error.code in {409, 412}:
                raise HostedAuthorityError(
                    "HOSTED_AUTHORITY.CAS_CONFLICT", f"HTTP {error.code}", retry_allowed=False
                ) from error
            if mutation_idempotency_key is not None and error.code >= 500:
                raise CommandOutcomeUnknown(
                    decision_id=decision_id, idempotency_key=mutation_idempotency_key
                ) from error
            raise HostedAuthorityError(
                "HOSTED_AUTHORITY.HTTP_FAILED", f"HTTP {error.code}", retry_allowed=False
            ) from error
        except (socket.timeout, TimeoutError) as error:
            if mutation_idempotency_key is not None:
                raise CommandOutcomeUnknown(
                    decision_id=decision_id, idempotency_key=mutation_idempotency_key
                ) from error
            raise HostedAuthorityError("HOSTED_AUTHORITY.TIMEOUT", "request timed out") from error
        except URLError as error:
            if mutation_idempotency_key is not None:
                raise CommandOutcomeUnknown(
                    decision_id=decision_id, idempotency_key=mutation_idempotency_key
                ) from error
            reason = error.reason
            code = (
                "HOSTED_AUTHORITY.TIMEOUT"
                if isinstance(reason, (socket.timeout, TimeoutError))
                else "HOSTED_AUTHORITY.DISCONNECTED"
            )
            raise HostedAuthorityError(code, "hosted authority is unreachable") from error
        except OSError as error:
            if mutation_idempotency_key is not None:
                raise CommandOutcomeUnknown(
                    decision_id=decision_id, idempotency_key=mutation_idempotency_key
                ) from error
            raise HostedAuthorityError(
                "HOSTED_AUTHORITY.DISCONNECTED", "hosted authority is unreachable"
            ) from error
        if status != 200:
            if mutation_idempotency_key is not None and status >= 500:
                raise CommandOutcomeUnknown(
                    decision_id=decision_id, idempotency_key=mutation_idempotency_key
                )
            raise HostedAuthorityError("HOSTED_AUTHORITY.HTTP_FAILED", f"unexpected HTTP {status}")
        if len(exact_body) > _MAX_BODY_BYTES:
            raise HostedAuthorityError("HOSTED_AUTHORITY.RESPONSE_INVALID", "response body exceeds limit")
        try:
            envelope = self._envelope(
                response_headers,
                tls=request.full_url.startswith("https://"),
                expected_decision_id=decision_id,
            )
        except HostedAuthorityError as error:
            if mutation_idempotency_key is not None:
                raise CommandOutcomeUnknown(
                    decision_id=decision_id, idempotency_key=mutation_idempotency_key
                ) from error
            raise
        try:
            wrapper = json.loads(exact_body)
        except (UnicodeError, json.JSONDecodeError) as error:
            if mutation_idempotency_key is not None:
                raise CommandOutcomeUnknown(decision_id=decision_id, idempotency_key=mutation_idempotency_key) from error
            raise HostedAuthorityError("HOSTED_AUTHORITY.RESPONSE_INVALID", "wrapper JSON is invalid") from error
        if not isinstance(wrapper, dict) or wrapper.get("decisionId") != decision_id or wrapper.get("etag") != envelope.version:
            if mutation_idempotency_key is not None:
                raise CommandOutcomeUnknown(decision_id=decision_id, idempotency_key=mutation_idempotency_key)
            raise HostedAuthorityError("HOSTED_AUTHORITY.RESPONSE_INVALID", "wrapper identity does not match HTTP envelope")
        return HostedAuthorityResponse(exact_body=exact_body, status_code=status, envelope=envelope)

    def _envelope(
        self, headers: Mapping[str, str], *, tls: bool, expected_decision_id: str
    ) -> SignatureEnvelope:
        names = {
            "algorithm": "X-QWQ-Authority-Signature-Algorithm",
            "key_id": "X-QWQ-Authority-Key-Id",
            "signature_b64": "X-QWQ-Authority-Signature",
            "issuer": "X-QWQ-Authority-Issuer",
            "provider_version": "X-QWQ-Authority-Provider-Version",
            "provider_commit": "X-QWQ-Authority-Provider-Commit",
            "contract_version": "X-QWQ-Authority-Contract-Version",
            "chain_commit": "X-QWQ-Authority-Chain-Commit",
            "version": "ETag",
        }
        values = {field: str(headers.get(name, "")).strip() for field, name in names.items()}
        if any(not value or any(ord(character) < 0x20 for character in value) for value in values.values()):
            raise ProtocolUnavailableBlocker(
                "response is not the detached exact-byte authority protocol; ordinary JSON is unauthenticated"
            )
        if values["algorithm"] != SIGNATURE_ALGORITHM:
            raise HostedAuthorityError(
                "HOSTED_AUTHORITY.ENVELOPE_INVALID", "signature algorithm is not Ed25519"
            )
        if _STRONG_ETAG.fullmatch(values["version"]) is None:
            raise ProtocolUnavailableBlocker("authority response does not expose one strong ETag version")
        if values["issuer"] != self.config.expected_issuer:
            raise HostedAuthorityError("HOSTED_AUTHORITY.ENVELOPE_INVALID", "issuer header mismatch")
        return SignatureEnvelope(
            decision_id=expected_decision_id,
            transport_tls=tls,
            **values,
        )
