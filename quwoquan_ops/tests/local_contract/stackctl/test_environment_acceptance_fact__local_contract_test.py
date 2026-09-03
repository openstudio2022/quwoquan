# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t11
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t12
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-035.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-035.t2
"""EnvironmentAcceptanceFact strict append-only contract tests.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_ops.cli.lib import environment_acceptance_fact as subject
from quwoquan_ops.cli.lib import environment_release_order_view as order_view
from quwoquan_ops.cli.lib.target_uat_binding import build_target_uat_binding

ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = (
    ROOT / "quwoquan_ops/environments/evidence/environment_acceptance_fact.schema.json"
)
RELEASE_DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64
SOURCE_FINGERPRINT = "sha256:" + "f" * 64
SPEC_REF = "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006"
RUNNER = "qwq_app.content_uat.feed.article.v1"
PROFILES = (
    {"platform": "android", "deviceProfile": "promotable"},
    {"platform": "ios", "deviceProfile": "promotable"},
)


def _write_json(root: Path, ref: str, value: object) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return {"ref": ref, "digest": subject.exact_byte_digest(path)}


def _identity(environment: str, target: str) -> dict[str, str]:
    return {
        "environment": environment,
        "target": target,
        "deploymentTarget": target,
        "releaseId": "release-a",
        "releaseDigest": RELEASE_DIGEST,
        "importRunId": "import-run-a",
        "verifyRunId": "verify-run-a",
    }


def _evidence(
    root: Path,
    environment: str = "alpha",
    target: str = "alpha-local",
    profiles: tuple[dict[str, str], ...] = PROFILES,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    identity = _identity(environment, target)
    entries = ("feed", "search", "recommendation", "direct_or_object_route")
    carriers = ("homepage", "article", "image", "video")
    plan = {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-a",
        "releaseDigest": RELEASE_DIGEST,
        "samples": [
            {
                "sampleId": "baseline-article-001",
                "carrier": "article",
                "objectId": "article-001",
                "objectRef": "objects/posts/article/article-001",
                "objectDigest": "sha256:" + "0" * 64,
            }
        ],
        "entryCarrierCells": [
            {
                "entry": entry,
                "carrier": carrier,
                "applicability": "required",
                "specRef": SPEC_REF,
                "runnerClass": RUNNER,
            }
            if (entry, carrier) == ("feed", "article")
            else {
                "entry": entry,
                "carrier": carrier,
                "applicability": "not_applicable",
                "reasonCode": "APP.UAT.NOT_APPLICABLE",
            }
            for entry in entries
            for carrier in carriers
        ],
    }
    plan_ref = _write_json(root, "release/sample-plan.json", plan)
    bindings: list[dict[str, str]] = []
    raw_results: list[dict[str, str]] = []
    for profile in profiles:
        platform = profile["platform"]
        device_profile = profile["deviceProfile"]
        physical = device_profile != "rehearsal"
        device_identity = f"{platform}-{device_profile}-device"
        binding = build_target_uat_binding(
            runtime_binding={
                "environment": environment,
                "target": target,
                "releaseId": "release-a",
                "manifestDigest": RELEASE_DIGEST,
                "candidateDigest": "sha256:" + "2" * 64,
                "packageDigest": "sha256:" + "3" * 64,
                "runtimeConfigDigest": "sha256:" + "4" * 64,
                "environmentRuntimeDigest": "sha256:" + "5" * 64,
                "startupIdentity": {"configurationDigest": "sha256:" + "6" * 64},
            },
            launch_binding={
                "environment": environment,
                "target": target,
                "platform": platform,
                "deviceId": device_identity,
                "artifactDigest": "sha256:" + "7" * 64,
                "applicationId": "com.leadwise.quwoquan.app",
            },
            sample_plan_binding={
                "releaseId": "release-a",
                "releaseUatSamplePlanRef": plan_ref["ref"],
                "releaseUatSamplePlanDigest": plan_ref["digest"],
            },
            active_cas={
                "ref": f"{environment}/binding-active-cas.json",
                "digest": "sha256:" + "8" * 64,
            },
            readback={
                "ref": f"{environment}/binding-readback.json",
                "digest": "sha256:" + "9" * 64,
            },
            artifact_class="production"
            if device_profile == "production"
            else "production_behavior",
            build_mode="release" if device_profile == "production" else "debug",
            build_profile="prod" if device_profile == "production" else "nonprod",
            provider={
                "identity": "first-party-https",
                "class": "first_party",
                "type": "https",
                "registered": True,
                "conformanceEvidence": {
                    "ref": "env/provider/conformance.json",
                    "digest": "sha256:" + "f" * 64,
                },
            },
            device={
                "identity": device_identity,
                "class": "physical"
                if physical
                else ("emulator" if platform == "android" else "simulator"),
                "registered": physical,
            },
            runner={
                "identity": "app-content-uat",
                "sourcePath": "quwoquan_app/test/user_acceptance/app_content_uat.dart",
                "digest": "sha256:" + "a" * 64,
                "registered": physical,
            },
            profile=device_profile,
            non_promotable=not physical,
            created_at="2026-08-29T07:00:00Z",
        )
        binding_ref = _write_json(
            root, f"{environment}/binding-{platform}.json", binding
        )
        bindings.append({**binding_ref, **profile})
        slot_id = subject.required_raw_slot_id(
            target_uat_binding_digest=binding_ref["digest"],
            sample_id="baseline-article-001",
            entry_surface="feed",
            carrier="article",
            spec_ref=SPEC_REF,
            runner_identity=RUNNER,
        )
        raw = {
            "objectId": "article-001",
            "objectRef": "objects/posts/article/article-001",
            "objectDigest": "sha256:" + "0" * 64,
            "specRef": SPEC_REF,
            "caseId": "baseline-article-001",
            "producer": "app",
            "layer": "user_acceptance",
            "status": "passed",
            "target": {"kind": "page", "id": "content.feed.list"},
            "commitSha": "a" * 40,
            "contractGraphSourceHash": "b" * 64,
            "deploymentTarget": target,
            "baselineId": "baseline-app-uat",
            "packageDigest": "sha256:" + "c" * 64,
            "configurationDigest": "sha256:" + "d" * 64,
            "candidateManifestSha256": "e" * 64,
            "releaseDigest": RELEASE_DIGEST,
            "releaseId": "release-a",
            "importRunId": "import-run-a",
            "verifyRunId": "verify-run-a",
            "targetUatBindingDigest": binding_ref["digest"],
            "entrySurface": "feed",
            "carrier": "article",
            "environment": environment,
            "platform": platform,
            "deviceClass": "physical"
            if physical
            else ("emulator" if platform == "android" else "simulator"),
            "provider": "first-party-https",
            "startedAt": "2026-08-29T07:00:00Z",
            "completedAt": "2026-08-29T07:01:00Z",
            "runnerIdentity": RUNNER,
            "artifactSha256": "f" * 64,
            "artifactPath": f"{environment}/raw-{platform}-artifact.json",
            "deviceIdentity": device_identity,
            "deviceRegistered": physical,
            "uatProfile": device_profile,
            "nonPromotable": not physical,
            "artifactClass": "production"
            if device_profile == "production"
            else "production_behavior",
            "physicalDevice": physical,
        }
        raw_ref = _write_json(root, f"{environment}/raw-{platform}.json", raw)
        raw_results.append({**raw_ref, "slotId": slot_id, "status": "passed"})

    def ready(name: str, status: str) -> dict[str, str]:
        return _write_json(
            root, f"{environment}/{name}.json", {**identity, "status": status}
        )

    cas = ready("active-cas", "active")
    cas_readback = ready("active-cas-readback", "passed")
    arguments: dict[str, object] = {
        "evidence_root": root,
        "acceptance_profile": "environment_promotion",
        "environment": environment,
        "target": target,
        "release_id": "release-a",
        "release_digest": RELEASE_DIGEST,
        "import_run_id": "import-run-a",
        "verify_run_id": "verify-run-a",
        "sample_plan_ref": plan_ref["ref"],
        "sample_plan_digest": plan_ref["digest"],
        "target_binding_refs": bindings,
        "required_raw_results": raw_results,
        "required_target_profiles": list(profiles),
        "data_readiness": _write_json(
            root,
            f"{environment}/data-readiness.json",
            {
                **identity,
                "passed": True,
                "manifestDigest": RELEASE_DIGEST,
                "activationEnvelope": {
                    "importReportRef": ready("import-report", "imported")["ref"],
                    "importReportDigest": ready("import-report", "imported")["digest"],
                },
            },
        ),
        "active_cas": {
            "ref": cas["ref"],
            "digest": cas["digest"],
            "readbackRef": cas_readback["ref"],
            "readbackDigest": cas_readback["digest"],
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
        },
        "lifecycle_exit": ready("lifecycle-exit", "Exit"),
        "provider_readiness": ready("provider-readiness", "ready"),
        "observability_readiness": ready("observability-readiness", "ready"),
        "rollback_readiness": ready("rollback-readiness", "ready"),
        "predecessor_acceptance": None,
        "resource_finalization": {
            "leaseRevocationRefs": [ready("lease-revocation", "revoked")],
            "lockReleaseRefs": [ready("lock-release", "released")],
            "gcProtectionRefs": [ready("gc-protection", "protected")],
        },
        "prod_release_facts": None,
        "created_at": "2026-08-29T07:00:00Z",
        "source_fingerprint": SOURCE_FINGERPRINT,
    }
    return arguments, list(profiles)


def _build(
    root: Path, **changes: object
) -> tuple[dict[str, object], list[dict[str, str]]]:
    arguments, profiles = _evidence(root)
    arguments.update(changes)
    return subject.build_environment_acceptance_fact(**arguments), profiles  # type: ignore[arg-type]


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _rewrite(root: Path, ref: str, mutate) -> str:
    path = root / ref
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return subject.exact_byte_digest(path)


def test_schema_fact_has_no_verdict_and_fact_id_is_deterministic(
    tmp_path: Path,
) -> None:
    fact, profiles = _build(tmp_path)
    _schema_validator().validate(fact)
    assert fact["schema"] == subject.SCHEMA
    assert len(fact["targetBindingRefs"]) == len(PROFILES)
    assert all(
        "targetUatBindingDigest"
        in json.loads((tmp_path / raw["ref"]).read_text(encoding="utf-8"))
        for raw in fact["requiredRawResults"]
    )
    assert fact["factId"] == subject.derive_fact_id(fact)
    assert not {"status", "verdict", "passed"}.intersection(fact)
    assert "bundle" not in json.dumps(fact).lower()
    changed_time = deepcopy(fact)
    changed_time["createdAt"] = "2026-08-29T08:00:00Z"
    assert subject.derive_fact_id(changed_time) == fact["factId"]
    moved_refs = deepcopy(fact)
    moved_refs["samplePlanRef"] = "moved/sample-plan.json"
    moved_refs["targetBindingRefs"][0]["ref"] = "moved/binding.json"
    moved_refs["requiredRawResults"][0]["ref"] = "moved/raw.json"
    assert subject.derive_fact_id(moved_refs) == fact["factId"]
    subject.validate_environment_acceptance_fact(
        fact, evidence_root=tmp_path, required_target_profiles=profiles
    )


@pytest.mark.parametrize("forbidden", ["status", "verdict", "passed"])
def test_fact_rejects_independent_outcome_fields(
    tmp_path: Path, forbidden: str
) -> None:
    fact, profiles = _build(tmp_path)
    fact[forbidden] = True
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="fields"):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=profiles
        )


def test_required_raw_nonpassed_missing_duplicate_and_bundle_substitution_block(
    tmp_path: Path,
) -> None:
    fact, profiles = _build(tmp_path)
    failed = deepcopy(fact)
    failed["requiredRawResults"][0]["status"] = "failed"
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="exactly passed"):
        subject.validate_environment_acceptance_fact(
            failed, evidence_root=tmp_path, required_target_profiles=profiles
        )
    missing = deepcopy(fact)
    missing["requiredRawResults"].pop()
    missing["factId"] = subject.derive_fact_id(missing)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="coverage drifted"
    ):
        subject.validate_environment_acceptance_fact(
            missing, evidence_root=tmp_path, required_target_profiles=profiles
        )
    duplicate = deepcopy(fact)
    duplicate["requiredRawResults"].append(deepcopy(duplicate["requiredRawResults"][0]))
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="duplicate"):
        subject.validate_environment_acceptance_fact(
            duplicate, evidence_root=tmp_path, required_target_profiles=profiles
        )
    bundle = deepcopy(fact)
    bundle["requiredRawResults"] = [{"bundleRef": "bundle.json"}]
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="bundle substitution"
    ):
        subject.validate_environment_acceptance_fact(
            bundle, evidence_root=tmp_path, required_target_profiles=profiles
        )


def test_sample_plan_and_profile_coverage_bind_each_raw_to_target_binding(
    tmp_path: Path,
) -> None:
    fact, profiles = _build(tmp_path)
    wrong_binding = deepcopy(fact)
    wrong_binding["requiredRawResults"][0]["slotId"] = "sha256:" + "9" * 64
    wrong_binding["factId"] = subject.derive_fact_id(wrong_binding)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="slotId drifted"):
        subject.validate_environment_acceptance_fact(
            wrong_binding, evidence_root=tmp_path, required_target_profiles=profiles
        )
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="exactly cover"):
        subject.validate_environment_acceptance_fact(
            fact,
            evidence_root=tmp_path,
            required_target_profiles=[
                {"platform": "android", "deviceProfile": "promotable"}
            ],
        )
    cross_binding = deepcopy(fact)
    raw_ref = cross_binding["requiredRawResults"][0]["ref"]
    digest = _rewrite(
        tmp_path,
        raw_ref,
        lambda value: value.update({"targetUatBindingDigest": "sha256:" + "8" * 64}),
    )
    cross_binding["requiredRawResults"][0]["digest"] = digest
    cross_binding["factId"] = subject.derive_fact_id(cross_binding)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="not directly listed"
    ):
        subject.validate_environment_acceptance_fact(
            cross_binding, evidence_root=tmp_path, required_target_profiles=profiles
        )


def test_raw_object_must_match_sample_plan_exact_object(tmp_path: Path) -> None:
    fact, profiles = _build(tmp_path)
    raw_ref = fact["requiredRawResults"][0]["ref"]
    digest = _rewrite(
        tmp_path,
        raw_ref,
        lambda value: value.update({"objectId": "article-999"}),
    )
    fact["requiredRawResults"][0]["digest"] = digest
    fact["factId"] = subject.derive_fact_id(fact)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="sample-plan object"
    ):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=profiles
        )


@pytest.mark.parametrize(
    "field,ref_getter",
    [
        ("dataReadiness", lambda fact: fact["dataReadiness"]),
        (
            "activeCas",
            lambda fact: {
                "ref": fact["activeCas"]["ref"],
                "digest": fact["activeCas"]["digest"],
            },
        ),
        (
            "activeCas.readback",
            lambda fact: {
                "ref": fact["activeCas"]["readbackRef"],
                "digest": fact["activeCas"]["readbackDigest"],
            },
        ),
        ("lifecycleExit", lambda fact: fact["lifecycleExit"]),
        ("providerReadiness", lambda fact: fact["providerReadiness"]),
        ("observabilityReadiness", lambda fact: fact["observabilityReadiness"]),
        ("rollbackReadiness", lambda fact: fact["rollbackReadiness"]),
    ],
)
def test_authority_exact_byte_drift_blocks(
    tmp_path: Path, field: str, ref_getter
) -> None:
    fact, profiles = _build(tmp_path)
    exact = ref_getter(fact)
    (tmp_path / exact["ref"]).write_bytes((tmp_path / exact["ref"]).read_bytes() + b" ")
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="digest drifted"):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=profiles
        )


def test_finalization_requires_three_nonempty_exact_arrays(tmp_path: Path) -> None:
    fact, profiles = _build(tmp_path)
    fact["resourceFinalization"]["lockReleaseRefs"] = []
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="must be non-empty"
    ):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=profiles
        )


def _write_fact(
    root: Path, fact: dict[str, object], profiles: list[dict[str, str]]
) -> tuple[str, str]:
    store = root / "facts"
    store.mkdir(exist_ok=True)
    path = subject.write_environment_acceptance_fact(
        root=store, fact=fact, evidence_root=root, required_target_profiles=profiles
    )
    ref = path.relative_to(root).as_posix()
    return ref, subject.exact_byte_digest(path)


def test_predecessor_mapping_fact_id_and_exact_digest_are_strict(
    tmp_path: Path,
) -> None:
    alpha, alpha_profiles = _build(tmp_path)
    alpha_ref, alpha_digest = _write_fact(tmp_path, alpha, alpha_profiles)
    arguments, _profiles = _evidence(tmp_path, "beta", "beta-local")
    predecessor = {
        "environment": "alpha",
        "factId": alpha["factId"],
        "ref": alpha_ref,
        "digest": alpha_digest,
    }
    arguments["predecessor_acceptance"] = predecessor
    beta = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    assert beta["predecessorAcceptance"]["factId"] == alpha["factId"]
    for mutation, message in (
        (lambda value: value.update({"environment": "gamma"}), "exactly alpha"),
        (
            lambda value: value.update({"factId": "sha256:" + "9" * 64}),
            "identity drifted",
        ),
        (
            lambda value: value.update({"digest": "sha256:" + "8" * 64}),
            "exact bytes drifted",
        ),
    ):
        wrong = deepcopy(predecessor)
        mutation(wrong)
        with pytest.raises(subject.EnvironmentAcceptanceFactError, match=message):
            subject.validate_predecessor_acceptance(
                environment="beta",
                predecessor_acceptance=wrong,
                evidence_root=tmp_path,
                release_id="release-a",
                release_digest=RELEASE_DIGEST,
            )
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="must not provide"
    ):
        subject.validate_predecessor_acceptance(
            environment="alpha",
            predecessor_acceptance=predecessor,
            evidence_root=tmp_path,
            release_id="release-a",
            release_digest=RELEASE_DIGEST,
        )


def _prod_release_facts(root: Path) -> dict[str, object]:
    identity = _identity("prod", "prod-hosted")

    def fact(name: str, status: str, **extra: str) -> dict[str, str]:
        return _write_json(
            root, f"prod/{name}.json", {**identity, "status": status, **extra}
        )

    return {
        "engineeringEligibility": fact(
            "engineering", "eligible", factType="engineeringEligibility"
        ),
        "durableApproval": fact("approval", "approved", factType="durableApproval"),
        "rolloutStages": [
            {
                "stage": stage,
                **fact(
                    f"rollout-{stage}",
                    "completed",
                    factType="rolloutStage",
                    stage=stage,
                ),
            }
            for stage in subject.PROD_ROLLOUT_STAGES
        ],
        "rollbackReadiness": fact(
            "prod-rollback", "ready", factType="rollbackReadiness"
        ),
    }


def test_prod_requires_canonical_release_fact_roles_and_rollout_order(
    tmp_path: Path,
) -> None:
    # Use a structurally valid predecessor from an explicit gamma fact.
    # A gamma fact itself needs beta; this test isolates prod release fact validation by
    # first building a real alpha/beta/gamma chain.
    predecessor = None
    for environment, target in (
        ("alpha", "alpha-local"),
        ("beta", "beta-local"),
        ("gamma", "gamma-local"),
    ):
        args, chain_profiles = _evidence(tmp_path, environment, target)
        args["predecessor_acceptance"] = predecessor
        chain_fact = subject.build_environment_acceptance_fact(**args)  # type: ignore[arg-type]
        ref, digest = _write_fact(tmp_path, chain_fact, chain_profiles)
        predecessor = {
            "environment": environment,
            "factId": chain_fact["factId"],
            "ref": ref,
            "digest": digest,
        }
    prod_args, profiles = _evidence(
        tmp_path,
        "prod",
        "prod-hosted",
        ({"platform": "android", "deviceProfile": "production"},),
    )
    prod_args["predecessor_acceptance"] = predecessor
    prod_args["prod_release_facts"] = _prod_release_facts(tmp_path)
    fact = subject.build_environment_acceptance_fact(**prod_args)  # type: ignore[arg-type]
    _schema_validator().validate(fact)
    missing = deepcopy(fact)
    missing["prodReleaseFacts"]["rolloutStages"].pop(2)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="canary/5/20/50/100"
    ):
        subject.validate_environment_acceptance_fact(
            missing, evidence_root=tmp_path, required_target_profiles=profiles
        )
    wrong_order = deepcopy(fact)
    (
        wrong_order["prodReleaseFacts"]["rolloutStages"][0],
        wrong_order["prodReleaseFacts"]["rolloutStages"][1],
    ) = (
        wrong_order["prodReleaseFacts"]["rolloutStages"][1],
        wrong_order["prodReleaseFacts"]["rolloutStages"][0],
    )
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="requires canary"):
        subject.validate_environment_acceptance_fact(
            wrong_order, evidence_root=tmp_path, required_target_profiles=profiles
        )


def test_raw_provider_must_match_target_binding_provider(tmp_path: Path) -> None:
    fact, profiles = _build(tmp_path)
    raw = fact["requiredRawResults"][0]
    raw_path = tmp_path / raw["ref"]
    value = json.loads(raw_path.read_text(encoding="utf-8"))
    value["provider"] = "different-provider"
    raw_path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    raw["digest"] = subject.exact_byte_digest(raw_path)
    fact["factId"] = subject.derive_fact_id(fact)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError,
        match="provider identity drifted",
    ):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=profiles
        )


def test_duplicate_json_key_and_symlink_evidence_are_rejected(tmp_path: Path) -> None:
    fact, profiles = _build(tmp_path)
    raw = fact["requiredRawResults"][0]
    path = tmp_path / raw["ref"]
    encoded = path.read_bytes()
    path.write_bytes(encoded[:-1] + b',"status":"passed"}')
    raw["digest"] = subject.exact_byte_digest(path)
    fact["factId"] = subject.derive_fact_id(fact)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="duplicate JSON key"
    ):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=profiles
        )

    clean_root = tmp_path / "linked"
    clean_root.mkdir()
    linked_fact, linked_profiles = _build(clean_root)
    target = clean_root / linked_fact["dataReadiness"]["ref"]
    outside = clean_root / "outside.json"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="linked"):
        subject.validate_environment_acceptance_fact(
            linked_fact,
            evidence_root=clean_root,
            required_target_profiles=linked_profiles,
        )


def test_create_once_helper_is_idempotent_append_only_and_nofollow(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    store = tmp_path / "store"
    store.mkdir()
    fact, profiles = _build(evidence)
    first = subject.write_environment_acceptance_fact(
        root=store, fact=fact, evidence_root=evidence, required_target_profiles=profiles
    )
    assert first.relative_to(
        store
    ).as_posix() == subject.environment_acceptance_fact_relative_path(fact)
    inode = (first.stat().st_dev, first.stat().st_ino)
    replay = subject.write_environment_acceptance_fact(
        root=store,
        fact=deepcopy(fact),
        evidence_root=evidence,
        required_target_profiles=profiles,
    )
    assert replay == first and (first.stat().st_dev, first.stat().st_ino) == inode

    # A distinct authority fingerprint yields another append-only fact, not replacement.
    newer = deepcopy(fact)
    newer["sourceFingerprint"] = "sha256:" + "e" * 64
    newer["factId"] = subject.derive_fact_id(newer)
    second = subject.write_environment_acceptance_fact(
        root=store,
        fact=newer,
        evidence_root=evidence,
        required_target_profiles=profiles,
    )
    assert second != first and first.exists() and second.exists()

    first.chmod(0o644)
    first.write_bytes(b"{}")
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="different exact bytes"
    ):
        subject.write_environment_acceptance_fact(
            root=store,
            fact=fact,
            evidence_root=evidence,
            required_target_profiles=profiles,
        )

    linked_store = tmp_path / "linked-store"
    linked_store.symlink_to(store, target_is_directory=True)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="non-symlink"):
        subject.write_environment_acceptance_fact(
            root=linked_store,
            fact=newer,
            evidence_root=evidence,
            required_target_profiles=profiles,
        )


def test_release_order_projection_uses_fact_existence_not_passed_field(
    tmp_path: Path,
) -> None:
    fact, profiles = _build(tmp_path)
    ref, _ = _write_fact(tmp_path, fact, profiles)
    view = order_view.derive_environment_release_order_view(
        release_id="release-a",
        derived_at="2026-08-29T08:00:00Z",
        artifact_root=tmp_path,
        acceptance_refs={"alpha": ref, "beta": None, "gamma": None, "prod": None},
    )
    assert "passed" not in fact
    assert view["environments"][0]["state"] == "accepted"
    assert view["environments"][1]["availableActions"] == ["create_acceptance"]


def _m1_api_evidence(root: Path) -> tuple[dict[str, object], list[dict[str, str]]]:
    arguments, _profiles = _evidence(root)
    arguments["acceptance_profile"] = "m1_api_consumer"
    arguments["target_binding_refs"] = []
    arguments["required_target_profiles"] = []
    plan = json.loads(
        (root / str(arguments["sample_plan_ref"])).read_text(encoding="utf-8")
    )
    plan["samples"] = [
        {
            "sampleId": f"baseline-{carrier}-001",
            "carrier": carrier,
            "objectId": f"{carrier}-001",
            "objectRef": (
                f"objects/entities/{carrier}-001"
                if carrier == "homepage"
                else f"objects/posts/{carrier}/{carrier}-001"
            ),
            "objectDigest": "sha256:" + str(index) * 64,
        }
        for index, carrier in enumerate(subject._CARRIERS, 1)
    ]
    plan["entryCarrierCells"] = [
        {
            "entry": entry,
            "carrier": carrier,
            "applicability": "required",
            "specRef": SPEC_REF,
            "runnerClass": f"qwq_service.content_api.{entry}.{carrier}.v1",
        }
        for entry in subject._ENTRIES
        for carrier in subject._CARRIERS
    ]
    plan_ref = _write_json(root, "release/m1-sample-plan.json", plan)
    arguments["sample_plan_ref"] = plan_ref["ref"]
    arguments["sample_plan_digest"] = plan_ref["digest"]
    samples = {item["carrier"]: item for item in plan["samples"]}
    results = []
    for cell in plan["entryCarrierCells"]:
        sample = samples[cell["carrier"]]
        raw = {
            "objectId": sample["objectId"],
            "objectRef": sample["objectRef"],
            "objectDigest": sample["objectDigest"],
            "specRef": cell["specRef"],
            "caseId": sample["sampleId"],
            "producer": "service",
            "layer": "api_integration",
            "status": "passed",
            "target": {"kind": "operation", "id": cell["entry"]},
            "commitSha": "a" * 40,
            "contractGraphSourceHash": "b" * 64,
            "deploymentTarget": "alpha-local",
            "baselineId": "baseline-m1-api-consumer",
            "packageDigest": "sha256:" + "c" * 64,
            "configurationDigest": "sha256:" + "d" * 64,
            "candidateManifestSha256": "e" * 64,
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
            "importRunId": "import-run-a",
            "verifyRunId": "verify-run-a",
            "entrySurface": cell["entry"],
            "carrier": cell["carrier"],
            "environment": "alpha",
            "provider": "first-party-https",
            "startedAt": "2026-08-29T07:00:00Z",
            "completedAt": "2026-08-29T07:01:00Z",
            "runnerIdentity": cell["runnerClass"],
            "artifactSha256": "f" * 64,
            "artifactPath": f"alpha/m1-{cell['entry']}-{cell['carrier']}-artifact.json",
        }
        observation = {
            "schema": subject._M1_OBSERVATION_SCHEMA,
            "sampleId": sample["sampleId"],
            "entrySurface": cell["entry"],
            "carrier": cell["carrier"],
            "objectId": sample["objectId"],
            "runtimeObjectId": f"runtime-{cell['carrier']}-001",
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
            "manifestDigest": MANIFEST_DIGEST,
            "importRunId": "import-run-a",
            "verifyRunId": "verify-run-a",
            "status": "passed",
            "startedAt": raw["startedAt"],
            "completedAt": raw["completedAt"],
            "http": {
                "method": "GET",
                "path": f"/{cell['entry']}",
                "status": 200,
                "requestId": "request-1",
                "traceId": "trace-1",
                "durationMs": 1,
                "responseSha256": "sha256:" + "9" * 64,
            },
            "assertion": {"matchedRuntimeObjectId": f"runtime-{cell['carrier']}-001"},
        }
        observation_ref = _write_json(
            root,
            f"alpha/m1-{cell['entry']}-{cell['carrier']}-artifact.json",
            observation,
        )
        raw["artifactSha256"] = observation_ref["digest"].removeprefix("sha256:")
        raw_ref = _write_json(
            root,
            f"alpha/m1-raw-{cell['entry']}-{cell['carrier']}.json",
            raw,
        )
        results.append(
            {
                **raw_ref,
                "slotId": subject.required_raw_slot_id(
                    sample_id=sample["sampleId"],
                    entry_surface=cell["entry"],
                    carrier=cell["carrier"],
                    spec_ref=cell["specRef"],
                    runner_identity=cell["runnerClass"],
                ),
                "status": "passed",
            }
        )
    arguments["required_raw_results"] = results
    arguments["manifest_digest"] = MANIFEST_DIGEST
    data_path = root / str(arguments["data_readiness"]["ref"])
    data_payload = json.loads(data_path.read_text(encoding="utf-8"))
    data_payload["manifestDigest"] = MANIFEST_DIGEST
    data_path.write_text(
        json.dumps(data_payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    arguments["data_readiness"]["digest"] = subject.exact_byte_digest(data_path)
    source_health = _write_json(
        root,
        "alpha/source-content-consumer-health.json",
        {
            "command": "health",
            "target": "alpha-local",
            "scope": "content-consumer",
            **_identity("alpha", "alpha-local"),
            "manifestDigest": MANIFEST_DIGEST,
            "findings": [],
            "generationIssues": [],
            "checks": [{"name": "content-api", "ok": True, "skipped": False}],
            "userAvailability": [
                {"name": name, "status": "ready", "issues": []}
                for name in subject._M1_REQUIRED_HEALTH_LAYERS
            ],
            "userAvailabilityReport": {
                "evidence": {
                    "content": {
                        "releaseId": "release-a",
                        "manifestDigest": MANIFEST_DIGEST,
                        "readinessReceiptRef": arguments["data_readiness"]["ref"],
                        "readinessReceiptDigest": arguments["data_readiness"]["digest"],
                        "releaseActive": True,
                        "exactQueriesReady": True,
                        "generationMatch": True,
                    }
                }
            },
        },
    )
    arguments["consumer_health"] = _write_json(
        root,
        "alpha/consumer-health.json",
        {
            "schema": subject._M1_HEALTH_SCHEMA,
            "status": "passed",
            "environment": "alpha",
            "deploymentTarget": "alpha-local",
            "releaseId": "release-a",
            "releaseDigest": RELEASE_DIGEST,
            "manifestDigest": MANIFEST_DIGEST,
            "importRunId": "import-run-a",
            "verifyRunId": "verify-run-a",
            "sourceHealth": source_health,
            "requiredLayers": list(subject._M1_REQUIRED_HEALTH_LAYERS),
        },
    )
    arguments["source_fingerprint"] = subject.derive_m1_source_fingerprint(
        environment="alpha",
        target="alpha-local",
        release_id="release-a",
        release_digest=RELEASE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
        import_run_id="import-run-a",
        verify_run_id="verify-run-a",
        sample_plan={"ref": plan_ref["ref"], "digest": plan_ref["digest"]},
        data_readiness=arguments["data_readiness"],
        consumer_health=arguments["consumer_health"],
        required_raw_results=results,
    )
    for field in (
        "active_cas",
        "lifecycle_exit",
        "provider_readiness",
        "observability_readiness",
        "rollback_readiness",
        "resource_finalization",
        "prod_release_facts",
    ):
        arguments.pop(field, None)
    return arguments, []


def test_m1_api_consumer_is_alpha_service_only_without_promotion_authority(
    tmp_path: Path,
) -> None:
    arguments, profiles = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    _schema_validator().validate(fact)
    assert fact["acceptanceProfile"] == "m1_api_consumer"
    assert fact["environment"] == "alpha" and fact["target"] == "alpha-local"
    assert "targetBindingRefs" not in fact
    assert set(fact["consumerHealth"]) == {"ref", "digest"}
    assert len(fact["requiredRawResults"]) == 16
    subject.validate_environment_acceptance_fact(
        fact,
        evidence_root=tmp_path,
        required_target_profiles=profiles,
    )

    wrong_target = deepcopy(fact)
    wrong_target["target"] = "alpha-proof"
    wrong_target["factId"] = subject.derive_fact_id(wrong_target)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="alpha-local"):
        subject.validate_environment_acceptance_fact(
            wrong_target,
            evidence_root=tmp_path,
            required_target_profiles=[],
        )

    promoted = deepcopy(fact)
    promoted["acceptanceProfile"] = "environment_promotion"
    promoted["factId"] = subject.derive_fact_id(promoted)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="fields are invalid"
    ):
        subject.validate_environment_acceptance_fact(
            promoted,
            evidence_root=tmp_path,
            required_target_profiles=[],
        )


def test_m1_api_consumer_rejects_app_raw_and_binding_derived_slot(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    first = fact["requiredRawResults"][0]
    path = tmp_path / first["ref"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.update({"producer": "app", "layer": "user_acceptance"})
    path.write_text(
        json.dumps(raw, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    first["digest"] = subject.exact_byte_digest(path)
    fact["factId"] = subject.derive_fact_id(fact)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="canonical ReadinessCaseResult"
    ):
        subject.validate_environment_acceptance_fact(
            fact,
            evidence_root=tmp_path,
            required_target_profiles=[],
        )


def test_m1_api_consumer_rejects_noncanonical_raw_and_missing_run_identity(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    first = fact["requiredRawResults"][0]
    for field in ("importRunId", "verifyRunId"):
        raw_path = tmp_path / first["ref"]
        original = json.loads(raw_path.read_text(encoding="utf-8"))
        broken = dict(original)
        broken.pop(field)
        raw_path.write_text(
            json.dumps(broken, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        first["digest"] = subject.exact_byte_digest(raw_path)
        fact["factId"] = subject.derive_fact_id(fact)
        with pytest.raises(
            subject.EnvironmentAcceptanceFactError,
            match="canonical ReadinessCaseResult",
        ):
            subject.validate_environment_acceptance_fact(
                fact, evidence_root=tmp_path, required_target_profiles=[]
            )
        raw_path.write_text(
            json.dumps(original, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )


def test_m1_api_consumer_rejects_promotion_fields_and_requires_consumer_health(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    for field, value in (
        ("activeCas", {}),
        ("lifecycleExit", {}),
        ("providerReadiness", {}),
        ("observabilityReadiness", {}),
        ("rollbackReadiness", {}),
        ("resourceFinalization", {}),
        ("targetBindingRefs", []),
    ):
        mixed = deepcopy(fact)
        mixed[field] = value
        with pytest.raises(
            subject.EnvironmentAcceptanceFactError, match="fields are invalid"
        ):
            subject.validate_environment_acceptance_fact(
                mixed, evidence_root=tmp_path, required_target_profiles=[]
            )
    missing_health = deepcopy(fact)
    missing_health.pop("consumerHealth")
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="fields are invalid"
    ):
        subject.validate_environment_acceptance_fact(
            missing_health, evidence_root=tmp_path, required_target_profiles=[]
        )


def test_data_readiness_rejects_status_alias_and_identity_drift(tmp_path: Path) -> None:
    fact, profiles = _build(tmp_path)
    readiness_path = tmp_path / fact["dataReadiness"]["ref"]
    canonical = json.loads(readiness_path.read_text(encoding="utf-8"))
    for mutation in (
        lambda value: (value.pop("passed"), value.update({"status": "passed"})),
        lambda value: value.update({"manifestDigest": "sha256:" + "9" * 64}),
        lambda value: value.update({"importRunId": "import-run-other"}),
        lambda value: value.update({"verifyRunId": "verify-run-other"}),
    ):
        broken = deepcopy(canonical)
        mutation(broken)
        readiness_path.write_text(
            json.dumps(broken, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        fact["dataReadiness"]["digest"] = subject.exact_byte_digest(readiness_path)
        fact["factId"] = subject.derive_fact_id(fact)
        with pytest.raises(
            subject.EnvironmentAcceptanceFactError, match="dataReadiness"
        ):
            subject.validate_environment_acceptance_fact(
                fact, evidence_root=tmp_path, required_target_profiles=profiles
            )


def test_m1_dual_digests_are_distinct_and_wrong_manifest_fails(tmp_path: Path) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    assert fact["releaseDigest"] == RELEASE_DIGEST
    assert fact["manifestDigest"] == MANIFEST_DIGEST
    assert fact["releaseDigest"] != fact["manifestDigest"]
    wrong = deepcopy(fact)
    wrong["manifestDigest"] = wrong["releaseDigest"]
    wrong["factId"] = subject.derive_fact_id(wrong)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="manifestDigest"):
        subject.validate_environment_acceptance_fact(
            wrong, evidence_root=tmp_path, required_target_profiles=[]
        )


def test_m1_source_fingerprint_is_recomputed_not_caller_authority(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    forged = deepcopy(fact)
    forged["sourceFingerprint"] = "sha256:" + "a" * 64
    forged["factId"] = subject.derive_fact_id(forged)
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="sourceFingerprint"
    ):
        subject.validate_environment_acceptance_fact(
            forged, evidence_root=tmp_path, required_target_profiles=[]
        )


def test_m1_health_binding_recurses_to_source_and_ignores_nonrequired_layers(
    tmp_path: Path,
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    health_path = tmp_path / arguments["consumer_health"]["ref"]
    binding = json.loads(health_path.read_text(encoding="utf-8"))
    source_path = tmp_path / binding["sourceHealth"]["ref"]
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["userAvailability"].extend(
        [
            {"name": "provider_ready", "status": "blocked", "issues": ["irrelevant"]},
            {"name": "device_bound", "status": "blocked", "issues": ["irrelevant"]},
            {
                "name": "content_live_passed",
                "status": "blocked",
                "issues": ["irrelevant"],
            },
        ]
    )
    source_path.write_text(
        json.dumps(source, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    binding["sourceHealth"]["digest"] = subject.exact_byte_digest(source_path)
    health_path.write_text(
        json.dumps(binding, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    arguments["consumer_health"]["digest"] = subject.exact_byte_digest(health_path)
    arguments["source_fingerprint"] = subject.derive_m1_source_fingerprint(
        environment="alpha",
        target="alpha-local",
        release_id="release-a",
        release_digest=RELEASE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
        import_run_id="import-run-a",
        verify_run_id="verify-run-a",
        sample_plan={
            "ref": arguments["sample_plan_ref"],
            "digest": arguments["sample_plan_digest"],
        },
        data_readiness=arguments["data_readiness"],
        consumer_health=arguments["consumer_health"],
        required_raw_results=arguments["required_raw_results"],
    )
    subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]

    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    source["userAvailability"][0]["status"] = "blocked"
    source_path.write_text(
        json.dumps(source, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    with pytest.raises(
        subject.EnvironmentAcceptanceFactError, match="exact-byte digest drifted"
    ):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=[]
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update({"http": None}), "requires HTTP facts"),
        (
            lambda value: value["http"].update({"status": 503}),
            "HTTP status is not 2xx",
        ),
        (
            lambda value: value.update({"runtimeObjectId": "runtime-drift"}),
            "runtimeObjectId did not match",
        ),
        (
            lambda value: value.update({"releaseDigest": "sha256:" + "8" * 64}),
            "identity drifted at releaseDigest",
        ),
    ],
)
def test_m1_observation_http_and_identity_are_strict(
    tmp_path: Path, mutation, message: str
) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    first = arguments["required_raw_results"][0]
    raw_path = tmp_path / first["ref"]
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    observation_path = tmp_path / raw["artifactPath"]
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    mutation(observation)
    observation_path.write_text(
        json.dumps(observation, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    raw["artifactSha256"] = subject.exact_byte_digest(observation_path).removeprefix(
        "sha256:"
    )
    raw_path.write_text(
        json.dumps(raw, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    first["digest"] = subject.exact_byte_digest(raw_path)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match=message):
        subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]


def test_m1_observation_missing_drift_and_symlink_are_blocked(tmp_path: Path) -> None:
    for mode, message in (
        ("missing", "missing"),
        ("bytes", "observation exact bytes drifted"),
        ("symlink", "linked"),
    ):
        root = tmp_path / mode
        root.mkdir()
        arguments, _ = _m1_api_evidence(root)
        first = arguments["required_raw_results"][0]
        raw = json.loads((root / first["ref"]).read_text(encoding="utf-8"))
        observation_path = root / raw["artifactPath"]
        if mode == "missing":
            observation_path.unlink()
        elif mode == "bytes":
            observation_path.write_bytes(observation_path.read_bytes() + b" ")
        else:
            outside = root / "outside-observation.json"
            outside.write_bytes(observation_path.read_bytes())
            observation_path.unlink()
            observation_path.symlink_to(outside)
        with pytest.raises(subject.EnvironmentAcceptanceFactError, match=message):
            subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
