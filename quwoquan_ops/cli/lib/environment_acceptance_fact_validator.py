"""Core validation flow for environment acceptance facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
    _ACTIVE_CAS_KEYS,
    _CARRIERS,
    _DEVICE_PROFILES,
    _FACT_KEYS_BY_PROFILE,
    _PLATFORMS,
    _RAW_RESULT_KEYS,
    _TARGET_BINDING_KEYS,
    ACCEPTANCE_PROFILES,
    ENVIRONMENTS,
    SCHEMA,
)
from quwoquan_ops.cli.lib.readiness_case_result import (
    ReadinessCaseResultError,
    validate_readiness_case_result,
)
from quwoquan_ops.cli.lib.target_uat_binding import (
    TargetUatBindingError,
    validate_target_uat_binding,
)


def validate_environment_acceptance_fact(
    payload: Mapping[str, Any],
    *,
    evidence_root: Path,
    required_target_profiles: Sequence[Mapping[str, str]],
    verify_references: bool = True,
    invalid_code: str,
    evidence_code: str,
    error_type: type[ValueError],
    block: Callable[[str, str], None],
    text: Callable[..., str],
    identity_value: Callable[..., str],
    digest: Callable[..., str],
    timestamp: Callable[..., str],
    relative_ref: Callable[..., str],
    normalize_profiles: Callable[..., set[tuple[str, str]]],
    absolute_real_root: Callable[..., Path],
    secure_read: Callable[..., bytes],
    exact_byte_digest: Callable[[bytes | Path], str],
    decode_json: Callable[..., dict[str, Any]],
    required_plan_cells: Callable[..., dict[tuple[str, str, str, str], dict[str, str]]],
    normalize_exact_ref: Callable[..., dict[str, str]],
    load_exact: Callable[..., tuple[dict[str, Any], bytes]],
    binding_device_profile: Callable[[Mapping[str, Any]], str],
    require_evidence_identity: Callable[..., None],
    verify_m1_observation: Callable[..., dict[str, Any]],
    required_raw_slot_id: Callable[..., str],
    verify_m1_consumer_health: Callable[..., dict[str, Any]],
    derive_m1_source_fingerprint: Callable[..., str],
    derive_fact_id: Callable[[Mapping[str, Any]], str],
    verify_common_evidence: Callable[..., dict[str, Any]],
    validate_finalization: Callable[..., dict[str, list[dict[str, str]]]],
    validate_prod_facts: Callable[..., dict[str, Any] | None],
    validate_predecessor_acceptance: Callable[..., dict[str, str] | None],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        block(invalid_code, "environment acceptance fact must be an object")
    fact = dict(payload)
    if fact.get("schema") != SCHEMA:
        block(invalid_code, "schema is not EnvironmentAcceptanceFact v1")
    acceptance_profile = text(fact.get("acceptanceProfile"), field="acceptanceProfile")
    if acceptance_profile not in ACCEPTANCE_PROFILES:
        block(invalid_code, "acceptanceProfile is unknown")
    if set(fact) != _FACT_KEYS_BY_PROFILE[acceptance_profile]:
        block(
            invalid_code,
            f"{acceptance_profile} environment acceptance fact fields are invalid",
        )
    fact_id = digest(fact.get("factId"), field="factId")
    environment = text(fact.get("environment"), field="environment")
    if environment not in ENVIRONMENTS:
        block(invalid_code, "environment is unknown")
    target = identity_value(fact.get("target"), field="target")
    if acceptance_profile == "m1_api_consumer" and (
        environment != "alpha" or target != "alpha-local"
    ):
        block(
            invalid_code, "m1_api_consumer requires environment=alpha,target=alpha-local"
        )
    release_id = identity_value(fact.get("releaseId"), field="releaseId")
    release_digest = digest(fact.get("releaseDigest"), field="releaseDigest")
    manifest_digest = (
        digest(fact.get("manifestDigest"), field="manifestDigest")
        if acceptance_profile == "m1_api_consumer"
        else release_digest
    )
    import_run_id = identity_value(fact.get("importRunId"), field="importRunId")
    verify_run_id = identity_value(fact.get("verifyRunId"), field="verifyRunId")
    if import_run_id == verify_run_id:
        block(
            invalid_code,
            "importRunId and verifyRunId must be distinct invocation identities",
        )
    timestamp(fact.get("createdAt"), field="createdAt")
    digest(fact.get("sourceFingerprint"), field="sourceFingerprint")
    plan_ref = relative_ref(fact.get("samplePlanRef"), field="samplePlanRef")
    plan_digest = digest(fact.get("samplePlanDigest"), field="samplePlanDigest")
    expected_profiles = (
        normalize_profiles(required_target_profiles, label="required_target_profiles")
        if verify_references and acceptance_profile == "environment_promotion"
        else set()
    )
    identity = {
        "environment": environment,
        "target": target,
        "release_id": release_id,
        "release_digest": release_digest,
        "import_run_id": import_run_id,
        "verify_run_id": verify_run_id,
    }
    root = absolute_real_root(evidence_root, label="evidence root")
    if not verify_references:
        if derive_fact_id(fact) != fact_id:
            block(invalid_code, "factId drifted from the authority digest collection")
        return fact
    plan_cells: dict[tuple[str, str, str, str], dict[str, str]] = {}
    plan_samples: list[dict[str, str]] = []
    if verify_references:
        plan_raw = secure_read(root, plan_ref, label="samplePlan")
        if exact_byte_digest(plan_raw) != plan_digest:
            block(evidence_code, "release UAT sample plan exact-byte digest drifted")
        plan = decode_json(plan_raw, label="samplePlan")
        if (
            plan.get("schema") != "quwoquan_data.release_uat_sample_plan"
            or plan.get("releaseId") != release_id
            or plan.get("releaseDigest") != release_digest
        ):
            block(evidence_code, "release UAT sample plan identity drifted")
        plan_cells = required_plan_cells(plan)
        raw_samples = plan.get("samples")
        if not isinstance(raw_samples, list) or not raw_samples:
            block(evidence_code, "release UAT sample plan samples are missing")
        seen_sample_ids: set[str] = set()
        seen_object_ids: set[str] = set()
        seen_object_refs: set[str] = set()
        for index, sample in enumerate(raw_samples):
            if not isinstance(sample, Mapping) or set(sample) != {
                "sampleId",
                "carrier",
                "objectId",
                "objectRef",
                "objectDigest",
            }:
                block(evidence_code, f"samplePlan.samples[{index}] fields are invalid")
            sample_id = identity_value(
                sample.get("sampleId"), field=f"samplePlan.samples[{index}].sampleId"
            )
            carrier = text(
                sample.get("carrier"), field=f"samplePlan.samples[{index}].carrier"
            )
            object_id = text(
                sample.get("objectId"), field=f"samplePlan.samples[{index}].objectId"
            )
            object_ref = relative_ref(
                sample.get("objectRef"), field=f"samplePlan.samples[{index}].objectRef"
            )
            object_digest = digest(
                sample.get("objectDigest"),
                field=f"samplePlan.samples[{index}].objectDigest",
            )
            if (
                sample_id in seen_sample_ids
                or object_id in seen_object_ids
                or object_ref in seen_object_refs
                or carrier not in _CARRIERS
            ):
                block(evidence_code, "sample plan sample/object id or ref is duplicated")
            expected_prefix = (
                "objects/entities/"
                if carrier == "homepage"
                else f"objects/posts/{carrier}/"
            )
            if not object_ref.startswith(expected_prefix):
                block(
                    evidence_code,
                    f"samplePlan.samples[{index}].objectRef is not carrier-bound",
                )
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
    bindings = fact.get("targetBindingRefs", [])
    if not isinstance(bindings, list):
        block(invalid_code, "targetBindingRefs must be an array")
    if acceptance_profile == "environment_promotion" and not bindings:
        block(invalid_code, "environment_promotion targetBindingRefs must be non-empty")
    binding_by_digest: dict[str, tuple[str, str, str]] = {}
    observed_profiles: set[tuple[str, str]] = set()
    seen_binding_refs: set[str] = set()
    for index, item in enumerate(bindings):
        label = f"targetBindingRefs[{index}]"
        if not isinstance(item, Mapping) or set(item) != _TARGET_BINDING_KEYS:
            block(invalid_code, f"{label} fields are invalid")
        exact = normalize_exact_ref(
            {"ref": item.get("ref"), "digest": item.get("digest")}, label=label
        )
        platform = text(item.get("platform"), field=f"{label}.platform")
        profile = text(item.get("deviceProfile"), field=f"{label}.deviceProfile")
        if platform not in _PLATFORMS or profile not in _DEVICE_PROFILES:
            block(invalid_code, f"{label} platform/deviceProfile is unknown")
        if exact["ref"] in seen_binding_refs or exact["digest"] in binding_by_digest:
            block(invalid_code, "targetBindingRefs contains duplicate ref or digest")
        if (platform, profile) in observed_profiles:
            block(
                invalid_code, "targetBindingRefs contains duplicate platform/device profile"
            )
        seen_binding_refs.add(exact["ref"])
        observed_profiles.add((platform, profile))
        if verify_references:
            binding, _ = load_exact(root, exact, label=label)
            try:
                binding = validate_target_uat_binding(binding)
            except TargetUatBindingError as exc:
                raise error_type(
                    evidence_code, f"{label} is not a strict TargetUatBinding: {exc}"
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
                    block(evidence_code, f"{label} identity drifted at {field}")
            if binding_device_profile(binding) != profile:
                block(evidence_code, f"{label} deviceProfile drifted")
            binding_by_digest[exact["digest"]] = (
                platform,
                profile,
                str(binding["provider"]["identity"]),
            )
    if (
        acceptance_profile == "environment_promotion"
        and observed_profiles != expected_profiles
    ):
        block(
            evidence_code,
            "targetBindingRefs do not exactly cover required platform/device profiles",
        )
    raw_results = fact.get("requiredRawResults")
    if not isinstance(raw_results, list) or not raw_results:
        block(invalid_code, "requiredRawResults must be non-empty")
    observed_slots: set[str] = set()
    seen_raw_refs: set[str] = set()
    verified_raw_results: list[dict[str, str]] = []
    for index, item in enumerate(raw_results):
        label = f"requiredRawResults[{index}]"
        if not isinstance(item, Mapping) or set(item) != _RAW_RESULT_KEYS:
            block(
                invalid_code,
                f"{label} fields are invalid; bundle substitution is forbidden",
            )
        exact = normalize_exact_ref(
            {"ref": item.get("ref"), "digest": item.get("digest")}, label=label
        )
        slot_id = digest(item.get("slotId"), field=f"{label}.slotId")
        if item.get("status") != "passed":
            block(evidence_code, f"{label}.status must be exactly passed")
        if exact["ref"] in seen_raw_refs or slot_id in observed_slots:
            block(evidence_code, "requiredRawResults contains duplicate raw ref or slotId")
        seen_raw_refs.add(exact["ref"])
        observed_slots.add(slot_id)
        if verify_references:
            raw_result, _ = load_exact(root, exact, label=label)
            try:
                raw_result = validate_readiness_case_result(
                    raw_result, generated_at=str(fact["createdAt"])
                )
            except ReadinessCaseResultError as exc:
                raise error_type(
                    evidence_code, f"{label} is not a canonical ReadinessCaseResult: {exc}"
                ) from exc
            if acceptance_profile == "environment_promotion":
                if (
                    raw_result.get("producer") != "app"
                    or raw_result.get("layer") != "user_acceptance"
                ):
                    block(
                        evidence_code,
                        f"{label} is not a direct raw App ReadinessCaseResult",
                    )
            elif (
                raw_result.get("producer") != "service"
                or raw_result.get("layer") != "api_integration"
            ):
                block(
                    evidence_code,
                    f"{label} is not a direct raw Service API integration result",
                )
            require_evidence_identity(raw_result, label=label, **identity)
            binding_digest: str | None = None
            if acceptance_profile == "environment_promotion":
                binding_digest = str(raw_result.get("targetUatBindingDigest"))
                profile = binding_by_digest.get(binding_digest)
                if profile is None:
                    block(
                        evidence_code,
                        f"{label} targetUatBindingDigest is not directly listed",
                    )
                platform, device_profile, provider_identity = profile
                if (
                    raw_result.get("platform") != platform
                    or raw_result.get("uatProfile") != device_profile
                    or raw_result.get("provider") != provider_identity
                ):
                    block(
                        evidence_code,
                        f"{label} platform/device profile/provider identity drifted",
                    )
            else:
                required_api_keys = {
                    "entrySurface",
                    "carrier",
                    "specRef",
                    "runnerIdentity",
                    "objectId",
                }
                if any(
                    not isinstance(raw_result.get(field), str)
                    or not raw_result.get(field)
                    for field in required_api_keys
                ):
                    block(evidence_code, f"{label} lacks direct API authority material")
                forbidden_api_authority = {
                    "targetUatBindingDigest",
                    "platform",
                    "deviceClass",
                    "deviceRegistered",
                    "deviceIdentity",
                    "uatProfile",
                    "nonPromotable",
                    "artifactClass",
                    "physicalDevice",
                    "deviceId",
                    "device",
                    "app",
                    "appArtifactDigest",
                    "appPackageDigest",
                }
                present_forbidden = sorted(forbidden_api_authority & set(raw_result))
                if present_forbidden:
                    block(
                        evidence_code,
                        f"{label} m1_api_consumer must not bind App/device authority: {present_forbidden}",
                    )
            cell_key = (
                str(raw_result.get("entrySurface") or ""),
                str(raw_result.get("carrier") or ""),
                str(raw_result.get("specRef") or ""),
                str(raw_result.get("runnerIdentity") or ""),
            )
            if cell_key not in plan_cells:
                block(evidence_code, f"{label} does not bind a required sample-plan cell")
            cell = plan_cells[cell_key]
            matching_samples = [
                sample
                for sample in plan_samples
                if sample["carrier"] == cell["carrier"]
                and sample["objectId"] == raw_result.get("objectId")
                and sample["objectRef"] == raw_result.get("objectRef")
                and sample["objectDigest"] == raw_result.get("objectDigest")
            ]
            if len(matching_samples) != 1:
                block(
                    evidence_code, f"{label} does not bind exactly one sample-plan object"
                )
            sample_id = matching_samples[0]["sampleId"]
            if acceptance_profile == "m1_api_consumer":
                verify_m1_observation(
                    root,
                    raw_result,
                    label=label,
                    sample_id=sample_id,
                    manifest_digest=manifest_digest,
                )
            expected_slot = required_raw_slot_id(
                target_uat_binding_digest=binding_digest,
                sample_id=sample_id,
                entry_surface=cell["entrySurface"],
                carrier=cell["carrier"],
                spec_ref=cell["specRef"],
                runner_identity=cell["runnerIdentity"],
            )
            if slot_id != expected_slot:
                block(
                    evidence_code,
                    f"{label}.slotId drifted from plan cell/profile authority",
                )
            if raw_result.get("status") != "passed":
                block(evidence_code, f"{label} referenced raw status is not passed")
            verified_raw_results.append(
                {**exact, "slotId": slot_id, "status": str(item["status"])}
            )
    if verify_references:
        expected_slots = {
            required_raw_slot_id(
                target_uat_binding_digest=(
                    binding_digest
                    if acceptance_profile == "environment_promotion"
                    else None
                ),
                sample_id=sample["sampleId"],
                entry_surface=cell["entrySurface"],
                carrier=cell["carrier"],
                spec_ref=cell["specRef"],
                runner_identity=cell["runnerIdentity"],
            )
            for sample in plan_samples
            for cell in plan_cells.values()
            if sample["carrier"] == cell["carrier"]
            for binding_digest, platform, device_profile in (
                [
                    (digest, values[0], values[1])
                    for digest, values in binding_by_digest.items()
                ]
                if acceptance_profile == "environment_promotion"
                else [(None, None, None)]
            )
            if acceptance_profile == "m1_api_consumer"
            or (platform, device_profile) in expected_profiles
        }
        if observed_slots != expected_slots:
            missing = sorted(expected_slots - observed_slots)
            extra = sorted(observed_slots - expected_slots)
            block(
                evidence_code,
                f"required raw exact coverage drifted: missing={missing}, extra={extra}",
            )
    data_exact = normalize_exact_ref(fact.get("dataReadiness"), label="dataReadiness")
    if verify_references:
        data_payload, _ = load_exact(root, data_exact, label="dataReadiness")
        if data_payload.get("passed") is not True:
            block(evidence_code, "dataReadiness.passed must be exactly true")
        data_expected = {
            "environment": environment,
            "releaseId": release_id,
            "manifestDigest": manifest_digest,
            "importRunId": import_run_id,
            "verifyRunId": verify_run_id,
        }
        for field, expected in data_expected.items():
            if data_payload.get(field) != expected:
                block(evidence_code, f"dataReadiness identity drifted at {field}")

    if acceptance_profile == "m1_api_consumer":
        consumer_health = normalize_exact_ref(
            fact.get("consumerHealth"), label="consumerHealth"
        )
        if verify_references:
            verify_m1_consumer_health(
                root,
                consumer_health,
                identity=identity,
                manifest_digest=manifest_digest,
                data_readiness=data_exact,
            )
            expected_fingerprint = derive_m1_source_fingerprint(
                environment=environment,
                target=target,
                release_id=release_id,
                release_digest=release_digest,
                manifest_digest=manifest_digest,
                import_run_id=import_run_id,
                verify_run_id=verify_run_id,
                sample_plan={"ref": plan_ref, "digest": plan_digest},
                data_readiness=data_exact,
                consumer_health=consumer_health,
                required_raw_results=verified_raw_results,
            )
            if fact.get("sourceFingerprint") != expected_fingerprint:
                block(evidence_code, "sourceFingerprint drifted from M1 exact authorities")
        if derive_fact_id(fact) != fact_id:
            block(invalid_code, "factId drifted from the authority digest collection")
        return fact

    exact_evidence = (
        ("lifecycleExit", {"Exit"}),
        ("providerReadiness", {"passed", "ready"}),
        ("observabilityReadiness", {"passed", "ready"}),
        ("rollbackReadiness", {"passed", "ready"}),
    )
    for field, statuses in exact_evidence:
        exact = normalize_exact_ref(fact.get(field), label=field)
        if verify_references:
            verify_common_evidence(
                root, exact, label=field, allowed_statuses=statuses, identity=identity
            )
    active = fact.get("activeCas")
    if not isinstance(active, Mapping) or set(active) != _ACTIVE_CAS_KEYS:
        block(invalid_code, "activeCas fields are invalid")
    if (
        active.get("releaseId") != release_id
        or active.get("releaseDigest") != release_digest
    ):
        block(evidence_code, "activeCas release identity drifted")
    active_ref = normalize_exact_ref(
        {"ref": active.get("ref"), "digest": active.get("digest")}, label="activeCas"
    )
    readback_ref = normalize_exact_ref(
        {"ref": active.get("readbackRef"), "digest": active.get("readbackDigest")},
        label="activeCas.readback",
    )
    if verify_references:
        verify_common_evidence(
            root,
            active_ref,
            label="activeCas",
            allowed_statuses={"active", "ready"},
            identity=identity,
        )
        verify_common_evidence(
            root,
            readback_ref,
            label="activeCas.readback",
            allowed_statuses={"active", "passed", "ready"},
            identity=identity,
        )
    validate_finalization(
        root,
        fact.get("resourceFinalization"),
        identity=identity,
        verify_references=verify_references,
    )
    validate_prod_facts(
        root,
        fact.get("prodReleaseFacts"),
        environment=environment,
        identity=identity,
        verify_references=verify_references,
    )
    validate_predecessor_acceptance(
        environment=environment,
        predecessor_acceptance=fact.get("predecessorAcceptance"),
        evidence_root=root,
        release_id=release_id,
        release_digest=release_digest,
    )
    if derive_fact_id(fact) != fact_id:
        block(invalid_code, "factId drifted from the authority digest collection")
    return fact


__all__ = ["validate_environment_acceptance_fact"]
