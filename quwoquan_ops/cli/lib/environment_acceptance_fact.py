from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    _ACTIVE_CAS_KEYS,
    _CARRIERS,
    _DEVICE_PROFILES,
    _DIGEST_RE,
    _ENTRIES,
    _EXACT_REF_KEYS,
    _FACT_KEYS_BY_PROFILE,
    _FINALIZATION_KEYS,
    _IDENTITY_RE,
    _PLATFORMS,
    _PREDECESSOR_KEYS,
    _PROD_FACT_KEYS,
    _RAW_RESULT_KEYS,
    _TARGET_BINDING_KEYS,
    ACCEPTANCE_PROFILES,
    ENVIRONMENTS,
    PREDECESSOR,
    PROD_ROLLOUT_STAGES,
    SCHEMA,
    SCHEMA_PATH,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact_evidence import (
    _M1_HEALTH_SCHEMA,
    _M1_OBSERVATION_SCHEMA,
    _M1_REQUIRED_HEALTH_LAYERS,
    _validate_finalization as _validate_finalization_impl,
    _validate_prod_facts as _validate_prod_facts_impl,
    _verify_common_evidence as _verify_common_evidence_impl,
    _verify_m1_consumer_health as _verify_m1_consumer_health_impl,
    _verify_m1_observation as _verify_m1_observation_impl,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact_identity import derive_fact_id as _derive_fact_id_impl
from quwoquan_ops.cli.lib.environment_acceptance_fact_predecessor import (
    validate_predecessor_acceptance as _validate_predecessor_acceptance_impl,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact_validator import (
    validate_environment_acceptance_fact as _validate_environment_acceptance_fact_impl,
)
from quwoquan_ops.cli.lib.readiness_case_result import (
    ReadinessCaseResultError,
    validate_readiness_case_result,
)
from quwoquan_ops.cli.lib.target_uat_binding import (
    TargetUatBindingError,
    validate_target_uat_binding,
)


class EnvironmentAcceptanceFactError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


_INVALID = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.invalid"
_EVIDENCE = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.evidence_blocked"
_PREDECESSOR_BLOCKED = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.predecessor_blocked"
_CREATE_CONFLICT = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.create_once_conflict"
_PATH_BLOCKED = "OPS.ENVIRONMENT_ACCEPTANCE_FACT.path_blocked"
def _block(code: str, detail: str) -> None:
    raise EnvironmentAcceptanceFactError(code, detail)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _block(_INVALID, f"{field} must be a non-empty canonical string")
    return value


def _identity(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if _IDENTITY_RE.fullmatch(text) is None:
        _block(_INVALID, f"{field} has invalid identity format")
    return text


def _digest(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if _DIGEST_RE.fullmatch(text) is None:
        _block(_INVALID, f"{field} must be sha256:<64 lowercase hex>")
    return text


def _timestamp(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EnvironmentAcceptanceFactError(
            _INVALID, f"{field} must be RFC3339"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _block(_INVALID, f"{field} must include a timezone")
    return text


def _relative_ref(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or path.as_posix() != text
        or not path.parts
        or "\\" in text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _block(_PATH_BLOCKED, f"{field} must be a contained relative reference")
    return text


def canonical_fact_bytes(fact: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(fact),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EnvironmentAcceptanceFactError(
            _INVALID, "fact is not canonical JSON"
        ) from exc


def exact_byte_digest(value: bytes | Path) -> str:
    raw = value if isinstance(value, bytes) else Path(value).read_bytes()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _decode_json(raw: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _block(_EVIDENCE, f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        text = raw.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: _block(
                _EVIDENCE, f"{label} contains invalid JSON constant {value}"
            ),
        )
        value, end = decoder.raw_decode(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnvironmentAcceptanceFactError(
            _EVIDENCE, f"{label} is not UTF-8 JSON"
        ) from exc
    if text[end:].strip():
        _block(_EVIDENCE, f"{label} contains trailing JSON content")
    if not isinstance(value, dict):
        _block(_EVIDENCE, f"{label} must contain one JSON object")
    return value


def _absolute_real_root(root: Path, *, label: str) -> Path:
    expanded = Path(root).expanduser()
    absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    absolute = Path(os.path.abspath(absolute))
    try:
        metadata = absolute.lstat()
        resolved = absolute.resolve(strict=True)
    except OSError as exc:
        raise EnvironmentAcceptanceFactError(
            _PATH_BLOCKED, f"{label} is unavailable"
        ) from exc
    if (
        absolute.is_symlink()
        or resolved != absolute
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        _block(_PATH_BLOCKED, f"{label} must be a real non-symlink directory")
    return absolute


def _directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        _block(_PATH_BLOCKED, "platform lacks required no-follow directory support")
    return os.O_RDONLY | nofollow | directory | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        _block(_PATH_BLOCKED, "platform lacks required no-follow file support")
    return os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)


def _secure_read(root: Path, ref: str, *, label: str) -> bytes:
    real_root = _absolute_real_root(root, label="evidence root")
    relative = PurePosixPath(_relative_ref(ref, field=f"{label}.ref"))
    directory = os.open(real_root, _directory_flags())
    descriptor = -1
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, _directory_flags(), dir_fd=directory)
            except OSError as exc:
                raise EnvironmentAcceptanceFactError(
                    _PATH_BLOCKED, f"{label} parent is missing, linked, or unsafe"
                ) from exc
            os.close(directory)
            directory = child
        try:
            before = os.stat(relative.name, dir_fd=directory, follow_symlinks=False)
            descriptor = os.open(relative.name, _file_flags(), dir_fd=directory)
        except OSError as exc:
            raise EnvironmentAcceptanceFactError(
                _PATH_BLOCKED, f"{label} is missing, linked, or unreadable"
            ) from exc
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            _block(_PATH_BLOCKED, f"{label} must be a stable regular non-symlink file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ) or sum(map(len, chunks)) != opened.st_size:
            _block(_PATH_BLOCKED, f"{label} changed while being read")
        return b"".join(chunks)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def _load_exact(
    root: Path, value: Mapping[str, Any], *, label: str
) -> tuple[dict[str, Any], bytes]:
    if not isinstance(value, Mapping) or set(value) != _EXACT_REF_KEYS:
        _block(_INVALID, f"{label} must contain only ref and digest")
    ref = _relative_ref(value.get("ref"), field=f"{label}.ref")
    expected = _digest(value.get("digest"), field=f"{label}.digest")
    raw = _secure_read(root, ref, label=label)
    actual = exact_byte_digest(raw)
    if actual != expected:
        _block(
            _EVIDENCE,
            f"{label} exact-byte digest drifted: expected {expected}, got {actual}",
        )
    return _decode_json(raw, label=label), raw


def _status(payload: Mapping[str, Any]) -> str:
    for field in ("status", "state", "phase", "lifecycleState"):
        value = payload.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


def _require_status(
    payload: Mapping[str, Any], *, label: str, allowed: set[str]
) -> None:
    observed = _status(payload)
    if observed.lower() not in {value.lower() for value in allowed}:
        _block(_EVIDENCE, f"{label} is not ready: got {observed!r}")


def _require_evidence_identity(
    payload: Mapping[str, Any],
    *,
    label: str,
    environment: str,
    target: str,
    release_id: str,
    release_digest: str,
    import_run_id: str,
    verify_run_id: str,
) -> None:
    expected = {
        "environment": environment,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            _block(_EVIDENCE, f"{label} identity drifted at {field}")
    observed_target = payload.get("deploymentTarget")
    if observed_target is None and isinstance(payload.get("target"), str):
        observed_target = payload.get("target")
    if observed_target != target:
        _block(_EVIDENCE, f"{label} identity drifted at target")


def _normalize_exact_ref(value: object, *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _EXACT_REF_KEYS:
        _block(_INVALID, f"{label} must contain only ref and digest")
    return {
        "ref": _relative_ref(value.get("ref"), field=f"{label}.ref"),
        "digest": _digest(value.get("digest"), field=f"{label}.digest"),
    }


def _normalize_profiles(
    value: Sequence[Mapping[str, str]], *, label: str
) -> set[tuple[str, str]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        _block(_INVALID, f"{label} must be a non-empty sequence")
    result: set[tuple[str, str]] = set()
    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        if not isinstance(item, Mapping) or set(item) != {"platform", "deviceProfile"}:
            _block(_INVALID, f"{item_label} fields are invalid")
        platform = _text(item.get("platform"), field=f"{item_label}.platform")
        profile = _text(item.get("deviceProfile"), field=f"{item_label}.deviceProfile")
        if platform not in _PLATFORMS or profile not in _DEVICE_PROFILES:
            _block(_INVALID, f"{item_label} uses an unknown platform/device profile")
        if (platform, profile) in result:
            _block(_INVALID, f"{label} contains a duplicate platform/device profile")
        result.add((platform, profile))
    return result


def _binding_device_profile(binding: Mapping[str, Any]) -> str:
    profile = _text(binding.get("profile"), field="TargetUatBinding.profile")
    if profile not in _DEVICE_PROFILES:
        _block(_EVIDENCE, "TargetUatBinding.profile is unknown")
    return profile


def required_raw_slot_id(
    *,
    target_uat_binding_digest: str | None = None,
    sample_id: str,
    entry_surface: str,
    carrier: str,
    spec_ref: str,
    runner_identity: str,
) -> str:
    material = {
        "sampleId": _identity(sample_id, field="sampleId"),
        "entrySurface": entry_surface,
        "carrier": carrier,
        "specRef": spec_ref,
        "runnerIdentity": runner_identity,
    }
    if target_uat_binding_digest is not None:
        material["targetUatBindingDigest"] = _digest(
            target_uat_binding_digest, field="targetUatBindingDigest"
        )
    return "sha256:" + hashlib.sha256(canonical_fact_bytes(material)).hexdigest()


def derive_m1_source_fingerprint(
    *,
    environment: str,
    target: str,
    release_id: str,
    release_digest: str,
    manifest_digest: str,
    import_run_id: str,
    verify_run_id: str,
    sample_plan: Mapping[str, Any],
    data_readiness: Mapping[str, Any],
    consumer_health: Mapping[str, Any],
    required_raw_results: Sequence[Mapping[str, Any]],
) -> str:
    """Derive the M1 authority-set fingerprint from exact input identities."""

    exact_plan = _normalize_exact_ref(sample_plan, label="sourceFingerprint.samplePlan")
    exact_data = _normalize_exact_ref(
        data_readiness, label="sourceFingerprint.dataReadiness"
    )
    exact_health = _normalize_exact_ref(
        consumer_health, label="sourceFingerprint.consumerHealth"
    )
    normalized_raw: list[dict[str, str]] = []
    for index, item in enumerate(required_raw_results):
        label = f"sourceFingerprint.requiredRawResults[{index}]"
        if not isinstance(item, Mapping) or set(item) != _RAW_RESULT_KEYS:
            _block(_INVALID, f"{label} fields are invalid")
        exact = _normalize_exact_ref(
            {"ref": item.get("ref"), "digest": item.get("digest")}, label=label
        )
        normalized_raw.append(
            {
                **exact,
                "slotId": _digest(item.get("slotId"), field=f"{label}.slotId"),
                "status": _text(item.get("status"), field=f"{label}.status"),
            }
        )
    material = {
        "schema": "qwq.m1_api_consumer.source_fingerprint.v1",
        "environment": _text(environment, field="sourceFingerprint.environment"),
        "target": _identity(target, field="sourceFingerprint.target"),
        "releaseId": _identity(release_id, field="sourceFingerprint.releaseId"),
        "releaseDigest": _digest(
            release_digest, field="sourceFingerprint.releaseDigest"
        ),
        "manifestDigest": _digest(
            manifest_digest, field="sourceFingerprint.manifestDigest"
        ),
        "importRunId": _identity(import_run_id, field="sourceFingerprint.importRunId"),
        "verifyRunId": _identity(verify_run_id, field="sourceFingerprint.verifyRunId"),
        "samplePlan": exact_plan,
        "dataReadiness": exact_data,
        "consumerHealth": exact_health,
        "requiredRawResults": sorted(
            normalized_raw,
            key=lambda item: (
                item["slotId"],
                item["digest"],
                item["ref"],
                item["status"],
            ),
        ),
    }
    return "sha256:" + hashlib.sha256(canonical_fact_bytes(material)).hexdigest()


def _required_plan_cells(
    plan: Mapping[str, Any],
) -> dict[tuple[str, str, str, str], dict[str, str]]:
    matrix = plan.get("entryCarrierCells")
    if not isinstance(matrix, list) or len(matrix) != len(_ENTRIES) * len(_CARRIERS):
        _block(
            _EVIDENCE, "release UAT sample plan must have exactly 16 entryCarrierCells"
        )
    result: dict[tuple[str, str, str, str], dict[str, str]] = {}
    observed_axes: set[tuple[str, str]] = set()
    for index, cell in enumerate(matrix):
        if not isinstance(cell, Mapping):
            _block(_EVIDENCE, f"entryCarrierCells[{index}] is invalid")
        entry = _text(cell.get("entry"), field=f"entryCarrierCells[{index}].entry")
        carrier = _text(
            cell.get("carrier"), field=f"entryCarrierCells[{index}].carrier"
        )
        axes = (entry, carrier)
        if entry not in _ENTRIES or carrier not in _CARRIERS or axes in observed_axes:
            _block(_EVIDENCE, "release UAT sample plan axes are unknown or duplicated")
        observed_axes.add(axes)
        applicability = cell.get("applicability")
        if applicability == "not_applicable":
            if set(cell) != {"entry", "carrier", "applicability", "reasonCode"}:
                _block(
                    _EVIDENCE,
                    f"entryCarrierCells[{index}] not_applicable fields drifted",
                )
            _text(
                cell.get("reasonCode"), field=f"entryCarrierCells[{index}].reasonCode"
            )
            continue
        if applicability != "required" or set(cell) != {
            "entry",
            "carrier",
            "applicability",
            "specRef",
            "runnerClass",
        }:
            _block(_EVIDENCE, f"entryCarrierCells[{index}] required fields drifted")
        spec_ref = _text(
            cell.get("specRef"), field=f"entryCarrierCells[{index}].specRef"
        )
        runner = _text(
            cell.get("runnerClass"), field=f"entryCarrierCells[{index}].runnerClass"
        )
        key = (entry, carrier, spec_ref, runner)
        if key in result:
            _block(_EVIDENCE, "sample plan contains a duplicate required cell")
        result[key] = {
            "entrySurface": entry,
            "carrier": carrier,
            "specRef": spec_ref,
            "runnerIdentity": runner,
        }
    if observed_axes != {
        (entry, carrier) for entry in _ENTRIES for carrier in _CARRIERS
    }:
        _block(_EVIDENCE, "release UAT sample plan does not cover the canonical matrix")
    if not result:
        _block(_EVIDENCE, "release UAT sample plan has no required cells")
    return result


def derive_fact_id(fact: Mapping[str, Any]) -> str:
    return _derive_fact_id_impl(fact, canonical_fact_bytes=canonical_fact_bytes)


def _verify_common_evidence(
    root: Path,
    value: object,
    *,
    label: str,
    allowed_statuses: set[str],
    identity: dict[str, str],
) -> dict[str, Any]:
    return _verify_common_evidence_impl(
        root,
        value,
        label=label,
        allowed_statuses=allowed_statuses,
        identity=identity,
        normalize_exact_ref=_normalize_exact_ref,
        load_exact=_load_exact,
        require_evidence_identity=_require_evidence_identity,
        require_status=_require_status,
    )


def _verify_m1_consumer_health(
    root: Path,
    value: object,
    *,
    identity: dict[str, str],
    manifest_digest: str,
    data_readiness: Mapping[str, str],
) -> dict[str, Any]:
    return _verify_m1_consumer_health_impl(
        root,
        value,
        identity=identity,
        manifest_digest=manifest_digest,
        data_readiness=data_readiness,
        normalize_exact_ref=_normalize_exact_ref,
        load_exact=_load_exact,
        text=_text,
        digest=_digest,
        block=_block,
        evidence_code=_EVIDENCE,
    )


def _verify_m1_observation(
    root: Path,
    raw_result: Mapping[str, Any],
    *,
    label: str,
    sample_id: str,
    manifest_digest: str,
) -> dict[str, Any]:
    return _verify_m1_observation_impl(
        root,
        raw_result,
        label=label,
        sample_id=sample_id,
        manifest_digest=manifest_digest,
        relative_ref=_relative_ref,
        text=_text,
        secure_read=_secure_read,
        decode_json=_decode_json,
        identity=_identity,
        digest=_digest,
        block=_block,
        evidence_code=_EVIDENCE,
    )


def _validate_finalization(
    root: Path,
    value: object,
    *,
    identity: dict[str, str],
    verify_references: bool,
) -> dict[str, list[dict[str, str]]]:
    return _validate_finalization_impl(
        root,
        value,
        identity=identity,
        verify_references=verify_references,
        normalize_exact_ref=_normalize_exact_ref,
        verify_common_evidence=_verify_common_evidence,
        block=_block,
        invalid_code=_INVALID,
    )


def _validate_prod_facts(
    root: Path,
    value: object,
    *,
    environment: str,
    identity: dict[str, str],
    verify_references: bool,
) -> dict[str, Any] | None:
    return _validate_prod_facts_impl(
        root,
        value,
        environment=environment,
        identity=identity,
        verify_references=verify_references,
        normalize_exact_ref=_normalize_exact_ref,
        verify_common_evidence=_verify_common_evidence,
        block=_block,
        invalid_code=_INVALID,
        evidence_code=_EVIDENCE,
    )


def validate_predecessor_acceptance(
    *,
    environment: str,
    predecessor_acceptance: Mapping[str, Any] | None,
    evidence_root: Path,
    release_id: str,
    release_digest: str,
) -> dict[str, str] | None:
    return _validate_predecessor_acceptance_impl(
        environment=environment,
        predecessor_acceptance=predecessor_acceptance,
        evidence_root=evidence_root,
        release_id=release_id,
        release_digest=release_digest,
        digest=_digest,
        relative_ref=_relative_ref,
        secure_read=_secure_read,
        exact_byte_digest=exact_byte_digest,
        decode_json=_decode_json,
        validate_fact=lambda payload, **kwargs: validate_environment_acceptance_fact(
            payload, **kwargs
        ),
        block=_block,
        error_type=EnvironmentAcceptanceFactError,
        invalid_code=_INVALID,
        predecessor_blocked_code=_PREDECESSOR_BLOCKED,
    )


def validate_environment_acceptance_fact(
    payload: Mapping[str, Any],
    *,
    evidence_root: Path,
    required_target_profiles: Sequence[Mapping[str, str]],
    verify_references: bool = True,
) -> dict[str, Any]:
    return _validate_environment_acceptance_fact_impl(
        payload,
        evidence_root=evidence_root,
        required_target_profiles=required_target_profiles,
        verify_references=verify_references,
        invalid_code=_INVALID,
        evidence_code=_EVIDENCE,
        error_type=EnvironmentAcceptanceFactError,
        block=_block,
        text=_text,
        identity_value=_identity,
        digest=_digest,
        timestamp=_timestamp,
        relative_ref=_relative_ref,
        normalize_profiles=_normalize_profiles,
        absolute_real_root=_absolute_real_root,
        secure_read=_secure_read,
        exact_byte_digest=exact_byte_digest,
        decode_json=_decode_json,
        required_plan_cells=_required_plan_cells,
        normalize_exact_ref=_normalize_exact_ref,
        load_exact=_load_exact,
        binding_device_profile=_binding_device_profile,
        require_evidence_identity=_require_evidence_identity,
        verify_m1_observation=_verify_m1_observation,
        required_raw_slot_id=required_raw_slot_id,
        verify_m1_consumer_health=_verify_m1_consumer_health,
        derive_m1_source_fingerprint=derive_m1_source_fingerprint,
        derive_fact_id=derive_fact_id,
        verify_common_evidence=_verify_common_evidence,
        validate_finalization=_validate_finalization,
        validate_prod_facts=_validate_prod_facts,
        validate_predecessor_acceptance=validate_predecessor_acceptance,
    )


def build_environment_acceptance_fact(
    *,
    evidence_root: Path,
    acceptance_profile: str,
    environment: str,
    target: str,
    release_id: str,
    release_digest: str,
    import_run_id: str,
    verify_run_id: str,
    sample_plan_ref: str,
    sample_plan_digest: str,
    target_binding_refs: Sequence[Mapping[str, Any]],
    required_raw_results: Sequence[Mapping[str, Any]],
    required_target_profiles: Sequence[Mapping[str, str]],
    data_readiness: Mapping[str, str],
    manifest_digest: str | None = None,
    consumer_health: Mapping[str, str] | None = None,
    active_cas: Mapping[str, str] | None = None,
    lifecycle_exit: Mapping[str, str] | None = None,
    provider_readiness: Mapping[str, str] | None = None,
    observability_readiness: Mapping[str, str] | None = None,
    rollback_readiness: Mapping[str, str] | None = None,
    predecessor_acceptance: Mapping[str, str] | None = None,
    resource_finalization: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
    prod_release_facts: Mapping[str, Any] | None = None,
    created_at: str,
    source_fingerprint: str,
) -> dict[str, Any]:
    fact: dict[str, Any] = {
        "schema": SCHEMA,
        "factId": "sha256:" + "0" * 64,
        "acceptanceProfile": acceptance_profile,
        "environment": environment,
        "target": target,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "samplePlanRef": sample_plan_ref,
        "samplePlanDigest": sample_plan_digest,
        "requiredRawResults": [dict(item) for item in required_raw_results],
        "dataReadiness": dict(data_readiness),
        "createdAt": created_at,
        "sourceFingerprint": source_fingerprint,
    }
    if acceptance_profile == "m1_api_consumer":
        if consumer_health is None:
            _block(_INVALID, "m1_api_consumer requires consumerHealth")
        fact["manifestDigest"] = _digest(manifest_digest, field="manifestDigest")
        fact["consumerHealth"] = dict(consumer_health)
        derived_source_fingerprint = derive_m1_source_fingerprint(
            environment=environment,
            target=target,
            release_id=release_id,
            release_digest=release_digest,
            manifest_digest=str(fact["manifestDigest"]),
            import_run_id=import_run_id,
            verify_run_id=verify_run_id,
            sample_plan={"ref": sample_plan_ref, "digest": sample_plan_digest},
            data_readiness=data_readiness,
            consumer_health=consumer_health,
            required_raw_results=required_raw_results,
        )
        fact["sourceFingerprint"] = derived_source_fingerprint
    else:
        fact["sourceFingerprint"] = _digest(
            source_fingerprint, field="sourceFingerprint"
        )
        if any(
            value is None
            for value in (
                active_cas,
                lifecycle_exit,
                provider_readiness,
                observability_readiness,
                rollback_readiness,
                resource_finalization,
            )
        ):
            _block(
                _INVALID, "environment_promotion requires promotion authority fields"
            )
        fact.update(
            {
                "targetBindingRefs": [dict(item) for item in target_binding_refs],
                "activeCas": dict(active_cas or {}),
                "lifecycleExit": dict(lifecycle_exit or {}),
                "providerReadiness": dict(provider_readiness or {}),
                "observabilityReadiness": dict(observability_readiness or {}),
                "rollbackReadiness": dict(rollback_readiness or {}),
                "predecessorAcceptance": (
                    dict(predecessor_acceptance)
                    if predecessor_acceptance is not None
                    else None
                ),
                "resourceFinalization": {
                    key: [dict(item) for item in values]
                    for key, values in (resource_finalization or {}).items()
                },
                "prodReleaseFacts": (
                    {
                        key: (
                            [dict(item) for item in value]
                            if key == "rolloutStages"
                            else dict(value)
                        )
                        for key, value in prod_release_facts.items()
                    }
                    if prod_release_facts is not None
                    else None
                ),
            }
        )
    fact["factId"] = derive_fact_id(fact)
    return validate_environment_acceptance_fact(
        fact,
        evidence_root=evidence_root,
        required_target_profiles=required_target_profiles,
        verify_references=True,
    )


def environment_acceptance_fact_relative_path(fact: Mapping[str, Any]) -> str:
    environment = _text(fact.get("environment"), field="environment")
    if environment not in ENVIRONMENTS:
        _block(_INVALID, "environment is unknown")
    fact_id = _digest(fact.get("factId"), field="factId")
    return f"{environment}/{fact_id}.json"


def _read_existing_at(directory_fd: int, name: str) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(name, _file_flags(), dir_fd=directory_fd)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            _block(_CREATE_CONFLICT, "existing fact slot is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError as exc:
        raise EnvironmentAcceptanceFactError(
            _CREATE_CONFLICT, "existing fact slot is linked or unreadable"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def write_environment_acceptance_fact(
    *,
    root: Path,
    fact: Mapping[str, Any],
    evidence_root: Path,
    required_target_profiles: Sequence[Mapping[str, str]],
) -> Path:
    validated = validate_environment_acceptance_fact(
        fact,
        evidence_root=evidence_root,
        required_target_profiles=required_target_profiles,
        verify_references=True,
    )
    encoded = canonical_fact_bytes(validated)
    store_root = _absolute_real_root(root, label="acceptance fact root")
    environment = str(validated["environment"])
    filename = f"{validated['factId']}.json"
    root_fd = os.open(store_root, _directory_flags())
    environment_fd = -1
    temporary = f".{filename}.tmp-{os.getpid()}-{secrets.token_hex(8)}"
    temporary_created = False
    try:
        try:
            os.mkdir(environment, mode=0o755, dir_fd=root_fd)
        except FileExistsError:
            pass
        try:
            environment_fd = os.open(environment, _directory_flags(), dir_fd=root_fd)
        except OSError as exc:
            raise EnvironmentAcceptanceFactError(
                _PATH_BLOCKED, "environment fact directory is linked or unsafe"
            ) from exc
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o444,
            dir_fd=environment_fd,
        )
        temporary_created = True
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    _block(_CREATE_CONFLICT, "fact write made no progress")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(
                temporary,
                filename,
                src_dir_fd=environment_fd,
                dst_dir_fd=environment_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            if _read_existing_at(environment_fd, filename) != encoded:
                _block(
                    _CREATE_CONFLICT, "factId already exists with different exact bytes"
                )
        os.fsync(environment_fd)
    finally:
        if temporary_created and environment_fd >= 0:
            try:
                os.unlink(temporary, dir_fd=environment_fd)
            except FileNotFoundError:
                pass
        if environment_fd >= 0:
            os.close(environment_fd)
        os.close(root_fd)
    return store_root / environment / filename


def create_environment_acceptance_fact(
    *,
    root: Path,
    evidence_root: Path,
    required_target_profiles: Sequence[Mapping[str, str]],
    **builder_arguments: Any,
) -> Path:
    fact = build_environment_acceptance_fact(
        evidence_root=evidence_root,
        required_target_profiles=required_target_profiles,
        **builder_arguments,
    )
    return write_environment_acceptance_fact(
        root=root,
        fact=fact,
        evidence_root=evidence_root,
        required_target_profiles=required_target_profiles,
    )


def load_environment_acceptance_fact(
    ref: str,
    *,
    evidence_root: Path,
    required_target_profiles: Sequence[Mapping[str, str]] | None = None,
    verify_references: bool = True,
) -> tuple[dict[str, Any], str]:
    raw = _secure_read(evidence_root, ref, label="environmentAcceptanceFact")
    fact = _decode_json(raw, label="environmentAcceptanceFact")
    profiles = required_target_profiles
    if verify_references and profiles is None:
        _block(
            _INVALID,
            "required_target_profiles must be supplied by the caller authority",
        )
    if profiles is None:
        profiles = []
    validated = validate_environment_acceptance_fact(
        fact,
        evidence_root=evidence_root,
        required_target_profiles=profiles,
        verify_references=verify_references,
    )
    return validated, exact_byte_digest(raw)


__all__ = [
    "ACCEPTANCE_PROFILES",
    "ENVIRONMENTS",
    "PREDECESSOR",
    "PROD_ROLLOUT_STAGES",
    "SCHEMA",
    "SCHEMA_PATH",
    "EnvironmentAcceptanceFactError",
    "build_environment_acceptance_fact",
    "canonical_fact_bytes",
    "create_environment_acceptance_fact",
    "derive_fact_id",
    "derive_m1_source_fingerprint",
    "environment_acceptance_fact_relative_path",
    "exact_byte_digest",
    "load_environment_acceptance_fact",
    "required_raw_slot_id",
    "validate_environment_acceptance_fact",
    "validate_predecessor_acceptance",
    "write_environment_acceptance_fact",
]
