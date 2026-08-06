"""Controlled deletion of one inactive, disposable immutable release."""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from content.release.canonical.acceptance_lease import validate_lease_event
from content.release.canonical.garbage_collection import (
    release_identity_incident_protected_release_ids,
    reviewed_closure_adoption_protected_refs,
)
from content.release.canonical.object_transaction_contract import _safe_id
from content.release.canonical.release_identity_incident import (
    release_identity_protection_lock,
)
from content.release.canonical.release_operation_lock import (
    release_operation_guard,
    release_operation_lock_root,
)
from core.io import read_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT


def _active_release_processes(release_id: str) -> tuple[str, ...]:
    """Return live release writers that still reference exactly one release."""

    process = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode:
        raise RuntimeError("unable to inspect active release commands before discard")
    active_commands = (
        "ship apply",
        "ship rollback",
        "ship verify",
        "release campaign-aggregate",
        "release baseline",
        "release lifecycle-exit",
        "release acceptance-lease",
    )
    return tuple(
        line.strip()
        for line in process.stdout.splitlines()
        if release_id in line and any(command in line for command in active_commands)
    )


def _environment_evidence_roots(*, output_root: Path, release_id: str) -> tuple[Path, ...]:
    """Find only derived environment evidence for the selected immutable release."""

    environment_root = output_root / "env"
    if not environment_root.is_dir():
        return ()
    return tuple(
        path
        for path in environment_root.glob(f"*/runs/data-release/{release_id}")
        if path.is_dir()
    )


def _acceptance_protection_refs(
    *,
    output_root: Path,
    release_id: str,
    evidence_roots: tuple[Path, ...],
) -> tuple[Path, ...]:
    """Return completed readiness receipts or explicit acceptance leases.

    A passed readiness receipt can be referenced by Ops readiness and real-device
    UAT long after the writer process exits.  Acceptance leases may live in an
    Ops-owned run outside the Data release run, so they are discovered across
    environment run roots and bound by their releaseId.
    """

    protected: set[Path] = set()
    for evidence_root in evidence_roots:
        for path in evidence_root.rglob("release-readiness.json"):
            try:
                document = read_json(path)
            except (OSError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"GATE_BLOCK unreadable release readiness evidence: {path}"
                ) from exc
            if not isinstance(document, dict):
                raise RuntimeError(
                    f"GATE_BLOCK invalid release readiness evidence: {path}"
                )
            if document.get("passed") is not True:
                continue
            if (
                document.get("schema")
                != "quwoquan_data.environment_release_readiness"
                or document.get("releaseId") != release_id
            ):
                raise RuntimeError(
                    f"GATE_BLOCK invalid passed release readiness evidence: {path}"
                )
            protected.add(path)

    environment_root = output_root / "env"
    if environment_root.is_dir():
        lease_events: dict[str, tuple[Path, dict]] = {}
        for path in environment_root.glob(
            "*/runs/release-acceptance/*/*/*/acceptance-lease.json"
        ):
            try:
                document = read_json(path)
            except (OSError, TypeError, ValueError) as exc:
                if release_id in path.parts:
                    raise RuntimeError(
                        f"GATE_BLOCK unreadable acceptance lease: {path}"
                    ) from exc
                continue
            if not isinstance(document, dict):
                if release_id in path.parts:
                    raise RuntimeError(
                        f"GATE_BLOCK invalid acceptance lease: {path}"
                    )
                continue
            if document.get("releaseId") != release_id:
                if release_id in path.parts:
                    raise RuntimeError(
                        f"GATE_BLOCK acceptance lease releaseId drift: {path}"
                    )
                continue
            issues = validate_lease_event(
                document,
                path=path,
                output_root=output_root,
            )
            if issues:
                raise RuntimeError(
                    "GATE_BLOCK invalid acceptance lease: "
                    + "; ".join(issues)
                )
            ref = path.relative_to(output_root).as_posix()
            lease_events[ref] = (path, document)
        revoked: set[str] = set()
        for _ref, (path, document) in lease_events.items():
            if document.get("action") != "revoke":
                continue
            predecessor = str(document.get("predecessorEventRef") or "")
            acquired = lease_events.get(predecessor)
            if acquired is None:
                raise RuntimeError(
                    f"GATE_BLOCK acceptance revoke has no bound acquire: {path}"
                )
            _acquire_path, acquire = acquired
            if acquire.get("action") != "acquire" or any(
                acquire.get(field) != document.get(field)
                for field in (
                    "environment",
                    "releaseId",
                    "manifestDigest",
                    "leaseId",
                    "holder",
                    "purpose",
                    "importRunId",
                    "verifyRunId",
                    "readinessRef",
                )
            ):
                raise RuntimeError(
                    f"GATE_BLOCK acceptance revoke identity drift: {path}"
                )
            revoked.add(predecessor)
        for ref, (path, document) in lease_events.items():
            if document.get("action") == "acquire" and ref not in revoked:
                protected.add(path)
    return tuple(sorted(protected))


def discard_release(
    release_id: str,
    *,
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> None:
    """Delete one derived release and its derived environment evidence.

    The command is deliberately narrow: it accepts only a single safe release
    identifier, rejects live writers, and never reaches source configuration or
    canonical publish.  Environment databases must already point at another
    immutable release before this disposable evidence is removed.
    """

    normalized_id = _safe_id(release_id, label="releaseId")
    release = release_root / normalized_id
    if not release.is_dir():
        raise FileNotFoundError(f"release output does not exist: {normalized_id}")
    with release_identity_protection_lock(
        output_root=output_root,
        exclusive=True,
    ), release_operation_guard(
        lock_root=release_operation_lock_root(release_root),
        release_ids=(normalized_id,),
        exclusive_releases=True,
    ):
        incident_release_ids = release_identity_incident_protected_release_ids(
            output_root
        )
        adoption_release_ids, _adoption_execution_ids = (
            reviewed_closure_adoption_protected_refs(output_root)
        )
        if normalized_id in incident_release_ids:
            raise RuntimeError(
                "GATE_BLOCK DATA.RELEASE.IDENTITY_INCIDENT_PROTECTED: "
                f"releaseId={normalized_id} is protected by append-only "
                "release identity incident evidence"
            )
        if normalized_id in adoption_release_ids:
            raise RuntimeError(
                "GATE_BLOCK DATA.RELEASE.ADOPTION_SOURCE_PROTECTED: "
                f"releaseId={normalized_id} is retained by reviewed-closure "
                "adoption evidence"
            )
        active_processes = _active_release_processes(normalized_id)
        if active_processes:
            raise RuntimeError(
                "GATE_BLOCK active release command owns release: "
                + "; ".join(active_processes)
            )
        evidence_roots = _environment_evidence_roots(
            output_root=output_root,
            release_id=normalized_id,
        )
        protected = _acceptance_protection_refs(
            output_root=output_root,
            release_id=normalized_id,
            evidence_roots=evidence_roots,
        )
        if protected:
            refs = "; ".join(str(path) for path in protected)
            raise RuntimeError(
                "GATE_BLOCK release is protected by acceptance evidence; "
                "canonical acceptance revocation is required before "
                f"discard: {refs}"
            )
        shutil.rmtree(release)
        for evidence_root in evidence_roots:
            shutil.rmtree(evidence_root)


def handle_discard(args: argparse.Namespace) -> None:
    release_id = str(getattr(args, "release_id", "") or "").strip()
    try:
        discard_release(release_id)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"[release discard] GATE_BLOCK {exc}") from exc
    print(f"[release discard] removed releaseId={release_id}")


__all__ = ["discard_release"]
