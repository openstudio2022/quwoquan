"""Append-only migration for incidents created before provenance classification.

The source incident and its attestation snapshots remain immutable.  This
module accepts only the exact closed-world legacy shape that predates the
current incident/recovery contract, then writes a source-bound current-schema
projection in a separate create-once namespace.
"""

from __future__ import annotations

import fcntl
import json
import re
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.closure.adoption_contract import (
    ReleaseIdentityIncident,
    canonical_digest,
    file_digest,
    validate_release_identity_incident,
)
from content.release.canonical.release_identity_incident import incident_path
from core.io import read_json, write_json
from core.paths import (
    OUTPUT_ROOT,
    RELEASE_IDENTITY_INCIDENT_MIGRATIONS_ROOT,
    RELEASE_IDENTITY_INCIDENTS_ROOT,
    REPO_ROOT,
)
from core.schema import assert_valid

MIGRATION_ID = "legacy-original-file-v1"
CONTRACT_BOUNDARY_COMMIT = "1810945435a567e099a480f153326ac6f489317f"
CONTRACT_BOUNDARY_AT = "2026-08-06T15:04:03+00:00"
CONTRACT_SCHEMA_REF = (
    "quwoquan_data/schema/release/release_identity_incident.schema.json"
)
CONTRACT_SCHEMA_FILE_SHA256 = (
    "sha256:97243c06169a8964ef077cc13c90ffbb071866a956f8ba00e6635650bba4f018"
)
LEGACY_INCIDENT_PREFIX = "data/local/release-identity-incidents"
CURRENT_INCIDENT_PREFIX = "data/local/workspace/release-identity-incidents"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_LEGACY_INCIDENT_FIELDS = {
    "schema",
    "incidentId",
    "releaseId",
    "status",
    "storageClass",
    "observedIdentities",
    "protectedExecutionIds",
    "recordedAt",
    "receiptDigest",
}
_LEGACY_OBSERVATION_FIELDS = {
    "releaseId",
    "payloadSha256",
    "canonicalMerkle",
    "attestationFileSha256",
    "attestationRef",
    "executionIds",
    "observedAt",
}
_RECOVERY_FIELDS = {
    "acquisitionMode",
    "recoveryProvenanceRef",
    "recoveryProvenanceFileSha256",
}


