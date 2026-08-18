"""Identity, digest, and safe-reference primitives for reviewed closure adoption."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid
from core.source_digest import SourceDefinitionSnapshot, SourceDigestError


class ReviewedClosureAdoptionError(ValueError):
    """Reviewed-closure adoption evidence is incomplete or has drifted."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"GATE_BLOCK DATA.RELEASE.ADOPTION_{code}: {detail}")
        self.code = code


def _typed(code: str, detail: str) -> ReviewedClosureAdoptionError:
    return ReviewedClosureAdoptionError(code, detail)


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


@dataclass(frozen=True, slots=True, order=True)
class ReleaseIdentityTuple:
    """Exact immutable release identity; releaseId alone is never sufficient."""

    release_id: str
    payload_sha256: str
    canonical_merkle: str
    attestation_file_sha256: str

    @classmethod
    def from_document(cls, value: object, *, label: str) -> ReleaseIdentityTuple:
        if not isinstance(value, Mapping):
            raise _typed("IDENTITY_INVALID", f"{label} must be an object")
        required = {
            "releaseId",
            "payloadSha256",
            "canonicalMerkle",
            "attestationFileSha256",
        }
        if set(value) != required:
            raise _typed("IDENTITY_INVALID", f"{label} fields are not exact")
        identity = cls(
            release_id=str(value.get("releaseId") or ""),
            payload_sha256=str(value.get("payloadSha256") or ""),
            canonical_merkle=str(value.get("canonicalMerkle") or ""),
            attestation_file_sha256=str(value.get("attestationFileSha256") or ""),
        )
        if not identity.release_id or any(
            not _is_sha256(item)
            for item in (
                identity.payload_sha256,
                identity.canonical_merkle,
                identity.attestation_file_sha256,
            )
        ):
            raise _typed("IDENTITY_INVALID", f"{label} tuple is invalid")
        return identity

    def to_document(self) -> dict[str, str]:
        return {
            "releaseId": self.release_id,
            "payloadSha256": self.payload_sha256,
            "canonicalMerkle": self.canonical_merkle,
            "attestationFileSha256": self.attestation_file_sha256,
        }


@dataclass(frozen=True, slots=True)
class ReleaseIdentityIncident:
    incident_id: str
    release_id: str
    observed_identities: tuple[ReleaseIdentityTuple, ...]
    protected_execution_ids: tuple[str, ...]
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class ReviewedClosureAdoptionRef:
    adoption_id: str
    source_release_identity: ReleaseIdentityTuple
    source_release_root: Path
    upstream_execution_ids: tuple[str, ...]
    upstream_source_digests: tuple[str, ...]
    closure_digests: tuple[tuple[str, str], ...]
    adoption_ref_digest: str


@dataclass(frozen=True, slots=True)
class ReviewedClosureAdoptionReceipt:
    adoption_id: str
    source_release_identity: ReleaseIdentityTuple
    target_source_revision: str
    target_source_digest: str
    lane_execution_ids: tuple[str, ...]
    receipt_digest: str


