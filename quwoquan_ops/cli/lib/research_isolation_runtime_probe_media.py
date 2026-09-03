"""Research isolation runtime probe 的媒体传输与严格资产校验职责。

入口模块继续拥有稳定 public import 与 monkeypatch surface；本模块只消费入口显式
注入的 HTTP、身份、目标解析和证书依赖，避免拆分后测试补丁落到错误模块。
"""

from __future__ import annotations

import ssl
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import parse_qs, quote, urlsplit

from .local_environment_auth import (
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
)
from .research_isolation_proof_document import (
    ResearchIsolationProbeError,
    _digest_bytes,
)

TargetResolver = Callable[[str], str | None]
CertificateResolver = Callable[[str], Path]
FetchBytes = Callable[..., tuple[int, bytes, str, str]]
RequestJson = Callable[..., Mapping[str, Any]]
RequiredValue = Callable[..., str]
ResponseInvalid = Callable[[str, str], ResearchIsolationProbeError]


def _transport(
    url: str,
    *,
    target_resolver: TargetResolver,
    certificate_resolver: CertificateResolver,
) -> tuple[request.OpenerDirector, str]:
    host = urlsplit(url).hostname
    if not host:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "media probe URL has no hostname",
        )
    target_name = target_resolver(host)
    if target_name is None:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "media probe URL is not a canonical local target",
        )
    ca_file = certificate_resolver(target_name)
    if not ca_file.is_file() or ca_file.is_symlink():
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_TRANSPORT_FAILED",
            "media probe root certificate is unavailable",
        )
    context = ssl.create_default_context(cafile=str(ca_file))
    return (
        request.build_opener(
            request.ProxyHandler({}),
            request.HTTPSHandler(context=context),
        ),
        target_name,
    )


def fetch_media_status(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = 12.0,
    target_resolver: TargetResolver,
    certificate_resolver: CertificateResolver,
) -> int:
    """对媒体 URL 执行真实 GET，并返回 HTTP status。"""

    opener, _target_name = _transport(
        url,
        target_resolver=target_resolver,
        certificate_resolver=certificate_resolver,
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


def fetch_media_bytes(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = 12.0,
    max_bytes: int,
    target_resolver: TargetResolver,
    certificate_resolver: CertificateResolver,
) -> tuple[int, bytes, str, str]:
    """通过 canonical local TLS 路径读取有界签名媒体字节。"""

    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "media probe byte budget must be positive",
        )
    opener, _target_name = _transport(
        url,
        target_resolver=target_resolver,
        certificate_resolver=certificate_resolver,
    )
    req = request.Request(url, headers=dict(headers or {}), method="GET")
    try:
        with opener.open(req, timeout=max(1.0, timeout_seconds)) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ResearchIsolationProbeError(
                    "OPS.RESEARCH.PROBE_RESPONSE_INVALID",
                    "signed media exceeds the release byte authority",
                )
            return (
                int(response.status),
                body,
                str(response.headers.get("Content-Type") or ""),
                str(response.headers.get("Content-Range") or ""),
            )
    except error.HTTPError as exc:
        body = exc.read(max_bytes + 1) if exc.fp else b""
        return (
            int(exc.code),
            body[:max_bytes],
            str(exc.headers.get("Content-Type") or ""),
            str(exc.headers.get("Content-Range") or ""),
        )
    except ResearchIsolationProbeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_TRANSPORT_FAILED",
            f"media probe transport failed: {type(exc).__name__}",
        ) from exc


