"""test-live content binding 的 Data 证据装载与校验（attestation/readiness/lifecycle）。

原单文件 ``test_live_content_binding.py`` 拆分出的证据子模块；``output_root`` /
``env_runs_root`` / ``test_live_startup_attempt_path`` 为被测试 monkeypatch 的
包属性，消费点一律经 ``_pkg.`` 访问。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import quwoquan_ops.cli.lib.test_live_content_binding as _pkg
from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (
    validate_test_live_startup_attempt,
)

from .constants import _DIGEST, _LIFECYCLE_FIELDS, _SEGMENT
from .safe_io import _RegularJson, _read_regular_json


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
        expected_fields = {*scalar_fields, "executionIds"}
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
            for field in scalar_fields
        }
        identity["executionIds"] = list(execution_ids)
        identities.append(identity)
    identity_keys = [
        (
            item["sourceRevision"],
            item["sourceDigest"],
            item["entityCatalogDigest"],
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
    root = _pkg.output_root().expanduser().absolute()

    startup_snapshot = _read_regular_json(
        _pkg.test_live_startup_attempt_path(target),
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
        _pkg.env_runs_root(environment)
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
