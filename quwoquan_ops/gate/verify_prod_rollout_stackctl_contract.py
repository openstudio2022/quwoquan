#!/usr/bin/env python3
from __future__ import annotations

import runpy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.immutable_image_composition import runtime_image_owner_names
WORKFLOWS = [
    ROOT / ".github" / "workflows" / "deploy-prod-auto.yml",
]
SERVICE_PIPELINE = ROOT / ".github" / "workflows" / "service_pipeline.yml"
ACCESS_MANIFEST = ROOT / "quwoquan_ops" / "environments" / "prod" / "access-isolation.yaml"
RELEASE_GENERATOR = (
    ROOT / "quwoquan_ops" / "cli" / "prod" / "generate_mainline_release_artifact.py"
)
RELEASE_PLANNER = ROOT / "quwoquan_ops" / "ci" / "plan_service_release_images.py"
DEPLOY_SCRIPT = ROOT / "quwoquan_ops" / "cli" / "prod" / "deploy_to_prod.sh"
PROD_RENDERER = ROOT / "quwoquan_ops" / "cli" / "prod" / "render_prod_plane_stack.py"
STACKCTL = ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
OCI_SUPPLY_CHAIN = (
    ROOT / "quwoquan_ops" / "cli" / "prod" / "oci_supply_chain.py"
)
HOSTED_LEDGER = (
    ROOT / "quwoquan_ops" / "cli" / "prod" / "hosted_release_ledger.py"
)
# hosted_release_ledger 已拆分为「双栖薄入口 + hosted_release_ledger_lib 包」；
# token 扫描覆盖入口与包内全部子模块。
HOSTED_LEDGER_LIB = (
    ROOT / "quwoquan_ops" / "cli" / "prod" / "hosted_release_ledger_lib"
)


def _hosted_ledger_text() -> str:
    return "\n".join(
        [HOSTED_LEDGER.read_text(encoding="utf-8")]
        + [
            path.read_text(encoding="utf-8")
            for path in sorted(HOSTED_LEDGER_LIB.glob("*.py"))
        ]
    )
# environment_stability_final_acceptance 已由单文件拆分为同名包；token 扫描覆盖包内全部子模块。
FINAL_ACCEPTANCE = (
    ROOT
    / "quwoquan_ops"
    / "cli"
    / "lib"
    / "environment_stability_final_acceptance"
)
SOAK_COLLECTOR = ROOT / "quwoquan_ops" / "ci" / "collect_prod_soak_observations.py"
REQUIRED_ROLLOUT_TOKENS = (
    "quwoquan_ops/cli/stackctl.py deploy",
    "--target prod-hosted",
    "--release-manifest",
    "fetch_mainline_release_artifact.py",
    "release_evidence_ref",
    "release-evidence-manifest",
    "verify_workflow_release_candidate.py",
    "--require-deployable",
    "--expected-candidate",
    "--expected-artifact-digest",
    "--from-candidate-digest",
    "--to-candidate-digest",
    "--release-evidence-ref",
    "RESOLVED_FROM_CANDIDATE_DIGEST",
    "RESOLVED_RESUME_STAGE",
    "PROD_PROMETHEUS_URL",
    "PROD_RELEASE_STATE_DIR",
    "PROD_BACKUP_RECOVERY_RECEIPT",
    "--backup-recovery-receipt",
    "group: prod-hosted-release",
)
CALLER_SUPPLIED_SLO_TOKENS = (
    "--error-rate",
    "--p95-ms",
    "--redis-error-rate",
    "inputs.error_rate",
    "inputs.p95_ms",
    "inputs.redis_error_rate",
)
FORBIDDEN_ROLLOUT_TOKENS = (
    "mainline-release-artifact",
    "manifestDigest",
    "versions",
    "release_artifact_ref",
    "releaseFiles",
    "MANIFEST_DIGEST",
    "--manifest-digest",
    "make config-gray-rollout",
    "make config-slo-gate",
    "make config-rollback",
    "bash quwoquan_ops/cli/prod/deploy_to_prod.sh",
    "--from-image",
    "--to-image",
    "--from-config",
    "--to-config",
)


PROD_ENVIRONMENT_JOBS = ("prod_rollout", "prod_soak_acceptance")
PROD_ROLLOUT_ENVIRONMENT = (
    "${{ needs.prepare.outputs.dry_run != 'true' && 'production' || "
    "'release-validation' }}"
)


def _job_environment_name(spec: object) -> str:
    if not isinstance(spec, dict):
        return ""
    environment = spec.get("environment")
    if isinstance(environment, str):
        return environment.strip()
    if isinstance(environment, dict):
        return str(environment.get("name") or "").strip()
    return ""


