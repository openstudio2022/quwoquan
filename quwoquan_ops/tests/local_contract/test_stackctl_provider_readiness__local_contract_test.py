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
        "version": 1,
        "evidenceCount": 9,
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
        target="",
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
        from_image="sha256:before",
        to_image="sha256:after",
        from_config="config-before",
        to_config="config-after",
        cloud_provider="aliyun",
        dry_run="true",
        release_manifest="/tmp/release-manifest.json",
        prometheus_url="",
        report_dir=str(report_dir),
    )


class StackctlProviderReadinessContractTest(unittest.TestCase):
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
                        "command_package",
                        return_value={"exitCode": 0, "details": [], "reportDir": ""},
                    ),
                    mock.patch.object(stackctl, "_selected_verify_commands", return_value=[]),
                    mock.patch.object(
                        stackctl,
                        "command_content_readiness",
                        return_value={"exitCode": 0, "details": [], "reportDir": ""},
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

    def test_gray_initial_provider_preflight_precedes_package_even_for_dry_run(self) -> None:
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
                    return_value=(release_manifest, "sha256:manifest", {}),
                ),
                mock.patch.object(stackctl, "_load_release_state", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_validate_release_transition",
                    return_value=("advance", 0),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_deploy(_deploy_args(report_dir))

            self.assertEqual(result["exitCode"], 1)
            self.assertEqual(
                invocations[0],
                [
                    "python3",
                    stackctl.PROVIDER_CONFORMANCE_SCRIPT,
                    "--require-ready",
                    "prod",
                ],
            )
            self.assertEqual(invocations[1][:3], ["python3", "quwoquan_ops/cli/stackctl.py", "package"])

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
