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
SCHEMA_PATH = ROOT / "quwoquan_ops/environments/evidence/environment_acceptance_fact.schema.json"
RELEASE_DIGEST = "sha256:" + "1" * 64
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
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
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
    root: Path, environment: str = "alpha", target: str = "alpha-local",
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
                "sampleId": "m100-article-001",
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
            active_cas={"ref": f"{environment}/binding-active-cas.json", "digest": "sha256:" + "8" * 64},
            readback={"ref": f"{environment}/binding-readback.json", "digest": "sha256:" + "9" * 64},
            artifact_class="production" if device_profile == "production" else "production_behavior",
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
                "class": "physical" if physical else ("emulator" if platform == "android" else "simulator"),
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
        binding_ref = _write_json(root, f"{environment}/binding-{platform}.json", binding)
        bindings.append({**binding_ref, **profile})
        slot_id = subject.required_raw_slot_id(
            target_uat_binding_digest=binding_ref["digest"],
            sample_id="m100-article-001",
            entry_surface="feed",
            carrier="article",
            spec_ref=SPEC_REF,
            runner_identity=RUNNER,
        )
        raw = {
            **identity,
            "producer": "app", "layer": "user_acceptance", "status": "passed",
            "caseId": "m100-article-001", "objectId": "article-001",
            "targetUatBindingDigest": binding_ref["digest"],
            "objectId": "article-001",
            "entrySurface": "feed", "carrier": "article", "specRef": SPEC_REF,
            "runnerIdentity": RUNNER, "platform": platform,
            "provider": "first-party-https", "uatProfile": device_profile,
        }
        raw_ref = _write_json(root, f"{environment}/raw-{platform}.json", raw)
        raw_results.append({**raw_ref, "slotId": slot_id, "status": "passed"})

    def ready(name: str, status: str) -> dict[str, str]:
        return _write_json(root, f"{environment}/{name}.json", {**identity, "status": status})

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
        "data_readiness": _write_json(root, f"{environment}/data-readiness.json", {
            **identity, "status": "passed",
            "activationEnvelope": {
                "importReportRef": ready("import-report", "imported")["ref"],
                "importReportDigest": ready("import-report", "imported")["digest"],
            },
        }),
        "active_cas": {
            "ref": cas["ref"], "digest": cas["digest"],
            "readbackRef": cas_readback["ref"], "readbackDigest": cas_readback["digest"],
            "releaseId": "release-a", "releaseDigest": RELEASE_DIGEST,
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


def _build(root: Path, **changes: object) -> tuple[dict[str, object], list[dict[str, str]]]:
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
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return subject.exact_byte_digest(path)


def test_schema_fact_has_no_verdict_and_fact_id_is_deterministic(tmp_path: Path) -> None:
    fact, profiles = _build(tmp_path)
    _schema_validator().validate(fact)
    assert fact["schema"] == subject.SCHEMA
    assert len(fact["targetBindingRefs"]) == len(PROFILES)
    assert all("targetUatBindingDigest" in json.loads((tmp_path / raw["ref"]).read_text(encoding="utf-8")) for raw in fact["requiredRawResults"])
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
def test_fact_rejects_independent_outcome_fields(tmp_path: Path, forbidden: str) -> None:
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
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="coverage drifted"):
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
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="bundle substitution"):
        subject.validate_environment_acceptance_fact(
            bundle, evidence_root=tmp_path, required_target_profiles=profiles
        )


def test_sample_plan_and_profile_coverage_bind_each_raw_to_target_binding(tmp_path: Path) -> None:
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
            fact, evidence_root=tmp_path,
            required_target_profiles=[{"platform": "android", "deviceProfile": "promotable"}],
        )
    cross_binding = deepcopy(fact)
    raw_ref = cross_binding["requiredRawResults"][0]["ref"]
    digest = _rewrite(tmp_path, raw_ref, lambda value: value.update({"targetUatBindingDigest": "sha256:" + "8" * 64}))
    cross_binding["requiredRawResults"][0]["digest"] = digest
    cross_binding["factId"] = subject.derive_fact_id(cross_binding)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="not directly listed"):
        subject.validate_environment_acceptance_fact(
            cross_binding, evidence_root=tmp_path, required_target_profiles=profiles
        )




