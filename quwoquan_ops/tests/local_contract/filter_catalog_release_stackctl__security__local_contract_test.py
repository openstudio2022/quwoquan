from __future__ import annotations

import argparse
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import filter_catalog_release
from quwoquan_ops.cli.lib.local_environment_auth import LocalAcceptanceSession


ROOT = Path(__file__).resolve().parents[3]


class FilterCatalogReleaseStackctlSecurityLocalContractTest(unittest.TestCase):
    def test_local_mutation_uses_ephemeral_service_profile_and_never_puts_token_in_argv(self) -> None:
        session = LocalAcceptanceSession(
            owner_id="filter-catalog-gamma-publisher",
            persona_id="filter-catalog-gamma-publisher",
            access_token="gamma-local-service-bearer",
        )
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"releaseId":"filter-catalog-20260720-001"}',
            stderr="",
        )
        with (
            mock.patch.object(
                filter_catalog_release,
                "open_local_acceptance_session",
                return_value=session,
            ) as open_session,
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
                api_base_url="https://gamma-api.quwoquan-env.test:19000",
                action="stage-and-activate",
                rollback_release_id="",
                token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                prod_gray_activation=False,
            )

        open_session.assert_called_once_with(
            "https://gamma-api.quwoquan-env.test:19000",
            environment="gamma",
            target_name="gamma-local",
            subject="filter-catalog-gamma-publisher",
            profile="content-filter-catalog-publisher",
        )
        self.assertEqual(execution.return_code, 0)
        self.assertNotIn("gamma-local-service-bearer", execution.argv)
        self.assertIn("--insecure-local-tls", execution.argv)
        self.assertNotIn("--prod-gray-activation", execution.argv)
        process_env = run.call_args.kwargs["env"]
        self.assertEqual(
            process_env["QWQ_FILTER_CATALOG_PUBLISH_TOKEN"],
            "gamma-local-service-bearer",
        )

    def test_prod_mutation_requires_pre_provisioned_service_token(self) -> None:
        with mock.patch.dict(filter_catalog_release.os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "requires QWQ_FILTER_CATALOG_PUBLISH_TOKEN"):
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
        with (
            mock.patch.object(
                filter_catalog_release,
                "open_local_acceptance_session",
            ) as open_session,
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
                api_base_url="https://beta-api.quwoquan-env.test:18000",
                action="verify",
                rollback_release_id="",
                token_env="QWQ_FILTER_CATALOG_PUBLISH_TOKEN",
                prod_gray_activation=False,
            )

        open_session.assert_not_called()
        self.assertEqual(execution.return_code, 0)
        self.assertIn("--insecure-local-tls", execution.argv)

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

    def test_environment_profiles_bind_public_active_catalog_verification(self) -> None:
        with mock.patch.object(stackctl, "_local_target_runtime_ready", return_value=True):
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
