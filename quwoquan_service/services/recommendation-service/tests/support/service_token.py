"""Explicit service-identity composition for recommendation API tests."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
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
    config_version = "sha256:" + hashlib.sha256(
        b"recommendation-service:local-contract-config"
    ).hexdigest()
    repo_root = Path(__file__).resolve().parents[5]
    config_root = (
        repo_root
        / ".qwq_output"
        / "env"
        / "repo"
        / "local"
        / "tests"
        / "recommendation-runtime-config"
    )
    config_root.mkdir(parents=True, exist_ok=True)
    (config_root / "recommendation-service.yaml").write_text(
        json.dumps(
            {
                "config": {"version": config_version},
                "service": {"http": {"addr": ":8080"}},
                "redis": {
                    "general": {
                        "mode": "standalone",
                        "addr": "127.0.0.1:6379",
                        "db": 0,
                        "tls": False,
                        "pool": {},
                    },
                    "rec": {
                        "mode": "standalone",
                        "addr": "127.0.0.1:6379",
                        "db": 0,
                        "tls": False,
                        "pool": {},
                    },
                },
                "ranked_window": {
                    "quota_shard_count": 256,
                    "maximum_live_records_per_shard": 128,
                    "maximum_live_bytes_per_shard": 134217728,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.environ["APP_ENV"] = "alpha"
    os.environ["SERVICE_NAME"] = "recommendation-service"
    os.environ["CONFIG_ROOT"] = str(config_root)
    os.environ["CONFIG_VERSION"] = config_version
    os.environ["IMAGE_VERSION"] = "recommendation-local-contract"


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