def prod_environment_job_issues(path: Path) -> list[str]:
    """受控 prod 事务的唯一允许清单：只有这些 job 可以绑定 production 环境。"""
    try:
        rel: Path | str = path.relative_to(ROOT)
    except ValueError:
        rel = path.name
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jobs = document.get("jobs") or {}
    environment_names = {
        name: _job_environment_name(spec) for name, spec in jobs.items()
    }
    bound = sorted(
        name
        for name, environment_name in environment_names.items()
        if environment_name == "production" or "'production'" in environment_name
    )
    issues: list[str] = []
    for name in bound:
        if name not in PROD_ENVIRONMENT_JOBS:
            issues.append(
                f"{rel} job {name} binds environment: production outside the controlled prod transaction"
            )
    if environment_names.get("prod_rollout") != PROD_ROLLOUT_ENVIRONMENT:
        issues.append(
            f"{rel} job prod_rollout must bind the exact dry-run release-validation / "
            "real-apply production environment expression"
        )
    if environment_names.get("prod_soak_acceptance") != "production":
        issues.append(
            f"{rel} job prod_soak_acceptance must bind environment: production "
            "for manual prod admission"
        )
    return issues


def workflow_rollout_issues(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(ROOT)
    issues: list[str] = []
    for token in REQUIRED_ROLLOUT_TOKENS:
        if token not in text:
            issues.append(f"{rel} missing governed rollout token: {token}")
    for token in CALLER_SUPPLIED_SLO_TOKENS:
        if token in text:
            issues.append(
                f"{rel} permits caller-supplied SLO evidence instead of Prometheus readback: {token}"
            )
    for token in FORBIDDEN_ROLLOUT_TOKENS:
        if token in text:
            issues.append(f"{rel} still contains legacy rollout entry: {token}")
    return issues


def candidate_identity_issues() -> list[str]:
    issues: list[str] = []
    ledger_text = _hosted_ledger_text()
    # stackctl.py 已按域拆分；candidate transition guard 位于 deploy 域模块。
    stackctl_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            STACKCTL,
            ROOT / "quwoquan_ops" / "cli" / "commands" / "deploy_release_state.py",
            ROOT / "quwoquan_ops" / "cli" / "commands" / "deploy_rollout.py",
            ROOT / "quwoquan_ops" / "cli" / "commands" / "deploy_prod_finalize.py",
            ROOT / "quwoquan_ops" / "cli" / "commands" / "deploy_domain.py",
            ROOT / "quwoquan_ops" / "cli" / "commands" / "deploy_release_inputs.py",
        )
    )
    for token in (
        '"fromCandidateDigest"',
        '"toCandidateDigest"',
        '"from_candidate_digest"',
        '"to_candidate_digest"',
        '"last_good_candidate_digest"',
    ):
        if token not in ledger_text:
            issues.append(
                f"{HOSTED_LEDGER.relative_to(ROOT)} missing candidate ledger identity: {token}"
            )
    for token in (
        '"fromImage"',
        '"toImage"',
        '"fromConfig"',
        '"toConfig"',
        '"from_image"',
        '"to_image"',
        '"from_config"',
        '"to_config"',
    ):
        if token in ledger_text:
            issues.append(
                f"{HOSTED_LEDGER.relative_to(ROOT)} uses transport coordinates as ledger identity: {token}"
            )
    for token in (
        "state.get(\"from_candidate_digest\")",
        "state.get(\"to_candidate_digest\")",
        "state.get(\"to_candidate_digest\") != from_candidate_digest",
        "candidate_digest=args.to_candidate_digest",
        '"IMAGE_TRANSPORT_TAG": to_image_transport_tag',
        '"CANDIDATE_DIGEST": args.to_candidate_digest',
        '"PREVIOUS_IMAGE_TRANSPORT_TAG": from_image_transport_tag',
        "hosted ledger lacks canonical source transport metadata",
    ):
        if token not in stackctl_text:
            issues.append(
                f"{STACKCTL.relative_to(ROOT)} missing canonical candidate transition guard: {token}"
            )
    for forbidden in (
        "args.from_image =",
        "args.to_image =",
        "args.from_config =",
        "args.to_config =",
    ):
        if forbidden in stackctl_text:
            issues.append(
                f"{STACKCTL.relative_to(ROOT)} retains a legacy rollout identity shim: {forbidden}"
            )
    return issues


