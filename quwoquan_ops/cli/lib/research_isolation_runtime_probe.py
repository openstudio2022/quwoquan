"""Environment-owner runtime probe for one research release isolation proof.

本模块对一个本地环境（alpha-local/beta-local/gamma-local）执行 12 个真实 HTTP
探针操作，并把 create-once 的 ``research-isolation-runtime-proof.json`` 写入
canonical verify run 目录。文档语义（字段、状态码、唯一性、checksum）与
``quwoquan_data/scripts/content/release/environment/research_isolation_proof.py``
和 ``research_isolation_verification.py`` 逐点对齐：Data ship 流程只会原样冻结
本文件写出的字节，任何探针不满足预期时这里必须 fail-closed、不写文件。

HTTP 边界全部通过本模块的模块级符号进出（``request_local_environment_json`` /
``request_local_environment_public_json`` / ``fetch_media_status``），local_contract
测试用 monkeypatch 替换它们即可覆盖组装、fail-closed 与 create-once 语义。

PASS 文档的键契约、checksum、组装校验与 create-once 写入实现位于职责伴生模块
``research_isolation_proof_document``；相关符号经本模块 re-export，公开导入
路径保持不变。
"""

from __future__ import annotations

import hashlib
import os
import ssl
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit
from uuid import uuid4

from .common import ROOT, load_json_yaml
from .environment_topology import (
    ENVIRONMENT_CANONICAL_TARGET,
    get_target,
    load_environment_topology,
)
from .local_environment_auth import (
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
    open_local_phone_acceptance_session,
    request_local_environment_json,
    request_local_environment_public_json,
)
from .local_target_handoff import target_for_hostname
from .output_paths import output_root
from .public_domain_tls import root_certificate_path
from .research_isolation_proof_document import (
    _DIGEST,
    _PROBE_ENVIRONMENTS,
    PASS_DOCUMENT_KEYS,
    ResearchIsolationProbeError,
    _digest_bytes,
    _safe_segment,
    _segment_operations,
    _utc_now_iso,
    build_runtime_proof_document,
    write_runtime_proof_create_once,
)

_PAGE_ID_PREFIX = "ops.research_isolation."
_ATTESTATION_HEADER = "X-Research-Identity-Attestation"
_RESEARCH_IDENTITY_SET_ID = "research-identity"
_PROBE_ACTOR_ROLE = "research-isolation-probe"
RUNTIME_PROOF_FILE_NAME = "research-isolation-runtime-proof.json"
IDENTITY_CONTRACT_REF = (
    "quwoquan_service/services/user-service/contracts/account/"
    "account_session/operations.yaml"
)


def new_probe_identity() -> str:
    """为一个 operation 生成 requestId/traceId；测试可注入固定值。"""

    return uuid4().hex


def fetch_media_status(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = 12.0,
) -> int:
    """对一个媒体 URL 执行真实 GET 并返回 HTTP status（不解析 body）。

    使用与身份链相同的 target root certificate；只读取少量字节以确认响应
    已开始交付。media 探针只需要状态码证据，不需要完整媒体负载。
    """

    host = urlsplit(url).hostname
    if not host:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "media probe URL has no hostname",
        )
    target_name = target_for_hostname(host)
    if target_name is None:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "media probe URL is not a canonical local target",
        )
    ca_file = root_certificate_path(target_name)
    if not ca_file.is_file() or ca_file.is_symlink():
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_TRANSPORT_FAILED",
            "media probe root certificate is unavailable",
        )
    context = ssl.create_default_context(cafile=str(ca_file))
    opener = request.build_opener(
        request.ProxyHandler({}),
        request.HTTPSHandler(context=context),
    )
    req = request.Request(url, headers=dict(headers or {}), method="GET")
    try:
        with opener.open(req, timeout=max(1.0, timeout_seconds)) as response:
            response.read(1)
            return int(response.status)
    except error.HTTPError as exc:
        return int(exc.code)
    except Exception as exc:  # noqa: BLE001
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_TRANSPORT_FAILED",
            f"media probe transport failed: {type(exc).__name__}",
        ) from exc


