"""Global local BuildKit cache reclamation contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import argparse
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl


LOCAL_TARGETS = ("alpha-local", "beta-local", "gamma-local")


def _repair_args(*, confirmed: bool) -> argparse.Namespace:
    return argparse.Namespace(
        target="alpha-local",
        fix="reclaim-build-cache",
        report_dir="",
        confirm_global_build_cache_reclaim=confirmed,
    )


def _runtime_audit(*, status: str = "running") -> dict[str, object]:
    targets = []
    for target in LOCAL_TARGETS:
        targets.append(
            {
                "target": target,
                "startupReceipts": [
                    {
                        "workload": "full",
                        "state": "present",
                        "status": status,
                        "path": f".qwq_output/env/{target}/startup_attempt.json",
                        "sha256": "sha256:" + "1" * 64,
                        "failure": None,
                        "cleanupFailure": None,
                    }
                ],
                "activeConsumerLeases": [
                    {"consumer": "flutter-run", "state": "active"}
                ],
                "ports": {"profile": target, "ports": []},
            }
        )
    return {"targets": targets, "evidenceIssues": []}


def _docker_results() -> list[CompletedProcess[str]]:
    return [
        CompletedProcess(["docker", "context", "show"], 0, "colima\n", ""),
        CompletedProcess(
            ["docker", "info", "--format", "{{json .}}"],
            0,
            '{"ID":"daemon-a","Name":"colima","Driver":"overlay2"}\n',
            "",
        ),
        CompletedProcess(
            ["docker", "builder", "ls", "--format", "json"],
            0,
            '{"Name":"default","Driver":"docker"}\n',
            "",
        ),
        CompletedProcess(["docker", "system", "df"], 0, "Build Cache 9.4GB\n", ""),
        CompletedProcess(
            ["docker", "builder", "prune", "--all", "--force"],
            0,
            "CACHE ID  RECLAIMABLE\ncache-a true\nTotal reclaimed space: 9.4GB\n",
            "",
        ),
        CompletedProcess(["docker", "system", "df"], 0, "Build Cache 0B\n", ""),
    ]


class StackctlReclaimBuildCacheGlobalLockContractTest(unittest.TestCase):
    @contextlib.contextmanager
    def _repair_context(self, report_dir: Path) -> object:
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(stackctl, "load_environment_topology", return_value={})
            )
            stack.enter_context(mock.patch.object(
                stackctl,
                "get_target",
                return_value={"env": "alpha"},
            ))
            stack.enter_context(
                mock.patch.object(stackctl, "resolve_report_dir", return_value=report_dir)
            )
            stack.enter_context(mock.patch.object(stackctl, "_write_summary_bundle"))
            yield

    def test_cli_requires_explicit_global_reclaim_confirmation(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "repair",
                "--target",
                "alpha-local",
                "--fix",
                "reclaim-build-cache",
            ]
        )
        self.assertFalse(args.confirm_global_build_cache_reclaim)

        confirmed = stackctl.build_parser().parse_args(
            [
                "repair",
                "--target",
                "alpha-local",
                "--fix",
                "reclaim-build-cache",
                "--confirm-global-build-cache-reclaim",
            ]
        )
        self.assertTrue(confirmed.confirm_global_build_cache_reclaim)

    def test_missing_confirmation_fails_before_any_docker_or_lock(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            self._repair_context(Path(temporary_dir)),
            mock.patch.object(stackctl, "run") as run,
            mock.patch.object(stackctl, "_global_local_build_cache_lock") as lock,
        ):
            payload = stackctl.command_repair(_repair_args(confirmed=False))

        self.assertEqual(payload["exitCode"], 2)
        self.assertIn("--confirm-global-build-cache-reclaim", " ".join(payload["details"]))
        run.assert_not_called()
        lock.assert_not_called()

    def test_global_exclusive_gc_conflicts_with_shared_runtime_use_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "local-runtime.lock"
            with mock.patch.object(
                stackctl,
                "local_runtime_operation_lock_path",
                return_value=lock_path,
            ):
                shared = stackctl.acquire_local_runtime_use_lock(
                    target="alpha-local",
                    purpose="runtime-package-build",
                    lock_path=lock_path,
                )
                try:
                    with self.assertRaisesRegex(RuntimeError, "already running"):
                        with stackctl._global_local_build_cache_lock():
                            self.fail("exclusive GC lock must not enter")
                finally:
                    shared.close()

    def test_command_lock_conflict_fails_before_runtime_audit_and_docker(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            self._repair_context(Path(temporary_dir)),
            mock.patch.object(
                stackctl,
                "_global_local_build_cache_lock",
                side_effect=RuntimeError("local runtime operation is already running: package"),
            ),
            mock.patch.object(stackctl, "_local_build_cache_runtime_audit") as audit,
            mock.patch.object(stackctl, "run") as run,
        ):
            payload = stackctl.command_repair(_repair_args(confirmed=True))
            report = json.loads((Path(temporary_dir) / "report.json").read_text())

        self.assertEqual(payload["exitCode"], 2)
        self.assertFalse(report["destructiveRepairPerformed"])
        self.assertIn("already running", " ".join(report["resourceReleaseIssues"]))
        audit.assert_not_called()
        run.assert_not_called()

    def test_shared_package_locks_allow_different_targets_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "local-runtime.lock"
            with mock.patch.object(
                stackctl,
                "local_runtime_operation_lock_path",
                return_value=lock_path,
            ):
                alpha = stackctl.acquire_local_runtime_use_lock(
                    target="alpha-local",
                    purpose="runtime-package-build",
                    lock_path=lock_path,
                )
                beta = stackctl.acquire_local_runtime_use_lock(
                    target="beta-local",
                    purpose="runtime-package-build",
                    lock_path=lock_path,
                )
                alpha.close()
                beta.close()

    def test_package_lock_conflict_is_reported_before_workspace_snapshot(self) -> None:
        args = argparse.Namespace(
            kind="runtime",
            env="alpha",
            target="alpha-local",
            service="",
            include_services=True,
            release_attestation="candidate.json",
            rollback_release_attestation="rollback.json",
        )
        with (
            mock.patch.object(stackctl, "validate_release_attestations", return_value={}),
            mock.patch.object(
                stackctl,
                "acquire_local_runtime_use_lock",
                side_effect=RuntimeError("local runtime operation is already running: gc"),
            ) as acquire,
            mock.patch.object(stackctl, "materialize_package_input_capsule") as snapshot,
        ):
            payload = stackctl.command_package(args)

        self.assertEqual(payload["exitCode"], 2)
        self.assertIn("already running", " ".join(payload["details"]))
        acquire.assert_called_once_with(
            target="alpha-local",
            purpose="runtime-package-build",
        )
        snapshot.assert_not_called()

    def test_provider_uat_holds_shared_lock_and_fails_closed_on_gc_conflict(self) -> None:
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
                "acquire_local_runtime_use_lock",
                side_effect=RuntimeError("local runtime operation is already running: gc"),
            ) as acquire,
            mock.patch.object(stackctl, "_command_provider_conformance_unlocked") as unlocked,
        ):
            payload = stackctl.command_provider_conformance(args)

        self.assertEqual(payload["exitCode"], 2)
        acquire.assert_called_once_with(
            target="alpha-local",
            purpose="provider-conformance-uat",
        )
        unlocked.assert_not_called()

    def test_running_receipts_and_app_leases_are_report_only_under_exclusive_lock(
        self,
    ) -> None:
        audit = _runtime_audit(status="running")
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            self._repair_context(Path(temporary_dir)),
            mock.patch.object(stackctl, "_local_build_cache_runtime_audit", return_value=audit),
            mock.patch.object(stackctl, "run", side_effect=_docker_results()) as run,
        ):
            payload = stackctl.command_repair(_repair_args(confirmed=True))
            report = json.loads((Path(temporary_dir) / "report.json").read_text())

        self.assertEqual(payload["exitCode"], 0)
        self.assertTrue(report["confirmation"])
        self.assertEqual(report["resourceScope"], "docker_daemon_global")
        self.assertFalse(report["targetScoped"])
        self.assertEqual(report["selection"], "unused_build_cache_all")
        self.assertEqual(report["runtimeAudit"], audit)
        self.assertEqual(
            report["preservedResourceClasses"],
            ["containers", "images", "volumes", "runtime-data"],
        )
        self.assertTrue(report["destructiveRepairPerformed"])
        self.assertEqual(report["resourceReleaseIssues"], [])
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [result.args for result in _docker_results()],
        )

    def test_missing_receipts_are_explicit_and_do_not_infer_target_ownership(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "consumer_lease_dir",
                return_value=Path(temporary_dir) / "missing-leases",
            ),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                return_value=None,
            ),
            mock.patch.object(stackctl, "active_consumer_leases", return_value=[]),
            mock.patch.object(
                stackctl,
                "_canonical_port_occupancy_report",
                return_value={"profile": "", "ports": [], "publicEndpoints": []},
            ),
            mock.patch.object(
                stackctl,
                "_network_report",
                side_effect=AssertionError(
                    "build-cache audit must not require active Provider identity"
                ),
            ),
        ):
            audit = stackctl._local_build_cache_runtime_audit()

        self.assertEqual(len(audit["targets"]), 3)
        for target in audit["targets"]:
            self.assertEqual(target["consumerLeaseReceipts"], [])
            self.assertEqual(
                [receipt["state"] for receipt in target["startupReceipts"]],
                ["missing", "missing", "missing", "missing"],
            )
            self.assertEqual(
                [receipt["status"] for receipt in target["startupReceipts"]],
                ["absent", "absent", "absent", "absent"],
            )

    def test_running_receipt_and_active_lease_are_normal_audit_facts(self) -> None:
        running = {
            "status": "running",
            "attemptId": "attempt-alpha",
            "candidateDigest": "sha256:" + "1" * 64,
            "failure": None,
            "cleanupFailure": None,
        }
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "consumer_lease_dir",
                return_value=Path(temporary_dir) / "missing-leases",
            ),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=running),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                return_value=running,
            ),
            mock.patch.object(
                stackctl,
                "startup_attempt_path",
                return_value=Path(temporary_dir) / "receipt.json",
            ),
            mock.patch.object(
                stackctl,
                "startup_attempt_path_for_workload",
                return_value=Path(temporary_dir) / "workload-receipt.json",
            ),
            mock.patch.object(stackctl, "_sha256_file", return_value="sha256:" + "2" * 64),
            mock.patch.object(
                stackctl,
                "active_consumer_leases",
                return_value=[{"consumer": "flutter-run", "state": "active"}],
            ),
            mock.patch.object(
                stackctl,
                "_canonical_port_occupancy_report",
                return_value={"profile": "alpha-local", "ports": []},
            ),
        ):
            audit = stackctl._local_build_cache_runtime_audit()

        self.assertEqual(audit["evidenceIssues"], [])
        self.assertEqual(audit["runtimeAnomalies"], [])
        self.assertFalse(audit["runningRuntimeBlocksCacheReclaim"])
        self.assertFalse(audit["activeConsumerLeaseBlocksCacheReclaim"])

    def test_unreadable_consumer_lease_receipt_blocks_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lease_dir = Path(temporary_dir)
            (lease_dir / "broken.json").write_text("{", encoding="utf-8")
            with mock.patch.object(
                stackctl,
                "consumer_lease_dir",
                return_value=lease_dir,
            ):
                with self.assertRaisesRegex(ValueError, "lease receipt is unreadable"):
                    stackctl._local_build_cache_runtime_audit()

    def test_unreadable_runtime_audit_fails_before_docker_prune(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            self._repair_context(Path(temporary_dir)),
            mock.patch.object(
                stackctl,
                "_local_build_cache_runtime_audit",
                side_effect=ValueError("startup attempt receipt is unreadable"),
            ),
            mock.patch.object(stackctl, "run") as run,
        ):
            payload = stackctl.command_repair(_repair_args(confirmed=True))
            report = json.loads((Path(temporary_dir) / "report.json").read_text())

        self.assertEqual(payload["exitCode"], 2)
        self.assertFalse(report["destructiveRepairPerformed"])
        self.assertIn("unreadable", " ".join(report["resourceReleaseIssues"]))
        run.assert_not_called()

    def test_prune_failure_is_typed_and_never_calls_other_prune_families(self) -> None:
        results = _docker_results()
        results[4] = CompletedProcess(
            ["docker", "builder", "prune", "--all", "--force"],
            1,
            "",
            "builder unavailable",
        )
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            self._repair_context(Path(temporary_dir)),
            mock.patch.object(
                stackctl,
                "_local_build_cache_runtime_audit",
                return_value=_runtime_audit(),
            ),
            mock.patch.object(stackctl, "run", side_effect=results) as run,
        ):
            payload = stackctl.command_repair(_repair_args(confirmed=True))
            report = json.loads((Path(temporary_dir) / "report.json").read_text())

        self.assertNotEqual(payload["exitCode"], 0)
        self.assertEqual(
            report["prune"]["argv"],
            ["docker", "builder", "prune", "--all", "--force"],
        )
        self.assertIn("builder unavailable", " ".join(report["resourceReleaseIssues"]))
        commands = [" ".join(call.args[0]) for call in run.call_args_list]
        self.assertFalse(any("system prune" in command for command in commands))
        self.assertFalse(any("image prune" in command for command in commands))
        self.assertFalse(any("volume prune" in command for command in commands))
        self.assertFalse(any("container prune" in command for command in commands))

    def test_gamma_no_space_guidance_uses_only_managed_stackctl_repair(self) -> None:
        source = (
            stackctl.ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("stackctl.py", source)
        self.assertIn("reclaim-build-cache", source)
        self.assertIn("--confirm-global-build-cache-reclaim", source)
        for forbidden in (
            "docker builder prune",
            "docker system prune",
            "docker image prune",
            "docker volume prune",
            "docker container prune",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
