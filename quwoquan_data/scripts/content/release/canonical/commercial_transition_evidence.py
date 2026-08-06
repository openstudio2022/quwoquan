"""Canonical create-once evidence for research-to-commercial environment cleanup."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.schema import assert_valid

ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})


class CommercialTransitionEvidenceError(RuntimeError):
    """Environment transition evidence is absent, mutable, or identity-drifted."""


@dataclass(frozen=True, slots=True)
class VerifiedCommercialTransitionEvidence:
    document: dict[str, Any]
    path: Path
    evidence_digest: str
    environments: tuple[dict[str, Any], ...]


def document_digest(document: Mapping[str, Any], *, excluded: str) -> str:
    payload = dict(document)
    payload.pop(excluded, None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _safe_segment(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    path = Path(normalized)
    if (
        not normalized
        or normalized in {".", ".."}
        or path.is_absolute()
        or len(path.parts) != 1
        or "/" in normalized
        or "\\" in normalized
    ):
        raise CommercialTransitionEvidenceError(
            f"{label} must be one safe path segment"
        )
    return normalized


def _receipt_path(
    *,
    output_root: Path,
    environment: str,
    commercial_release_id: str,
    run_id: str,
    kind: str,
) -> Path:
    filename = {
        "cleanup": "cleanup-receipt.json",
        "readback": "readback-receipt.json",
    }.get(kind)
    if filename is None:
        raise CommercialTransitionEvidenceError(f"invalid receipt kind: {kind}")
    return (
        output_root
        / "env"
        / environment
        / "runs/commercial-transition"
        / commercial_release_id
        / run_id
        / filename
    )


def _evidence_path(
    *, output_root: Path, commercial_release_id: str, evidence_id: str
) -> Path:
    return (
        output_root
        / "data/commercial-transition-evidence"
        / commercial_release_id
        / evidence_id
        / "evidence.json"
    )


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CommercialTransitionEvidenceError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CommercialTransitionEvidenceError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise CommercialTransitionEvidenceError(f"{label} must be a JSON object")
    return value


def _validate_document(
    document: Mapping[str, Any],
    *,
    schema_name: str,
    digest_field: str,
    label: str,
) -> str:
    payload = dict(document)
    try:
        assert_valid(payload, "release", schema_name, label=label)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise CommercialTransitionEvidenceError(str(exc)) from exc
    actual = document_digest(payload, excluded=digest_field)
    if payload.get(digest_field) != actual:
        raise CommercialTransitionEvidenceError(f"{label} {digest_field} drift")
    return actual


def _publish_create_once(path: Path, document: Mapping[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _write_document(
    *,
    path: Path,
    stable: Mapping[str, Any],
    schema_name: str,
    digest_field: str,
    label: str,
) -> tuple[dict[str, Any], Path]:
    def load_existing() -> dict[str, Any]:
        existing = _read_object(path, label=label)
        _validate_document(
            existing,
            schema_name=schema_name,
            digest_field=digest_field,
            label=label,
        )
        if any(existing.get(key) != value for key, value in stable.items()):
            raise CommercialTransitionEvidenceError(
                f"create-once {label} identity conflict: {path}"
            )
        return existing

    if path.exists() or path.is_symlink():
        return load_existing(), path
    document = {
        **dict(stable),
        "recordedAt": datetime.now(timezone.utc).isoformat(),
    }
    document[digest_field] = document_digest(document, excluded=digest_field)
    _validate_document(
        document,
        schema_name=schema_name,
        digest_field=digest_field,
        label=label,
    )
    if not _publish_create_once(path, document):
        return load_existing(), path
    return document, path


def _identity(
    *,
    environment: str,
    run_id: str,
    research_release_id: str,
    research_manifest_digest: str,
    commercial_release_id: str,
    commercial_manifest_digest: str,
) -> dict[str, str]:
    environment = _safe_segment(environment, label="environment")
    if environment not in ENVIRONMENTS:
        raise CommercialTransitionEvidenceError("environment is invalid")
    return {
        "environment": environment,
        "runId": _safe_segment(run_id, label="runId"),
        "researchReleaseId": _safe_segment(
            research_release_id, label="researchReleaseId"
        ),
        "researchManifestDigest": research_manifest_digest,
        "commercialReleaseId": _safe_segment(
            commercial_release_id, label="commercialReleaseId"
        ),
        "commercialManifestDigest": commercial_manifest_digest,
    }


def write_commercial_transition_cleanup_receipt(
    *,
    environment: str,
    run_id: str,
    research_release_id: str,
    research_manifest_digest: str,
    commercial_release_id: str,
    commercial_manifest_digest: str,
    cache_purged: bool,
    media_copies_purged: bool,
    signed_urls_revoked: bool,
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    identity = _identity(
        environment=environment,
        run_id=run_id,
        research_release_id=research_release_id,
        research_manifest_digest=research_manifest_digest,
        commercial_release_id=commercial_release_id,
        commercial_manifest_digest=commercial_manifest_digest,
    )
    stable = {
        "schema": "quwoquan_data.commercial_transition_cleanup",
        **identity,
        "cachePurged": cache_purged,
        "mediaCopiesPurged": media_copies_purged,
        "signedUrlsRevoked": signed_urls_revoked,
        "passed": True,
    }
    return _write_document(
        path=_receipt_path(
            output_root=output_root,
            environment=identity["environment"],
            commercial_release_id=identity["commercialReleaseId"],
            run_id=identity["runId"],
            kind="cleanup",
        ),
        stable=stable,
        schema_name="commercial_transition_cleanup_receipt",
        digest_field="receiptDigest",
        label="commercial transition cleanup receipt",
    )


def write_commercial_transition_readback_receipt(
    *,
    environment: str,
    run_id: str,
    research_release_id: str,
    research_manifest_digest: str,
    commercial_release_id: str,
    commercial_manifest_digest: str,
    unauthorized_readback_count: int,
    unauthorized_asset_ids: Sequence[str],
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    identity = _identity(
        environment=environment,
        run_id=run_id,
        research_release_id=research_release_id,
        research_manifest_digest=research_manifest_digest,
        commercial_release_id=commercial_release_id,
        commercial_manifest_digest=commercial_manifest_digest,
    )
    stable = {
        "schema": "quwoquan_data.commercial_transition_readback",
        **identity,
        "unauthorizedReadbackCount": unauthorized_readback_count,
        "unauthorizedAssetIds": sorted(str(item) for item in unauthorized_asset_ids),
        "passed": True,
    }
    return _write_document(
        path=_receipt_path(
            output_root=output_root,
            environment=identity["environment"],
            commercial_release_id=identity["commercialReleaseId"],
            run_id=identity["runId"],
            kind="readback",
        ),
        stable=stable,
        schema_name="commercial_transition_readback_receipt",
        digest_field="receiptDigest",
        label="commercial transition readback receipt",
    )


def _load_environment_receipt(
    path: Path,
    *,
    kind: str,
    output_root: Path,
    environment: str,
    research_release_id: str,
    research_manifest_digest: str,
    commercial_release_id: str,
    commercial_manifest_digest: str,
) -> tuple[dict[str, Any], str]:
    document = _read_object(path, label=f"commercial transition {kind} receipt")
    schema_name = f"commercial_transition_{kind}_receipt"
    digest = _validate_document(
        document,
        schema_name=schema_name,
        digest_field="receiptDigest",
        label=f"commercial transition {kind} receipt",
    )
    expected = {
        "environment": environment,
        "researchReleaseId": research_release_id,
        "researchManifestDigest": research_manifest_digest,
        "commercialReleaseId": commercial_release_id,
        "commercialManifestDigest": commercial_manifest_digest,
    }
    if any(document.get(key) != value for key, value in expected.items()):
        raise CommercialTransitionEvidenceError(
            f"{environment}: commercial transition {kind} identity drift"
        )
    expected_path = _receipt_path(
        output_root=output_root,
        environment=environment,
        commercial_release_id=commercial_release_id,
        run_id=str(document.get("runId") or ""),
        kind=kind,
    )
    if path.resolve() != expected_path.resolve():
        raise CommercialTransitionEvidenceError(
            f"{environment}: commercial transition {kind} path is not canonical"
        )
    return document, digest


def _relative(path: Path, *, output_root: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise CommercialTransitionEvidenceError(
            f"{label} must be below QWQ_OUTPUT_ROOT"
        ) from exc


def _referenced_path(ref: object, *, output_root: Path, label: str) -> Path:
    relative = str(ref or "").strip()
    if not relative:
        raise CommercialTransitionEvidenceError(f"{label} is missing")
    path = (output_root / relative).resolve()
    try:
        path.relative_to(output_root.resolve())
    except ValueError as exc:
        raise CommercialTransitionEvidenceError(
            f"{label} escapes QWQ_OUTPUT_ROOT"
        ) from exc
    return path


def write_commercial_transition_evidence(
    *,
    evidence_id: str,
    research_release_id: str,
    research_manifest_digest: str,
    commercial_release_id: str,
    commercial_manifest_digest: str,
    environment_receipts: Sequence[tuple[Path, Path]],
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    evidence_id = _safe_segment(evidence_id, label="evidenceId")
    research_release_id = _safe_segment(
        research_release_id, label="researchReleaseId"
    )
    commercial_release_id = _safe_segment(
        commercial_release_id, label="commercialReleaseId"
    )
    rows: list[dict[str, str]] = []
    for cleanup_path, readback_path in environment_receipts:
        cleanup = _read_object(cleanup_path, label="commercial cleanup receipt")
        environment = str(cleanup.get("environment") or "")
        cleanup_document, cleanup_digest = _load_environment_receipt(
            cleanup_path,
            kind="cleanup",
            output_root=output_root,
            environment=environment,
            research_release_id=research_release_id,
            research_manifest_digest=research_manifest_digest,
            commercial_release_id=commercial_release_id,
            commercial_manifest_digest=commercial_manifest_digest,
        )
        _readback_document, readback_digest = _load_environment_receipt(
            readback_path,
            kind="readback",
            output_root=output_root,
            environment=environment,
            research_release_id=research_release_id,
            research_manifest_digest=research_manifest_digest,
            commercial_release_id=commercial_release_id,
            commercial_manifest_digest=commercial_manifest_digest,
        )
        rows.append(
            {
                "environment": environment,
                "cleanupReceiptRef": _relative(
                    cleanup_path, output_root=output_root, label="cleanup receipt"
                ),
                "cleanupReceiptDigest": cleanup_digest,
                "readbackReceiptRef": _relative(
                    readback_path, output_root=output_root, label="readback receipt"
                ),
                "readbackReceiptDigest": readback_digest,
            }
        )
        if cleanup_document.get("passed") is not True:
            raise CommercialTransitionEvidenceError(
                f"{environment}: cleanup receipt did not pass"
            )
    if {row["environment"] for row in rows} != ENVIRONMENTS or len(rows) != 4:
        raise CommercialTransitionEvidenceError(
            "commercial transition evidence requires exact four environments"
        )
    stable = {
        "schema": "quwoquan_data.commercial_transition_evidence",
        "evidenceId": evidence_id,
        "researchReleaseId": research_release_id,
        "researchManifestDigest": research_manifest_digest,
        "commercialReleaseId": commercial_release_id,
        "commercialManifestDigest": commercial_manifest_digest,
        "environments": sorted(rows, key=lambda row: row["environment"]),
    }
    return _write_document(
        path=_evidence_path(
            output_root=output_root,
            commercial_release_id=commercial_release_id,
            evidence_id=evidence_id,
        ),
        stable=stable,
        schema_name="commercial_transition_evidence",
        digest_field="evidenceDigest",
        label="commercial transition evidence",
    )


def load_commercial_transition_evidence(
    path: Path,
    *,
    research_release_id: str,
    research_manifest_digest: str,
    commercial_release_id: str,
    commercial_manifest_digest: str,
    output_root: Path,
) -> VerifiedCommercialTransitionEvidence:
    document = _read_object(path, label="commercial transition evidence")
    evidence_digest = _validate_document(
        document,
        schema_name="commercial_transition_evidence",
        digest_field="evidenceDigest",
        label="commercial transition evidence",
    )
    expected = {
        "researchReleaseId": research_release_id,
        "researchManifestDigest": research_manifest_digest,
        "commercialReleaseId": commercial_release_id,
        "commercialManifestDigest": commercial_manifest_digest,
    }
    if any(document.get(key) != value for key, value in expected.items()):
        raise CommercialTransitionEvidenceError(
            "commercial transition evidence release identity drift"
        )
    expected_path = _evidence_path(
        output_root=output_root,
        commercial_release_id=commercial_release_id,
        evidence_id=str(document.get("evidenceId") or ""),
    )
    if path.resolve() != expected_path.resolve():
        raise CommercialTransitionEvidenceError(
            "commercial transition evidence path is not canonical"
        )
    projections: list[dict[str, Any]] = []
    rows = document.get("environments")
    if not isinstance(rows, list):
        raise CommercialTransitionEvidenceError(
            "commercial transition evidence environments are missing"
        )
    for row in rows:
        if not isinstance(row, Mapping):
            raise CommercialTransitionEvidenceError(
                "commercial transition environment evidence is invalid"
            )
        environment = str(row.get("environment") or "")
        cleanup_ref = str(row.get("cleanupReceiptRef") or "")
        readback_ref = str(row.get("readbackReceiptRef") or "")
        cleanup, cleanup_digest = _load_environment_receipt(
            _referenced_path(
                cleanup_ref, output_root=output_root, label="cleanupReceiptRef"
            ),
            kind="cleanup",
            output_root=output_root,
            environment=environment,
            research_release_id=research_release_id,
            research_manifest_digest=research_manifest_digest,
            commercial_release_id=commercial_release_id,
            commercial_manifest_digest=commercial_manifest_digest,
        )
        readback, readback_digest = _load_environment_receipt(
            _referenced_path(
                readback_ref, output_root=output_root, label="readbackReceiptRef"
            ),
            kind="readback",
            output_root=output_root,
            environment=environment,
            research_release_id=research_release_id,
            research_manifest_digest=research_manifest_digest,
            commercial_release_id=commercial_release_id,
            commercial_manifest_digest=commercial_manifest_digest,
        )
        if (
            row.get("cleanupReceiptDigest") != cleanup_digest
            or row.get("readbackReceiptDigest") != readback_digest
        ):
            raise CommercialTransitionEvidenceError(
                f"{environment}: environment receipt digest drift"
            )
        projections.append(
            {
                "environment": environment,
                "cachePurged": cleanup["cachePurged"],
                "mediaCopiesPurged": cleanup["mediaCopiesPurged"],
                "signedUrlsRevoked": cleanup["signedUrlsRevoked"],
                "unauthorizedReadbackCount": readback[
                    "unauthorizedReadbackCount"
                ],
                "cleanupReceiptRef": cleanup_ref,
                "cleanupReceiptDigest": cleanup_digest,
                "readbackReceiptRef": readback_ref,
                "readbackReceiptDigest": readback_digest,
            }
        )
    if (
        {row["environment"] for row in projections} != ENVIRONMENTS
        or len(projections) != 4
    ):
        raise CommercialTransitionEvidenceError(
            "commercial transition evidence requires exact four environments"
        )
    return VerifiedCommercialTransitionEvidence(
        document=document,
        path=path,
        evidence_digest=evidence_digest,
        environments=tuple(sorted(projections, key=lambda row: row["environment"])),
    )


__all__ = [
    "CommercialTransitionEvidenceError",
    "VerifiedCommercialTransitionEvidence",
    "document_digest",
    "load_commercial_transition_evidence",
    "write_commercial_transition_cleanup_receipt",
    "write_commercial_transition_evidence",
    "write_commercial_transition_readback_receipt",
]