def _perform_operation(
    *,
    segment: str,
    path: str,
    expected_statuses: frozenset[int],
    invoke: Callable[[dict[str, str]], tuple[int, Mapping[str, Any] | None]],
) -> tuple[int, Mapping[str, Any] | None, dict[str, Any]]:
    request_id = new_probe_identity()
    trace_id = new_probe_identity()
    headers = {"X-Request-Id": request_id, "X-Trace-Id": trace_id}
    started_at = _utc_now_iso()
    started_monotonic = time.monotonic()
    status, payload = invoke(headers)
    duration_ms = max(0, int((time.monotonic() - started_monotonic) * 1000))
    ended_at = _utc_now_iso()
    operation = {
        "path": path,
        "pageId": _PAGE_ID_PREFIX + segment,
        "status": int(status),
        "requestId": request_id,
        "traceId": trace_id,
        "startedAt": started_at,
        "endedAt": ended_at,
        "durationMs": duration_ms,
    }
    if status not in expected_statuses:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS",
            f"{segment} probe {path} returned HTTP {status}, "
            f"expected one of {sorted(expected_statuses)}",
        )
    return int(status), payload, operation


def _authenticated_json(
    base_url: str,
    *,
    path: str,
    session: LocalAcceptanceSession,
    method: str,
    body: Mapping[str, Any] | None,
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, Mapping[str, Any] | None]:
    try:
        payload = request_local_environment_json(
            base_url,
            path=path,
            session=session,
            method=method,
            body=dict(body) if body is not None else None,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )
        return 200, payload
    except LocalEnvironmentHTTPError as exc:
        return int(exc.status), None


def _anonymous_json(
    base_url: str,
    *,
    path: str,
    method: str,
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, Mapping[str, Any] | None]:
    try:
        payload = request_local_environment_public_json(
            base_url,
            path=path,
            method=method,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )
        return 200, payload
    except LocalEnvironmentHTTPError as exc:
        return int(exc.status), None


def _response_invalid(segment: str, reason: str) -> ResearchIsolationProbeError:
    return ResearchIsolationProbeError(
        "OPS.RESEARCH.PROBE_RESPONSE_INVALID",
        f"{segment} probe response is invalid: {reason}",
    )


def _required_string(
    payload: Mapping[str, Any] | None,
    field: str,
    *,
    segment: str,
) -> str:
    value = (payload or {}).get(field)
    if not isinstance(value, str) or not value.strip():
        raise _response_invalid(segment, f"{field} must be a non-empty string")
    return value.strip()


def _required_digest(
    payload: Mapping[str, Any] | None,
    field: str,
    *,
    segment: str,
) -> str:
    value = _required_string(payload, field, segment=segment)
    if _DIGEST.fullmatch(value) is None:
        raise _response_invalid(segment, f"{field} must be a canonical digest")
    return value


def _required_exact(
    payload: Mapping[str, Any] | None,
    field: str,
    expected: object,
    *,
    segment: str,
) -> None:
    value = (payload or {}).get(field)
    if value != expected or type(value) is not type(expected):
        raise _response_invalid(
            segment,
            f"{field} must equal the release-bound expectation",
        )


def _unique_strings(
    payload: Mapping[str, Any] | None,
    field: str,
    *,
    segment: str,
) -> list[str]:
    value = (payload or {}).get(field)
    if not isinstance(value, list):
        raise _response_invalid(segment, f"{field} must be an array")
    rows = [str(item).strip() for item in value]
    if not rows or any(not row for row in rows) or len(rows) != len(set(rows)):
        raise _response_invalid(
            segment,
            f"{field} must contain unique non-empty strings",
        )
    return rows


def _url_path(url: str, *, segment: str) -> str:
    path = urlsplit(url).path
    if not path.startswith("/"):
        raise _response_invalid(segment, "URL path must start with /")
    return path


