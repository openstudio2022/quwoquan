"""Run-bound content evidence for one mutable non-production runtime.

The binding deliberately does not create or consume an immutable deployment
candidate.  It joins an already-running ``test_live`` startup attempt to an
explicit Data release readiness receipt and, for commercial readiness, its
rollback/replay lifecycle exit.  The resulting target-scoped record is always
non-promotable and create-once.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .app_content_uat_plan import build_app_content_uat_plan
from .output_paths import env_runs_root, output_root, target_process_dir
from .test_live_startup_attempt_receipt import (
    test_live_startup_attempt_path,
    validate_test_live_startup_attempt,
)

SCHEMA = "stackctl.mutable_test_live_content_binding.v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}")
_BINDING_FIELDS = frozenset(
    {
        "schema",
        "launchPolicy",
        "nonPromotable",
        "contentBindingState",
        "retentionClass",
        "environment",
        "target",
        "startupAttemptId",
        "startupIdentity",
        "releaseId",
        "verifyRunId",
        "manifestDigest",
        "readinessPhase",
        "releaseAttestationRef",
        "releaseAttestationDigest",
        "readinessReceiptRef",
        "readinessReceiptDigest",
        "dataSourceIdentity",
        "appUatEnvelope",
        "appUatEnvelopeDigest",
        "appUatPlan",
        "appUatPlanDigest",
        "activationEnvelope",
        "activationEnvelopeDigest",
        "lifecycleExitRef",
        "lifecycleExitDigest",
        "boundAt",
    }
)
_STARTUP_IDENTITY_FIELDS = (
    "sourceRevision",
    "workspaceStatusDigest",
    "mutableStateDigest",
    "composeDigest",
    "configurationDigest",
    "providerRuntimeDigest",
    "resolverHandoffDigest",
)
_LIFECYCLE_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "sourceOwner",
        "exitRunId",
        "originalReleaseId",
        "originalManifestDigest",
        "originalImportRunId",
        "originalVerifyRunId",
        "originalImportResultRef",
        "originalVerifyResultRef",
        "rollbackToReleaseId",
        "rollbackToManifestDigest",
        "rollbackRunId",
        "rollbackVerifyRunId",
        "rollbackResultRef",
        "rollbackVerifyResultRef",
        "replayImportRunId",
        "replayVerifyRunId",
        "replayManifestDigest",
        "replayImportResultRef",
        "replayVerifyResultRef",
        "recordedAt",
        "verificationChecksum",
        "passed",
    }
)


class UnsafeTestLiveContentBindingPath(ValueError):
    """An evidence or binding path could not be read without following links."""


@dataclass(frozen=True)
class _RegularJson:
    value: dict[str, Any]
    digest: str
    identity: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class _Evidence:
    startup: dict[str, Any]
    startup_snapshot: _RegularJson
    attestation: dict[str, Any]
    attestation_snapshot: _RegularJson
    readiness: dict[str, Any]
    readiness_snapshot: _RegularJson
    readiness_phase: str
    source_identity: dict[str, Any]
    attestation_ref: str
    readiness_ref: str
    lifecycle: dict[str, Any] | None
    lifecycle_snapshot: _RegularJson | None
    lifecycle_ref: str


def test_live_content_binding_path(target: str, startup_attempt_id: str) -> Path:
    """Return one target-and-attempt-scoped binding path without creating it."""

    attempt_id = _safe_segment(startup_attempt_id, label="startupAttemptId")
    return target_process_dir(target) / f"test_live_content_binding.{attempt_id}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_segment(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if _SEGMENT.fullmatch(text) is None or text in {".", ".."}:
        raise ValueError(f"test-live content binding {label} is invalid")
    return text


def _canonical_digest(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if _DIGEST.fullmatch(text) is None:
        raise ValueError(
            f"test-live content binding {label} must be sha256:<64 lowercase hex>"
        )
    return text


def _document_checksum(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _source_identity(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    scalar_fields = ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    set_fields = ("sourceIdentities", "sourceIdentitySetDigest")
    present_scalar = {field for field in scalar_fields if field in value}
    present_set = {field for field in set_fields if field in value}
    if present_scalar and present_set:
        raise ValueError(f"{label} source identity representations must not be mixed")
    if present_scalar:
        if present_scalar != set(scalar_fields):
            raise ValueError(f"{label} scalar source identity is incomplete")
        return {
            field: _canonical_digest(value.get(field), label=f"{label} {field}")
            for field in scalar_fields
        }
    if present_set != set(set_fields):
        raise ValueError(f"{label} aggregate source identity is incomplete")
    raw_identities = value.get("sourceIdentities")
    if not isinstance(raw_identities, list) or not raw_identities:
        raise ValueError(f"{label} sourceIdentities must be a non-empty array")
    identities: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_identities):
        if not isinstance(raw, Mapping):
            raise ValueError(f"{label} sourceIdentities[{index}] must be an object")
        is_legacy = raw.get("identityKind") == "legacy_canonical_migration"
        digest_fields = (
            ("sourceDigest", "canonicalObjectDigest", "migrationEvidenceDigest")
            if is_legacy
            else scalar_fields
        )
        expected_fields = {*digest_fields, "executionIds"}
        if is_legacy:
            expected_fields.add("identityKind")
        if set(raw) != expected_fields:
            raise ValueError(f"{label} sourceIdentities[{index}] fields mismatch")
        execution_ids = raw.get("executionIds")
        if (
            not isinstance(execution_ids, list)
            or not execution_ids
            or any(not isinstance(item, str) or not item.strip() for item in execution_ids)
            or execution_ids != sorted(set(execution_ids))
        ):
            raise ValueError(
                f"{label} sourceIdentities[{index}].executionIds must be sorted unique strings"
            )
        identity: dict[str, Any] = {
            field: _canonical_digest(
                raw.get(field),
                label=f"{label} sourceIdentities[{index}].{field}",
            )
            for field in digest_fields
        }
        if is_legacy:
            identity["identityKind"] = "legacy_canonical_migration"
        identity["executionIds"] = list(execution_ids)
        identities.append(identity)
    identity_keys = [
        (
            (
                "legacy_canonical_migration",
                item["sourceDigest"],
                item["canonicalObjectDigest"],
                item["migrationEvidenceDigest"],
            )
            if item.get("identityKind") == "legacy_canonical_migration"
            else (
                "modern_execution",
                item["sourceRevision"],
                item["sourceDigest"],
                item["entityCatalogDigest"],
            )
        )
        for item in identities
    ]
    if identity_keys != sorted(identity_keys) or len(identity_keys) != len(
        set(identity_keys)
    ):
        raise ValueError(f"{label} sourceIdentities must be canonically sorted")
    set_digest = _canonical_digest(
        value.get("sourceIdentitySetDigest"),
        label=f"{label} sourceIdentitySetDigest",
    )
    expected_digest = _document_checksum(
        {
            "schema": "quwoquan_data.source_identity_set",
            "sourceIdentities": identities,
        }
    )
    if set_digest != expected_digest:
        raise ValueError(f"{label} sourceIdentitySetDigest mismatch")
    return {
        "sourceIdentities": identities,
        "sourceIdentitySetDigest": set_digest,
    }


def _copy_source_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value), ensure_ascii=False))


def _file_digest(encoded: bytes) -> str:
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError("test-live content binding requires O_NOFOLLOW/O_DIRECTORY")
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _file_flags(*, create: bool = False) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("test-live content binding requires O_NOFOLLOW")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL if create else os.O_RDONLY
    return flags | nofollow | getattr(os, "O_CLOEXEC", 0)


def _open_directory_chain(path: Path, *, label: str) -> tuple[int, tuple[tuple[int, int], ...]]:
    absolute = path.expanduser().absolute()
    if not absolute.is_absolute() or ".." in absolute.parts:
        raise UnsafeTestLiveContentBindingPath(f"{label} parent path is unsafe")
    descriptor = os.open(Path(absolute.anchor), _directory_flags())
    identities: list[tuple[int, int]] = []
    try:
        root = os.fstat(descriptor)
        identities.append((root.st_dev, root.st_ino))
        for part in absolute.parts[1:]:
            try:
                child = os.open(part, _directory_flags(), dir_fd=descriptor)
            except OSError as exc:
                raise UnsafeTestLiveContentBindingPath(
                    f"{label} parent is a symlink, missing, or non-directory: {part}"
                ) from exc
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            identities.append((info.st_dev, info.st_ino))
        return descriptor, tuple(identities)
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_directory_chain(
    path: Path,
    *,
    label: str,
    identities: tuple[tuple[int, int], ...],
) -> None:
    descriptor, observed = _open_directory_chain(path, label=label)
    os.close(descriptor)
    if observed != identities:
        raise UnsafeTestLiveContentBindingPath(f"{label} parent changed during access")


def _regular_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_regular_json(path: Path, *, label: str, optional: bool = False) -> _RegularJson | None:
    try:
        parent_descriptor, parent_identities = _open_directory_chain(
            path.parent,
            label=label,
        )
    except UnsafeTestLiveContentBindingPath:
        if optional and not path.parent.exists():
            return None
        raise
    descriptor = -1
    try:
        try:
            before = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            if optional:
                return None
            raise ValueError(f"{label} is missing")
        if not stat.S_ISREG(before.st_mode):
            raise UnsafeTestLiveContentBindingPath(
                f"{label} is a symlink or non-regular file"
            )
        try:
            descriptor = os.open(path.name, _file_flags(), dir_fd=parent_descriptor)
        except OSError as exc:
            raise UnsafeTestLiveContentBindingPath(
                f"{label} is a symlink or unreadable"
            ) from exc
        opened = os.fstat(descriptor)
        identity = _regular_identity(opened)
        if not stat.S_ISREG(opened.st_mode) or identity != _regular_identity(before):
            raise UnsafeTestLiveContentBindingPath(f"{label} changed during access")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
        if _regular_identity(after_fd) != identity:
            raise UnsafeTestLiveContentBindingPath(f"{label} changed during access")
        encoded = b"".join(chunks)
        _revalidate_directory_chain(
            path.parent,
            label=label,
            identities=parent_identities,
        )
        after = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not stat.S_ISREG(after.st_mode) or _regular_identity(after) != identity:
            raise UnsafeTestLiveContentBindingPath(f"{label} changed during access")
    except FileNotFoundError as exc:
        raise UnsafeTestLiveContentBindingPath(f"{label} changed during access") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return _RegularJson(dict(value), _file_digest(encoded), identity)


def _canonical_ref(path: Path, *, root: Path, label: str) -> str:
    absolute_root = root.expanduser().absolute()
    absolute_path = path.expanduser().absolute()
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes QWQ_OUTPUT_ROOT") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{label} is not canonical")
    return relative.as_posix()


def _validate_attestation(
    value: Mapping[str, Any],
    *,
    release_id: str,
    manifest_digest: str,
) -> tuple[str, str, dict[str, Any]]:
    expected = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "releaseKind": "content",
        "payloadSha256": manifest_digest,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise ValueError(f"Data release attestation {field} mismatch")
    release_class = str(value.get("releaseClass") or "")
    lifecycle_state = str(value.get("productLifecycleState") or "")
    if release_class not in {"research", "commercial"} or lifecycle_state != release_class:
        raise ValueError("Data release attestation lifecycle identity mismatch")
    source_identity = _source_identity(value, label="attestation")
    return release_class, lifecycle_state, source_identity


def _validate_readiness(
    value: Mapping[str, Any],
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    release_class: str,
    lifecycle_state: str,
    source_identity: Mapping[str, Any],
) -> str:
    expected = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": environment,
        "releaseId": release_id,
        "releaseKind": "content",
        "sourceOwner": "qwq_data",
        "manifestDigest": manifest_digest,
        "verifyRunId": verify_run_id,
        "releaseClass": release_class,
        "productLifecycleState": lifecycle_state,
        "passed": True,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise ValueError(f"Data readiness {field} mismatch")
    phase = str(value.get("readinessPhase") or "")
    if phase not in {"consumer", "research", "commercial"}:
        raise ValueError(
            "test-live content binding requires consumer, research, or commercial readiness"
        )
    if phase == "research" and release_class != "research":
        raise ValueError("research readiness must bind a research release")
    if phase == "commercial" and release_class != "commercial":
        raise ValueError("commercial readiness must bind a commercial release")
    if not str(value.get("importRunId") or "").strip():
        raise ValueError("Data readiness importRunId is missing")
    for field, expected_value in source_identity.items():
        if value.get(field) != expected_value:
            raise ValueError(f"Data readiness {field} mismatch")
    if _source_identity(value, label="Data readiness") != source_identity:
        raise ValueError("Data readiness source identity mismatch")
    checksum = dict(value)
    declared = str(checksum.pop("verificationChecksum", ""))
    if declared != _document_checksum(checksum):
        raise ValueError("Data readiness verificationChecksum mismatch")
    envelope = value.get("appUatEnvelope")
    if not isinstance(envelope, Mapping):
        raise ValueError("Data readiness is missing canonical appUatEnvelope")
    for field, expected_value in (
        ("releaseId", release_id),
        ("releaseClass", release_class),
        ("productLifecycleState", lifecycle_state),
    ):
        if envelope.get(field) != expected_value:
            raise ValueError(f"Data readiness appUatEnvelope {field} mismatch")
    app_uat_digest = _document_checksum(envelope)
    if value.get("appUatEnvelopeDigest") != app_uat_digest:
        raise ValueError("Data readiness appUatEnvelopeDigest mismatch")
    activation = value.get("activationEnvelope")
    if not isinstance(activation, Mapping):
        raise ValueError("Data readiness is missing canonical activationEnvelope")
    expected_activation = {
        "schema": "quwoquan_data.environment_activation_envelope",
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        **source_identity,
        "releaseClass": release_class,
        "productLifecycleState": lifecycle_state,
        "readinessPhase": phase,
        "importRunId": value["importRunId"],
        "verifyRunId": verify_run_id,
        "appUatEnvelopeDigest": app_uat_digest,
    }
    for field, expected_value in expected_activation.items():
        if activation.get(field) != expected_value:
            raise ValueError(f"Data readiness activationEnvelope {field} mismatch")
    if _source_identity(activation, label="Data readiness activationEnvelope") != source_identity:
        raise ValueError("Data readiness activationEnvelope source identity mismatch")
    for field in ("importReportRef", "importReportDigest"):
        if not str(activation.get(field) or "").strip():
            raise ValueError(f"Data readiness activationEnvelope {field} is missing")
    if value.get("activationEnvelopeDigest") != _document_checksum(activation):
        raise ValueError("Data readiness activationEnvelopeDigest mismatch")
    return phase


def _validate_lifecycle(
    value: Mapping[str, Any],
    *,
    environment: str,
    release_id: str,
    manifest_digest: str,
    exit_run_id: str,
    readiness: Mapping[str, Any],
) -> None:
    if set(value) != _LIFECYCLE_FIELDS:
        raise ValueError("Data lifecycle Exit receipt fields mismatch")
    expected = {
        "schema": "quwoquan_data.environment_release_lifecycle_exit",
        "environment": environment,
        "sourceOwner": "qwq_data",
        "exitRunId": exit_run_id,
        "originalReleaseId": release_id,
        "originalManifestDigest": manifest_digest,
        "replayManifestDigest": manifest_digest,
        "passed": True,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise ValueError(f"Data lifecycle Exit {field} mismatch")
    checksum = dict(value)
    declared = str(checksum.pop("verificationChecksum", ""))
    if declared != _document_checksum(checksum):
        raise ValueError("Data lifecycle Exit verificationChecksum mismatch")
    _canonical_digest(value.get("rollbackToManifestDigest"), label="rollback manifest")
    if value.get("rollbackToReleaseId") == release_id:
        raise ValueError("Data lifecycle Exit rollback release must differ")
    run_fields = (
        "originalImportRunId",
        "originalVerifyRunId",
        "rollbackRunId",
        "rollbackVerifyRunId",
        "replayImportRunId",
        "replayVerifyRunId",
    )
    run_ids = [str(value.get(field) or "").strip() for field in run_fields]
    if any(not item for item in run_ids) or len(set(run_ids)) != len(run_ids):
        raise ValueError("Data lifecycle Exit run IDs must be non-empty and distinct")
    rollback_release_id = _safe_segment(
        value.get("rollbackToReleaseId"),
        label="rollback releaseId",
    )
    expected_refs = {
        "originalImportResultRef": (
            f"env/{environment}/runs/data-release/{release_id}/"
            f"{value['originalImportRunId']}/result.json"
        ),
        "originalVerifyResultRef": (
            f"env/{environment}/runs/data-release/{release_id}/"
            f"{value['originalVerifyRunId']}/result.json"
        ),
        "rollbackResultRef": (
            f"env/{environment}/runs/data-release/{rollback_release_id}/"
            f"{value['rollbackRunId']}/result.json"
        ),
        "rollbackVerifyResultRef": (
            f"env/{environment}/runs/data-release/{rollback_release_id}/"
            f"{value['rollbackVerifyRunId']}/result.json"
        ),
        "replayImportResultRef": (
            f"env/{environment}/runs/data-release/{release_id}/"
            f"{value['replayImportRunId']}/result.json"
        ),
        "replayVerifyResultRef": (
            f"env/{environment}/runs/data-release/{release_id}/"
            f"{value['replayVerifyRunId']}/result.json"
        ),
    }
    for field, expected_ref in expected_refs.items():
        if value.get(field) != expected_ref:
            raise ValueError(f"Data lifecycle Exit {field} is not canonical")
    readiness_import = str(readiness.get("importRunId") or "").strip()
    readiness_verify = str(readiness.get("verifyRunId") or "").strip()
    commercial_on_replay = (
        readiness.get("readinessPhase") == "commercial"
        and readiness_import == value.get("replayImportRunId")
    )
    if not commercial_on_replay and (
        value.get("originalImportRunId") != readiness_import
        or value.get("originalVerifyRunId") != readiness_verify
    ):
        raise ValueError("Data lifecycle Exit does not bind the readiness run")


def _lifecycle_path(
    ref: str,
    *,
    root: Path,
    environment: str,
    release_id: str,
) -> tuple[Path, str]:
    relative = Path(str(ref or "").strip())
    expected_prefix = ("env", environment, "runs", "release-lifecycle-exit", release_id)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) != 7
        or tuple(relative.parts[:5]) != expected_prefix
        or relative.parts[-1] != "lifecycle-exit.json"
    ):
        raise ValueError(
            "lifecycleExitRef must bind the explicit environment/release/exitRunId"
        )
    exit_run_id = _safe_segment(relative.parts[5], label="lifecycle exitRunId")
    path = root / relative
    if _canonical_ref(path, root=root, label="lifecycleExitRef") != relative.as_posix():
        raise ValueError("lifecycleExitRef is not canonical")
    return path, exit_run_id


def _load_evidence(
    *,
    environment: str,
    target: str,
    startup_attempt_id: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    lifecycle_exit_ref: str,
) -> _Evidence:
    if environment not in {"alpha", "beta", "gamma"} or target != f"{environment}-local":
        raise ValueError("test-live content binding target identity mismatch")
    attempt_id = _safe_segment(startup_attempt_id, label="startupAttemptId")
    release = _safe_segment(release_id, label="releaseId")
    verify = _safe_segment(verify_run_id, label="verifyRunId")
    digest = _canonical_digest(manifest_digest, label="manifestDigest")
    root = output_root().expanduser().absolute()

    startup_snapshot = _read_regular_json(
        test_live_startup_attempt_path(target),
        label="test-live startup receipt",
    )
    assert startup_snapshot is not None
    startup = validate_test_live_startup_attempt(
        startup_snapshot.value,
        expected_environment=environment,
        expected_target=target,
    )
    if (
        startup.get("attemptId") != attempt_id
        or startup.get("status") != "running"
        or startup.get("failure") is not None
    ):
        raise ValueError("test-live content binding requires the exact running startup attempt")

    attestation_path = root / "data" / "releases" / release / "attestations" / "release.json"
    readiness_path = (
        env_runs_root(environment)
        / "data-release"
        / release
        / verify
        / "release-readiness.json"
    )
    attestation_ref = _canonical_ref(
        attestation_path,
        root=root,
        label="release attestation",
    )
    readiness_ref = _canonical_ref(readiness_path, root=root, label="release readiness")
    attestation_snapshot = _read_regular_json(
        attestation_path,
        label="Data release attestation",
    )
    readiness_snapshot = _read_regular_json(
        readiness_path,
        label="Data readiness receipt",
    )
    assert attestation_snapshot is not None and readiness_snapshot is not None
    release_class, lifecycle_state, source_identity = _validate_attestation(
        attestation_snapshot.value,
        release_id=release,
        manifest_digest=digest,
    )
    phase = _validate_readiness(
        readiness_snapshot.value,
        environment=environment,
        release_id=release,
        verify_run_id=verify,
        manifest_digest=digest,
        release_class=release_class,
        lifecycle_state=lifecycle_state,
        source_identity=source_identity,
    )

    lifecycle_ref = str(lifecycle_exit_ref or "").strip()
    lifecycle_snapshot: _RegularJson | None = None
    lifecycle: dict[str, Any] | None = None
    if phase == "commercial" and not lifecycle_ref:
        raise ValueError("commercial readiness requires explicit lifecycleExitRef")
    if lifecycle_ref:
        lifecycle_path, exit_run_id = _lifecycle_path(
            lifecycle_ref,
            root=root,
            environment=environment,
            release_id=release,
        )
        lifecycle_snapshot = _read_regular_json(
            lifecycle_path,
            label="Data lifecycle Exit receipt",
        )
        assert lifecycle_snapshot is not None
        lifecycle = lifecycle_snapshot.value
        _validate_lifecycle(
            lifecycle,
            environment=environment,
            release_id=release,
            manifest_digest=digest,
            exit_run_id=exit_run_id,
            readiness=readiness_snapshot.value,
        )
    return _Evidence(
        startup=startup,
        startup_snapshot=startup_snapshot,
        attestation=attestation_snapshot.value,
        attestation_snapshot=attestation_snapshot,
        readiness=readiness_snapshot.value,
        readiness_snapshot=readiness_snapshot,
        readiness_phase=phase,
        source_identity=_copy_source_identity(source_identity),
        attestation_ref=attestation_ref,
        readiness_ref=readiness_ref,
        lifecycle=lifecycle,
        lifecycle_snapshot=lifecycle_snapshot,
        lifecycle_ref=lifecycle_ref,
    )


def _startup_identity(startup: Mapping[str, Any]) -> dict[str, str]:
    return {field: str(startup.get(field) or "") for field in _STARTUP_IDENTITY_FIELDS}


def _evidence_token(evidence: _Evidence) -> tuple[object, ...]:
    return (
        evidence.startup,
        evidence.startup_snapshot.identity,
        evidence.startup_snapshot.digest,
        evidence.attestation,
        evidence.attestation_snapshot.identity,
        evidence.attestation_snapshot.digest,
        evidence.readiness,
        evidence.readiness_snapshot.identity,
        evidence.readiness_snapshot.digest,
        evidence.lifecycle,
        evidence.lifecycle_snapshot.identity if evidence.lifecycle_snapshot else None,
        evidence.lifecycle_snapshot.digest if evidence.lifecycle_snapshot else "",
    )


def _binding_payload(
    *,
    evidence: _Evidence,
    environment: str,
    target: str,
) -> dict[str, Any]:
    app_uat_plan = build_app_content_uat_plan(evidence.readiness)
    return {
        "schema": SCHEMA,
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "bound",
        "retentionClass": "run_bound",
        "environment": environment,
        "target": target,
        "startupAttemptId": evidence.startup["attemptId"],
        "startupIdentity": _startup_identity(evidence.startup),
        "releaseId": evidence.readiness["releaseId"],
        "verifyRunId": evidence.readiness["verifyRunId"],
        "manifestDigest": evidence.readiness["manifestDigest"],
        "readinessPhase": evidence.readiness_phase,
        "releaseAttestationRef": evidence.attestation_ref,
        "releaseAttestationDigest": evidence.attestation_snapshot.digest,
        "readinessReceiptRef": evidence.readiness_ref,
        "readinessReceiptDigest": evidence.readiness_snapshot.digest,
        "dataSourceIdentity": _copy_source_identity(evidence.source_identity),
        "appUatEnvelope": dict(evidence.readiness["appUatEnvelope"]),
        "appUatEnvelopeDigest": evidence.readiness["appUatEnvelopeDigest"],
        "appUatPlan": app_uat_plan,
        "appUatPlanDigest": _document_checksum(app_uat_plan),
        "activationEnvelope": dict(evidence.readiness["activationEnvelope"]),
        "activationEnvelopeDigest": evidence.readiness[
            "activationEnvelopeDigest"
        ],
        "lifecycleExitRef": evidence.lifecycle_ref,
        "lifecycleExitDigest": (
            evidence.lifecycle_snapshot.digest if evidence.lifecycle_snapshot else ""
        ),
        "boundAt": _utc_now(),
    }


def _validate_timestamp(value: object) -> None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("test-live content binding boundAt is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("test-live content binding boundAt is invalid")


def _validate_binding(value: object, *, evidence: _Evidence, target: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _BINDING_FIELDS:
        raise ValueError("test-live content binding fields mismatch")
    app_uat_plan = build_app_content_uat_plan(evidence.readiness)
    expected = {
        "schema": SCHEMA,
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "bound",
        "retentionClass": "run_bound",
        "environment": evidence.startup["environment"],
        "target": target,
        "startupAttemptId": evidence.startup["attemptId"],
        "startupIdentity": _startup_identity(evidence.startup),
        "releaseId": evidence.readiness["releaseId"],
        "verifyRunId": evidence.readiness["verifyRunId"],
        "manifestDigest": evidence.readiness["manifestDigest"],
        "readinessPhase": evidence.readiness_phase,
        "releaseAttestationRef": evidence.attestation_ref,
        "releaseAttestationDigest": evidence.attestation_snapshot.digest,
        "readinessReceiptRef": evidence.readiness_ref,
        "readinessReceiptDigest": evidence.readiness_snapshot.digest,
        "dataSourceIdentity": _copy_source_identity(evidence.source_identity),
        "appUatEnvelope": dict(evidence.readiness["appUatEnvelope"]),
        "appUatEnvelopeDigest": evidence.readiness["appUatEnvelopeDigest"],
        "appUatPlan": app_uat_plan,
        "appUatPlanDigest": _document_checksum(app_uat_plan),
        "activationEnvelope": dict(evidence.readiness["activationEnvelope"]),
        "activationEnvelopeDigest": evidence.readiness[
            "activationEnvelopeDigest"
        ],
        "lifecycleExitRef": evidence.lifecycle_ref,
        "lifecycleExitDigest": (
            evidence.lifecycle_snapshot.digest if evidence.lifecycle_snapshot else ""
        ),
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise ValueError(f"test-live content binding {field} drift")
    _validate_timestamp(value.get("boundAt"))
    return dict(value)


def _create_once(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    parent_descriptor, parent_identities = _open_directory_chain(
        path.parent,
        label="test-live content binding",
    )
    temporary = f".{path.name}.{uuid4().hex}.tmp"
    descriptor = -1
    temporary_exists = False
    try:
        descriptor = os.open(
            temporary,
            _file_flags(create=True),
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_exists = True
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _revalidate_directory_chain(
            path.parent,
            label="test-live content binding",
            identities=parent_identities,
        )
        try:
            os.link(
                temporary,
                path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            raise
        else:
            os.fsync(parent_descriptor)
        finally:
            os.unlink(temporary, dir_fd=parent_descriptor)
            temporary_exists = False
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_exists:
            try:
                os.unlink(temporary, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def load_test_live_content_binding(target: str) -> dict[str, Any] | None:
    """Load a binding and prove it still names the current running attempt/evidence."""

    startup_snapshot = _read_regular_json(
        test_live_startup_attempt_path(target),
        label="test-live startup receipt",
        optional=True,
    )
    if startup_snapshot is None:
        return None
    startup = validate_test_live_startup_attempt(
        startup_snapshot.value,
        expected_target=target,
    )
    path = test_live_content_binding_path(target, str(startup["attemptId"]))
    first = _read_regular_json(path, label="test-live content binding", optional=True)
    if first is None:
        return None
    raw = first.value
    environment = str(raw.get("environment") or "")
    evidence = _load_evidence(
        environment=environment,
        target=target,
        startup_attempt_id=str(raw.get("startupAttemptId") or ""),
        release_id=str(raw.get("releaseId") or ""),
        verify_run_id=str(raw.get("verifyRunId") or ""),
        manifest_digest=str(raw.get("manifestDigest") or ""),
        lifecycle_exit_ref=str(raw.get("lifecycleExitRef") or ""),
    )
    validated = _validate_binding(raw, evidence=evidence, target=target)
    second = _read_regular_json(path, label="test-live content binding")
    assert second is not None
    if first != second:
        raise UnsafeTestLiveContentBindingPath(
            "test-live content binding changed during validation"
        )
    return validated


def create_test_live_content_binding(
    *,
    environment: str,
    target: str,
    startup_attempt_id: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    expected_readiness_receipt_digest: str = "",
    lifecycle_exit_ref: str = "",
) -> dict[str, Any]:
    """Create exactly one binding for the current mutable startup attempt."""

    first = _load_evidence(
        environment=environment,
        target=target,
        startup_attempt_id=startup_attempt_id,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
        lifecycle_exit_ref=lifecycle_exit_ref,
    )
    expected_readiness_digest = str(expected_readiness_receipt_digest or "").strip()
    if expected_readiness_digest:
        _canonical_digest(
            expected_readiness_digest,
            label="readiness receipt digest",
        )
        if first.readiness_snapshot.digest != expected_readiness_digest:
            raise ValueError("test-live content binding readiness receipt digest mismatch")
    existing = load_test_live_content_binding(target)
    if existing is not None:
        requested = (
            first.startup["attemptId"],
            first.readiness["releaseId"],
            first.readiness["verifyRunId"],
            first.readiness["manifestDigest"],
            str(lifecycle_exit_ref or "").strip(),
        )
        observed = (
            existing["startupAttemptId"],
            existing["releaseId"],
            existing["verifyRunId"],
            existing["manifestDigest"],
            existing["lifecycleExitRef"],
        )
        if requested != observed:
            raise ValueError("test-live content binding is create-once and cannot be rebound")
        return existing

    second = _load_evidence(
        environment=environment,
        target=target,
        startup_attempt_id=startup_attempt_id,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
        lifecycle_exit_ref=lifecycle_exit_ref,
    )
    if (
        expected_readiness_digest
        and second.readiness_snapshot.digest != expected_readiness_digest
    ):
        raise ValueError("test-live content binding readiness receipt digest mismatch")
    if _evidence_token(first) != _evidence_token(second):
        raise UnsafeTestLiveContentBindingPath(
            "test-live content evidence changed before binding"
        )
    payload = _binding_payload(
        evidence=second,
        environment=environment,
        target=target,
    )
    path = test_live_content_binding_path(
        target,
        str(second.startup["attemptId"]),
    )
    try:
        _create_once(path, payload)
    except FileExistsError:
        existing = load_test_live_content_binding(target)
        if existing is None:
            raise UnsafeTestLiveContentBindingPath(
                "test-live content binding raced with an invalid writer"
            )
        requested = (
            second.startup["attemptId"],
            second.readiness["releaseId"],
            second.readiness["verifyRunId"],
            second.readiness["manifestDigest"],
            str(lifecycle_exit_ref or "").strip(),
        )
        observed = (
            existing["startupAttemptId"],
            existing["releaseId"],
            existing["verifyRunId"],
            existing["manifestDigest"],
            existing["lifecycleExitRef"],
        )
        if requested != observed:
            raise ValueError("test-live content binding is create-once and cannot be rebound")
        return existing
    loaded = load_test_live_content_binding(target)
    if loaded is None:
        raise UnsafeTestLiveContentBindingPath("test-live content binding was not committed")
    return loaded
