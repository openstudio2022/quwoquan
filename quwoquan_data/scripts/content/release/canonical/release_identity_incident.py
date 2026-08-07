"""Create-once evidence for a reused releaseId with conflicting byte identity.

The incident is evidence only.  Recording it never mutates either observed
release, and every supplied attestation is snapshotted below the non-release
``data/local`` evidence root before the incident receipt is committed.
"""

from __future__ import annotations

import fcntl
import re
import shutil
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.execution.closure.adoption_contract import (
    canonical_digest,
    file_digest,
    validate_release_identity_incident,
)
from content.release.canonical.release_identity_recovery import (
    recovery_provenance_path,
    validate_release_identity_recovery_provenance,
)
from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, RELEASE_IDENTITY_INCIDENTS_ROOT

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


class ReleaseIdentityIncidentOpenError(RuntimeError):
    """A canonical release ID is permanently reserved by collision evidence."""

    code = "DATA.RELEASE.IDENTITY_INCIDENT_OPEN"

    def __init__(self, release_id: str, evidence_refs: Sequence[str]) -> None:
        self.release_id = release_id
        self.evidence_refs = tuple(evidence_refs)
        super().__init__(
            f"{self.code}: releaseId={release_id} is reserved by identity incident: "
            + ", ".join(self.evidence_refs)
        )


def _safe_id(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_ID.fullmatch(normalized):
        raise ValueError(f"{label} is not a safe identifier")
    return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def incident_path(
    *,
    output_root: Path,
    release_id: str,
    incident_id: str,
) -> Path:
    return (
        output_root.resolve()
        / RELEASE_IDENTITY_INCIDENTS_ROOT.relative_to(OUTPUT_ROOT)
        / _safe_id(release_id, label="releaseId")
        / _safe_id(incident_id, label="incidentId")
        / "incident.json"
    )


def identity_protection_lock_path(*, output_root: Path) -> Path:
    """One lock serializes incident protection discovery with destructive GC."""

    return (
        output_root.resolve()
        / RELEASE_IDENTITY_INCIDENTS_ROOT.relative_to(OUTPUT_ROOT)
        / ".protection.lock"
    )


@contextmanager
def release_identity_protection_lock(
    *,
    output_root: Path,
    exclusive: bool = True,
) -> Iterator[None]:
    """Hold before any per-incident lock and across scan/snapshot/delete.

    Writers use exclusive mode from source-evidence read through create-once
    commit.  GC/discard callers must also use exclusive mode across their full
    protection scan and destructive action, so no new incident can race after
    reachability was calculated.
    """

    lock = identity_protection_lock_path(output_root=output_root)
    lock.parent.mkdir(parents=True, exist_ok=True)
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), operation)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def release_output_root(release_root: Path) -> Path:
    """Resolve QWQ_OUTPUT_ROOT from canonical or isolated test release roots."""

    resolved = release_root.resolve()
    if resolved.name == "releases" and resolved.parent.name == "data":
        return resolved.parent.parent
    return resolved.parent


def _incident_refs(*, output_root: Path, release_id: str) -> tuple[str, ...]:
    root = (
        output_root.resolve()
        / RELEASE_IDENTITY_INCIDENTS_ROOT.relative_to(OUTPUT_ROOT)
        / _safe_id(release_id, label="releaseId")
    )
    if root.is_symlink():
        raise ReleaseIdentityIncidentOpenError(release_id, [str(root)])
    if not root.exists():
        return ()
    if not root.is_dir():
        raise ReleaseIdentityIncidentOpenError(release_id, [str(root)])
    refs: list[str] = []
    for incident_root in sorted(path for path in root.iterdir() if not path.name.startswith(".")):
        path = incident_root / "incident.json"
        try:
            document = read_json(path)
            validated = validate_release_identity_incident(
                document,
                output_root=output_root.resolve(),
            )
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            raise ReleaseIdentityIncidentOpenError(
                release_id,
                [f"{path} (invalid: {exc})"],
            ) from exc
        if validated.release_id != release_id:
            raise ReleaseIdentityIncidentOpenError(
                release_id,
                [f"{path} (releaseId drift)"],
            )
        refs.append(path.relative_to(output_root.resolve()).as_posix())
    return tuple(refs)


