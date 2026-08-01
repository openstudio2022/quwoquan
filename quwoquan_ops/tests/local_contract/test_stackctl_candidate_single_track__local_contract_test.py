"""stackctl candidate and verify stay on one canonical environment contract.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import deployment_candidate_manifest, output_paths


class StackctlCandidateSingleTrackTest(unittest.TestCase):
    def test_internal_candidate_schemas_are_canonical_and_unversioned(self) -> None:
        self.assertEqual(
            deployment_candidate_manifest.CANDIDATE_MANIFEST_SCHEMA,
            "stackctl-deployment-candidate",
        )
        self.assertEqual(
            output_paths.ACTIVE_CANDIDATE_SCHEMA,
            "stackctl-active-deployment-candidate",
        )
        self.assertEqual(
            stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
            "stackctl-package-oci-images",
        )

    def test_reused_candidate_returns_original_report_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_id = f"sha256:{'a' * 64}"
            candidate_dir = root / "candidate"
            fingerprint_path = (
                candidate_dir / "packages/app/package-fingerprint.json"
            )
            fingerprint_path.parent.mkdir(parents=True)
            fingerprint_path.write_text(
                json.dumps({"reportRef": "env/alpha/runs/original-package"})
                + "\n",
                encoding="utf-8",
            )
            snapshot = {"baselineId": baseline_id}
            release_bindings = {
                "candidate": {"releaseId": "candidate"},
                "rollback": {"releaseId": "rollback"},
            }

            with (
                mock.patch.object(
                    stackctl,
                    "workspace_snapshot",
                    return_value=snapshot,
                ),
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "can_reuse_package",
                    return_value=(True, "reuse ok"),
                ) as reuse_package,
                mock.patch.object(
                    stackctl,
                    "validate_release_attestations",
                    return_value=release_bindings,
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value={"release": release_bindings},
                ),
                mock.patch.object(
                    stackctl,
                    "activate_deployment_candidate",
                    return_value=root / "active-candidate.json",
                ),
                mock.patch.object(
                    stackctl,
                    "_target_package_lock",
                    side_effect=lambda _target: contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_command_package_unlocked",
                    side_effect=AssertionError(
                        "a reusable candidate must not be rebuilt"
                    ),
                ),
            ):
                result = stackctl.command_package(
                    argparse.Namespace(
                        env="alpha",
                        target="alpha-local",
                        kind="runtime",
                        include_services=False,
                        service="",
                        release_attestation="candidate.json",
                        rollback_release_attestation="rollback.json",
                    )
                )

            self.assertEqual(result["exitCode"], 0)
            self.assertEqual(
                result["reportDir"],
                "env/alpha/runs/original-package",
            )
            self.assertEqual(result["baselineId"], baseline_id)
            self.assertTrue(reuse_package.call_args.kwargs["include_services"])

    def test_verify_children_override_inherited_cross_environment_target(self) -> None:
        invocations: list[tuple[list[str], dict[str, str]]] = []

        def run_child(
            argv: list[str],
            *,
            cwd: Path | None = None,
            env: dict[str, str] | None = None,
            **_kwargs: object,
        ) -> CompletedProcess[str]:
            del cwd
            invocations.append((argv, dict(env or {})))
            return CompletedProcess(argv, 0, "", "")

        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            os.environ,
            {"QWQ_DEPLOY_TARGET": "gamma-local"},
            clear=False,
        ), mock.patch.object(
            stackctl,
            "run",
            side_effect=run_child,
        ), mock.patch.object(
            stackctl,
            "can_reuse_package",
            return_value=(True, "candidate ready"),
        ), mock.patch.object(
            stackctl,
            "_selected_verify_commands",
            return_value=[["static-gate"]],
        ), mock.patch.object(
            stackctl,
            "_selected_profile_commands",
            return_value=[
                {
                    "name": "profile-gate",
                    "argv": ["profile-gate"],
                    "env": {
                        "QWQ_DEPLOY_TARGET": "gamma-local",
                        "PROFILE_SENTINEL": "preserved",
                    },
                }
            ],
        ):
            result = stackctl.command_verify(
                argparse.Namespace(
                    command="verify",
                    service="",
                    kind="topology",
                    profile="smoke",
                    env="alpha",
                    target="",
                    report_dir=str(Path(temporary) / "verify"),
                )
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            [argv for argv, _env in invocations],
            [["static-gate"], ["profile-gate"]],
        )
        self.assertTrue(
            all(
                env["QWQ_DEPLOY_TARGET"] == "alpha-local"
                for _argv, env in invocations
            )
        )
        self.assertTrue(
            all(
                env["QWQ_APP_RUNTIME_ENV"] == "alpha"
                for _argv, env in invocations
            )
        )
        self.assertEqual(invocations[1][1]["PROFILE_SENTINEL"], "preserved")

    def test_provider_readiness_clears_inherited_target(self) -> None:
        completed = CompletedProcess(["provider-readiness"], 0, "{}", "")
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            os.environ,
            {"QWQ_DEPLOY_TARGET": "gamma-local"},
            clear=False,
        ), mock.patch.object(
            stackctl,
            "run",
            return_value=completed,
        ) as run, mock.patch.object(
            stackctl,
            "_sanitized_provider_readiness_report",
            return_value=({"failureCategories": []}, True),
        ):
            result = stackctl._run_provider_readiness_preflight(
                "prod",
                Path(temporary),
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            run.call_args.kwargs["env"],
            {"QWQ_DEPLOY_TARGET": "", "QWQ_APP_RUNTIME_ENV": ""},
        )


if __name__ == "__main__":
    unittest.main()
