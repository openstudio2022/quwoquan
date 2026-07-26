from __future__ import annotations

import fcntl
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
    validate_environment_topology,
)
from quwoquan_ops.cli.lib.local_runtime_reservation import (
    acquire_local_runtime_use_lock,
    active_conflicting_local_targets,
    assert_local_runtime_available,
)


class LocalRuntimeReservationContractTest(unittest.TestCase):
    def test_local_targets_share_one_metadata_owned_resource_group(self) -> None:
        topology = load_environment_topology()

        self.assertEqual(validate_environment_topology(topology), [])
        self.assertEqual(
            {
                get_target(topology, target)["localResourceGroup"]
                for target in (
                    "alpha-local",
                    "beta-local",
                    "gamma-local",
                    "prod-sim",
                )
            },
            {"workstation-commercial-runtime"},
        )

    def test_beta_start_rejects_an_active_alpha_runtime(self) -> None:
        topology = load_environment_topology()
        alpha_port = urlparse(
            get_target(topology, "alpha-local")["origins"]["contentService"]
        ).port

        def probe(host: str, port: int) -> bool:
            self.assertIn(host, {"127.0.0.1", "localhost"})
            return port == alpha_port

        with self.assertRaisesRegex(
            RuntimeError,
            "stackctl.py down --target alpha-local",
        ):
            assert_local_runtime_available(
                topology,
                "beta-local",
                port_probe=probe,
            )

    def test_running_requested_target_does_not_conflict_with_itself(self) -> None:
        topology = load_environment_topology()
        beta_port = urlparse(
            get_target(topology, "beta-local")["origins"]["contentService"]
        ).port

        conflicts = active_conflicting_local_targets(
            topology,
            "beta-local",
            port_probe=lambda _host, port: port == beta_port,
        )

        self.assertEqual(conflicts, ())

    def test_patrol_use_lease_blocks_destructive_runtime_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "local-runtime.lock"
            lease = acquire_local_runtime_use_lock(
                target="beta-local",
                purpose="environment-patrol-smoke",
                lock_path=lock_path,
            )
            contender = lock_path.open("a+", encoding="utf-8")
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(
                        contender.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
            finally:
                contender.close()
                lease.close()


if __name__ == "__main__":
    unittest.main()
