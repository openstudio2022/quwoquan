"""Create-once stable-tag production admission, rollout, rollback and soak facts."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from quwoquan_ops.ci.release_evidence_reader import _window_seconds
from quwoquan_ops.cli.prod import hosted_release_ledger
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_STABLE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_STAGES = ("canary", "5", "20", "50", "100")
_EVIDENCE = ("activation", "health", "slo", "placement", "readback")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_ROOT = _REPO_ROOT / "quwoquan_ops/environments/evidence"
_SOAK_POLICY = _REPO_ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
_FACT_SCHEMAS = {
    "quwoquan_ops.prod_stage_attempt_fact.v1": ("prod_stage_attempt_fact.schema.json", "attemptId"),
    "quwoquan_ops.prod_released_fact.v1": ("prod_released_fact.schema.json", "releaseId"),
    "quwoquan_ops.prod_rollback_fact.v1": ("prod_rollback_fact.schema.json", "rollbackId"),
    "quwoquan_ops.post_release_soak_fact.v1": ("post_release_soak_fact.schema.json", "soakId"),
}
class QualifiedProdError(ValueError):
    pass
def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
def digest(value: Mapping[str, Any] | Path | bytes) -> str:
    raw = value.read_bytes() if isinstance(value, Path) else value if isinstance(value, bytes) else canonical_bytes(value)
    return "sha256:" + hashlib.sha256(raw).hexdigest()
@lru_cache(maxsize=None)
def _fact_validator(schema_name: str) -> Draft202012Validator:
    contract = _FACT_SCHEMAS.get(schema_name)
    if contract is None:
        raise QualifiedProdError(f"unsupported Prod lifecycle schema: {schema_name!r}")
    path = _SCHEMA_ROOT / contract[0]
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError) as exc:
        raise QualifiedProdError(f"canonical lifecycle schema is unavailable: {path}") from exc
    return Draft202012Validator(schema, format_checker=FormatChecker())
def validate_prod_lifecycle_fact(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one lifecycle fact against its sole schema and canonical self-ID."""
    if not isinstance(value, Mapping):
        raise QualifiedProdError("Prod lifecycle fact must be an object")
    fact = dict(value)
    schema_name = fact.get("schema")
    if not isinstance(schema_name, str) or schema_name not in _FACT_SCHEMAS:
        raise QualifiedProdError("Prod lifecycle fact schema is not canonical")
    try:
        _fact_validator(schema_name).validate(fact)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise QualifiedProdError(
            f"{schema_name} schema validation failed at {location}: {exc.message}"
        ) from exc
    identity_field = _FACT_SCHEMAS[schema_name][1]
    unsigned = dict(fact)
    declared = unsigned.pop(identity_field)
    if declared != digest(unsigned):
        raise QualifiedProdError(f"{schema_name} canonical self-ID is invalid")
    return fact
def _typed_fact(value: Mapping[str, Any], schema: str, label: str) -> dict[str, Any]:
    fact = validate_prod_lifecycle_fact(value)
    if fact["schema"] != schema:
        raise QualifiedProdError(f"expected {label}")
    return fact
def validate_prod_stage_attempt_fact(value: Mapping[str, Any]) -> dict[str, Any]:
    return _typed_fact(value, "quwoquan_ops.prod_stage_attempt_fact.v1", "ProdStageAttemptFact")
def validate_prod_released_fact(value: Mapping[str, Any]) -> dict[str, Any]:
    return _typed_fact(value, "quwoquan_ops.prod_released_fact.v1", "ProdReleasedFact")
def validate_prod_rollback_fact(value: Mapping[str, Any]) -> dict[str, Any]:
    return _typed_fact(value, "quwoquan_ops.prod_rollback_fact.v1", "ProdRollbackFact")
def validate_post_release_soak_fact(value: Mapping[str, Any]) -> dict[str, Any]:
    return _typed_fact(value, "quwoquan_ops.post_release_soak_fact.v1", "PostReleaseSoakFact")
def _timestamp(value: object, field: str) -> tuple[str, dt.datetime]:
    text = _text(value, field)
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QualifiedProdError(f"{field} is not a timestamp") from exc
    if parsed.tzinfo is None:
        raise QualifiedProdError(f"{field} has no timezone")
    return text, parsed.astimezone(dt.timezone.utc)
def _authoritative_timestamp(value: object, expected: object, field: str) -> str:
    expected_text, expected_time = _timestamp(expected, f"{field}.hosted")
    _, actual_time = _timestamp(value, field)
    if actual_time != expected_time:
        raise QualifiedProdError(f"{field} must equal hosted receipt verifiedAt")
    return expected_text
def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ch in value for ch in "\x00\r\n"):
        raise QualifiedProdError(f"{field} is invalid")
    return value
def _sha(value: object, field: str) -> str:
    result = _text(value, field)
    if _GIT.fullmatch(result) is None:
        raise QualifiedProdError(f"{field} is not exact Git identity")
    return result
def _exact_digest(value: object, field: str) -> str:
    result = _text(value, field)
    if _DIGEST.fullmatch(result) is None:
        raise QualifiedProdError(f"{field} is not exact digest")
    return result
