"""Single-track v2 local Human calibration records and exact-byte readback."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contract import load_contract

DEFAULT_STORE = Path(".qwq_output/env/repo/runs/human-agent-delivery-calibration/sessions")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class CalibrationError(ValueError):
    """Fail-closed calibration validation or compatibility error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CalibrationWriteResult:
    path: Path
    ref: str
    digest: str
    session: dict[str, Any]
    created: bool


def _fail(code: str, detail: str) -> None:
    raise CalibrationError(code, detail)


def _contract_parts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_contract()
    return contract, contract["closed_sets"], contract["schemas"], contract["calibration_model"]


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _exact_fields(value: object, expected: Sequence[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("HAD.CALIBRATION_INVALID", f"{label} must be an object")
    actual, required = set(value), set(expected)
    if actual != required:
        _fail("HAD.CALIBRATION_INVALID", f"{label} fields drifted missing={sorted(required-actual)} extra={sorted(actual-required)}")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("HAD.CALIBRATION_INVALID", f"{label} must be non-empty text")
    return value


def _timestamp(value: object, *, label: str) -> datetime:
    raw = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        _fail("HAD.CALIBRATION_INVALID", f"{label} must be a valid timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("HAD.CALIBRATION_INVALID", f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _reject_forbidden_keys(value: object, *, forbidden: set[str], path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in forbidden:
                _fail("HAD.CALIBRATION_PII_FORBIDDEN", f"{path}.{key} is forbidden")
            _reject_forbidden_keys(child, forbidden=forbidden, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_keys(child, forbidden=forbidden, path=f"{path}[{index}]")


def _version_check(value: Mapping[str, Any], *, contract: Mapping[str, Any], model: Mapping[str, Any], label: str) -> None:
    expected = {
        "schema_version": contract["schema_version"],
        "contract_version": model["contract_version"],
        "role_model_version": model["role_model_version"],
        "observation_model_version": model["observation_model_version"],
    }
    actual = {name: value.get(name) for name in expected}
    if actual != expected:
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", f"{label} version incompatible expected={expected} actual={actual}")


def validate_calibration_session(value: object) -> dict[str, Any]:
    """Validate one exact v2 role-session; unknown fields and versions fail closed."""
    contract, closed, schemas, model = _contract_parts()
    session_schema = schemas["human_calibration_session"]
    observation_schema = schemas["human_calibration_observation"]
    forbidden = set(session_schema["direct_identity_fields_forbidden"]) | set(session_schema["raw_content_fields_forbidden"])
    _reject_forbidden_keys(value, forbidden=forbidden, path="session")
    session = _exact_fields(value, session_schema["required_fields"], label="human_calibration_session")
    _version_check(session, contract=contract, model=model, label="human_calibration_session")
    session_id = _text(session["session_id"], label="session_id")
    if not re.fullmatch(session_schema["session_id_pattern"], session_id):
        _fail("HAD.CALIBRATION_INVALID", "session_id must be calibration-<deidentified-token>")
    principal = session["principal_class"]
    if principal not in closed["human_calibration_principal_class"]:
        _fail("HAD.CALIBRATION_INVALID", "principal_class is unknown")
    participant_ref = _text(session["participant_ref"], label="participant_ref")
    if not re.fullmatch(session_schema["participant_ref_pattern"], participant_ref):
        _fail("HAD.CALIBRATION_PII_FORBIDDEN", "participant_ref must be a deidentified token")
    scope = _exact_fields(session["scope"], session_schema["scope_required_fields"], label="scope")
    _text(scope["decision_unit_id"], label="scope.decision_unit_id")
    _text(scope["task_id"], label="scope.task_id")
    if not isinstance(scope["evidence_fingerprint"], str) or not _SHA256_RE.fullmatch(scope["evidence_fingerprint"]):
        _fail("HAD.CALIBRATION_INVALID", "scope.evidence_fingerprint must be sha256")
    responsibilities = scope["responsibility_classes"]
    if not isinstance(responsibilities, list) or not responsibilities or len(responsibilities) != len(set(responsibilities)):
        _fail("HAD.CALIBRATION_INVALID", "scope.responsibility_classes must be a unique non-empty list")
    expected_responsibilities = model["principal_responsibility_mapping"][principal]
    if responsibilities != expected_responsibilities:
        _fail("HAD.CALIBRATION_INVALID", "principal responsibility mapping drifted")
    started = _timestamp(session["started_at"], label="started_at")
    completed = _timestamp(session["completed_at"], label="completed_at")
    if completed < started:
        _fail("HAD.CALIBRATION_INVALID", "completed_at precedes started_at")
    assurance = _exact_fields(session["source_assurance"], session_schema["source_assurance_required_fields"], label="source_assurance")
    if assurance["source_kind"] not in closed["human_calibration_source_kind"]:
        _fail("HAD.CALIBRATION_INVALID", "source_assurance.source_kind is unknown")
    provider = assurance["authentication_provider_ref"]
    if provider is not None and (not isinstance(provider, str) or not provider):
        _fail("HAD.CALIBRATION_INVALID", "authentication_provider_ref must be null or non-empty text")
    for field in ("participant_authenticated", "consent_obtained", "direct_identifiers_removed", "free_text_excluded", "observer_attested"):
        if not isinstance(assurance[field], bool):
            _fail("HAD.CALIBRATION_INVALID", f"source_assurance.{field} must be boolean")
    consent_at = _timestamp(assurance["consent_recorded_at"], label="source_assurance.consent_recorded_at")
    if consent_at > started:
        _fail("HAD.CALIBRATION_INVALID", "consent must be recorded no later than session start")
    if session["separation_policy"] not in closed["sod_policy"]:
        _fail("HAD.CALIBRATION_INVALID", "separation_policy is unknown")
    observations = session["observations"]
    if not isinstance(observations, list) or not observations:
        _fail("HAD.CALIBRATION_INVALID", "observations must be a non-empty list")
    seen_ids: set[str] = set()
    seen_dimensions: set[str] = set()
    for index, raw in enumerate(observations):
        observation = _exact_fields(raw, observation_schema["required_fields"], label=f"observations[{index}]")
        observation_id = _text(observation["observation_id"], label=f"observations[{index}].observation_id")
        if not re.fullmatch(observation_schema["observation_id_pattern"], observation_id) or observation_id in seen_ids:
            _fail("HAD.CALIBRATION_INVALID", "observation_id must be unique and canonical")
        seen_ids.add(observation_id)
        dimension = observation["dimension"]
        if dimension not in closed["human_calibration_observation_dimension"] or dimension in seen_dimensions:
            _fail("HAD.CALIBRATION_INVALID", "observation dimension must be unique and closed")
        seen_dimensions.add(dimension)
        observed = _timestamp(observation["observed_at"], label=f"observations[{index}].observed_at")
        if observed < started or observed > completed:
            _fail("HAD.CALIBRATION_INVALID", "observation timestamp falls outside session chronology")
        if observation["outcome"] not in closed["human_calibration_observation_outcome"]:
            _fail("HAD.CALIBRATION_INVALID", "observation outcome is unknown")
        covered = observation["responsibility_classes"]
        if not isinstance(covered, list) or not covered or any(item not in responsibilities for item in covered):
            _fail("HAD.CALIBRATION_INVALID", "observation responsibility coverage exceeds role-session scope")
    return json.loads(json.dumps(session, ensure_ascii=False))


def calibration_session_digest(session: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(validate_calibration_session(dict(session)))).hexdigest()


def _source_assured(session: Mapping[str, Any]) -> bool:
    assurance = session["source_assurance"]
    return bool(
        assurance["source_kind"] == "human_participant"
        and assurance["authentication_provider_ref"]
        and assurance["participant_authenticated"] is True
        and assurance["consent_obtained"] is True
        and assurance["direct_identifiers_removed"] is True
        and assurance["free_text_excluded"] is True
        and assurance["observer_attested"] is True
    )


def _session_demonstrated(session: Mapping[str, Any], dimensions: Sequence[str]) -> bool:
    by_dimension = {item["dimension"]: item for item in session["observations"]}
    observed_responsibilities = {
        responsibility
        for item in session["observations"]
        if item["outcome"] == "demonstrated"
        for responsibility in item["responsibility_classes"]
    }
    return (
        set(by_dimension) == set(dimensions)
        and all(item["outcome"] == "demonstrated" for item in by_dimension.values())
        and observed_responsibilities == set(session["scope"]["responsibility_classes"])
    )


def summarize_calibration_sessions(
    sessions: Sequence[Mapping[str, Any]], *, now: datetime | None = None,
    decision_unit_id: str | None = None, evidence_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Derive v2 status exclusively from validated role-session records."""
    contract, closed, _schemas, model = _contract_parts()
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        _fail("HAD.CALIBRATION_INVALID", "now must be timezone-aware")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    validated = [validate_calibration_session(dict(item)) for item in sessions]
    principals = list(closed["human_calibration_principal_class"])
    responsibilities = list(closed["human_calibration_responsibility_class"])
    dimensions = list(closed["human_calibration_observation_dimension"])
    inferred_unit = decision_unit_id or (validated[0]["scope"]["decision_unit_id"] if validated else "not-observed")
    inferred_fingerprint = evidence_fingerprint or (validated[0]["scope"]["evidence_fingerprint"] if validated else "sha256:" + "0" * 64)
    for session in validated:
        if session["scope"]["decision_unit_id"] != inferred_unit or session["scope"]["evidence_fingerprint"] != inferred_fingerprint:
            _fail("HAD.CALIBRATION_INVALID", "role-session scope/fingerprint mismatch")
    human_sessions = [item for item in validated if item["source_assurance"]["source_kind"] == "human_participant"]
    machine_sessions = [item for item in validated if item["source_assurance"]["source_kind"] != "human_participant"]
    qualifying = [item for item in human_sessions if _source_assured(item) and _session_demonstrated(item, dimensions)]
    completed_principals = sorted({item["principal_class"] for item in qualifying}, key=principals.index)
    completed_responsibilities = sorted({
        value
        for item in qualifying
        for observation in item["observations"]
        if observation["outcome"] == "demonstrated"
        for value in observation["responsibility_classes"]
    }, key=responsibilities.index)
    completed_dimensions = sorted({observation["dimension"] for item in qualifying for observation in item["observations"] if observation["outcome"] == "demonstrated"}, key=dimensions.index)
    participant_refs = {item["participant_ref"] for item in qualifying}
    policies = {item["separation_policy"] for item in validated}
    separation_policy = "independent-principal-required" if "independent-principal-required" in policies else "role-record-only"
    required_distinct = len(principals) if separation_policy == "independent-principal-required" else 1 if qualifying else 0
    separation_satisfied = len(participant_refs) >= required_distinct
    freshness_limit = timedelta(seconds=int(model["freshness_seconds"]))
    qualifying_fresh = bool(qualifying) and all(timedelta(0) <= current - _timestamp(item["completed_at"], label="completed_at") <= freshness_limit for item in qualifying)
    source_flags = {
        "authenticated": bool(qualifying) and all(item["source_assurance"]["participant_authenticated"] for item in qualifying),
        "consented": bool(qualifying) and all(item["source_assurance"]["consent_obtained"] for item in qualifying),
        "deidentified": bool(qualifying) and all(item["source_assurance"]["direct_identifiers_removed"] for item in qualifying),
        "raw_content_excluded": bool(qualifying) and all(item["source_assurance"]["free_text_excluded"] for item in qualifying),
        "human_source_only": bool(qualifying) and len(qualifying) == len(validated),
    }
    blockers: list[str] = []
    if not qualifying:
        blockers.append("no_qualifying_human_session")
    if (human_sessions and len(qualifying) != len(human_sessions)) or machine_sessions:
        blockers.append("source_assurance_incomplete")
    if qualifying and not qualifying_fresh:
        blockers.append("session_stale")
    if set(completed_principals) != set(principals):
        blockers.append("principal_coverage_incomplete")
    if set(completed_responsibilities) != set(responsibilities):
        blockers.append("responsibility_coverage_incomplete")
    if set(completed_dimensions) != set(dimensions):
        blockers.append("observation_dimension_coverage_incomplete")
    if len(qualifying) < int(model["minimum_qualifying_role_sessions"]):
        blockers.append("minimum_qualifying_role_sessions_not_met")
    if not separation_satisfied:
        blockers.append("independent_principal_required")
    if not qualifying:
        status = "not_observed"
    elif blockers:
        status = "insufficient"
    else:
        status = "calibrated"
    if machine_sessions and not human_sessions:
        status = "not_observed"
    completed_at_values = [_timestamp(item["completed_at"], label="completed_at") for item in qualifying]
    fresh_until = min((item + freshness_limit for item in completed_at_values), default=current + freshness_limit)
    refs = [{
        "session_id": item["session_id"], "ref": f"sessions/{item['session_id']}.json",
        "digest": calibration_session_digest(item), "byte_length": len(_canonical_bytes(item)),
        "principal_class": item["principal_class"], "participant_ref": item["participant_ref"],
    } for item in validated]
    refs.sort(key=lambda item: item["session_id"])
    readback = {
        "schema_version": contract["schema_version"], "contract_version": model["contract_version"],
        "role_model_version": model["role_model_version"], "observation_model_version": model["observation_model_version"],
        "generated_at": current.isoformat(timespec="seconds"), "fresh_until": fresh_until.isoformat(timespec="seconds"),
        "status": status,
        "scope": {"decision_unit_id": inferred_unit, "evidence_fingerprint": inferred_fingerprint, "task_ids": sorted({item["scope"]["task_id"] for item in validated})},
        "sample_counters": {"session_count": len(validated), "human_source_session_count": len(human_sessions), "machine_source_session_count": len(machine_sessions), "qualifying_role_session_count": len(qualifying), "unique_participant_count": len(participant_refs)},
        "coverage": {"required_principal_classes": principals, "completed_principal_classes": completed_principals, "required_responsibility_classes": responsibilities, "completed_responsibility_classes": completed_responsibilities, "required_observation_dimensions": dimensions, "completed_observation_dimensions": completed_dimensions},
        "source_assurance": source_flags,
        "separation": {"policy": separation_policy, "satisfied": separation_satisfied, "distinct_participant_count": len(participant_refs), "required_distinct_participant_count": required_distinct},
        "session_refs": refs, "blockers": sorted(set(blockers), key=closed["human_calibration_blocker"].index),
    }
    return validate_calibration_readback(readback)


def validate_calibration_readback(value: object) -> dict[str, Any]:
    """Verify one Human-owned v2 readback structurally and semantically."""
    contract, closed, schemas, model = _contract_parts()
    if not isinstance(value, Mapping):
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "human_calibration_readback must be an object")
    try:
        readback = _exact_fields(dict(value), schemas["human_calibration_readback"]["required_fields"], label="human_calibration_readback")
    except CalibrationError as error:
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", error.detail)
    _version_check(readback, contract=contract, model=model, label="human_calibration_readback")
    if readback["status"] not in closed["human_calibration_status"]:
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "readback status unknown")
    for field, declaration in (("scope", "scope_required_fields"), ("sample_counters", "sample_counters_required_fields"), ("coverage", "coverage_required_fields"), ("source_assurance", "source_assurance_required_fields"), ("separation", "separation_required_fields")):
        try:
            _exact_fields(readback[field], schemas["human_calibration_readback"][declaration], label=f"readback.{field}")
        except CalibrationError as error:
            _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", error.detail)
    _timestamp(readback["generated_at"], label="generated_at")
    generated_at = _timestamp(readback["generated_at"], label="generated_at")
    fresh_until = _timestamp(readback["fresh_until"], label="fresh_until")
    if (fresh_until - generated_at).total_seconds() > int(model["freshness_seconds"]):
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "readback freshness window exceeds contract")
    if not isinstance(readback["session_refs"], list) or not isinstance(readback["blockers"], list):
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "session_refs/blockers must be lists")
    counters = readback["sample_counters"]
    if any(not isinstance(counters[field], int) or counters[field] < 0 for field in counters):
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "sample counters must be non-negative integers")
    if counters["session_count"] != len(readback["session_refs"]):
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "session count/ref count mismatch")
    coverage = readback["coverage"]
    assurance = readback["source_assurance"]
    separation = readback["separation"]
    for field in coverage:
        if not isinstance(coverage[field], list) or len(coverage[field]) != len(set(coverage[field])):
            _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", f"coverage.{field} must be a unique list")
    for field in assurance:
        if not isinstance(assurance[field], bool):
            _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", f"source_assurance.{field} must be boolean")
    if not isinstance(separation["satisfied"], bool):
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "separation.satisfied must be boolean")
    if readback["status"] == "calibrated" and (
        counters["qualifying_role_session_count"] < int(model["minimum_qualifying_role_sessions"])
        or coverage["required_principal_classes"] != coverage["completed_principal_classes"]
        or coverage["required_responsibility_classes"] != coverage["completed_responsibility_classes"]
        or coverage["required_observation_dimensions"] != coverage["completed_observation_dimensions"]
        or not all(assurance.values())
        or separation["satisfied"] is not True
        or readback["blockers"]
    ):
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "calibrated status contradicts readback facts")
    for index, ref in enumerate(readback["session_refs"]):
        try:
            item = _exact_fields(ref, schemas["human_calibration_readback"]["session_ref_required_fields"], label=f"session_refs[{index}]")
        except CalibrationError as error:
            _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", error.detail)
        if not _SHA256_RE.fullmatch(str(item["digest"])) or not isinstance(item["byte_length"], int) or item["byte_length"] <= 0:
            _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "session ref digest/byte_length invalid")
    return json.loads(json.dumps(readback, ensure_ascii=False))


def verify_calibration_readback(
    value: object, *, session_bytes_by_ref: Mapping[str, bytes], now: datetime,
    expected_scope: Mapping[str, str],
) -> dict[str, Any]:
    """Verify freshness, exact referenced bytes/digests, scope, and Human-derived status."""
    readback = validate_calibration_readback(value)
    if now.tzinfo is None or now.utcoffset() is None:
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "verification time must be timezone-aware")
    current = now.astimezone(timezone.utc)
    generated = _timestamp(readback["generated_at"], label="generated_at")
    fresh_until = _timestamp(readback["fresh_until"], label="fresh_until")
    if generated > current or current > fresh_until:
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "readback is stale or generated in the future")
    scope = readback["scope"]
    if scope["decision_unit_id"] != expected_scope["decision_unit_id"] or scope["evidence_fingerprint"] != expected_scope["evidence_fingerprint"]:
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "readback scope/fingerprint mismatch")
    sessions: list[dict[str, Any]] = []
    for ref in readback["session_refs"]:
        raw = session_bytes_by_ref.get(ref["ref"])
        if raw is None or len(raw) != ref["byte_length"] or "sha256:" + hashlib.sha256(raw).hexdigest() != ref["digest"]:
            _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "session exact bytes/digest drifted")
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "session bytes are not valid JSON")
        try:
            session = validate_calibration_session(value)
        except CalibrationError as error:
            _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", error.detail)
        if raw != _canonical_bytes(session) or session["session_id"] != ref["session_id"] or session["principal_class"] != ref["principal_class"] or session["participant_ref"] != ref["participant_ref"]:
            _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "session ref does not match exact session bytes")
        sessions.append(session)
    derived = summarize_calibration_sessions(sessions, now=generated, decision_unit_id=scope["decision_unit_id"], evidence_fingerprint=scope["evidence_fingerprint"])
    comparable_fields = ("status", "scope", "sample_counters", "coverage", "source_assurance", "separation", "session_refs", "blockers", "fresh_until")
    if any(readback[field] != derived[field] for field in comparable_fields):
        _fail("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE", "readback differs from Human-derived session semantics")
    return readback


def _read_regular_nofollow(path: Path) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            _fail("HAD.CALIBRATION_CONFLICT", "session path is not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError as error:
        _fail("HAD.CALIBRATION_CONFLICT", f"session cannot be read safely: {error}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_calibration_session(path: Path) -> dict[str, Any]:
    raw = _read_regular_nofollow(path)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("HAD.CALIBRATION_INVALID", f"session JSON is invalid: {error}")
    session = validate_calibration_session(value)
    if raw != _canonical_bytes(session):
        _fail("HAD.CALIBRATION_CONFLICT", "session bytes are not canonical")
    return session


def write_create_once_calibration_session(*, store: Path, session: Mapping[str, Any]) -> CalibrationWriteResult:
    validated = validate_calibration_session(dict(session))
    encoded = _canonical_bytes(validated)
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    store.mkdir(parents=True, exist_ok=True)
    if store.is_symlink() or not store.is_dir():
        _fail("HAD.CALIBRATION_CONFLICT", "session store must be a real directory")
    destination = store / f"{validated['session_id']}.json"
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o444)
    except FileExistsError:
        if _read_regular_nofollow(destination) != encoded:
            _fail("HAD.CALIBRATION_CONFLICT", "session_id already has different bytes")
        return CalibrationWriteResult(destination, f"sessions/{destination.name}", digest, validated, False)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("HAD.CALIBRATION_CONFLICT", "session write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(store, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return CalibrationWriteResult(destination, f"sessions/{destination.name}", digest, validated, True)


def read_calibration_store(store: Path, *, now: datetime | None = None) -> dict[str, Any]:
    if not store.exists():
        return summarize_calibration_sessions([], now=now)
    if store.is_symlink() or not store.is_dir():
        _fail("HAD.CALIBRATION_CONFLICT", "session store must be a real directory")
    sessions: list[dict[str, Any]] = []
    for path in sorted(store.iterdir()):
        if path.name.startswith("."):
            continue
        if path.suffix != ".json":
            _fail("HAD.CALIBRATION_CONFLICT", f"unexpected store entry: {path.name}")
        session = read_calibration_session(path)
        if path.name != f"{session['session_id']}.json":
            _fail("HAD.CALIBRATION_CONFLICT", f"noncanonical session path: {path.name}")
        sessions.append(session)
    return summarize_calibration_sessions(sessions, now=now)
