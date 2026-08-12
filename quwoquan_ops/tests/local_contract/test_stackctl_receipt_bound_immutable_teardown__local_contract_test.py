"""Receipt-bound immutable local teardown contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


def _running_attempt(candidate_digest: str) -> dict[str, object]:
    return {
        "schema": "stackctl-local-startup-attempt",
        "status": "running",
        "env": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "attemptId": "attempt-alpha-receipt-bound",
        "candidateDigest": candidate_digest,
        "providerRuntimeDigest": "sha256:" + "2" * 64,
        "observabilityLogSinkDigest": "sha256:" + "3" * 64,
    }


def _down_args(report_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        target="alpha-local",
        workload="full",
        formal_release=False,
        release_manifest="",
        purge_rebuildable_state=False,
        report_dir=str(report_dir),
    )


class StackctlReceiptBoundImmutableTeardownTest(unittest.TestCase):
    def test_bind_projects_exact_receipt_candidate_root_without_active_fallback(
        self,
    ) -> None:
        receipt_candidate = "sha256:" + "1" * 64
        switched_active_candidate = "sha256:" + "9" * 64
        runtime_composition = {
            "configurationDigest": "sha256:" + "4" * 64,
            "images": {},
        }
        environment: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as temporary:
            candidate_root = (Path(temporary) / "receipt-candidate").resolve()
            with (
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=_running_attempt(receipt_candidate),
                ),
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_root,
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value={"baselineId": receipt_candidate},
                ) as load_manifest,
                mock.patch.object(
                    stackctl,
                    "_candidate_provider_runtime",
                    return_value={
                        "candidateRoot": candidate_root,
                        "providerRuntime": {"composition": {}},
                    },
                ) as candidate_provider,
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value={
                        "QWQ_PROVIDER_RUNTIME_DIGEST": "sha256:" + "2" * 64
                    },
                ) as provider_environment,
                mock.patch.object(
                    stackctl,
                    "_candidate_observability_log_sink",
                    return_value={
                        "candidateRoot": candidate_root,
                        "composition": {},
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_observability_log_sink_launch_environment",
                    return_value={
                        "QWQ_OBSERVABILITY_LOG_SINK_DIGEST": "sha256:" + "3" * 64
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=(runtime_composition, "quwoquan_alpha_release"),
                ),
                mock.patch.object(stackctl, "_apply_gamma_image_composition"),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": switched_active_candidate},
                ) as active_candidate,
            ):
                bound = stackctl._bind_local_teardown_runtime(
                    env_name="alpha",
                    target_name="alpha-local",
                    environment=environment,
                    purge_rebuildable_state=False,
                )

        self.assertEqual(bound[1], "runtime-receipt")
        self.assertEqual(
            environment[stackctl.RUNTIME_CANDIDATE_ROOT_ENV],
            str(candidate_root),
        )
        self.assertEqual(
            environment["QWQ_RELEASE_CANDIDATE_DIGEST"],
            receipt_candidate,
        )
        candidate_provider.assert_called_once_with(
            "alpha",
            "alpha-local",
            receipt_candidate,
            candidate_manifest={"baselineId": receipt_candidate},
            candidate_root=candidate_root,
        )
        load_manifest.assert_called_once_with(
            "alpha",
            "alpha-local",
            receipt_candidate,
            require_full=True,
            require_current_contract_graph=False,
        )
        provider_environment.assert_called_once_with(
            {"composition": {}},
            candidate_root=candidate_root,
            workload="full",
        )
        active_candidate.assert_not_called()

    def test_candidate_provider_rejects_root_outside_receipt_baseline(self) -> None:
        receipt_candidate = "sha256:" + "1" * 64
        with tempfile.TemporaryDirectory() as temporary:
            expected_root = (Path(temporary) / "expected").resolve()
            wrong_root = (Path(temporary) / "active-pointer-drift").resolve()
            with (
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=expected_root,
                ),
                mock.patch.object(stackctl, "load_candidate_manifest") as manifest,
                self.assertRaisesRegex(
                    ValueError,
                    "root differs from its baseline identity",
                ),
            ):
                stackctl._candidate_provider_runtime(
                    "alpha",
                    "alpha-local",
                    receipt_candidate,
                    candidate_root=wrong_root,
                )

        manifest.assert_not_called()

    def test_zero_lease_down_preserves_state_and_never_requests_purge(self) -> None:
        receipt_candidate = "sha256:" + "1" * 64
        attempt = _running_attempt(receipt_candidate)
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "alpha"},
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "active_consumer_leases",
                    return_value=[],
                ) as leases,
                mock.patch.object(
                    stackctl,
                    "load_test_live_startup_attempt",
                    return_value=None,
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=attempt,
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_LOCAL_RELEASE_ENV": "alpha",
                        "QWQ_LOCAL_RELEASE_TARGET": "alpha-local",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_local_teardown_runtime",
                    return_value=(
                        {"images": {}},
                        "runtime-receipt",
                        "quwoquan_alpha_release",
                        False,
                    ),
                ) as bind_runtime,
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [], 0, stdout="", stderr=""
                    ),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_wait_for_network_ports_released",
                    return_value=[],
                ) as wait_for_ports,
                mock.patch.object(
                    stackctl,
                    "transition_startup_attempt",
                    return_value={"status": "stopped"},
                ),
                mock.patch.object(stackctl.shutil, "rmtree") as rmtree,
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(_down_args(report_dir))

            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 0, result)
        leases.assert_called_once_with("alpha-local")
        bind_runtime.assert_called_once_with(
            env_name="alpha",
            target_name="alpha-local",
            environment=mock.ANY,
            purge_rebuildable_state=False,
        )
        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "bash",
                "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                "--down",
            ],
        )
        self.assertNotIn("--purge-rebuildable-state", run.call_args_list[0].args[0])
        wait_for_ports.assert_called_once_with(
            "alpha-local",
            port_reporter=stackctl._canonical_port_occupancy_report,
        )
        self.assertFalse(report["destructiveRepairPerformed"])
        self.assertEqual(report["destructiveActions"], [])
        rmtree.assert_not_called()


if __name__ == "__main__":
    unittest.main()
