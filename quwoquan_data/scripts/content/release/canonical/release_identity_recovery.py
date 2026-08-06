"""Atomic writer for deterministic release-attestation recovery evidence."""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.reviewed_closure_adoption_identity import (
    _is_sha256,
    _safe_ref,
    _timestamp,
    canonical_digest,
    file_digest,
)
from content.release.canonical.release_identity_recovery_contract import (
    HISTORICAL_WRITER_SOURCE_REFS,
    ReleaseIdentityRecoveryProvenance,
    SERIALIZATION_CONTRACT,
    artifact_identity,
    candidate_count,
    canonical_attestation_bytes,
    evidence_ref,
    matching_recorded_at_values,
    parsed_timestamp,
    recovery_provenance_path,
    recovery_root,
    safe_id,
    validate_release_identity_recovery_provenance,
)
from core.io import read_json, write_json
from core.schema import assert_valid

_REVISION = re.compile(r"^[0-9a-f]{40}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _recovery_lock(root: Path) -> Iterator[None]:
    root.parent.mkdir(parents=True, exist_ok=True)
    lock = root.parent / f".{root.name}.lock"
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _snapshot(source: Path, target: Path, *, label: str) -> str:
    if source.is_symlink():
        raise ValueError(f"{label} cannot be a symlink: {source}")
    resolved = source.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file: {source}")
    before = file_digest(resolved)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        if file_digest(target) != before:
            raise ValueError(f"{label} snapshot digest collision: {target}")
        return before
    shutil.copyfile(resolved, target)
    if file_digest(target) != before:
        target.unlink(missing_ok=True)
        raise ValueError(f"{label} changed while being snapshotted")
    return before


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _writer_inputs(
    values: Sequence[tuple[str, Path]],
) -> list[tuple[str, Path, str]]:
    rows: list[tuple[str, Path, str]] = []
    for logical_ref, source_path in values:
        normalized_ref = _safe_ref(
            logical_ref, label="historicalWriterSources.logicalRef"
        ).as_posix()
        source = _regular_file(source_path, label=f"writer source {normalized_ref}")
        rows.append((normalized_ref, source, file_digest(source)))
    rows.sort(key=lambda item: item[0])
    if (
        tuple(item[0] for item in rows) != HISTORICAL_WRITER_SOURCE_REFS
        or len({item[2] for item in rows}) != len(rows)
    ):
        raise ValueError("historical writer source closure must contain four exact files")
    return rows


def _independent_inputs(
    values: Sequence[tuple[str, Path]],
) -> list[tuple[str, Path, str]]:
    rows: list[tuple[str, Path, str]] = []
    for role, source_path in values:
        normalized_role = str(role or "").strip()
        if normalized_role not in {"execution_closure", "release_identity"}:
            raise ValueError("independent evidence role is unsupported")
        source = _regular_file(source_path, label=f"independent evidence {role}")
        rows.append((normalized_role, source, file_digest(source)))
    rows.sort(key=lambda item: item[0])
    if (
        [item[0] for item in rows] != ["execution_closure", "release_identity"]
        or len({item[2] for item in rows}) != len(rows)
    ):
        raise ValueError("independent evidence requires both exact roles and files")
    return rows


def _assert_evidence_claims(
    rows: Sequence[tuple[str, Path, str]],
    *,
    identity: Mapping[str, object],
    artifact_digest: str,
) -> None:
    text = {
        role: source.read_text(encoding="utf-8")
        for role, source, _digest in rows
    }
    if (
        artifact_digest not in text["release_identity"]
        or str(identity["payloadSha256"]) not in text["release_identity"]
    ):
        raise ValueError("release-identity evidence does not contain the target tuple")
    closure = text["execution_closure"]
    if str(identity["canonicalMerkle"]) not in closure or any(
        execution_id not in closure for execution_id in identity["executionIds"]
    ):
        raise ValueError("execution-closure evidence does not contain the target closure")


def _template_projection(
    *,
    template_path: Path,
    semantic: Mapping[str, Any],
) -> tuple[Path, str, dict[str, object]]:
    template_source = _regular_file(template_path, label="template attestation")
    template = read_json(template_source)
    if not isinstance(template, dict):
        raise TypeError("template attestation must be a JSON object")
    replacements: dict[str, object] = {
        "payloadSha256": semantic.get("payloadSha256"),
        "canonicalMerkle": semantic.get("canonicalMerkle"),
        "recordedAt": semantic.get("recordedAt"),
    }
    if (
        not _is_sha256(str(replacements["payloadSha256"] or ""))
        or not _is_sha256(str(replacements["canonicalMerkle"] or ""))
    ):
        raise ValueError("template field replacements contain an invalid digest")
    _timestamp(replacements["recordedAt"], label="fieldReplacements.recordedAt")
    projected = dict(template)
    projected.update(replacements)
    if projected != dict(semantic):
        raise ValueError(
            "template attestation plus exact field replacements differs from semantic input"
        )
    return template_source, file_digest(template_source), replacements


def write_deterministic_identity_attestation_recovery(
    *,
    release_id: str,
    recovery_id: str,
    attestation_document_path: Path,
    template_attestation_path: Path,
    target_attestation_file_sha256: str,
    writer_revision: str,
    historical_writer_sources: Sequence[tuple[str, Path]],
    recovered_recorded_at: str,
    search_start_at: str,
    search_end_at: str,
    independent_evidence: Sequence[tuple[str, Path]],
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    """Atomically write exact recovered bytes and every reconstruction input."""

    normalized_release = safe_id(release_id, label="releaseId")
    normalized_recovery = safe_id(recovery_id, label="recoveryId")
    root = output_root.resolve()
    semantic_path = _regular_file(
        attestation_document_path, label="attestation reconstruction input"
    )
    semantic = read_json(semantic_path)
    if not isinstance(semantic, dict):
        raise TypeError("attestation reconstruction input must be a JSON object")
    identity = artifact_identity(semantic, release_id=normalized_release)
    if identity["recordedAt"] != recovered_recorded_at:
        raise ValueError("recovered recordedAt differs from semantic input")
    _timestamp(recovered_recorded_at, label="recoveredRecordedAt")
    if not _is_sha256(target_attestation_file_sha256):
        raise ValueError("target attestation digest must be sha256")
    artifact_bytes = canonical_attestation_bytes(semantic)
    artifact_digest = "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
    if artifact_digest != target_attestation_file_sha256:
        raise ValueError("deterministic reconstruction does not match target digest")
    if not _REVISION.fullmatch(str(writer_revision or "")):
        raise ValueError("writer revision must be a full lowercase commit digest")
    writer_inputs = _writer_inputs(historical_writer_sources)
    template_source, template_digest, replacements = _template_projection(
        template_path=template_attestation_path,
        semantic=semantic,
    )
    count = candidate_count(start_at=search_start_at, end_at=search_end_at)
    recovered_time = parsed_timestamp(recovered_recorded_at, label="recoveredRecordedAt")
    if not (
        parsed_timestamp(search_start_at, label="searchStartAt")
        <= recovered_time
        <= parsed_timestamp(search_end_at, label="searchEndAt")
    ):
        raise ValueError("recovered recordedAt is outside the candidate search window")
    if matching_recorded_at_values(
        semantic,
        target_digest=target_attestation_file_sha256,
        start_at=search_start_at,
        end_at=search_end_at,
    ) != [recovered_recorded_at]:
        raise ValueError("candidate search did not produce one unique target match")
    evidence_inputs = _independent_inputs(independent_evidence)
    _assert_evidence_claims(
        evidence_inputs,
        identity=identity,
        artifact_digest=artifact_digest,
    )

    final_root = recovery_root(
        output_root=root,
        release_id=normalized_release,
        recovery_id=normalized_recovery,
    )
    root_ref = final_root.relative_to(root).as_posix()
    artifact_ref = f"{root_ref}/artifact/attestation.json"
    reconstruction = {
        "method": "deterministic_canonical_json",
        "serializationContract": SERIALIZATION_CONTRACT,
        "semanticInputSha256": canonical_digest(semantic),
        "writerRevision": writer_revision,
        "historicalWriterSources": [
            {
                "logicalRef": logical_ref,
                "snapshotRef": evidence_ref(root_ref, digest),
                "fileSha256": digest,
            }
            for logical_ref, _source, digest in writer_inputs
        ],
        "templateAttestationRef": evidence_ref(root_ref, template_digest),
        "templateAttestationFileSha256": template_digest,
        "fieldReplacements": replacements,
        "recoveredField": "recordedAt",
        "recoveredValue": recovered_recorded_at,
        "candidateSearch": {
            "startAt": search_start_at,
            "endAt": search_end_at,
            "granularity": "microsecond",
            "stepMicros": 1,
            "candidateCount": count,
            "matchedCandidateCount": 1,
        },
    }
    evidence_rows = [
        {
            "role": role,
            "ref": evidence_ref(root_ref, digest),
            "fileSha256": digest,
        }
        for role, _source, digest in evidence_inputs
    ]
    expected_stable = {
        "schema": "quwoquan_data.release_identity_recovery_provenance",
        "recoveryId": normalized_recovery,
        "releaseId": normalized_release,
        "acquisitionMode": "deterministic_byte_reconstruction",
        "storageClass": "append_only_create_once",
        "artifactRef": artifact_ref,
        "artifactFileSha256": artifact_digest,
        "targetAttestationFileSha256": target_attestation_file_sha256,
        "artifactIdentity": identity,
        "reconstruction": reconstruction,
        "independentEvidence": evidence_rows,
    }
    provenance_path = final_root / "provenance.json"
    with _recovery_lock(final_root):
        if final_root.is_symlink():
            raise ValueError("release identity recovery root cannot be a symlink")
        if provenance_path.is_file():
            existing = read_json(provenance_path)
            validate_release_identity_recovery_provenance(existing, output_root=root)
            if not isinstance(existing, dict) or any(
                existing.get(key) != value for key, value in expected_stable.items()
            ):
                raise ValueError("release identity recovery create-once conflict")
            return existing, provenance_path
        if final_root.exists():
            raise ValueError("incomplete release identity recovery root already exists")

        final_root.parent.mkdir(parents=True, exist_ok=True)
        stage_root = Path(
            tempfile.mkdtemp(
                prefix=f".{normalized_recovery}.",
                dir=final_root.parent,
            )
        )
        try:
            _write_bytes(stage_root / "artifact/attestation.json", artifact_bytes)
            snapshots = [
                *(source for _logical, source, _digest in writer_inputs),
                template_source,
                *(source for _role, source, _digest in evidence_inputs),
            ]
            for source in snapshots:
                digest = file_digest(source)
                _snapshot(
                    source,
                    stage_root / "evidence" / digest.removeprefix("sha256:"),
                    label=f"recovery input {source.name}",
                )
            document = {**expected_stable, "recordedAt": _utc_now()}
            document["receiptDigest"] = canonical_digest(document)
            assert_valid(
                document,
                "release",
                "release_identity_recovery_provenance",
                label="release identity recovery provenance",
            )
            write_json(stage_root / "provenance.json", document)
            stage_root.replace(final_root)
        finally:
            if stage_root.exists():
                shutil.rmtree(stage_root)
        written = read_json(provenance_path)
        validate_release_identity_recovery_provenance(written, output_root=root)
        return written, provenance_path


__all__ = [
    "HISTORICAL_WRITER_SOURCE_REFS",
    "ReleaseIdentityRecoveryProvenance",
    "recovery_provenance_path",
    "recovery_root",
    "validate_release_identity_recovery_provenance",
    "write_deterministic_identity_attestation_recovery",
]
