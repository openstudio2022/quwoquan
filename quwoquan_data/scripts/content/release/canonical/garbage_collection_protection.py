"""Append-only release identity and reviewed-closure GC protections."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from content.execution.closure.adoption_contract import (
    ReleaseIdentityIncident,
    file_digest,
    validate_release_identity_incident,
    validate_reviewed_closure_adoption_receipt,
    validate_reviewed_closure_adoption_ref,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from core.paths import (
    OUTPUT_ROOT,
    RELEASE_IDENTITY_INCIDENT_MIGRATIONS_ROOT,
    RELEASE_IDENTITY_INCIDENTS_ROOT,
)

_INCIDENT_OBSERVATION_IDENTITY_KEYS = (
    "releaseId",
    "payloadSha256",
    "canonicalMerkle",
    "attestationFileSha256",
    "executionIds",
    "observedAt",
)


def _observation_identity_rows(value: object, *, label: str) -> list[dict[str, object]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    rows = value.get("observedIdentities")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{label} observedIdentities must be a non-empty array")
    identity_rows: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} observation must be an object")
        identity_rows.append(
            {key: row.get(key) for key in _INCIDENT_OBSERVATION_IDENTITY_KEYS}
        )
    return identity_rows


def _migrated_incident_projection(
    incident_path: Path,
    *,
    output_root: Path,
) -> ReleaseIdentityIncident:
    """Validate the create-once migrated projection of a pre-contract incident.

    Incidents recorded before the current provenance contract stay immutable in
    their canonical location; the completed one-shot migration left a
    current-schema projection in the append-only migration namespace.  The
    projection is only consumed while the source incident still matches the
    migration receipt byte-for-byte and the projection replays the exact
    observation identities and execution closure; any drift stays fail closed.
    """

    root = output_root.resolve()
    incident_root = incident_path.parent
    migration_namespace = (
        root
        / RELEASE_IDENTITY_INCIDENT_MIGRATIONS_ROOT.relative_to(OUTPUT_ROOT)
        / incident_root.parent.name
        / incident_root.name
    )
    if migration_namespace.is_symlink() or not migration_namespace.is_dir():
        raise ValueError("pre-contract incident has no migrated projection namespace")
    candidates = sorted(
        (
            path
            for path in migration_namespace.iterdir()
            if path.is_dir() and not path.is_symlink()
        ),
        key=lambda path: path.name,
    )
    if len(candidates) != 1:
        raise ValueError(
            "migrated incident projection namespace must hold exactly one migration"
        )
    receipt = _read_json(candidates[0] / "migration_receipt.json")
    source_binding = (
        receipt.get("sourceIncident") if isinstance(receipt, Mapping) else None
    )
    if (
        not isinstance(source_binding, Mapping)
        or file_digest(incident_path) != source_binding.get("fileSha256")
    ):
        raise ValueError(
            "pre-contract incident no longer matches its migration receipt binding"
        )
    projection_path = candidates[0] / "incident_projection.json"
    if projection_path.is_symlink() or not projection_path.is_file():
        raise ValueError("migrated incident projection file is missing")
    projection = _read_json(projection_path)
    source = _read_json(incident_path)
    if not isinstance(source, Mapping) or not isinstance(projection, Mapping):
        raise ValueError("incident and migrated projection must be objects")
    if (
        projection.get("releaseId") != source.get("releaseId")
        or projection.get("incidentId") != source.get("incidentId")
        or projection.get("protectedExecutionIds")
        != source.get("protectedExecutionIds")
        or _observation_identity_rows(projection, label="migrated projection")
        != _observation_identity_rows(source, label="pre-contract incident")
    ):
        raise ValueError("migrated incident projection drifted from its source")
    return validate_release_identity_incident(projection, output_root=root)


def release_identity_incident_refs(
    output_root: Path,
) -> tuple[set[str], set[str]]:
    """Return release and execution identities protected by incidents."""

    root = output_root.resolve() / RELEASE_IDENTITY_INCIDENTS_ROOT.relative_to(
        OUTPUT_ROOT
    )
    if not root.exists():
        return set(), set()
    if root.is_symlink() or not root.is_dir():
        raise ObjectTransactionError(
            "GATE_BLOCK DATA.RELEASE.IDENTITY_INCIDENT_INVALID: "
            f"incident root is not a regular directory; evidence={root}"
        )

    protected_releases: set[str] = set()
    protected_executions: set[str] = set()
    try:
        lock_path = root / ".protection.lock"
        if lock_path.exists() and (lock_path.is_symlink() or not lock_path.is_file()):
            raise ObjectTransactionError(
                "GATE_BLOCK DATA.RELEASE.IDENTITY_INCIDENT_INVALID: "
                f"global protection lock path is invalid; evidence={lock_path}"
            )
        release_roots = sorted(
            (path for path in root.iterdir() if path.name != ".protection.lock"),
            key=lambda path: path.name,
        )
        for release_path in release_roots:
            if release_path.is_symlink() or not release_path.is_dir():
                raise ObjectTransactionError(
                    "GATE_BLOCK DATA.RELEASE.IDENTITY_INCIDENT_INVALID: "
                    "release incident entry is not a regular directory; "
                    f"evidence={release_path}"
                )
            for incident_root in sorted(
                release_path.iterdir(), key=lambda path: path.name
            ):
                if incident_root.is_symlink() or not incident_root.is_dir():
                    raise ObjectTransactionError(
                        "GATE_BLOCK DATA.RELEASE.IDENTITY_INCIDENT_INVALID: "
                        "incident entry is not a regular directory; "
                        f"evidence={incident_root}"
                    )
                incident_path = incident_root / "incident.json"
                if incident_path.is_symlink() or not incident_path.is_file():
                    raise ObjectTransactionError(
                        "GATE_BLOCK DATA.RELEASE.IDENTITY_INCIDENT_INVALID: "
                        "canonical incident receipt is missing; "
                        f"evidence={incident_path}"
                    )
                try:
                    incident = validate_release_identity_incident(
                        _read_json(incident_path),
                        output_root=output_root.resolve(),
                    )
                except (OSError, TypeError, ValueError):
                    incident = _migrated_incident_projection(
                        incident_path,
                        output_root=output_root.resolve(),
                    )
                if (
                    incident.release_id != release_path.name
                    or incident.incident_id != incident_root.name
                ):
                    raise ObjectTransactionError(
                        "GATE_BLOCK DATA.RELEASE.IDENTITY_INCIDENT_INVALID: "
                        "incident identity differs from its canonical path; "
                        f"evidence={incident_path}"
                    )
                protected_releases.add(incident.release_id)
                protected_executions.update(incident.protected_execution_ids)
    except ObjectTransactionError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            "GATE_BLOCK DATA.RELEASE.IDENTITY_INCIDENT_INVALID: "
            f"incident evidence is unreadable or invalid; evidence={root}"
        ) from exc
    return protected_releases, protected_executions


def release_identity_incident_protected_release_ids(output_root: Path) -> set[str]:
    protected_releases, _protected_executions = release_identity_incident_refs(
        output_root
    )
    return protected_releases


def release_identity_incident_protected_execution_ids(output_root: Path) -> set[str]:
    _protected_releases, protected_executions = release_identity_incident_refs(
        output_root
    )
    return protected_executions


def reviewed_closure_adoption_protected_refs(
    output_root: Path,
) -> tuple[set[str], set[str]]:
    """Return source releases and executions retained by adoption evidence."""

    root = output_root.resolve() / "data/local/reviewed-closure-adoptions"
    if not root.exists():
        return set(), set()
    if root.is_symlink() or not root.is_dir():
        raise ObjectTransactionError(
            "GATE_BLOCK DATA.RELEASE.ADOPTION_EVIDENCE_INVALID: "
            f"adoption evidence root is not a regular directory; evidence={root}"
        )
    release_ids: set[str] = set()
    execution_ids: set[str] = set()
    try:
        for adoption_root in sorted(root.iterdir(), key=lambda path: path.name):
            if adoption_root.is_symlink() or not adoption_root.is_dir():
                raise ObjectTransactionError(
                    "GATE_BLOCK DATA.RELEASE.ADOPTION_EVIDENCE_INVALID: "
                    "adoption entry is not a regular directory; "
                    f"evidence={adoption_root}"
                )
            ref_path = adoption_root / "adoption_ref.json"
            if ref_path.is_symlink() or not ref_path.is_file():
                raise ObjectTransactionError(
                    "GATE_BLOCK DATA.RELEASE.ADOPTION_EVIDENCE_INVALID: "
                    f"canonical adoption ref is missing; evidence={ref_path}"
                )
            adoption_ref = validate_reviewed_closure_adoption_ref(
                _read_json(ref_path),
                output_root=output_root.resolve(),
            )
            if adoption_ref.adoption_id != adoption_root.name:
                raise ObjectTransactionError(
                    "GATE_BLOCK DATA.RELEASE.ADOPTION_EVIDENCE_INVALID: "
                    "adoption identity differs from its canonical path; "
                    f"evidence={ref_path}"
                )
            release_ids.add(adoption_ref.source_release_identity.release_id)
            execution_ids.update(adoption_ref.upstream_execution_ids)

            receipt_path = adoption_root / "adoption_receipt.json"
            if receipt_path.exists() or receipt_path.is_symlink():
                if receipt_path.is_symlink() or not receipt_path.is_file():
                    raise ObjectTransactionError(
                        "GATE_BLOCK DATA.RELEASE.ADOPTION_EVIDENCE_INVALID: "
                        "canonical adoption receipt path is invalid; "
                        f"evidence={receipt_path}"
                    )
                receipt = validate_reviewed_closure_adoption_receipt(
                    _read_json(receipt_path),
                    output_root=output_root.resolve(),
                )
                if (
                    receipt.adoption_id != adoption_ref.adoption_id
                    or receipt.source_release_identity
                    != adoption_ref.source_release_identity
                ):
                    raise ObjectTransactionError(
                        "GATE_BLOCK DATA.RELEASE.ADOPTION_EVIDENCE_INVALID: "
                        "adoption receipt differs from its canonical ref; "
                        f"evidence={receipt_path}"
                    )
                execution_ids.update(receipt.lane_execution_ids)
    except ObjectTransactionError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            "GATE_BLOCK DATA.RELEASE.ADOPTION_EVIDENCE_INVALID: "
            f"adoption evidence is unreadable or invalid; evidence={root}"
        ) from exc
    return release_ids, execution_ids


__all__ = [
    "release_identity_incident_protected_execution_ids",
    "release_identity_incident_protected_release_ids",
    "release_identity_incident_refs",
    "reviewed_closure_adoption_protected_refs",
]
