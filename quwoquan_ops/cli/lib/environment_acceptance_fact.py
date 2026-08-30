from __future__ import annotations
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from quwoquan_ops.cli.lib.target_uat_binding import (
    TargetUatBindingError,
    validate_target_uat_binding,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    ENVIRONMENTS,
    PREDECESSOR,
    PROD_ROLLOUT_STAGES,
    SCHEMA,
    SCHEMA_PATH,
    _ACTIVE_CAS_KEYS,
    _CARRIERS,
    _DEVICE_PROFILES,
    _DIGEST_RE,
    _ENTRIES,
    _EXACT_REF_KEYS,
    _FACT_KEYS,
    _FINALIZATION_KEYS,
    _IDENTITY_RE,
    _PLATFORMS,
    _PREDECESSOR_KEYS,
    _PROD_FACT_KEYS,
    _RAW_RESULT_KEYS,
    _TARGET_BINDING_KEYS,
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
        raise EnvironmentAcceptanceFactError(_INVALID, f"{field} must be RFC3339") from exc
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
            dict(fact), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EnvironmentAcceptanceFactError(_INVALID, "fact is not canonical JSON") from exc
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
        raise EnvironmentAcceptanceFactError(_EVIDENCE, f"{label} is not UTF-8 JSON") from exc
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
        raise EnvironmentAcceptanceFactError(_PATH_BLOCKED, f"{label} is unavailable") from exc
    if absolute.is_symlink() or resolved != absolute or not stat.S_ISDIR(metadata.st_mode):
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
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            or sum(map(len, chunks)) != opened.st_size
        ):
            _block(_PATH_BLOCKED, f"{label} changed while being read")
        return b"".join(chunks)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)
def _load_exact(root: Path, value: Mapping[str, Any], *, label: str) -> tuple[dict[str, Any], bytes]:
    if not isinstance(value, Mapping) or set(value) != _EXACT_REF_KEYS:
        _block(_INVALID, f"{label} must contain only ref and digest")
    ref = _relative_ref(value.get("ref"), field=f"{label}.ref")
    expected = _digest(value.get("digest"), field=f"{label}.digest")
    raw = _secure_read(root, ref, label=label)
    actual = exact_byte_digest(raw)
    if actual != expected:
        _block(_EVIDENCE, f"{label} exact-byte digest drifted: expected {expected}, got {actual}")
    return _decode_json(raw, label=label), raw
def _status(payload: Mapping[str, Any]) -> str:
    for field in ("status", "state", "phase", "lifecycleState"):
        value = payload.get(field)
        if isinstance(value, str) and value:
            return value
    return ""
def _require_status(payload: Mapping[str, Any], *, label: str, allowed: set[str]) -> None:
    observed = _status(payload)
    if observed.lower() not in {value.lower() for value in allowed}:
        _block(_EVIDENCE, f"{label} is not ready: got {observed!r}")
