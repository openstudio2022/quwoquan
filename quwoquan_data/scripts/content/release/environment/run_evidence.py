"""Schema-bound append-only environment release run evidence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

_MAX_PATH_SEGMENT_BYTES = 255
_VERIFY_PREDEPOSITED_FILES = frozenset({"research-isolation-runtime-proof.json"})
_RESULT_REF_FIELDS = (
    "lifecycleExitRef",
    "homepageVerificationCasesRef",
    "tagImportReportRef",
    "creatorImportReportRef",
    "contentImportReportRef",
    "homepageImportReportRef",
    "coverageReceiptRef",
    "postApiVerificationRef",
    "releaseReadinessRef",
    "researchIsolationVerificationRef",
    "tagConsumerVerificationRef",
    "homepageApiVerificationRef",
    "baselineApiVerificationRef",
    "contentCandidateReceiptRef",
    "contentPreActiveReceiptRef",
    "contentActivationReceiptRef",
    "contentPostActiveReceiptRef",
)


def validate_path_segment(value: str, *, label: str) -> str:
    """Validate one user-controlled identity as exactly one safe path segment."""

    segment = str(value)
    encoded = segment.encode("utf-8")
    if (
        not segment
        or segment != segment.strip()
        or segment in {".", ".."}
        or Path(segment).is_absolute()
        or "/" in segment
        or "\\" in segment
        or any(ord(character) < 32 or ord(character) == 127 for character in segment)
        or len(encoded) > _MAX_PATH_SEGMENT_BYTES
    ):
        raise SystemExit(
            f"[ship] {label} 必须是单一安全路径段且不超过 "
            f"{_MAX_PATH_SEGMENT_BYTES} bytes"
        )
    return segment


def _assert_no_symlink_components(path: Path, *, label: str) -> None:
    absolute = path.absolute()
    # macOS exposes these root-owned aliases as part of its filesystem layout.
    # They are outside the release writer's trust boundary and resolve to fixed
    # root-owned directories; all caller-selected descendants remain no-symlink.
    platform_aliases = {
        Path("/tmp"): Path("/private/tmp"),
        Path("/var"): Path("/private/var"),
    }
    for candidate in reversed((absolute, *absolute.parents)):
        if not candidate.is_symlink():
            continue
        expected = platform_aliases.get(candidate)
        if expected is not None and candidate.resolve() == expected:
            continue
        raise SystemExit(f"[ship] {label} 不得包含 symlink：{candidate}")


def _canonical_json_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(document),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _canonical_document_checksum(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def create_once_canonical_json(path: Path, document: Mapping[str, Any]) -> None:
    """Durably create canonical JSON via hardlink, failing closed otherwise."""

    _assert_no_symlink_components(path.parent, label="evidence parent")
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink_components(path.parent, label="evidence parent")
    if path.is_symlink():
        raise FileExistsError(f"create-once target is a symlink: {path}")
    payload = _canonical_json_bytes(document)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary:
            try:
                Path(temporary).unlink()
            except FileNotFoundError:
                pass


def read_environment_result(
    path: Path,
    *,
    expected: Mapping[str, object] | None = None,
    required_status: str | None = None,
    label: str = "environment release result",
) -> dict[str, Any]:
    """Read one sealed result and verify its schema, checksum, and bindings."""

    _assert_no_symlink_components(path, label=label)
    if not path.is_file():
        raise SystemExit(f"[ship] {label} 必须是普通文件：{path}")
    try:
        value = read_json(path)
        if not isinstance(value, Mapping):
            raise ValueError(f"{label} 必须是对象")
        document = dict(value)
        assert_valid(
            document,
            "release",
            "environment_release_result",
            label=f"environment_release_result:{path}",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[ship] {label} 非法：{exc}") from exc

    unsigned = dict(document)
    declared_checksum = str(unsigned.pop("verificationChecksum", ""))
    if declared_checksum != _canonical_document_checksum(unsigned):
        raise SystemExit(f"[ship] {label} verificationChecksum drift：{path}")
    if required_status is not None and document.get("status") != required_status:
        raise SystemExit(
            f"[ship] {label} status 不一致：expected={required_status} "
            f"actual={document.get('status')}"
        )
    for field, expected_value in dict(expected or {}).items():
        if document.get(field) != expected_value:
            raise SystemExit(
                f"[ship] {label} {field} 不一致：expected={expected_value} "
                f"actual={document.get(field)}"
            )
    return document


def _with_result_timing(path: Path, document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    run_identity = read_json(path.parent / "run.json")
    started_at = str(payload.get("startedAt") or run_identity.get("startedAt") or "")
    ended_at = str(payload.get("endedAt") or datetime.now(timezone.utc).isoformat())
    started = datetime.fromisoformat(started_at)
    ended = datetime.fromisoformat(ended_at)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if ended.tzinfo is None:
        ended = ended.replace(tzinfo=timezone.utc)
    payload["startedAt"] = started_at
    payload["endedAt"] = ended_at
    payload.setdefault(
        "durationMs",
        max(
            0,
            int(
                (
                    ended.astimezone(timezone.utc) - started.astimezone(timezone.utc)
                ).total_seconds()
                * 1000
            ),
        ),
    )
    return payload


def write_environment_result(path: Path, result: Mapping[str, Any]) -> None:
    """Enrich, seal, validate, and create one terminal environment result."""

    document = _with_result_timing(path, result)
    document.pop("verificationChecksum", None)
    for field in _RESULT_REF_FIELDS:
        document.setdefault(field, "")
    document["verificationChecksum"] = _canonical_document_checksum(document)
    assert_valid(
        document,
        "release",
        "environment_release_result",
        label=f"environment_release_result:{path}",
    )
    create_once_canonical_json(path, document)


def write_release_evidence(
    path: Path,
    document: Mapping[str, Any],
    schema_name: str,
) -> None:
    if schema_name == "environment_release_result":
        write_environment_result(path, document)
        return
    payload = dict(document)
    assert_valid(payload, "release", schema_name, label=f"{schema_name}:{path}")
    create_once_canonical_json(path, payload)


def write_verification_result(path: Path, result: Mapping[str, Any]) -> None:
    """Compatibility injection name for the unique environment result writer."""

    write_environment_result(path, result)


def _assert_run_directory_admissible(run: Path, *, kind: str) -> None:
    _assert_no_symlink_components(run, label="run path")
    if run.exists() and not run.is_dir():
        raise SystemExit(f"[ship] run path 必须是目录：{run}")
    run.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink_components(run, label="run path")
    entries = tuple(run.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise SystemExit(f"[ship] run 目录不得包含 symlink：{run}")
    if any(entry.name == "run.json" for entry in entries):
        raise SystemExit(f"[ship] append-only run 已存在：{run}")
    allowed = _VERIFY_PREDEPOSITED_FILES if kind == "verify" else frozenset()
    unexpected = sorted(entry.name for entry in entries if entry.name not in allowed)
    if unexpected:
        raise SystemExit(
            f"[ship] run 目录含预存证据，拒绝复用：{run}: " + ", ".join(unexpected)
        )
    for entry in entries:
        if not entry.is_file():
            raise SystemExit(f"[ship] verify 预存 proof 必须是普通文件：{entry}")


def create_run(
    *,
    output_root: Path,
    environment: str,
    release_id: str,
    run_id: str,
    kind: str,
    valid_environments: frozenset[str],
) -> Path:
    if environment not in valid_environments:
        raise SystemExit(f"[ship] environment 非法：{environment}")
    safe_release_id = validate_path_segment(release_id, label="release_id")
    safe_run_id = validate_path_segment(run_id, label="run_id")
    run_kind = str(kind)
    run = (
        output_root
        / "env"
        / environment
        / "runs"
        / "data-release"
        / safe_release_id
        / safe_run_id
    )
    _assert_run_directory_admissible(run, kind=run_kind)
    try:
        write_release_evidence(
            run / "run.json",
            {
                "schema": "quwoquan_data.environment_release_run",
                "environment": environment,
                "releaseId": safe_release_id,
                "runId": safe_run_id,
                "kind": run_kind,
                "startedAt": datetime.now(timezone.utc).isoformat(),
            },
            "environment_release_run",
        )
    except FileExistsError as exc:
        raise SystemExit(f"[ship] append-only run 已存在：{run}") from exc
    return run


def write_applied_ref(
    *,
    output_root: Path,
    run: Path,
    environment: str,
    release_id: str,
    release_ref: str,
) -> None:
    write_release_evidence(
        run / "applied_ref.json",
        {
            "schema": "quwoquan_data.applied_release_ref",
            "environment": environment,
            "releaseId": release_id,
            "releaseRef": release_ref,
            "evidenceRef": run.relative_to(output_root).as_posix(),
        },
        "applied_release_ref",
    )


__all__ = [
    "create_once_canonical_json",
    "create_run",
    "read_environment_result",
    "validate_path_segment",
    "write_applied_ref",
    "write_environment_result",
    "write_release_evidence",
    "write_verification_result",
]
