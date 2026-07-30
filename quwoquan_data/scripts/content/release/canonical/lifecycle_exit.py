"""Create-once rollback/replay Exit evidence from existing environment runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root
from content.release.canonical.release_operation_lock import (
    ReleaseOperationConflict,
    release_operation_guard,
    release_operation_lock_root,
)
from verify.release_lifecycle_attestation import read_object
from verify.release_lifecycle_exit import checksum, lifecycle_exit_issues, receipt_path


class ReleaseLifecycleExitError(RuntimeError):
    """Existing run evidence cannot prove rollback and same-digest replay."""


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
        raise ReleaseLifecycleExitError(f"{label} must be one safe path segment")
    return normalized


def _manifest_digest(release_root: Path, release_id: str) -> str:
    issues: list[str] = []
    path = attestation_root(release_root / release_id) / "release.json"
    document = read_object(path, label="release attestation", issues=issues)
    digest = str(document.get("payloadSha256") or "")
    if issues or not digest:
        raise ReleaseLifecycleExitError("; ".join(issues or [f"{path}: payloadSha256 missing"]))
    return digest


def _result_ref(environment: str, release_id: str, run_id: str) -> str:
    return (
        Path("env")
        / environment
        / "runs"
        / "data-release"
        / release_id
        / run_id
        / "result.json"
    ).as_posix()


def write_lifecycle_exit_receipt(
    *,
    environment: str,
    original_release_id: str,
    original_import_run_id: str,
    original_verify_run_id: str,
    rollback_to_release_id: str,
    rollback_run_id: str,
    rollback_verify_run_id: str,
    replay_import_run_id: str,
    replay_verify_run_id: str,
    exit_run_id: str,
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> tuple[dict[str, Any], Path]:
    values = {
        name: _safe_segment(value, label=name)
        for name, value in {
            "environment": environment,
            "originalReleaseId": original_release_id,
            "originalImportRunId": original_import_run_id,
            "originalVerifyRunId": original_verify_run_id,
            "rollbackToReleaseId": rollback_to_release_id,
            "rollbackRunId": rollback_run_id,
            "rollbackVerifyRunId": rollback_verify_run_id,
            "replayImportRunId": replay_import_run_id,
            "replayVerifyRunId": replay_verify_run_id,
            "exitRunId": exit_run_id,
        }.items()
    }
    original = values["originalReleaseId"]
    rollback_to = values["rollbackToReleaseId"]
    original_digest = _manifest_digest(release_root, original)
    rollback_digest = _manifest_digest(release_root, rollback_to)
    document: dict[str, Any] = {
        "schema": "quwoquan_data.environment_release_lifecycle_exit",
        "environment": values["environment"],
        "sourceOwner": "qwq_data",
        "exitRunId": values["exitRunId"],
        "originalReleaseId": original,
        "originalManifestDigest": original_digest,
        "originalImportRunId": values["originalImportRunId"],
        "originalVerifyRunId": values["originalVerifyRunId"],
        "originalImportResultRef": _result_ref(
            values["environment"], original, values["originalImportRunId"]
        ),
        "originalVerifyResultRef": _result_ref(
            values["environment"], original, values["originalVerifyRunId"]
        ),
        "rollbackToReleaseId": rollback_to,
        "rollbackToManifestDigest": rollback_digest,
        "rollbackRunId": values["rollbackRunId"],
        "rollbackVerifyRunId": values["rollbackVerifyRunId"],
        "rollbackResultRef": _result_ref(
            values["environment"], rollback_to, values["rollbackRunId"]
        ),
        "rollbackVerifyResultRef": _result_ref(
            values["environment"], rollback_to, values["rollbackVerifyRunId"]
        ),
        "replayImportRunId": values["replayImportRunId"],
        "replayVerifyRunId": values["replayVerifyRunId"],
        "replayManifestDigest": original_digest,
        "replayImportResultRef": _result_ref(
            values["environment"], original, values["replayImportRunId"]
        ),
        "replayVerifyResultRef": _result_ref(
            values["environment"], original, values["replayVerifyRunId"]
        ),
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "passed": True,
    }
    document["verificationChecksum"] = checksum(document)
    path = receipt_path(
        output_root=output_root,
        environment=values["environment"],
        original_release_id=original,
        exit_run_id=values["exitRunId"],
    )
    issues = lifecycle_exit_issues(
        document,
        path=path,
        release_root=release_root,
        output_root=output_root,
    )
    if issues:
        raise ReleaseLifecycleExitError("; ".join(issues))
    try:
        path.parent.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ReleaseLifecycleExitError(f"append-only Exit run already exists: {path.parent}") from exc
    write_json(path, document)
    return document, path


def handle_lifecycle_exit(args: Any) -> None:
    try:
        original_release_id = str(args.original_release_id)
        rollback_to_release_id = str(args.rollback_to_release_id)
        with release_operation_guard(
            lock_root=release_operation_lock_root(RELEASE_ROOT),
            release_ids=(original_release_id, rollback_to_release_id),
        ):
            document, path = write_lifecycle_exit_receipt(
                environment=str(args.env),
                original_release_id=original_release_id,
                original_import_run_id=str(args.original_import_run_id),
                original_verify_run_id=str(args.original_verify_run_id),
                rollback_to_release_id=rollback_to_release_id,
                rollback_run_id=str(args.rollback_run_id),
                rollback_verify_run_id=str(args.rollback_verify_run_id),
                replay_import_run_id=str(args.replay_import_run_id),
                replay_verify_run_id=str(args.replay_verify_run_id),
                exit_run_id=str(args.run_id),
            )
    except (OSError, ReleaseLifecycleExitError, ReleaseOperationConflict, ValueError) as exc:
        raise SystemExit(f"[release lifecycle-exit] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {**document, "receiptRef": path.relative_to(OUTPUT_ROOT).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


__all__ = ["ReleaseLifecycleExitError", "handle_lifecycle_exit", "write_lifecycle_exit_receipt"]
