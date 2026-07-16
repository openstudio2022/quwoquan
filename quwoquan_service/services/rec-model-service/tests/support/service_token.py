"""Explicit service-identity composition for recommendation API tests."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

from fastapi.testclient import TestClient


TEST_SECRET = "recommendation-test-secret-0123456789abcdef"
TEST_ISSUER = "quwoquan-test"
TEST_AUDIENCE = "quwoquan-services"
TEST_VERSION = 1


def configure_test_auth_environment() -> None:
    os.environ["AUTH_JWT_SECRET"] = TEST_SECRET
    os.environ["AUTH_JWT_ISSUER"] = TEST_ISSUER
    os.environ["AUTH_JWT_AUDIENCE"] = TEST_AUDIENCE
    os.environ["AUTH_JWT_TOKEN_VERSION"] = str(TEST_VERSION)


def _segment(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def service_token(*, scopes: list[str] | None = None) -> str:
    now = int(time.time())
    header = _segment({"alg": "HS256", "typ": "JWT"})
    payload = _segment(
        {
            "iss": TEST_ISSUER,
            "aud": TEST_AUDIENCE,
            "tkn": "access",
            "sub": "service:content-service",
            "ver": TEST_VERSION,
            "scope": " ".join(scopes or ["recommendation.model.score"]),
            "roles": ["service"],
            "jti": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + 300,
        }
    )
    signature = hmac.new(
        TEST_SECRET.encode("utf-8"),
        f"{header}.{payload}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{header}.{payload}.{encoded_signature}"


class ServiceAuthorizedTestClient(TestClient):
    def request(self, method: str, url: str, **kwargs: Any):  # type: ignore[override]
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Authorization", f"Bearer {service_token()}")
        return super().request(method, url, headers=headers, **kwargs)
