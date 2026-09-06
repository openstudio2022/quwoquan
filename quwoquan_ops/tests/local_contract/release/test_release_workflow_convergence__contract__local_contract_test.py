"""Permanent atomic release-chain workflow convergence contracts.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t2
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t3
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t4
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t5
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t1
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t1
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t2
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-wave-deployment/spec.md#gwt-001.t2
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#gwt-001.t1
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#gwt-001.t2
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#gwt-001.t3
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = ROOT / ".github/workflows"
DELIVERY = WORKFLOWS / "delivery-gate.yml"
QUALIFICATION = WORKFLOWS / "release-qualification.yml"
TAG_SELECTION = WORKFLOWS / "release-tag-selection.yml"
PROD = WORKFLOWS / "deploy-prod-auto.yml"
TIMING_BUDGETS = ROOT / "quwoquan_ops/environments/pr_gate_timing_budgets.json"
PROMOTION_RATCHET = ROOT / "quwoquan_ops/policies/promotion_timing_ratchet.yaml"
RELEASE_POLICY = ROOT / "quwoquan_ops/policies/release_selection_policy.yaml"
RELEASE_QUALIFICATION = ROOT / "quwoquan_ops/ci/release_qualification.py"
RELEASE_TAG_ADMISSION = ROOT / "quwoquan_ops/ci/release_tag_admission.py"
QUALIFIED_PROD = ROOT / "quwoquan_ops/ci/qualified_prod.py"
RELEASE_CONTROL = ROOT / "quwoquan_ops/ci/release_control.py"

LEGACY_WORKFLOWS = (
    "pre-release-gate.yml",
    "app-env-device-matrix-self-hosted.yml",
    "beta-device-platform.yml",
    "provider-release-evidence.yml",
)
PERMANENT_WORKFLOWS = (
    "delivery-gate.yml",
    "release-qualification.yml",
    "release-tag-selection.yml",
    "deploy-prod-auto.yml",
)
FORBIDDEN_RELEASE_TOKENS = (
    "latestQualified",
    "latest-qualified",
    "RELEASED_RELEASE_EVIDENCE_REF",
    "RELEASED_TAG",
    "RELEASED_VERSION",
    "vars.RELEASED",
    "dry_run",
    "dry-run",
)
PLACEHOLDER_TOKENS = (
    "python3 -B -m py_compile",
    "pending-controller-output",
    "verified-pre-push-local-admission",
    "The existing pinned service/app factories",
    "must now publish creator/ruleset readback facts",
    "unreachable until",
    "transport must expose",
)


def load_workflow(path: Path) -> tuple[str, dict[str, Any]]:
    source = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    assert isinstance(workflow, dict)
    return source, workflow


def trigger(workflow: dict[str, Any]) -> dict[str, Any]:
    value = workflow[True]
    assert isinstance(value, dict)
    return value


def commands(job: dict[str, Any]) -> str:
    return "\n".join(str(step.get("run") or "") for step in job.get("steps", []))


def function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


def test_delivery_gate_is_verify_only_and_excludes_heavy_execution() -> None:
    source, workflow = load_workflow(DELIVERY)
    assert set(workflow["jobs"]) == {"promotion_verify", "main_source_seal", "system_backsync"}
    assert set(trigger(workflow)) == {"pull_request", "push"}
    assert trigger(workflow)["pull_request"]["branches"] == ["main"]
    assert trigger(workflow)["push"]["branches"] == ["main"]
    assert workflow["jobs"]["promotion_verify"]["if"] == "${{ github.event_name == 'pull_request' }}"
    assert workflow["jobs"]["main_source_seal"]["if"] == "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
    caller = workflow["jobs"]["system_backsync"]
    assert caller["needs"] == "main_source_seal"
    assert caller["if"] == "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
    assert caller["uses"] == "./.github/workflows/system-backsync.yml"
    assert "steps" not in caller
    assert "secrets" not in caller
    assert "promotion-admit" in source
    assert "promotion_evidence.py main-seal" in source
    assert "validate-hosted-handoff" in source
    assert "oras resolve" not in source
    assert '"promotion_admission_ref"' not in source

    executable = "\n".join(
        line.strip()
        for job in workflow["jobs"].values()
        for line in commands(job).splitlines()
        if not line.strip().startswith("echo")
    ).casefold()
    forbidden = (
        "build_", "stackctl", "flutter", "gradle", "xcode",
        "app_tests", "service_pipeline", "provider live", "device matrix",
        "self-hosted", "runs-on: macos", "environment: production",
        "python3 -b -m py_compile",
    )
    for token in forbidden:
        assert token not in executable, f"delivery-gate regained heavy operation: {token}"


def test_release_workflows_are_dispatch_only_and_single_responsibility() -> None:
    qualification_source, qualification = load_workflow(QUALIFICATION)
    selection_source, selection = load_workflow(TAG_SELECTION)
    prod_source, prod = load_workflow(PROD)

    for workflow in (qualification, selection, prod):
        assert set(trigger(workflow)) == {"workflow_dispatch"}
    assert set(qualification["jobs"]) == {
        "allocate_build_number", "service_factory", "app_factory",
        "materialize_candidate",
    }
    assert set(selection["jobs"]) == {"pre_admission", "create_and_readback"}
    assert set(prod["jobs"]) == {
        "prod_activation_admission", "prod_rollout", "post_release_soak",
    }

    assert "git tag -a" not in qualification_source
    assert "stackctl.py deploy" not in qualification_source
    assert "build, sign and attest once" in qualification_source.casefold()
    assert "git tag -a" in selection_source
    assert "stackctl.py deploy" not in selection_source
    assert "build_sign_attest_once" not in selection_source
    assert "git tag -a" not in prod_source
    assert "stackctl.py deploy --target prod-hosted" in prod_source
    assert "build_sign_attest_once" not in prod_source
    for command in (
        "prod-admit", "prod-stage-append", "prod-terminal-release",
        "prod-rollback", "prod-soak",
    ):
        assert command in prod_source
    permanent_source = "\n".join(
        (qualification_source, selection_source, prod_source)
    )
    for token in PLACEHOLDER_TOKENS:
        assert token not in permanent_source, f"placeholder release path remains: {token}"


def test_main_push_only_creates_source_seal_not_build_tag_or_prod() -> None:
    delivery_source, delivery = load_workflow(DELIVERY)
    assert set(trigger(delivery)) == {"pull_request", "push"}
    assert trigger(delivery)["push"] == {"branches": ["main"]}
    post_commands = commands(delivery["jobs"]["main_source_seal"])
    caller = delivery["jobs"]["system_backsync"]
    assert "promotion_evidence.py main-seal" in post_commands
    assert caller["needs"] == "main_source_seal"
    assert caller["with"]["expected_dev_before"] == "${{ needs.main_source_seal.outputs.source_sha }}"
    assert caller["with"]["source_sha"] == "${{ needs.main_source_seal.outputs.source_sha }}"
    for forbidden in ("git tag -a", "stackctl.py deploy", "build_sign_attest_once"):
        assert forbidden not in post_commands
    for path in (QUALIFICATION, TAG_SELECTION, PROD):
        source, workflow = load_workflow(path)
        assert "push" not in trigger(workflow), f"{path.name} must not react to main push"
        assert "github.event_name == 'push'" not in source
    assert set(trigger(load_workflow(QUALIFICATION)[1])) == {"workflow_dispatch"}
    assert set(trigger(load_workflow(TAG_SELECTION)[1])) == {"workflow_dispatch"}
    assert set(trigger(load_workflow(PROD)[1])) == {"workflow_dispatch"}


def test_rc_factory_builds_once_and_finalizes_exact_qualification_facts() -> None:
    source, workflow = load_workflow(QUALIFICATION)
    inputs = trigger(workflow)["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "rc_tag_admission_ref", "qualification_request_ref",
        "source_git_sha", "product_version_manifest_ref",
        "package_acceptance_fact_ref", "provider_fact_ref",
        "uat_fact_ref", "supply_chain_fact_ref",
    }
    assert all(value["required"] is True for value in inputs.values())
    assert "@sha256" in inputs["rc_tag_admission_ref"]["description"]
    assert "release_control.py" in source
    assert "qualification-material" in source
    assert "qualification-finalize" in source
    assert workflow["jobs"]["allocate_build_number"]["environment"] == "release-qualification"
    assert workflow["jobs"]["materialize_candidate"]["environment"] == "release-qualification"
    assert workflow["jobs"]["service_factory"]["uses"] == "./.github/workflows/service_pipeline.yml"
    assert workflow["jobs"]["app_factory"]["uses"] == "./.github/workflows/app_pipeline.yml"
    for fact in ("package acceptance", "provider", "uat", "supply-chain"):
        assert fact.casefold() in source.casefold()
    assert "materialize_evidence_oci.py" in source
    assert '--service-material "$SERVICE_MATERIAL_EXACT"' in source
    assert '--app-material "$APP_MATERIAL_EXACT"' in source
    assert "actual OCI payload lacks canonical manifest.json" in source

    definitions = function_names(RELEASE_QUALIFICATION)
    assert {
        "create_qualification_request",
        "create_candidate_material_from_factory_outputs",
        "create_qualification_fact",
    } <= definitions
    material = function_source(
        RELEASE_QUALIFICATION, "create_candidate_material_from_factory_outputs"
    )
    finalized = function_source(RELEASE_QUALIFICATION, "create_qualification_fact")
    for token in (
        '_canonical_material(',
        '_validate_service_factory_material(',
        '_validate_app_factory_material(',
        '"reusable factory scalar drifted from actual material bytes"',
        '"buildPolicy": "build_sign_attest_once"',
        '"artifactBuildNumber": build_number',
        '"factoryOutputs": factory_outputs',
        '"supplyChainSubjects": [app_locator, service_locator]',
        '"artifactByteDigests": exact_artifact_digests',
    ):
        assert token in material
    for token in (
        '"packageAcceptance"',
        '"provider"',
        '"uat"',
        '"supplyChain"',
        '["android", "ios"]',
        '"decision": "qualified"',
    ):
        assert token in finalized


def test_stable_reuses_qualified_rc_material_and_admits_after_readback() -> None:
    selection_source, workflow = load_workflow(TAG_SELECTION)
    inputs = trigger(workflow)["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "tag_kind", "tag_name", "source_git_sha", "selection_fact_ref",
        "initial_release_authority_ref", "selected_rc_admission_ref",
        "qualification_fact_ref", "release_authority_fact_ref",
    }
    assert inputs["tag_kind"]["options"] == ["rc", "stable"]
    assert "! git ls-remote --exit-code --tags" in selection_source
    admit_rc = selection_source.index("tag-admit-rc-intent")
    admit_stable = selection_source.index("tag-admit-stable-intent")
    create_local = selection_source.index('git tag -a "$TAG" "$SOURCE_SHA"')
    push = selection_source.index('git push origin "refs/tags/$TAG:refs/tags/$TAG"')
    tag_readback = selection_source.index('/git/ref/tags/${TAG}', push)
    outcome = selection_source.index("OUTCOME_RESULT=", tag_readback)
    hosted_readback = selection_source.index("post_readback post_mutation", outcome)
    finalize = selection_source.index('"tag-admit-$KIND-finalize"', hosted_readback)
    assert admit_rc < create_local < push < tag_readback < outcome < hosted_readback < finalize
    assert admit_stable < create_local < push < tag_readback < outcome < hosted_readback < finalize
    assert "tag-mutation-outcome" in selection_source[outcome:hosted_readback]

    policy = yaml.safe_load(RELEASE_POLICY.read_text(encoding="utf-8"))
    assert policy["stableSelection"]["source"] == "one_exact_qualified_rc"
    assert policy["stableSelection"]["rebuild"] == "denied"
    assert policy["stableSelection"]["requiredExactBindings"] == [
        "peeledCommit",
        "sourceTree",
        "candidateMaterialManifest",
        "artifactBuildNumber",
        "artifactDigests",
        "qualificationFact",
        "productVersionManifestDigest",
        "productAuthorityFact",
        "releaseAuthorityFact",
    ]

    definitions = function_names(RELEASE_TAG_ADMISSION)
    assert "admit_release_tag" not in definitions
    for callable_name in (
        "create_release_tag_intent",
        "record_tag_mutation_outcome",
        "finalize_release_tag_admission",
    ):
        assert callable_name in definitions

    stable_intent = function_source(RELEASE_TAG_ADMISSION, "create_release_tag_intent")
    qualified_material = function_source(RELEASE_TAG_ADMISSION, "_validate_stable_authorities")
    mutation_outcome = function_source(RELEASE_TAG_ADMISSION, "record_tag_mutation_outcome")
    created_outcome = function_source(RELEASE_TAG_ADMISSION, "_created_outcome")
    final_readbacks = function_source(RELEASE_TAG_ADMISSION, "_final_readbacks")
    final_admission = function_source(RELEASE_TAG_ADMISSION, "finalize_release_tag_admission")

    assert """authorities = _validate_stable_authorities(
        root=root, tag_name=tag_name, source=source, version=version,
        manifest_digest=manifest_digest, selected_rc_admission_ref=selected_rc_admission_ref,
        qualification_fact_ref=qualification_fact_ref,
        product_authority_fact_ref=product_authority_fact_ref,
        release_authority_fact_ref=release_authority_fact_ref,
    )""" in stable_intent
    assert """if (
        rc.get("schema") != RC_SCHEMA or rc.get("decision") != "admitted"
        or rc.get("productVersion") != version
        or rc.get("peeledCommit") != source["peeledCommit"]
        or rc.get("sourceTree") != source["sourceTree"]
        or rc.get("productVersionManifestDigest") != manifest_digest
    )""" in qualified_material
    assert """if (
        qualification.get("schema") != QUALIFICATION_SCHEMA
        or qualification.get("decision") != "qualified"
        or material.get("schema") != MATERIAL_SCHEMA
        or qualification.get("tagName") != rc.get("tagName")
        or qualification.get("sourceGitSha") != source["peeledCommit"]
        or qualification.get("sourceTree") != source["sourceTree"]
        or qualification.get("artifactBuildNumber") != material.get("artifactBuildNumber")
        or qualified_artifacts != material_artifacts
        or qualification.get("candidateMaterialManifest") != material_exact
        or material.get("sourceGitSha") != source["peeledCommit"]
        or material.get("sourceTree") != source["sourceTree"]
        or material.get("tagName") != rc.get("tagName")
        or material.get("productVersionManifest", {}).get("digest") != manifest_digest
    )""" in qualified_material
    assert """candidate_identity = digest({
        "peeledCommit": source["peeledCommit"], "sourceTree": source["sourceTree"],
        "artifactBuildNumber": material["artifactBuildNumber"], "artifacts": material_artifacts,
    })""" in qualified_material
    assert """return {
        "selectedRcAdmission": rc_exact, "selectedRcTagName": rc["tagName"],
        "selectedRcTagObjectOid": rc["tagObjectOid"],
        "qualificationFact": qualification_exact, "qualificationId": qualification_id,
        "candidateMaterialManifest": material_exact, "candidateMaterialId": material_id,
        "candidateIdentity": candidate_identity,
        "artifactBuildNumber": material["artifactBuildNumber"], "artifacts": material_artifacts,
        "productAuthorityFact": product_exact, "releaseAuthorityFact": release_exact,
    }""" in qualified_material
    assert """body: dict[str, Any] = {
        "schema": INTENT_SCHEMA, "decision": "mutation_admitted",
        **tag, "productVersion": version, "reservation": reservation,
        **authorities, "productVersionManifestDigest": manifest_digest,
        "releaseSelectionPolicyDigest": policy_digest,
        "repository": repository_identity, "controllerProducer": producer,
        "preCreatorReadback": creator, "preRulesetReadback": ruleset,
        "admittedAt": _timestamp(admitted_at, "admittedAt"),
    }""" in stable_intent
    assert 'return _write_once(_intent_path(root, "stable", tag_name), body)' in stable_intent

    assert 'if status == "created" and commit != intent.get("peeledCommit"):' in mutation_outcome
    assert """body: dict[str, Any] = {
        "schema": MUTATION_SCHEMA, "intent": intent_exact,
        "intentId": intent["intentId"], "tagKind": tag_kind,
        "tagName": tag_name, "status": status,
        "tagObjectOid": object_oid, "peeledCommit": commit,
        "recordedAt": _timestamp(recorded_at, "recordedAt"),
    }""" in mutation_outcome
    assert 'return _write_once(_outcome_path(root, intent["intentId"]), body)' in mutation_outcome
    assert """if (
        set(outcome) != {
            "schema", "outcomeId", "intent", "intentId", "tagKind",
            "tagName", "status", "tagObjectOid", "peeledCommit", "recordedAt",
        }
        or outcome.get("schema") != MUTATION_SCHEMA
        or outcome.get("intent") != dict(intent_exact)
        or outcome.get("intentId") != intent.get("intentId")
        or outcome.get("tagKind") != intent.get("tagKind")
        or outcome.get("tagName") != tag["tagName"]
        or outcome.get("status") != "created"
        or outcome.get("tagObjectOid") != tag["tagObjectOid"]
        or outcome.get("peeledCommit") != tag["peeledCommit"]
    )""" in created_outcome

    assert """outcome_fact, outcome = _created_outcome(
        root, intent, intent_exact, mutation_outcome_ref, tag=tag,
    )""" in final_admission
    assert """creator, ruleset = _final_readbacks(
        root, intent=intent, tag=tag, outcome=outcome_fact,
        creator_ref=creator_readback_ref, ruleset_ref=ruleset_readback_ref,
        admitted_at=admitted_at,
    )""" in final_admission
    assert """outcome_id = _digest(outcome.get("outcomeId"), "mutationOutcome.outcomeId")
    creator, creator_at = _creator_readback(
        root, creator_ref, phase="post_mutation", tag_name=tag["tagName"],
        tag=tag, producer=producer, repository=repository,
        outcome_id=outcome_id,
    )
    ruleset, ruleset_at, post_ruleset_identity = _ruleset_readback(
        root, ruleset_ref, phase="post_mutation", tag_name=tag["tagName"],
        tag=tag, producer=producer, repository=repository,
    )""" in final_readbacks
    assert """if pre_ruleset_identity != post_ruleset_identity:
        _fail(
            "RELEASE_TAG.READBACK_INVALID",
            "ruleset id or version drifted during mutation",
        )""" in final_readbacks
    assert """if (
        max(pre_creator_at, pre_ruleset_at) > intent_at
        or not (intent_at <= outcome_at <= min(creator_at, ruleset_at))
        or max(creator_at, ruleset_at) > final_at
    )""" in final_readbacks
    assert """carried = {key: intent[key] for key in (
        "selectedRcAdmission", "selectedRcTagName", "selectedRcTagObjectOid",
        "qualificationFact", "qualificationId", "candidateMaterialManifest",
        "candidateMaterialId", "candidateIdentity", "artifactBuildNumber", "artifacts",
        "productAuthorityFact", "releaseAuthorityFact",
    )}""" in final_admission
    assert """"admissionIntent": intent_exact, "mutationOutcome": outcome,
        "creatorReadback": creator, "rulesetReadback": ruleset,""" in final_admission
    assert 'return _write_once(root / "release-tags" / "stable" / tag_name / "admission.json", body)' in final_admission


def test_prod_accepts_only_stable_admission_exact_oci_and_orders_rollout() -> None:
    source, workflow = load_workflow(PROD)
    inputs = trigger(workflow)["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "release_tag_admission_ref",
        "previous_active_released_ledger_ref",
        "rollback_readiness_ref",
    }
    assert inputs["release_tag_admission_ref"]["required"] is True
    assert "stable ReleaseTagAdmissionFact" in inputs["release_tag_admission_ref"]["description"]
    assert "@sha256" in inputs["release_tag_admission_ref"]["description"]
    assert "release_control.py" in source
    assert "prod-admit" in source
    assert "pending-controller-output" not in source
    assert "python3 -B -m py_compile" not in source

    jobs = workflow["jobs"]
    assert jobs["prod_rollout"]["needs"] == "prod_activation_admission"
    assert jobs["post_release_soak"]["needs"] == "prod_rollout"
    assert jobs["prod_activation_admission"]["environment"] == "production"
    assert jobs["prod_rollout"]["environment"] == "production"
    assert jobs["post_release_soak"]["environment"] == "production"
    assert "ProdActivationAdmissionFact" in source
    assert source.index("prod_activation_admission:") < source.index("prod_rollout:")
    assert "for stage in canary 5 20 50 100" in source
    assert source.count("stackctl.py deploy --target prod-hosted") == 1

    admission = function_source(QUALIFIED_PROD, "create_prod_activation_admission")
    for token in (
        "releaseTagAdmission",
        'tag.get("schema") != "quwoquan_ops.release_tag_admission_fact.v1"',
        "Prod requires admitted stable SemVer tag",
        "tag and qualification exact OCI artifacts drifted",
        '"createdBeforeStage": "canary"',
    ):
        assert token in admission


def test_prod_materialized_input_is_consumed_inside_rollout_store() -> None:
    source, workflow = load_workflow(PROD)
    activation_steps = [
        step
        for step in workflow["jobs"]["prod_rollout"]["steps"]
        if step.get("id") == "activation_input"
    ]
    assert len(activation_steps) == 1
    activation = str(activation_steps[0]["run"])
    rollout = commands(workflow["jobs"]["prod_rollout"])

    canonical_output = "$STORE/$ADMISSION_LOCAL_REF"
    assert activation.count("prod-materialize-input") == 1
    assert source.count("prod-materialize-input") == 1
    assert 'STORE="$RUNNER_TEMP/release-control"' in activation
    assert 'ADMISSION_LOCAL_REF="activation-input.json"' in activation
    assert f'--output "{canonical_output}"' in activation
    assert '--github-output "$GITHUB_OUTPUT"' in activation
    assert 'envelope.get("prodActivationAdmission") != {"ref": admission_ref, "digest": admission_digest}' in activation
    assert rollout.count("--prod-activation-admission") == 1
    assert '--prod-activation-admission "$STORE/$ADMISSION_LOCAL_REF"' in rollout
    assert "$RUNNER_TEMP/prod-activation-input.json" not in source
    for retired in (
        "QWQ_ENVIRONMENT_ACCEPTANCE_ROOT",
        "PROD_ENVIRONMENT_ACCEPTANCE_REF",
        "PROD_ENVIRONMENT_ACCEPTANCE_DIGEST",
        "PROD_ENVIRONMENT_ACCEPTANCE_ROOT",
        "--environment-acceptance-ref",
        "--environment-acceptance-sha256",
        "--environment-acceptance-root",
    ):
        assert retired not in source

    release_control_main = function_source(RELEASE_CONTROL, "main")
    assert "except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:" in release_control_main
    assert '"terminal": "GATE_BLOCK"' in release_control_main
    assert "return 1" in release_control_main


def test_prod_rollback_targets_previous_released_and_soak_is_independent() -> None:
    admission = function_source(QUALIFIED_PROD, "create_prod_activation_admission")
    rollback = function_source(QUALIFIED_PROD, "create_prod_rollback_fact")
    soak = function_source(QUALIFIED_PROD, "create_post_release_soak_fact")

    for token in (
        "previous_active_released_ledger_ref",
        'previous.get("terminal") != "released"',
        'previous.get("active") is not True',
        'previous.get("revoked") is not False',
        '"previousActiveReleasedLedger": previous_exact',
    ):
        assert token in admission
    for token in (
        '"terminal": "rolled_back"',
        '"rollbackTarget": previous_exact',
        '"builderInvocationCount": 0',
        '"tagMutation": False',
    ):
        assert token in rollback
    for token in (
        '"schema": "quwoquan_ops.post_release_soak_fact.v1"',
        '"readOnly": True',
        'root / "prod" / "soak"',
    ):
        assert token in soak
    prod_jobs = load_workflow(PROD)[1]["jobs"]
    assert "create_post_release_soak_fact" not in commands(prod_jobs["prod_rollout"])
    assert "create_post_release_soak_fact" in commands(prod_jobs["post_release_soak"])


def test_timing_contracts_separate_promotion_rc_and_prod() -> None:
    budgets = json.loads(TIMING_BUDGETS.read_text(encoding="utf-8"))
    promotion = budgets["gates"]["03.delivery_gate"]
    rc = budgets["gates"]["06.rc_qualification"]
    prod = budgets["gates"]["07.stable_tag_prod"]

    assert budgets["softBudgetSeconds"] == 300
    assert budgets["promotionCutoffSeconds"] == 300
    assert promotion["budgetSeconds"] == 300
    assert promotion["timingPolicy"] == "promotion_timing_ratchet"
    assert promotion["criticalPath"].startswith("promotionReadyAt -> mainReadbackAt")
    assert "promotion_verify only" in promotion["machinePath"]
    assert rc["budgetSeconds"] == 3600
    assert rc["hardFailSeconds"] == 7200
    assert prod["budgetSeconds"] == 1800
    assert prod["hardFailSeconds"] == 3600
    assert prod["rollbackBudgetSeconds"] == 300
    assert "06.rc_qualification" != "07.stable_tag_prod"

    ratchet = yaml.safe_load(PROMOTION_RATCHET.read_text(encoding="utf-8"))
    assert ratchet["contract_id"] == "promotion-timing-ratchet-v1"
    assert ratchet["targetP95Seconds"] == 300
    assert ratchet["governance"]["expires_when"].startswith("never")
    assert ratchet["requiredTimingCompleteness"] == 1.0
    assert ratchet["allowedUnclassifiedCancellations"] == 0
    assert ratchet["allowedDuplicateEvents"] == 0
    assert ratchet["allowedMissingEvidence"] == 0


def test_legacy_workflows_mutable_selectors_and_dry_run_are_gone() -> None:
    for name in LEGACY_WORKFLOWS:
        assert not (WORKFLOWS / name).exists(), f"legacy workflow returned: {name}"

    permanent_source = "\n".join(
        (WORKFLOWS / name).read_text(encoding="utf-8")
        for name in PERMANENT_WORKFLOWS
    )
    for token in FORBIDDEN_RELEASE_TOKENS:
        assert token not in permanent_source, f"forbidden release entry returned: {token}"
    prod_source = PROD.read_text(encoding="utf-8")
    for token in ("refs/heads/main", "github.sha }}", "source_git_sha:"):
        assert token not in prod_source, f"bare source selector returned to Prod: {token}"

    policy = yaml.safe_load(RELEASE_POLICY.read_text(encoding="utf-8"))
    assert policy["production"] == {
        "selector": "ReleaseTagAdmissionFact",
        "acceptedTagKind": "stable",
        "rcDenied": True,
        "mainHeadDenied": True,
        "mutablePointerDenied": True,
    }
