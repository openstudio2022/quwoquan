from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.gate import verify_github_supply_chain


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t4
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t5
ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = ROOT / ".github" / "workflows"


def _patched_workflow(path: Path, forged: str):
    original_read_text = Path.read_text

    def read_text(candidate: Path, *args: object, **kwargs: object) -> str:
        if candidate == path:
            return forged
        return original_read_text(candidate, *args, **kwargs)

    return mock.patch.object(Path, "read_text", autospec=True, side_effect=read_text)


class GithubSupplyChainContractTest(unittest.TestCase):
    def test_repository_workflows_satisfy_the_supply_chain_gate(self) -> None:
        result = subprocess.run(
            ["python3", "quwoquan_ops/gate/verify_github_supply_chain.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_permanent_workflows_require_minimum_top_level_permissions(self) -> None:
        for name, path in verify_github_supply_chain.RELEASE_WORKFLOWS.items():
            with self.subTest(workflow=name):
                failures = verify_github_supply_chain._verify_top_level_permissions(
                    path,
                    path.read_text(encoding="utf-8"),
                    {"contents: read"},
                )
                self.assertEqual(failures, [])

    def test_dispatch_inputs_are_exact_and_prod_has_no_source_selector(self) -> None:
        qualification = (WORKFLOWS / "release-qualification.yml").read_text(encoding="utf-8")
        selection = (WORKFLOWS / "release-tag-selection.yml").read_text(encoding="utf-8")
        production = (WORKFLOWS / "deploy-prod-auto.yml").read_text(encoding="utf-8")

        self.assertEqual(
            verify_github_supply_chain._dispatch_inputs(qualification),
            {
                "rc_tag_admission_ref",
                "qualification_request_ref",
                "source_git_sha",
                "product_version_manifest_ref",
                "package_acceptance_fact_ref",
                "provider_fact_ref",
                "uat_fact_ref",
                "supply_chain_fact_ref",
            },
        )
        self.assertEqual(
            verify_github_supply_chain._dispatch_inputs(selection),
            {
                "tag_kind",
                "tag_name",
                "source_git_sha",
                "selection_fact_ref",
                "initial_release_authority_ref",
                "selected_rc_admission_ref",
                "qualification_fact_ref",
                "release_authority_fact_ref",
            },
        )
        self.assertEqual(
            verify_github_supply_chain._dispatch_inputs(production),
            {
                "release_tag_admission_ref",
                "previous_active_released_ledger_ref",
                "rollback_readiness_ref",
            },
        )

    def test_release_qualification_builds_through_canonical_reusable_factories(self) -> None:
        path = WORKFLOWS / "release-qualification.yml"
        text = path.read_text(encoding="utf-8")
        self.assertIn("uses: ./.github/workflows/service_pipeline.yml", text)
        self.assertIn("uses: ./.github/workflows/app_pipeline.yml", text)
        self.assertIn("artifact_build_number.py", text)
        self.assertIn("qualification-material", text)
        self.assertIn("qualification-finalize", text)
        self.assertEqual(
            verify_github_supply_chain.verify_release_qualification_controls(),
            [],
        )

    def test_tag_controller_uses_trusted_two_phase_order(self) -> None:
        """controller 即 hosted deploy key（DEC-009）：pre-readback → 双 intent → intent check →
        远端不存在 → 私钥指纹与 /keys 比对 → ssh remote → create-once → 恢复 https remote →
        REST ref/object 读回 → outcome → post-readback → finalize → 删私钥。"""
        selection = WORKFLOWS / "release-tag-selection.yml"
        text = selection.read_text(encoding="utf-8")
        pre_readback = text.index("--phase pre_mutation")
        admit_rc = text.index("tag-admit-rc-intent")
        admit_stable = text.index("tag-admit-stable-intent")
        intent_check = text.index("tag-admission-intent-check")
        remote_absent = text.index("already exists before mutation", intent_check)
        key_match = text.index('test "$LOCAL_FINGERPRINT" = "$HOSTED_FINGERPRINT"')
        ssh_remote = text.index(
            'git remote set-url origin "ssh://git@${GITHUB_SERVER_URL#https://}/${GITHUB_REPOSITORY}.git"'
        )
        create = text.index('git tag -a "$TAG" "$SOURCE_SHA"')
        push = text.index('git push origin "refs/tags/$TAG:refs/tags/$TAG"')
        restored_remote = text.index(
            'git remote set-url origin "https://github.com/${GITHUB_REPOSITORY}.git"',
            push,
        )
        ref_readback = text.index("/git/ref/tags/${TAG}", push)
        object_readback = text.index("/git/tags/${REMOTE_OBJECT_OID}", ref_readback)
        outcome = text.index("tag-mutation-outcome", object_readback)
        post_readback = text.index("--phase post_mutation", outcome)
        finalize = text.index('"tag-admit-$KIND-finalize"', post_readback)
        key_removed = text.index('rm -f "$KEY_FILE"', finalize)

        self.assertLess(pre_readback, admit_rc)
        self.assertLess(pre_readback, admit_stable)
        self.assertLess(max(admit_rc, admit_stable), intent_check)
        self.assertLess(intent_check, remote_absent)
        self.assertLess(remote_absent, key_match)
        self.assertLess(key_match, ssh_remote)
        self.assertLess(ssh_remote, create)
        self.assertLessEqual(create, push)
        self.assertLess(push, restored_remote)
        self.assertLess(restored_remote, ref_readback)
        self.assertLess(ref_readback, object_readback)
        self.assertLess(object_readback, outcome)
        self.assertLess(outcome, post_readback)
        self.assertLess(post_readback, finalize)
        self.assertLess(finalize, key_removed)
        self.assertNotIn("actions/create-github-app-token@", text)
        self.assertNotIn("RELEASE_CONTROLLER_READBACK_URL", text)
        self.assertEqual(
            verify_github_supply_chain.verify_release_tag_selection_controls(),
            [],
        )

    def test_tag_controller_forged_controls_fail_closed(self) -> None:
        selection = WORKFLOWS / "release-tag-selection.yml"
        original = selection.read_text(encoding="utf-8")
        for label, forged in (
            (
                "pre-readback",
                original.replace("--phase pre_mutation", "--phase pre_retired"),
            ),
            (
                "RC intent",
                original.replace("tag-admit-rc-intent", "tag-admit-rc-retired"),
            ),
            (
                "stable intent",
                original.replace(
                    "tag-admit-stable-intent", "tag-admit-stable-retired"
                ),
            ),
            (
                "controller App token resurrected",
                original + "\n      - uses: actions/create-github-app-token@" + "0" * 40 + "\n",
            ),
            (
                "external readback service resurrected",
                original + "\nenv:\n  READBACK_URL: ${{ vars.RELEASE_CONTROLLER_READBACK_URL }}\n",
            ),
            (
                "deploy key fingerprint check",
                original.replace(
                    'test "$LOCAL_FINGERPRINT" = "$HOSTED_FINGERPRINT"',
                    'test -n "$LOCAL_FINGERPRINT"',
                ),
            ),
            (
                "deploy key secret",
                original.replace(
                    "RELEASE_CONTROLLER_DEPLOY_KEY: ${{ secrets.RELEASE_CONTROLLER_DEPLOY_KEY }}",
                    "RELEASE_CONTROLLER_DEPLOY_KEY: ${{ secrets.RETIRED_DEPLOY_KEY }}",
                ),
            ),
            (
                "REST object readback",
                original.replace("/git/tags/${REMOTE_OBJECT_OID}", "/git/commits/${REMOTE_OBJECT_OID}"),
            ),
            (
                "post-readback",
                original.replace("--phase post_mutation", "--phase post_retired"),
            ),
            (
                "finalize",
                original.replace('"tag-admit-$KIND-finalize"', '"tag-admit-$KIND-retired"'),
            ),
            (
                "intent binding in tag message",
                original.replace("release-tag-intent: $INTENT_ID", "release-tag: $TAG"),
            ),
            (
                "private key left on runner",
                original.replace('rm -f "$KEY_FILE"', "echo key-retained"),
            ),
            (
                "checkout credential persistence",
                original.replace("          persist-credentials: false\n", "", 1),
            ),
            (
                "missing remote restoration",
                original.replace(
                    'git remote set-url origin "https://github.com/${GITHUB_REPOSITORY}.git"',
                    "echo remote-restoration-retired",
                ),
            ),
            (
                "force fetch",
                original + "\njobs:\n  forged:\n    steps:\n      - run: git fetch --force origin\n",
            ),
            (
                "fixed creator self assertion",
                original
                + "\n# forged\n      run: echo '\"creator\": \"release-controller[bot]\"'\n",
            ),
            (
                "forced refspec",
                original + "\njobs:\n  forged:\n    steps:\n      - run: git push origin +refs/tags/v1.0.0\n",
            ),
            (
                "external readback dispatch",
                original.replace(
                    "      release_authority_fact_ref:\n",
                    "      creator_readback_ref:\n"
                    "        description: forged external readback\n"
                    "        required: true\n"
                    "        type: string\n"
                    "      ruleset_readback_ref:\n"
                    "        description: forged external readback\n"
                    "        required: true\n"
                    "        type: string\n"
                    "      release_authority_fact_ref:\n",
                ),
            ),
        ):
            with self.subTest(control=label), _patched_workflow(selection, forged):
                failures = verify_github_supply_chain.verify_release_tag_selection_controls()
                self.assertTrue(failures, f"{label} forgery unexpectedly passed")

    def test_tag_controller_rejects_reordered_evidence_phases(self) -> None:
        selection = WORKFLOWS / "release-tag-selection.yml"
        original = selection.read_text(encoding="utf-8")
        ref_readback = original.index("/git/ref/tags/${TAG}", original.index("git push origin"))
        object_readback = original.index("/git/tags/${REMOTE_OBJECT_OID}", ref_readback)
        outcome = original.index("tag-mutation-outcome", object_readback)
        object_line_start = original.rfind("\n", 0, object_readback) + 1
        object_line_end = original.index("\n", object_readback) + 1
        object_line = original[object_line_start:object_line_end]
        without_object = original[:object_line_start] + original[object_line_end:]
        moved_after = without_object.index("\n", without_object.index("tag-mutation-outcome")) + 1
        forged = without_object[:moved_after] + object_line + without_object[moved_after:]

        with _patched_workflow(selection, forged):
            failures = verify_github_supply_chain.verify_release_tag_selection_controls()

        self.assertTrue(
            any("must then remain ordered" in failure for failure in failures),
            failures,
        )

    def test_tag_mutation_outside_unique_controller_fails_closed(self) -> None:
        production = WORKFLOWS / "deploy-prod-auto.yml"
        forged = production.read_text(encoding="utf-8") + "\n# injected\n      run: git tag -a forbidden HEAD\n"

        with _patched_workflow(production, forged):
            failures = verify_github_supply_chain.verify_unique_release_tag_controller()

        self.assertTrue(
            any("outside the unique controller" in failure for failure in failures),
            failures,
        )

    def test_production_reads_attestations_and_runs_canonical_fact_transaction(self) -> None:
        production = WORKFLOWS / "deploy-prod-auto.yml"
        text = production.read_text(encoding="utf-8")
        self.assertIn("environment: production", text)
        self.assertIn("runs-on: [self-hosted, macOS, ARM64]", text)
        self.assertIn("attestations: read", text)
        self.assertIn("prod-admit", text)
        self.assertIn("prod-materialize-input", text)
        self.assertIn("stackctl.py deploy --target prod-hosted", text)
        for control in (
            "--service-factory-material",
            "--app-factory-material",
            "--hosted-receipt-readback",
            "--hosted-soak-readback",
        ):
            self.assertIn(control, text)
        for retired in (
            "verify_release_governance.py",
            "governance-receipt.json",
            "pull-requests: read",
            "--release-evidence-ref",
            "--release-manifest",
            "fetch_mainline_release_artifact.py",
            "releaseEvidenceRef",
        ):
            self.assertNotIn(retired, text)
        self.assertEqual(
            verify_github_supply_chain.verify_production_execution_isolation(),
            [],
        )

    def test_production_factory_and_hosted_readbacks_fail_closed_when_missing(self) -> None:
        production = WORKFLOWS / "deploy-prod-auto.yml"
        original = production.read_text(encoding="utf-8")
        for label, control in (
            ("service factory material", "--service-factory-material"),
            ("App factory material", "--app-factory-material"),
            ("hosted stage receipt readback", "--hosted-receipt-readback"),
            ("hosted soak readback", "--hosted-soak-readback"),
        ):
            self.assertIn(control, original)
            forged = original.replace(control, f"--retired-{control.removeprefix('--')}")
            with self.subTest(control=label), _patched_workflow(production, forged):
                failures = verify_github_supply_chain.verify_production_execution_isolation()
                self.assertTrue(
                    any(
                        f"missing qualified production transaction control: {control}"
                        in failure
                        for failure in failures
                    ),
                    failures,
                )

    def test_production_rejects_retired_release_evidence_surfaces(self) -> None:
        production = WORKFLOWS / "deploy-prod-auto.yml"
        original = production.read_text(encoding="utf-8")
        for retired in (
            "--release-evidence-ref",
            "--release-manifest",
            "fetch_mainline_release_artifact.py",
            "releaseEvidenceRef",
        ):
            self.assertNotIn(retired, original)
            forged = original + (
                "\njobs:\n"
                "  forged_retired_release_surface:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                f"      - run: printf '%s\\n' '{retired}'\n"
            )
            with self.subTest(retired=retired), _patched_workflow(production, forged):
                failures = verify_github_supply_chain.verify_production_execution_isolation()
                self.assertTrue(
                    any(
                        f"contains forbidden production selector, mutation, authority transport, "
                        f"or macOS-incompatible shell builtin: {retired}" in failure
                        for failure in failures
                    ),
                    failures,
                )

    def test_retired_production_runner_label_fails_closed(self) -> None:
        production = WORKFLOWS / "deploy-prod-auto.yml"
        forged = production.read_text(encoding="utf-8").replace(
            "runs-on: [self-hosted, macOS, ARM64]",
            "runs-on: [self-hosted, macOS, prod-release]",
        )

        with _patched_workflow(production, forged):
            failures = verify_github_supply_chain.verify_production_execution_isolation()

        self.assertTrue(
            any("retired prod-release runner label" in failure for failure in failures),
            failures,
        )
        self.assertTrue(
            any(
                "missing qualified production transaction control: "
                "runs-on: [self-hosted, macOS, ARM64]" in failure
                for failure in failures
            ),
            failures,
        )

    def test_invalid_job_context_property_fails_closed(self) -> None:
        backsync = WORKFLOWS / "system-backsync.yml"
        canonical = backsync.read_text(encoding="utf-8")
        needle = (
            "${{ github.repository }}/.github/workflows/system-backsync.yml"
            "@${{ github.ref }}"
        )
        self.assertIn(needle, canonical)
        forged = canonical.replace(needle, "${{ job.workflow_ref }}")

        with _patched_workflow(backsync, forged):
            failures = verify_github_supply_chain.verify_action_pins()

        self.assertTrue(
            any(
                ".github/workflows/system-backsync.yml:" in failure
                and "job.workflow_ref is not a GitHub Actions job context property" in failure
                for failure in failures
            ),
            failures,
        )
        legal = canonical.replace(needle, "${{ job.status }}")
        with _patched_workflow(backsync, legal):
            self.assertEqual(
                [
                    failure
                    for failure in verify_github_supply_chain.verify_action_pins()
                    if "job context property" in failure
                ],
                [],
            )

    def test_job_level_env_rejects_runner_steps_env_and_job_contexts(self) -> None:
        """delivery-gate.yml:27 曾在 job 级 env 里写 `runner.temp`，让 03 在每次 push 上
        以 0-job run 静默失败。job 级 env 只能引用 github/inputs/matrix/needs/secrets/
        strategy/vars；step 级 env 引用 runner/steps 则合法，不得误报。
        """
        gate = WORKFLOWS / "delivery-gate.yml"
        canonical = gate.read_text(encoding="utf-8")
        needle = "      CONTROL_ROOT: ${{ github.workspace }}/.qwq_output/env/repo/runs/release-control"
        self.assertIn(needle, canonical)
        for context in ("runner.temp", "steps.inputs.outputs.x", "env.HOME", "job.status"):
            with self.subTest(context=context):
                forged = canonical.replace(needle, f"      CONTROL_ROOT: ${{{{ {context} }}}}/x")
                with _patched_workflow(gate, forged):
                    failures = verify_github_supply_chain.verify_action_pins()
                self.assertTrue(
                    any(
                        ".github/workflows/delivery-gate.yml:" in failure
                        and "job-level env references the" in failure
                        for failure in failures
                    ),
                    failures,
                )
        # step 级 env（缩进 10）里引用 runner/steps 是合法的，不得被 job 级规则误报。
        step_env = canonical.replace(
            "        env:\n          PR_HEAD_REF: ${{ github.event.pull_request.head.ref }}",
            "        env:\n          SCRATCH: ${{ runner.temp }}/scratch\n"
            "          PR_HEAD_REF: ${{ github.event.pull_request.head.ref }}",
        )
        self.assertNotEqual(step_env, canonical)
        with _patched_workflow(gate, step_env):
            self.assertEqual(
                [
                    failure
                    for failure in verify_github_supply_chain.verify_action_pins()
                    if "job-level env references" in failure
                ],
                [],
            )


if __name__ == "__main__":
    unittest.main()