def probe_release_bound_signed_media(
    *,
    api_base_url: str,
    session: LocalAcceptanceSession,
    asset: Mapping[str, Any],
    attestation_token: str,
    timeout_seconds: float,
    request_json: RequestJson,
    fetch_bytes: FetchBytes,
    identity_factory: Callable[[], str],
    required_string: RequiredValue,
    required_digest: RequiredValue,
    response_invalid: ResponseInvalid,
) -> dict[str, Any]:
    """签发一个 release 资产授权，并验证精确字节与视频 Range。"""

    asset_id = required_string(asset, "assetId", segment="strict_signed_media")
    kind = required_string(asset, "kind", segment="strict_signed_media")
    expected_sha256 = required_digest(
        asset, "expectedSha256", segment="strict_signed_media"
    )
    expected_mime_type = required_string(
        asset, "expectedMimeType", segment="strict_signed_media"
    ).lower()
    expected_bytes = asset.get("expectedBytes")
    classifications = asset.get("classifications")
    require_range = asset.get("requireRange")
    if (
        kind not in {"avatar", "image", "video"}
        or not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes <= 0
        or not isinstance(classifications, list)
        or not classifications
        or any(not str(value or "").strip() for value in classifications)
        or len(classifications) != len(set(classifications))
        or require_range is not (kind == "video")
        or not expected_mime_type.startswith(
            "video/" if kind == "video" else "image/"
        )
    ):
        raise response_invalid(
            "strict_signed_media", "asset classification is invalid"
        )
    issuance_path = "/content/media/" + quote(asset_id, safe="") + "/original:access"
    idempotency_key = identity_factory()
    try:
        grant = request_json(
            api_base_url,
            path=issuance_path,
            session=session,
            method="POST",
            body={"mediaId": asset_id, "purpose": "view"},
            headers={
                "Idempotency-Key": idempotency_key,
                **(
                    {"X-Research-Identity-Attestation": attestation_token}
                    if str(attestation_token or "").strip()
                    else {}
                ),
            },
            timeout_seconds=timeout_seconds,
        )
    except LocalEnvironmentHTTPError as exc:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_UNEXPECTED_STATUS",
            f"strict signed media issuance returned HTTP {exc.status}",
        ) from exc
    if str(grant.get("mediaId") or "").strip() != asset_id:
        raise response_invalid(
            "strict_signed_media",
            "grant mediaId is not the exact release asset",
        )
    original_url = required_string(
        grant, "originalUrl", segment="strict_signed_media"
    )
    signed_query = parse_qs(urlsplit(original_url).query, keep_blank_values=True)
    if not (signed_query.get("sign") or [""])[0] or not (
        signed_query.get("t") or [""]
    )[0]:
        raise response_invalid(
            "strict_signed_media",
            "originalUrl lacks canonical sign/t binding",
        )
    status, body, content_type, _content_range = fetch_bytes(
        original_url,
        headers={"Accept": "*/*"},
        timeout_seconds=timeout_seconds,
        max_bytes=expected_bytes,
    )
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    observed_sha256 = _digest_bytes(body)
    if (
        status != 200
        or len(body) != expected_bytes
        or observed_sha256 != expected_sha256
        or normalized_type != expected_mime_type
    ):
        raise response_invalid(
            "strict_signed_media",
            "signed media bytes/MIME/hash drift from release authority",
        )
    range_status = 0
    content_range = ""
    range_bytes = 0
    if require_range:
        range_status, range_body, range_type, content_range = fetch_bytes(
            original_url,
            headers={"Accept": "*/*", "Range": "bytes=0-1"},
            timeout_seconds=timeout_seconds,
            max_bytes=2,
        )
        if (
            range_status != 206
            or not range_body
            or len(range_body) > 2
            or not content_range.startswith("bytes 0-")
            or range_type.split(";", 1)[0].strip().lower() != expected_mime_type
        ):
            raise response_invalid(
                "strict_signed_media",
                "video signed media does not honor the required byte Range",
            )
        range_bytes = len(range_body)
    return {
        "assetId": asset_id,
        "kind": kind,
        "classifications": sorted(
            str(value).strip() for value in classifications
        ),
        "statusCode": status,
        "mimeType": normalized_type,
        "bytes": len(body),
        "sha256": observed_sha256,
        "hashVerified": True,
        "signedUrlHash": _digest_bytes(original_url.encode("utf-8")),
        "rangeRequested": bool(require_range),
        "rangeStatusCode": range_status,
        "rangeBytes": range_bytes,
        "contentRange": content_range,
        "auditEventId": required_string(
            grant, "auditId", segment="strict_signed_media"
        ),
    }
