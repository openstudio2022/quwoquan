#!/usr/bin/env python3
"""Create immutable release-chain facts; Git refs remain controller-owned."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.promotion_evidence import create_main_source_seal, create_promotion_admission, digest
from quwoquan_ops.ci.artifact_build_number import allocate_hosted_sequence
from quwoquan_ops.ci.qualified_prod import create_prod_activation_admission, materialize_prod_activation_input
from quwoquan_ops.ci.release_qualification import (
    create_candidate_material_from_factory_outputs,
    create_qualification_fact,
    create_qualification_request,
)
from quwoquan_ops.ci.release_tag_admission import (
    assert_release_tag_intent_unused,
    create_release_candidate_tag_intent,
    create_release_tag_intent,
    finalize_release_candidate_tag_admission,
    finalize_release_tag_admission,
    record_tag_mutation_outcome,
)


POLICY = ROOT / "quwoquan_ops/policies/release_selection_policy.yaml"
VERSION = ROOT / "quwoquan_ops/policies/product_version.yaml"


def _exact(value: str, label: str) -> dict[str, str]:
    try:
        ref, exact_digest = value.split("=", 1)
    except ValueError as error:
        raise ValueError(f"{label} must be ref=digest") from error
    return {"ref": ref, "digest": exact_digest}


def _refs(values: list[str], label: str) -> list[dict[str, str]]:
    return [_exact(value, label) for value in values]


def _result(path: Path, store: Path) -> dict[str, str]:
    return {"ref": path.relative_to(store).as_posix(), "digest": digest(path)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store-root", type=Path,
        default=ROOT / ".qwq_output/env/repo/runs/release-control",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    promotion = sub.add_parser("promotion-admit")
    for name in ("qualification", "approval", "threads", "ruleset", "boundary"):
        promotion.add_argument(f"--{name}", required=True, help="exact ref=digest")
    promotion.add_argument("--required-evidence", action="append", required=True)
    promotion.add_argument("--head-sha", required=True)
    promotion.add_argument("--base-sha", required=True)
    promotion.add_argument("--synthetic-merge-sha", required=True)
    promotion.add_argument("--promotion-ready-at", required=True)

    seal = sub.add_parser("main-seal")
    seal.add_argument("--admission", required=True)
    seal.add_argument("--main-sha", required=True)
    seal.add_argument("--main-readback-at", required=True)

    request = sub.add_parser("qualification-request")
    request.add_argument("--rc-admission", required=True)
    request.add_argument("--main-source-seal", required=True)
    request.add_argument("--integration-qualification", required=True)
    request.add_argument("--request-authority", required=True)
    request.add_argument("--requested-at", required=True)

    allocation = sub.add_parser("build-number-allocate")
    allocation.add_argument("--request", required=True)
    allocation.add_argument("--hosted-run-number", required=True, type=int)
    allocation.add_argument("--hosted-run-id", required=True)

    material = sub.add_parser("qualification-material")
    material.add_argument("--repository-root", type=Path, default=ROOT)
    for name in (
        "request", "allocation", "product-version-manifest",
    ):
        material.add_argument(f"--{name}", required=True)
    for name in (
        "request-oci-ref", "allocation-oci-ref", "service-material",
        "service-evidence-ref", "service-source-git-sha", "service-source-tree",
        "service-qualification-request-ref", "service-qualification-request-digest",
        "service-material-digest", "service-artifact-digest", "app-material",
        "app-evidence-ref", "app-source-git-sha", "app-source-tree", "app-qualification-request-ref",
        "app-qualification-request-digest", "app-allocation-ref",
        "app-allocation-digest", "app-material-digest",
        "app-android-artifact-digest", "app-ios-artifact-digest",
        "app-web-artifact-digest", "created-at",
    ):
        material.add_argument(f"--{name}", required=True)
    material.add_argument("--app-artifact-build-number", required=True, type=int)

    qualify = sub.add_parser("qualification-finalize")
    for name in ("request", "material", "package-acceptance", "provider", "uat", "supply-chain"):
        qualify.add_argument(f"--{name}", required=True)
    qualify.add_argument("--qualified-at", required=True)

    for kind in ("rc", "stable"):
        intent = sub.add_parser(f"tag-admit-{kind}-intent")
        intent.add_argument("--tag-name", required=True)
        intent.add_argument("--source-git-sha", required=True)
        intent.add_argument("--reservation", required=True)
        intent.add_argument("--creator-readback", required=True)
        intent.add_argument("--ruleset-readback", required=True)
        intent.add_argument("--repository", required=True)
        intent.add_argument("--controller-app-id", required=True, type=int)
        intent.add_argument("--controller-installation-id", required=True, type=int)
        intent.add_argument("--controller-app-slug", required=True)
        intent.add_argument("--initial-release-authority")
        intent.add_argument("--admitted-at", required=True)
        if kind == "rc":
            intent.add_argument("--selection", required=True)
        else:
            intent.add_argument("--selected-rc-admission", required=True)
            intent.add_argument("--qualification", required=True)
            intent.add_argument("--product-authority", required=True)
            intent.add_argument("--release-authority", required=True)

        finalize = sub.add_parser(f"tag-admit-{kind}-finalize")
        finalize.add_argument("--tag-name", required=True)
        finalize.add_argument("--intent", required=True)
        finalize.add_argument("--mutation-outcome", required=True)
        finalize.add_argument("--creator-readback", required=True)
        finalize.add_argument("--ruleset-readback", required=True)
        finalize.add_argument("--admitted-at", required=True)

    intent_check = sub.add_parser("tag-admission-intent-check")
    intent_check.add_argument("--tag-kind", required=True, choices=("rc", "stable"))
    intent_check.add_argument("--tag-name", required=True)
    intent_check.add_argument("--intent", required=True)

    mutation = sub.add_parser("tag-mutation-outcome")
    mutation.add_argument("--tag-kind", required=True, choices=("rc", "stable"))
    mutation.add_argument("--tag-name", required=True)
    mutation.add_argument("--intent", required=True)
    mutation.add_argument("--status", required=True, choices=("created", "failed"))
    mutation.add_argument("--tag-object-oid")
    mutation.add_argument("--peeled-commit")
    mutation.add_argument("--recorded-at", required=True)

    prod = sub.add_parser("prod-admit")
    prod.add_argument("--release-tag-admission", required=True)
    prod.add_argument("--previous-active-released-ledger", required=True)
    prod.add_argument("--rollback-readiness", required=True)
    prod.add_argument("--control-plane-git-sha", required=True)
    prod.add_argument("--admitted-at", required=True)

    prod_input = sub.add_parser("prod-materialize-input")
    prod_input.add_argument("--admission", required=True)
    prod_input.add_argument("--service-factory-material", required=True)
    prod_input.add_argument("--app-factory-material", required=True)
    prod_input.add_argument("--output", required=True, type=Path)
    prod_input.add_argument("--github-output", type=Path)

    prod_stage = sub.add_parser("prod-stage-append")
    prod_stage.add_argument("--admission", required=True)
    prod_stage.add_argument("--stage", required=True)
    prod_stage.add_argument("--status", required=True, choices=("passed", "failed"))
    for name in ("activation", "health", "slo", "placement", "readback"):
        prod_stage.add_argument(f"--{name}", required=True)
    prod_stage.add_argument("--predecessor")
    prod_stage.add_argument("--hosted-receipt-readback", required=True)
    prod_stage.add_argument("--recorded-at", required=True)

    prod_terminal = sub.add_parser("prod-terminal-release")
    prod_terminal.add_argument("--admission", required=True)
    prod_terminal.add_argument("--final-attempt", required=True)
    prod_terminal.add_argument("--hosted-receipt-readback", required=True)
    prod_terminal.add_argument("--released-at", required=True)

    prod_rollback = sub.add_parser("prod-rollback")
    prod_rollback.add_argument("--admission", required=True)
    prod_rollback.add_argument("--failed-attempt", required=True)
    for name in ("activation", "health", "readback"):
        prod_rollback.add_argument(f"--{name}", required=True)
    prod_rollback.add_argument("--hosted-receipt-readback", required=True)
    prod_rollback.add_argument("--rolled-back-at", required=True)

    prod_soak_request = sub.add_parser("prod-soak-request")
    prod_soak_request.add_argument("--released-fact", required=True)
    prod_soak_request.add_argument("--released-oci-ref", required=True)
    prod_soak_request.add_argument("--full-stage-readback", required=True, type=Path)
    for name in ("health", "slo", "alerts"):
        prod_soak_request.add_argument(f"--{name}", required=True)
    prod_soak_request.add_argument("--credential-evidence", required=True, type=Path)
    prod_soak_request.add_argument("--repository", required=True)
    prod_soak_request.add_argument("--workflow-run-id", required=True)
    prod_soak_request.add_argument("--workflow-run-attempt", required=True)
    prod_soak_request.add_argument("--actor", required=True)
    prod_soak_request.add_argument("--verified-at", required=True)
    prod_soak_request.add_argument("--output", required=True, type=Path)

    prod_soak = sub.add_parser("prod-soak")
    prod_soak.add_argument("--released-fact", required=True)
    prod_soak.add_argument("--hosted-soak-readback", required=True)
    for name in ("health", "slo", "alerts"):
        prod_soak.add_argument(f"--{name}", required=True)
    prod_soak.add_argument("--status", required=True, choices=("passed", "failed"))
    prod_soak.add_argument("--observed-at", required=True)
    return parser


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _prod_soak_request(*, store: Path, args: argparse.Namespace) -> Path:
    import hashlib

    from quwoquan_ops.ci.qualified_prod import (
        _exact,
        _hosted_stage_readback,
        _validated_exact_fact,
    )
    from quwoquan_ops.cli.prod import hosted_release_ledger

    released, released_exact = _validated_exact_fact(
        store,
        _exact(args.released_fact, "released-fact"),
        schema="quwoquan_ops.prod_released_fact.v1",
        field="releasedFact",
    )
    full_path = args.full_stage_readback.expanduser().resolve()
    full_payload = json.loads(full_path.read_text(encoding="utf-8"))
    full_local = store / "prod" / "soak" / "full-stage-readback.json"
    full_local.parent.mkdir(parents=True, exist_ok=True)
    full_local.write_bytes(_canonical_bytes(full_payload) + b"\n")
    full_exact = {
        "ref": full_local.relative_to(store).as_posix(),
        "digest": "sha256:" + hashlib.sha256(full_local.read_bytes()).hexdigest(),
    }
    _, _, full = _hosted_stage_readback(
        store, full_exact, service="prod-stack", field="fullStageReadback"
    )
    admission, _ = _exact(
        store, released.get("admission"), "releasedFact.admission"
    )
    if admission.get("schema") != "quwoquan_ops.prod_activation_admission_fact.v1":
        raise ValueError("released admission schema is invalid")
    hosted_ref = released.get("hostedReceiptReadback")
    if (
        not isinstance(hosted_ref, dict)
        or hosted_ref.get("digest") != full_exact["digest"]
        or released.get("candidateId") != full.get("toCandidateDigest")
    ):
        raise ValueError("full hosted receipt does not bind released terminal")

    observations = {
        name: _exact(store, _exact(getattr(args, name), name), name)[0]
        for name in ("health", "slo", "alerts")
    }
    hosted = {}
    for name, value in observations.items():
        if value.get("release") != released_exact or value.get("status") != "passed" or value.get("readOnly") is not True:
            raise ValueError(f"soak {name} observation does not bind released fact")
        hosted[name] = value.get("source")
    slo_source = hosted["slo"]
    alert_source = hosted["alerts"]
    health_source = hosted["health"]
    observed_at = args.verified_at
    released_oci_ref = args.released_oci_ref.strip()
    if not hosted_release_ledger.OCI_REF_RE.fullmatch(released_oci_ref):
        raise ValueError("released-oci-ref must be an exact immutable OCI ref")
    request = {
        "schema": hosted_release_ledger.SOAK_REQUEST_SCHEMA,
        "service": "prod-stack",
        "environment": "prod",
        "target": "prod-hosted",
        "fullRolloutReceiptId": full["receiptId"],
        "candidateId": released["candidateId"],
        "candidateMaterialId": full["candidateMaterialId"],
        "prodActivationAdmissionRef": full["prodActivationAdmissionRef"],
        "prodActivationAdmissionOciDigest": full["prodActivationAdmissionOciDigest"],
        "prodActivationAdmissionPayloadDigest": full["prodActivationAdmissionPayloadDigest"],
        "prodActivationAdmissionId": full["prodActivationAdmissionId"],
        "candidateMaterialManifestRef": full["candidateMaterialManifestRef"],
        "candidateMaterialManifestOciDigest": full["candidateMaterialManifestOciDigest"],
        "candidateMaterialManifestPayloadDigest": full["candidateMaterialManifestPayloadDigest"],
        "serviceFactoryOciDigest": full["toServiceFactoryOciDigest"],
        "appFactoryOciDigest": full["toAppFactoryOciDigest"],
        "releasedRef": released_oci_ref,
        "releasedOciDigest": released_oci_ref.rsplit("@", 1)[-1],
        "releasedPayloadDigest": released_exact["digest"],
        "releasedId": released["releaseId"],
        "sourceGitSha": released["sourceGitSha"],
        "sourceTreeDigest": "sha1:" + str(admission["sourceTree"]),
        "rolloutConfigDigest": full["configDigest"],
        "configGraphDigest": full["configDigest"],
        "contractGraphDigest": full["contractGraphDigest"],
        "requiredSoakSeconds": 86400,
        "soakPolicyDigest": "sha256:" + hashlib.sha256((ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml").read_bytes()).hexdigest(),
        "credentialPolicyDigest": "sha256:" + hashlib.sha256((ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml").read_bytes()).hexdigest(),
        "slo": {"source": "prometheus", "observedAt": str(slo_source["queriedAt"]), "windowSeconds": 86400, "minimumSamples": int(slo_source["minimumSamples"]), "sampleCount": int(float(slo_source["values"]["sampleCount"])), "status": "passed", "decision": "continue", "values": {name: float(slo_source["values"][name]) for name in ("errorRate", "p95Ms", "redisErrorRate")}, "receiptDigest": str(observations["slo"]["sourceDigest"])},
        "alerts": {"source": "alertmanager", "observedAt": str(alert_source["queriedAt"]), "status": "passed", "activeFiring": int(alert_source["activeFiring"]), "receiptDigest": str(observations["alerts"]["sourceDigest"])},
        "health": {"source": "stackctl", "observedAt": str(health_source["timestamp"]), "target": "prod-hosted", "scope": "full", "status": "passed", "receiptDigest": str(observations["health"]["sourceDigest"])},
        "credentials": json.loads(args.credential_evidence.read_text(encoding="utf-8"))["credentials"],
        "approval": {
            "kind": "github-production-environment",
            "repository": args.repository,
            "sourceGitSha": released["sourceGitSha"],
            "candidateMaterialId": full["candidateMaterialId"],
            "prodActivationAdmissionId": full["prodActivationAdmissionId"],
            "environment": "production",
            "workflowRunId": args.workflow_run_id,
            "workflowRunAttempt": args.workflow_run_attempt,
            "actor": args.actor,
            "receiptDigest": full_exact["digest"],
            "verifiedAt": observed_at,
        },
    }
    hosted_release_ledger._validate_soak_request(request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_bytes(request) + b"\n")
    return args.output


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = args.store_root.expanduser().resolve()
    try:
        if args.command == "promotion-admit":
            path = create_promotion_admission(
                repository=ROOT, evidence_root=store,
                qualification_ref=_exact(args.qualification, "qualification"),
                head_sha=args.head_sha, base_sha=args.base_sha,
                synthetic_merge_sha=args.synthetic_merge_sha,
                approval_fact_ref=_exact(args.approval, "approval"),
                thread_fact_ref=_exact(args.threads, "threads"),
                ruleset_fact_ref=_exact(args.ruleset, "ruleset"),
                boundary_fact_ref=_exact(args.boundary, "boundary"),
                required_evidence=_refs(args.required_evidence, "required-evidence"),
                promotion_ready_at=args.promotion_ready_at,
            )
        elif args.command == "main-seal":
            path = create_main_source_seal(repository=ROOT, evidence_root=store, admission_ref=_exact(args.admission, "admission"), main_sha=args.main_sha, main_readback_at=args.main_readback_at)
        elif args.command == "qualification-request":
            path = create_qualification_request(root=store, rc_tag_admission_ref=_exact(args.rc_admission, "rc-admission"), main_source_seal_ref=_exact(args.main_source_seal, "main-source-seal"), integration_qualification_ref=_exact(args.integration_qualification, "integration-qualification"), requested_by_ref=_exact(args.request_authority, "request-authority"), requested_at=args.requested_at)
        elif args.command == "build-number-allocate":
            path = allocate_hosted_sequence(root=store, request_ref=_exact(args.request, "request"), hosted_run_number=args.hosted_run_number, hosted_run_id=args.hosted_run_id)
        elif args.command == "qualification-material":
            path = create_candidate_material_from_factory_outputs(
                root=store,
                request_ref=_exact(args.request, "request"),
                request_oci_ref=args.request_oci_ref,
                artifact_build_number_allocation_ref=_exact(args.allocation, "allocation"),
                allocation_oci_ref=args.allocation_oci_ref,
                product_version_manifest_ref=_exact(args.product_version_manifest, "product-version-manifest"),
                service_material_ref=_exact(args.service_material, "service-material"),
                service_evidence_ref=args.service_evidence_ref,
                service_source_git_sha=args.service_source_git_sha,
                service_source_tree=args.service_source_tree,
                service_qualification_request_ref=args.service_qualification_request_ref,
                service_qualification_request_digest=args.service_qualification_request_digest,
                service_material_digest=args.service_material_digest,
                service_artifact_digest=args.service_artifact_digest,
                app_material_ref=_exact(args.app_material, "app-material"),
                app_evidence_ref=args.app_evidence_ref,
                app_source_git_sha=args.app_source_git_sha,
                app_source_tree=args.app_source_tree,
                app_qualification_request_ref=args.app_qualification_request_ref,
                app_qualification_request_digest=args.app_qualification_request_digest,
                app_artifact_build_number=args.app_artifact_build_number,
                app_allocation_ref=args.app_allocation_ref,
                app_allocation_digest=args.app_allocation_digest,
                app_material_digest=args.app_material_digest,
                app_android_artifact_digest=args.app_android_artifact_digest,
                app_ios_artifact_digest=args.app_ios_artifact_digest,
                app_web_artifact_digest=args.app_web_artifact_digest,
                created_at=args.created_at,
                repository_root=args.repository_root,
            )
        elif args.command == "qualification-finalize":
            path = create_qualification_fact(root=store, request_ref=_exact(args.request, "request"), material_ref=_exact(args.material, "material"), package_acceptance_ref=_exact(args.package_acceptance, "package-acceptance"), provider_fact_ref=_exact(args.provider, "provider"), uat_fact_ref=_exact(args.uat, "uat"), supply_chain_fact_ref=_exact(args.supply_chain, "supply-chain"), qualified_at=args.qualified_at)
        elif args.command == "tag-admit-rc-intent":
            path = create_release_candidate_tag_intent(
                repository=ROOT, evidence_root=store, tag_name=args.tag_name,
                source_git_sha=args.source_git_sha,
                product_version_manifest_path=VERSION,
                release_selection_policy_path=POLICY,
                reservation_ref=_exact(args.reservation, "reservation"),
                selection_fact_ref=_exact(args.selection, "selection"),
                creator_readback_ref=_exact(args.creator_readback, "creator-readback"),
                ruleset_readback_ref=_exact(args.ruleset_readback, "ruleset-readback"),
                repository_identity=args.repository,
                controller_app_id=args.controller_app_id,
                controller_installation_id=args.controller_installation_id,
                controller_app_slug=args.controller_app_slug,
                initial_release_authority_ref=_exact(args.initial_release_authority, "initial-release-authority") if args.initial_release_authority else None,
                admitted_at=args.admitted_at,
            )
        elif args.command == "tag-admit-stable-intent":
            path = create_release_tag_intent(
                repository=ROOT, evidence_root=store, tag_name=args.tag_name,
                source_git_sha=args.source_git_sha,
                product_version_manifest_path=VERSION,
                release_selection_policy_path=POLICY,
                reservation_ref=_exact(args.reservation, "reservation"),
                selected_rc_admission_ref=_exact(args.selected_rc_admission, "selected-rc-admission"),
                qualification_fact_ref=_exact(args.qualification, "qualification"),
                product_authority_fact_ref=_exact(args.product_authority, "product-authority"),
                release_authority_fact_ref=_exact(args.release_authority, "release-authority"),
                creator_readback_ref=_exact(args.creator_readback, "creator-readback"),
                ruleset_readback_ref=_exact(args.ruleset_readback, "ruleset-readback"),
                repository_identity=args.repository,
                controller_app_id=args.controller_app_id,
                controller_installation_id=args.controller_installation_id,
                controller_app_slug=args.controller_app_slug,
                initial_release_authority_ref=_exact(args.initial_release_authority, "initial-release-authority") if args.initial_release_authority else None,
                admitted_at=args.admitted_at,
            )
        elif args.command == "tag-admission-intent-check":
            assert_release_tag_intent_unused(
                evidence_root=store, admission_intent_ref=_exact(args.intent, "intent"),
                tag_kind=args.tag_kind, tag_name=args.tag_name,
            )
            path = store / _exact(args.intent, "intent")["ref"]
        elif args.command == "tag-mutation-outcome":
            path = record_tag_mutation_outcome(
                evidence_root=store, admission_intent_ref=_exact(args.intent, "intent"),
                tag_kind=args.tag_kind, tag_name=args.tag_name, status=args.status,
                tag_object_oid=args.tag_object_oid, peeled_commit=args.peeled_commit,
                recorded_at=args.recorded_at,
            )
        elif args.command == "tag-admit-rc-finalize":
            path = finalize_release_candidate_tag_admission(
                repository=ROOT, evidence_root=store, tag_name=args.tag_name,
                admission_intent_ref=_exact(args.intent, "intent"),
                mutation_outcome_ref=_exact(args.mutation_outcome, "mutation-outcome"),
                creator_readback_ref=_exact(args.creator_readback, "creator-readback"),
                ruleset_readback_ref=_exact(args.ruleset_readback, "ruleset-readback"),
                admitted_at=args.admitted_at, release_selection_policy_path=POLICY,
            )
        elif args.command == "tag-admit-stable-finalize":
            path = finalize_release_tag_admission(
                repository=ROOT, evidence_root=store, tag_name=args.tag_name,
                admission_intent_ref=_exact(args.intent, "intent"),
                mutation_outcome_ref=_exact(args.mutation_outcome, "mutation-outcome"),
                creator_readback_ref=_exact(args.creator_readback, "creator-readback"),
                ruleset_readback_ref=_exact(args.ruleset_readback, "ruleset-readback"),
                admitted_at=args.admitted_at, release_selection_policy_path=POLICY,
            )
        elif args.command == "prod-admit":
            path = create_prod_activation_admission(root=store, release_tag_admission_ref=_exact(args.release_tag_admission, "release-tag-admission"), previous_active_released_ledger_ref=_exact(args.previous_active_released_ledger, "previous-active-released-ledger"), rollback_readiness_ref=_exact(args.rollback_readiness, "rollback-readiness"), control_plane_git_sha=args.control_plane_git_sha, admitted_at=args.admitted_at)
        elif args.command == "prod-materialize-input":
            materialize_prod_activation_input(root=store, admission_ref=_exact(args.admission, "admission"), service_material_ref=_exact(args.service_factory_material, "service-factory-material"), app_material_ref=_exact(args.app_factory_material, "app-factory-material"), output=args.output, repository_root=ROOT)
            path = args.output.resolve()
            if args.github_output:
                payload = json.loads(path.read_text(encoding="utf-8"))
                args.github_output.write_text(
                    f"source_git_sha={payload['sourceGitSha']}\n"
                    f"service_factory_oci_ref={payload['serviceFactoryMaterial']['ociRef']}\n"
                    f"app_factory_oci_ref={payload['appFactoryMaterial']['ociRef']}\n"
                    f"candidate_digest={payload['candidateDigest']}\n"
                    f"from_candidate_digest={payload['previousCandidateDigest']}\n",
                    encoding="utf-8",
                )
        elif args.command == "prod-soak-request":
            path = _prod_soak_request(store=store, args=args)
        elif args.command == "prod-stage-append":
            from quwoquan_ops.ci.qualified_prod import append_prod_stage_attempt
            path = append_prod_stage_attempt(
                root=store,
                admission_ref=_exact(args.admission, "admission"),
                stage=args.stage,
                status=args.status,
                evidence_refs={name: _exact(getattr(args, name), name) for name in ("activation", "health", "slo", "placement", "readback")},
                hosted_receipt_readback_ref=_exact(args.hosted_receipt_readback, "hosted-receipt-readback"),
                predecessor_ref=_exact(args.predecessor, "predecessor") if args.predecessor else None,
                recorded_at=args.recorded_at,
            )
        elif args.command == "prod-terminal-release":
            from quwoquan_ops.ci.qualified_prod import create_terminal_released_fact
            path = create_terminal_released_fact(root=store, admission_ref=_exact(args.admission, "admission"), final_attempt_ref=_exact(args.final_attempt, "final-attempt"), hosted_receipt_readback_ref=_exact(args.hosted_receipt_readback, "hosted-receipt-readback"), released_at=args.released_at)
        elif args.command == "prod-rollback":
            from quwoquan_ops.ci.qualified_prod import create_prod_rollback_fact
            path = create_prod_rollback_fact(
                root=store,
                admission_ref=_exact(args.admission, "admission"),
                failed_attempt_ref=_exact(args.failed_attempt, "failed-attempt"),
                evidence_refs={name: _exact(getattr(args, name), name) for name in ("activation", "health", "readback")},
                hosted_receipt_readback_ref=_exact(args.hosted_receipt_readback, "hosted-receipt-readback"),
                rolled_back_at=args.rolled_back_at,
            )
        else:
            from quwoquan_ops.ci.qualified_prod import create_post_release_soak_fact
            path = create_post_release_soak_fact(
                root=store,
                released_fact_ref=_exact(args.released_fact, "released-fact"),
                observation_refs={name: _exact(getattr(args, name), name) for name in ("health", "slo", "alerts")},
                hosted_soak_readback_ref=_exact(args.hosted_soak_readback, "hosted-soak-readback"),
                status=args.status,
                observed_at=args.observed_at,
            )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"terminal": "GATE_BLOCK", "detail": str(error)}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(_result(path, store), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