def _require_evidence_identity(
    payload: Mapping[str, Any], *, label: str, environment: str, target: str,
    release_id: str, release_digest: str,
) -> None:
    expected = {
        "environment": environment,
        "releaseId": release_id,
        "releaseDigest": release_digest,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            _block(_EVIDENCE, f"{label} identity drifted at {field}")
    observed_target = payload.get("deploymentTarget", payload.get("target"))
    if observed_target != target:
        _block(_EVIDENCE, f"{label} identity drifted at target")
def _normalize_exact_ref(value: object, *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _EXACT_REF_KEYS:
        _block(_INVALID, f"{label} must contain only ref and digest")
    return {
        "ref": _relative_ref(value.get("ref"), field=f"{label}.ref"),
        "digest": _digest(value.get("digest"), field=f"{label}.digest"),
    }
def _normalize_profiles(value: Sequence[Mapping[str, str]], *, label: str) -> set[tuple[str, str]]:
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
    target_uat_binding_digest: str,
    sample_id: str,
    entry_surface: str,
    carrier: str,
    spec_ref: str,
    runner_identity: str,
) -> str:
    material = {
        "targetUatBindingDigest": _digest(
            target_uat_binding_digest, field="targetUatBindingDigest"
        ),
        "sampleId": _identity(sample_id, field="sampleId"),
        "entrySurface": entry_surface,
        "carrier": carrier,
        "specRef": spec_ref,
        "runnerIdentity": runner_identity,
    }
    return "sha256:" + hashlib.sha256(canonical_fact_bytes(material)).hexdigest()
def _required_plan_cells(plan: Mapping[str, Any]) -> dict[tuple[str, str, str, str], dict[str, str]]:
    matrix = plan.get("entryCarrierCells")
    if not isinstance(matrix, list) or len(matrix) != len(_ENTRIES) * len(_CARRIERS):
        _block(_EVIDENCE, "release UAT sample plan must have exactly 16 entryCarrierCells")
    result: dict[tuple[str, str, str, str], dict[str, str]] = {}
    observed_axes: set[tuple[str, str]] = set()
    for index, cell in enumerate(matrix):
        if not isinstance(cell, Mapping):
            _block(_EVIDENCE, f"entryCarrierCells[{index}] is invalid")
        entry = _text(cell.get("entry"), field=f"entryCarrierCells[{index}].entry")
        carrier = _text(cell.get("carrier"), field=f"entryCarrierCells[{index}].carrier")
        axes = (entry, carrier)
        if entry not in _ENTRIES or carrier not in _CARRIERS or axes in observed_axes:
            _block(_EVIDENCE, "release UAT sample plan axes are unknown or duplicated")
        observed_axes.add(axes)
        applicability = cell.get("applicability")
        if applicability == "not_applicable":
            if set(cell) != {"entry", "carrier", "applicability", "reasonCode"}:
                _block(_EVIDENCE, f"entryCarrierCells[{index}] not_applicable fields drifted")
            _text(cell.get("reasonCode"), field=f"entryCarrierCells[{index}].reasonCode")
            continue
        if applicability != "required" or set(cell) != {
            "entry", "carrier", "applicability", "specRef", "runnerClass"
        }:
            _block(_EVIDENCE, f"entryCarrierCells[{index}] required fields drifted")
        spec_ref = _text(cell.get("specRef"), field=f"entryCarrierCells[{index}].specRef")
        runner = _text(cell.get("runnerClass"), field=f"entryCarrierCells[{index}].runnerClass")
        key = (entry, carrier, spec_ref, runner)
        if key in result:
            _block(_EVIDENCE, "sample plan contains a duplicate required cell")
        result[key] = {
            "entrySurface": entry,
            "carrier": carrier,
            "specRef": spec_ref,
            "runnerIdentity": runner,
        }
    if observed_axes != {(entry, carrier) for entry in _ENTRIES for carrier in _CARRIERS}:
        _block(_EVIDENCE, "release UAT sample plan does not cover the canonical matrix")
    if not result:
        _block(_EVIDENCE, "release UAT sample plan has no required cells")
    return result
def _fact_id_material(fact: Mapping[str, Any]) -> dict[str, Any]:
    target_bindings = fact.get("targetBindingRefs")
    raw_results = fact.get("requiredRawResults")
    finalization = fact.get("resourceFinalization")
    prod = fact.get("prodReleaseFacts")
    predecessor = fact.get("predecessorAcceptance")
    return {
        "schema": fact.get("schema"),
        "environment": fact.get("environment"),
        "target": fact.get("target"),
        "releaseId": fact.get("releaseId"),
        "releaseDigest": fact.get("releaseDigest"),
        "samplePlanDigest": fact.get("samplePlanDigest"),
        "targetBindingDigests": sorted(
            (
                {
                    "digest": item.get("digest"),
                    "platform": item.get("platform"),
                    "deviceProfile": item.get("deviceProfile"),
                }
                for item in target_bindings
                if isinstance(item, Mapping)
            ),
            key=lambda item: (
                str(item["platform"]), str(item["deviceProfile"]), str(item["digest"])
            ),
        ) if isinstance(target_bindings, list) else target_bindings,
        "requiredRawDigests": sorted(
            (
                {"digest": item.get("digest"), "slotId": item.get("slotId")}
                for item in raw_results
                if isinstance(item, Mapping)
            ),
            key=lambda item: (str(item["slotId"]), str(item["digest"])),
        ) if isinstance(raw_results, list) else raw_results,
        "dataReadinessDigest": (fact.get("dataReadiness") or {}).get("digest")
        if isinstance(fact.get("dataReadiness"), Mapping) else None,
        "activeCas": {
            field: (fact.get("activeCas") or {}).get(field)
            for field in ("digest", "readbackDigest", "releaseId", "releaseDigest")
        } if isinstance(fact.get("activeCas"), Mapping) else fact.get("activeCas"),
        "lifecycleExitDigest": (fact.get("lifecycleExit") or {}).get("digest")
        if isinstance(fact.get("lifecycleExit"), Mapping) else None,
        "providerReadinessDigest": (fact.get("providerReadiness") or {}).get("digest")
        if isinstance(fact.get("providerReadiness"), Mapping) else None,
        "observabilityReadinessDigest": (fact.get("observabilityReadiness") or {}).get("digest")
        if isinstance(fact.get("observabilityReadiness"), Mapping) else None,
        "rollbackReadinessDigest": (fact.get("rollbackReadiness") or {}).get("digest")
        if isinstance(fact.get("rollbackReadiness"), Mapping) else None,
        "predecessorAcceptance": {
            field: predecessor.get(field)
            for field in ("environment", "factId", "digest")
        } if isinstance(predecessor, Mapping) else predecessor,
        "resourceFinalizationDigests": {
            field: sorted(
                str(item.get("digest")) for item in finalization.get(field, [])
                if isinstance(item, Mapping)
            )
            for field in _FINALIZATION_KEYS
        } if isinstance(finalization, Mapping) else finalization,
        "prodReleaseFacts": {
            "engineeringEligibilityDigest": (prod.get("engineeringEligibility") or {}).get("digest"),
            "durableApprovalDigest": (prod.get("durableApproval") or {}).get("digest"),
            "rolloutStageDigests": [
                {"stage": item.get("stage"), "digest": item.get("digest")}
                for item in prod.get("rolloutStages", []) if isinstance(item, Mapping)
            ],
            "rollbackReadinessDigest": (prod.get("rollbackReadiness") or {}).get("digest"),
        } if isinstance(prod, Mapping) else prod,
        "sourceFingerprint": fact.get("sourceFingerprint"),
    }
def derive_fact_id(fact: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_fact_bytes(_fact_id_material(fact))).hexdigest()
def _verify_common_evidence(
    root: Path, value: object, *, label: str, allowed_statuses: set[str],
    identity: dict[str, str],
) -> dict[str, Any]:
    exact = _normalize_exact_ref(value, label=label)
    payload, _ = _load_exact(root, exact, label=label)
    _require_evidence_identity(payload, label=label, **identity)
    _require_status(payload, label=label, allowed=allowed_statuses)
    return payload
def _validate_finalization(
    root: Path, value: object, *, identity: dict[str, str], verify_references: bool,
) -> dict[str, list[dict[str, str]]]:
    if not isinstance(value, Mapping) or set(value) != _FINALIZATION_KEYS:
        _block(_INVALID, "resourceFinalization fields are invalid")
    statuses = {
        "leaseRevocationRefs": {"revoked"},
        "lockReleaseRefs": {"released"},
        "gcProtectionRefs": {"protected", "ready", "passed"},
    }
    result: dict[str, list[dict[str, str]]] = {}
    for field, allowed in statuses.items():
        items = value.get(field)
        if not isinstance(items, list) or not items:
            _block(_INVALID, f"resourceFinalization.{field} must be non-empty")
        seen: set[str] = set()
        normalized: list[dict[str, str]] = []
        for index, item in enumerate(items):
            label = f"resourceFinalization.{field}[{index}]"
            exact = _normalize_exact_ref(item, label=label)
            if exact["ref"] in seen:
                _block(_INVALID, f"resourceFinalization.{field} contains duplicate refs")
            seen.add(exact["ref"])
            normalized.append(exact)
            if verify_references:
                _verify_common_evidence(
                    root, exact, label=label, allowed_statuses=allowed, identity=identity
                )
        result[field] = normalized
    return result
def _validate_prod_facts(
    root: Path, value: object, *, environment: str, identity: dict[str, str],
    verify_references: bool,
) -> dict[str, Any] | None:
    if environment != "prod":
        if value is not None:
            _block(_INVALID, "non-prod fact must have prodReleaseFacts=null")
        return None
    if not isinstance(value, Mapping) or set(value) != _PROD_FACT_KEYS:
        _block(_INVALID, "prod requires the closed canonical prodReleaseFacts set")
    result: dict[str, Any] = {
        "engineeringEligibility": _normalize_exact_ref(
            value.get("engineeringEligibility"), label="prodReleaseFacts.engineeringEligibility"
        ),
        "durableApproval": _normalize_exact_ref(
            value.get("durableApproval"), label="prodReleaseFacts.durableApproval"
        ),
        "rollbackReadiness": _normalize_exact_ref(
            value.get("rollbackReadiness"), label="prodReleaseFacts.rollbackReadiness"
        ),
    }
    stages = value.get("rolloutStages")
    if not isinstance(stages, list) or len(stages) != len(PROD_ROLLOUT_STAGES):
        _block(_INVALID, "prod rolloutStages must contain canary/5/20/50/100")
    normalized_stages: list[dict[str, str]] = []
    for expected, item in zip(PROD_ROLLOUT_STAGES, stages, strict=True):
        if not isinstance(item, Mapping) or set(item) != {"stage", "ref", "digest"}:
            _block(_INVALID, "prod rollout stage fields are invalid")
        if item.get("stage") != expected:
            _block(_INVALID, f"prod rollout stage order requires {expected}")
        exact = _normalize_exact_ref(
            {"ref": item.get("ref"), "digest": item.get("digest")},
            label=f"prodReleaseFacts.rolloutStages[{expected}]",
        )
        normalized_stages.append({"stage": expected, **exact})
    result["rolloutStages"] = normalized_stages
    if verify_references:
        role_specs = (
            ("engineeringEligibility", "engineeringEligibility", {"eligible", "passed", "ready"}),
            ("durableApproval", "durableApproval", {"approved", "passed"}),
            ("rollbackReadiness", "rollbackReadiness", {"ready", "passed"}),
        )
        for field, role, statuses in role_specs:
            payload = _verify_common_evidence(
                root, result[field], label=f"prodReleaseFacts.{field}",
                allowed_statuses=statuses, identity=identity,
            )
            if payload.get("factType") != role:
                _block(_EVIDENCE, f"prodReleaseFacts.{field} has the wrong factType")
        for stage in normalized_stages:
            payload = _verify_common_evidence(
                root, {"ref": stage["ref"], "digest": stage["digest"]},
                label=f"prodReleaseFacts.rolloutStages[{stage['stage']}]",
                allowed_statuses={"passed", "completed", "continue"}, identity=identity,
            )
            if payload.get("factType") != "rolloutStage" or payload.get("stage") != stage["stage"]:
                _block(_EVIDENCE, "prod rollout fact role or stage drifted")
    return result
def validate_predecessor_acceptance(
    *, environment: str, predecessor_acceptance: Mapping[str, Any] | None,
    evidence_root: Path, release_id: str, release_digest: str,
) -> dict[str, str] | None:
    expected = PREDECESSOR.get(environment)
    if expected is None:
        if environment != "alpha":
            _block(_INVALID, "environment is unknown")
        if predecessor_acceptance is not None:
            _block(_PREDECESSOR_BLOCKED, "alpha must not provide predecessor acceptance")
        return None
    if not isinstance(predecessor_acceptance, Mapping) or set(predecessor_acceptance) != _PREDECESSOR_KEYS:
        _block(_PREDECESSOR_BLOCKED, f"{environment} requires exact {expected} predecessor")
    if predecessor_acceptance.get("environment") != expected:
        _block(_PREDECESSOR_BLOCKED, f"{environment} predecessor must be exactly {expected}")
    normalized = {
        "environment": expected,
        "factId": _digest(predecessor_acceptance.get("factId"), field="predecessorAcceptance.factId"),
        "ref": _relative_ref(predecessor_acceptance.get("ref"), field="predecessorAcceptance.ref"),
        "digest": _digest(predecessor_acceptance.get("digest"), field="predecessorAcceptance.digest"),
    }
    raw = _secure_read(evidence_root, normalized["ref"], label="predecessorAcceptance")
    if exact_byte_digest(raw) != normalized["digest"]:
        _block(_PREDECESSOR_BLOCKED, "predecessor acceptance exact bytes drifted")
    previous = _decode_json(raw, label="predecessorAcceptance")
    previous_profiles = [
        {"platform": item.get("platform"), "deviceProfile": item.get("deviceProfile")}
        for item in previous.get("targetBindingRefs", [])
        if isinstance(item, Mapping)
    ]
    try:
        validate_environment_acceptance_fact(
            previous, evidence_root=evidence_root,
            required_target_profiles=previous_profiles, verify_references=True,
        )
    except EnvironmentAcceptanceFactError as exc:
        raise EnvironmentAcceptanceFactError(
            _PREDECESSOR_BLOCKED, f"predecessor acceptance is invalid: {exc}"
        ) from exc
    if (
        previous.get("environment") != expected
        or previous.get("releaseId") != release_id
        or previous.get("releaseDigest") != release_digest
        or previous.get("factId") != normalized["factId"]
    ):
        _block(_PREDECESSOR_BLOCKED, "predecessor acceptance identity drifted")
    return normalized
def validate_environment_acceptance_fact(
    payload: Mapping[str, Any], *, evidence_root: Path,
    required_target_profiles: Sequence[Mapping[str, str]], verify_references: bool = True,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _FACT_KEYS:
        _block(_INVALID, "environment acceptance fact fields are invalid")
    fact = dict(payload)
    if fact.get("schema") != SCHEMA:
        _block(_INVALID, "schema is not EnvironmentAcceptanceFact v1")
    fact_id = _digest(fact.get("factId"), field="factId")
    environment = _text(fact.get("environment"), field="environment")
    if environment not in ENVIRONMENTS:
        _block(_INVALID, "environment is unknown")
    target = _identity(fact.get("target"), field="target")
    release_id = _identity(fact.get("releaseId"), field="releaseId")
    release_digest = _digest(fact.get("releaseDigest"), field="releaseDigest")
    _timestamp(fact.get("createdAt"), field="createdAt")
    _digest(fact.get("sourceFingerprint"), field="sourceFingerprint")
    plan_ref = _relative_ref(
        fact.get("samplePlanRef"), field="samplePlanRef"
    )
    plan_digest = _digest(
        fact.get("samplePlanDigest"), field="samplePlanDigest"
    )
    expected_profiles = _normalize_profiles(
        required_target_profiles, label="required_target_profiles"
    )
    identity = {
        "environment": environment, "target": target,
        "release_id": release_id, "release_digest": release_digest,
    }
    root = _absolute_real_root(evidence_root, label="evidence root")
    if not verify_references:
        if derive_fact_id(fact) != fact_id:
            _block(_INVALID, "factId drifted from the authority digest collection")
        return fact
    plan_cells: dict[tuple[str, str, str, str], dict[str, str]] = {}
    plan_samples: list[dict[str, str]] = []
    if verify_references:
        plan_raw = _secure_read(root, plan_ref, label="samplePlan")
        if exact_byte_digest(plan_raw) != plan_digest:
            _block(_EVIDENCE, "release UAT sample plan exact-byte digest drifted")
        plan = _decode_json(plan_raw, label="samplePlan")
        if (
            plan.get("schema") != "quwoquan_data.release_uat_sample_plan"
            or plan.get("releaseId") != release_id
        ):
            _block(_EVIDENCE, "release UAT sample plan identity drifted")
        plan_cells = _required_plan_cells(plan)
        raw_samples = plan.get("samples")
        if not isinstance(raw_samples, list) or not raw_samples:
            _block(_EVIDENCE, "release UAT sample plan samples are missing")
        seen_sample_ids: set[str] = set()
        seen_object_ids: set[str] = set()
        seen_object_refs: set[str] = set()
        for index, sample in enumerate(raw_samples):
            if not isinstance(sample, Mapping) or set(sample) != {
                "sampleId", "carrier", "objectId", "objectRef", "objectDigest",
            }:
                _block(_EVIDENCE, f"samplePlan.samples[{index}] fields are invalid")
            sample_id = _identity(
                sample.get("sampleId"), field=f"samplePlan.samples[{index}].sampleId"
            )
            carrier = _text(
                sample.get("carrier"), field=f"samplePlan.samples[{index}].carrier"
            )
            object_id = _text(
                sample.get("objectId"), field=f"samplePlan.samples[{index}].objectId"
            )
            object_ref = _relative_ref(
                sample.get("objectRef"), field=f"samplePlan.samples[{index}].objectRef"
            )
            object_digest = _digest(
                sample.get("objectDigest"), field=f"samplePlan.samples[{index}].objectDigest"
            )
            if (
                sample_id in seen_sample_ids
                or object_id in seen_object_ids
                or object_ref in seen_object_refs
                or carrier not in _CARRIERS
            ):
                _block(_EVIDENCE, "sample plan sample/object id or ref is duplicated")
            expected_prefix = (
                "objects/entities/"
                if carrier == "homepage"
                else f"objects/posts/{carrier}/"
            )
            if not object_ref.startswith(expected_prefix):
                _block(_EVIDENCE, f"samplePlan.samples[{index}].objectRef is not carrier-bound")
            seen_sample_ids.add(sample_id)
            seen_object_ids.add(object_id)
            seen_object_refs.add(object_ref)
            plan_samples.append(
                {
                    "sampleId": sample_id,
                    "carrier": carrier,
                    "objectId": object_id,
                    "objectRef": object_ref,
                    "objectDigest": object_digest,
                }
            )
    bindings = fact.get("targetBindingRefs")
    if not isinstance(bindings, list) or not bindings:
        _block(_INVALID, "targetBindingRefs must be non-empty")
    binding_by_digest: dict[str, tuple[str, str, str]] = {}
    observed_profiles: set[tuple[str, str]] = set()
    seen_binding_refs: set[str] = set()
    for index, item in enumerate(bindings):
        label = f"targetBindingRefs[{index}]"
        if not isinstance(item, Mapping) or set(item) != _TARGET_BINDING_KEYS:
            _block(_INVALID, f"{label} fields are invalid")
        exact = _normalize_exact_ref(
            {"ref": item.get("ref"), "digest": item.get("digest")}, label=label
        )
        platform = _text(item.get("platform"), field=f"{label}.platform")
        profile = _text(item.get("deviceProfile"), field=f"{label}.deviceProfile")
        if platform not in _PLATFORMS or profile not in _DEVICE_PROFILES:
            _block(_INVALID, f"{label} platform/deviceProfile is unknown")
        if exact["ref"] in seen_binding_refs or exact["digest"] in binding_by_digest:
            _block(_INVALID, "targetBindingRefs contains duplicate ref or digest")
        if (platform, profile) in observed_profiles:
            _block(_INVALID, "targetBindingRefs contains duplicate platform/device profile")
        seen_binding_refs.add(exact["ref"])
        observed_profiles.add((platform, profile))
        if verify_references:
            binding, _ = _load_exact(root, exact, label=label)
            try:
                binding = validate_target_uat_binding(binding)
            except TargetUatBindingError as exc:
                raise EnvironmentAcceptanceFactError(
                    _EVIDENCE, f"{label} is not a strict TargetUatBinding: {exc}"
                ) from exc
            expected_binding = {
                "releaseId": release_id,
                "releaseDigest": release_digest,
                "releaseUatSamplePlanRef": plan_ref,
                "releaseUatSamplePlanDigest": plan_digest,
                "environment": environment,
                "target": target,
                "platform": platform,
            }
            for field, expected_value in expected_binding.items():
                if binding.get(field) != expected_value:
                    _block(_EVIDENCE, f"{label} identity drifted at {field}")
            if _binding_device_profile(binding) != profile:
                _block(_EVIDENCE, f"{label} deviceProfile drifted")
            binding_by_digest[exact["digest"]] = (
                platform,
                profile,
                str(binding["provider"]["identity"]),
            )
    if observed_profiles != expected_profiles:
        _block(_EVIDENCE, "targetBindingRefs do not exactly cover required platform/device profiles")
    raw_results = fact.get("requiredRawResults")
    if not isinstance(raw_results, list) or not raw_results:
        _block(_INVALID, "requiredRawResults must be non-empty")
    observed_slots: set[str] = set()
    seen_raw_refs: set[str] = set()
    for index, item in enumerate(raw_results):
        label = f"requiredRawResults[{index}]"
        if not isinstance(item, Mapping) or set(item) != _RAW_RESULT_KEYS:
            _block(_INVALID, f"{label} fields are invalid; bundle substitution is forbidden")
        exact = _normalize_exact_ref(
            {"ref": item.get("ref"), "digest": item.get("digest")}, label=label
        )
        slot_id = _digest(item.get("slotId"), field=f"{label}.slotId")
        if item.get("status") != "passed":
            _block(_EVIDENCE, f"{label}.status must be exactly passed")
        if exact["ref"] in seen_raw_refs or slot_id in observed_slots:
            _block(_EVIDENCE, "requiredRawResults contains duplicate raw ref or slotId")
        seen_raw_refs.add(exact["ref"])
        observed_slots.add(slot_id)
        if verify_references:
            raw_result, _ = _load_exact(root, exact, label=label)
            if raw_result.get("producer") != "app" or raw_result.get("layer") != "user_acceptance":
                _block(_EVIDENCE, f"{label} is not a direct raw App ReadinessCaseResult")
            if raw_result.get("status") != "passed":
                _block(_EVIDENCE, f"{label} referenced raw status is not passed")
            _require_evidence_identity(raw_result, label=label, **identity)
            binding_digest = raw_result.get("targetUatBindingDigest")
            binding_digest = str(binding_digest)
            profile = binding_by_digest.get(binding_digest)
            if profile is None:
                _block(_EVIDENCE, f"{label} targetUatBindingDigest is not directly listed")
            platform, device_profile, provider_identity = profile
            if (
                raw_result.get("platform") != platform
                or raw_result.get("uatProfile") != device_profile
                or raw_result.get("provider") != provider_identity
            ):
                _block(
                    _EVIDENCE,
                    f"{label} platform/device profile/provider identity drifted",
                )
            cell_key = (
                str(raw_result.get("entrySurface") or ""),
                str(raw_result.get("carrier") or ""),
                str(raw_result.get("specRef") or ""),
                str(raw_result.get("runnerIdentity") or ""),
            )
            if cell_key not in plan_cells:
                _block(_EVIDENCE, f"{label} does not bind a required sample-plan cell")
            cell = plan_cells[cell_key]
            matching_samples = [
                sample
                for sample in plan_samples
                if sample["carrier"] == cell["carrier"]
                and sample["objectId"] == raw_result.get("objectId")
            ]
            if len(matching_samples) != 1:
                _block(_EVIDENCE, f"{label} does not bind exactly one sample-plan object")
            sample_id = matching_samples[0]["sampleId"]
            expected_slot = required_raw_slot_id(
                target_uat_binding_digest=binding_digest,
                sample_id=sample_id,
                entry_surface=cell["entrySurface"],
                carrier=cell["carrier"],
                spec_ref=cell["specRef"],
                runner_identity=cell["runnerIdentity"],
            )
            if slot_id != expected_slot:
                _block(_EVIDENCE, f"{label}.slotId drifted from plan cell/profile authority")
    if verify_references:
        expected_slots = {
            required_raw_slot_id(
                target_uat_binding_digest=binding_digest,
                sample_id=sample["sampleId"],
                entry_surface=cell["entrySurface"],
                carrier=cell["carrier"],
                spec_ref=cell["specRef"],
                runner_identity=cell["runnerIdentity"],
            )
            for sample in plan_samples
            for cell in plan_cells.values()
            if sample["carrier"] == cell["carrier"]
            for binding_digest, (platform, device_profile, _provider) in binding_by_digest.items()
            if (platform, device_profile) in expected_profiles
        }
        if observed_slots != expected_slots:
            missing = sorted(expected_slots - observed_slots)
            extra = sorted(observed_slots - expected_slots)
            _block(_EVIDENCE, f"required raw exact coverage drifted: missing={missing}, extra={extra}")
    exact_evidence = (
        ("dataReadiness", {"passed", "ready"}),
        ("lifecycleExit", {"Exit"}),
        ("providerReadiness", {"passed", "ready"}),
        ("observabilityReadiness", {"passed", "ready"}),
        ("rollbackReadiness", {"passed", "ready"}),
    )
    for field, statuses in exact_evidence:
        exact = _normalize_exact_ref(fact.get(field), label=field)
        if verify_references:
            _verify_common_evidence(
                root, exact, label=field, allowed_statuses=statuses, identity=identity
            )
    active = fact.get("activeCas")
    if not isinstance(active, Mapping) or set(active) != _ACTIVE_CAS_KEYS:
        _block(_INVALID, "activeCas fields are invalid")
    if active.get("releaseId") != release_id or active.get("releaseDigest") != release_digest:
        _block(_EVIDENCE, "activeCas release identity drifted")
    active_ref = _normalize_exact_ref(
        {"ref": active.get("ref"), "digest": active.get("digest")}, label="activeCas"
    )
    readback_ref = _normalize_exact_ref(
        {"ref": active.get("readbackRef"), "digest": active.get("readbackDigest")},
        label="activeCas.readback",
    )
    if verify_references:
        _verify_common_evidence(
            root, active_ref, label="activeCas", allowed_statuses={"active", "ready"},
            identity=identity,
        )
        _verify_common_evidence(
            root, readback_ref, label="activeCas.readback",
            allowed_statuses={"active", "passed", "ready"}, identity=identity,
        )
    _validate_finalization(
        root, fact.get("resourceFinalization"), identity=identity,
        verify_references=verify_references,
    )
    _validate_prod_facts(
        root, fact.get("prodReleaseFacts"), environment=environment,
        identity=identity, verify_references=verify_references,
    )
    validate_predecessor_acceptance(
        environment=environment,
        predecessor_acceptance=fact.get("predecessorAcceptance"),
        evidence_root=root, release_id=release_id, release_digest=release_digest,
    )
    if derive_fact_id(fact) != fact_id:
        _block(_INVALID, "factId drifted from the authority digest collection")
    return fact
def build_environment_acceptance_fact(
    *, evidence_root: Path, environment: str, target: str, release_id: str,
    release_digest: str, sample_plan_ref: str,
    sample_plan_digest: str,
    target_binding_refs: Sequence[Mapping[str, Any]],
    required_raw_results: Sequence[Mapping[str, Any]],
    required_target_profiles: Sequence[Mapping[str, str]],
    data_readiness: Mapping[str, str], active_cas: Mapping[str, str],
    lifecycle_exit: Mapping[str, str], provider_readiness: Mapping[str, str],
    observability_readiness: Mapping[str, str], rollback_readiness: Mapping[str, str],
    predecessor_acceptance: Mapping[str, str] | None,
    resource_finalization: Mapping[str, Sequence[Mapping[str, str]]],
    prod_release_facts: Mapping[str, Any] | None,
    created_at: str, source_fingerprint: str,
) -> dict[str, Any]:
    fact: dict[str, Any] = {
        "schema": SCHEMA,
        "factId": "sha256:" + "0" * 64,
        "environment": environment,
        "target": target,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "samplePlanRef": sample_plan_ref,
        "samplePlanDigest": sample_plan_digest,
        "targetBindingRefs": [dict(item) for item in target_binding_refs],
        "requiredRawResults": [dict(item) for item in required_raw_results],
        "dataReadiness": dict(data_readiness),
        "activeCas": dict(active_cas),
        "lifecycleExit": dict(lifecycle_exit),
        "providerReadiness": dict(provider_readiness),
        "observabilityReadiness": dict(observability_readiness),
        "rollbackReadiness": dict(rollback_readiness),
        "predecessorAcceptance": (
            dict(predecessor_acceptance) if predecessor_acceptance is not None else None
        ),
        "resourceFinalization": {
            key: [dict(item) for item in values]
            for key, values in resource_finalization.items()
        },
        "prodReleaseFacts": (
            {
                key: ([dict(item) for item in value] if key == "rolloutStages" else dict(value))
                for key, value in prod_release_facts.items()
            }
            if prod_release_facts is not None else None
        ),
        "createdAt": created_at,
        "sourceFingerprint": source_fingerprint,
    }
    fact["factId"] = derive_fact_id(fact)
    return validate_environment_acceptance_fact(
        fact, evidence_root=evidence_root,
        required_target_profiles=required_target_profiles, verify_references=True,
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
    *, root: Path, fact: Mapping[str, Any], evidence_root: Path,
    required_target_profiles: Sequence[Mapping[str, str]],
) -> Path:
    validated = validate_environment_acceptance_fact(
        fact, evidence_root=evidence_root,
        required_target_profiles=required_target_profiles, verify_references=True,
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
                temporary, filename, src_dir_fd=environment_fd,
                dst_dir_fd=environment_fd, follow_symlinks=False,
            )
        except FileExistsError:
            if _read_existing_at(environment_fd, filename) != encoded:
                _block(_CREATE_CONFLICT, "factId already exists with different exact bytes")
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
    *, root: Path, evidence_root: Path,
    required_target_profiles: Sequence[Mapping[str, str]], **builder_arguments: Any,
) -> Path:
    fact = build_environment_acceptance_fact(
        evidence_root=evidence_root,
        required_target_profiles=required_target_profiles,
        **builder_arguments,
    )
    return write_environment_acceptance_fact(
        root=root, fact=fact, evidence_root=evidence_root,
        required_target_profiles=required_target_profiles,
    )
def load_environment_acceptance_fact(
    ref: str, *, evidence_root: Path,
    required_target_profiles: Sequence[Mapping[str, str]] | None = None,
    verify_references: bool = True,
) -> tuple[dict[str, Any], str]:
    raw = _secure_read(evidence_root, ref, label="environmentAcceptanceFact")
    fact = _decode_json(raw, label="environmentAcceptanceFact")
    profiles = required_target_profiles
    if profiles is None:
        refs = fact.get("targetBindingRefs")
        profiles = [
            {"platform": item.get("platform"), "deviceProfile": item.get("deviceProfile")}
            for item in refs
        ] if isinstance(refs, list) else []
    validated = validate_environment_acceptance_fact(
        fact, evidence_root=evidence_root,
        required_target_profiles=profiles, verify_references=verify_references,
    )
    return validated, exact_byte_digest(raw)
__all__ = ["ENVIRONMENTS", "PREDECESSOR", "PROD_ROLLOUT_STAGES", "SCHEMA", "SCHEMA_PATH",
    "EnvironmentAcceptanceFactError", "build_environment_acceptance_fact", "canonical_fact_bytes", "create_environment_acceptance_fact", "derive_fact_id",
    "environment_acceptance_fact_relative_path", "exact_byte_digest", "load_environment_acceptance_fact", "required_raw_slot_id",
    "validate_environment_acceptance_fact", "validate_predecessor_acceptance", "write_environment_acceptance_fact"]