def test_raw_object_must_match_sample_plan_exact_object(tmp_path: Path) -> None:
    fact, profiles = _build(tmp_path)
    raw_ref = fact["requiredRawResults"][0]["ref"]
    digest = _rewrite(
        tmp_path, raw_ref,
        lambda value: value.update({"objectId": "article-999"}),
    )
    fact["requiredRawResults"][0]["digest"] = digest
    fact["factId"] = subject.derive_fact_id(fact)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="sample-plan object"):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=profiles
        )


@pytest.mark.parametrize(
    "field,ref_getter",
    [
        ("dataReadiness", lambda fact: fact["dataReadiness"]),
        ("activeCas", lambda fact: {"ref": fact["activeCas"]["ref"], "digest": fact["activeCas"]["digest"]}),
        ("activeCas.readback", lambda fact: {"ref": fact["activeCas"]["readbackRef"], "digest": fact["activeCas"]["readbackDigest"]}),
        ("lifecycleExit", lambda fact: fact["lifecycleExit"]),
        ("providerReadiness", lambda fact: fact["providerReadiness"]),
        ("observabilityReadiness", lambda fact: fact["observabilityReadiness"]),
        ("rollbackReadiness", lambda fact: fact["rollbackReadiness"]),
    ],
)
def test_authority_exact_byte_drift_blocks(tmp_path: Path, field: str, ref_getter) -> None:
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
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="must be non-empty"):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=profiles
        )


def _write_fact(root: Path, fact: dict[str, object], profiles: list[dict[str, str]]) -> tuple[str, str]:
    store = root / "facts"
    store.mkdir(exist_ok=True)
    path = subject.write_environment_acceptance_fact(
        root=store, fact=fact, evidence_root=root, required_target_profiles=profiles
    )
    ref = path.relative_to(root).as_posix()
    return ref, subject.exact_byte_digest(path)


def test_predecessor_mapping_fact_id_and_exact_digest_are_strict(tmp_path: Path) -> None:
    alpha, alpha_profiles = _build(tmp_path)
    alpha_ref, alpha_digest = _write_fact(tmp_path, alpha, alpha_profiles)
    arguments, profiles = _evidence(tmp_path, "beta", "beta-local")
    predecessor = {
        "environment": "alpha", "factId": alpha["factId"],
        "ref": alpha_ref, "digest": alpha_digest,
    }
    arguments["predecessor_acceptance"] = predecessor
    beta = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    assert beta["predecessorAcceptance"]["factId"] == alpha["factId"]
    for mutation, message in (
        (lambda value: value.update({"environment": "gamma"}), "exactly alpha"),
        (lambda value: value.update({"factId": "sha256:" + "9" * 64}), "identity drifted"),
        (lambda value: value.update({"digest": "sha256:" + "8" * 64}), "exact bytes drifted"),
    ):
        wrong = deepcopy(predecessor)
        mutation(wrong)
        with pytest.raises(subject.EnvironmentAcceptanceFactError, match=message):
            subject.validate_predecessor_acceptance(
                environment="beta", predecessor_acceptance=wrong,
                evidence_root=tmp_path, release_id="release-a", release_digest=RELEASE_DIGEST,
            )
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="must not provide"):
        subject.validate_predecessor_acceptance(
            environment="alpha", predecessor_acceptance=predecessor,
            evidence_root=tmp_path, release_id="release-a", release_digest=RELEASE_DIGEST,
        )


