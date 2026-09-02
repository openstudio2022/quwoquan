"""research 消费核验凭证签发（环境 owner 侧）。

ship verify 的 research readiness 需要以受保护的白名单研究身份完成
post API 消费核验（feed/detail/search）；匿名 guest 不能复用为 research
证据。凭证 = 白名单账号 Bearer session + research attestation，均为短
TTL，只经调用方进程内存传递，绝不落盘。
"""
from __future__ import annotations

import hashlib
import os
from typing import Any

from .environment_topology import (
    ENVIRONMENT_CANONICAL_TARGET,
    get_target,
    load_environment_topology,
)
from .local_environment_auth import (
    LocalEnvironmentHTTPError,
    open_local_phone_acceptance_session,
    request_local_environment_json,
)
from .public_domain_tls import root_certificate_path

_RESEARCH_IDENTITY_SET_ID = "research-identity"
_CONSUMER_ACTOR_ROLE = "research-consumer-verification"


class ResearchConsumerCredentialError(RuntimeError):
    """research 消费凭证签发失败（fail-closed）。"""


def issue_research_consumer_credential(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """登录白名单研究账号并签发 research session，返回内存态凭证。"""
    if environment not in ENVIRONMENT_CANONICAL_TARGET:
        raise ResearchConsumerCredentialError(
            f"unsupported research credential environment: {environment}"
        )
    target_name = ENVIRONMENT_CANONICAL_TARGET[environment]
    target = get_target(load_environment_topology(), target_name)
    public_bases = target.get("publicBases") or {}
    api_base = str(public_bases.get("api") or "").strip().rstrip("/")
    if not api_base:
        raise ResearchConsumerCredentialError(
            f"{target_name} api public base is unavailable"
        )
    ca_file = root_certificate_path(target_name)
    if not ca_file.is_file() or ca_file.is_symlink():
        raise ResearchConsumerCredentialError(
            f"{target_name} root certificate is unavailable: {ca_file}"
        )
    instance_id = hashlib.sha256(
        (
            "research-consumer-credential\0"
            + environment
            + "\0"
            + release_id
            + "\0"
            + verify_run_id
        ).encode("utf-8")
    ).hexdigest()
    previous_ssl_cert_file = os.environ.get("SSL_CERT_FILE")
    os.environ["SSL_CERT_FILE"] = str(ca_file)
    try:
        actor = open_local_phone_acceptance_session(
            api_base,
            environment=environment,
            target_name=target_name,
            test_data_instance_id=instance_id,
            identity_set_id=_RESEARCH_IDENTITY_SET_ID,
            actor_role=_CONSUMER_ACTOR_ROLE,
            actor_index=0,
            timeout_seconds=max(timeout_seconds, 30.0),
        )
    finally:
        if previous_ssl_cert_file is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = previous_ssl_cert_file
    try:
        issuance = request_local_environment_json(
            api_base,
            path="/auth/research/session",
            session=actor.session,
            method="POST",
            body=None,
            headers={},
            timeout_seconds=timeout_seconds,
        )
    except LocalEnvironmentHTTPError as exc:
        raise ResearchConsumerCredentialError(
            f"research session issuance returned HTTP {exc.status}"
        ) from exc
    subject_hash = str((issuance or {}).get("subjectHash") or "").strip()
    attestation_token = str((issuance or {}).get("attestationId") or "").strip()
    expires_at = str((issuance or {}).get("expiresAt") or "").strip()
    if not subject_hash or not attestation_token or not expires_at:
        raise ResearchConsumerCredentialError(
            "research session issuance response lacks subjectHash/attestationId/expiresAt"
        )
    try:
        readback = request_local_environment_json(
            api_base,
            path="/auth/research/session/attestation",
            session=actor.session,
            method="GET",
            body=None,
            headers={
                "X-Research-Identity-Attestation": attestation_token,
            },
            timeout_seconds=timeout_seconds,
        )
    except LocalEnvironmentHTTPError as exc:
        raise ResearchConsumerCredentialError(
            f"research session attestation readback returned HTTP {exc.status}"
        ) from exc
    expected_readback = {
        "subjectHash": subject_hash,
        "attestationId": attestation_token,
        "expiresAt": expires_at,
    }
    if not isinstance(readback, dict) or set(readback) != set(expected_readback):
        raise ResearchConsumerCredentialError(
            "research session attestation readback field set drifted"
        )
    if any(readback.get(field) != value for field, value in expected_readback.items()):
        raise ResearchConsumerCredentialError(
            "research session attestation readback drifted from issuance"
        )
    return {
        "apiBaseUrl": api_base,
        "sslCaFile": str(ca_file),
        "bearerToken": actor.session.access_token,
        "attestationToken": attestation_token,
        "subjectHash": subject_hash,
        "expiresAt": expires_at,
    }


__all__ = [
    "ResearchConsumerCredentialError",
    "issue_research_consumer_credential",
]
