from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import external_provider_governance
from quwoquan_ops.cli.lib import provider_conformance


def _provider_report(
    environment: str,
    *,
    ready: bool,
    issues: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema": "provider-conformance-readiness",
        "evidenceCount": 9,
        "executableSourceCount": 9,
        "sourceCoverageIssues": [],
        "issues": issues or [],
        "readiness": {
            environment: {
                "content.embedding.generation": {
                    "required": True,
                    "capability_ready": ready,
                }
            }
        },
    }


def _verify_args(environment: str, report_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        command="verify",
        env=environment,
        # Provider readiness is independent from the hosted backup receipt gate.
        # Use prod-sim here so this contract verifies only the provider preflight;
        # prod-hosted disaster-recovery evidence has its own acceptance coverage.
        target="prod-sim" if environment == "prod" else "",
        kind="all",
        profile="release",
        output_format="json",
        report_dir=str(report_dir),
    )


def _deploy_args(report_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        command="deploy",
        target="prod-hosted",
        mode="rollout",
        stage="canary",
        step="0",
        service="content-service",
        from_candidate_digest=f"sha256:{'1' * 64}",
        to_candidate_digest=f"sha256:{'2' * 64}",
        release_evidence_ref=f"ghcr.io/quwoquan/release-evidence@sha256:{'3' * 64}",
        cloud_provider="aliyun",
        dry_run="true",
        reuse_package=False,
        release_manifest="/tmp/release-manifest.json",
        prometheus_url="",
        promotion_deadline_epoch=0,
        hard_deadline_epoch=0,
        rollback_budget_seconds=300,
        report_dir=str(report_dir),
    )