def _prod_release_facts(root: Path) -> dict[str, object]:
    identity = _identity("prod", "prod-hosted")
    def fact(name: str, status: str, **extra: str) -> dict[str, str]:
        return _write_json(root, f"prod/{name}.json", {**identity, "status": status, **extra})
    return {
        "engineeringEligibility": fact("engineering", "eligible", factType="engineeringEligibility"),
        "durableApproval": fact("approval", "approved", factType="durableApproval"),
        "rolloutStages": [
            {"stage": stage, **fact(f"rollout-{stage}", "completed", factType="rolloutStage", stage=stage)}
            for stage in subject.PROD_ROLLOUT_STAGES
        ],
        "rollbackReadiness": fact("prod-rollback", "ready", factType="rollbackReadiness"),
    }


def test_prod_requires_canonical_release_fact_roles_and_rollout_order(tmp_path: Path) -> None:
    # Use a structurally valid predecessor from an explicit gamma fact.
    gamma_args, gamma_profiles = _evidence(tmp_path, "gamma", "gamma-local")
    # A gamma fact itself needs beta; this test isolates prod release fact validation by
    # first building a real alpha/beta/gamma chain.
    predecessor = None
    for environment, target in (("alpha", "alpha-local"), ("beta", "beta-local"), ("gamma", "gamma-local")):
        args, chain_profiles = _evidence(tmp_path, environment, target)
        args["predecessor_acceptance"] = predecessor
        chain_fact = subject.build_environment_acceptance_fact(**args)  # type: ignore[arg-type]
        ref, digest = _write_fact(tmp_path, chain_fact, chain_profiles)
        predecessor = {"environment": environment, "factId": chain_fact["factId"], "ref": ref, "digest": digest}
    prod_args, profiles = _evidence(
        tmp_path, "prod", "prod-hosted",
        ({"platform": "android", "deviceProfile": "production"},),
    )
    prod_args["predecessor_acceptance"] = predecessor
    prod_args["prod_release_facts"] = _prod_release_facts(tmp_path)
    fact = subject.build_environment_acceptance_fact(**prod_args)  # type: ignore[arg-type]
    _schema_validator().validate(fact)
    missing = deepcopy(fact)
    missing["prodReleaseFacts"]["rolloutStages"].pop(2)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="canary/5/20/50/100"):
        subject.validate_environment_acceptance_fact(
            missing, evidence_root=tmp_path, required_target_profiles=profiles
        )
    wrong_order = deepcopy(fact)
    wrong_order["prodReleaseFacts"]["rolloutStages"][0], wrong_order["prodReleaseFacts"]["rolloutStages"][1] = wrong_order["prodReleaseFacts"]["rolloutStages"][1], wrong_order["prodReleaseFacts"]["rolloutStages"][0]
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
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="duplicate JSON key"):
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
            linked_fact, evidence_root=clean_root, required_target_profiles=linked_profiles
        )


def test_create_once_helper_is_idempotent_append_only_and_nofollow(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    store = tmp_path / "store"
    store.mkdir()
    fact, profiles = _build(evidence)
    first = subject.write_environment_acceptance_fact(
        root=store, fact=fact, evidence_root=evidence, required_target_profiles=profiles
    )
    assert first.relative_to(store).as_posix() == subject.environment_acceptance_fact_relative_path(fact)
    inode = (first.stat().st_dev, first.stat().st_ino)
    replay = subject.write_environment_acceptance_fact(
        root=store, fact=deepcopy(fact), evidence_root=evidence,
        required_target_profiles=profiles,
    )
    assert replay == first and (first.stat().st_dev, first.stat().st_ino) == inode

    # A distinct authority fingerprint yields another append-only fact, not replacement.
    newer = deepcopy(fact)
    newer["sourceFingerprint"] = "sha256:" + "e" * 64
    newer["factId"] = subject.derive_fact_id(newer)
    second = subject.write_environment_acceptance_fact(
        root=store, fact=newer, evidence_root=evidence, required_target_profiles=profiles
    )
    assert second != first and first.exists() and second.exists()

    first.chmod(0o644)
    first.write_bytes(b"{}")
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="different exact bytes"):
        subject.write_environment_acceptance_fact(
            root=store, fact=fact, evidence_root=evidence,
            required_target_profiles=profiles,
        )

    linked_store = tmp_path / "linked-store"
    linked_store.symlink_to(store, target_is_directory=True)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="non-symlink"):
        subject.write_environment_acceptance_fact(
            root=linked_store, fact=newer, evidence_root=evidence,
            required_target_profiles=profiles,
        )


