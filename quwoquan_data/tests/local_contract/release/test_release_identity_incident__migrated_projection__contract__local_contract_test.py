"""GC protection consumes the create-once migrated projection of a pre-contract incident."""

from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.closure.adoption_contract import canonical_digest, file_digest
from content.release.canonical.garbage_collection_protection import (
    release_identity_incident_refs,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core.io import read_json, write_json

RELEASE_ID = "pre-contract-collided-release"
INCIDENT_ID = "pre-contract-collision-001"
MIGRATION_DIR = "original-file-v1"
EXECUTIONS = ("execution-1", "execution-2")
RECORDED_AT = "2026-08-05T03:47:16+00:00"


def _incident_path(output_root: Path) -> Path:
    return (
        output_root
        / "data/local/workspace/release-identity-incidents"
        / RELEASE_ID
        / INCIDENT_ID
        / "incident.json"
    )


def _with_digest(document: dict[str, object]) -> dict[str, object]:
    stable = {key: value for key, value in document.items() if key != "receiptDigest"}
    return {**stable, "receiptDigest": canonical_digest(stable)}


def _write_pre_contract_incident_with_projection(output_root: Path) -> Path:
    """Write the immutable pre-contract incident plus its migrated projection."""

    incident_path = _incident_path(output_root)
    source_rows: list[dict[str, object]] = []
    projection_rows: list[dict[str, object]] = []
    for index, digest_character in enumerate(("a", "b"), start=1):
        attestation = {
            "schema": "quwoquan_data.release_attestation",
            "releaseId": RELEASE_ID,
            "payloadSha256": "sha256:" + digest_character * 64,
            "canonicalMerkle": "sha256:" + str(index) * 64,
            "executionIds": list(EXECUTIONS),
            "recordedAt": "2026-08-03T19:27:08+00:00",
        }
        staged = output_root / f"attestation-{index}.json"
        write_json(staged, attestation)
        digest = file_digest(staged)
        evidence_ref = (
            "data/local/workspace/release-identity-incidents/"
            f"{RELEASE_ID}/{INCIDENT_ID}/evidence/{digest[7:]}.json"
        )
        write_json(output_root / evidence_ref, attestation)
        staged.unlink()
        identity = {
            "releaseId": RELEASE_ID,
            "payloadSha256": attestation["payloadSha256"],
            "canonicalMerkle": attestation["canonicalMerkle"],
            "attestationFileSha256": digest,
            "executionIds": list(EXECUTIONS),
            "observedAt": RECORDED_AT,
        }
        source_rows.append(
            {
                **identity,
                "attestationRef": (
                    "data/local/release-identity-incidents/"
                    f"{RELEASE_ID}/{INCIDENT_ID}/evidence/{digest[7:]}.json"
                ),
            }
        )
        projection_rows.append(
            {
                **identity,
                "attestationRef": evidence_ref,
                "acquisitionMode": "original_file",
            }
        )

    header = {
        "schema": "quwoquan_data.release_identity_incident",
        "incidentId": INCIDENT_ID,
        "releaseId": RELEASE_ID,
        "status": "identity_collided",
        "storageClass": "append_only_create_once",
        "protectedExecutionIds": list(EXECUTIONS),
        "recordedAt": RECORDED_AT,
    }
    write_json(
        incident_path,
        _with_digest({**header, "observedIdentities": source_rows}),
    )

    migration_root = (
        output_root
        / "data/local/workspace/release-identity-incident-migrations"
        / RELEASE_ID
        / INCIDENT_ID
        / MIGRATION_DIR
    )
    write_json(
        migration_root / "incident_projection.json",
        _with_digest({**header, "observedIdentities": projection_rows}),
    )
    write_json(
        migration_root / "migration_receipt.json",
        {
            "releaseId": RELEASE_ID,
            "incidentId": INCIDENT_ID,
            "status": "migrated",
            "sourceIncident": {
                "ref": incident_path.relative_to(output_root).as_posix(),
                "fileSha256": file_digest(incident_path),
            },
        },
    )
    return incident_path


def test_migrated_projection_protects_gc_refs(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _write_pre_contract_incident_with_projection(output_root)

    releases, executions = release_identity_incident_refs(output_root)

    assert releases == {RELEASE_ID}
    assert executions == set(EXECUTIONS)


def test_migrated_projection_fails_closed_on_source_drift(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    incident_path = _write_pre_contract_incident_with_projection(output_root)
    document = read_json(incident_path)
    document["recordedAt"] = "2026-08-05T03:47:17+00:00"
    write_json(incident_path, _with_digest(document))

    with pytest.raises(ObjectTransactionError, match="IDENTITY_INCIDENT_INVALID"):
        release_identity_incident_refs(output_root)


def test_migrated_projection_fails_closed_on_projection_tamper(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _write_pre_contract_incident_with_projection(output_root)
    projection_path = (
        output_root
        / "data/local/workspace/release-identity-incident-migrations"
        / RELEASE_ID
        / INCIDENT_ID
        / MIGRATION_DIR
        / "incident_projection.json"
    )
    document = read_json(projection_path)
    document["protectedExecutionIds"] = [EXECUTIONS[0]]
    document["observedIdentities"] = [
        {**row, "executionIds": [EXECUTIONS[0]]}
        for row in document["observedIdentities"]
    ]
    write_json(projection_path, _with_digest(document))

    with pytest.raises(ObjectTransactionError, match="IDENTITY_INCIDENT_INVALID"):
        release_identity_incident_refs(output_root)
