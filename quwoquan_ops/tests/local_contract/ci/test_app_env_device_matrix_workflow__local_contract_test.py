from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t2

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
PROFILES = ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"
TIMING_BUDGETS = ROOT / "quwoquan_ops/environments/pr_gate_timing_budgets.json"
MOBILE_MATRIX_RUNNER = ROOT / "quwoquan_ops/ci/run_mobile_platform_matrix.sh"
CONCURRENCY_GROUP_EXPRESSION = (
    "group: app-env-device-matrix-${{ (inputs.validation_profile == '' && "
    "(github.event_name == 'push' || github.event_name == 'pull_request')) && "
    "format('pr-light-{0}-{1}', github.event_name, github.ref) || "
    "'shared-runtime' }}"
)


def _expected_concurrency_group(
    *, event_name: str, selected_profile: str, git_ref: str
) -> str:
    if selected_profile == "" and event_name in {"push", "pull_request"}:
        return f"app-env-device-matrix-pr-light-{event_name}-{git_ref}"
    return "app-env-device-matrix-shared-runtime"


def _run_stubbed_mobile_matrix(
    tmp_path: Path, *, matrix_kind: str, video_work_id: str = ""
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / f"bin-{matrix_kind}"
    bin_dir.mkdir()
    invocation_log = tmp_path / f"{matrix_kind}-invocations"
    python_stub = bin_dir / "python3"
    python_stub.write_text(
        """#!/bin/sh
if [ "${1:-}" = - ]; then
  if [ -n "${MOBILE_MATRIX_ENV_JSON_VALUE:-}" ]; then
    printf '%s\n' beta
  elif [ -n "${MOBILE_MATRIX_KIND_VALUE:-}" ]; then
    printf '%s\n' "$MOBILE_MATRIX_KIND_VALUE"
  elif [ "${2:-}" = beta-local ]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      http://api http://ops http://avatar http://image http://video http://upload ws://rtc
  else
    echo "unexpected inline python invocation: $*" >&2
    exit 91
  fi
  exit 0
fi
printf '%s\n' "$*" >> "$MOBILE_MATRIX_INVOCATION_LOG"
exit 0
""",
        encoding="utf-8",
    )
    python_stub.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "MOBILE_PLATFORM": "android",
        "MOBILE_DEVICE_ID": "emulator-contract",
        "MOBILE_MATRIX_ENV_JSON": '["beta"]',
        "MOBILE_MATRIX_KIND": matrix_kind,
        "MOBILE_MATRIX_INVOCATION_LOG": str(invocation_log),
        "QWQ_OUTPUT_ROOT": str(tmp_path / "output"),
    }
    environment.pop("VIDEO_PLAYBACK_CANARY_WORK_ID", None)
    if video_work_id:
        environment["VIDEO_PLAYBACK_CANARY_WORK_ID"] = video_work_id
    completed = subprocess.run(
        ["/bin/bash", str(MOBILE_MATRIX_RUNNER)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    invocations = (
        invocation_log.read_text(encoding="utf-8").splitlines()
        if invocation_log.exists()
        else []
    )
    return completed, invocations


class AppEnvDeviceMatrixWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
        cls.timing_budgets = json.loads(TIMING_BUDGETS.read_text(encoding="utf-8"))

    def test_promotion_pull_request_is_gated_by_canonical_branch_policy(self) -> None:
        self.assertNotIn("pull_request:\n    branches:", self.workflow)
        self.assertIn("App Matrix — Impact Plan", self.workflow)
        self.assertIn("Generate and validate typed device impact plan", self.workflow)
        self.assertIn("App Matrix — Branch Policy", self.workflow)
        self.assertIn("Enforce canonical repository branch admission", self.workflow)
        self.assertIn("needs: branch_policy", self.workflow)

    def test_pr_light_events_do_not_cancel_each_other_or_relax_full_runtime_serialisation(
        self,
    ) -> None:
        concurrency = self.workflow.split("concurrency:\n", maxsplit=1)[1].split(
            "\njobs:\n", maxsplit=1
        )[0]
        self.assertIn(CONCURRENCY_GROUP_EXPRESSION, concurrency)
        self.assertIn("cancel-in-progress: false", concurrency)

        cases = (
            (
                "push",
                "",
                "refs/heads/dev1.0",
                "app-env-device-matrix-pr-light-push-refs/heads/dev1.0",
            ),
            (
                "pull_request",
                "",
                "refs/pull/60/merge",
                "app-env-device-matrix-pr-light-pull_request-refs/pull/60/merge",
            ),
            (
                "workflow_call",
                "mainline_auto_prod",
                "refs/heads/main",
                "app-env-device-matrix-shared-runtime",
            ),
            (
                "workflow_dispatch",
                "manual_full",
                "refs/heads/dev1.0",
                "app-env-device-matrix-shared-runtime",
            ),
            (
                "schedule",
                "nightly_full",
                "refs/heads/main",
                "app-env-device-matrix-shared-runtime",
            ),
        )
        for event_name, selected_profile, git_ref, expected in cases:
            with self.subTest(event_name=event_name, profile=selected_profile):
                self.assertEqual(
                    _expected_concurrency_group(
                        event_name=event_name,
                        selected_profile=selected_profile,
                        git_ref=git_ref,
                    ),
                    expected,
                )

    def test_pr_light_binds_checkout_to_the_exact_pull_request_head(self) -> None:
        self.assertIn(
            "DEFAULT_SOURCE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}",
            self.workflow,
        )
        self.assertIn(
            'CHECKOUT_REF="${INPUT_CHECKOUT_REF:-$DEFAULT_SOURCE_SHA}"',
            self.workflow,
        )
        self.assertNotIn('CHECKOUT_REF="${INPUT_CHECKOUT_REF:-${{ github.sha }}}"', self.workflow)

    def test_pr_light_is_content_free_but_full_profiles_keep_release_readback(self) -> None:
        profiles = self.profiles["profiles"]
        self.assertEqual(
            profiles["pr_light"]["deviceMatrix"]["matrixKinds"],
            ["assistant", "environment-smoke"],
        )
        self.assertTrue(profiles["pr_light"]["deviceMatrix"]["requireAllPlatforms"])
        for profile_name in ("manual_full", "nightly_full", "release_candidate"):
            self.assertIn(
                "app-core-readback",
                profiles[profile_name]["deviceMatrix"]["matrixKinds"],
            )

    def test_content_free_smoke_dispatches_without_video_canary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, invocations = _run_stubbed_mobile_matrix(
                Path(temp_dir), matrix_kind="environment-smoke"
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(invocations), 1)
        invocation = invocations[0]
        self.assertIn("run_environment_patrol_smoke.py", invocation)
        self.assertIn("basic_viability__user_acceptance_test.dart", invocation)
        self.assertNotIn("--video-playback-canary-work-id", invocation)

    def test_release_readback_fails_before_dispatch_without_video_canary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, invocations = _run_stubbed_mobile_matrix(
                Path(temp_dir), matrix_kind="app-core-readback"
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(invocations, [])
        self.assertIn("VIDEO_PLAYBACK_CANARY_WORK_ID is required", result.stdout)

    def test_release_readback_dispatches_exact_video_canary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, invocations = _run_stubbed_mobile_matrix(
                Path(temp_dir),
                matrix_kind="app-core-readback",
                video_work_id="release-video-42",
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(invocations), 1)
        invocation = invocations[0]
        self.assertIn("app_core_readback__user_acceptance_test.dart", invocation)
        self.assertIn(
            "--video-playback-canary-work-id release-video-42", invocation
        )

    def run_summary(
        self,
        *,
        enabled: bool,
        debug_skip_requested: bool = False,
        stack: str = "success",
        android: str = "success",
        ios: str = "success",
        aggregate: str = "success",
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        summary_section = self.workflow.split(
            "      - id: summary\n", maxsplit=1
        )[1].split("\n\n  attest_nightly_receipt:", maxsplit=1)[0]
        script = textwrap.dedent(
            summary_section.split("        run: |\n", maxsplit=1)[1]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "github-output"
            env = {
                **os.environ,
                "SELF_HOSTED_ENABLED": str(enabled).lower(),
                "DEBUG_SKIP_REQUESTED": str(debug_skip_requested).lower(),
                "STACK": stack,
                "ANDROID": android,
                "IOS": ios,
                "AGGREGATE": aggregate,
                "TEARDOWN": "skipped",
                "FORMAL_RUNTIME_STARTED": "false",
                "MANAGED_RUNTIME_STARTED": "false",
                "ALLOW_MISSING": "false",
                "SUMMARY_REPO_DIR": str(ROOT),
                "GITHUB_OUTPUT": str(output),
            }
            result = subprocess.run(
                ["bash", "-c", script],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            return result, output.read_text(encoding="utf-8") if output.exists() else ""

    def test_required_path_missing_enablement_variable_fails_closed(self) -> None:
        result, output = self.run_summary(enabled=False)

        self.assertEqual(result.returncode, 2)
        self.assertIn("ENABLE_SELF_HOSTED_MOBILE_MATRIX must equal true", result.stdout)
        self.assertNotIn("result=success", output)

    def test_explicit_standalone_manual_debug_can_report_skipped(self) -> None:
        self.assertIn("allow_disabled_mobile_matrix_debug:", self.workflow)
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && "
            "inputs.allow_disabled_mobile_matrix_debug == true",
            self.workflow,
        )
        result, output = self.run_summary(
            enabled=False,
            debug_skip_requested=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, "result=skipped\n")

    def test_missing_ios_platform_fails_closed(self) -> None:
        result, output = self.run_summary(enabled=True, ios="skipped")

        self.assertEqual(result.returncode, 1)
        self.assertIn("ios expected success, got skipped", result.stderr)
        self.assertNotIn("result=success", output)

    def test_dual_platform_success_is_aggregated(self) -> None:
        result, output = self.run_summary(enabled=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, "result=success\n")
        self.assertIn("device matrix gate passed", result.stdout)

    def test_nightly_schedule_resolves_to_strict_full_profile(self) -> None:
        self.assertIn("- cron: '0 18 * * *'", self.workflow)
        self.assertIn(
            'if [ "$EVENT_NAME" = "schedule" ]; then PROFILE="nightly_full"; fi',
            self.workflow,
        )
        nightly = self.profiles["profiles"]["nightly_full"]
        self.assertTrue(nightly["readinessBlocking"])
        self.assertTrue(nightly["deviceMatrix"]["requireAllPlatforms"])
        self.assertEqual(nightly["deviceMatrix"]["envs"], ["gamma"])

    def test_full_profile_has_bounded_managed_runtime_and_attestations(self) -> None:
        self.assertIn("beta_stack:\n", self.workflow)
        self.assertIn("    timeout-minutes: 20\n", self.workflow)
        self.assertNotIn("&& 20 || 10", self.workflow)
        self.assertIn("name: Start stackctl-managed Gamma full runtime", self.workflow)
        self.assertIn(
            "steps.defaults.outputs.profile == 'nightly_full'",
            self.workflow,
        )
        self.assertIn(
            "name: Verify OIDC, manifest and complete artifact closure",
            self.workflow,
        )
        self.assertIn(
            "echo \"QWQ_RELEASE_ATTESTATION=${{ steps.release.outputs.pilot_release_path }}\"",
            self.workflow,
        )
        self.assertIn(
            "echo \"QWQ_ROLLBACK_RELEASE_ATTESTATION=${{ steps.release.outputs.pilot_rollback_path }}\"",
            self.workflow,
        )
        self.assertIn(
            'for attestation in "$QWQ_RELEASE_ATTESTATION" '
            '"$QWQ_ROLLBACK_RELEASE_ATTESTATION"',
            self.workflow,
        )
        self.assertIn(
            '[[ -z "$attestation" || ! -s "$attestation" ]]',
            self.workflow,
        )
        self.assertIn("--env gamma", self.workflow)
        managed_runtime = self.workflow.split(
            "name: Start stackctl-managed Gamma full runtime", maxsplit=1
        )[1].split(
            "name: Inspect and doctor the managed Gamma runtime before soak", maxsplit=1
        )[0]
        self.assertNotIn("--release-attestation", managed_runtime)
        self.assertNotIn("--rollback-release-attestation", managed_runtime)
        self.assertIn("echo \"started=true\" >> \"$GITHUB_OUTPUT\"", self.workflow)
        timing_gate = self.timing_budgets["gates"]["05.app_env_device_matrix_pr"]
        self.assertEqual(
            timing_gate["profileTiming"],
            {
                "pr_light": {"policy": "telemetry_advisory", "hardFailSeconds": 5400},
                "manual_full": {"policy": "telemetry_advisory", "hardFailSeconds": 7200},
                "release_candidate": {"policy": "telemetry_advisory", "hardFailSeconds": 7200},
                "mainline_auto_prod": {"policy": "release_sla", "hardFailSeconds": 7800},
                "nightly_full": {"policy": "telemetry_advisory", "hardFailSeconds": 7200},
            },
        )
        self.assertEqual(timing_gate["timingPolicy"], "telemetry_advisory")
        self.assertEqual(
            set(timing_gate["phaseBudgetsSeconds"]),
            {"beta_stack", "android", "ios", "aggregation"},
        )
        self.assertNotIn("profileHardFailSeconds", self.workflow)
        self.assertIn('--budget-profile "$VALIDATION_PROFILE"', self.workflow)
        self.assertIn('"$timing_policy_class" == release_sla', self.workflow)
        self.assertIn('"$timing_outcome" == GATE_BLOCK', self.workflow)
        self.assertIn("GATE_BLOCK: canonical App device release SLA exceeded", self.workflow)
        self.assertIn("TIMING_PR_WARN", self.workflow)
        self.assertNotIn(
            '"$calendar_lead_time_seconds" -gt "$profile_hard_fail_seconds"',
            self.workflow,
        )

    def test_managed_dev_session_command_matches_current_stackctl_argparse(self) -> None:
        managed_runtime = self.workflow.split(
            "name: Start stackctl-managed Gamma full runtime", maxsplit=1
        )[1].split(
            "name: Inspect and doctor the managed Gamma runtime before soak", maxsplit=1
        )[0]
        command_lines = managed_runtime.split(
            "python3 quwoquan_ops/cli/stackctl.py dev-session", maxsplit=1
        )[1].split("SESSION_KIND=", maxsplit=1)[0]
        command_text = "dev-session " + " ".join(
            line.strip().removesuffix("\\").strip()
            for line in command_lines.splitlines()
            if line.strip()
        )
        arguments = shlex.split(command_text)

        from quwoquan_ops.cli import stackctl

        parsed = stackctl.build_parser().parse_args(arguments)
        self.assertEqual(parsed.command, "dev-session")
        self.assertEqual(parsed.env, "gamma")
        self.assertEqual(parsed.report_dir, "$ROOT/dev-session")
        self.assertNotIn("--release-attestation", arguments)
        self.assertNotIn("--rollback-release-attestation", arguments)

        # output-format 是 stackctl 全局参数，必须位于子命令前；app-content-uat
        # 的 adapter 使用当前 --targets/--platform/--device-id 名称。
        uat = stackctl.build_parser().parse_args(
            [
                "--output-format",
                "json",
                "app-content-uat",
                "--targets",
                "alpha-local,gamma-local",
                "--platform",
                "ios-simulator",
                "--device-id",
                "simulator-contract",
            ]
        )
        self.assertEqual(uat.output_format, "json")
        self.assertEqual(uat.targets, "alpha-local,gamma-local")
        self.assertEqual(uat.platform, "ios-simulator")
        self.assertEqual(uat.device_id, "simulator-contract")

    def test_formal_package_keeps_its_current_legal_arguments(self) -> None:
        formal_runtime = self.workflow.split(
            "name: Run immutable Beta formal runtime", maxsplit=1
        )[1].split(
            "name: Verify nightly runtime release matches candidate", maxsplit=1
        )[0]
        package = formal_runtime.split(
            "python3 quwoquan_ops/cli/stackctl.py package", maxsplit=1
        )[1].split("cp \"$ROOT/package/report.json\"", maxsplit=1)[0]
        self.assertIn("--env beta", package)
        self.assertIn("--include-services", package)
        self.assertIn('--report-dir "$ROOT/package"', package)

    def test_android_and_ios_are_independent_required_jobs(self) -> None:
        self.assertIn("android_device_matrix:\n    name: Android device matrix", self.workflow)
        self.assertIn("ios_device_matrix:\n    name: iOS device matrix", self.workflow)
        self.assertEqual(
            self.workflow.count("needs: beta_stack\n    if: ${{ needs.beta_stack.result == 'success' }}"),
            2,
        )
        self.assertIn(
            "needs: [beta_stack, android_device_matrix, ios_device_matrix]",
            self.workflow,
        )
        self.assertIn(
            "always() && vars.ENABLE_SELF_HOSTED_MOBILE_MATRIX == 'true'",
            self.workflow,
        )
        self.assertIn(
            "name: Require successful dual-platform job aggregation",
            self.workflow,
        )
        self.assertIn('test "$AGGREGATE" = success', self.workflow)
        self.assertIn("--has-android true", self.workflow)
        self.assertIn("--has-ios true", self.workflow)
        self.assertEqual(
            self.workflow.count(
                "account_closure_disposable_ack: "
                "${{ inputs.account_closure_disposable_ack == true }}"
            ),
            2,
        )
        self.assertEqual(
            self.workflow.count(
                "account_closure_prod_platform: "
                "${{ inputs.account_closure_prod_platform || 'ios' }}"
            ),
            2,
        )

    def test_managed_runtime_teardown_is_always_run_and_gate_visible(self) -> None:
        self.assertIn(
            "always() && (needs.beta_stack.outputs.formal_runtime_started == 'true' "
            "|| needs.beta_stack.outputs.managed_runtime_started == 'true')",
            self.workflow,
        )
        self.assertIn(
            "timeout-minutes: ${{ needs.beta_stack.outputs.managed_runtime_started == 'true' && 10 || 1 }}",
            self.workflow,
        )
        self.assertIn("name: Inspect and doctor the managed Gamma runtime after soak", self.workflow)
        self.assertIn("name: Verify and teardown only the Gamma runtime started here", self.workflow)
        self.assertIn("--target gamma-local", self.workflow)
        self.assertIn("--workload full", self.workflow)
        self.assertIn(
            'if [ "$MANAGED_RUNTIME_STARTED" = true ]; then test "$TEARDOWN" = success; fi',
            self.workflow,
        )
        self.assertIn("canonical App device timing status", self.workflow)

    def test_pr_device_matrix_is_changed_path_filtered_with_typed_skip(self) -> None:
        self.assertIn("force_device_matrix:", self.workflow)
        self.assertIn("device_required: ${{ steps.plan.outputs.device }}", self.workflow)
        self.assertIn("Emit typed not-required result", self.workflow)
        self.assertIn("state=not_required impact_plan_digest=", self.workflow)
        self.assertIn("summary_result: ${{ steps.summary.outputs.result || steps.typed_skip.outputs.result }}", self.workflow)
        self.assertIn("github.event_name != 'pull_request' || needs.impact.outputs.device_required == 'true'", self.workflow)
        self.assertIn("VALIDATION_PROFILE: ${{ inputs.validation_profile || 'pr_light' }}", self.workflow)
        self.assertIn("PROMOTION_PR:", self.workflow)
        self.assertIn('"$VALIDATION_PROFILE" != pr_light', self.workflow)
        self.assertIn('"$PROMOTION_PR" == true', self.workflow)

    def test_device_impact_artifact_is_versioned_and_validated_once(self) -> None:
        self.assertIn('--impact-plan "$ROOT/impact-plan.json"', self.workflow)
        self.assertIn('--validate-impact-plan "$ROOT/impact-plan.json"', self.workflow)
        self.assertIn("--expected-plan-digest", self.workflow)
        self.assertIn("Upload typed device impact plan", self.workflow)


if __name__ == "__main__":
    unittest.main()
