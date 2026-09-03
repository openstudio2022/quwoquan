"""Evidence-specific validators for environment acceptance facts."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    _FINALIZATION_KEYS,
    _PROD_FACT_KEYS,
    PROD_ROLLOUT_STAGES,
)

_M1_HEALTH_SCHEMA = "qwq.content_api_consumer.health_binding.v1"
_M1_OBSERVATION_SCHEMA = "qwq.content_api_consumer.observation.v1"
_M1_REQUIRED_HEALTH_LAYERS = (
    "build_ready",
    "runtime_full_ready",
    "release_active",
    "content_exact_queries_ready",
)


def _verify_common_evidence(
    root: Path,
    value: object,
    *,
    label: str,
    allowed_statuses: set[str],
    identity: dict[str, str],
    normalize_exact_ref: Callable[..., dict[str, str]],
    load_exact: Callable[..., tuple[dict[str, Any], bytes]],
    require_evidence_identity: Callable[..., None],
    require_status: Callable[..., None],
) -> dict[str, Any]:
    exact = normalize_exact_ref(value, label=label)
    payload, _ = load_exact(root, exact, label=label)
    require_evidence_identity(payload, label=label, **identity)
    require_status(payload, label=label, allowed=allowed_statuses)
    return payload


def _verify_m1_consumer_health(
    root: Path,
    value: object,
    *,
    identity: dict[str, str],
    manifest_digest: str,
    data_readiness: Mapping[str, str],
    normalize_exact_ref: Callable[..., dict[str, str]],
    load_exact: Callable[..., tuple[dict[str, Any], bytes]],
    text: Callable[..., str],
    digest: Callable[..., str],
    block: Callable[[str, str], None],
    evidence_code: str,
) -> dict[str, Any]:
    exact = normalize_exact_ref(value, label="consumerHealth")
    binding, _ = load_exact(root, exact, label="consumerHealth")
    expected_keys = {
        "schema",
        "status",
        "environment",
        "deploymentTarget",
        "releaseId",
        "releaseDigest",
        "manifestDigest",
        "importRunId",
        "verifyRunId",
        "sourceHealth",
        "requiredLayers",
    }
    if set(binding) != expected_keys or binding.get("schema") != _M1_HEALTH_SCHEMA:
        block(evidence_code, "consumerHealth binding schema/fields drifted")
    expected_identity = {
        "status": "passed",
        "environment": identity["environment"],
        "deploymentTarget": identity["target"],
        "releaseId": identity["release_id"],
        "releaseDigest": identity["release_digest"],
        "manifestDigest": manifest_digest,
        "importRunId": identity["import_run_id"],
        "verifyRunId": identity["verify_run_id"],
    }
    for field, expected in expected_identity.items():
        if binding.get(field) != expected:
            block(evidence_code, f"consumerHealth binding identity drifted at {field}")
    if binding.get("requiredLayers") != list(_M1_REQUIRED_HEALTH_LAYERS):
        block(evidence_code, "consumerHealth required layers drifted")

    source = normalize_exact_ref(
        binding.get("sourceHealth"), label="consumerHealth.sourceHealth"
    )
    health, _ = load_exact(root, source, label="consumerHealth.sourceHealth")
    expected_health = {
        "command": "health",
        "target": identity["target"],
        "scope": "content-consumer",
    }
    for field, expected in expected_health.items():
        if health.get(field) != expected:
            block(evidence_code, f"source content-consumer health drifted at {field}")
    if health.get("findings") != [] or health.get("generationIssues") not in (None, []):
        block(evidence_code, "source content-consumer health contains findings")
    checks = health.get("checks")
    executed = (
        [
            row
            for row in checks
            if isinstance(row, Mapping) and not bool(row.get("skipped"))
        ]
        if isinstance(checks, list)
        else []
    )
    if not executed or any(row.get("ok") is not True for row in executed):
        block(evidence_code, "source content-consumer health checks are not healthy")
    layers = health.get("userAvailability")
    if not isinstance(layers, list):
        block(evidence_code, "source content-consumer health availability is missing")
    by_name = {
        str(row.get("name") or ""): row for row in layers if isinstance(row, Mapping)
    }
    if any(
        by_name.get(name, {}).get("status") != "ready"
        for name in _M1_REQUIRED_HEALTH_LAYERS
    ):
        block(evidence_code, "source content-consumer health required layers are blocked")
    report = health.get("userAvailabilityReport")
    evidence = report.get("evidence") if isinstance(report, Mapping) else None
    content = evidence.get("content") if isinstance(evidence, Mapping) else None
    if not isinstance(content, Mapping):
        block(evidence_code, "source content-consumer health content evidence is missing")
    expected_content = {
        "releaseId": identity["release_id"],
        "manifestDigest": manifest_digest,
        "readinessReceiptRef": data_readiness["ref"],
        "readinessReceiptDigest": data_readiness["digest"],
        "releaseActive": True,
        "exactQueriesReady": True,
        "generationMatch": True,
    }
    for field, expected in expected_content.items():
        if content.get(field) != expected:
            block(
                evidence_code,
                f"source content-consumer health content drifted at {field}",
            )
    optional_identity = {
        "environment": identity["environment"],
        "deploymentTarget": identity["target"],
        "releaseId": identity["release_id"],
        "releaseDigest": identity["release_digest"],
        "manifestDigest": manifest_digest,
        "importRunId": identity["import_run_id"],
        "verifyRunId": identity["verify_run_id"],
    }
    for field, expected in optional_identity.items():
        if field in health and health.get(field) != expected:
            block(
                evidence_code,
                f"source content-consumer health identity drifted at {field}",
            )
    return binding


def _validate_m1_observation_payload(
    observation: Mapping[str, Any],
    *,
    raw_result: Mapping[str, Any],
    label: str,
    sample_id: str,
    manifest_digest: str,
    identity: Callable[..., str],
    digest: Callable[..., str],
    block: Callable[[str, str], None],
    evidence_code: str,
) -> dict[str, Any]:
    expected_keys = {
        "schema",
        "sampleId",
        "entrySurface",
        "carrier",
        "objectId",
        "runtimeObjectId",
        "releaseId",
        "releaseDigest",
        "manifestDigest",
        "importRunId",
        "verifyRunId",
        "status",
        "startedAt",
        "completedAt",
        "http",
        "assertion",
    }
    if (
        set(observation) != expected_keys
        or observation.get("schema") != _M1_OBSERVATION_SCHEMA
    ):
        block(evidence_code, f"{label} observation schema/fields drifted")
    expected = {
        "sampleId": sample_id,
        "entrySurface": raw_result.get("entrySurface"),
        "carrier": raw_result.get("carrier"),
        "objectId": raw_result.get("objectId"),
        "releaseId": raw_result.get("releaseId"),
        "releaseDigest": raw_result.get("releaseDigest"),
        "manifestDigest": manifest_digest,
        "importRunId": raw_result.get("importRunId"),
        "verifyRunId": raw_result.get("verifyRunId"),
        "status": raw_result.get("status"),
        "startedAt": raw_result.get("startedAt"),
        "completedAt": raw_result.get("completedAt"),
    }
    for field, value in expected.items():
        if observation.get(field) != value:
            block(evidence_code, f"{label} observation identity drifted at {field}")
    runtime_object_id = identity(
        observation.get("runtimeObjectId"),
        field=f"{label}.observation.runtimeObjectId",
    )
    assertion = observation.get("assertion")
    if not isinstance(assertion, Mapping):
        block(evidence_code, f"{label} observation assertion is invalid")
    status = observation.get("status")
    http = observation.get("http")
    if status == "passed":
        if not isinstance(http, Mapping):
            block(evidence_code, f"{label} passed observation requires HTTP facts")
        http_status = http.get("status")
        if (
            isinstance(http_status, bool)
            or not isinstance(http_status, int)
            or not 200 <= http_status < 300
        ):
            block(evidence_code, f"{label} passed observation HTTP status is not 2xx")
        digest(
            http.get("responseSha256"),
            field=f"{label}.observation.http.responseSha256",
        )
        if assertion.get("matchedRuntimeObjectId") != runtime_object_id:
            block(evidence_code, f"{label} observation runtimeObjectId did not match")
    elif status in {"failed", "blocked"}:
        if http is not None and not isinstance(http, Mapping):
            block(evidence_code, f"{label} non-passed observation HTTP facts are invalid")
        if isinstance(http, Mapping):
            http_status = http.get("status")
            if isinstance(http_status, bool) or not isinstance(http_status, int):
                block(
                    evidence_code,
                    f"{label} non-passed observation HTTP status is invalid",
                )
            digest(
                http.get("responseSha256"),
                field=f"{label}.observation.http.responseSha256",
            )
    else:
        block(evidence_code, f"{label} observation status is invalid")
    return dict(observation)


def _verify_m1_observation(
    root: Path,
    raw_result: Mapping[str, Any],
    *,
    label: str,
    sample_id: str,
    manifest_digest: str,
    relative_ref: Callable[..., str],
    text: Callable[..., str],
    secure_read: Callable[..., bytes],
    decode_json: Callable[..., dict[str, Any]],
    identity: Callable[..., str],
    digest: Callable[..., str],
    block: Callable[[str, str], None],
    evidence_code: str,
) -> dict[str, Any]:
    artifact_ref = relative_ref(
        raw_result.get("artifactPath"), field=f"{label}.artifactPath"
    )
    artifact_sha = text(
        raw_result.get("artifactSha256"), field=f"{label}.artifactSha256"
    )
    if re.fullmatch(r"[0-9a-f]{64}", artifact_sha) is None:
        block(evidence_code, f"{label}.artifactSha256 must be 64 lowercase hex")
    observation_raw = secure_read(root, artifact_ref, label=f"{label}.observation")
    observed_sha = hashlib.sha256(observation_raw).hexdigest()
    if observed_sha != artifact_sha:
        block(evidence_code, f"{label} observation exact bytes drifted")
    observation = decode_json(observation_raw, label=f"{label}.observation")
    return _validate_m1_observation_payload(
        observation,
        raw_result=raw_result,
        label=label,
        sample_id=sample_id,
        manifest_digest=manifest_digest,
        identity=identity,
        digest=digest,
        block=block,
        evidence_code=evidence_code,
    )


def _validate_finalization(
    root: Path,
    value: object,
    *,
    identity: dict[str, str],
    verify_references: bool,
    normalize_exact_ref: Callable[..., dict[str, str]],
    verify_common_evidence: Callable[..., dict[str, Any]],
    block: Callable[[str, str], None],
    invalid_code: str,
) -> dict[str, list[dict[str, str]]]:
    if not isinstance(value, Mapping) or set(value) != _FINALIZATION_KEYS:
        block(invalid_code, "resourceFinalization fields are invalid")
    statuses = {
        "leaseRevocationRefs": {"revoked"},
        "lockReleaseRefs": {"released"},
        "gcProtectionRefs": {"protected", "ready", "passed"},
    }
    result: dict[str, list[dict[str, str]]] = {}
    for field, allowed in statuses.items():
        items = value.get(field)
        if not isinstance(items, list) or not items:
            block(invalid_code, f"resourceFinalization.{field} must be non-empty")
        seen: set[str] = set()
        normalized: list[dict[str, str]] = []
        for index, item in enumerate(items):
            label = f"resourceFinalization.{field}[{index}]"
            exact = normalize_exact_ref(item, label=label)
            if exact["ref"] in seen:
                block(
                    invalid_code,
                    f"resourceFinalization.{field} contains duplicate refs",
                )
            seen.add(exact["ref"])
            normalized.append(exact)
            if verify_references:
                verify_common_evidence(
                    root,
                    exact,
                    label=label,
                    allowed_statuses=allowed,
                    identity=identity,
                )
        result[field] = normalized
    return result


def _validate_prod_facts(
    root: Path,
    value: object,
    *,
    environment: str,
    identity: dict[str, str],
    verify_references: bool,
    normalize_exact_ref: Callable[..., dict[str, str]],
    verify_common_evidence: Callable[..., dict[str, Any]],
    block: Callable[[str, str], None],
    invalid_code: str,
    evidence_code: str,
) -> dict[str, Any] | None:
    if environment != "prod":
        if value is not None:
            block(invalid_code, "non-prod fact must have prodReleaseFacts=null")
        return None
    if not isinstance(value, Mapping) or set(value) != _PROD_FACT_KEYS:
        block(invalid_code, "prod requires the closed canonical prodReleaseFacts set")
    result: dict[str, Any] = {
        "engineeringEligibility": normalize_exact_ref(
            value.get("engineeringEligibility"),
            label="prodReleaseFacts.engineeringEligibility",
        ),
        "durableApproval": normalize_exact_ref(
            value.get("durableApproval"), label="prodReleaseFacts.durableApproval"
        ),
        "rollbackReadiness": normalize_exact_ref(
            value.get("rollbackReadiness"), label="prodReleaseFacts.rollbackReadiness"
        ),
    }
    stages = value.get("rolloutStages")
    if not isinstance(stages, list) or len(stages) != len(PROD_ROLLOUT_STAGES):
        block(invalid_code, "prod rolloutStages must contain canary/5/20/50/100")
    normalized_stages: list[dict[str, str]] = []
    for expected, item in zip(PROD_ROLLOUT_STAGES, stages, strict=True):
        if not isinstance(item, Mapping) or set(item) != {"stage", "ref", "digest"}:
            block(invalid_code, "prod rollout stage fields are invalid")
        if item.get("stage") != expected:
            block(invalid_code, f"prod rollout stage order requires {expected}")
        exact = normalize_exact_ref(
            {"ref": item.get("ref"), "digest": item.get("digest")},
            label=f"prodReleaseFacts.rolloutStages[{expected}]",
        )
        normalized_stages.append({"stage": expected, **exact})
    result["rolloutStages"] = normalized_stages
    if verify_references:
        role_specs = (
            (
                "engineeringEligibility",
                "engineeringEligibility",
                {"eligible", "passed", "ready"},
            ),
            ("durableApproval", "durableApproval", {"approved", "passed"}),
            ("rollbackReadiness", "rollbackReadiness", {"ready", "passed"}),
        )
        for field, role, statuses in role_specs:
            payload = verify_common_evidence(
                root,
                result[field],
                label=f"prodReleaseFacts.{field}",
                allowed_statuses=statuses,
                identity=identity,
            )
            if payload.get("factType") != role:
                block(evidence_code, f"prodReleaseFacts.{field} has the wrong factType")
        for stage in normalized_stages:
            payload = verify_common_evidence(
                root,
                {"ref": stage["ref"], "digest": stage["digest"]},
                label=f"prodReleaseFacts.rolloutStages[{stage['stage']}]",
                allowed_statuses={"passed", "completed", "continue"},
                identity=identity,
            )
            if (
                payload.get("factType") != "rolloutStage"
                or payload.get("stage") != stage["stage"]
            ):
                block(evidence_code, "prod rollout fact role or stage drifted")
    return result

__all__ = [
    "_M1_HEALTH_SCHEMA",
    "_M1_OBSERVATION_SCHEMA",
    "_M1_REQUIRED_HEALTH_LAYERS",
    "_validate_finalization",
    "_validate_prod_facts",
    "_verify_common_evidence",
    "_verify_m1_consumer_health",
    "_verify_m1_observation",
]
