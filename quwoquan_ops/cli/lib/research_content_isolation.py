"""Validate canonical runtime evidence for research-content isolation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import ROOT, load_json_yaml
from .output_paths import output_root

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_CONTRACT = (
    ROOT / "quwoquan_service/services/user-service/contracts/account/"
    "account_session/operations.yaml"
)
_SIGNED_MEDIA_CONTRACT = (
    ROOT / "quwoquan_service/services/content-service/contracts/media/"
    "media_original_access_fact/operations.yaml"
)
_SIGNED_MEDIA_POLICY = (
    ROOT / "quwoquan_service/services/content-service/contracts/media/"
    "media_original_access_fact/original_access_policy.yaml"
)
_REQUIRED_IDENTITY_OPERATION = "IssueWhitelistedResearchSession"
_REQUIRED_TRUE = (
    "identityWhitelistRequired",
    "sharingDisabled",
    "exportDisabled",
    "searchIndexingDisabled",
    "internalAppSignatureRequired",
    "researchBadgeRequired",
    "shortLivedSignedMediaUrlsRequired",
    "mediaAccessAuditLogRequired",
)
_REQUIRED_FALSE = (
    "anonymousContentAccess",
    "anonymousMediaAccess",
    "publicContentDistribution",
)
_SECRET_KEY_PARTS = ("token", "authorization", "credential", "password", "secret")
_OPERATION_FIELDS = frozenset(
    {
        "path",
        "pageId",
        "status",
        "requestId",
        "traceId",
        "startedAt",
        "endedAt",
        "durationMs",
    }
)
_PASS_KEYS = frozenset(
    {
        "schema",
        "environment",
        "releaseId",
        "manifestDigest",
        "releaseClass",
        "productLifecycleState",
        "verifyRunId",
        "policyRef",
        "policySha256",
        "outcome",
        "subjectHash",
        "identityIssuance",
        "identityAttestation",
        "internalAppReadback",
        "anonymousContentProbe",
        "anonymousMediaProbe",
        "networkExposureReadback",
        "deniedCapabilities",
        "signedMedia",
        "positiveReadback",
        "verifiedAt",
        "verificationChecksum",
    }
)


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _checksum(document: Mapping[str, Any]) -> str:
    return _sha256(
        json.dumps(
            dict(document),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _policy(environment: str) -> tuple[Path, Mapping[str, Any], int]:
    path = ROOT / "quwoquan_ops" / "environments" / environment / "runtime.yaml"
    try:
        payload = load_json_yaml(path)
    except Exception as exc:
        raise ValueError(
            "DATA.RESEARCH.ISOLATION_POLICY_INVALID: research runtime policy "
            f"is unreadable: {path}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: runtime must be an object")
    if payload.get("productLifecycleState") != "research":
        raise ValueError(f"{environment}: productLifecycleState must be research")
    isolation = payload.get("researchContentIsolation")
    if not isinstance(isolation, Mapping):
        raise ValueError(f"{environment}: researchContentIsolation is missing")
    issues = [
        f"{environment}: researchContentIsolation.{field} must be true"
        for field in _REQUIRED_TRUE
        if isolation.get(field) is not True
    ]
    issues.extend(
        f"{environment}: researchContentIsolation.{field} must be false"
        for field in _REQUIRED_FALSE
        if isolation.get(field) is not False
    )
    ttl = isolation.get("signedMediaUrlMaxTtlSeconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= 900:
        issues.append(
            f"{environment}: signedMediaUrlMaxTtlSeconds must be within 1..900"
        )
        ttl = 0
    if issues:
        raise ValueError("; ".join(issues))
    return path, isolation, ttl


def _identity_adapter_available() -> bool:
    try:
        payload = load_json_yaml(_IDENTITY_CONTRACT)
    except Exception:
        return False
    routes = payload.get("api_routes") if isinstance(payload, Mapping) else None
    if not isinstance(routes, list):
        return False
    for raw in routes:
        if not isinstance(raw, Mapping):
            continue
        security = raw.get("security")
        response_fields = raw.get("response_fields")
        if (
            raw.get("operation") == _REQUIRED_IDENTITY_OPERATION
            and raw.get("method") == "POST"
            and isinstance(security, Mapping)
            and security.get("auth_mode") == "required"
            and security.get("anonymous_policy") == "deny"
            and isinstance(response_fields, list)
            and {"subjectHash", "attestationId"}.issubset(response_fields)
        ):
            return True
    return False


def _signed_media_adapter_available() -> bool:
    try:
        operations = load_json_yaml(_SIGNED_MEDIA_CONTRACT)
        policy = load_json_yaml(_SIGNED_MEDIA_POLICY)
    except Exception:
        return False
    routes = operations.get("api_routes") if isinstance(operations, Mapping) else None
    ttl = policy.get("grant_ttl_seconds") if isinstance(policy, Mapping) else None
    if not isinstance(routes, list) or not isinstance(ttl, int) or not 1 <= ttl <= 900:
        return False
    for raw in routes:
        if not isinstance(raw, Mapping):
            continue
        security = raw.get("security")
        fields = raw.get("response_fields")
        if (
            raw.get("operation") == "RequestOriginalImageAccess"
            and isinstance(security, Mapping)
            and security.get("auth_mode") == "required"
            and security.get("anonymous_policy") == "deny"
            and isinstance(fields, list)
            and {"originalUrl", "ttlSeconds", "auditId"}.issubset(fields)
        ):
            return True
    return False


def _runtime_proof_blocker_code() -> str:
    if not _identity_adapter_available():
        return "DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE"
    if not _signed_media_adapter_available():
        return "DATA.RESEARCH.SIGNED_MEDIA_ADAPTER_UNAVAILABLE"
    return "DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE"


def _assert_no_secrets(value: object, *, path: str = "receipt") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            if any(part in key.casefold() for part in _SECRET_KEY_PARTS):
                raise ValueError(
                    "research isolation receipt contains forbidden secret field: "
                    f"{path}.{key}"
                )
            _assert_no_secrets(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_secrets(child, path=f"{path}[{index}]")


def _validate_operation(
    value: object,
    *,
    label: str,
    statuses: frozenset[int],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _OPERATION_FIELDS:
        raise ValueError(f"research isolation {label} operation is incomplete")
    status = value.get("status")
    duration = value.get("durationMs")
    if (
        not isinstance(value.get("path"), str)
        or not str(value["path"]).startswith("/")
        or not str(value.get("pageId") or "").strip()
        or not isinstance(status, int)
        or isinstance(status, bool)
        or status not in statuses
        or not str(value.get("requestId") or "").strip()
        or not str(value.get("traceId") or "").strip()
        or not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration < 0
    ):
        raise ValueError(f"research isolation {label} operation fields are invalid")
    try:
        started = datetime.fromisoformat(
            str(value.get("startedAt") or "").replace("Z", "+00:00")
        )
        ended = datetime.fromisoformat(
            str(value.get("endedAt") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            f"research isolation {label} operation timestamps are invalid"
        ) from exc
    if started.utcoffset() is None or ended.utcoffset() is None or ended < started:
        raise ValueError(f"research isolation {label} operation timestamps are invalid")
    return value


def _string_set(value: object, *, label: str) -> set[str]:
    if not isinstance(value, list):
        raise ValueError(f"research isolation {label} must be an array")
    rows = [str(item).strip() for item in value]
    if not rows or any(not item for item in rows) or len(rows) != len(set(rows)):
        raise ValueError(
            f"research isolation {label} must contain unique non-empty strings"
        )
    return set(rows)


def _load_receipt(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    data_readiness: Mapping[str, Any] | None,
    data_readiness_path: Path | None,
) -> tuple[dict[str, Any], Path, str]:
    if data_readiness is None or data_readiness_path is None:
        blocker_code = _runtime_proof_blocker_code()
        raise ValueError(
            f"{blocker_code}: canonical Data research isolation verification is missing"
        )
    ref = str(data_readiness.get("researchIsolationVerificationRef") or "").strip()
    digest = str(
        data_readiness.get("researchIsolationVerificationDigest") or ""
    ).strip()
    expected_ref = (
        Path("env")
        / environment
        / "runs/data-release"
        / release_id
        / verify_run_id
        / "research-isolation-verification.json"
    ).as_posix()
    if ref != expected_ref or _DIGEST.fullmatch(digest) is None:
        raise ValueError(
            "canonical Data research isolation ref/digest is not release-bound"
        )
    root = output_root().expanduser().resolve()
    path = (root / ref).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("research isolation receipt escapes QWQ_OUTPUT_ROOT") from exc
    expected_readiness = path.with_name("release-readiness.json")
    if data_readiness_path.resolve() != expected_readiness.resolve():
        raise ValueError(
            "research isolation receipt does not share the canonical Data verify run"
        )
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"research isolation receipt is missing: {ref}")
    if _sha256(path.read_bytes()) != digest:
        raise ValueError("research isolation receipt file digest drift")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("research isolation receipt is unreadable") from exc
    if not isinstance(raw, dict):
        raise ValueError("research isolation receipt must be an object")
    receipt = dict(raw)
    expected = {
        "schema": "quwoquan_data.research_isolation_verification",
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "verifyRunId": verify_run_id,
        "outcome": "PASS",
    }
    if set(receipt) != _PASS_KEYS or any(
        receipt.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("research isolation PASS receipt fields/identity drift")
    unsigned = dict(receipt)
    declared_checksum = str(unsigned.pop("verificationChecksum", ""))
    if declared_checksum != _checksum(unsigned):
        raise ValueError("research isolation verificationChecksum drift")
    _assert_no_secrets(receipt)
    return receipt, path, digest


def _verify_runtime_proof(
    receipt: Mapping[str, Any],
    *,
    release_id: str,
    data_readiness: Mapping[str, Any],
    policy_ttl: int,
) -> None:
    if not _identity_adapter_available():
        raise ValueError(
            "DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE: canonical whitelisted "
            "research identity issuance/attestation operation is absent"
        )
    if not _signed_media_adapter_available():
        raise ValueError(
            "DATA.RESEARCH.SIGNED_MEDIA_ADAPTER_UNAVAILABLE: canonical "
            "authenticated signed-media operation is absent"
        )
    subject_hash = str(receipt.get("subjectHash") or "")
    issuance = receipt.get("identityIssuance")
    attestation = receipt.get("identityAttestation")
    app = receipt.get("internalAppReadback")
    anonymous_content = receipt.get("anonymousContentProbe")
    anonymous_media = receipt.get("anonymousMediaProbe")
    exposure = receipt.get("networkExposureReadback")
    denied = receipt.get("deniedCapabilities")
    signed = receipt.get("signedMedia")
    readback = receipt.get("positiveReadback")
    if _DIGEST.fullmatch(subject_hash) is None:
        raise ValueError("research isolation subjectHash is invalid")
    if any(
        not isinstance(item, Mapping)
        for item in (
            issuance,
            attestation,
            app,
            anonymous_content,
            anonymous_media,
            exposure,
            denied,
            signed,
            readback,
        )
    ):
        raise ValueError("research isolation runtime proof is incomplete")
    if (
        issuance.get("subjectHash") != subject_hash
        or attestation.get("subjectHash") != subject_hash
        or app.get("releaseId") != release_id
        or app.get("signatureVerified") is not True
        or app.get("researchBadgeVisible") is not True
        or anonymous_content.get("decision") != "denied"
        or anonymous_media.get("decision") != "denied"
        or exposure.get("publicCdnDetected") is not False
        or exposure.get("anonymousMediaUrlDetected") is not False
        or readback.get("releaseId") != release_id
    ):
        raise ValueError("research isolation runtime decisions are not fail-closed")
    if data_readiness.get("internalSubjectHash") != subject_hash:
        raise ValueError(
            "research isolation subjectHash drifts from canonical Data readiness"
        )
    for label, proof in (
        ("identityIssuance", issuance),
        ("identityAttestation", attestation),
    ):
        contract_ref = Path(str(proof.get("contractRef") or ""))
        contract_path = (ROOT / contract_ref).resolve()
        try:
            contract_path.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise ValueError(
                f"research isolation {label} contractRef escapes repository"
            ) from exc
        if (
            contract_path != _IDENTITY_CONTRACT.resolve()
            or contract_path.is_symlink()
            or not contract_path.is_file()
            or proof.get("contractSha256") != _sha256(contract_path.read_bytes())
        ):
            raise ValueError(f"research isolation {label} contract digest drift")
    for label, probe in (
        ("anonymous content", anonymous_content),
        ("anonymous media", anonymous_media),
    ):
        operation = probe.get("operation")
        if not isinstance(operation, Mapping) or operation.get("status") not in {
            401,
            403,
        }:
            raise ValueError(f"research isolation {label} did not return 401/403")
    if set(denied) != {"share", "export", "indexing"} or any(
        not isinstance(row, Mapping) or row.get("decision") != "denied"
        for row in denied.values()
    ):
        raise ValueError(
            "research isolation share/export/indexing denial is incomplete"
        )
    ttl = signed.get("ttlSeconds")
    if (
        not isinstance(ttl, int)
        or isinstance(ttl, bool)
        or not 1 <= ttl <= min(900, policy_ttl)
        or _DIGEST.fullmatch(str(signed.get("signedUrlHash") or "")) is None
        or not str(signed.get("auditEventId") or "").strip()
    ):
        raise ValueError(
            "research isolation signed media TTL/audit evidence is invalid"
        )
    expected_sets = {
        "entityRefs": data_readiness.get("entityRefs"),
        "postIds": data_readiness.get("postIds"),
        "mediaAssetIds": data_readiness.get("mediaAssetIds"),
    }
    for field, expected in expected_sets.items():
        if _string_set(readback.get(field), label=field) != _string_set(
            expected,
            label=f"Data readiness {field}",
        ):
            raise ValueError(f"research isolation exact {field} readback drift")
    if signed.get("assetId") not in (readback.get("mediaAssetIds") or []):
        raise ValueError("research isolation signed media is not release-bound")
    specs = (
        (issuance.get("operation"), "identity issuance", frozenset({200})),
        (attestation.get("operation"), "identity attestation", frozenset({200})),
        (app.get("operation"), "internal App", frozenset({200})),
        (
            anonymous_content.get("operation"),
            "anonymous content",
            frozenset({401, 403}),
        ),
        (
            anonymous_media.get("operation"),
            "anonymous media",
            frozenset({401, 403}),
        ),
        (exposure.get("operation"), "network exposure", frozenset({200})),
        (denied["share"].get("operation"), "share denial", frozenset({200, 401, 403})),
        (
            denied["export"].get("operation"),
            "export denial",
            frozenset({200, 401, 403}),
        ),
        (
            denied["indexing"].get("operation"),
            "index denial",
            frozenset({200, 401, 403}),
        ),
        (signed.get("issuanceOperation"), "media issuance", frozenset({200})),
        (signed.get("accessOperation"), "media access", frozenset({200, 206})),
        (signed.get("auditReadbackOperation"), "media audit", frozenset({200})),
        (readback.get("operation"), "positive readback", frozenset({200})),
    )
    operations = [
        _validate_operation(value, label=label, statuses=statuses)
        for value, label, statuses in specs
    ]
    request_ids = [str(row.get("requestId") or "") for row in operations]
    trace_ids = [str(row.get("traceId") or "") for row in operations]
    if (
        len(operations) != 13
        or len(request_ids) != len(set(request_ids))
        or len(trace_ids) != len(set(trace_ids))
    ):
        raise ValueError(
            "research isolation operation evidence is incomplete or reused"
        )


def verify_research_content_isolation(
    environment: str,
    *,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    data_readiness: Mapping[str, Any] | None,
    data_readiness_path: Path | None,
) -> dict[str, Any]:
    """Require live canonical evidence; runtime.yaml alone can never PASS."""

    policy_path, _isolation, policy_ttl = _policy(environment)
    receipt, path, digest = _load_receipt(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
        data_readiness=data_readiness,
        data_readiness_path=data_readiness_path,
    )
    expected_policy_ref = policy_path.relative_to(ROOT).as_posix()
    if receipt.get("policyRef") != expected_policy_ref or receipt.get(
        "policySha256"
    ) != _sha256(policy_path.read_bytes()):
        raise ValueError("research isolation runtime policy snapshot drift")
    assert data_readiness is not None
    _verify_runtime_proof(
        receipt,
        release_id=release_id,
        data_readiness=data_readiness,
        policy_ttl=policy_ttl,
    )
    return {
        "schema": "quwoquan_ops.research_content_isolation",
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "outcome": "PASS",
        "subjectHash": receipt["subjectHash"],
        "receiptRef": path.relative_to(output_root().expanduser().resolve()).as_posix(),
        "receiptDigest": digest,
        "policyRef": expected_policy_ref,
        "anonymousContentStatus": receipt["anonymousContentProbe"]["operation"][
            "status"
        ],
        "anonymousMediaStatus": receipt["anonymousMediaProbe"]["operation"]["status"],
        "signedMediaTtlSeconds": receipt["signedMedia"]["ttlSeconds"],
        "mediaAuditEventId": receipt["signedMedia"]["auditEventId"],
        "exactReadbackCounts": {
            "entities": len(receipt["positiveReadback"]["entityRefs"]),
            "posts": len(receipt["positiveReadback"]["postIds"]),
            "mediaAssets": len(receipt["positiveReadback"]["mediaAssetIds"]),
        },
    }


__all__ = ["verify_research_content_isolation"]
