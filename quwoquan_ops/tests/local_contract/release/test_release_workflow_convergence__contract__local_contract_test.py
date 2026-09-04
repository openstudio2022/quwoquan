"""Canonical four-environment release workflow contracts."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DELIVERY = ROOT / ".github/workflows/delivery-gate.yml"
CONTROLLED_PROD = ROOT / ".github/workflows/deploy-prod-auto.yml"
GITHUB_TIMING = ROOT / "quwoquan_ops/ci/github_actions_timing.py"
GITHUB_ACTIONS_API = ROOT / "quwoquan_ops/ci/lib/github_actions_api.py"
AI_ADVISORY = ROOT / "quwoquan_ops/ci/ai_ci_advisory.py"
EVIDENCE_GATE = ROOT / "quwoquan_ops/gate/verify_ci_cd_evidence_contracts.py"
BUDGETS = ROOT / "quwoquan_ops/environments/pr_gate_timing_budgets.json"
VALIDATION = ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"
PIPELINE_SPEC = (
    ROOT / "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md"
)
SOURCE_ADMISSION_SPEC_REFS = (
    "spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t1",
    "spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t2",
    "spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t1",
    "spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t2",
)


class ReleaseWorkflowConvergenceContractTest(unittest.TestCase):
    def test_formal_prod_authority_preflight_fails_before_heavy_release_jobs(
        self,
    ) -> None:
        import yaml

        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        jobs = yaml.safe_load(source)["jobs"]
        preflight = jobs["formal_prod_authority_preflight"]
        preflight_commands = "\n".join(
            str(step.get("run") or "") for step in preflight["steps"]
        )

        self.assertEqual(preflight["timeout-minutes"], 1)
        self.assertEqual(preflight["permissions"], {"contents": "read"})
        self.assertIn('EVENT_NAME" != "workflow_dispatch"', preflight_commands)
        self.assertIn('DRY_RUN" == "true"', preflight_commands)
        self.assertIn("applicability=not_applicable", preflight_commands)
        self.assertIn("decision=pass", preflight_commands)
        self.assertIn("OPS.BRANCH.AUTHORITY_UNAVAILABLE", preflight_commands)
        self.assertIn("terminal=blocked", preflight_commands)
        self.assertIn(
            "recovery=restore_git_authority_then_retry", preflight_commands
        )
        self.assertNotIn("hostedProtectionVerified=true", preflight_commands)
        self.assertNotIn("formalProd=true", preflight_commands)

        def run_preflight(dry_run: str) -> tuple[subprocess.CompletedProcess[str], str]:
            with tempfile.TemporaryDirectory() as temporary:
                output_path = Path(temporary) / "github-output"
                result = subprocess.run(
                    ["bash", "-c", preflight_commands],
                    cwd=ROOT,
                    env={
                        **os.environ,
                        "EVENT_NAME": "workflow_dispatch",
                        "DRY_RUN": dry_run,
                        "GITHUB_OUTPUT": str(output_path),
                    },
                    text=True,
                    capture_output=True,
                    check=False,
                )
                output = (
                    output_path.read_text(encoding="utf-8")
                    if output_path.exists()
                    else ""
                )
                return result, output

        dry_run_result, dry_run_output = run_preflight("true")
        self.assertEqual(dry_run_result.returncode, 0)
        self.assertEqual(
            dry_run_output.splitlines(),
            ["applicability=not_applicable", "decision=pass"],
        )
        self.assertNotIn(
            "OPS.BRANCH.AUTHORITY_UNAVAILABLE", dry_run_result.stdout
        )

        formal_result, formal_output = run_preflight("false")
        self.assertEqual(formal_result.returncode, 2)
        self.assertEqual(
            formal_output.splitlines(),
            ["applicability=required", "decision=blocked"],
        )
        self.assertIn("OPS.BRANCH.AUTHORITY_UNAVAILABLE", formal_result.stdout)
        self.assertIn("terminal=blocked", formal_result.stdout)
        self.assertIn(
            "recovery=restore_git_authority_then_retry", formal_result.stdout
        )

        heavy_jobs = (
            "source_context",
            "service_pipeline",
            "app_pipeline",
            "delivery_gate",
            "prepare",
            "alpha_local",
            "beta_device_matrix",
            "gamma_local",
            "preprod_evidence",
            "prod_rollout",
            "prod_soak_acceptance",
        )
        for job_name in heavy_jobs:
            needs = jobs[job_name].get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            self.assertIn(
                "formal_prod_authority_preflight",
                needs,
                f"{job_name} can start before formal Prod authority preflight",
            )

        preflight_offset = source.index("  formal_prod_authority_preflight:\n")
        for job_name in heavy_jobs:
            self.assertLess(preflight_offset, source.index(f"  {job_name}:\n"))

        prod_steps = jobs["prod_rollout"]["steps"]
        defensive = next(
            step
            for step in prod_steps
            if step.get("name")
            == "Defensively recheck formal Prod hosted authority before mutation"
        )
        defensive_commands = str(defensive["run"])
        self.assertEqual(
            defensive["if"],
            "${{ needs.prepare.outputs.dry_run != 'true' }}",
        )
        self.assertIn("OPS.BRANCH.AUTHORITY_UNAVAILABLE", defensive_commands)
        self.assertIn("terminal=blocked", defensive_commands)
        self.assertIn(
            "recovery=restore_git_authority_then_retry", defensive_commands
        )
        mutation_names = (
            "Deploy Prod canary",
            "Deploy Prod 5%",
            "Deploy Prod 20%",
            "Deploy Prod 50%",
            "Deploy Prod 100%",
        )
        step_names = [str(step.get("name") or "") for step in prod_steps]
        defensive_index = step_names.index(str(defensive["name"]))
        for mutation_name in mutation_names:
            self.assertLess(defensive_index, step_names.index(mutation_name))

    def test_source_promotion_admission_precedes_candidate_and_prod_credentials(
        self,
    ) -> None:
        for spec_ref in SOURCE_ADMISSION_SPEC_REFS:
            self.assertTrue(spec_ref.startswith("spec_ref: "))

        import yaml

        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        jobs = yaml.safe_load(source)["jobs"]
        source_context = jobs["source_context"]
        admission_step = next(
            step
            for step in source_context["steps"]
            if step.get("name")
            == "Admit the unique reviewed dev1.0 to main promotion"
        )
        source_commands = "\n".join(
            str(step.get("run") or "") for step in source_context["steps"]
        )

        self.assertEqual(source_context["permissions"]["contents"], "read")
        self.assertEqual(source_context["permissions"]["actions"], "read")
        self.assertEqual(source_context["permissions"]["checks"], "read")
        self.assertEqual(
            source_context["permissions"]["pull-requests"], "read"
        )
        self.assertNotIn("git merge-base --is-ancestor", source_commands)
        self.assertNotIn("EXPECTED_WORKFLOW_REF", source_commands)
        self.assertIn("verify_release_governance.py", source_commands)
        self.assertIn("PyYAML==6.0.3", source_commands)
        self.assertIn('--git-sha "$SOURCE_SHA"', source_commands)
        self.assertNotIn("ADMISSION_DIGEST", source_commands)
        self.assertIn('--minimum-approvals 1', source_commands)
        self.assertIn("$RUNNER_TEMP/source-promotion-admission.json", source_commands)
        self.assertNotIn("--release-manifest", source_commands)
        self.assertIn("OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE", source_commands)
        self.assertNotIn("if", admission_step)
        self.assertNotIn("continue-on-error", admission_step)
        self.assertEqual(
            admission_step["env"]["SOURCE_SHA"],
            "${{ steps.source.outputs.source_git_sha }}",
        )
        self.assertIn('"schema": "prod-source-governance-receipt"', source_commands)

        for producer in ("service_pipeline", "app_pipeline", "delivery_gate"):
            needs = jobs[producer]["needs"]
            if isinstance(needs, str):
                needs = [needs]
            self.assertIn("source_context", needs)

        def depends_on_source_context(job_name: str) -> bool:
            needs = jobs[job_name].get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            return "source_context" in needs or any(
                depends_on_source_context(dependency) for dependency in needs
            )

        for protected_job in (
            "service_pipeline",
            "app_pipeline",
            "delivery_gate",
            "prepare",
            "alpha_local",
            "beta_device_matrix",
            "gamma_local",
            "preprod_evidence",
            "prod_rollout",
            "prod_soak_acceptance",
        ):
            self.assertTrue(
                depends_on_source_context(protected_job),
                f"{protected_job} could run after rejected direct/non-dev promotion",
            )

        self.assertEqual(
            jobs["mainline_summary"]["if"],
            "${{ always() && needs.source_context.result == 'success' }}",
        )
        early_admission = source.index(
            "Admit the unique reviewed dev1.0 to main promotion"
        )
        for protected_operation in (
            "Service Pipeline (same mainline DAG)",
            "App package evidence (same mainline DAG)",
            "Delivery Gate (mainline)",
            "Publish sealed candidate evidence",
            "Materialize hosted service-plane SSH credential",
            "Materialize hosted rollout SSH credentials",
            "Deploy Prod canary",
        ):
            self.assertLess(early_admission, source.index(protected_operation))

        formal_block = source.index(
            "Defensively recheck formal Prod hosted authority before mutation"
        )
        self.assertLess(
            formal_block,
            source.index("Materialize hosted rollout SSH credentials"),
        )
        self.assertIn("OPS.BRANCH.AUTHORITY_UNAVAILABLE", source[formal_block:])

    def test_release_budgets_have_one_unversioned_10_30_contract(self) -> None:
        payload = json.loads(BUDGETS.read_text(encoding="utf-8"))
        self.assertNotIn("version", payload)
        self.assertEqual(payload["softBudgetSeconds"], 600)
        self.assertEqual(payload["hardFailSeconds"], 1800)
        self.assertEqual(payload["promotionCutoffSeconds"], 1500)
        gate = payload["gates"]["07.mainline_auto_prod"]
        self.assertEqual(gate["budgetSeconds"], 600)
        self.assertEqual(gate["hardFailSeconds"], 1800)
        self.assertEqual(gate["promotionCutoffSeconds"], 1500)
        self.assertNotIn("07.main_commit_to_prod", payload["gates"])
        self.assertIn("workflow run created_at", gate["criticalPath"])
        self.assertIn("official approval waits", gate["criticalPath"])
        self.assertIn(
            "max(service_pipeline, app_pipeline, delivery_gate)",
            gate["machinePath"],
        )
        self.assertIn(
            "max(alpha_stage, beta_device_matrix, gamma_local)",
            gate["machinePath"],
        )

    def test_mainline_profile_is_unversioned_and_keeps_beta_device_scope(self) -> None:
        payload = json.loads(VALIDATION.read_text(encoding="utf-8"))
        self.assertNotIn("version", payload)
        profile = payload["profiles"]["mainline_auto_prod"]
        self.assertEqual(profile["deviceMatrix"]["envs"], ["beta"])
        self.assertIn("Gamma-local release-fast", profile["description"])
        self.assertIn("600", profile["description"])
        self.assertIn("1800", profile["description"])
        self.assertIn("1500", profile["description"])

    def test_delivery_gate_measures_every_app_shard_from_jobs_api(self) -> None:
        source = DELIVERY.read_text(encoding="utf-8")
        helper = GITHUB_TIMING.read_text(encoding="utf-8")
        actions_api = GITHUB_ACTIONS_API.read_text(encoding="utf-8")
        self.assertIn("github_actions_timing.py", source)
        self.assertIn('--require-count "app_tests=4"', source)
        self.assertIn('shard_index: [0, 1, 2, 3]', source)
        self.assertIn("run, jobs, _ = load_run_and_jobs(", helper)
        self.assertNotIn("/actions/runs/", helper)
        self.assertNotIn('"filter": "latest"', helper)
        self.assertIn("/actions/runs/", actions_api)
        self.assertIn('f"{run_url}/jobs"', actions_api)
        self.assertIn('query={"filter": "latest"}', actions_api)
        self.assertIn("--critical-path-source github_run_calendar", source)
        self.assertIn("--machine-critical-path-seconds", source)
        self.assertIn("CALENDAR_SECONDS", source)
        self.assertIn("outputs.machine_critical_path_seconds", source)
        self.assertNotIn("outputs.critical_path_seconds", source)
        self.assertNotIn("approximate wall", source)
        self.assertNotIn("wall≈", source)

    def test_controlled_workflow_has_four_environment_blocking_chain(self) -> None:
        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        import yaml

        jobs = yaml.safe_load(source)["jobs"]
        self.assertEqual(jobs["source_context"]["timeout-minutes"], 2)
        self.assertEqual(jobs["prepare"]["timeout-minutes"], 10)
        self.assertEqual(jobs["alpha_local"]["timeout-minutes"], 8)
        self.assertEqual(jobs["gamma_local"]["timeout-minutes"], 8)
        self.assertEqual(jobs["preprod_evidence"]["timeout-minutes"], 2)
        self.assertEqual(jobs["prod_rollout"]["timeout-minutes"], 30)
        self.assertIn("--critical-path-source github_run_calendar", source)
        self.assertIn("--machine-critical-path-seconds", source)
        self.assertIn(
            "needs.service_pipeline.outputs.machine_critical_path_seconds",
            source,
        )
        self.assertIn(
            "needs.app_pipeline.outputs.machine_critical_path_seconds",
            source,
        )
        self.assertIn(
            "needs.delivery_gate.outputs.machine_critical_path_seconds",
            source,
        )
        self.assertIn(
            "needs.beta_device_matrix.outputs.machine_critical_path_seconds",
            source,
        )
        self.assertNotIn("outputs.critical_path_seconds", source)
        self.assertIn(
            "APPROVAL_EVIDENCE_REASON",
            source,
        )
        self.assertIn("Canonical summary remains historical_incomplete", source)
        self.assertIn("  gamma_local:\n", source)
        self.assertIn("--target gamma-local", source)
        self.assertIn("--profile release", source)
        for job_name, target_name in (
            ("alpha_local", "alpha-local"),
            ("gamma_local", "gamma-local"),
        ):
            job_commands = "\n".join(
                str(step.get("run") or "") for step in jobs[job_name]["steps"]
            )
            self.assertIn(f"--target {target_name}", job_commands)
            self.assertIn("--formal-release", job_commands)
            self.assertIn(
                '--release-manifest "$QWQ_PROD_RELEASE_ARTIFACT_ROOT/manifest.json"',
                job_commands,
            )
            self.assertIn("--skip-build", job_commands)
            self.assertIn("--skip-app", job_commands)
        self.assertIn("  prod_rollout:\n", source)
        self.assertNotIn("  prod_initial:\n", source)
        self.assertNotIn("  prod_carry_on:\n", source)
        self.assertNotIn("  prod_full:\n", source)
        self.assertEqual(source.count("environment: production"), 1)
        self.assertIn("'production' || 'release-validation'", source)
        self.assertIn("  prod_soak_acceptance:\n", source)
        self.assertEqual(
            jobs["prod_soak_acceptance"]["environment"],
            "production",
        )
        self.assertGreaterEqual(
            jobs["prod_soak_acceptance"]["timeout-minutes"],
            1500,
        )
        self.assertIn("- alpha_local\n      - beta_device_matrix\n      - gamma_local", source)

    def test_mainline_timing_uses_exact_oci_and_hosted_append_only_authority(
        self,
    ) -> None:
        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        mainline = source[source.index("  mainline_summary:\n") :]
        publish = mainline.index("Publish canonical CiTimingSummary to immutable OCI")
        bind = mainline.index("Bind exact timing OCI into hosted append-only authority")
        query = mainline.index("Query hosted timing authority and verify readback")
        diagnostic = mainline.index("Upload diagnostic timing copy (non-authoritative)")

        self.assertIn("packages: write", mainline)
        self.assertIn("ci_timing_summary.Dockerfile", mainline)
        self.assertIn(
            "ghcr.io/${{ github.repository }}/ci-timing-summary@${TIMING_EVIDENCE_DIGEST}",
            mainline,
        )
        self.assertIn("sync_hosted_ci_timing_ledger.py bind", mainline)
        self.assertIn("sync_hosted_ci_timing_ledger.py query", mainline)
        self.assertIn("hosted-bind-readback.json", mainline)
        self.assertIn("hosted-query-readback.json", mainline)
        self.assertIn("cmp -s", mainline)
        self.assertLess(publish, bind)
        self.assertLess(bind, query)
        self.assertLess(query, diagnostic)
        self.assertNotIn("continue-on-error: true", mainline[bind:diagnostic])

    def test_actions_artifact_is_only_a_short_lived_diagnostic_copy(self) -> None:
        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        mainline = source[source.index("  mainline_summary:\n") :]
        artifact = mainline.index("Upload diagnostic timing copy (non-authoritative)")
        authority = mainline.index("Query hosted timing authority and verify readback")

        self.assertGreater(artifact, authority)
        self.assertIn("retention-days: 3", mainline[artifact:])
        self.assertIn("continue-on-error: true", mainline[artifact:])

    def test_job_created_at_gap_is_rendered_then_fails_closed(self) -> None:
        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        mainline = source[source.index("  mainline_summary:\n") :]
        helper = GITHUB_TIMING.read_text(encoding="utf-8")

        self.assertIn('result["missing_evidence"] = "githubJobs.createdAt"', helper)
        self.assertIn("UPSTREAM_MISSING_EVIDENCE", mainline)
        self.assertIn('--missing-evidence "$UPSTREAM_MISSING_EVIDENCE"', mainline)
        self.assertIn("timing is historical_incomplete", mainline)
        self.assertNotIn('--queue-seconds "0"', mainline)

    def test_mainline_failure_path_publishes_incomplete_summary_without_fabrication(
        self,
    ) -> None:
        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        mainline = source[source.index("  mainline_summary:\n") :]
        fallback = mainline.index(
            "Preserve canonical failure-path timing without fabrication"
        )
        publish = mainline.index("Publish canonical CiTimingSummary to immutable OCI")

        self.assertIn(
            "ref: ${{ needs.source_context.outputs.source_git_sha || github.sha }}",
            mainline,
        )
        self.assertIn("if: ${{ steps.workflow_timing.outcome == 'success' }}", mainline)
        self.assertIn('if [[ -s "$SUMMARY" ]]', mainline[fallback:publish])
        self.assertIn('--workflow-run-id "${{ github.run_id }}"', mainline[fallback:publish])
        self.assertIn('--source-git-sha "${{ github.sha }}"', mainline[fallback:publish])
        self.assertIn(
            '--missing-evidence "workflowTiming.authoritativeDAG"',
            mainline[fallback:publish],
        )
        self.assertIn('CANDIDATE_ARGS+=(--candidate-digest "$CANDIDATE_DIGEST")', mainline[fallback:publish])
        self.assertNotIn("--machine-critical-path-seconds", mainline[fallback:publish])
        self.assertLess(fallback, publish)
        self.assertIn("Bind exact timing OCI into hosted append-only authority", mainline[publish:])

    def test_ai_and_evidence_gate_have_no_hosted_timing_write_path(self) -> None:
        for path in (AI_ADVISORY, EVIDENCE_GATE):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("sync_hosted_ci_timing_ledger.py bind", source)
            self.assertNotIn("_remote_action(action=\"bind\"", source)

    def test_prod_transaction_materializes_once_and_uses_candidate_identity(self) -> None:
        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        prod = source[
            source.index("  prod_rollout:\n") :
            source.index("  prod_soak_acceptance:\n")
        ]
        soak = source[
            source.index("  prod_soak_acceptance:\n") :
            source.index("  mainline_summary:\n")
        ]
        self.assertEqual(prod.count("fetch_mainline_release_artifact.py"), 1)
        self.assertEqual(soak.count("fetch_mainline_release_artifact.py"), 1)
        self.assertEqual(prod.count("verify_release_governance.py"), 1)
        self.assertEqual(prod.count("Materialize canonical configuration packages once"), 1)
        self.assertEqual(prod.count("QWQ_PROD_RELEASE_ARTIFACT_ROOT"), 1)
        self.assertEqual(prod.count("docker/login-action@"), 1)
        for stage in ("canary", "5", "20", "50", "100"):
            self.assertEqual(prod.count(f"--stage {stage} \\"), 1)
        self.assertGreaterEqual(prod.count("--from-candidate-digest"), 5)
        self.assertEqual(prod.count("--to-candidate-digest"), 5)
        self.assertEqual(prod.count("--release-evidence-ref"), 5)
        self.assertNotIn("--from-image", prod)
        self.assertNotIn("--to-image", prod)
        self.assertNotIn("--from-config", prod)
        self.assertNotIn("--to-config", prod)
        self.assertIn("needs.prepare.outputs.resume_stage", prod)
        self.assertEqual(prod.count("--promotion-deadline-epoch"), 5)
        self.assertEqual(prod.count("--hard-deadline-epoch"), 6)
        self.assertIn("'production' || 'release-validation'", prod)
        self.assertIn("timeout-minutes: 30", prod)
        self.assertIn("--readback-output", source)
        self.assertIn("existing_release_evidence_ref", source)
        for field in (
            "canary_receipt_id",
            "percent_5_receipt_id",
            "percent_20_receipt_id",
            "percent_50_receipt_id",
            "percent_100_receipt_id",
        ):
            self.assertIn(field, prod)
        for legacy in (
            "gray-initial",
            "carry-on",
            "gray_initial_receipt_id",
            "carry_on_receipt_id",
            "full_receipt_id",
        ):
            self.assertNotIn(legacy, prod)
        self.assertIn("render_hosted_release_stage_report.py", prod)
        self.assertIn('decision == "rolled_back"', prod)
        self.assertNotIn('decision in {"rolled_back", "rollback_failed"}', prod)
        self.assertIn("PROD_SSH_HOST: ${{ secrets.PROD_SSH_HOST }}", prod)
        self.assertIn(
            "QWQ_PROD_ROLLOUT_EVIDENCE_ROOT: ${{ secrets.PROD_ROLLOUT_STAGE_EVIDENCE_ROOT }}",
            prod,
        )
        self.assertNotIn("vars.PROD_ROLLOUT_STAGE_EVIDENCE_ROOT", prod)
        validation = prod.index("Validate protected rollout promotion evidence root")
        initial_apply = prod.index("Deploy Prod canary")
        self.assertLess(validation, initial_apply)
        validation_source = prod[validation:initial_apply]
        for guard in (
            "root.is_absolute()",
            "os.lstat(root)",
            "stat.S_ISLNK(metadata.st_mode)",
            "stat.S_ISDIR(metadata.st_mode)",
            "metadata.st_uid != os.getuid()",
            "stat.S_IWGRP | stat.S_IWOTH",
        ):
            self.assertIn(guard, validation_source)
        self.assertIn("needs.prepare.outputs.dry_run != 'true'", validation_source)
        for stage in ("canary", "5", "20", "50", "100"):
            self.assertEqual(
                prod.count(
                    f'--promotion-evidence "$QWQ_PROD_ROLLOUT_EVIDENCE_ROOT/{stage}.json"'
                ),
                1,
            )
        self.assertIn("PROD_EDGE_SSH_KEY_FILE=$EDGE_KEY_FILE", prod)
        self.assertIn("PROD_SERVICE_SSH_KEY_FILE=$KEY_FILE", prod)
        self.assertNotIn("PROD_SERVICE_SSH_KEY: ${{ secrets.PROD_SERVICE_SSH_KEY }}", prod)

    def test_dry_run_does_not_fabricate_later_ledger_stages(self) -> None:
        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        self.assertIn("default: true", source)
        self.assertIn("real Prod apply requires explicit workflow_dispatch", source)
        self.assertIn("'production' || 'release-validation'", source)
        self.assertIn("Dry-run remained read-only after canary validation", source)
        for stage in (
            "Deploy Prod 5%",
            "Deploy Prod 20%",
            "Deploy Prod 50%",
            "Deploy Prod 100%",
        ):
            offset = source.index(stage)
            guarded = source[offset : offset + 300]
            self.assertIn(
                "needs.prepare.outputs.dry_run != 'true'", guarded
            )
        terminal = source[source.index("Seal terminal Prod outcome") :]
        self.assertIn("needs.prepare.outputs.dry_run != 'true'", terminal)
        summary = source[source.index("  mainline_summary:\n") :]
        self.assertIn('if [[ "$DRY_RUN" != "true" ]]; then', summary)
        self.assertIn("automatic dry-run must not execute Prod soak", summary)
        self.assertIn("rollback-readiness", source)

    def test_prod_lifecycle_is_sealed_before_and_after_apply(self) -> None:
        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        prod = source[source.index("  prod_rollout:\n") : source.index("  mainline_summary:\n")]
        readiness = prod.index("render_release_lifecycle_receipts.py rollback-readiness")
        require_deployable = prod.index("--require-deployable")
        initial_apply = prod.index("Deploy Prod canary")
        outcome = prod.index("render_release_lifecycle_receipts.py prod-outcome")
        terminal_publish = prod.index("Publish immutable terminal ReleaseEvidenceManifest")
        self.assertLess(readiness, require_deployable)
        self.assertLess(require_deployable, initial_apply)
        self.assertLess(initial_apply, outcome)
        self.assertLess(outcome, terminal_publish)
        self.assertIn("PROD_ROLLBACK_DRILL_RECEIPT_ID", prod)
        self.assertIn("release-ledger-fetch", prod)
        self.assertIn("release-ledger-receipt", prod)
        self.assertIn("--environment-receipts-dir", prod)
        self.assertIn("--rollout-receipt", prod)
        self.assertIn("--rollback-receipt", prod)
        self.assertNotIn("release-artifact:sha-", source)
        self.assertIn('--release-outcome "$RELEASE_OUTCOME"', source)
        self.assertIn('PROD_RELEASE_STATUS: ${{ needs.prod_rollout.outputs.release_status }}', source)
        self.assertIn('PROD_RELEASE_STATUS}" != "released', source)

    def test_workflow_rejects_legacy_release_evidence_envelopes(self) -> None:
        source = CONTROLLED_PROD.read_text(encoding="utf-8")
        self.assertIn("release_evidence_ref", source)
        self.assertIn("verify_workflow_release_candidate.py", source)
        self.assertIn("--require-deployable", source)
        self.assertNotIn(
            'manifest.get("candidateId") != manifest.get("artifactDigest")', source
        )
        for forbidden in (
            "release_artifact_ref",
            "mainline-release-artifact",
            "manifestDigest",
            'manifest["versions"]',
            "releaseFiles",
            "schemaVersion",
            "contractVersion",
            "registryRevision",
        ):
            self.assertNotIn(forbidden, source)

    def test_feature_spec_declares_honest_10_30_gate(self) -> None:
        source = PIPELINE_SPEC.read_text(encoding="utf-8")
        self.assertIn("alpha -> beta -> gamma", source)
        self.assertIn("600 秒", source)
        self.assertIn("1800 秒", source)
        self.assertIn("1500 秒", source)
        self.assertIn("historical_incomplete", source)


if __name__ == "__main__":
    unittest.main()