@contextmanager
def canonical_release_identity_guard(
    *, output_root: Path, release_id: str
) -> Iterator[None]:
    """Block ordinary create/reuse while exact recovery/adoption remains separate."""

    normalized = _safe_id(release_id, label="releaseId")
    with release_identity_protection_lock(output_root=output_root, exclusive=False):
        refs = _incident_refs(output_root=output_root, release_id=normalized)
        if refs:
            raise ReleaseIdentityIncidentOpenError(normalized, refs)
        yield


@contextmanager
def _incident_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.parent / ".incident.lock"
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _attestation_observation(
    source_path: Path,
    *,
    release_id: str,
    output_root: Path,
    evidence_root: Path,
    observed_at: str,
    acquisition_mode: str,
    recovery_provenance_ref: str | None = None,
    recovery_provenance_file_sha256: str | None = None,
) -> dict[str, Any]:
    if source_path.is_symlink():
        raise ValueError(
            f"identity attestation cannot be a symlink: {source_path}"
        )
    source = source_path.resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"identity attestation must be a regular file: {source}")
    document = read_json(source)
    if not isinstance(document, dict):
        raise TypeError(f"identity attestation must be an object: {source}")
    execution_ids = document.get("executionIds")
    if (
        document.get("releaseId") != release_id
        or not isinstance(execution_ids, list)
        or not execution_ids
        or any(not isinstance(item, str) or not item for item in execution_ids)
        or execution_ids != sorted(set(execution_ids))
    ):
        raise ValueError(f"identity attestation closure is invalid: {source}")
    digest = file_digest(source)
    snapshot = evidence_root / f"{digest.removeprefix('sha256:')}.json"
    if snapshot.is_symlink():
        raise ValueError(f"identity evidence cannot be a symlink: {snapshot}")
    if snapshot.is_file():
        if file_digest(snapshot) != digest:
            raise ValueError(f"identity evidence digest collision: {snapshot}")
    else:
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporary = snapshot.parent / f".{snapshot.name}.tmp"
        if temporary.exists():
            raise ValueError(f"identity evidence staging path exists: {temporary}")
        shutil.copyfile(source, temporary)
        if file_digest(temporary) != digest:
            temporary.unlink(missing_ok=True)
            raise ValueError("identity evidence changed during snapshot")
        temporary.replace(snapshot)
    observation: dict[str, Any] = {
        "releaseId": release_id,
        "payloadSha256": str(document.get("payloadSha256") or ""),
        "canonicalMerkle": str(document.get("canonicalMerkle") or ""),
        "attestationFileSha256": digest,
        "attestationRef": snapshot.relative_to(output_root).as_posix(),
        "acquisitionMode": acquisition_mode,
        "executionIds": list(execution_ids),
        "observedAt": observed_at,
    }
    if acquisition_mode == "deterministic_byte_reconstruction":
        observation.update(
            {
                "recoveryProvenanceRef": str(recovery_provenance_ref or ""),
                "recoveryProvenanceFileSha256": str(
                    recovery_provenance_file_sha256 or ""
                ),
            }
        )
    return observation


def _recovery_observation_source(
    provenance_path: Path,
    *,
    release_id: str,
    output_root: Path,
) -> dict[str, object]:
    if provenance_path.is_symlink():
        raise ValueError("identity recovery provenance cannot be a symlink")
    resolved = provenance_path.resolve(strict=True)
    try:
        provenance_ref = resolved.relative_to(output_root).as_posix()
    except ValueError as exc:
        raise ValueError("identity recovery provenance escaped output root") from exc
    document = read_json(resolved)
    validated = validate_release_identity_recovery_provenance(
        document,
        output_root=output_root,
    )
    expected = recovery_provenance_path(
        output_root=output_root,
        release_id=validated.release_id,
        recovery_id=validated.recovery_id,
    )
    if (
        validated.release_id != release_id
        or resolved != expected.resolve(strict=True)
    ):
        raise ValueError("identity recovery provenance is not canonical for release")
    return {
        "attestationPath": validated.artifact_path,
        "acquisitionMode": "deterministic_byte_reconstruction",
        "recoveryProvenanceRef": provenance_ref,
        "recoveryProvenanceFileSha256": file_digest(resolved),
    }


