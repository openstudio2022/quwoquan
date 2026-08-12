"""Provider conformance runtime selector contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.cli import stackctl


_BASELINE_A = "sha256:" + "1" * 64
_BASELINE_B = "sha256:" + "2" * 64
_PROVIDER_DIGEST = "sha256:" + "3" * 64


def _composition() -> dict[str, object]:
    return {
        "runtimeCompositionDigest": _PROVIDER_DIGEST,
        "bindings": [],
        "workloads": [],
    }


def _mutable_receipt(*, status: str = "running") -> dict[str, object]:
    return {
        "status": status,
        "environment": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "attemptId": "attempt-test-live-alpha",
        "providerRuntimeDigest": _PROVIDER_DIGEST,
        "composeDigest": "sha256:" + "4" * 64,
        "configurationDigest": "sha256:" + "5" * 64,
        "mutableStateDigest": "sha256:" + "6" * 64,
        "workspaceStatusDigest": "sha256:" + "7" * 64,
        "resolverHandoffDigest": "sha256:" + "8" * 64,
        "sourceRevision": "a" * 40,
        "failure": None,
        "cleanupFailure": None,
    }


def _immutable_receipt(*, candidate: str = _BASELINE_A) -> dict[str, object]:
    return {
        "status": "running",
        "env": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "attemptId": "attempt-immutable-alpha",
        "candidateDigest": candidate,
        "providerRuntimeDigest": _PROVIDER_DIGEST,
        "failure": None,
        "cleanupFailure": None,
    }


class StackctlProviderConformanceRuntimeSelectorTest(unittest.TestCase):
    def _patch_common(self) -> tuple[mock.Mock, mock.Mock]:
        auth = mock.Mock(environment={"QWQ_LOCAL_AUTH": "ready"})

        def bind(
            values: dict[str, str],
            **_kwargs: object,
        ) -> None:
            values["INTEGRATION_SMS_ENDPOINT"] = "https://127.0.0.1:17330"

        return auth, mock.Mock(side_effect=bind)

    def test_running_test_live_selects_only_exact_mutable_composition(self) -> None:
        auth, binder = self._patch_common()
        receipt = _mutable_receipt()
        composition = _composition()
        with (
            mock.patch.object(
                stackctl, "load_local_environment_auth", return_value=auth
            ),
            mock.patch.object(
                stackctl, "load_test_live_startup_attempt", return_value=receipt
            ),
            mock.patch.object(
                stackctl,
                "compile_provider_runtime_composition",
                return_value=composition,
            ) as compile_mutable,
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                side_effect=AssertionError("running test_live must not fallback"),
            ) as active_immutable,
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                side_effect=AssertionError("running test_live must not read immutable"),
            ) as immutable_receipt,
            mock.patch.object(
                stackctl, "_bind_local_external_provider_environment", binder
            ),
        ):
            environment = stackctl._provider_conformance_runtime_environment("alpha")

        self.assertEqual(
            environment["INTEGRATION_SMS_ENDPOINT"],
            "https://127.0.0.1:17330",
        )
        compile_mutable.assert_called_once_with(
            environment="alpha", target="alpha-local"
        )
        active_immutable.assert_not_called()
        immutable_receipt.assert_not_called()
        self.assertIs(binder.call_args.kwargs["runtime_composition"], composition)
        self.assertEqual(
            json.loads(
                environment["QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"]
            ),
            {
                "schema": "stackctl.provider_conformance_runtime_identity.v1",
                "runtimeMode": "test_live",
                "environment": "alpha",
                "target": "alpha-local",
                "workload": "full",
                "startupAttemptId": "attempt-test-live-alpha",
                "providerRuntimeDigest": _PROVIDER_DIGEST,
                "failureFree": True,
                "nonPromotable": True,
                "mutableComposeDigest": receipt["composeDigest"],
                "mutableConfigurationDigest": receipt["configurationDigest"],
                "mutableStateDigest": receipt["mutableStateDigest"],
                "mutableWorkspaceStatusDigest": receipt[
                    "workspaceStatusDigest"
                ],
                "mutableResolverHandoffDigest": receipt[
                    "resolverHandoffDigest"
                ],
                "mutableSourceRevision": receipt["sourceRevision"],
            },
        )

    def test_running_test_live_identity_drift_fails_without_immutable_fallback(
        self,
    ) -> None:
        auth, binder = self._patch_common()
        receipt = _mutable_receipt()
        receipt["target"] = "beta-local"
        with (
            mock.patch.object(
                stackctl, "load_local_environment_auth", return_value=auth
            ),
            mock.patch.object(
                stackctl, "load_test_live_startup_attempt", return_value=receipt
            ),
            mock.patch.object(
                stackctl,
                "compile_provider_runtime_composition",
                return_value=_composition(),
            ) as compile_mutable,
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                side_effect=AssertionError("drift must fail, not fallback"),
            ) as active_immutable,
            mock.patch.object(
                stackctl, "_bind_local_external_provider_environment", binder
            ),
            self.assertRaisesRegex(RuntimeError, "test_live runtime identity drifted"),
        ):
            stackctl._provider_conformance_runtime_environment("alpha")

        compile_mutable.assert_not_called()
        active_immutable.assert_not_called()
        binder.assert_not_called()

    def test_stopped_foreign_test_live_does_not_pollute_current_immutable(
        self,
    ) -> None:
        auth, binder = self._patch_common()
        stopped_foreign = _mutable_receipt(status="stopped")
        stopped_foreign.update({"environment": "beta", "target": "beta-local"})
        active = {"baselineId": _BASELINE_A, "composition": _composition()}
        with (
            mock.patch.object(
                stackctl, "load_local_environment_auth", return_value=auth
            ),
            mock.patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value=stopped_foreign,
            ),
            mock.patch.object(
                stackctl,
                "compile_provider_runtime_composition",
                side_effect=AssertionError("stopped test_live must not be selected"),
            ) as compile_mutable,
            mock.patch.object(
                stackctl, "_active_provider_runtime", return_value=active
            ) as active_immutable,
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=_immutable_receipt(),
            ) as immutable_receipt,
            mock.patch.object(
                stackctl, "_bind_local_external_provider_environment", binder
            ),
        ):
            environment = stackctl._provider_conformance_runtime_environment("alpha")

        self.assertIn("INTEGRATION_SMS_ENDPOINT", environment)
        compile_mutable.assert_not_called()
        active_immutable.assert_called_once_with("alpha", "alpha-local")
        immutable_receipt.assert_called_once_with("alpha-local")
        self.assertIs(
            binder.call_args.kwargs["runtime_composition"], active["composition"]
        )
        self.assertEqual(
            json.loads(
                environment["QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"]
            ),
            {
                "schema": "stackctl.provider_conformance_runtime_identity.v1",
                "runtimeMode": "immutable_candidate",
                "environment": "alpha",
                "target": "alpha-local",
                "workload": "full",
                "startupAttemptId": "attempt-immutable-alpha",
                "providerRuntimeDigest": _PROVIDER_DIGEST,
                "failureFree": True,
                "nonPromotable": False,
                "candidateDigest": _BASELINE_A,
            },
        )

    def test_explicit_identity_is_not_elided_as_an_inherited_environment_delta(
        self,
    ) -> None:
        auth, binder = self._patch_common()
        active = {"baselineId": _BASELINE_A, "composition": _composition()}
        expected_identity = json.dumps(
            {
                "schema": "stackctl.provider_conformance_runtime_identity.v1",
                "runtimeMode": "immutable_candidate",
                "environment": "alpha",
                "target": "alpha-local",
                "workload": "full",
                "startupAttemptId": "attempt-immutable-alpha",
                "providerRuntimeDigest": _PROVIDER_DIGEST,
                "failureFree": True,
                "nonPromotable": False,
                "candidateDigest": _BASELINE_A,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with (
            mock.patch.dict(
                stackctl.os.environ,
                {
                    stackctl.PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV: (
                        expected_identity
                    )
                },
                clear=False,
            ),
            mock.patch.object(
                stackctl, "load_local_environment_auth", return_value=auth
            ),
            mock.patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value=_mutable_receipt(status="stopped"),
            ),
            mock.patch.object(
                stackctl, "_active_provider_runtime", return_value=active
            ),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=_immutable_receipt(),
            ),
            mock.patch.object(
                stackctl, "_bind_local_external_provider_environment", binder
            ),
        ):
            environment = stackctl._provider_conformance_runtime_environment(
                "alpha"
            )

        self.assertEqual(
            environment[stackctl.PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV],
            expected_identity,
        )

    def test_immutable_startup_mismatch_fails_without_mutable_fallback(self) -> None:
        auth, binder = self._patch_common()
        active = {"baselineId": _BASELINE_A, "composition": _composition()}
        with (
            mock.patch.object(
                stackctl, "load_local_environment_auth", return_value=auth
            ),
            mock.patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value=_mutable_receipt(status="stopped"),
            ),
            mock.patch.object(
                stackctl,
                "compile_provider_runtime_composition",
                side_effect=AssertionError("immutable mismatch must not fallback"),
            ) as compile_mutable,
            mock.patch.object(
                stackctl, "_active_provider_runtime", return_value=active
            ),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=_immutable_receipt(candidate=_BASELINE_B),
            ),
            mock.patch.object(
                stackctl, "_bind_local_external_provider_environment", binder
            ),
            self.assertRaisesRegex(
                RuntimeError, "immutable runtime does not match the active candidate"
            ),
        ):
            stackctl._provider_conformance_runtime_environment("alpha")

        compile_mutable.assert_not_called()
        binder.assert_not_called()

    def test_single_cell_forwards_exact_runtime_identity_to_runner(self) -> None:
        runtime_environment = {
            "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY": json.dumps(
                {"environment": "alpha"}
            )
        }
        runner = mock.Mock()
        runner.main.return_value = 0
        args = argparse.Namespace(
            matrix=False,
            environment_matrix=False,
            adapter_id="ext.sms.local_capture",
            capability_id="identity.sms.otp",
            env="alpha",
            layer="user_acceptance",
            execute=True,
            image_digest="",
            data_digest="",
        )
        with (
            mock.patch.object(
                stackctl,
                "_provider_conformance_runtime_environment",
                return_value=runtime_environment,
            ) as select_runtime,
            mock.patch.object(
                stackctl,
                "_provider_conformance_runner",
                return_value=runner,
            ),
        ):
            result = stackctl.command_provider_conformance(args)

        self.assertEqual(result["exitCode"], 0)
        select_runtime.assert_called_once_with("alpha")
        self.assertEqual(
            runner.main.call_args.kwargs["runtime_environments"],
            {"alpha": runtime_environment},
        )

    def test_matrix_preselects_every_environment_identity_before_runner(
        self,
    ) -> None:
        environments = ("alpha", "beta", "gamma")
        runtime_environments = {
            environment: {
                "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY": json.dumps(
                    {"environment": environment}
                )
            }
            for environment in environments
        }
        runner = mock.Mock()
        runner.main.return_value = 0
        conformance = mock.Mock(ENVIRONMENTS=environments)
        args = argparse.Namespace(
            matrix=True,
            environment_matrix=False,
            adapter_id="",
            capability_id="identity.sms.otp",
            env="",
            layer="",
            execute=True,
            image_digest="",
            data_digest="",
        )
        with (
            mock.patch.object(
                stackctl,
                "_provider_conformance_runtime_environment",
                side_effect=lambda environment: runtime_environments[environment],
            ) as select_runtime,
            mock.patch.object(
                stackctl,
                "_provider_conformance",
                return_value=conformance,
            ),
            mock.patch.object(
                stackctl,
                "_provider_conformance_runner",
                return_value=runner,
            ),
        ):
            result = stackctl.command_provider_conformance(args)

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            [call.args[0] for call in select_runtime.call_args_list],
            list(environments),
        )
        self.assertEqual(
            runner.main.call_args.kwargs["runtime_environments"],
            runtime_environments,
        )

    def test_environment_matrix_forwards_one_exact_identity_to_every_cell(
        self,
    ) -> None:
        runtime_environment = {
            "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY": json.dumps(
                {"environment": "alpha"}
            )
        }
        binding = {
            "adapter_id": "ext.sms.local_capture",
            "state": "enabled",
        }
        compiled = {
            "selectedBindings": {
                "alpha": {"identity.sms.otp": binding},
            }
        }
        governance = mock.Mock()
        governance.load_and_compile.return_value = (compiled, [])
        governance.load_registry.return_value = {}
        governance.requires_provider_conformance.return_value = True
        conformance = mock.Mock()
        conformance.expected_required_cell_keys.return_value = {
            ("identity.sms.otp", "alpha", "local_contract")
        }
        conformance.discover_test_sources.return_value = ({}, [])
        conformance.load_validate_local_functional_readiness.return_value = (
            [Path("one"), Path("two"), Path("three")],
            [],
        )
        runner = mock.Mock()

        def run_cell(
            _argv: list[str],
            *,
            evidence_paths_out: list[Path],
            runtime_environments: dict[str, dict[str, str]],
        ) -> int:
            self.assertEqual(runtime_environments, {"alpha": runtime_environment})
            evidence_paths_out.append(Path(str(len(evidence_paths_out))))
            return 0

        runner.main.side_effect = run_cell
        args = argparse.Namespace(
            matrix=False,
            environment_matrix=True,
            adapter_id="",
            capability_id="",
            env="alpha",
            layer="",
            execute=True,
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "_external_provider_governance",
                return_value=governance,
            ),
            mock.patch.object(
                stackctl,
                "_provider_conformance",
                return_value=conformance,
            ),
            mock.patch.object(
                stackctl,
                "_provider_conformance_runner",
                return_value=runner,
            ),
            mock.patch.object(
                stackctl,
                "_provider_conformance_runtime_environment",
                return_value=runtime_environment,
            ) as select_runtime,
        ):
            result = stackctl.command_provider_conformance(args)

        self.assertEqual(result["exitCode"], 0)
        select_runtime.assert_called_once_with("alpha")
        self.assertEqual(runner.main.call_count, 3)


if __name__ == "__main__":
    unittest.main()