def hosted_soak_authority_issues() -> list[str]:
    issues: list[str] = []
    workflow_text = WORKFLOWS[0].read_text(encoding="utf-8")
    ledger_text = _hosted_ledger_text()
    verifier_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(FINAL_ACCEPTANCE.glob("*.py"))
    )
    collector_text = SOAK_COLLECTOR.read_text(encoding="utf-8")
    for token in (
        "prod_soak_acceptance:",
        "environment: production",
        "collect_prod_soak_observations.py",
        "release-ledger-soak-commit",
        "release-ledger-soak-receipt",
        "PROD_ALERTMANAGER_URL",
        "PROD_EDGE_SSH_KEY_PUBLIC_DIGEST",
        "PROD_SERVICE_SSH_KEY_EXPIRES_AT",
        'cmp "$COMMITTED" "$READBACK"',
    ):
        if token not in workflow_text:
            issues.append(f"prod workflow missing hosted soak authority token: {token}")
    for token in (
        'SOAK_REQUEST_SCHEMA = "prod-hosted-soak-request"',
        'SOAK_RECEIPT_SCHEMA = "prod-hosted-soak-receipt"',
        '"fullRolloutReceiptId"',
        '"configGraphDigest"',
        '"contractGraphDigest"',
        '"credentialPolicyDigest"',
        "authoritative prod soak window is incomplete",
        "fetch_soak_receipt",
    ):
        if token not in ledger_text:
            issues.append(f"hosted release ledger missing soak authority token: {token}")
    for token in (
        "verify_canonical_hosted_prod_soak",
        "remote_raw != raw",
        "receipt.get(\"soakPolicyDigest\")",
        "actual_credentials != expected_credentials",
        "soak_authority_verifier: SoakAuthorityVerifier = verify_canonical_hosted_prod_soak",
    ):
        if token not in verifier_text:
            issues.append(f"final acceptance missing hosted soak verifier token: {token}")
    for token in (
        "_wait_for_authoritative_window",
        "_read_prometheus_slo",
        "_read_alertmanager",
        '"prod-hosted"',
        '"full"',
    ):
        if token not in collector_text:
            issues.append(f"Prod soak collector missing authority token: {token}")
    if "approvalReceiptRef" in ledger_text or "approvalReceiptRef" in verifier_text:
        issues.append("Prod soak authority must not trust string approvalReceiptRef")
    return issues


