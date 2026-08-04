from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl


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
        stage="gray-initial",
        step="5",
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
        with mock.patch.object(
            stackctl,
            "_provider_conformance_runner",
            return_value=runner,
        ):
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
            ]
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
            runner.main.return_value = 0
            conformance = mock.Mock()
            conformance.discover_test_sources.return_value = ({}, [])
            conformance.load_validate_and_derive.return_value = ({}, [])
            conformance.readiness_issues.return_value = []
            with (
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
            ):
                result = stackctl.command_provider_conformance(args)

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["bindingCapabilityCount"], 17)
        self.assertEqual(result["capabilityCount"], 14)
        self.assertEqual(result["expectedCells"], 42)
        self.assertEqual(result["executed"], 42)
        runner.preflight_environment_matrix.assert_called_once()
        self.assertEqual(runner.main.call_count, 42)
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
                        "_runtime_media_t4_evidence",
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