def _original_observation_source(candidate: Path) -> dict[str, object]:
    if candidate.is_symlink():
        raise ValueError(f"identity attestation cannot be a symlink: {candidate}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"identity attestation must be a regular file: {candidate}")
    return {
        "attestationPath": resolved,
        "acquisitionMode": "original_file",
    }


def _observation_key(source: Mapping[str, object]) -> tuple[str, str, str, str]:
    attestation = source["attestationPath"]
    if not isinstance(attestation, Path):
        raise TypeError("identity observation attestation path is invalid")
    return (
        file_digest(attestation.resolve(strict=True)),
        str(source["acquisitionMode"]),
        str(source.get("recoveryProvenanceRef") or ""),
        str(source.get("recoveryProvenanceFileSha256") or ""),
    )


def record_release_identity_incident(
    *,
    release_id: str,
    incident_id: str,
    original_attestations: Sequence[Path],
    recovery_provenances: Sequence[Path],
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    """Snapshot conflicting attestations and write one immutable incident."""

    normalized_release = _safe_id(release_id, label="releaseId")
    normalized_incident = _safe_id(incident_id, label="incidentId")
    if len(original_attestations) + len(recovery_provenances) < 2:
        raise ValueError("identity incident requires at least two attestations")
    root = output_root.resolve()
    path = incident_path(
        output_root=root,
        release_id=normalized_release,
        incident_id=normalized_incident,
    )
    with release_identity_protection_lock(output_root=root, exclusive=True):
        sources = [
            _original_observation_source(candidate)
            for candidate in original_attestations
        ]
        sources.extend(
            _recovery_observation_source(
                candidate,
                release_id=normalized_release,
                output_root=root,
            )
            for candidate in recovery_provenances
        )
        with _incident_lock(path):
            if path.is_symlink():
                raise ValueError("identity incident path cannot be a symlink")
            if path.is_file():
                existing = read_json(path)
                validated = validate_release_identity_incident(
                    existing,
                    output_root=root,
                )
                supplied_observations = sorted(
                    _observation_key(row) for row in sources
                )
                existing_observations = sorted(
                    (
                        str(row.get("attestationFileSha256") or ""),
                        str(row.get("acquisitionMode") or ""),
                        str(row.get("recoveryProvenanceRef") or ""),
                        str(row.get("recoveryProvenanceFileSha256") or ""),
                    )
                    for row in existing.get("observedIdentities") or []
                )
                if (
                    validated.release_id != normalized_release
                    or validated.incident_id != normalized_incident
                    or supplied_observations != existing_observations
                ):
                    raise ValueError("release identity incident create-once conflict")
                return dict(existing), path

            observed_at = _utc_now()
            evidence_root = path.parent / "evidence"
            observations = [
                _attestation_observation(
                    source["attestationPath"],
                    release_id=normalized_release,
                    output_root=root,
                    evidence_root=evidence_root,
                    observed_at=observed_at,
                    acquisition_mode=str(source["acquisitionMode"]),
                    recovery_provenance_ref=str(
                        source.get("recoveryProvenanceRef") or ""
                    ),
                    recovery_provenance_file_sha256=str(
                        source.get("recoveryProvenanceFileSha256") or ""
                    ),
                )
                for source in sources
            ]
            observations.sort(
                key=lambda row: (
                    row["releaseId"],
                    row["payloadSha256"],
                    row["canonicalMerkle"],
                    row["attestationFileSha256"],
                )
            )
            protected = sorted(
                {
                    execution_id
                    for observation in observations
                    for execution_id in observation["executionIds"]
                }
            )
            stable: dict[str, Any] = {
                "schema": "quwoquan_data.release_identity_incident",
                "incidentId": normalized_incident,
                "releaseId": normalized_release,
                "status": "identity_collided",
                "storageClass": "append_only_create_once",
                "observedIdentities": observations,
                "protectedExecutionIds": protected,
                "recordedAt": observed_at,
            }
            document = {**stable, "receiptDigest": canonical_digest(stable)}
            validate_release_identity_incident(document, output_root=root)
            write_json(path, document)
            return document, path


__all__ = [
    "ReleaseIdentityIncidentOpenError",
    "canonical_release_identity_guard",
    "identity_protection_lock_path",
    "incident_path",
    "record_release_identity_incident",
    "release_output_root",
    "release_identity_protection_lock",
]