def main() -> int:
    issues: list[str] = []
    for path in WORKFLOWS:
        issues.extend(workflow_rollout_issues(path))
        issues.extend(prod_environment_job_issues(path))
    issues.extend(candidate_identity_issues())
    issues.extend(hosted_soak_authority_issues())

    controlled_rollout = (
        ROOT / ".github" / "workflows" / "deploy-prod-auto.yml"
    ).read_text(encoding="utf-8")
    if "workflow_run:" in controlled_rollout:
        issues.append(
            ".github/workflows/deploy-prod-auto.yml must not automatically promote a main merge"
        )
    for token in (
        "name: 07. Deploy To Prod (Controlled)",
        "Service Pipeline (same mainline DAG)",
        "App package evidence (same mainline DAG)",
        "default: true",
    ):
        if token not in controlled_rollout:
            issues.append(
                ".github/workflows/deploy-prod-auto.yml missing controlled rollout token: "
                + token
            )

    access = yaml.safe_load(ACCESS_MANIFEST.read_text(encoding="utf-8")) or {}
    governed_compose_services = {
        str(service)
        for plane in access.get("planes") or []
        for service in plane.get("rootlessGovernedComposeServices") or []
    }
    if not governed_compose_services:
        issues.append("prod access manifest has no governed compose services")
    expected_images = set(runtime_image_owner_names(ROOT))
    generator_globals = runpy.run_path(str(RELEASE_GENERATOR))
    if generator_globals.get("SCHEMA") != "release-evidence-manifest":
        issues.append(
            "release evidence producer must emit the canonical release-evidence-manifest schema"
        )
    declared_images = set(generator_globals.get("DEPLOYED_SERVICES") or ())
    if declared_images != expected_images:
        issues.append(
            "mainline release image set must equal canonical runtime image owners: "
            f"missing={sorted(expected_images - declared_images)} "
            f"extra={sorted(declared_images - expected_images)}"
        )

    planner_globals = runpy.run_path(str(RELEASE_PLANNER))
    planned_images = set(planner_globals.get("ALL_SERVICES") or ())
    if planned_images != expected_images:
        issues.append(
            "service release planner image set must equal canonical runtime image owners: "
            f"missing={sorted(expected_images - planned_images)} "
            f"extra={sorted(planned_images - expected_images)}"
        )
    build_definitions = planner_globals.get("SERVICE_BUILD_DEFINITIONS") or ()
    recommendation = next(
        (
            item
            for item in build_definitions
            if isinstance(item, dict)
            and item.get("runtime_image_owner") == "recommendation-service"
        ),
        None,
    )
    if not isinstance(recommendation, dict) or recommendation.get("context") != (
        "quwoquan_service"
    ):
        issues.append(
            f"{RELEASE_PLANNER.relative_to(ROOT)} must build recommendation-service "
            "from quwoquan_service context"
        )

    pipeline_text = SERVICE_PIPELINE.read_text(encoding="utf-8")
    for token in (
        "sbom: true",
        "provenance: mode=max",
        "finalize_mainline_release_artifact.py",
        "collect_mainline_image_descriptors.py",
        "/release-artifact:${{ needs.prepare-release.outputs.image_transport_tag }}",
        'DOCKER_BUILD_RECORD_UPLOAD: "false"',
        "plan_service_release_images.py",
        "matrix: ${{ fromJSON(needs.prepare-release.outputs.image_matrix) }}",
        "${{ matrix.environment }}",
        "${{ matrix.runtime_image_owner }}",
        "${{ matrix.image_name }}",
        "BUILD_IMAGE_COUNT: ${{ needs.prepare-release.outputs.build_count }}",
        "REUSE_IMAGE_COUNT: ${{ needs.prepare-release.outputs.reuse_count }}",
        "IMAGE_JOB_COUNT=$((BUILD_IMAGE_COUNT + REUSE_IMAGE_COUNT))",
        '--require-count "build_release_images=${IMAGE_JOB_COUNT}"',
        "id: base_images",
        "runs-on: [self-hosted, macOS, ARM64]",
        "docker/setup-qemu-action@c7c53464625b32c7a7e944ae62b3e17d2b600130",
        "image: docker.io/tonistiigi/binfmt@sha256:b4c6a09270133b3c5b4dff94f83067df4dd27eced195fc6a1dbad102999e24dd",
        "platforms: amd64",
        "cache-image: false",
        "version: v0.35.0",
        "cache-binary: false",
        "clean: false",
        'cache_root="${RUNNER_TEMP}/quwoquan-service-pipeline/go-${RUNNER_ARCH}"',
        'echo "GOCACHE=${cache_root}/go-build" >> "$GITHUB_ENV"',
        'echo "GOMODCACHE=${cache_root}/go-mod" >> "$GITHUB_ENV"',
        "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6",
        "id-token: write",
        "attestations: write",
        "oci_supply_chain.py extract-sbom",
        "Sign image provenance with GitHub OIDC",
        "Sign image SPDX SBOM with GitHub OIDC",
    ):
        if token not in pipeline_text:
            issues.append(
                f"{SERVICE_PIPELINE.relative_to(ROOT)} missing release provenance token: {token}"
            )
    verifier_text = OCI_SUPPLY_CHAIN.read_text(encoding="utf-8")
    for token in (
        "--bundle-from-oci",
        "--signer-workflow",
        "--cert-oidc-issuer",
        "https://token.actions.githubusercontent.com",
        "{{json .SBOM}}",
        "{{json .Provenance}}",
    ):
        if token not in verifier_text:
            issues.append(
                f"{OCI_SUPPLY_CHAIN.relative_to(ROOT)} missing signed OCI verification token: {token}"
            )
    for image_variable, output in (
        ("GO_BASE_IMAGE", "go_base_image"),
        ("ALPINE_BASE_IMAGE", "alpine_base_image"),
        ("PYTHON_BASE_IMAGE", "python_base_image"),
    ):
        if (
            f"{image_variable}: ${{{{ steps.base_images.outputs.{output} }}}}"
            not in pipeline_text
            or f'--build-arg "{image_variable}=${image_variable}"' not in pipeline_text
        ):
            issues.append(
                f"{SERVICE_PIPELINE.relative_to(ROOT)} must pass governed {image_variable} to release image builds"
            )
    for forbidden in (
        "actions/upload-artifact@",
        "name: mainline-release-input",
        "name: mainline-release-artifact",
        "pattern: mainline-image-*",
        "cache-from: type=gha",
        "cache-to: type=gha",
        "runs-on: ubuntu-latest",
        "github.workspace }}/.qwq_output/env/repo/local/ci/cache/go",
    ):
        if forbidden in pipeline_text:
            issues.append(
                f"{SERVICE_PIPELINE.relative_to(ROOT)} still permits ungoverned Actions storage: {forbidden}"
            )
    deploy_script_text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    for token in (
        "readyz/config-convergence",
        "config ACK convergence",
        "all governed service instances did not reach config ACK convergence",
    ):
        if token not in deploy_script_text:
            issues.append(
                f"{DEPLOY_SCRIPT.relative_to(ROOT)} missing config ACK convergence gate: {token}"
            )
    renderer_text = PROD_RENDERER.read_text(encoding="utf-8")
    for token in (
        "CONFIG_ACK_REQUIRED_INSTANCES",
        "SERVICE_INSTANCE_ID",
        "PLATFORM_OPS_BASE_URL",
    ):
        if token not in renderer_text:
            issues.append(
                f"{PROD_RENDERER.relative_to(ROOT)} missing config ACK render binding: {token}"
            )

    if issues:
        print("[verify_prod_rollout_stackctl_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_prod_rollout_stackctl_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
