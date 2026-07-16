"""Fail-closed HS256 service-token verification for scoring operations."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any


UNAUTHORIZED_CODE = "RECOMMENDATION.USER.unauthorized"
FORBIDDEN_CODE = "RECOMMENDATION.USER.forbidden"
REQUIRED_SCOPE = "recommendation.model.score"
MAX_ACCESS_TOKEN_TTL_SECONDS = 30 * 60
CLOCK_SKEW_SECONDS = 30


@dataclass(frozen=True)
class AuthorizationFailure(Exception):
    status_code: int
    code: str


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required recommendation auth config: {name}")
    return value


def _decode_segment(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("JWT segment must be an object")
    return payload


class ServiceTokenVerifier:
    def __init__(self, *, secret: str, issuer: str, audience: str, token_version: int):
        if len(secret.encode("utf-8")) < 32:
            raise RuntimeError("AUTH_JWT_SECRET must contain at least 32 bytes")
        if not issuer or not audience or token_version <= 0:
            raise RuntimeError("recommendation auth issuer, audience and token version are required")
        self._secret = secret.encode("utf-8")
        self._issuer = issuer
        self._audience = audience
        self._token_version = token_version

    @classmethod
    def from_env(cls) -> "ServiceTokenVerifier":
        raw_version = _required_env("AUTH_JWT_TOKEN_VERSION")
        try:
            token_version = int(raw_version)
        except ValueError as exc:
            raise RuntimeError("AUTH_JWT_TOKEN_VERSION must be a positive integer") from exc
        return cls(
            secret=_required_env("AUTH_JWT_SECRET"),
            issuer=_required_env("AUTH_JWT_ISSUER"),
            audience=_required_env("AUTH_JWT_AUDIENCE"),
            token_version=token_version,
        )

    def verify(self, authorization: str | None) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthorizationFailure(401, UNAUTHORIZED_CODE)
        token = authorization.removeprefix("Bearer ").strip()
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthorizationFailure(401, UNAUTHORIZED_CODE)
        try:
            header = _decode_segment(parts[0])
            claims = _decode_segment(parts[1])
            expected = hmac.new(
                self._secret,
                f"{parts[0]}.{parts[1]}".encode("ascii"),
                hashlib.sha256,
            ).digest()
            padded_signature = parts[2] + "=" * (-len(parts[2]) % 4)
            actual = base64.urlsafe_b64decode(padded_signature.encode("ascii"))
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeError):
            raise AuthorizationFailure(401, UNAUTHORIZED_CODE) from None
        if header != {"alg": "HS256", "typ": "JWT"} or not hmac.compare_digest(expected, actual):
            raise AuthorizationFailure(401, UNAUTHORIZED_CODE)

        now = int(time.time())
        issued_at = claims.get("iat")
        not_before = claims.get("nbf")
        expires_at = claims.get("exp")
        valid_times = all(isinstance(value, int) and value > 0 for value in (issued_at, not_before, expires_at))
        if (
            not valid_times
            or expires_at <= issued_at
            or expires_at - issued_at > MAX_ACCESS_TOKEN_TTL_SECONDS + CLOCK_SKEW_SECONDS
            or now - CLOCK_SKEW_SECONDS >= expires_at
            or not_before > now + CLOCK_SKEW_SECONDS
            or issued_at > now + CLOCK_SKEW_SECONDS
        ):
            raise AuthorizationFailure(401, UNAUTHORIZED_CODE)
        if (
            claims.get("iss") != self._issuer
            or claims.get("aud") != self._audience
            or claims.get("tkn") != "access"
            or claims.get("ver") != self._token_version
            or not str(claims.get("jti", "")).strip()
            or not str(claims.get("sub", "")).startswith("service:")
        ):
            raise AuthorizationFailure(401, UNAUTHORIZED_CODE)

        roles = claims.get("roles")
        scopes = str(claims.get("scope", "")).split()
        if not isinstance(roles, list) or "service" not in roles or REQUIRED_SCOPE not in scopes:
            raise AuthorizationFailure(403, FORBIDDEN_CODE)
        return claims
