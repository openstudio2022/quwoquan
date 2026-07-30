"""Data-owned append-only release acceptance lease events."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root
from core.schema import assert_valid
from content.release.canonical.release_operation_lock import (
    ReleaseOperationConflict,
    release_operation_guard,
    release_operation_lock_root,
)
from verify.verify_release_lifecycle import environment_lifecycle_issues

SCHEMA = "quwoquan_data.release_acceptance_lease_event"
FILENAME = "acceptance-lease.json"
ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})


class AcceptanceLeaseError(RuntimeError):
    """Acceptance lease evidence is missing, ambiguous, or invalid."""


def _safe_segment(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    candidate = Path(normalized)
    if (
        not normalized
        or normalized in {".", ".."}
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or "/" in normalized
        or "\\" in normalized
    ):
        raise AcceptanceLeaseError(f"{label} must be one safe path segment")
    return normalized


def event_checksum(document: Mapping[str, Any]) -> str:
    unsigned = dict(document)
    unsigned.pop("verificationChecksum", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def event_path(
    *,
    output_root: Path,
    environment: str,
    release_id: str,
    lease_id: str,
    event_id: str,
) -> Path:
    return (
        output_root
        / "env"
        / environment
        / "runs"
        / "release-acceptance"
        / release_id
        / lease_id
        / event_id
        / FILENAME
    )


def validate_lease_event(
    document: Mapping[str, Any],
    *,
    path: Path,
    output_root: Path,
) -> list[str]:
    event = dict(document)
    issues: list[str] = []
    try:
        assert_valid(
            event,
            "release",
            "release_acceptance_lease_event",
            label=f"release_acceptance_lease_event:{path}",
        )
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]
    expected_path = event_path(
        output_root=output_root,
        environment=str(event["environment"]),
        release_id=str(event["releaseId"]),
        lease_id=str(event["leaseId"]),
        event_id=str(event["eventId"]),
    )
    if path.resolve() != expected_path.resolve():
        issues.append(f"{path}: lease path does not bind event identity")
    if event.get("verificationChecksum") != event_checksum(event):
        issues.append(f"{path}: verificationChecksum drift")
    expected_readiness_ref = (
        Path("env")
        / str(event["environment"])
        / "runs"
        / "data-release"
        / str(event["releaseId"])
        / str(event["verifyRunId"])
        / "release-readiness.json"
    ).as_posix()
    if str(event.get("readinessRef") or "") != expected_readiness_ref:
        issues.append(f"{path}: readinessRef does not bind environment/release/verifyRunId")
    action = event.get("action")
    predecessor = str(event.get("predecessorEventRef") or "")
    if action == "acquire" and predecessor:
        issues.append(f"{path}: acquire must not declare predecessorEventRef")
    if action == "revoke" and not predecessor:
        issues.append(f"{path}: revoke must bind predecessorEventRef")
    return issues


def active_acceptance_lease_refs(
    *,
    output_root: Path,
    release_id: str = "",
    environment: str = "",
) -> tuple[Path, ...]:
    """Return active leases in the requested release/environment conflict domain.

    Omitting ``release_id`` intentionally scans every release in the selected
    environment.  Ship and acceptance acquire use this environment-wide view so
    switching from release A to B cannot bypass a persistent UAT lease.
    """

    normalized_release_id = (
        _safe_segment(release_id, label="releaseId") if release_id else ""
    )
    environments = (
        (_safe_segment(environment, label="environment"),)
        if environment
        else tuple(sorted(ENVIRONMENTS))
    )
    active: list[Path] = []
    for current_environment in environments:
        environment_root = (
            output_root
            / "env"
            / current_environment
            / "runs"
            / "release-acceptance"
        )
        if not environment_root.is_dir():
            continue
        release_roots = (
            (environment_root / normalized_release_id,)
            if normalized_release_id
            else tuple(
                sorted(path for path in environment_root.iterdir() if path.is_dir())
            )
        )
        for current_release_root in release_roots:
            if not current_release_root.is_dir():
                continue
            for lease_root in sorted(
                path for path in current_release_root.iterdir() if path.is_dir()
            ):
                events: list[tuple[dict[str, Any], Path]] = []
                for path in sorted(lease_root.glob(f"*/{FILENAME}")):
                    try:
                        document = read_json(path)
                    except (OSError, TypeError, ValueError) as exc:
                        raise AcceptanceLeaseError(
                            f"acceptance lease event is unreadable: {path}"
                        ) from exc
                    if not isinstance(document, dict):
                        raise AcceptanceLeaseError(
                            f"acceptance lease event must be an object: {path}"
                        )
                    issues = validate_lease_event(
                        document,
                        path=path,
                        output_root=output_root,
                    )
                    if issues:
                        raise AcceptanceLeaseError("; ".join(issues))
                    events.append((document, path))
                acquires = [item for item in events if item[0].get("action") == "acquire"]
                if len(acquires) != 1:
                    raise AcceptanceLeaseError(
                        "acceptance lease must contain exactly one acquire event: "
                        f"{lease_root}"
                    )
                acquire, acquire_path = acquires[0]
                canonical_ref = acquire_path.resolve().relative_to(
                    output_root.resolve()
                ).as_posix()
                revokes = [
                    item
                    for item in events
                    if item[0].get("action") == "revoke"
                    and item[0].get("predecessorEventRef") == canonical_ref
                ]
                if len(revokes) > 1:
                    raise AcceptanceLeaseError(
                        f"acceptance lease contains duplicate revoke events: {lease_root}"
                    )
                if not revokes:
                    active.append(acquire_path)
    return tuple(active)


def _readiness_binding(
    *,
    output_root: Path,
    environment: str,
    release_id: str,
    import_run_id: str,
    verify_run_id: str,
    release_root: Path,
) -> tuple[str, str]:
    issues = environment_lifecycle_issues(
        release_id,
        environment=environment,
        import_run_id=import_run_id,
        verify_run_id=verify_run_id,
        release_root=release_root,
        output_root=output_root,
    )
    if issues:
        raise AcceptanceLeaseError("; ".join(issues))
    readiness = (
        output_root
        / "env"
        / environment
        / "runs"
        / "data-release"
        / release_id
        / verify_run_id
        / "release-readiness.json"
    )
    try:
        document = read_json(readiness)
    except (OSError, TypeError, ValueError) as exc:
        raise AcceptanceLeaseError(f"canonical passed readiness is unreadable: {readiness}") from exc
    expected = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": environment,
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "passed": True,
    }
    if not isinstance(document, dict) or any(
        document.get(field) != value for field, value in expected.items()
    ):
        raise AcceptanceLeaseError(f"canonical passed readiness identity drift: {readiness}")
    digest = str(document.get("manifestDigest") or "")
    attestation_path = attestation_root(release_root / release_id) / "release.json"
    try:
        attestation = read_json(attestation_path)
    except (OSError, TypeError, ValueError) as exc:
        raise AcceptanceLeaseError(f"release attestation is unreadable: {attestation_path}") from exc
    if (
        not isinstance(attestation, dict)
        or attestation.get("sourceOwner") != "qwq_data"
        or attestation.get("payloadSha256") != digest
    ):
        raise AcceptanceLeaseError("readiness manifestDigest does not bind immutable release attestation")
    return readiness.relative_to(output_root).as_posix(), digest


def _new_event_id(action: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{action}-{stamp}-{uuid4().hex[:8]}"


def _write_event(
    document: dict[str, Any],
    *,
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    document["verificationChecksum"] = event_checksum(document)
    path = event_path(
        output_root=output_root,
        environment=str(document["environment"]),
        release_id=str(document["releaseId"]),
        lease_id=str(document["leaseId"]),
        event_id=str(document["eventId"]),
    )
    issues = validate_lease_event(document, path=path, output_root=output_root)
    if issues:
        raise AcceptanceLeaseError("; ".join(issues))
    try:
        path.parent.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise AcceptanceLeaseError(f"append-only lease event already exists: {path.parent}") from exc
    write_json(path, document)
    return document, path


def acquire_acceptance_lease(
    *,
    environment: str,
    release_id: str,
    import_run_id: str,
    verify_run_id: str,
    lease_id: str,
    event_id: str = "",
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> tuple[dict[str, Any], Path]:
    environment = _safe_segment(environment, label="environment")
    if environment not in ENVIRONMENTS:
        raise AcceptanceLeaseError(f"environment must be one of {sorted(ENVIRONMENTS)}")
    release_id = _safe_segment(release_id, label="releaseId")
    import_run_id = _safe_segment(import_run_id, label="importRunId")
    verify_run_id = _safe_segment(verify_run_id, label="verifyRunId")
    lease_id = _safe_segment(lease_id, label="leaseId")
    with release_operation_guard(
        lock_root=release_operation_lock_root(release_root),
        release_ids=(release_id,),
        exclusive_releases=True,
        environments=(environment,),
        exclusive_environments=True,
    ):
        lease_root = (
            output_root
            / "env"
            / environment
            / "runs"
            / "release-acceptance"
            / release_id
            / lease_id
        )
        active = active_acceptance_lease_refs(
            output_root=output_root,
            environment=environment,
        )
        if active:
            raise AcceptanceLeaseError(
                "environment already has an active acceptance lease: "
                + ", ".join(path.as_posix() for path in active)
            )
        if lease_root.exists():
            raise AcceptanceLeaseError(
                f"leaseId is create-once and already exists: {lease_root}"
            )
        readiness_ref, digest = _readiness_binding(
            output_root=output_root,
            environment=environment,
            release_id=release_id,
            import_run_id=import_run_id,
            verify_run_id=verify_run_id,
            release_root=release_root,
        )
        document: dict[str, Any] = {
            "schema": SCHEMA,
            "environment": environment,
            "releaseId": release_id,
            "sourceOwner": "qwq_data",
            "manifestDigest": digest,
            "leaseId": lease_id,
            "eventId": _safe_segment(
                event_id or _new_event_id("acquire"), label="eventId"
            ),
            "action": "acquire",
            "holder": "stackctl.content-uat",
            "purpose": "user_acceptance",
            "importRunId": import_run_id,
            "verifyRunId": verify_run_id,
            "readinessRef": readiness_ref,
            "predecessorEventRef": "",
            "recordedAt": datetime.now(timezone.utc).isoformat(),
        }
        return _write_event(document, output_root=output_root)


def _resolve_event_ref(output_root: Path, ref: str) -> Path:
    relative = Path(str(ref or "").strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise AcceptanceLeaseError("acquireEventRef must stay below QWQ_OUTPUT_ROOT")
    path = (output_root / relative).resolve()
    try:
        path.relative_to(output_root.resolve())
    except ValueError as exc:
        raise AcceptanceLeaseError("acquireEventRef escapes QWQ_OUTPUT_ROOT") from exc
    return path


def revoke_acceptance_lease(
    *,
    environment: str,
    release_id: str,
    lease_id: str,
    acquire_event_ref: str,
    event_id: str = "",
    release_root: Path | None = None,
    output_root: Path = OUTPUT_ROOT,
) -> tuple[dict[str, Any], Path]:
    environment = _safe_segment(environment, label="environment")
    if environment not in ENVIRONMENTS:
        raise AcceptanceLeaseError(f"environment must be one of {sorted(ENVIRONMENTS)}")
    release_id = _safe_segment(release_id, label="releaseId")
    lease_id = _safe_segment(lease_id, label="leaseId")
    effective_release_root = release_root or (output_root / "data" / "releases")
    with release_operation_guard(
        lock_root=release_operation_lock_root(effective_release_root),
        release_ids=(release_id,),
        exclusive_releases=True,
        environments=(environment,),
        exclusive_environments=True,
    ):
        acquire_path = _resolve_event_ref(output_root, acquire_event_ref)
        try:
            acquire = read_json(acquire_path)
        except (OSError, TypeError, ValueError) as exc:
            raise AcceptanceLeaseError(
                f"acquire event is unreadable: {acquire_path}"
            ) from exc
        if not isinstance(acquire, dict):
            raise AcceptanceLeaseError(
                f"acquire event must be an object: {acquire_path}"
            )
        issues = validate_lease_event(
            acquire,
            path=acquire_path,
            output_root=output_root,
        )
        expected = {
            "action": "acquire",
            "environment": environment,
            "releaseId": release_id,
            "leaseId": lease_id,
        }
        if issues or any(
            acquire.get(field) != value for field, value in expected.items()
        ):
            raise AcceptanceLeaseError(
                "; ".join(issues or ["acquire event identity drift"])
            )
        canonical_ref = acquire_path.relative_to(output_root.resolve()).as_posix()
        lease_root = acquire_path.parents[1]
        for candidate in lease_root.glob(f"*/{FILENAME}"):
            if candidate == acquire_path:
                continue
            try:
                existing = read_json(candidate)
            except (OSError, TypeError, ValueError) as exc:
                raise AcceptanceLeaseError(
                    f"existing lease event is unreadable: {candidate}"
                ) from exc
            if (
                isinstance(existing, dict)
                and existing.get("action") == "revoke"
                and existing.get("predecessorEventRef") == canonical_ref
            ):
                raise AcceptanceLeaseError(
                    f"acceptance lease is already revoked: {candidate}"
                )
        document: dict[str, Any] = {
            **{
                field: acquire[field]
                for field in (
                    "schema",
                    "environment",
                    "releaseId",
                    "sourceOwner",
                    "manifestDigest",
                    "leaseId",
                    "holder",
                    "purpose",
                    "importRunId",
                    "verifyRunId",
                    "readinessRef",
                )
            },
            "eventId": _safe_segment(
                event_id or _new_event_id("revoke"), label="eventId"
            ),
            "action": "revoke",
            "predecessorEventRef": canonical_ref,
            "recordedAt": datetime.now(timezone.utc).isoformat(),
        }
        return _write_event(document, output_root=output_root)


def handle_acceptance_lease(args: Any) -> None:
    try:
        release_id = str(args.release_id)
        if args.acceptance_lease_action == "acquire":
            document, path = acquire_acceptance_lease(
                environment=str(args.env),
                release_id=release_id,
                import_run_id=str(args.import_run_id),
                verify_run_id=str(args.verify_run_id),
                lease_id=str(args.lease_id),
                event_id=str(args.event_id or ""),
            )
        elif args.acceptance_lease_action == "revoke":
            document, path = revoke_acceptance_lease(
                environment=str(args.env),
                release_id=release_id,
                lease_id=str(args.lease_id),
                acquire_event_ref=str(args.acquire_event_ref),
                event_id=str(args.event_id or ""),
            )
        else:
            raise AcceptanceLeaseError("acceptance lease action is required")
    except (AcceptanceLeaseError, OSError, ReleaseOperationConflict, ValueError) as exc:
        raise SystemExit(f"[release acceptance-lease] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**document, "eventRef": path.relative_to(OUTPUT_ROOT).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


__all__ = [
    "AcceptanceLeaseError",
    "active_acceptance_lease_refs",
    "acquire_acceptance_lease",
    "event_checksum",
    "event_path",
    "handle_acceptance_lease",
    "revoke_acceptance_lease",
    "validate_lease_event",
]
