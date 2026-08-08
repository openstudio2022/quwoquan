from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.closure.adoption_contract import canonical_digest, file_digest
from content.release.canonical import release_identity_incident_legacy_migration as migration
from content.release.canonical.garbage_collection_protection import (
    release_identity_incident_refs,
)
from core.io import read_json, write_json

RELEASE_ID = "legacy-collided-release"
INCIDENT_ID = "legacy-collision-001"
EXECUTIONS = ("execution-1", "execution-2")


def _source_path(output_root: Path) -> Path:
    return (
        output_root
        / "data/local/workspace/release-identity-incidents"
        / RELEASE_ID
        / INCIDENT_ID
        / "incident.json"
    )


def _rewrite_receipt(path: Path, document: dict[str, object]) -> None:
    stable = {key: value for key, value in document.items() if key != "receiptDigest"}
    write_json(path, {**stable, "receiptDigest": canonical_digest(stable)})


def _legacy_incident(
    output_root: Path,
    *,
    recorded_at: str = "2026-08-05T03:47:16+00:00",
) -> Path:
    incident_path = _source_path(output_root)
    rows: list[dict[str, object]] = []
    for index, digest_character in enumerate(("a", "b"), start=1):
        attestation = {
            "schema": "quwoquan_data.release_attestation",
            "releaseId": RELEASE_ID,
            "payloadSha256": "sha256:" + digest_character * 64,
            "canonicalMerkle": "sha256:" + str(index) * 64,
            "executionIds": list(EXECUTIONS),
            "recordedAt": "2026-08-03T19:27:08+00:00",
        }
        temporary = output_root / f"attestation-{index}.json"
        write_json(temporary, attestation)
        digest = file_digest(temporary)
        evidence_path = incident_path.parent / "evidence" / f"{digest[7:]}.json"
        write_json(evidence_path, attestation)
        temporary.unlink()
        rows.append(
            {
                "releaseId": RELEASE_ID,
                "payloadSha256": attestation["payloadSha256"],
                "canonicalMerkle": attestation["canonicalMerkle"],
                "attestationFileSha256": digest,
                "attestationRef": (
                    "data/local/release-identity-incidents/"
                    f"{RELEASE_ID}/{INCIDENT_ID}/evidence/{digest[7:]}.json"
                ),
                "executionIds": list(EXECUTIONS),
                "observedAt": recorded_at,
            }
        )
    rows.sort(
        key=lambda row: (
            row["releaseId"],
            row["payloadSha256"],
            row["canonicalMerkle"],
            row["attestationFileSha256"],
        )
    )
    stable = {
        "schema": "quwoquan_data.release_identity_incident",
        "incidentId": INCIDENT_ID,
        "releaseId": RELEASE_ID,
        "status": "identity_collided",
        "storageClass": "append_only_create_once",
        "observedIdentities": rows,
        "protectedExecutionIds": list(EXECUTIONS),
        "recordedAt": recorded_at,
    }
    write_json(
        incident_path,
        {**stable, "receiptDigest": canonical_digest(stable)},
    )
    return incident_path


def _migrate(
    output_root: Path,
    incident_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], Path]:
    monkeypatch.setattr(
        migration,
        "_verify_contract_introduction",
        lambda _repo_root: None,
    )
    return migration.migrate_legacy_release_identity_incident(
        source_incident_path=incident_path,
        source_incident_file_sha256=file_digest(incident_path),
        output_root=output_root,
    )


def test_legacy_incident_migration_is_idempotent_and_protects_gc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    incident_path = _legacy_incident(output_root)

    receipt, receipt_path = _migrate(output_root, incident_path, monkeypatch)
    first_bytes = receipt_path.read_bytes()
    repeated, repeated_path = _migrate(output_root, incident_path, monkeypatch)

    assert repeated == receipt
    assert repeated_path == receipt_path
    assert repeated_path.read_bytes() == first_bytes
    assert receipt["classification"]["acquisitionMode"] == "original_file"
    assert all(
        "/workspace/release-identity-incidents/" in row["normalizedRef"]
        for row in receipt["evidenceSnapshots"]
    )
    releases, executions = release_identity_incident_refs(output_root)
    assert releases == {RELEASE_ID}
    assert executions == set(EXECUTIONS)


def test_legacy_incident_migration_rejects_evidence_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    incident_path = _legacy_incident(output_root)
    receipt, _ = _migrate(output_root, incident_path, monkeypatch)
    evidence_ref = receipt["evidenceSnapshots"][0]["normalizedRef"]
    evidence = output_root / evidence_ref
    evidence.write_bytes(evidence.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="evidence digest drifted"):
        migration.load_validated_legacy_incident_projection(
            incident_path,
            output_root=output_root,
        )


def test_legacy_incident_migration_rejects_recovery_ambiguity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    incident_path = _legacy_incident(output_root)
    document = read_json(incident_path)
    document["observedIdentities"][0]["acquisitionMode"] = (
        "deterministic_byte_reconstruction"
    )
    _rewrite_receipt(incident_path, document)

    with pytest.raises(ValueError, match="deterministic-recovery ambiguity"):
        _migrate(output_root, incident_path, monkeypatch)


def test_legacy_incident_migration_rejects_wrong_temporal_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    incident_path = _legacy_incident(
        output_root,
        recorded_at=migration.CONTRACT_BOUNDARY_AT,
    )

    with pytest.raises(ValueError, match="does not predate"):
        _migrate(output_root, incident_path, monkeypatch)


def test_legacy_incident_migration_rejects_wrong_contract_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    incident_path = _legacy_incident(output_root)
    monkeypatch.setattr(
        migration,
        "_verify_contract_introduction",
        lambda _repo_root: (_ for _ in ()).throw(
            ValueError("incident contract boundary commit identity drifted")
        ),
    )

    with pytest.raises(ValueError, match="boundary commit identity drifted"):
        migration.migrate_legacy_release_identity_incident(
            source_incident_path=incident_path,
            source_incident_file_sha256=file_digest(incident_path),
            output_root=output_root,
        )


def test_legacy_incident_migration_rejects_path_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    incident_path = _legacy_incident(output_root)
    document = read_json(incident_path)
    document["observedIdentities"][0]["attestationRef"] = "../outside.json"
    _rewrite_receipt(incident_path, document)

    with pytest.raises(ValueError, match="exact old namespace"):
        _migrate(output_root, incident_path, monkeypatch)


def test_legacy_incident_migration_rejects_source_drift_after_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    incident_path = _legacy_incident(output_root)
    _migrate(output_root, incident_path, monkeypatch)
    document = read_json(incident_path)
    document["recordedAt"] = "2026-08-05T03:47:17+00:00"
    _rewrite_receipt(incident_path, document)

    with pytest.raises(ValueError, match="source incident file digest"):
        migration.load_validated_legacy_incident_projection(
            incident_path,
            output_root=output_root,
        )
