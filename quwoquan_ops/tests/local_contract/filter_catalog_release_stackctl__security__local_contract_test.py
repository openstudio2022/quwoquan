# spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-004

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import filter_catalog_release
ROOT = Path(__file__).resolve().parents[3]


class FilterCatalogReleaseStackctlSecurityLocalContractTest(unittest.TestCase):
    def test_alpha_mutation_uses_the_same_protected_local_publish_plane(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"passed":true}',
            stderr="",
        )
        with (
            mock.patch.dict(
                filter_catalog_release.os.environ,
                {"QWQ_FILTER_CATALOG_PUBLISH_TOKEN": "alpha-local-service-bearer"},
            ),
            mock.patch.object(
                filter_catalog_release.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            execution = filter_catalog_release.execute_filter_catalog_command(
                repo_root=ROOT,
                target_name="alpha-local",
                environment="alpha",
                api_base_url="https://api.alpha.quwoquan.com:17000",
                action="stage-and-activate",
                rollback_release_id="",
                token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                prod_gray_activation=False,
            )

        self.assertEqual(execution.return_code, 0)
        self.assertIn("alpha", execution.argv)
        self.assertNotIn("alpha-local-service-bearer", execution.argv)
        self.assertEqual(
            run.call_args.kwargs["env"]["QWQ_FILTER_CATALOG_PUBLISH_TOKEN"],
            "alpha-local-service-bearer",
        )

    def test_local_publish_injects_managed_ca_without_disabling_tls(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"passed":true}',
            stderr="",
        )
        with tempfile.TemporaryDirectory() as temporary:
            ca_file = Path(temporary) / "root.crt"
            ca_file.write_text("managed-ca", encoding="utf-8")
            with (
                mock.patch.dict(
                    filter_catalog_release.os.environ,
                    {"QWQ_FILTER_CATALOG_PUBLISH_TOKEN": "local-service-bearer"},
                ),
                mock.patch.object(
                    filter_catalog_release.subprocess,
                    "run",
                    return_value=completed,
                ) as run,
            ):
                execution = filter_catalog_release.execute_filter_catalog_command(
                    repo_root=ROOT,
                    target_name="alpha-local",
                    environment="alpha",
                    api_base_url="https://api.alpha.quwoquan.com:17000",
                    action="stage",
                    rollback_release_id="",
                    token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                    prod_gray_activation=False,
                    ssl_cafile=str(ca_file),
                )

        self.assertEqual(execution.return_code, 0)
        self.assertEqual(run.call_args.kwargs["env"]["SSL_CERT_FILE"], str(ca_file))
        self.assertNotIn("--insecure-local-tls", execution.argv)

    def test_local_mutation_uses_protected_service_token_and_never_puts_it_in_argv(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"releaseId":"filter-catalog-20260720-001"}',
            stderr="",
        )
        with (
            mock.patch.dict(
                filter_catalog_release.os.environ,
                {"QWQ_FILTER_CATALOG_PUBLISH_TOKEN": "gamma-local-service-bearer"},
            ),
            mock.patch.object(
                filter_catalog_release.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            execution = filter_catalog_release.execute_filter_catalog_command(
                repo_root=ROOT,
                target_name="gamma-local",
                environment="gamma",
                api_base_url="https://api.gamma.quwoquan.com:19000",
                action="stage-and-activate",
                rollback_release_id="",
                token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                prod_gray_activation=False,
            )

        self.assertEqual(execution.return_code, 0)
        self.assertNotIn("gamma-local-service-bearer", execution.argv)
        self.assertNotIn("--insecure-local-tls", execution.argv)
        self.assertNotIn("--prod-gray-activation", execution.argv)
        process_env = run.call_args.kwargs["env"]
        self.assertEqual(
            process_env["QWQ_FILTER_CATALOG_PUBLISH_TOKEN"],
            "gamma-local-service-bearer",
        )

    def test_failed_local_publish_writes_private_redacted_diagnostic(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="publish failed beta-local-secret-bearer\n",
            stderr="CONTENT.USER.filter_catalog_invalid_transition\n",
        )
        with tempfile.TemporaryDirectory() as temporary:
            diagnostic_path = Path(temporary) / "stdout" / "filter-catalog.log"
            with (
                mock.patch.dict(
                    filter_catalog_release.os.environ,
                    {"QWQ_FILTER_CATALOG_PUBLISH_TOKEN": "beta-local-secret-bearer"},
                ),
                mock.patch.object(
                    filter_catalog_release.subprocess,
                    "run",
                    return_value=completed,
                ),
            ):
                execution = filter_catalog_release.execute_filter_catalog_command(
                    repo_root=ROOT,
                    target_name="beta-local",
                    environment="beta",
                    api_base_url="https://api.beta.quwoquan.com:18000",
                    action="stage-and-activate",
                    rollback_release_id="",
                    token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                    prod_gray_activation=False,
                    diagnostic_log_path=diagnostic_path,
                )

            self.assertEqual(execution.return_code, 1)
            diagnostic = diagnostic_path.read_text(encoding="utf-8")
            self.assertNotIn("beta-local-secret-bearer", diagnostic)
            self.assertIn("***", diagnostic)
            self.assertIn(
                "CONTENT.USER.filter_catalog_invalid_transition",
                diagnostic,
            )
            self.assertEqual(diagnostic_path.stat().st_mode & 0o777, 0o600)

    def test_prod_mutation_requires_pre_provisioned_service_token(self) -> None:
        with mock.patch.dict(filter_catalog_release.os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "publisher token"):
                filter_catalog_release.execute_filter_catalog_command(
                    repo_root=ROOT,
                    target_name="prod-hosted",
                    environment="prod",
                    api_base_url="https://api.quwoquan.com",
                    action="stage",
                    rollback_release_id="",
                    token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                    prod_gray_activation=False,
                )

    def test_public_verify_neither_issues_nor_requires_a_bearer(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"active":{"releaseId":"filter-catalog-20260720-001"}}',
            stderr="",
        )
        with mock.patch.object(
                filter_catalog_release.subprocess,
                "run",
                return_value=completed,
            ):
            execution = filter_catalog_release.execute_filter_catalog_command(
                repo_root=ROOT,
                target_name="beta-local",
                environment="beta",
                api_base_url="https://api.beta.quwoquan.com:18000",
                action="verify",
                rollback_release_id="",
                token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                prod_gray_activation=False,
            )

        self.assertEqual(execution.return_code, 0)
        self.assertNotIn("--insecure-local-tls", execution.argv)

    def test_stackctl_records_only_sanitized_passed_publish_receipt(self) -> None:
        execution = filter_catalog_release.FilterCatalogCommandExecution(
            argv=(
                "python3",
                "quwoquan_data/scripts/cli.py",
                "filter-catalog",
                "publish",
            ),
            return_code=0,
            stdout=json.dumps(
                {
                    "schema": "quwoquan_data.filter_catalog_publish_receipt",
                    "passed": True,
                    "releaseId": "filter-catalog-20260720-001",
                    "canonicalDigest": "a" * 64,
                }
            ),
            stderr="",
        )
        with (
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path("/tmp/filter-catalog-stackctl"),
            ),
            mock.patch.object(
                stackctl,
                "execute_filter_catalog_command",
                return_value=execution,
            ) as execute,
            mock.patch.object(stackctl, "_write_filter_catalog_command_report") as write_report,
        ):
            result = stackctl.command_filter_catalog(
                argparse.Namespace(
                    target="gamma-local",
                    action="verify",
                    rollback_release_id="",
                    token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                    prod_gray_activation=False,
                )
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertNotIn("local-service-bearer", json.dumps(result))
        execute.assert_called_once()
        report_kwargs = write_report.call_args.kwargs
        self.assertEqual(
            report_kwargs["publish_receipt"]["releaseId"],
            "filter-catalog-20260720-001",
        )
        self.assertEqual(
            report_kwargs["argv"],
            (
                "python3",
                "quwoquan_data/scripts/cli.py",
                "filter-catalog",
                "publish",
            ),
        )

    def test_stackctl_mints_local_service_token_only_for_mutating_child_env(self) -> None:
        execution = filter_catalog_release.FilterCatalogCommandExecution(
            argv=("python3", "quwoquan_data/scripts/cli.py", "filter-catalog"),
            return_code=0,
            stdout=json.dumps(
                {
                    "passed": True,
                    "releaseId": "filter-catalog-20260720-001",
                    "canonicalDigest": "a" * 64,
                }
            ),
            stderr="",
        )
        with (
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path("/tmp/filter-catalog-stackctl"),
            ),
            mock.patch.object(
                stackctl,
                "mint_local_filter_catalog_service_token",
                return_value="ephemeral-local-service-token",
            ) as mint,
            mock.patch.object(
                stackctl,
                "execute_filter_catalog_command",
                return_value=execution,
            ) as execute,
            mock.patch.object(stackctl, "_write_filter_catalog_command_report"),
        ):
            result = stackctl.command_filter_catalog(
                argparse.Namespace(
                    target="alpha-local",
                    action="stage-and-activate",
                    rollback_release_id="",
                    token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                    prod_gray_activation=False,
                )
            )

        self.assertEqual(result["exitCode"], 0)
        mint.assert_called_once_with("alpha", "alpha-local")
        self.assertEqual(
            execute.call_args.kwargs["token_value"],
            "ephemeral-local-service-token",
        )
        self.assertNotIn("ephemeral-local-service-token", json.dumps(result))

    def test_environment_profiles_bind_public_active_catalog_verification(self) -> None:
        commands = stackctl._selected_profile_commands(
            "gamma",
            "gamma-local",
            stackctl.VerificationProfile.INTEGRATION,
        )

        catalog_command = next(
            command
            for command in commands
            if command["name"] == "filter-catalog-active-release"
        )
        self.assertEqual(
            catalog_command["argv"][-4:],
            ["--target", "gamma-local", "--action", "verify"],
        )
        self.assertNotIn("--base-url", catalog_command["argv"])


if __name__ == "__main__":
    unittest.main()