def _is_sha256(value: str) -> bool:
    return (
        value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _timestamp(value: object, *, label: str) -> None:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _typed("TIMESTAMP_INVALID", f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise _typed("TIMESTAMP_INVALID", f"{label} must include a timezone")


def _safe_ref(ref: object, *, label: str) -> Path:
    relative = Path(str(ref or "").strip())
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise _typed("ROOT_DRIFT", f"{label} is not a safe output-relative ref")
    return relative


def _resolve_path(
    ref: object,
    *,
    output_root: Path,
    label: str,
    kind: str,
) -> Path:
    relative = _safe_ref(ref, label=label)
    root = output_root.resolve()
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise _typed(
            "EVIDENCE_MISSING", f"{label} is missing or outside output root"
        ) from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise _typed("ROOT_DRIFT", f"{label} traverses a symlink")
    if kind == "file" and not resolved.is_file():
        raise _typed("EVIDENCE_MISSING", f"{label} must be a regular file")
    if kind == "directory" and not resolved.is_dir():
        raise _typed("EVIDENCE_MISSING", f"{label} must be a directory")
    return resolved


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise _typed("EVIDENCE_INVALID", f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise _typed("EVIDENCE_INVALID", f"{label} must be an object")
    return value


def _validate_file_evidence(
    value: object,
    *,
    output_root: Path,
    label: str,
    expected_ref: str | None = None,
) -> Path:
    if not isinstance(value, Mapping) or set(value) != {"ref", "sha256"}:
        raise _typed("EVIDENCE_INVALID", f"{label} binding fields are invalid")
    ref = str(value.get("ref") or "")
    if expected_ref is not None and ref != expected_ref:
        raise _typed("ROOT_DRIFT", f"{label} ref differs from the canonical path")
    path = _resolve_path(ref, output_root=output_root, label=label, kind="file")
    if file_digest(path) != value.get("sha256"):
        raise _typed("DIGEST_DRIFT", f"{label} file digest drifted")
    return path


def _validate_digest_field(document: Mapping[str, Any], field: str) -> None:
    stable = {key: value for key, value in document.items() if key != field}
    if document.get(field) != canonical_digest(stable):
        raise _typed("DIGEST_DRIFT", f"{field} does not match canonical content")


def _sorted_unique_strings(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise _typed("CLOSURE_INVALID", f"{label} must be a non-empty array")
    rows = tuple(str(item or "") for item in value)
    if any(not item for item in rows) or rows != tuple(sorted(set(rows))):
        raise _typed("CLOSURE_INVALID", f"{label} must be sorted and unique")
    return rows


def _source_digests(value: object, *, label: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not value:
        raise _typed("UPSTREAM_INVALID", f"{label} must be a non-empty array")
    documents: list[dict[str, object]] = []
    for index, row in enumerate(value):
        try:
            SourceDefinitionSnapshot.from_document(row)
        except SourceDigestError as exc:
            raise _typed("UPSTREAM_INVALID", f"{label}[{index}] is invalid") from exc
        documents.append(dict(row))
    digests = tuple(str(row["digest"]) for row in documents)
    if digests != tuple(sorted(set(digests))):
        raise _typed("UPSTREAM_INVALID", f"{label} must be sorted and unique")
    return tuple(documents)


def validate_release_identity_incident(
    value: object,
    *,
    output_root: Path,
) -> ReleaseIdentityIncident:
    """Validate one append-only collision receipt and its attestation snapshots."""
    try:
        assert_valid(
            value,
            "release",
            "release_identity_incident",
            label="release identity incident",
        )
    except ValueError as exc:
        raise _typed("INCIDENT_SCHEMA_INVALID", str(exc)) from exc
    if not isinstance(value, Mapping):
        raise _typed("INCIDENT_SCHEMA_INVALID", "incident must be an object")
    document = dict(value)
    _validate_digest_field(document, "receiptDigest")
    _timestamp(document.get("recordedAt"), label="incident.recordedAt")
    release_id = str(document.get("releaseId") or "")
    rows = document.get("observedIdentities")
    if not isinstance(rows, list) or len(rows) < 2:
        raise _typed(
            "INCIDENT_INVALID", "at least two observed identities are required"
        )

    identities: list[ReleaseIdentityTuple] = []
    protected: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise _typed("INCIDENT_INVALID", f"observedIdentities[{index}] is invalid")
        identity = ReleaseIdentityTuple.from_document(
            {
                "releaseId": row.get("releaseId"),
                "payloadSha256": row.get("payloadSha256"),
                "canonicalMerkle": row.get("canonicalMerkle"),
                "attestationFileSha256": row.get("attestationFileSha256"),
            },
            label=f"observedIdentities[{index}]",
        )
        if identity.release_id != release_id:
            raise _typed("INCIDENT_INVALID", "observed releaseId differs from incident")
        executions = _sorted_unique_strings(
            row.get("executionIds"),
            label=f"observedIdentities[{index}].executionIds",
        )
        _timestamp(
            row.get("observedAt"), label=f"observedIdentities[{index}].observedAt"
        )
        acquisition_mode = str(row.get("acquisitionMode") or "")
        provenance_fields = {
            "recoveryProvenanceRef",
            "recoveryProvenanceFileSha256",
        }
        if acquisition_mode == "original_file":
            if provenance_fields.intersection(row):
                raise _typed(
                    "INCIDENT_INVALID",
                    "original-file observation cannot claim recovery provenance",
                )
        elif acquisition_mode == "deterministic_byte_reconstruction":
            if not provenance_fields.issubset(row):
                raise _typed(
                    "INCIDENT_INVALID",
                    "deterministic reconstruction requires recovery provenance",
                )
            provenance_path = _resolve_path(
                row.get("recoveryProvenanceRef"),
                output_root=output_root,
                label=f"observedIdentities[{index}].recoveryProvenanceRef",
                kind="file",
            )
            if file_digest(provenance_path) != row.get(
                "recoveryProvenanceFileSha256"
            ):
                raise _typed(
                    "DIGEST_DRIFT", "identity recovery provenance digest drifted"
                )
            from content.release.canonical.release_identity_recovery import (
                validate_release_identity_recovery_provenance,
            )

            recovery = validate_release_identity_recovery_provenance(
                _read_object(provenance_path, label="identity recovery provenance"),
                output_root=output_root,
            )
            if (
                recovery.release_id != release_id
                or recovery.artifact_file_sha256
                != identity.attestation_file_sha256
            ):
                raise _typed(
                    "INCIDENT_INVALID",
                    "identity recovery provenance does not bind the observation",
                )
        else:
            raise _typed(
                "INCIDENT_INVALID", "observation acquisitionMode is unsupported"
            )
        attestation = _resolve_path(
            row.get("attestationRef"),
            output_root=output_root,
            label=f"observedIdentities[{index}].attestationRef",
            kind="file",
        )
        if file_digest(attestation) != identity.attestation_file_sha256:
            raise _typed("DIGEST_DRIFT", "identity incident attestation digest drifted")
        attestation_document = _read_object(attestation, label="identity attestation")
        expected_fields = {
            "releaseId": identity.release_id,
            "payloadSha256": identity.payload_sha256,
            "canonicalMerkle": identity.canonical_merkle,
            "executionIds": list(executions),
        }
        if any(
            attestation_document.get(key) != item
            for key, item in expected_fields.items()
        ):
            raise _typed(
                "INCIDENT_INVALID", "identity attestation tuple/closure drifted"
            )
        identities.append(identity)
        protected.update(executions)

    identity_tuple = tuple(identities)
    if identity_tuple != tuple(sorted(set(identity_tuple))):
        raise _typed(
            "INCIDENT_INVALID", "observed identities must be sorted and unique"
        )
    payload_identities = {
        (item.payload_sha256, item.canonical_merkle) for item in identity_tuple
    }
    if len(payload_identities) < 2:
        raise _typed(
            "INCIDENT_INVALID",
            "identity collision requires two distinct payload/canonical tuples",
        )
    protected_ids = tuple(sorted(protected))
    if document.get("protectedExecutionIds") != list(protected_ids):
        raise _typed(
            "INCIDENT_INVALID",
            "protectedExecutionIds must equal the observed execution closure",
        )
    return ReleaseIdentityIncident(
        incident_id=str(document.get("incidentId") or ""),
        release_id=release_id,
        observed_identities=identity_tuple,
        protected_execution_ids=protected_ids,
        receipt_digest=str(document["receiptDigest"]),
    )


__all__ = [
    "ReleaseIdentityIncident",
    "ReleaseIdentityTuple",
    "ReviewedClosureAdoptionError",
    "ReviewedClosureAdoptionReceipt",
    "ReviewedClosureAdoptionRef",
    "_is_sha256",
    "_read_object",
    "_resolve_path",
    "_safe_ref",
    "_sorted_unique_strings",
    "_source_digests",
    "_timestamp",
    "_typed",
    "_validate_digest_field",
    "_validate_file_evidence",
    "canonical_digest",
    "file_digest",
    "validate_release_identity_incident",
]