class StackctlProviderReadinessContractTest(unittest.TestCase):
    def test_provider_config_test_live_compiles_current_workspace_identity(self) -> None:
        composition = {"schema": "stackctl-provider-runtime-composition"}
        compiler = mock.Mock(
            compile_provider_config=mock.Mock(
                return_value={"exitCode": 0, "summary": "passed"}
            )
        )
        args = argparse.Namespace(
            env="alpha",
            target="alpha-local",
            provider_config_action="validate",
            runtime_mode="test_live",
        )

        with (
            mock.patch.object(
                stackctl,
                "compile_provider_runtime_composition",
                return_value=composition,
            ) as compile_current,
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                side_effect=AssertionError("test_live must not read active candidate"),
            ),
            mock.patch.object(stackctl, "_provider_config", return_value=compiler),
        ):
            result = stackctl.command_provider_config(args)

        self.assertEqual(result["exitCode"], 0, result)
        compile_current.assert_called_once_with(
            environment="alpha",
            target="alpha-local",
        )
        compiler.compile_provider_config.assert_called_once_with(
            action="validate",
            environment="alpha",
            target="alpha-local",
            runtime_composition=composition,
        )

    def test_provider_config_test_live_rejects_prod(self) -> None:
        result = stackctl.command_provider_config(
            argparse.Namespace(
                env="prod",
                target="prod-hosted",
                provider_config_action="validate",
                runtime_mode="test_live",
            )
        )

        self.assertEqual(result["exitCode"], 2)
        self.assertIn("limited to local nonprod", " ".join(result["details"]))

    def test_sanitizer_accepts_only_canonical_positive_provider_evidence(self) -> None:
        canonical = _provider_report("prod", ready=True)
        report, passed = stackctl._sanitized_provider_readiness_report(
            "prod",
            child_exit_code=0,
            child_stdout=json.dumps(canonical),
        )
        self.assertTrue(passed)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["evidenceCount"], 9)

        historical = dict(canonical)
        historical["version"] = 1
        report, passed = stackctl._sanitized_provider_readiness_report(
            "prod",
            child_exit_code=0,
            child_stdout=json.dumps(historical),
        )
        self.assertFalse(passed)
        self.assertEqual(report["status"], "gate_block")

        empty = dict(canonical)
        empty["evidenceCount"] = 0
        report, passed = stackctl._sanitized_provider_readiness_report(
            "prod",
            child_exit_code=0,
            child_stdout=json.dumps(empty),
        )
        self.assertFalse(passed)
        self.assertEqual(report["status"], "gate_block")

    def test_provider_conformance_matrix_derives_all_cells_from_actual_bindings(self) -> None:
        args = argparse.Namespace(
            matrix=True,
            capability_id="assistant.model.generation",
            adapter_id="",
            env="",
            layer="",
            execute=True,
            image_digest=f"sha256:{'1' * 64}",
            data_digest="",
            adapter_health_receipt_ref="",
            switch_compatibility_receipt_ref="",
            callback_drain_receipt_ref="",
            last_good_receipt_ref="",
            rollback_receipt_ref="",
            prod_binding_preflight_receipt_ref="",
            prod_adapter_health_receipt_ref="",
        )
        runner = mock.Mock()
        runner.main.return_value = 0
        runtime_environments = {
            environment: {
                stackctl.PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV: (
                    f"explicit-{environment}-runtime-identity"
                )
            }
            for environment in provider_conformance.ENVIRONMENTS
        }
        with mock.patch.object(
            stackctl,
            "_provider_conformance_runner",
            return_value=runner,
        ), mock.patch.object(
            stackctl,
            "_provider_conformance_runtime_environment",
            side_effect=lambda environment: runtime_environments[environment],
        ) as select_runtime:
            result = stackctl.command_provider_conformance(args)

        self.assertEqual(result["exitCode"], 0)
        runner.main.assert_called_once_with(
            [
                "--matrix",
                "--capability-id",
                "assistant.model.generation",
                "--execute",
                "--image-digest",
                f"sha256:{'1' * 64}",
            ],
            runtime_environments=runtime_environments,
        )
        self.assertEqual(
            [call.args[0] for call in select_runtime.call_args_list],
            list(provider_conformance.ENVIRONMENTS),
        )

    def test_environment_matrix_executes_only_external_provider_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(
                matrix=False,
                environment_matrix=True,
                capability_id="",
                adapter_id="",
                env="gamma",
                layer="",
                execute=True,
                image_digest="",
                data_digest="",
                report_dir=str(Path(temporary) / "matrix"),
            )
            runner = mock.Mock()
            conformance = mock.Mock()
            conformance.discover_test_sources.return_value = ({}, [])
            compiled, governance_issues = external_provider_governance.load_and_compile()
            self.assertEqual(governance_issues, [])
            expected_cells = provider_conformance.expected_required_cell_keys(compiled)
            selected_gamma_bindings = compiled["selectedBindings"]["gamma"]
            provider_capability_ids = {
                capability_id
                for capability_id, binding in selected_gamma_bindings.items()
                if external_provider_governance.requires_provider_conformance(
                    binding
                )
            }
            expected_environment_cells = {
                cell
                for cell in expected_cells
                if cell[1] == "gamma" and cell[0] in provider_capability_ids
            }
            expected_count = len(expected_environment_cells)
            attempt_paths = [
                Path(temporary) / f"provider-evidence-{index}.json"
                for index in range(expected_count)
            ]
            execution_index = 0
            runtime_environment = {
                stackctl.PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV: (
                    "explicit-gamma-runtime-identity"
                )
            }

            def execute_cell(
                _argv: list[str],
                *,
                evidence_paths_out: list[Path],
                runtime_environments: dict[str, dict[str, str]],
            ) -> int:
                nonlocal execution_index
                self.assertEqual(
                    runtime_environments,
                    {"gamma": runtime_environment},
                )
                evidence_paths_out.append(attempt_paths[execution_index])
                execution_index += 1
                return 0

            runner.main.side_effect = execute_cell
            conformance.load_validate_local_functional_readiness.return_value = (
                [{} for _ in range(expected_count)],
                [],
            )
            conformance.expected_required_cell_keys.return_value = expected_cells
            runtime_use_lock = mock.Mock()
            with (
                mock.patch.object(
                    stackctl,
                    "acquire_local_runtime_use_lock",
                    return_value=runtime_use_lock,
                ) as acquire_runtime_use_lock,
                mock.patch.object(
                    stackctl,
                    "_provider_conformance_runner",
                    return_value=runner,
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_conformance",
                    return_value=conformance,
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_conformance_runtime_environment",
                    return_value=runtime_environment,
                ) as select_runtime,
            ):
                result = stackctl.command_provider_conformance(args)

        self.assertEqual(result["exitCode"], 0, result)
        acquire_runtime_use_lock.assert_called_once_with(
            target="gamma-local",
            purpose="provider-conformance-uat",
        )
        runtime_use_lock.close.assert_called_once_with()
        self.assertEqual(
            result["bindingCapabilityCount"], compiled["capabilityCount"]
        )
        self.assertEqual(
            result["capabilityCount"],
            len(provider_capability_ids),
        )
        self.assertEqual(result["expectedCells"], expected_count)
        self.assertEqual(result["executed"], expected_count)
        self.assertEqual(result["attemptEvidenceCount"], expected_count)
        select_runtime.assert_called_once_with("gamma")
        self.assertEqual(result["readinessScope"], "local_functional")
        self.assertFalse(result["releasePromotionClaimed"])
        self.assertEqual(
            runner.preflight_environment_matrix.call_args.kwargs[
                "runtime_environment"
            ],
            runtime_environment,
        )
        self.assertEqual(runner.main.call_count, expected_count)
        conformance.load_validate_local_functional_readiness.assert_called_once()
        local_validation = (
            conformance.load_validate_local_functional_readiness.call_args
        )
        self.assertEqual(set(local_validation.args[0]), set(attempt_paths))
        self.assertEqual(local_validation.kwargs["environment"], "gamma")
        conformance.evidence_files.assert_not_called()
        self.assertFalse(
            any(
                call.args[0][1] == "ext.first_party.http_authority"
                for call in runner.main.call_args_list
            )
        )

    def test_release_verify_invokes_provider_readiness_for_gamma_and_prod(self) -> None:
        for environment in ("gamma", "prod"):
            with self.subTest(environment=environment), tempfile.TemporaryDirectory() as temporary:
                report_dir = Path(temporary) / "report"
                invocations: list[list[str]] = []

                def run_provider(argv: list[str], **_kwargs: object) -> CompletedProcess[str]:
                    invocations.append(argv)
                    return CompletedProcess(
                        argv,
                        0,
                        json.dumps(_provider_report(environment, ready=True)),
                        "",
                    )

                with (
                    mock.patch.object(stackctl, "run", side_effect=run_provider),
                    mock.patch.object(
                        stackctl,
                        "can_reuse_package",
                        return_value=(True, "candidate ready"),
                    ),
                    mock.patch.object(stackctl, "_selected_verify_commands", return_value=[]),
                    mock.patch.object(
                        stackctl,
                        "command_content_readiness",
                        return_value={"exitCode": 0, "details": [], "reportDir": ""},
                    ),
                    mock.patch.object(
                        stackctl,
                        "_inspect_distribution_for_target",
                        return_value=({"status": "passed", "issues": []}, report_dir, True),
                    ),
                    mock.patch.object(stackctl, "_selected_profile_commands", return_value=[]),
                    mock.patch.object(
                        stackctl,
                        "_runtime_media_playback_evidence",
                        return_value={"status": "passed"},
                    ),
                    mock.patch.object(stackctl, "_write_summary_bundle"),
                ):
                    result = stackctl.command_verify(_verify_args(environment, report_dir))

                self.assertEqual(result["exitCode"], 0)
                self.assertEqual(
                    invocations,
                    [
                        [
                            "python3",
                            stackctl.PROVIDER_CONFORMANCE_SCRIPT,
                            "--require-ready",
                            environment,
                        ]
                    ],
                )
                report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
                sidecar = json.loads(
                    (report_dir / "provider-readiness.json").read_text(encoding="utf-8")
                )
                self.assertEqual(report["providerReadiness"], sidecar)
                self.assertEqual(sidecar["status"], "passed")
                self.assertEqual(
                    sidecar["requiredCapabilities"],
                    [{"capabilityId": "content.embedding.generation", "ready": True}],
                )

    def test_release_verify_fails_closed_with_redacted_provider_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary) / "report"
            provider_output = _provider_report(
                "gamma",
                ready=False,
                issues=[
                    "evidence artifact missing at https://secret.invalid/?token=top-secret",
                    "configDigest does not match the selected binding",
                    "adapter continuity is incomplete",
                ],
            )
            with (
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess(
                        [],
                        1,
                        json.dumps(provider_output),
                        "token=top-secret",
                    ),
                ),
                mock.patch.object(stackctl, "command_package") as command_package,
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_verify(_verify_args("gamma", report_dir))

            self.assertEqual(result["exitCode"], 2)
            command_package.assert_not_called()
            report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
            sidecar = json.loads(
                (report_dir / "provider-readiness.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "GATE_BLOCK")
            self.assertEqual(
                sidecar["failureCategories"],
                [
                    "adapter-continuity",
                    "configuration",
                    "evidence",
                    "provider-readiness",
                    "readiness",
                ],
            )
            self.assertNotIn("secret.invalid", json.dumps(report))
            self.assertNotIn("top-secret", json.dumps(report))

    def test_selected_typed_data_graph_runs_under_its_exact_provider_closure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary) / "report"
            args = _verify_args("gamma", report_dir)
            args.test_data_request = "selected-request.json"
            selected_result = {
                "schema": "qwq.case_result",
                "status": "passed",
                "executed": 1,
                "skipped": 0,
                "issues": [],
            }
            provider_preflight = {
                "kind": "provider-readiness",
                "report": {"status": "gate_block"},
                "argv": ["provider-readiness"],
                "exitCode": 2,
                "reportPath": "provider-readiness.json",
                "details": ["an unselected Provider is unavailable"],
            }
            with (
                mock.patch.object(
                    stackctl,
                    "_run_provider_readiness_preflight",
                    return_value=provider_preflight,
                ),
                mock.patch.object(
                    stackctl,
                    "_inspect_distribution_for_target",
                    return_value=({"issues": []}, Path(temporary), True),
                ),
                mock.patch.object(
                    stackctl,
                    "can_reuse_package",
                    return_value=(True, "candidate ready"),
                ),
                mock.patch.object(
                    stackctl,
                    "_run_static_verify_wave",
                    return_value=([], {"exitCode": 0, "details": []}, 7),
                ),
                mock.patch.object(
                    stackctl,
                    "_selected_profile_commands",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "_run_profile_commands_parallel",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "_current_runtime_workload",
                    return_value="full",
                ),
                mock.patch.object(
                    stackctl,
                    "_run_test_data_profile",
                    return_value=selected_result,
                ) as selected,
                mock.patch.object(
                    stackctl,
                    "_runtime_media_playback_evidence",
                    return_value={"status": "passed"},
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_verify(args)

            self.assertEqual(result["exitCode"], 2)
            self.assertTrue(
                selected.call_args.kwargs["prerequisites_passed"]
            )
            report = json.loads(
                (report_dir / "report.json").read_text(encoding="utf-8")
            )
            test_data_step = next(
                item for item in report["steps"] if item["kind"] == "test-data"
            )
            self.assertEqual(test_data_step["caseResult"]["status"], "passed")
            self.assertEqual(report["status"], "failed")

    def test_gray_initial_provider_preflight_precedes_fixed_package_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary) / "report"
            release_manifest = Path(temporary) / "release-manifest.json"
            invocations: list[list[str]] = []

            def run_preflight_then_package(
                argv: list[str],
                **_kwargs: object,
            ) -> CompletedProcess[str]:
                invocations.append(argv)
                if argv[1:3] == [
                    stackctl.PROVIDER_CONFORMANCE_SCRIPT,
                    "--require-ready",
                ]:
                    return CompletedProcess(
                        argv,
                        0,
                        json.dumps(_provider_report("prod", ready=True)),
                        "",
                    )
                if argv[:4] == [
                    "python3",
                    "quwoquan_ops/cli/stackctl.py",
                    "package",
                    "--env",
                ]:
                    return CompletedProcess(argv, 1, "", "package unavailable")
                raise AssertionError(f"unexpected subprocess: {argv}")

            with (
                mock.patch.object(
                    stackctl,
                    "require_prod_hosted_release_redundancy",
                ),
                mock.patch.object(stackctl, "run", side_effect=run_preflight_then_package),
                mock.patch.object(
                    stackctl,
                    "_deployable_release_manifest",
                    return_value=(
                        release_manifest,
                        f"sha256:{'4' * 64}",
                        {
                            "images": {
                                "content-service": {
                                    "repository": "ghcr.io/quwoquan/content-service",
                                    "transportRef": "ghcr.io/quwoquan/content-service:release-test",
                                }
                            }
                        },
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_fetch_hosted_release_ledger_projection",
                    return_value=(
                        {
                            "to_candidate_digest": f"sha256:{'1' * 64}",
                            "to_release_evidence_ref": (
                                f"ghcr.io/quwoquan/release-evidence@sha256:{'5' * 64}"
                            ),
                            "to_image_transport_tag": "release-before",
                            "last_good_candidate_digest": f"sha256:{'1' * 64}",
                        },
                        None,
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_validate_release_transition",
                    return_value=("advance", 0),
                ),
                mock.patch.object(
                    stackctl,
                    "_materialize_release_evidence_configuration",
                    side_effect=ValueError("fixed prod package unavailable"),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_deploy(_deploy_args(report_dir))

            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(
                invocations[0],
                [
                    "python3",
                    stackctl.PROVIDER_CONFORMANCE_SCRIPT,
                    "--require-ready",
                    "prod",
                ],
            )
            self.assertEqual(len(invocations), 1)
            self.assertIn("fixed prod package unavailable", result["details"][0])

    def test_gray_initial_dry_run_cannot_bypass_failed_provider_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary) / "report"
            with (
                mock.patch.object(
                    stackctl,
                    "require_prod_hosted_release_redundancy",
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess(
                        [],
                        1,
                        json.dumps(
                            _provider_report(
                                "prod",
                                ready=False,
                                issues=["required adapter lacks current evidence"],
                            )
                        ),
                        "",
                    ),
                ) as run,
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_deploy(_deploy_args(report_dir))

            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(run.call_count, 1)
            report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "GATE_BLOCK")
            self.assertEqual(report["providerReadiness"]["status"], "gate_block")


if __name__ == "__main__":
    unittest.main()
