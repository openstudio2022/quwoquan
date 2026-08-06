"""Strict positive-proof validation for research environment isolation."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
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


class ResearchIsolationProofError(ValueError):
    """A purported PASS receipt lacks live, bound, fail-closed proof."""


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchIsolationProofError(
            f"research isolation {label} proof must be an object"
        )
    return value


def _operation(
    value: object,
    *,
    label: str,
    statuses: frozenset[int],
) -> Mapping[str, Any]:
    row = _mapping(value, label=f"{label} operation")
    status = row.get("status")
    duration = row.get("durationMs")
    if (
        set(row) != _OPERATION_FIELDS
        or not isinstance(row.get("path"), str)
        or not str(row["path"]).startswith("/")
        or not str(row.get("pageId") or "").strip()
        or not isinstance(status, int)
        or isinstance(status, bool)
        or status not in statuses
        or not str(row.get("requestId") or "").strip()
        or not str(row.get("traceId") or "").strip()
        or not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration < 0
    ):
        raise ResearchIsolationProofError(
            f"research isolation {label} operation fields are invalid"
        )
    try:
        started = datetime.fromisoformat(
            str(row.get("startedAt") or "").replace("Z", "+00:00")
        )
        ended = datetime.fromisoformat(
            str(row.get("endedAt") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ResearchIsolationProofError(
            f"research isolation {label} operation timestamps are invalid"
        ) from exc
    if started.utcoffset() is None or ended.utcoffset() is None or ended < started:
        raise ResearchIsolationProofError(
            f"research isolation {label} operation timestamps are invalid"
        )
    return row


def _identity_contract(
    proof: Mapping[str, Any],
    *,
    label: str,
    repository_root: Path,
    identity_contract: Path,
) -> None:
    contract_path = (repository_root / str(proof.get("contractRef") or "")).resolve()
    try:
        contract_path.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise ResearchIsolationProofError(
            f"research isolation {label} contractRef escapes repository"
        ) from exc
    if (
        contract_path != identity_contract.resolve()
        or contract_path.is_symlink()
        or not contract_path.is_file()
        or proof.get("contractSha256") != _digest_bytes(contract_path.read_bytes())
    ):
        raise ResearchIsolationProofError(
            f"research isolation {label} contract digest drift"
        )


def _nonempty_unique_strings(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ResearchIsolationProofError(
            f"research isolation {label} must be an array"
        )
    rows = [str(item).strip() for item in value]
    if not rows or any(not row for row in rows) or len(rows) != len(set(rows)):
        raise ResearchIsolationProofError(
            f"research isolation {label} must contain unique non-empty IDs"
        )
    return rows


def validate_research_isolation_pass_proof(
    payload: Mapping[str, Any],
    *,
    policy_ttl: int,
    repository_root: Path,
    identity_contract: Path,
) -> None:
    """Validate every required live operation without trusting schema conditionals."""

    subject_hash = str(payload.get("subjectHash") or "")
    if _DIGEST.fullmatch(subject_hash) is None:
        raise ResearchIsolationProofError(
            "research isolation subjectHash is not a canonical digest"
        )
    issuance = _mapping(payload.get("identityIssuance"), label="identity issuance")
    attestation = _mapping(
        payload.get("identityAttestation"),
        label="identity attestation",
    )
    app = _mapping(payload.get("internalAppReadback"), label="internal App")
    anonymous_content = _mapping(
        payload.get("anonymousContentProbe"),
        label="anonymous content",
    )
    anonymous_media = _mapping(
        payload.get("anonymousMediaProbe"),
        label="anonymous media",
    )
    exposure = _mapping(
        payload.get("networkExposureReadback"),
        label="network exposure",
    )
    denied = _mapping(payload.get("deniedCapabilities"), label="capability denial")
    signed = _mapping(payload.get("signedMedia"), label="signed media")
    readback = _mapping(payload.get("positiveReadback"), label="positive readback")
    release_id = payload.get("releaseId")
    manifest_digest = payload.get("manifestDigest")
    attestation_id_hash = str(issuance.get("attestationIdHash") or "")
    if (
        issuance.get("subjectHash") != subject_hash
        or attestation.get("subjectHash") != subject_hash
        or _DIGEST.fullmatch(attestation_id_hash) is None
        or attestation.get("attestationIdHash") != attestation_id_hash
        or app.get("releaseId") != release_id
        or app.get("manifestDigest") != manifest_digest
        or app.get("subjectHash") != subject_hash
        or app.get("attestationIdHash") != attestation_id_hash
        or app.get("signatureVerified") is not True
        or app.get("researchBadgeVisible") is not True
        or anonymous_content.get("decision") != "denied"
        or anonymous_media.get("decision") != "denied"
        or exposure.get("publicCdnDetected") is not False
        or exposure.get("anonymousMediaUrlDetected") is not False
        or readback.get("releaseId") != release_id
        or readback.get("manifestDigest") != manifest_digest
        or readback.get("subjectHash") != subject_hash
        or set(denied) != {"share", "export", "indexing"}
        or any(
            not isinstance(item, Mapping) or item.get("decision") != "denied"
            for item in denied.values()
        )
    ):
        raise ResearchIsolationProofError(
            "research isolation PASS decisions are not release-bound and fail-closed"
        )
    for label, proof in (
        ("identity issuance", issuance),
        ("identity attestation", attestation),
    ):
        _identity_contract(
            proof,
            label=label,
            repository_root=repository_root,
            identity_contract=identity_contract,
        )
    media_ids = _nonempty_unique_strings(
        readback.get("mediaAssetIds"),
        label="positiveReadback.mediaAssetIds",
    )
    _nonempty_unique_strings(
        readback.get("entityRefs"),
        label="positiveReadback.entityRefs",
    )
    _nonempty_unique_strings(
        readback.get("postIds"),
        label="positiveReadback.postIds",
    )
    ttl = signed.get("ttlSeconds")
    if (
        signed.get("assetId") not in media_ids
        or _DIGEST.fullmatch(str(signed.get("signedUrlHash") or "")) is None
        or not isinstance(ttl, int)
        or isinstance(ttl, bool)
        or not 1 <= ttl <= min(policy_ttl, 900)
        or not str(signed.get("auditEventId") or "").strip()
    ):
        raise ResearchIsolationProofError(
            "research isolation signed media TTL/audit evidence is invalid"
        )
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
        _operation(value, label=label, statuses=statuses)
        for value, label, statuses in specs
    ]
    request_ids = [str(row["requestId"]) for row in operations]
    trace_ids = [str(row["traceId"]) for row in operations]
    if len(request_ids) != len(set(request_ids)) or len(trace_ids) != len(
        set(trace_ids)
    ):
        raise ResearchIsolationProofError(
            "research isolation operation evidence is reused"
        )


__all__ = [
    "ResearchIsolationProofError",
    "validate_research_isolation_pass_proof",
]