def collect_research_isolation_probe_segments(
    *,
    release_id: str,
    manifest_digest: str,
    api_base_url: str,
    media_image_base_url: str,
    session: LocalAcceptanceSession,
    identity_contract_sha256: str,
    policy_ttl_seconds: int,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """执行 12 个真实 HTTP 探针并返回 PASS 文档的 10 个证据段。

    任何一个探针不满足预期状态或响应语义时立即抛出
    ``ResearchIsolationProbeError``；调用方不得在失败后写出任何文件。
    """

    api_base = str(api_base_url or "").strip().rstrip("/")
    media_base = str(media_image_base_url or "").strip().rstrip("/")
    if not api_base or not media_base:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "api/mediaImage public bases are required",
        )
    if (
        not isinstance(policy_ttl_seconds, int)
        or isinstance(policy_ttl_seconds, bool)
        or not 1 <= policy_ttl_seconds <= 900
    ):
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "policy signedMediaUrlMaxTtlSeconds must be within 1..900",
        )
    if _DIGEST.fullmatch(str(identity_contract_sha256 or "")) is None:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "identity contract sha256 must be a canonical digest",
        )

    # 1. identityIssuance: POST /auth/research/session（Bearer；仅白名单账号 200）。
    issuance_path = "/auth/research/session"
    _status, issuance_payload, issuance_operation = _perform_operation(
        segment="identity_issuance",
        path=issuance_path,
        expected_statuses=frozenset({200}),
        invoke=lambda headers: _authenticated_json(
            api_base,
            path=issuance_path,
            session=session,
            method="POST",
            body=None,
            headers=headers,
            timeout_seconds=timeout_seconds,
        ),
    )
    subject_hash = _required_digest(
        issuance_payload,
        "subjectHash",
        segment="identity_issuance",
    )
    attestation_token = _required_string(
        issuance_payload,
        "attestationId",
        segment="identity_issuance",
    )
    attestation_id_hash = _digest_bytes(attestation_token.encode("utf-8"))
    identity_issuance = {
        "subjectHash": subject_hash,
        "attestationIdHash": attestation_id_hash,
        "contractRef": IDENTITY_CONTRACT_REF,
        "contractSha256": identity_contract_sha256,
        "operation": issuance_operation,
    }
    attested_headers = {_ATTESTATION_HEADER: attestation_token}

    # 2. identityAttestation: GET /auth/research/session/attestation。
    #    必须回读同一 attestation（两段 attestationIdHash 必须一致）。
    attestation_path = "/auth/research/session/attestation"
    _status, attestation_payload, attestation_operation = _perform_operation(
        segment="identity_attestation",
        path=attestation_path,
        expected_statuses=frozenset({200}),
        invoke=lambda headers: _authenticated_json(
            api_base,
            path=attestation_path,
            session=session,
            method="GET",
            body=None,
            headers={**headers, **attested_headers},
            timeout_seconds=timeout_seconds,
        ),
    )
    if (
        _required_digest(
            attestation_payload,
            "subjectHash",
            segment="identity_attestation",
        )
        != subject_hash
    ):
        raise _response_invalid(
            "identity_attestation",
            "subjectHash drifts from identity issuance",
        )
    if (
        _required_string(
            attestation_payload,
            "attestationId",
            segment="identity_attestation",
        )
        != attestation_token
    ):
        raise _response_invalid(
            "identity_attestation",
            "attestationId drifts from identity issuance",
        )
    identity_attestation = {
        "subjectHash": subject_hash,
        "attestationIdHash": attestation_id_hash,
        "contractRef": IDENTITY_CONTRACT_REF,
        "contractSha256": identity_contract_sha256,
        "operation": attestation_operation,
    }

    # 3..5. 三次独立的 GET /content/research/readback（各自唯一 request/trace）。
    readback_path = "/content/research/readback"

    def _readback(segment: str) -> tuple[Mapping[str, Any], dict[str, Any]]:
        _inner_status, payload, operation = _perform_operation(
            segment=segment,
            path=readback_path,
            expected_statuses=frozenset({200}),
            invoke=lambda headers: _authenticated_json(
                api_base,
                path=readback_path,
                session=session,
                method="GET",
                body=None,
                headers={**headers, **attested_headers},
                timeout_seconds=timeout_seconds,
            ),
        )
        if not isinstance(payload, Mapping):
            raise _response_invalid(segment, "readback payload must be an object")
        _required_exact(payload, "releaseId", release_id, segment=segment)
        _required_exact(payload, "manifestDigest", manifest_digest, segment=segment)
        if (
            _required_digest(payload, "subjectHash", segment=segment)
            != subject_hash
        ):
            raise _response_invalid(segment, "subjectHash drifts from issuance")
        return payload, operation

    app_payload, app_operation = _readback("internal_app_readback")
    if (
        _required_digest(
            app_payload,
            "attestationIdHash",
            segment="internal_app_readback",
        )
        != attestation_id_hash
    ):
        raise _response_invalid(
            "internal_app_readback",
            "attestationIdHash drifts from identity issuance",
        )
    if app_payload.get("signatureVerified") is not True:
        raise _response_invalid(
            "internal_app_readback",
            "signatureVerified must be true",
        )
    if app_payload.get("researchBadgeVisible") is not True:
        raise _response_invalid(
            "internal_app_readback",
            "researchBadgeVisible must be true",
        )
    internal_app_readback = {
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "subjectHash": subject_hash,
        "attestationIdHash": attestation_id_hash,
        "signatureVerified": True,
        "researchBadgeVisible": True,
        "operation": app_operation,
    }

    exposure_payload, exposure_operation = _readback("network_exposure_readback")
    if exposure_payload.get("publicCdnDetected") is not False:
        raise _response_invalid(
            "network_exposure_readback",
            "publicCdnDetected must be false",
        )
    if exposure_payload.get("anonymousMediaUrlDetected") is not False:
        raise _response_invalid(
            "network_exposure_readback",
            "anonymousMediaUrlDetected must be false",
        )
    network_exposure_readback = {
        "publicCdnDetected": False,
        "anonymousMediaUrlDetected": False,
        "operation": exposure_operation,
    }

    positive_payload, positive_operation = _readback("positive_readback")
    entity_refs = _unique_strings(
        positive_payload,
        "entityRefs",
        segment="positive_readback",
    )
    post_ids = _unique_strings(
        positive_payload,
        "postIds",
        segment="positive_readback",
    )
    media_asset_ids = _unique_strings(
        positive_payload,
        "mediaAssetIds",
        segment="positive_readback",
    )
    positive_readback = {
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "subjectHash": subject_hash,
        "entityRefs": entity_refs,
        "postIds": post_ids,
        "mediaAssetIds": media_asset_ids,
        "operation": positive_operation,
    }

    # 6. anonymousContentProbe：无 Bearer、无 attestation → 401/403。
    _status, _payload, anonymous_content_operation = _perform_operation(
        segment="anonymous_content_probe",
        path=readback_path,
        expected_statuses=frozenset({401, 403}),
        invoke=lambda headers: _anonymous_json(
            api_base,
            path=readback_path,
            method="GET",
            headers=headers,
            timeout_seconds=timeout_seconds,
        ),
    )
    anonymous_content_probe = {
        "decision": "denied",
        "operation": anonymous_content_operation,
    }

    # 7. anonymousMediaProbe：按环境 media 交付形态对一个 release 资产匿名 GET。
    anonymous_media_url = media_base + "/" + media_asset_ids[0]
    _status, _payload, anonymous_media_operation = _perform_operation(
        segment="anonymous_media_probe",
        path=_url_path(anonymous_media_url, segment="anonymous_media_probe"),
        expected_statuses=frozenset({401, 403}),
        invoke=lambda headers: (
            fetch_media_status(
                anonymous_media_url,
                headers=headers,
                timeout_seconds=timeout_seconds,
            ),
            None,
        ),
    )
    anonymous_media_probe = {
        "decision": "denied",
        "operation": anonymous_media_operation,
    }

    # 8. signedMedia issuance：研究态预留一次原图访问授权（Idempotency-Key 必填）。
    signed_asset_id = media_asset_ids[0]
    issuance_media_path = f"/content/media/{signed_asset_id}/original:access"
    idempotency_key = new_probe_identity()
    _status, grant_payload, media_issuance_operation = _perform_operation(
        segment="signed_media_issuance",
        path=issuance_media_path,
        expected_statuses=frozenset({200}),
        invoke=lambda headers: _authenticated_json(
            api_base,
            path=issuance_media_path,
            session=session,
            method="POST",
            body={"mediaId": signed_asset_id, "purpose": "view"},
            headers={
                **headers,
                **attested_headers,
                "Idempotency-Key": idempotency_key,
            },
            timeout_seconds=timeout_seconds,
        ),
    )
    original_url = _required_string(
        grant_payload,
        "originalUrl",
        segment="signed_media_issuance",
    )
    audit_event_id = _required_string(
        grant_payload,
        "auditId",
        segment="signed_media_issuance",
    )
    ttl_seconds = (grant_payload or {}).get("ttlSeconds")
    if (
        not isinstance(ttl_seconds, int)
        or isinstance(ttl_seconds, bool)
        or not 1 <= ttl_seconds <= min(policy_ttl_seconds, 900)
    ):
        raise _response_invalid(
            "signed_media_issuance",
            "ttlSeconds must be within the runtime policy TTL ceiling",
        )
    signed_url_hash = _digest_bytes(original_url.encode("utf-8"))
    original_path = _url_path(original_url, segment="signed_media_issuance")
    split_original = urlsplit(original_url)
    if not split_original.query:
        raise _response_invalid(
            "signed_media_issuance",
            "originalUrl must be a signed short-lived URL",
        )

    # 9. deniedCapabilities.export：研究态未持 grant 直接访问 original 媒体
    #    URL（剥去签名 query）必须 deny。
    unsigned_original_url = split_original._replace(query="", fragment="").geturl()
    _status, _payload, export_operation = _perform_operation(
        segment="denied_export",
        path=original_path,
        expected_statuses=frozenset({401, 403}),
        invoke=lambda headers: (
            fetch_media_status(
                unsigned_original_url,
                headers=headers,
                timeout_seconds=timeout_seconds,
            ),
            None,
        ),
    )
    denied_export = {"decision": "denied", "operation": export_operation}

    # 10. deniedCapabilities.share：研究态调用真实站外分享事实入口必须 deny。
    share_post_id = post_ids[0]
    share_path = f"/content/posts/{share_post_id}/outbound-shares"
    share_idempotency_key = new_probe_identity()
    _status, _payload, share_operation = _perform_operation(
        segment="denied_share",
        path=share_path,
        expected_statuses=frozenset({401, 403}),
        invoke=lambda headers: _authenticated_json(
            api_base,
            path=share_path,
            session=session,
            method="POST",
            body={
                "postId": share_post_id,
                "channel": "system_share",
                "destinationKind": "external_app",
                "referralId": share_idempotency_key,
                "providerReceiptId": share_idempotency_key,
                "clientConfirmedAt": _utc_now_iso(),
                "deliverySucceeded": True,
            },
            headers={
                **headers,
                **attested_headers,
                "Idempotency-Key": share_idempotency_key,
            },
            timeout_seconds=timeout_seconds,
        ),
    )
    denied_share = {"decision": "denied", "operation": share_operation}

    # 11. signedMedia access：持签名 URL 的 GET 必须 200/206。
    _status, _payload, media_access_operation = _perform_operation(
        segment="signed_media_access",
        path=original_path,
        expected_statuses=frozenset({200, 206}),
        invoke=lambda headers: (
            fetch_media_status(
                original_url,
                headers=headers,
                timeout_seconds=timeout_seconds,
            ),
            None,
        ),
    )

    # 12. signedMedia audit readback：审计事实必须可回读。
    audit_path = f"/content/media/original-access-audits/{audit_event_id}"
    _status, audit_payload, audit_operation = _perform_operation(
        segment="signed_media_audit_readback",
        path=audit_path,
        expected_statuses=frozenset({200}),
        invoke=lambda headers: _authenticated_json(
            api_base,
            path=audit_path,
            session=session,
            method="GET",
            body=None,
            headers={**headers, **attested_headers},
            timeout_seconds=timeout_seconds,
        ),
    )
    if not isinstance(audit_payload, Mapping):
        raise _response_invalid(
            "signed_media_audit_readback",
            "audit readback payload must be an object",
        )
    signed_media = {
        "assetId": signed_asset_id,
        "signedUrlHash": signed_url_hash,
        "ttlSeconds": ttl_seconds,
        "auditEventId": audit_event_id,
        "issuanceOperation": media_issuance_operation,
        "accessOperation": media_access_operation,
        "auditReadbackOperation": audit_operation,
    }

    return {
        "subjectHash": subject_hash,
        "identityIssuance": identity_issuance,
        "identityAttestation": identity_attestation,
        "internalAppReadback": internal_app_readback,
        "anonymousContentProbe": anonymous_content_probe,
        "anonymousMediaProbe": anonymous_media_probe,
        "networkExposureReadback": network_exposure_readback,
        "deniedCapabilities": {"share": denied_share, "export": denied_export},
        "signedMedia": signed_media,
        "positiveReadback": positive_readback,
    }


