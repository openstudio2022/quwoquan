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
    def _activate_service_candidate(
        self,
        *,
        target: str = "alpha-local",
        environment: str = "alpha",
        service: str = "content-service",
    ) -> Path:
        baseline_id = f"sha256:{'b' * 64}"
        candidate_dir = output_paths.deployment_candidate_dir(target, baseline_id)
        package_dir = candidate_dir / "packages" / "services" / service
        (package_dir / "config").mkdir(parents=True)
        (package_dir / "manifests").mkdir(parents=True)
        (package_dir / "image.lock").write_text(
            "example.invalid/content@sha256:" + ("c" * 64) + "\n",
            encoding="utf-8",
        )
        (package_dir / "config/config.yaml").write_text(
            "environment: alpha\n",
            encoding="utf-8",
        )
        (package_dir / "manifests/all.yaml").write_text(
            "---\nkind: List\nitems: []\n",
            encoding="utf-8",
        )
        (package_dir / "provenance.json").write_text(
            json.dumps(
                {
                    "schema": "qwq.service_package",
                    "service": service,
                    "environment": environment,
                    "configVersion": f"sha256:{'e' * 64}",
                    "digests": {"sourceTree": f"sha256:{'d' * 64}"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (candidate_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "candidateType": "runtime-full",
                    "target": target,
                    "baselineId": baseline_id,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        # This suite exercises service verification against an already active
        # candidate, not the full candidate compiler.  Keep activation on the
        # canonical validation seam without recreating a partial manifest as a
        # runnable candidate fixture.
        full_candidate_loader = mock.patch.object(
            output_paths,
            "_load_full_deployment_candidate",
            return_value={
                "candidateType": "runtime-full",
                "target": target,
                "baselineId": baseline_id,
            },
        )
        full_candidate_loader.start()
        self.addCleanup(full_candidate_loader.stop)
        output_paths.activate_deployment_candidate(target, baseline_id)
        return package_dir

    @staticmethod
    def _service_verify_args(report_dir: Path) -> argparse.Namespace:
        return argparse.Namespace(
            command="verify",
            service="content-service",
            env="alpha",
            target="alpha-local",
            profile="baseline",
            report_dir=str(report_dir),
        )

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
            report_dir = root / "package-report"
            report_dir.mkdir()
            report_path = report_dir / "report.json"
            identity = {
                "releaseInputClassification": "commercial_inputs",
                "contractGraphDigest": f"sha256:{'f' * 64}",
                "graphqlReadRegistry": {
                    "schema": "stackctl-graphql-read-registry-package",
                    "candidateDigest": baseline_id,
                },
            }
            report_path.write_text(json.dumps(identity) + "\n", encoding="utf-8")
            (candidate_dir / "manifest.json").write_text(
                json.dumps(identity) + "\n",
                encoding="utf-8",
            )
            fingerprint_path.write_text(
                json.dumps(
                    {
                        "reportRef": str(report_dir),
                        **identity,
                    }
                )
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
                    "deployment_input_roots",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "materialize_package_input_capsule",
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
                    return_value={
                        "release": release_bindings,
                        "releaseInputClassification": "commercial_inputs",
                        "contractGraphDigest": f"sha256:{'f' * 64}",
                        "packageDigest": f"sha256:{'1' * 64}",
                        "buildInputDigest": f"sha256:{'2' * 64}",
                        "imageDigest": f"sha256:{'3' * 64}",
                        "runtimeConfigDigest": f"sha256:{'4' * 64}",
                        "environmentRuntimeDigest": f"sha256:{'5' * 64}",
                        "runtimeSchemaVersion": "environment-runtime-package",
                        "observabilityLogSink": {
                            "adapterId": "ext.obs.elasticsearch",
                            "deploymentMode": "package-bound-local",
                            "imageDigest": f"sha256:{'6' * 64}",
                            "bindingDigest": f"sha256:{'7' * 64}",
                            "deploymentDigest": f"sha256:{'8' * 64}",
                            "clusterRef": "target:alpha-local/product-ops/elasticsearch",
                        },
                        "providerRuntime": {
                            "composition": {
                                "runtimeCompositionDigest": f"sha256:{'9' * 64}"
                            },
                            "images": {},
                        },
                    },
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
                str(report_dir),
            )
            self.assertEqual(result["baselineId"], baseline_id)
            self.assertEqual(
                result["releaseInputClassification"],
                "commercial_inputs",
            )
            self.assertEqual(
                result["contractGraphDigest"],
                f"sha256:{'f' * 64}",
            )
            self.assertTrue(reuse_package.call_args.kwargs["include_services"])

    def test_new_candidate_readback_failure_blocks_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_dir = root / "candidate"
            report_dir = root / "report"
            baseline_id = f"sha256:{'a' * 64}"
            release_bindings = {
                "candidate": {"releaseId": "candidate"},
                "rollback": {"releaseId": "rollback"},
            }
            manifest = {
                "release": release_bindings,
                "releaseInputClassification": "commercial_inputs",
                "contractGraphDigest": f"sha256:{'f' * 64}",
                "graphqlReadRegistry": {
                    "schema": "stackctl-graphql-read-registry-package",
                    "candidateDigest": baseline_id,
                },
                "packageDigest": f"sha256:{'1' * 64}",
                "buildInputDigest": f"sha256:{'2' * 64}",
                "imageDigest": f"sha256:{'3' * 64}",
                "runtimeConfigDigest": f"sha256:{'4' * 64}",
                "environmentRuntimeDigest": f"sha256:{'5' * 64}",
                "runtimeSchemaVersion": "environment-runtime-package",
                "observabilityLogSink": {},
                "providerRuntime": {},
            }

            def materialize(
                _args: argparse.Namespace,
                *,
                package_snapshot: dict[str, object] | None,
                **_kwargs: object,
            ) -> dict[str, object]:
                self.assertIsNotNone(package_snapshot)
                return {
                    "exitCode": 0,
                    "reportDir": str(report_dir),
                }

            use_lock = mock.Mock()
            use_lock.close = mock.Mock()
            with (
                mock.patch.object(
                    stackctl,
                    "deployment_input_roots",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "materialize_package_input_capsule",
                    return_value={"baselineId": baseline_id},
                ),
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "validate_release_attestations",
                    return_value=release_bindings,
                ),
                mock.patch.object(
                    stackctl,
                    "acquire_local_runtime_use_lock",
                    return_value=use_lock,
                ),
                mock.patch.object(
                    stackctl,
                    "_target_package_lock",
                    side_effect=lambda _target: contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_command_package_unlocked",
                    side_effect=materialize,
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_graphql_read_signing_material",
                    return_value=object(),
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value=manifest,
                ),
                mock.patch.object(
                    stackctl,
                    "_validate_runtime_package_identity_readback",
                    side_effect=ValueError("runtime package ContractGraph drifted"),
                    create=True,
                ),
                mock.patch.object(
                    stackctl,
                    "activate_deployment_candidate",
                ) as activate,
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

            self.assertEqual(result["exitCode"], 2, result)
            self.assertIn("ContractGraph drifted", "\n".join(result["details"]))
            activate.assert_not_called()

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
        self.assertTrue(
            all(
                env[stackctl.PACKAGE_ROOT_OVERRIDE_ENV] == ""
                and env[stackctl.RUNTIME_CANDIDATE_ROOT_ENV] == ""
                for _argv, env in invocations
            )
        )

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
            {
                "QWQ_DEPLOY_PACKAGE_ROOT_OVERRIDE": "",
                "QWQ_RUNTIME_CANDIDATE_ROOT": "",
                "QWQ_DEPLOY_TARGET": "",
                "QWQ_APP_RUNTIME_ENV": "",
            },
        )

    def test_service_verify_reads_active_candidate_without_rebuilding_or_mutating(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            os.environ,
            {"QWQ_DEPLOY_WORK_ROOT": str(Path(temporary) / "deploy")},
            clear=False,
        ):
            package_dir = self._activate_service_candidate()
            before = stackctl._sha256_tree(package_dir)
            with (
                mock.patch.object(
                    stackctl,
                    "run",
                    side_effect=AssertionError(
                        "verify --service must not build or mutate a candidate"
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_selected_profile_commands",
                    return_value=[],
                ),
            ):
                result = stackctl._command_verify_service_environment(
                    self._service_verify_args(Path(temporary) / "report")
                )

            after = stackctl._sha256_tree(package_dir)
            report = json.loads(
                (Path(temporary) / "report/report.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(after, before)
        self.assertEqual(report["steps"][0]["kind"], "candidate-package")
        self.assertEqual(report["steps"][0]["mode"], "read-only")
        self.assertEqual(report["steps"][0]["contentDigestBefore"], before)
        self.assertEqual(report["steps"][0]["contentDigestAfter"], before)
        self.assertTrue(report["steps"][0]["unchanged"])

    def test_service_verify_blocks_without_an_active_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            os.environ,
            {"QWQ_DEPLOY_WORK_ROOT": str(Path(temporary) / "deploy")},
            clear=False,
        ), mock.patch.object(
            stackctl,
            "run",
            side_effect=AssertionError("verify must not create a package"),
        ), mock.patch.object(
            stackctl,
            "_selected_profile_commands",
            return_value=[],
        ):
            result = stackctl._command_verify_service_environment(
                self._service_verify_args(Path(temporary) / "report")
            )

        self.assertEqual(result["exitCode"], 1)
        self.assertIn("active immutable candidate is required", result["details"][0])

    def test_service_verify_detects_profile_mutation_of_the_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            os.environ,
            {"QWQ_DEPLOY_WORK_ROOT": str(Path(temporary) / "deploy")},
            clear=False,
        ):
            package_dir = self._activate_service_candidate()

            def mutate_candidate(
                argv: list[str],
                **_kwargs: object,
            ) -> CompletedProcess[str]:
                (package_dir / "config/config.yaml").write_text(
                    "environment: mutated\n",
                    encoding="utf-8",
                )
                return CompletedProcess(argv, 0, "", "")

            with (
                mock.patch.object(
                    stackctl,
                    "run",
                    side_effect=mutate_candidate,
                ),
                mock.patch.object(
                    stackctl,
                    "_selected_profile_commands",
                    return_value=[
                        {
                            "name": "mutation-probe",
                            "argv": ["mutation-probe"],
                        }
                    ],
                ),
            ):
                result = stackctl._command_verify_service_environment(
                    self._service_verify_args(Path(temporary) / "report")
                )

        self.assertEqual(result["exitCode"], 1)
        self.assertIn(
            "active immutable service package changed during verification",
            result["details"],
        )


if __name__ == "__main__":
    unittest.main()