def _safe_id(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_ID.fullmatch(normalized):
        raise ValueError(f"{label} is not a safe identifier")
    return normalized


def _parsed_timestamp(value: object, *, label: str) -> datetime:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _require_pre_boundary(value: object, *, label: str) -> None:
    if _parsed_timestamp(value, label=label) >= _parsed_timestamp(
        CONTRACT_BOUNDARY_AT,
        label="contractBoundary.committedAt",
    ):
        raise ValueError(f"{label} does not predate the current incident contract")


def _sorted_strings(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty array")
    rows = tuple(str(item or "") for item in value)
    if any(not item for item in rows) or rows != tuple(sorted(set(rows))):
        raise ValueError(f"{label} must be sorted and unique")
    return rows


def migration_root(
    *,
    output_root: Path,
    release_id: str,
    incident_id: str,
) -> Path:
    return (
        output_root.resolve()
        / RELEASE_IDENTITY_INCIDENT_MIGRATIONS_ROOT.relative_to(OUTPUT_ROOT)
        / _safe_id(release_id, label="releaseId")
        / _safe_id(incident_id, label="incidentId")
        / MIGRATION_ID
    )


@contextmanager
def _migration_lock(root: Path) -> Iterator[None]:
    root.parent.mkdir(parents=True, exist_ok=True)
    lock_path = root.parent / f".{MIGRATION_ID}.lock"
    if lock_path.is_symlink():
        raise ValueError("legacy incident migration lock cannot be a symlink")
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=False,
        capture_output=True,
    )


def _verify_contract_introduction(repo_root: Path) -> None:
    commit = _run_git(repo_root, "show", "-s", "--format=%H%n%cI", CONTRACT_BOUNDARY_COMMIT)
    if commit.returncode != 0:
        raise ValueError("incident contract boundary commit is unavailable")
    lines = commit.stdout.decode("utf-8").strip().splitlines()
    if lines != [
        CONTRACT_BOUNDARY_COMMIT,
        "2026-08-06T23:04:03+08:00",
    ]:
        raise ValueError("incident contract boundary commit identity drifted")
    predecessor = _run_git(
        repo_root,
        "cat-file",
        "-e",
        f"{CONTRACT_BOUNDARY_COMMIT}^:{CONTRACT_SCHEMA_REF}",
    )
    if predecessor.returncode == 0:
        raise ValueError("incident schema unexpectedly existed before contract boundary")
    introduced = _run_git(
        repo_root,
        "show",
        f"{CONTRACT_BOUNDARY_COMMIT}:{CONTRACT_SCHEMA_REF}",
    )
    if introduced.returncode != 0:
        raise ValueError("introduced incident schema snapshot is unavailable")
    digest = "sha256:" + __import__("hashlib").sha256(introduced.stdout).hexdigest()
    if digest != CONTRACT_SCHEMA_FILE_SHA256:
        raise ValueError("introduced incident schema snapshot digest drifted")


def _safe_existing_file(path: Path, *, root: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    resolved = path.resolve(strict=True)
    resolved.relative_to(root.resolve())
    current = root.resolve()
    relative = resolved.relative_to(current)
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} traverses a symlink")
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _legacy_source(
    source_incident_path: Path,
    *,
    output_root: Path,
    expected_file_sha256: str | None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    root = output_root.resolve()
    source_path = _safe_existing_file(
        source_incident_path,
        root=root,
        label="source incident",
    )
    source_digest = file_digest(source_path)
    if expected_file_sha256 is not None and source_digest != expected_file_sha256:
        raise ValueError("source incident file digest differs from required digest")
    value = read_json(source_path)
    if not isinstance(value, dict) or set(value) != _LEGACY_INCIDENT_FIELDS:
        raise ValueError("source incident is not the exact pre-contract legacy shape")
    source = dict(value)
    if (
        source.get("schema") != "quwoquan_data.release_identity_incident"
        or source.get("status") != "identity_collided"
        or source.get("storageClass") != "append_only_create_once"
    ):
        raise ValueError("legacy incident header is invalid")
    if source.get("receiptDigest") != canonical_digest(
        {key: item for key, item in source.items() if key != "receiptDigest"}
    ):
        raise ValueError("legacy incident receiptDigest drifted")
    _require_pre_boundary(source.get("recordedAt"), label="incident.recordedAt")
    release_id = _safe_id(source.get("releaseId"), label="releaseId")
    incident_id = _safe_id(source.get("incidentId"), label="incidentId")
    expected_source = incident_path(
        output_root=root,
        release_id=release_id,
        incident_id=incident_id,
    )
    if source_path != expected_source.resolve(strict=True):
        raise ValueError("legacy incident is outside its canonical current location")
    rows = source.get("observedIdentities")
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("legacy incident requires at least two observations")

    projection_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    identities: list[tuple[str, str, str, str]] = []
    protected: set[str] = set()
    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, Mapping):
            raise ValueError(f"legacy observation {index} must be an object")
        row = dict(raw_row)
        if set(row) != _LEGACY_OBSERVATION_FIELDS:
            if _RECOVERY_FIELDS.intersection(row):
                raise ValueError(
                    "legacy observation has deterministic-recovery ambiguity"
                )
            raise ValueError("legacy observation fields are not exact")
        _require_pre_boundary(row.get("observedAt"), label=f"observation[{index}].observedAt")
        if row.get("releaseId") != release_id:
            raise ValueError("legacy observation releaseId drifted")
        payload = str(row.get("payloadSha256") or "")
        merkle = str(row.get("canonicalMerkle") or "")
        attestation_digest = str(row.get("attestationFileSha256") or "")
        if not all(_SHA256.fullmatch(item) for item in (payload, merkle, attestation_digest)):
            raise ValueError("legacy observation identity digest is invalid")
        executions = _sorted_strings(
            row.get("executionIds"),
            label=f"observation[{index}].executionIds",
        )
        legacy_ref = str(row.get("attestationRef") or "")
        expected_legacy_ref = (
            f"{LEGACY_INCIDENT_PREFIX}/{release_id}/{incident_id}/evidence/"
            f"{attestation_digest.removeprefix('sha256:')}.json"
        )
        if legacy_ref != expected_legacy_ref:
            raise ValueError("legacy attestationRef is not the exact old namespace")
        normalized_ref = (
            f"{CURRENT_INCIDENT_PREFIX}/{release_id}/{incident_id}/evidence/"
            f"{attestation_digest.removeprefix('sha256:')}.json"
        )
        evidence_path = _safe_existing_file(
            root / normalized_ref,
            root=root,
            label=f"observation[{index}] evidence",
        )
        if file_digest(evidence_path) != attestation_digest:
            raise ValueError("legacy observation evidence digest drifted")
        attestation = read_json(evidence_path)
        if not isinstance(attestation, Mapping):
            raise ValueError("legacy observation evidence must be an object")
        expected_identity = {
            "releaseId": release_id,
            "payloadSha256": payload,
            "canonicalMerkle": merkle,
            "executionIds": list(executions),
        }
        if any(attestation.get(key) != item for key, item in expected_identity.items()):
            raise ValueError("legacy observation evidence identity/closure drifted")
        if attestation.get("schema") != "quwoquan_data.release_attestation":
            raise ValueError("legacy observation evidence is not a release attestation")
        _require_pre_boundary(
            attestation.get("recordedAt"),
            label=f"observation[{index}].attestation.recordedAt",
        )
        projection_rows.append(
            {
                **row,
                "attestationRef": normalized_ref,
                "acquisitionMode": "original_file",
            }
        )
        evidence_rows.append(
            {
                "sourceRef": legacy_ref,
                "normalizedRef": normalized_ref,
                "fileSha256": attestation_digest,
                **expected_identity,
            }
        )
        identities.append((release_id, payload, merkle, attestation_digest))
        protected.update(executions)
    if identities != sorted(set(identities)):
        raise ValueError("legacy observations must be sorted and unique")
    if len({(row[1], row[2]) for row in identities}) < 2:
        raise ValueError("legacy incident does not contain two conflicting identities")
    if source.get("protectedExecutionIds") != sorted(protected):
        raise ValueError("legacy protected execution closure drifted")
    projection_stable = {
        **{key: item for key, item in source.items() if key not in {"observedIdentities", "receiptDigest"}},
        "observedIdentities": projection_rows,
    }
    projection = {
        **projection_stable,
        "receiptDigest": canonical_digest(projection_stable),
    }
    return source, projection, evidence_rows


def _boundary_document() -> dict[str, object]:
    return {
        "commit": CONTRACT_BOUNDARY_COMMIT,
        "committedAt": CONTRACT_BOUNDARY_AT,
        "schemaRef": CONTRACT_SCHEMA_REF,
        "schemaFileSha256": CONTRACT_SCHEMA_FILE_SHA256,
        "predecessorSchemaAbsent": True,
    }


def _portable_ref(path: Path, *, output_root: Path) -> str:
    return path.resolve().relative_to(output_root.resolve()).as_posix()


def load_validated_legacy_incident_projection(
    source_incident_path: Path,
    *,
    output_root: Path,
) -> ReleaseIdentityIncident:
    root = output_root.resolve()
    source_value = read_json(source_incident_path)
    if not isinstance(source_value, Mapping):
        raise ValueError("legacy incident source must be an object")
    release_id = _safe_id(source_value.get("releaseId"), label="releaseId")
    incident_id = _safe_id(source_value.get("incidentId"), label="incidentId")
    migration = migration_root(
        output_root=root,
        release_id=release_id,
        incident_id=incident_id,
    )
    receipt_path = _safe_existing_file(
        migration / "migration_receipt.json",
        root=root,
        label="legacy incident migration receipt",
    )
    receipt = read_json(receipt_path)
    assert_valid(
        receipt,
        "release",
        "release_identity_incident_legacy_migration",
        label="legacy incident migration receipt",
    )
    if not isinstance(receipt, dict):
        raise ValueError("legacy incident migration receipt must be an object")
    if receipt.get("receiptDigest") != canonical_digest(
        {key: item for key, item in receipt.items() if key != "receiptDigest"}
    ):
        raise ValueError("legacy incident migration receiptDigest drifted")
    source_binding = receipt["sourceIncident"]
    if source_binding.get("ref") != _portable_ref(
        source_incident_path,
        output_root=root,
    ):
        raise ValueError("legacy incident migration source ref drifted")
    source, expected_projection, expected_evidence = _legacy_source(
        source_incident_path,
        output_root=root,
        expected_file_sha256=str(source_binding.get("fileSha256") or ""),
    )
    if (
        receipt.get("releaseId") != release_id
        or receipt.get("incidentId") != incident_id
        or receipt.get("migrationId") != MIGRATION_ID
        or receipt.get("contractBoundary") != _boundary_document()
        or receipt.get("classification")
        != {
            "acquisitionMode": "original_file",
            "basis": "pre_contract_original_snapshot_closed_world",
            "recoveryFieldsAbsent": True,
        }
        or receipt.get("evidenceSnapshots") != expected_evidence
        or source_binding.get("receiptDigest") != source.get("receiptDigest")
        or source_binding.get("recordedAt") != source.get("recordedAt")
    ):
        raise ValueError("legacy incident migration source binding drifted")
    projection_binding = receipt["projection"]
    expected_projection_path = migration / "incident_projection.json"
    if projection_binding.get("ref") != _portable_ref(
        expected_projection_path,
        output_root=root,
    ):
        raise ValueError("legacy incident migration projection ref drifted")
    projection_path = _safe_existing_file(
        expected_projection_path,
        root=root,
        label="legacy incident migration projection",
    )
    if file_digest(projection_path) != projection_binding.get("fileSha256"):
        raise ValueError("legacy incident migration projection file drifted")
    projection = read_json(projection_path)
    if (
        projection != expected_projection
        or projection_binding.get("receiptDigest") != projection.get("receiptDigest")
    ):
        raise ValueError("legacy incident migration projection content drifted")
    return validate_release_identity_incident(projection, output_root=root)


def migrate_legacy_release_identity_incident(
    *,
    source_incident_path: Path,
    source_incident_file_sha256: str,
    output_root: Path,
    repo_root: Path = REPO_ROOT,
) -> tuple[dict[str, Any], Path]:
    if not _SHA256.fullmatch(source_incident_file_sha256):
        raise ValueError("source incident sha256 must use canonical sha256:<hex>")
    _verify_contract_introduction(repo_root.resolve())
    root = output_root.resolve()
    source, projection, evidence_rows = _legacy_source(
        source_incident_path,
        output_root=root,
        expected_file_sha256=source_incident_file_sha256,
    )
    release_id = str(source["releaseId"])
    incident_id = str(source["incidentId"])
    final_root = migration_root(
        output_root=root,
        release_id=release_id,
        incident_id=incident_id,
    )
    receipt_path = final_root / "migration_receipt.json"
    with _migration_lock(final_root):
        if final_root.is_symlink():
            raise ValueError("legacy incident migration root cannot be a symlink")
        if receipt_path.is_file():
            load_validated_legacy_incident_projection(
                source_incident_path,
                output_root=root,
            )
            existing = read_json(receipt_path)
            if existing["sourceIncident"]["fileSha256"] != source_incident_file_sha256:
                raise ValueError("legacy incident migration create-once conflict")
            return existing, receipt_path
        if final_root.exists():
            raise ValueError("incomplete legacy incident migration root exists")
        final_root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{MIGRATION_ID}-",
            dir=final_root.parent,
        ) as temporary:
            stage = Path(temporary)
            projection_path = stage / "incident_projection.json"
            write_json(projection_path, projection)
            stable = {
                "schema": "quwoquan_data.release_identity_incident_legacy_migration",
                "migrationId": MIGRATION_ID,
                "releaseId": release_id,
                "incidentId": incident_id,
                "status": "migrated",
                "storageClass": "append_only_create_once",
                "sourceIncident": {
                    "ref": _portable_ref(source_incident_path, output_root=root),
                    "fileSha256": source_incident_file_sha256,
                    "receiptDigest": source["receiptDigest"],
                    "recordedAt": source["recordedAt"],
                },
                "contractBoundary": _boundary_document(),
                "classification": {
                    "acquisitionMode": "original_file",
                    "basis": "pre_contract_original_snapshot_closed_world",
                    "recoveryFieldsAbsent": True,
                },
                "evidenceSnapshots": evidence_rows,
                "projection": {
                    "ref": _portable_ref(
                        final_root / "incident_projection.json",
                        output_root=root,
                    ),
                    "fileSha256": file_digest(projection_path),
                    "receiptDigest": projection["receiptDigest"],
                },
                "recordedAt": datetime.now(timezone.utc).isoformat(),
            }
            receipt = {**stable, "receiptDigest": canonical_digest(stable)}
            assert_valid(
                receipt,
                "release",
                "release_identity_incident_legacy_migration",
                label="legacy incident migration receipt",
            )
            write_json(stage / "migration_receipt.json", receipt)
            stage.replace(final_root)
    load_validated_legacy_incident_projection(
        source_incident_path,
        output_root=root,
    )
    return receipt, receipt_path


__all__ = [
    "CONTRACT_BOUNDARY_AT",
    "CONTRACT_BOUNDARY_COMMIT",
    "MIGRATION_ID",
    "load_validated_legacy_incident_projection",
    "migrate_legacy_release_identity_incident",
    "migration_root",
]