def runtime_proof_output_path(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
) -> Path:
    """canonical verify run 内的 create-once runtime proof 路径。"""

    return (
        output_root()
        / "env"
        / _safe_segment(environment, label="environment")
        / "runs"
        / "data-release"
        / _safe_segment(release_id, label="releaseId")
        / _safe_segment(verify_run_id, label="verifyRunId")
        / RUNTIME_PROOF_FILE_NAME
    )


def _policy_snapshot(environment: str) -> tuple[str, int]:
    policy_path = ROOT / "quwoquan_ops" / "environments" / environment / "runtime.yaml"
    try:
        policy_bytes = policy_path.read_bytes()
        policy = load_json_yaml(policy_path)
    except (OSError, ValueError) as exc:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            f"runtime policy is unreadable: {policy_path}",
        ) from exc
    if not isinstance(policy, Mapping) or policy.get(
        "productLifecycleState"
    ) != "research":
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            f"{environment} productLifecycleState must be research",
        )
    isolation = policy.get("researchContentIsolation")
    ttl = isolation.get("signedMediaUrlMaxTtlSeconds") if isinstance(
        isolation, Mapping
    ) else None
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 900:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "researchContentIsolation.signedMediaUrlMaxTtlSeconds must be 1..900",
        )
    return _digest_bytes(policy_bytes), ttl