def test_release_order_projection_uses_fact_existence_not_passed_field(tmp_path: Path) -> None:
    fact, profiles = _build(tmp_path)
    ref, _ = _write_fact(tmp_path, fact, profiles)
    view = order_view.derive_environment_release_order_view(
        release_id="release-a", derived_at="2026-08-29T08:00:00Z",
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
    plan = json.loads((root / str(arguments["sample_plan_ref"])).read_text(encoding="utf-8"))
    plan["samples"] = [
        {
            "sampleId": f"m1-{carrier}-001",
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
            **_identity("alpha", "alpha-local"),
            "producer": "service",
            "layer": "api_integration",
            "status": "passed",
            "entrySurface": cell["entry"],
            "carrier": cell["carrier"],
            "specRef": cell["specRef"],
            "runnerIdentity": cell["runnerClass"],
            "objectId": sample["objectId"],
        }
        raw_ref = _write_json(
            root,
            f"alpha/m1-raw-{cell['entry']}-{cell['carrier']}.json",
            raw,
        )
        results.append({
            **raw_ref,
            "slotId": subject.required_raw_slot_id(
                sample_id=sample["sampleId"],
                entry_surface=cell["entry"],
                carrier=cell["carrier"],
                spec_ref=cell["specRef"],
                runner_identity=cell["runnerClass"],
            ),
            "status": "passed",
        })
    arguments["required_raw_results"] = results
    return arguments, []


def test_m1_api_consumer_is_alpha_service_only_without_promotion_authority(tmp_path: Path) -> None:
    arguments, profiles = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    _schema_validator().validate(fact)
    assert fact["acceptanceProfile"] == "m1_api_consumer"
    assert fact["environment"] == "alpha" and fact["target"] == "alpha-local"
    assert fact["targetBindingRefs"] == []
    assert len(fact["requiredRawResults"]) == 16
    subject.validate_environment_acceptance_fact(
        fact, evidence_root=tmp_path, required_target_profiles=profiles,
    )

    wrong_target = deepcopy(fact)
    wrong_target["target"] = "alpha-proof"
    wrong_target["factId"] = subject.derive_fact_id(wrong_target)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="alpha-local"):
        subject.validate_environment_acceptance_fact(
            wrong_target, evidence_root=tmp_path, required_target_profiles=[],
        )

    promoted = deepcopy(fact)
    promoted["acceptanceProfile"] = "environment_promotion"
    promoted["factId"] = subject.derive_fact_id(promoted)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="non-empty"):
        subject.validate_environment_acceptance_fact(
            promoted, evidence_root=tmp_path, required_target_profiles=[],
        )


def test_m1_api_consumer_rejects_app_raw_and_binding_derived_slot(tmp_path: Path) -> None:
    arguments, _ = _m1_api_evidence(tmp_path)
    fact = subject.build_environment_acceptance_fact(**arguments)  # type: ignore[arg-type]
    first = fact["requiredRawResults"][0]
    path = tmp_path / first["ref"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.update({"producer": "app", "layer": "user_acceptance"})
    path.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    first["digest"] = subject.exact_byte_digest(path)
    fact["factId"] = subject.derive_fact_id(fact)
    with pytest.raises(subject.EnvironmentAcceptanceFactError, match="Service API integration"):
        subject.validate_environment_acceptance_fact(
            fact, evidence_root=tmp_path, required_target_profiles=[],
        )
