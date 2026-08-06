"""Deterministic attestation recovery is byte-exact and provenance-bound."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import pytest

from content.execution.reviewed_closure_adoption_identity import (
    ReviewedClosureAdoptionError,
    canonical_digest,
    validate_release_identity_incident,
)
from content.release.canonical.handler import (
    handle_release_identity_recovery,
    register_parser,
)
from content.release.canonical.release_identity_incident import (
    record_release_identity_incident,
)
from content.release.canonical.release_identity_recovery import (
    HISTORICAL_WRITER_SOURCE_REFS,
    validate_release_identity_recovery_provenance,
    write_deterministic_identity_attestation_recovery,
)

_RELEASE_ID = "20260804--travel-commercial-rights-closure--china--pilot-003"
_RECOVERY_ID = "pilot-003-attestation-66e805-recovery-001"
_RECORDED_AT = "2026-08-03T19:27:08.320332+00:00"
_SEARCH_START = "2026-08-03T19:27:08.300000+00:00"
_SEARCH_END = "2026-08-03T19:27:08.341878+00:00"


def _canonical_bytes(document: dict[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_canonical(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(document))


def _recovery_fixture(tmp_path: Path) -> dict[str, object]:
    output_root = tmp_path / "output"
    attestation = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": _RELEASE_ID,
        "payloadSha256": "sha256:" + "6" * 64,
        "canonicalMerkle": "sha256:" + "a" * 64,
        "executionIds": [
            "20260731--travel-article-copy-ready--china--scale-017",
            "20260731--travel-homepage-copy-ready--china--scale-017",
            "20260731--travel-image-copy-ready--china--scale-017",
            "20260731--travel-video-copy-ready--china--scale-017",
        ],
        "recordedAt": _RECORDED_AT,
    }
    semantic_input = tmp_path / "inputs/recovered-attestation-fields.json"
    _write_json(semantic_input, attestation)
    writer_sources: list[tuple[str, Path]] = []
    for index, logical_ref in enumerate(HISTORICAL_WRITER_SOURCE_REFS):
        writer_source = tmp_path / "inputs/writers" / f"writer-{index}"
        writer_source.parent.mkdir(parents=True, exist_ok=True)
        writer_source.write_text(
            f"historical writer source {index}: {logical_ref}\n",
            encoding="utf-8",
        )
        writer_sources.append((logical_ref, writer_source))
    template_attestation = copy.deepcopy(attestation)
    template_attestation.update(
        {
            "payloadSha256": "sha256:" + "b" * 64,
            "canonicalMerkle": "sha256:" + "c" * 64,
            "recordedAt": "2026-08-04T00:00:00+00:00",
        }
    )
    template_path = tmp_path / "inputs/template-b01-attestation.json"
    _write_canonical(template_path, template_attestation)
    expected = "sha256:" + hashlib.sha256(_canonical_bytes(attestation)).hexdigest()
    candidate_manifest = tmp_path / "inputs/candidate-manifest.json"
    candidate_manifest.write_text(
        json.dumps(
            {
                "releaseDigest": attestation["payloadSha256"],
                "attestationDigest": expected,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    aggregate_log = tmp_path / "inputs/aggregate.log"
    aggregate_log.write_text(
        json.dumps(
            {
                "canonicalMerkle": attestation["canonicalMerkle"],
                "executionIds": attestation["executionIds"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    document, provenance_path = write_deterministic_identity_attestation_recovery(
        release_id=_RELEASE_ID,
        recovery_id=_RECOVERY_ID,
        attestation_document_path=semantic_input,
        template_attestation_path=template_path,
        target_attestation_file_sha256=expected,
        writer_revision="3921bb69b55ad9144d30db9214bbd4fd100b023e",
        historical_writer_sources=writer_sources,
        recovered_recorded_at=_RECORDED_AT,
        search_start_at=_SEARCH_START,
        search_end_at=_SEARCH_END,
        independent_evidence=(
            ("release_identity", candidate_manifest),
            ("execution_closure", aggregate_log),
        ),
        output_root=output_root,
    )
    return {
        "outputRoot": output_root,
        "document": document,
        "provenancePath": provenance_path,
        "artifactPath": output_root / document["artifactRef"],
        "semanticInput": semantic_input,
        "writerSources": writer_sources,
        "templatePath": template_path,
        "candidateManifest": candidate_manifest,
        "aggregateLog": aggregate_log,
        "expectedDigest": expected,
    }


def test_recovery_writer_is_byte_exact_create_once_and_freezes_search(
    tmp_path: Path,
) -> None:
    fixture = _recovery_fixture(tmp_path)
    document = fixture["document"]
    artifact_path = fixture["artifactPath"]
    assert isinstance(document, dict)
    assert isinstance(artifact_path, Path)
    first_provenance_bytes = fixture["provenancePath"].read_bytes()
    artifact_bytes = artifact_path.read_bytes()

    validated = validate_release_identity_recovery_provenance(
        document,
        output_root=fixture["outputRoot"],
    )
    replay, replay_path = write_deterministic_identity_attestation_recovery(
        release_id=_RELEASE_ID,
        recovery_id=_RECOVERY_ID,
        attestation_document_path=fixture["semanticInput"],
        template_attestation_path=fixture["templatePath"],
        target_attestation_file_sha256=fixture["expectedDigest"],
        writer_revision="3921bb69b55ad9144d30db9214bbd4fd100b023e",
        historical_writer_sources=fixture["writerSources"],
        recovered_recorded_at=_RECORDED_AT,
        search_start_at=_SEARCH_START,
        search_end_at=_SEARCH_END,
        independent_evidence=(
            ("release_identity", fixture["candidateManifest"]),
            ("execution_closure", fixture["aggregateLog"]),
        ),
        output_root=fixture["outputRoot"],
    )

    assert validated.artifact_file_sha256 == fixture["expectedDigest"]
    assert artifact_bytes.endswith(b"\n")
    assert hashlib.sha256(artifact_bytes).hexdigest() == str(
        fixture["expectedDigest"]
    ).removeprefix("sha256:")
    assert document["reconstruction"]["candidateSearch"] == {
        "startAt": _SEARCH_START,
        "endAt": _SEARCH_END,
        "granularity": "microsecond",
        "stepMicros": 1,
        "candidateCount": 41879,
        "matchedCandidateCount": 1,
    }
    assert [
        row["logicalRef"]
        for row in document["reconstruction"]["historicalWriterSources"]
    ] == list(HISTORICAL_WRITER_SOURCE_REFS)
    assert document["reconstruction"]["fieldReplacements"] == {
        "payloadSha256": "sha256:" + "6" * 64,
        "canonicalMerkle": "sha256:" + "a" * 64,
        "recordedAt": _RECORDED_AT,
    }
    assert replay == document
    assert replay_path.read_bytes() == first_provenance_bytes


def test_incident_requires_recovery_provenance_for_reconstructed_bytes(
    tmp_path: Path,
) -> None:
    fixture = _recovery_fixture(tmp_path)
    output_root = fixture["outputRoot"]
    current_attestation = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": _RELEASE_ID,
        "payloadSha256": "sha256:" + "b" * 64,
        "canonicalMerkle": "sha256:" + "c" * 64,
        "executionIds": [
            "20260804--travel-article-rights--china--pilot-003",
            "20260804--travel-homepage-rights--china--pilot-003",
            "20260804--travel-image-rights--china--pilot-003",
            "20260804--travel-video-rights--china--pilot-003",
        ],
        "recordedAt": "2026-08-04T00:00:00+00:00",
    }
    current_path = tmp_path / "inputs/current-attestation.json"
    _write_canonical(current_path, current_attestation)

    incident, incident_path = record_release_identity_incident(
        release_id=_RELEASE_ID,
        incident_id="pilot-003-identity-collision-002",
        original_attestations=(current_path,),
        recovery_provenances=(fixture["provenancePath"],),
        output_root=output_root,
    )
    first_bytes = incident_path.read_bytes()
    replay, replay_path = record_release_identity_incident(
        release_id=_RELEASE_ID,
        incident_id="pilot-003-identity-collision-002",
        original_attestations=(current_path,),
        recovery_provenances=(fixture["provenancePath"],),
        output_root=output_root,
    )
    reconstructed = next(
        row
        for row in incident["observedIdentities"]
        if row["acquisitionMode"] == "deterministic_byte_reconstruction"
    )

    assert reconstructed["recoveryProvenanceRef"] == fixture[
        "provenancePath"
    ].relative_to(output_root).as_posix()
    assert reconstructed["recoveryProvenanceFileSha256"].startswith("sha256:")
    assert replay == incident
    assert replay_path.read_bytes() == first_bytes
    assert validate_release_identity_incident(
        incident, output_root=output_root
    ).release_id == _RELEASE_ID

    unbound = copy.deepcopy(incident)
    reconstructed = next(
        row
        for row in unbound["observedIdentities"]
        if row["acquisitionMode"] == "deterministic_byte_reconstruction"
    )
    reconstructed.pop("recoveryProvenanceRef")
    reconstructed.pop("recoveryProvenanceFileSha256")
    unbound["receiptDigest"] = canonical_digest(
        {key: value for key, value in unbound.items() if key != "receiptDigest"}
    )
    with pytest.raises(
        ReviewedClosureAdoptionError,
        match="deterministic reconstruction requires recovery provenance",
    ):
        validate_release_identity_incident(unbound, output_root=output_root)


def test_recovery_create_once_rejects_writer_provenance_drift(tmp_path: Path) -> None:
    fixture = _recovery_fixture(tmp_path)
    writer_sources = fixture["writerSources"]
    assert isinstance(writer_sources, list)
    writer_source = writer_sources[0][1]
    assert isinstance(writer_source, Path)
    writer_source.write_text("different historical writer bytes\n", encoding="utf-8")

    with pytest.raises(ValueError, match="create-once conflict"):
        write_deterministic_identity_attestation_recovery(
            release_id=_RELEASE_ID,
            recovery_id=_RECOVERY_ID,
            attestation_document_path=fixture["semanticInput"],
            template_attestation_path=fixture["templatePath"],
            target_attestation_file_sha256=fixture["expectedDigest"],
            writer_revision="3921bb69b55ad9144d30db9214bbd4fd100b023e",
            historical_writer_sources=writer_sources,
            recovered_recorded_at=_RECORDED_AT,
            search_start_at=_SEARCH_START,
            search_end_at=_SEARCH_END,
            independent_evidence=(
                ("release_identity", fixture["candidateManifest"]),
                ("execution_closure", fixture["aggregateLog"]),
            ),
            output_root=fixture["outputRoot"],
        )


def test_recovery_validator_rejects_template_replacement_tamper(
    tmp_path: Path,
) -> None:
    fixture = _recovery_fixture(tmp_path)
    tampered = copy.deepcopy(fixture["document"])
    tampered["reconstruction"]["fieldReplacements"]["payloadSha256"] = (
        "sha256:" + "d" * 64
    )
    tampered["receiptDigest"] = canonical_digest(
        {key: value for key, value in tampered.items() if key != "receiptDigest"}
    )

    with pytest.raises(
        ReviewedClosureAdoptionError,
        match="field replacements are not exact",
    ):
        validate_release_identity_recovery_provenance(
            tampered,
            output_root=fixture["outputRoot"],
        )


def test_release_cli_registers_identity_recovery_as_canonical_command() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_parser(subparsers)
    args = parser.parse_args(
        [
            "release",
            "identity-recovery",
            "--release-id",
            _RELEASE_ID,
            "--recovery-id",
            _RECOVERY_ID,
            "--attestation-document",
            "semantic.json",
            "--template-attestation",
            "template.json",
            "--target-attestation-sha256",
            "sha256:" + "6" * 64,
            "--writer-revision",
            "3921bb69b55ad9144d30db9214bbd4fd100b023e",
            *[
                item
                for index, logical_ref in enumerate(HISTORICAL_WRITER_SOURCE_REFS)
                for item in ("--writer-source", f"{logical_ref}=writer-{index}")
            ],
            "--recovered-recorded-at",
            _RECORDED_AT,
            "--search-start-at",
            _SEARCH_START,
            "--search-end-at",
            _SEARCH_END,
            "--evidence",
            "release_identity=candidate.json",
            "--evidence",
            "execution_closure=aggregate.log",
        ]
    )

    assert args.handler is handle_release_identity_recovery