def run_research_isolation_runtime_probe(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """环境 owner 侧一次完整探针执行：登录、12 探针、组装、create-once 写入。"""

    environment = _safe_segment(environment, label="environment")
    release_id = _safe_segment(release_id, label="releaseId")
    verify_run_id = _safe_segment(verify_run_id, label="verifyRunId")
    if environment not in _PROBE_ENVIRONMENTS:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "environment must be one of alpha/beta/gamma",
        )
    if _DIGEST.fullmatch(str(manifest_digest or "")) is None:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "manifest digest must be a canonical sha256 digest",
        )
    output_path = runtime_proof_output_path(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
    )
    if output_path.exists() or output_path.is_symlink():
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROOF_ALREADY_EXISTS",
            f"runtime proof already exists (create-once): {output_path}",
        )
    policy_sha256, policy_ttl = _policy_snapshot(environment)
    identity_contract_path = ROOT / IDENTITY_CONTRACT_REF
    if identity_contract_path.is_symlink() or not identity_contract_path.is_file():
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            f"identity contract is unavailable: {identity_contract_path}",
        )
    identity_contract_sha256 = _digest_bytes(identity_contract_path.read_bytes())
    target_name = ENVIRONMENT_CANONICAL_TARGET[environment]
    target = get_target(load_environment_topology(), target_name)
    public_bases = target.get("publicBases") or {}
    api_base = str(public_bases.get("api") or "").strip().rstrip("/")
    media_image_base = str(public_bases.get("mediaImage") or "").strip().rstrip("/")
    if not api_base or not media_image_base:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            f"{target_name} api/mediaImage public bases are unavailable",
        )
    instance_id = hashlib.sha256(
        (
            "research-isolation-probe\0"
            + environment
            + "\0"
            + release_id
            + "\0"
            + verify_run_id
        ).encode("utf-8")
    ).hexdigest()
    previous_ssl_cert_file = os.environ.get("SSL_CERT_FILE")
    os.environ["SSL_CERT_FILE"] = str(root_certificate_path(target_name))
    try:
        actor = open_local_phone_acceptance_session(
            api_base,
            environment=environment,
            target_name=target_name,
            test_data_instance_id=instance_id,
            identity_set_id=_RESEARCH_IDENTITY_SET_ID,
            actor_role=_PROBE_ACTOR_ROLE,
            actor_index=0,
            timeout_seconds=max(timeout_seconds, 30.0),
        )
    finally:
        if previous_ssl_cert_file is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = previous_ssl_cert_file
    segments = collect_research_isolation_probe_segments(
        release_id=release_id,
        manifest_digest=manifest_digest,
        api_base_url=api_base,
        media_image_base_url=media_image_base,
        session=actor.session,
        identity_contract_sha256=identity_contract_sha256,
        policy_ttl_seconds=policy_ttl,
        timeout_seconds=timeout_seconds,
    )
    document = build_runtime_proof_document(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
        policy_sha256=policy_sha256,
        segments=segments,
    )
    write_runtime_proof_create_once(output_path, document)
    operations = _segment_operations(segments)
    return {
        "outputPath": str(output_path),
        "environment": environment,
        "releaseId": release_id,
        "verifyRunId": verify_run_id,
        "manifestDigest": manifest_digest,
        "subjectHash": segments["subjectHash"],
        "operationCount": len(operations),
        "operationStatuses": [int(row["status"]) for row in operations],
        "verificationChecksum": document["verificationChecksum"],
    }


__all__ = [
    "IDENTITY_CONTRACT_REF",
    "PASS_DOCUMENT_KEYS",
    "RUNTIME_PROOF_FILE_NAME",
    "ResearchIsolationProbeError",
    "build_runtime_proof_document",
    "collect_research_isolation_probe_segments",
    "fetch_media_status",
    "new_probe_identity",
    "run_research_isolation_runtime_probe",
    "runtime_proof_output_path",
    "write_runtime_proof_create_once",
]