def _exact(root: Path, value: object, field: str) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise QualifiedProdError(f"{field} must contain exact ref and digest")
    ref = _text(value.get("ref"), f"{field}.ref")
    relative = PurePosixPath(ref)
    if relative.is_absolute() or relative.as_posix() != ref or "\\" in ref or any(part in {"", ".", "..", "latest", "main"} for part in relative.parts):
        raise QualifiedProdError(f"{field}.ref is mutable or unsafe")
    expected = _exact_digest(value.get("digest"), f"{field}.digest")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise QualifiedProdError(f"{field}.ref traverses symlink")
    if not current.is_file() or digest(current) != expected:
        raise QualifiedProdError(f"{field} exact bytes drifted")
    try:
        payload = json.loads(current.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualifiedProdError(f"{field} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise QualifiedProdError(f"{field} must be an object")
    return payload, {"ref": ref, "digest": expected}
def _write_once(path: Path, payload: Mapping[str, Any]) -> Path:
    encoded = canonical_bytes(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError as exc:
        if path.is_symlink() or path.read_bytes() != encoded:
            raise QualifiedProdError(f"create-once conflict: {path}") from exc
        return path
    with os.fdopen(fd, "wb") as handle:
        handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
    return path
def _artifacts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise QualifiedProdError("qualification artifacts are empty")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"platform", "ociRef", "digest"}:
            raise QualifiedProdError("artifact shape drifted")
        platform = _text(item.get("platform"), "artifact.platform")
        locator = _text(item.get("ociRef"), "artifact.ociRef")
        artifact_digest = _exact_digest(item.get("digest"), "artifact.digest")
        if platform in seen or not locator.endswith("@" + artifact_digest):
            raise QualifiedProdError("artifact must be one unique exact OCI @sha256 identity")
        seen.add(platform)
        result.append({"platform": platform, "ociRef": locator, "digest": artifact_digest})
    return sorted(result, key=lambda item: item["platform"])


def _factory_outputs(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise QualifiedProdError("CandidateMaterialManifest factoryOutputs are missing")
    if set(value) != {
        "service", "app", "qualificationRequestOciRef",
        "artifactBuildNumberAllocationOciRef",
    }:
        raise QualifiedProdError("CandidateMaterialManifest factoryOutputs shape drifted")
    result: dict[str, dict[str, Any]] = {}
    expected = {
        "service": {
            "ociRef", "ociDigest", "payloadDigest", "materialDigest",
            "serviceDigest", "prodRuntimeConfigDeploymentBundle",
        },
        "app": {
            "ociRef", "ociDigest", "payloadDigest", "materialDigest",
            "artifactDigests", "artifactManifests", "sourceTreeDigest",
        },
    }
    for kind, fields in expected.items():
        item = value.get(kind)
        if not isinstance(item, Mapping) or set(item) != fields:
            raise QualifiedProdError(f"{kind} factory output shape drifted")
        locator = _text(item.get("ociRef"), f"factoryOutputs.{kind}.ociRef")
        oci_digest = _exact_digest(
            item.get("ociDigest"), f"factoryOutputs.{kind}.ociDigest"
        )
        if not locator.endswith("@" + oci_digest):
            raise QualifiedProdError(f"{kind} factory OCI locator drifted")
        for field in ("payloadDigest", "materialDigest"):
            _exact_digest(item.get(field), f"factoryOutputs.{kind}.{field}")
        result[kind] = dict(item)
    for field in (
        "qualificationRequestOciRef", "artifactBuildNumberAllocationOciRef"
    ):
        locator = _text(value.get(field), f"factoryOutputs.{field}")
        if re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}", locator) is None:
            raise QualifiedProdError(f"factoryOutputs.{field} is not exact OCI")
    return result


def _factory_refs(outputs: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    return {
        kind: {
            "ociRef": str(outputs[kind]["ociRef"]),
            "ociDigest": str(outputs[kind]["ociDigest"]),
            "payloadDigest": str(outputs[kind]["payloadDigest"]),
            "materialDigest": str(outputs[kind]["materialDigest"]),
        }
        for kind in ("service", "app")
    }


def _validated_factory_actual_materials(
    *,
    root: Path,
    material: Mapping[str, Any],
    service_material_ref: Mapping[str, str],
    app_material_ref: Mapping[str, str],
    repository_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, str]]:
    """Re-run the qualification-owned actual-byte validators for formal Prod."""
    from quwoquan_ops.ci.release_qualification import (
        ReleaseQualificationError,
        _canonical_material,
        _validate_app_factory_material,
        _validate_hosted_allocation,
        _validate_service_factory_material,
    )

    outputs = _factory_outputs(material.get("factoryOutputs"))
    try:
        request, request_exact = _exact(
            root, material.get("qualificationRequest"), "qualificationRequest"
        )
        allocation, allocation_exact = _exact(
            root,
            material.get("artifactBuildNumberAllocation"),
            "artifactBuildNumberAllocation",
        )
        service_material, service_exact = _canonical_material(
            root, service_material_ref, "serviceFactoryMaterial"
        )
        app_material, app_exact = _canonical_material(
            root, app_material_ref, "appFactoryMaterial"
        )
        build_number = allocation.get("artifactBuildNumber")
        if type(build_number) is not int or build_number < 1:
            raise QualifiedProdError("factory allocation build number drifted")
        _validate_hosted_allocation(
            allocation=allocation,
            request=request,
            request_exact=request_exact,
            artifact_build_number=build_number,
        )
        request_locator = _text(
            material.get("qualificationRequestOciRef"),
            "qualificationRequestOciRef",
        )
        allocation_locator = _text(
            material.get("artifactBuildNumberAllocationOciRef"),
            "artifactBuildNumberAllocationOciRef",
        )
        service = _validate_service_factory_material(
            material=service_material,
            payload_exact=service_exact,
            locator=str(outputs["service"]["ociRef"]),
            locator_digest=str(outputs["service"]["ociDigest"]),
            request=request,
            request_exact=request_exact,
            request_locator=request_locator,
            request_transport_digest=request_locator.rsplit("@", 1)[-1],
            allocation=allocation,
            allocation_exact=allocation_exact,
            allocation_locator=allocation_locator,
            allocation_transport_digest=allocation_locator.rsplit("@", 1)[-1],
            repository_root=repository_root,
        )
        app = _validate_app_factory_material(
            material=app_material,
            payload_exact=app_exact,
            locator=str(outputs["app"]["ociRef"]),
            locator_digest=str(outputs["app"]["ociDigest"]),
            request=request,
            request_locator=request_locator,
            request_transport_digest=request_locator.rsplit("@", 1)[-1],
            allocation=allocation,
            allocation_locator=allocation_locator,
            allocation_transport_digest=allocation_locator.rsplit("@", 1)[-1],
        )
    except ReleaseQualificationError as exc:
        raise QualifiedProdError(f"factory actual material validation failed: {exc}") from exc
    if service != outputs["service"] or app != outputs["app"]:
        raise QualifiedProdError("factory actual material drifted from CandidateMaterialManifest")
    return service_material, app_material, service_exact, app_exact


def create_prod_activation_admission(
    *,
    root: Path,
    release_tag_admission_ref: Mapping[str, str],
    previous_active_released_ledger_ref: Mapping[str, str],
    rollback_readiness_ref: Mapping[str, str],
    control_plane_git_sha: str,
    admitted_at: str,
    service: str = "prod-stack",
) -> Path:
    """Admit Prod from stable -> Qualification -> CMM factory authority."""
    root = root.resolve()
    tag, tag_exact = _exact(root, release_tag_admission_ref, "releaseTagAdmission")
    qualification, qualification_exact = _exact(
        root, tag.get("qualificationFact"), "releaseTagAdmission.qualificationFact"
    )
    previous, previous_exact = _exact(
        root, previous_active_released_ledger_ref, "previousActiveReleasedLedger"
    )
    validate_prod_released_fact(previous)
    _, _, previous_receipt = _hosted_stage_readback(
        root,
        previous.get("hostedReceiptReadback"),
        service=service,
        field="previousActiveReleasedLedger.hostedReceiptReadback",
    )
    rollback, rollback_exact = _exact(root, rollback_readiness_ref, "rollbackReadiness")
    source = _sha(tag.get("peeledCommit"), "releaseTagAdmission.peeledCommit")
    control = _sha(control_plane_git_sha, "controlPlaneGitSha")
    tag_name = _text(tag.get("tagName"), "tagName")
    if (
        tag.get("schema") != "quwoquan_ops.release_tag_admission_fact.v1"
        or tag.get("decision") != "admitted"
        or tag.get("tagKind") != "stable"
        or _STABLE.fullmatch(tag_name) is None
    ):
        raise QualifiedProdError("Prod requires admitted stable SemVer tag")
    if (
        qualification.get("schema") != "quwoquan_ops.qualification_fact.v1"
        or qualification.get("decision") != "qualified"
        or qualification.get("sourceGitSha") != source
        or tag.get("qualificationFact") != qualification_exact
        or tag.get("qualificationId") != qualification.get("qualificationId")
    ):
        raise QualifiedProdError("qualification does not bind stable source")
    artifacts = _artifacts(tag.get("artifacts"))
    if artifacts != _artifacts(qualification.get("artifacts")):
        raise QualifiedProdError("tag and qualification exact OCI artifacts drifted")
    material, material_exact = _exact(
        root, tag.get("candidateMaterialManifest"), "candidateMaterialManifest"
    )
    outputs = _factory_outputs(material.get("factoryOutputs"))
    refs = _factory_refs(outputs)
    if (
        qualification.get("candidateMaterialManifest") != material_exact
        or tag.get("candidateMaterialManifest") != material_exact
        or tag.get("candidateMaterialId") != material.get("materialId")
        or qualification.get("sourceTree") != tag.get("sourceTree")
        or qualification.get("artifactBuildNumber") != tag.get("artifactBuildNumber")
        or qualification.get("artifactBuildNumber") != material.get("artifactBuildNumber")
        or material.get("sourceGitSha") != source
        or material.get("sourceTree") != tag.get("sourceTree")
        or _artifacts(material.get("artifacts")) != artifacts
        or outputs["service"]["ociRef"]
        != next(item["ociRef"] for item in artifacts if item["platform"] == "service")
        or any(
            item["ociRef"] != outputs["app"]["ociRef"]
            for item in artifacts if item["platform"] in {"android", "ios", "web"}
        )
    ):
        raise QualifiedProdError("stable material exact binding drifted")
    if (
        previous.get("schema") != "quwoquan_ops.prod_released_fact.v1"
        or previous.get("terminal") != "released"
        or previous.get("active") is not True
        or previous.get("revoked") is not False
        or previous.get("digestsExist") is not True
        or previous.get("compatible") is not True
        or previous_receipt.get("stage") != "100"
        or previous_receipt.get("triggerStage") != "100"
        or previous_receipt.get("decision") != "continue"
        or previous_receipt.get("rollbackOutcome") != "not_triggered"
        or previous_receipt.get("toCandidateDigest") != previous.get("candidateId")
        or previous_receipt.get("lastGoodCandidateDigest") != previous.get("candidateId")
    ):
        raise QualifiedProdError("previous active released ledger is invalid")
    previous_digests = sorted(
        {_exact_digest(value, "previous.ociDigest") for value in previous.get("ociDigests", [])}
    )
    if not previous_digests:
        raise QualifiedProdError("previous active released ledger has no exact digests")
    if (
        rollback.get("schema") != "quwoquan_ops.rollback_readiness_fact.v1"
        or rollback.get("status") != "ready"
        or rollback.get("previousActiveReleasedLedger") != previous_exact
        or sorted(rollback.get("ociDigests", [])) != previous_digests
        or rollback.get("digestsExist") is not True
        or rollback.get("compatible") is not True
    ):
        raise QualifiedProdError("rollback readiness is not exact")
    current_digests = sorted(
        {item["digest"] for item in artifacts}
        | {str(refs[kind]["ociDigest"]) for kind in refs}
        | {str(refs[kind]["materialDigest"]) for kind in refs}
    )
    body: dict[str, Any] = {
        "schema": "quwoquan_ops.prod_activation_admission_fact.v1",
        "decision": "admitted",
        "stableTag": tag_name,
        "tagObjectOid": _sha(tag.get("tagObjectOid"), "tagObjectOid"),
        "sourceGitSha": source,
        "sourceTree": _text(tag.get("sourceTree"), "sourceTree"),
        "controlPlaneGitSha": control,
        "releaseTagAdmission": tag_exact,
        "qualification": qualification_exact,
        "candidateMaterialManifest": material_exact,
        "factoryMaterials": refs,
        "previousActiveReleasedLedger": previous_exact,
        "rollbackReadiness": rollback_exact,
        "artifacts": artifacts,
        "ociDigests": current_digests,
        "previousOciDigests": previous_digests,
        "createdBeforeStage": "canary",
        "admittedAt": _text(admitted_at, "admittedAt"),
    }
    body["admissionId"] = digest(body)
    return _write_once(root / "prod" / "admissions" / f"{body['admissionId']}.json", body)


def materialize_prod_activation_input(
    *,
    root: Path,
    admission_ref: Mapping[str, str],
    service_material_ref: Mapping[str, str],
    app_material_ref: Mapping[str, str],
    output: Path,
    repository_root: Path | None = None,
) -> Path:
    """Write the only formal stackctl envelope after actual-byte validation."""
    root = root.resolve()
    repository_root = (
        Path(__file__).resolve().parents[2]
        if repository_root is None
        else repository_root.resolve()
    )
    admission, normalized = _exact(root, admission_ref, "admission")
    if (
        admission.get("schema") != "quwoquan_ops.prod_activation_admission_fact.v1"
        or admission.get("decision") != "admitted"
    ):
        raise QualifiedProdError("Prod admission is invalid")
    tag, _ = _exact(root, admission.get("releaseTagAdmission"), "releaseTagAdmission")
    _exact(root, admission.get("qualification"), "qualification")
    material, _ = _exact(
        root, admission.get("candidateMaterialManifest"), "candidateMaterialManifest"
    )
    previous, _ = _exact(
        root, admission.get("previousActiveReleasedLedger"), "previousActiveReleasedLedger"
    )
    service_material, app_material, service_exact, app_exact = (
        _validated_factory_actual_materials(
            root=root,
            material=material,
            service_material_ref=service_material_ref,
            app_material_ref=app_material_ref,
            repository_root=repository_root,
        )
    )
    outputs = _factory_outputs(material.get("factoryOutputs"))
    refs = _factory_refs(outputs)
    if admission.get("factoryMaterials") != refs:
        raise QualifiedProdError("Prod admission factory locator closure drifted")
    artifacts = _artifacts(admission.get("artifacts"))
    expected_digests = sorted(
        {item["digest"] for item in artifacts}
        | {str(refs[kind]["ociDigest"]) for kind in refs}
        | {str(refs[kind]["materialDigest"]) for kind in refs}
    )
    if sorted(admission.get("ociDigests") or []) != expected_digests:
        raise QualifiedProdError("Prod admission digest set drifted")
    payload = {
        "schema": "quwoquan_ops.prod_activation_input.v1",
        "prodActivationAdmission": normalized,
        "releaseTagAdmission": admission["releaseTagAdmission"],
        "qualification": admission["qualification"],
        "candidateMaterialManifest": admission["candidateMaterialManifest"],
        "serviceFactoryMaterial": {
            **refs["service"],
            "materializedManifest": service_exact,
        },
        "appFactoryMaterial": {
            **refs["app"],
            "materializedManifest": app_exact,
        },
        "previousReleased": admission["previousActiveReleasedLedger"],
        "rollbackReadiness": admission["rollbackReadiness"],
        "stableTag": admission["stableTag"],
        "sourceGitSha": admission["sourceGitSha"],
        "sourceTree": admission["sourceTree"],
        "controlPlaneGitSha": admission["controlPlaneGitSha"],
        "candidateMaterialId": _exact_digest(material.get("materialId"), "candidateMaterialId"),
        "previousReleasedId": _exact_digest(previous.get("releaseId"), "previousReleasedId"),
        "candidateDigest": _exact_digest(
            tag.get("candidateIdentity") or tag.get("candidateMaterialId"),
            "candidateIdentity",
        ),
        "previousCandidateDigest": _exact_digest(
            previous.get("candidateMaterialId") or previous.get("candidateId"),
            "previous.candidateMaterialId",
        ),
        "serviceMaterialDigest": service_material["materialDigest"],
        "appMaterialDigest": app_material["materialDigest"],
        "ociDigests": admission["ociDigests"],
        "previousOciDigests": admission["previousOciDigests"],
    }
    destination = output.expanduser()
    if destination.is_symlink():
        raise QualifiedProdError("Prod activation input output is unsafe")
    return _write_once(destination.resolve(), payload)


def _validated_exact_fact(
    root: Path,
    value: object,
    *,
    schema: str,
    field: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    fact, exact = _exact(root, value, field)
    validated = validate_prod_lifecycle_fact(fact)
    if validated["schema"] != schema:
        raise QualifiedProdError(f"{field} lifecycle schema is invalid")
    return validated, exact
def _hosted_stage_readback(
    root: Path,
    value: object,
    *,
    service: str,
    field: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    payload, exact = _exact(root, value, field)
    try:
        if (
            set(payload) != {"schema", "authority", "receipt", "receiptRef"}
            or payload.get("schema") != hosted_release_ledger.RECEIPT_READBACK_SCHEMA
            or payload.get("authority") != hosted_release_ledger.AUTHORITY
            or not isinstance(payload.get("receipt"), dict)
        ):
            raise ValueError("hosted receipt readback shape is invalid")
        receipt = payload["receipt"]
        if (
            set(receipt) != hosted_release_ledger.RECEIPT_FIELDS
            or receipt.get("schema") != hosted_release_ledger.RECEIPT_SCHEMA
            or receipt.get("authority") != hosted_release_ledger.AUTHORITY
            or receipt.get("service") != _text(service, "service")
            or receipt.get("receiptId") != hosted_release_ledger._receipt_id(receipt)
            or payload.get("receiptRef") != f"receipt:hosted:{receipt.get('receiptId')}"
        ):
            raise ValueError("hosted receipt identity is invalid")
        request = {
            key: receipt[key]
            for key in hosted_release_ledger.REQUEST_FIELDS
            if key != "schema"
        }
        request["schema"] = hosted_release_ledger.REQUEST_SCHEMA
        hosted_release_ledger._validate_request(request)
        if receipt.get("committedGeneration") != receipt.get("expectedGeneration") + 1:
            raise ValueError("hosted receipt generation is invalid")
    except (KeyError, TypeError, ValueError) as exc:
        raise QualifiedProdError(f"{field} is not a canonical hosted receipt readback") from exc
    return payload, exact, receipt
def _hosted_soak_readback(
    root: Path,
    value: object,
    *,
    service: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    payload, exact = _exact(root, value, "hostedSoakReadback")
    try:
        if (
            set(payload) != {"schema", "authority", "receipt", "receiptRef"}
            or payload.get("schema") != hosted_release_ledger.SOAK_RECEIPT_READBACK_SCHEMA
            or payload.get("authority") != hosted_release_ledger.AUTHORITY
            or not isinstance(payload.get("receipt"), dict)
        ):
            raise ValueError("hosted soak readback shape is invalid")
        receipt = payload["receipt"]
        if (
            set(receipt) != hosted_release_ledger.SOAK_RECEIPT_FIELDS
            or receipt.get("schema") != hosted_release_ledger.SOAK_RECEIPT_SCHEMA
            or receipt.get("authority") != hosted_release_ledger.AUTHORITY
            or receipt.get("service") != _text(service, "service")
            or receipt.get("receiptId") != hosted_release_ledger._receipt_id(receipt)
            or payload.get("receiptRef") != f"receipt:hosted-soak:{receipt.get('receiptId')}"
        ):
            raise ValueError("hosted soak receipt identity is invalid")
        request = {
            key: receipt[key]
            for key in hosted_release_ledger.SOAK_REQUEST_FIELDS
            if key != "schema"
        }
        request["schema"] = hosted_release_ledger.SOAK_REQUEST_SCHEMA
        hosted_release_ledger._validate_soak_request(request)
    except (KeyError, TypeError, ValueError) as exc:
        raise QualifiedProdError(
            "hostedSoakReadback is not a canonical hosted soak receipt readback"
        ) from exc
    return payload, exact, receipt
def _admission_candidate_bindings(
    root: Path, admission: Mapping[str, Any]
) -> tuple[str, str]:
    tag, _ = _exact(root, admission.get("releaseTagAdmission"), "releaseTagAdmission")
    previous, _ = _exact(
        root,
        admission.get("previousActiveReleasedLedger"),
        "previousActiveReleasedLedger",
    )
    validate_prod_released_fact(previous)
    candidate = _exact_digest(
        tag.get("candidateIdentity") or tag.get("candidateMaterialId"),
        "releaseTagAdmission.candidateIdentity",
    )
    previous_candidate = _exact_digest(
        previous.get("candidateId") or previous.get("candidateMaterialId"),
        "previousActiveReleasedLedger.candidateId",
    )
    if candidate == previous_candidate:
        raise QualifiedProdError("Prod candidate must differ from previous released identity")
    return candidate, previous_candidate
def _validate_stage_receipt_binding(
    *,
    receipt: Mapping[str, Any],
    stage: str,
    status: str,
    candidate: str,
    previous_candidate: str,
) -> None:
    if receipt.get("triggerStage") != stage:
        raise QualifiedProdError("hosted receipt trigger stage drifted")
    post_checks = receipt.get("postChecks")
    if not isinstance(post_checks, list) or not post_checks:
        raise QualifiedProdError("hosted receipt post-check evidence is incomplete")
    if status == "passed":
        if (
            receipt.get("stage") != stage
            or receipt.get("decision") != "continue"
            or receipt.get("rollbackOutcome") != "not_triggered"
            or receipt.get("toCandidateDigest") != candidate
            or receipt.get("lastGoodCandidateDigest") != candidate
            or any(item.get("status") != "passed" for item in post_checks)
        ):
            raise QualifiedProdError("passed stage is not supported by hosted receipt")
        return
    decision = receipt.get("decision")
    if decision == "rolled_back":
        valid = (
            receipt.get("stage") == "100"
            and receipt.get("rollbackOutcome") == "rolled_back"
            and receipt.get("fromCandidateDigest") == candidate
            and receipt.get("toCandidateDigest") == previous_candidate
            and receipt.get("lastGoodCandidateDigest") == previous_candidate
        )
    elif decision == "rollback_failed":
        valid = (
            receipt.get("stage") == stage
            and receipt.get("rollbackOutcome") == "rollback_failed"
            and receipt.get("toCandidateDigest") == candidate
            and receipt.get("lastGoodCandidateDigest") == previous_candidate
        )
    elif decision == "pause":
        valid = (
            receipt.get("stage") == stage
            and receipt.get("rollbackOutcome") == "not_triggered"
            and receipt.get("toCandidateDigest") == candidate
        )
    else:
        valid = False
    if not valid:
        raise QualifiedProdError("failed stage is not supported by hosted receipt")
def _attempts(
    root: Path, admission_id: str
) -> list[tuple[Path, dict[str, Any], dict[str, str]]]:
    result: list[tuple[Path, dict[str, Any], dict[str, str]]] = []
    directory = root / "prod" / "rollout" / admission_id
    for path in sorted(directory.rglob("*.json")) if directory.exists() else []:
        try:
            payload = json.loads(path.read_bytes())
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise QualifiedProdError(f"rollout attempt is invalid JSON: {path}") from exc
        if not isinstance(payload, Mapping):
            raise QualifiedProdError(f"rollout attempt must be an object: {path}")
        fact = validate_prod_stage_attempt_fact(payload)
        if path.stem != fact["attemptId"]:
            raise QualifiedProdError("rollout attempt path does not bind canonical self-ID")
        result.append(
            (
                path,
                fact,
                {"ref": path.relative_to(root).as_posix(), "digest": digest(path)},
            )
        )
    return sorted(
        result,
        key=lambda item: (str(item[1]["recordedAt"]), str(item[1]["attemptId"])),
    )
def _verify_evidence(
    root: Path,
    refs: Mapping[str, Mapping[str, str]],
    admission: Mapping[str, str],
    stage: str,
    status: str,
    kinds: tuple[str, ...],
    *,
    hosted_readback: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    if not isinstance(refs, Mapping) or set(refs) != set(kinds):
        raise QualifiedProdError("stage evidence set is incomplete")
    normalized: dict[str, dict[str, str]] = {}
    statuses: list[str] = []
    for kind in kinds:
        fact, exact = _exact(root, refs[kind], f"{stage}.{kind}")
        if (
            set(fact) != {"schema", "admission", "stage", "status", "source"}
            or fact.get("schema") != f"quwoquan_ops.prod_{kind}_evidence.v1"
            or fact.get("admission") != admission
            or fact.get("stage") != stage
            or fact.get("status") not in {"passed", "failed"}
        ):
            raise QualifiedProdError("stage evidence identity drifted")
        if kind == "readback" and (
            hosted_readback is None
            or fact.get("source") != dict(hosted_readback)
            or fact.get("status") != status
        ):
            raise QualifiedProdError("stage readback evidence is not hosted-authoritative")
        normalized[kind] = exact
        statuses.append(str(fact["status"]))
    if status == "passed" and statuses != ["passed"] * len(statuses):
        raise QualifiedProdError("passed stage has failed evidence")
    if status == "failed" and "failed" not in statuses:
        raise QualifiedProdError("failed stage has no failed evidence")
    return normalized
def append_prod_stage_attempt(
    *,
    root: Path,
    admission_ref: Mapping[str, str],
    stage: str,
    status: str,
    evidence_refs: Mapping[str, Mapping[str, str]],
    hosted_receipt_readback_ref: Mapping[str, str],
    predecessor_ref: Mapping[str, str] | None,
    recorded_at: str,
    service: str = "prod-stack",
) -> Path:
    root = root.resolve()
    admission, admission_exact = _exact(root, admission_ref, "admission")
    if (
        admission.get("schema") != "quwoquan_ops.prod_activation_admission_fact.v1"
        or admission.get("decision") != "admitted"
    ):
        raise QualifiedProdError("Prod admission is invalid")
    _exact(root, admission.get("releaseTagAdmission"), "releaseTagAdmission")
    _exact(root, admission.get("qualification"), "qualification")
    if stage not in _STAGES or status not in {"passed", "failed"}:
        raise QualifiedProdError("stage or status is invalid")
    hosted_payload, hosted_exact, receipt = _hosted_stage_readback(
        root,
        hosted_receipt_readback_ref,
        service=service,
        field="hostedReceiptReadback",
    )
    candidate, previous_candidate = _admission_candidate_bindings(root, admission)
    _validate_stage_receipt_binding(
        receipt=receipt,
        stage=stage,
        status=status,
        candidate=candidate,
        previous_candidate=previous_candidate,
    )
    authoritative_at = _authoritative_timestamp(
        recorded_at, receipt.get("verifiedAt"), "recordedAt"
    )
    attempts = _attempts(root, str(admission["admissionId"]))
    predecessor: dict[str, str] | None = None
    predecessor_fact: dict[str, Any] | None = None
    if predecessor_ref is not None:
        predecessor_fact, predecessor = _validated_exact_fact(
            root,
            predecessor_ref,
            schema="quwoquan_ops.prod_stage_attempt_fact.v1",
            field="predecessor",
        )
        if predecessor_fact.get("admission") != admission_exact:
            raise QualifiedProdError("predecessor admission drifted")
    if attempts:
        latest_payload, latest_exact = attempts[-1][1], attempts[-1][2]
        if predecessor != latest_exact or predecessor_fact != latest_payload:
            raise QualifiedProdError("predecessor is not the latest canonical append")
        _, _, predecessor_receipt = _hosted_stage_readback(
            root,
            latest_payload.get("hostedReceiptReadback"),
            service=service,
            field="predecessor.hostedReceiptReadback",
        )
        if receipt.get("expectedGeneration") != predecessor_receipt.get(
            "committedGeneration"
        ):
            raise QualifiedProdError("hosted receipt generation does not follow predecessor")
        if latest_payload["status"] == "failed":
            expected_stage = latest_payload["stage"]
        else:
            index = _STAGES.index(latest_payload["stage"])
            expected_stage = _STAGES[index + 1] if index + 1 < len(_STAGES) else None
    else:
        expected_stage = "canary"
        if predecessor is not None:
            raise QualifiedProdError("first stage cannot have predecessor")
        previous, _ = _exact(
            root,
            admission.get("previousActiveReleasedLedger"),
            "previousActiveReleasedLedger",
        )
        _, _, previous_receipt = _hosted_stage_readback(
            root,
            previous.get("hostedReceiptReadback"),
            service=service,
            field="previousActiveReleasedLedger.hostedReceiptReadback",
        )
        if receipt.get("expectedGeneration") != previous_receipt.get(
            "committedGeneration"
        ):
            raise QualifiedProdError("first hosted receipt does not follow released predecessor")
    if stage != expected_stage:
        raise QualifiedProdError("stage order is invalid")
    same_stage = [item for item in attempts if item[1]["stage"] == stage]
    normalized = _verify_evidence(
        root,
        evidence_refs,
        admission_exact,
        stage,
        status,
        _EVIDENCE,
        hosted_readback=hosted_payload,
    )
    body: dict[str, Any] = {"schema": "quwoquan_ops.prod_stage_attempt_fact.v1", "admission": admission_exact,
        "stage": stage, "attemptNumber": len(same_stage) + 1, "status": status,
        "predecessor": predecessor, "evidence": normalized,
        "hostedReceiptReadback": hosted_exact, "ociDigests": admission["ociDigests"],
        "recordedAt": authoritative_at,
    }
    body["attemptId"] = digest(body)
    validate_prod_stage_attempt_fact(body)
    return _write_once(
        root
        / "prod"
        / "rollout"
        / str(admission["admissionId"])
        / stage
        / f"{body['attemptId']}.json",
        body,
    )
def create_terminal_released_fact(
    *,
    root: Path,
    admission_ref: Mapping[str, str],
    final_attempt_ref: Mapping[str, str],
    hosted_receipt_readback_ref: Mapping[str, str],
    released_at: str,
    service: str = "prod-stack",
) -> Path:
    root = root.resolve()
    admission, admission_exact = _exact(root, admission_ref, "admission")
    final, final_exact = _validated_exact_fact(
        root,
        final_attempt_ref,
        schema="quwoquan_ops.prod_stage_attempt_fact.v1",
        field="finalAttempt",
    )
    hosted_payload, hosted_exact, receipt = _hosted_stage_readback(
        root,
        hosted_receipt_readback_ref,
        service=service,
        field="hostedReceiptReadback",
    )
    if final.get("hostedReceiptReadback") != hosted_exact:
        raise QualifiedProdError("final attempt does not bind supplied hosted readback")
    candidate, previous_candidate = _admission_candidate_bindings(root, admission)
    _validate_stage_receipt_binding(
        receipt=receipt,
        stage="100",
        status="passed",
        candidate=candidate,
        previous_candidate=previous_candidate,
    )
    if (
        final.get("admission") != admission_exact
        or final.get("stage") != "100"
        or final.get("status") != "passed"
    ):
        raise QualifiedProdError("released terminal requires passed 100 percent stage")
    attempts = _attempts(root, str(admission["admissionId"]))
    if not attempts or attempts[-1][2] != final_exact:
        raise QualifiedProdError("final attempt is not latest append")
    latest_pass = [item[1]["stage"] for item in attempts if item[1]["status"] == "passed"]
    if latest_pass != list(_STAGES):
        raise QualifiedProdError("rollout stages are incomplete")
    authoritative_at = _authoritative_timestamp(
        released_at, receipt.get("verifiedAt"), "releasedAt"
    )
    body: dict[str, Any] = {"schema": "quwoquan_ops.prod_released_fact.v1", "terminal": "released",
        "active": True, "revoked": False, "digestsExist": True, "compatible": True,
        "candidateId": candidate,
        "admission": admission_exact,
        "stableTag": admission["stableTag"],
        "sourceGitSha": admission["sourceGitSha"],
        "controlPlaneGitSha": admission["controlPlaneGitSha"],
        "ociDigests": admission["ociDigests"],
        "finalAttempt": final_exact,
        "hostedReceiptReadback": hosted_exact,
        "releasedAt": authoritative_at,
    }
    if hosted_payload.get("receipt") != receipt:
        raise QualifiedProdError("hosted released readback payload drifted")
    body["releaseId"] = digest(body)
    validate_prod_released_fact(body)
    return _write_once(root / "prod" / "released" / f"{body['releaseId']}.json", body)
def create_prod_rollback_fact(
    *,
    root: Path,
    admission_ref: Mapping[str, str],
    failed_attempt_ref: Mapping[str, str],
    evidence_refs: Mapping[str, Mapping[str, str]],
    hosted_receipt_readback_ref: Mapping[str, str],
    rolled_back_at: str,
    service: str = "prod-stack",
) -> Path:
    root = root.resolve()
    admission, admission_exact = _exact(root, admission_ref, "admission")
    failed, failed_exact = _validated_exact_fact(
        root,
        failed_attempt_ref,
        schema="quwoquan_ops.prod_stage_attempt_fact.v1",
        field="failedAttempt",
    )
    previous, previous_exact = _exact(
        root, admission.get("previousActiveReleasedLedger"), "previousReleased"
    )
    validate_prod_released_fact(previous)
    hosted_payload, hosted_exact, receipt = _hosted_stage_readback(
        root,
        hosted_receipt_readback_ref,
        service=service,
        field="hostedReceiptReadback",
    )
    if failed.get("hostedReceiptReadback") != hosted_exact:
        raise QualifiedProdError("failed attempt does not bind supplied hosted readback")
    candidate, previous_candidate = _admission_candidate_bindings(root, admission)
    _validate_stage_receipt_binding(
        receipt=receipt,
        stage=str(failed.get("stage")),
        status="failed",
        candidate=candidate,
        previous_candidate=previous_candidate,
    )
    if receipt.get("decision") != "rolled_back":
        raise QualifiedProdError("rollback fact requires hosted successful rollback receipt")
    if failed.get("admission") != admission_exact or failed.get("status") != "failed":
        raise QualifiedProdError("rollback requires a failed current attempt")
    attempts = _attempts(root, str(admission["admissionId"]))
    if not attempts or attempts[-1][2] != failed_exact:
        raise QualifiedProdError("failed attempt is not latest append")
    if not isinstance(evidence_refs, Mapping) or set(evidence_refs) != {
        "activation",
        "health",
        "readback",
    }:
        raise QualifiedProdError("rollback evidence set is incomplete")
    normalized: dict[str, dict[str, str]] = {}
    for kind in ("activation", "health", "readback"):
        fact, normalized[kind] = _exact(root, evidence_refs[kind], f"rollback.{kind}")
        if (
            set(fact) != {"schema", "admission", "stage", "status", "rollbackTarget", "ociDigests", "source"}
            or fact.get("schema")
            != f"quwoquan_ops.prod_rollback_{kind}_evidence.v1"
            or fact.get("admission") != admission_exact
            or fact.get("stage") != failed["stage"]
            or fact.get("status") != "passed"
            or fact.get("rollbackTarget") != previous_exact
            or sorted(fact.get("ociDigests", []))
            != sorted(previous.get("ociDigests", []))
        ):
            raise QualifiedProdError(
                "rollback evidence does not bind previous released identity"
            )
        if kind == "readback" and fact.get("source") != hosted_payload:
            raise QualifiedProdError("rollback readback evidence is not hosted-authoritative")
    authoritative_at = _authoritative_timestamp(
        rolled_back_at, receipt.get("verifiedAt"), "rolledBackAt"
    )
    body: dict[str, Any] = {"schema": "quwoquan_ops.prod_rollback_fact.v1", "terminal": "rolled_back",
        "admission": admission_exact, "failedAttempt": failed_exact,
        "rollbackTarget": previous_exact, "ociDigests": sorted(previous["ociDigests"]),
        "evidence": normalized, "hostedReceiptReadback": hosted_exact,
        "builderInvocationCount": 0, "tagMutation": False, "rolledBackAt": authoritative_at,
    }
    body["rollbackId"] = digest(body)
    validate_prod_rollback_fact(body)
    return _write_once(root / "prod" / "rollbacks" / f"{body['rollbackId']}.json", body)
@lru_cache(maxsize=1)
def _canonical_soak_policy() -> tuple[dict[str, Any], str]:
    try:
        policy = yaml.safe_load(_SOAK_POLICY.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise QualifiedProdError("canonical soak policy is unavailable") from exc
    if (
        not isinstance(policy, dict)
        or not isinstance(policy.get("readback"), dict)
        or not isinstance(policy.get("thresholds"), dict)
    ):
        raise QualifiedProdError("canonical soak policy is invalid")
    return policy, digest(_SOAK_POLICY)
def _finite_number(value: object, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise QualifiedProdError(f"{field} is not numeric")
    number = float(value)
    if not math.isfinite(number):
        raise QualifiedProdError(f"{field} is not finite")
    return number
def _validate_soak_policy_receipt(receipt: Mapping[str, Any]) -> dict[str, float]:
    policy, policy_digest = _canonical_soak_policy()
    readback = policy["readback"]
    required = _window_seconds(readback.get("post_100_soak_window"))
    minimum_samples = int(readback.get("minimum_samples") or 0)
    if (
        receipt.get("soakPolicyDigest") != policy_digest
        or receipt.get("requiredSoakSeconds") != required
        or receipt.get("soakDurationSeconds", 0) < required
    ):
        raise QualifiedProdError("hosted soak receipt does not bind canonical window policy")
    slo = receipt.get("slo")
    if not isinstance(slo, Mapping):
        raise QualifiedProdError("hosted soak SLO aggregate is missing")
    if (
        slo.get("windowSeconds") != required
        or slo.get("minimumSamples") != minimum_samples
        or not isinstance(slo.get("sampleCount"), int)
        or isinstance(slo.get("sampleCount"), bool)
        or slo["sampleCount"] < minimum_samples
        or slo.get("status") != "passed"
        or slo.get("decision") != "continue"
    ):
        raise QualifiedProdError("hosted soak SLO aggregate is incomplete")
    values = slo.get("values")
    if not isinstance(values, Mapping) or set(values) != {
        "errorRate",
        "p95Ms",
        "redisErrorRate",
    }:
        raise QualifiedProdError("hosted soak SLO values are incomplete")
    normalized = {field: _finite_number(values[field], f"slo.values.{field}") for field in values}
    if not (0.0 <= normalized["errorRate"] <= 1.0) or not (
        0.0 <= normalized["redisErrorRate"] <= 1.0
    ):
        raise QualifiedProdError("hosted soak failure ratios are outside [0,1]")
    bindings = {
        "errorRate": "error_rate",
        "p95Ms": "p95_ms",
        "redisErrorRate": "redis_error_rate",
    }
    for field, policy_field in bindings.items():
        threshold = policy["thresholds"].get(policy_field)
        limit = threshold.get("warn") if isinstance(threshold, Mapping) else None
        if (
            not isinstance(limit, (int, float))
            or isinstance(limit, bool)
            or normalized[field] >= float(limit)
        ):
            raise QualifiedProdError(f"hosted soak breached {policy_field} threshold")
    return normalized
def _validate_soak_observation(
    *,
    kind: str,
    fact: Mapping[str, Any],
    release_exact: Mapping[str, str],
    hosted_evidence: Mapping[str, Any],
    slo_values: Mapping[str, float],
) -> None:
    expected_fields = {"schema", "release", "status", "readOnly", "observedAt", "sourceDigest", "source"}
    if (
        set(fact) != expected_fields
        or fact.get("schema") != f"quwoquan_ops.prod_soak_{kind}_observation.v1"
        or fact.get("release") != release_exact
        or fact.get("readOnly") is not True
        or fact.get("status") != "passed"
        or fact.get("observedAt") != hosted_evidence.get("observedAt")
        or fact.get("sourceDigest") != hosted_evidence.get("receiptDigest")
        or not isinstance(fact.get("source"), Mapping)
    ):
        raise QualifiedProdError(f"soak {kind} observation identity is incomplete")
    source = fact["source"]
    if kind == "slo":
        source_values = source.get("values")
        if (
            source.get("source") != "prometheus"
            or source.get("queriedAt") != hosted_evidence.get("observedAt")
            or not isinstance(source_values, Mapping)
            or int(_finite_number(source_values.get("sampleCount"), "slo.sampleCount"))
            != hosted_evidence.get("sampleCount")
            or any(
                _finite_number(source_values.get(field), f"slo.{field}") != slo_values[field]
                for field in slo_values
            )
        ):
            raise QualifiedProdError("soak SLO observation aggregate drifted")
    elif kind == "alerts":
        if (
            source.get("schema") != "prod-alertmanager-soak-observation"
            or source.get("source") != "alertmanager"
            or source.get("queriedAt") != hosted_evidence.get("observedAt")
            or source.get("status") != "passed"
            or source.get("activeFiring") != 0
        ):
            raise QualifiedProdError("soak alerts observation is not clear")
    elif kind == "health":
        checks = source.get("checks")
        if (
            source.get("command") != "health"
            or source.get("target") != "prod-hosted"
            or source.get("scope") != "full"
            or source.get("timestamp") != hosted_evidence.get("observedAt")
            or source.get("findings") != []
            or not isinstance(checks, list)
            or not checks
            or any(not isinstance(check, Mapping) or check.get("ok") is not True for check in checks)
        ):
            raise QualifiedProdError("soak health observation did not pass")
def create_post_release_soak_fact(
    *,
    root: Path,
    released_fact_ref: Mapping[str, str],
    observation_refs: Mapping[str, Mapping[str, str]],
    hosted_soak_readback_ref: Mapping[str, str],
    status: str,
    observed_at: str,
    service: str = "prod-stack",
) -> Path:
    root = root.resolve()
    released, released_exact = _validated_exact_fact(
        root,
        released_fact_ref,
        schema="quwoquan_ops.prod_released_fact.v1",
        field="releasedFact",
    )
    _, hosted_exact, receipt = _hosted_soak_readback(
        root, hosted_soak_readback_ref, service=service
    )
    if status != "passed":
        raise QualifiedProdError("failed soak cannot create an accepted lifecycle fact")
    if released.get("terminal") != "released":
        raise QualifiedProdError("soak requires terminal released fact")
    final_payload, _, final_receipt = _hosted_stage_readback(
        root,
        released.get("hostedReceiptReadback"),
        service=service,
        field="releasedFact.hostedReceiptReadback",
    )
    if (
        receipt.get("fullRolloutReceiptId") != final_receipt.get("receiptId")
        or receipt.get("candidateId") != released.get("candidateId")
        or receipt.get("candidateMaterialId") != final_receipt.get("candidateMaterialId")
        or receipt.get("prodActivationAdmissionRef") != final_receipt.get("prodActivationAdmissionRef")
        or receipt.get("prodActivationAdmissionOciDigest") != final_receipt.get("prodActivationAdmissionOciDigest")
        or receipt.get("prodActivationAdmissionPayloadDigest") != final_receipt.get("prodActivationAdmissionPayloadDigest")
        or receipt.get("prodActivationAdmissionId") != final_receipt.get("prodActivationAdmissionId")
        or receipt.get("candidateMaterialManifestRef") != final_receipt.get("candidateMaterialManifestRef")
        or receipt.get("candidateMaterialManifestOciDigest") != final_receipt.get("candidateMaterialManifestOciDigest")
        or receipt.get("candidateMaterialManifestPayloadDigest") != final_receipt.get("candidateMaterialManifestPayloadDigest")
        or receipt.get("serviceFactoryOciDigest") != final_receipt.get("toServiceFactoryOciDigest")
        or receipt.get("appFactoryOciDigest") != final_receipt.get("toAppFactoryOciDigest")
        or not str(receipt.get("releasedRef") or "").endswith("@" + released_exact.get("digest", ""))
        or receipt.get("releasedPayloadDigest") != released_exact.get("digest")
        or receipt.get("releasedId") != released.get("releaseId")
        or final_receipt.get("toCandidateDigest") != released.get("candidateId")
    ):
        raise QualifiedProdError("hosted soak receipt does not bind released terminal authority")
    if not isinstance(observation_refs, Mapping) or set(observation_refs) != {"health", "slo", "alerts"}:
        raise QualifiedProdError("soak observation set is incomplete")
    slo_values = _validate_soak_policy_receipt(receipt)
    normalized: dict[str, dict[str, str]] = {}
    statuses: list[str] = []
    for kind in ("health", "slo", "alerts"):
        fact, normalized[kind] = _exact(root, observation_refs[kind], kind)
        hosted_evidence = receipt.get(kind)
        if not isinstance(hosted_evidence, Mapping):
            raise QualifiedProdError(f"hosted soak {kind} evidence is missing")
        _validate_soak_observation(
            kind=kind,
            fact=fact,
            release_exact=released_exact,
            hosted_evidence=hosted_evidence,
            slo_values=slo_values,
        )
        statuses.append(str(fact["status"]))
    failed_count = sum(item != "passed" for item in statuses)
    passed_count = len(statuses) - failed_count
    success_ratio = passed_count / len(statuses)
    failure_ratio = failed_count / len(statuses)
    hosted_statuses = [receipt.get(kind, {}).get("status") for kind in ("health", "slo", "alerts") if isinstance(receipt.get(kind), Mapping)]
    if failed_count != 0 or success_ratio != 1.0 or failure_ratio != 0.0 or hosted_statuses != ["passed"] * 3:
        raise QualifiedProdError("soak aggregate did not pass completely")
    authoritative_at = _authoritative_timestamp(
        observed_at, receipt.get("verifiedAt"), "observedAt"
    )
    started_at, started = _timestamp(receipt.get("soakStartedAt"), "soakStartedAt")
    ended_at, ended = _timestamp(receipt.get("soakEndedAt"), "soakEndedAt")
    observed_seconds = int((ended - started).total_seconds())
    if observed_seconds != receipt.get("soakDurationSeconds"):
        raise QualifiedProdError("hosted soak window duration drifted")
    window = {
        "startedAt": started_at, "endedAt": ended_at,
        "requiredSeconds": receipt["requiredSoakSeconds"], "observedSeconds": observed_seconds,
        "complete": observed_seconds >= receipt["requiredSoakSeconds"],
    }
    aggregate = {
        "status": "passed", "complete": True, "observationCount": len(statuses),
        "passedCount": passed_count, "failedCount": failed_count,
        "successRatio": success_ratio, "failureRatio": failure_ratio,
        "requestSuccessRatio": 1.0 - slo_values["errorRate"],
        "requestFailureRatio": slo_values["errorRate"], "window": window,
    }
    if aggregate["window"]["complete"] is not True:
        raise QualifiedProdError("soak aggregate window is incomplete")
    if final_payload.get("receipt") != final_receipt:
        raise QualifiedProdError("released hosted readback payload drifted")
    body: dict[str, Any] = {"schema": "quwoquan_ops.post_release_soak_fact.v1", "releasedFact": released_exact,
        "status": "passed", "readOnly": True, "hostedSoakReadback": hosted_exact,
        "observations": normalized, "aggregate": aggregate, "observedAt": authoritative_at,
    }
    body["soakId"] = digest(body)
    validate_post_release_soak_fact(body)
    return _write_once(root / "prod" / "soak" / f"{body['soakId']}.json", body)
