"""Validation contract for deterministic release-attestation recovery."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from content.execution.closure.adoption_identity import (
    _is_sha256,
    _read_object,
    _resolve_path,
    _safe_ref,
    _sorted_unique_strings,
    _timestamp,
    _typed,
    _validate_digest_field,
    canonical_digest,
    file_digest,
)
from core.schema import assert_valid

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
SERIALIZATION_CONTRACT = "json_utf8_sorted_keys_compact_lf"
HISTORICAL_WRITER_SOURCE_REFS = tuple(
    sorted(
        {
            "quwoquan_data/scripts/content/release/canonical/aggregate_release.py",
            "quwoquan_data/scripts/content/release/canonical/object_transaction_contract.py",
            "quwoquan_data/scripts/content/release/canonical/release_attestation.py",
            "quwoquan_data/schema/release/release_attestation.schema.json",
        }
    )
)


@dataclass(frozen=True, slots=True)
class ReleaseIdentityRecoveryProvenance:
    recovery_id: str
    release_id: str
    artifact_path: Path
    artifact_file_sha256: str
    receipt_digest: str


def safe_id(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_ID.fullmatch(normalized):
        raise _typed("RECOVERY_SCHEMA_INVALID", f"{label} is not a safe identifier")
    return normalized


def parsed_timestamp(value: object, *, label: str) -> datetime:
    _timestamp(value, label=label)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def canonical_attestation_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def artifact_identity(
    document: Mapping[str, Any],
    *,
    release_id: str,
) -> dict[str, object]:
    execution_ids = _sorted_unique_strings(
        document.get("executionIds"), label="recoveredAttestation.executionIds"
    )
    recorded_at = str(document.get("recordedAt") or "")
    _timestamp(recorded_at, label="recoveredAttestation.recordedAt")
    payload_sha256 = str(document.get("payloadSha256") or "")
    canonical_merkle = str(document.get("canonicalMerkle") or "")
    if (
        document.get("releaseId") != release_id
        or not _is_sha256(payload_sha256)
        or not _is_sha256(canonical_merkle)
    ):
        raise _typed(
            "RECOVERY_INPUT_INVALID",
            "recovered attestation identity fields are invalid",
        )
    return {
        "releaseId": release_id,
        "payloadSha256": payload_sha256,
        "canonicalMerkle": canonical_merkle,
        "executionIds": list(execution_ids),
        "recordedAt": recorded_at,
    }


def recovery_root(
    *,
    output_root: Path,
    release_id: str,
    recovery_id: str,
) -> Path:
    return (
        output_root
        / "data/local/release-identity-recoveries"
        / safe_id(release_id, label="releaseId")
        / safe_id(recovery_id, label="recoveryId")
    )


def recovery_provenance_path(
    *,
    output_root: Path,
    release_id: str,
    recovery_id: str,
) -> Path:
    return recovery_root(
        output_root=output_root,
        release_id=release_id,
        recovery_id=recovery_id,
    ) / "provenance.json"


def evidence_ref(root_ref: str, digest: str) -> str:
    return f"{root_ref}/evidence/{digest.removeprefix('sha256:')}"


def candidate_count(*, start_at: str, end_at: str) -> int:
    start = parsed_timestamp(start_at, label="candidateSearch.startAt")
    end = parsed_timestamp(end_at, label="candidateSearch.endAt")
    if end < start:
        raise _typed("RECOVERY_SEARCH_INVALID", "candidate search end precedes start")
    delta = end - start
    count = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
        + 1
    )
    if count > 1_000_000:
        raise _typed(
            "RECOVERY_SEARCH_INVALID", "candidate search exceeds one million values"
        )
    return count


def matching_recorded_at_values(
    document: Mapping[str, Any],
    *,
    target_digest: str,
    start_at: str,
    end_at: str,
) -> list[str]:
    start = parsed_timestamp(start_at, label="candidateSearch.startAt")
    count = candidate_count(start_at=start_at, end_at=end_at)
    matches: list[str] = []
    for offset in range(count):
        candidate = dict(document)
        candidate["recordedAt"] = (start + timedelta(microseconds=offset)).isoformat()
        digest = "sha256:" + hashlib.sha256(
            canonical_attestation_bytes(candidate)
        ).hexdigest()
        if digest == target_digest:
            matches.append(str(candidate["recordedAt"]))
    return matches


def _canonical_recovery_ref(
    *,
    output_root: Path,
    release_id: str,
    recovery_id: str,
) -> str:
    return recovery_root(
        output_root=output_root,
        release_id=release_id,
        recovery_id=recovery_id,
    ).relative_to(output_root).as_posix()


def _validated_snapshot(
    *,
    ref: object,
    digest: object,
    expected_ref: str,
    output_root: Path,
    label: str,
) -> Path:
    if ref != expected_ref:
        raise _typed("ROOT_DRIFT", f"{label} is not content addressed")
    path = _resolve_path(
        expected_ref,
        output_root=output_root,
        label=label,
        kind="file",
    )
    if file_digest(path) != digest:
        raise _typed("DIGEST_DRIFT", f"{label} drifted")
    return path


def _validate_writer_sources(
    value: object,
    *,
    root_ref: str,
    output_root: Path,
) -> None:
    if not isinstance(value, list):
        raise _typed("RECOVERY_INPUT_INVALID", "historical writer sources are invalid")
    logical_refs: list[str] = []
    digests: list[str] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise _typed(
                "RECOVERY_INPUT_INVALID", f"historicalWriterSources[{index}] is invalid"
            )
        logical_ref = _safe_ref(
            row.get("logicalRef"), label=f"historicalWriterSources[{index}].logicalRef"
        ).as_posix()
        digest = str(row.get("fileSha256") or "")
        _validated_snapshot(
            ref=row.get("snapshotRef"),
            digest=digest,
            expected_ref=evidence_ref(root_ref, digest),
            output_root=output_root,
            label=f"historicalWriterSources[{index}].snapshotRef",
        )
        logical_refs.append(logical_ref)
        digests.append(digest)
    if (
        tuple(logical_refs) != HISTORICAL_WRITER_SOURCE_REFS
        or len(set(digests)) != len(digests)
    ):
        raise _typed(
            "RECOVERY_INPUT_INVALID",
            "historical writer source closure is not exact and unique",
        )


def _validate_template_projection(
    reconstruction: Mapping[str, Any],
    *,
    artifact_document: Mapping[str, Any],
    root_ref: str,
    output_root: Path,
) -> None:
    digest = str(reconstruction.get("templateAttestationFileSha256") or "")
    template_path = _validated_snapshot(
        ref=reconstruction.get("templateAttestationRef"),
        digest=digest,
        expected_ref=evidence_ref(root_ref, digest),
        output_root=output_root,
        label="reconstruction.templateAttestationRef",
    )
    template = _read_object(template_path, label="template attestation")
    replacements = reconstruction.get("fieldReplacements")
    expected_replacements = {
        "payloadSha256": artifact_document.get("payloadSha256"),
        "canonicalMerkle": artifact_document.get("canonicalMerkle"),
        "recordedAt": artifact_document.get("recordedAt"),
    }
    if replacements != expected_replacements:
        raise _typed("RECOVERY_INPUT_INVALID", "field replacements are not exact")
    projected = dict(template)
    projected.update(expected_replacements)
    if projected != dict(artifact_document):
        raise _typed(
            "RECOVERY_INPUT_INVALID",
            "template plus field replacements differs from recovered attestation",
        )


def _validate_candidate_search(
    reconstruction: Mapping[str, Any],
    *,
    artifact_document: Mapping[str, Any],
    artifact_digest: str,
    recovered_value: str,
) -> None:
    search = reconstruction.get("candidateSearch")
    if not isinstance(search, Mapping):
        raise _typed("RECOVERY_SEARCH_INVALID", "candidate search must be an object")
    start_at = str(search.get("startAt") or "")
    end_at = str(search.get("endAt") or "")
    count = candidate_count(start_at=start_at, end_at=end_at)
    recovered_time = parsed_timestamp(
        recovered_value, label="reconstruction.recoveredValue"
    )
    start_time = parsed_timestamp(start_at, label="candidateSearch.startAt")
    end_time = parsed_timestamp(end_at, label="candidateSearch.endAt")
    if (
        search.get("granularity") != "microsecond"
        or search.get("stepMicros") != 1
        or search.get("candidateCount") != count
        or search.get("matchedCandidateCount") != 1
        or not start_time <= recovered_time <= end_time
    ):
        raise _typed("RECOVERY_SEARCH_INVALID", "candidate search proof is inconsistent")
    if matching_recorded_at_values(
        artifact_document,
        target_digest=artifact_digest,
        start_at=start_at,
        end_at=end_at,
    ) != [recovered_value]:
        raise _typed(
            "RECOVERY_SEARCH_INVALID",
            "candidate search does not reproduce one unique recovered value",
        )


def _validate_independent_evidence(
    value: object,
    *,
    root_ref: str,
    output_root: Path,
    identity: Mapping[str, object],
    artifact_digest: str,
) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise _typed(
            "RECOVERY_EVIDENCE_INVALID",
            "exactly two independent evidence snapshots are required",
        )
    roles: list[str] = []
    digests: list[str] = []
    evidence_text: dict[str, str] = {}
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise _typed(
                "RECOVERY_EVIDENCE_INVALID", f"independentEvidence[{index}] is invalid"
            )
        role = str(row.get("role") or "")
        digest = str(row.get("fileSha256") or "")
        evidence = _validated_snapshot(
            ref=row.get("ref"),
            digest=digest,
            expected_ref=evidence_ref(root_ref, digest),
            output_root=output_root,
            label=f"independentEvidence[{index}]",
        )
        try:
            evidence_text[role] = evidence.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise _typed(
                "RECOVERY_EVIDENCE_INVALID", f"independent evidence {role} is not text"
            ) from exc
        roles.append(role)
        digests.append(digest)
    if (
        roles != ["execution_closure", "release_identity"]
        or len(set(digests)) != len(digests)
    ):
        raise _typed(
            "RECOVERY_EVIDENCE_INVALID",
            "independent evidence roles and file digests must be exact and unique",
        )
    if (
        artifact_digest not in evidence_text["release_identity"]
        or str(identity["payloadSha256"]) not in evidence_text["release_identity"]
    ):
        raise _typed(
            "RECOVERY_EVIDENCE_INVALID",
            "release-identity evidence does not contain the target tuple",
        )
    closure_evidence = evidence_text["execution_closure"]
    if str(identity["canonicalMerkle"]) not in closure_evidence or any(
        execution_id not in closure_evidence
        for execution_id in identity["executionIds"]
    ):
        raise _typed(
            "RECOVERY_EVIDENCE_INVALID",
            "execution-closure evidence does not contain the target closure",
        )


def validate_release_identity_recovery_provenance(
    value: object,
    *,
    output_root: Path,
) -> ReleaseIdentityRecoveryProvenance:
    """Validate recovered bytes and every input needed to reproduce them."""

    try:
        assert_valid(
            value,
            "release",
            "release_identity_recovery_provenance",
            label="release identity recovery provenance",
        )
    except ValueError as exc:
        raise _typed("RECOVERY_SCHEMA_INVALID", str(exc)) from exc
    if not isinstance(value, Mapping):
        raise _typed("RECOVERY_SCHEMA_INVALID", "recovery provenance must be an object")
    document = dict(value)
    _validate_digest_field(document, "receiptDigest")
    _timestamp(document.get("recordedAt"), label="recovery.recordedAt")
    release_id = safe_id(str(document.get("releaseId") or ""), label="releaseId")
    recovery_id = safe_id(str(document.get("recoveryId") or ""), label="recoveryId")
    root_ref = _canonical_recovery_ref(
        output_root=output_root,
        release_id=release_id,
        recovery_id=recovery_id,
    )
    expected_artifact_ref = f"{root_ref}/artifact/attestation.json"
    if document.get("artifactRef") != expected_artifact_ref:
        raise _typed("ROOT_DRIFT", "recovered artifact ref is not canonical")
    artifact = _resolve_path(
        expected_artifact_ref,
        output_root=output_root,
        label="recovery.artifactRef",
        kind="file",
    )
    artifact_digest = file_digest(artifact)
    if (
        artifact_digest != document.get("artifactFileSha256")
        or artifact_digest != document.get("targetAttestationFileSha256")
    ):
        raise _typed("DIGEST_DRIFT", "recovered artifact does not match target digest")
    artifact_document = _read_object(artifact, label="recovered attestation")
    identity = artifact_identity(artifact_document, release_id=release_id)
    if document.get("artifactIdentity") != identity:
        raise _typed("RECOVERY_INPUT_INVALID", "artifact identity projection drifted")
    if artifact.read_bytes() != canonical_attestation_bytes(artifact_document):
        raise _typed(
            "RECOVERY_BYTES_DRIFT",
            "artifact bytes do not match the frozen serialization contract",
        )
    reconstruction = document.get("reconstruction")
    if not isinstance(reconstruction, Mapping):
        raise _typed("RECOVERY_SCHEMA_INVALID", "reconstruction must be an object")
    if reconstruction.get("semanticInputSha256") != canonical_digest(
        artifact_document
    ):
        raise _typed("DIGEST_DRIFT", "semantic reconstruction input drifted")
    if not _REVISION.fullmatch(str(reconstruction.get("writerRevision") or "")):
        raise _typed("RECOVERY_INPUT_INVALID", "writer revision must be a full commit")
    _validate_writer_sources(
        reconstruction.get("historicalWriterSources"),
        root_ref=root_ref,
        output_root=output_root,
    )
    _validate_template_projection(
        reconstruction,
        artifact_document=artifact_document,
        root_ref=root_ref,
        output_root=output_root,
    )
    recovered_value = str(reconstruction.get("recoveredValue") or "")
    _timestamp(recovered_value, label="reconstruction.recoveredValue")
    if recovered_value != identity["recordedAt"]:
        raise _typed("RECOVERY_INPUT_INVALID", "recovered value differs from artifact")
    _validate_candidate_search(
        reconstruction,
        artifact_document=artifact_document,
        artifact_digest=artifact_digest,
        recovered_value=recovered_value,
    )
    _validate_independent_evidence(
        document.get("independentEvidence"),
        root_ref=root_ref,
        output_root=output_root,
        identity=identity,
        artifact_digest=artifact_digest,
    )
    return ReleaseIdentityRecoveryProvenance(
        recovery_id=recovery_id,
        release_id=release_id,
        artifact_path=artifact,
        artifact_file_sha256=artifact_digest,
        receipt_digest=str(document["receiptDigest"]),
    )


__all__ = [
    "HISTORICAL_WRITER_SOURCE_REFS",
    "ReleaseIdentityRecoveryProvenance",
    "SERIALIZATION_CONTRACT",
    "artifact_identity",
    "candidate_count",
    "canonical_attestation_bytes",
    "evidence_ref",
    "matching_recorded_at_values",
    "parsed_timestamp",
    "recovery_provenance_path",
    "recovery_root",
    "safe_id",
    "validate_release_identity_recovery_provenance",
]
