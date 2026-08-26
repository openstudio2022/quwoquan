from __future__ import annotations

import copy
import unittest

from quwoquan_ops.cli.lib.environment_topology import (
    load_environment_topology,
    validate_environment_topology,
)


class EnvironmentTopologyUserPostgresContractTest(unittest.TestCase):
    def test_canonical_topology_requires_user_postgres_coordinates(self) -> None:
        issues = validate_environment_topology(load_environment_topology())
        self.assertEqual(issues, [])

    def test_every_environment_declares_exactly_the_four_runtime_planes(self) -> None:
        # spec_ref: specs/feature-tree/runtime/system-topology-and-networking/spec.md#sit-002.t1
        topology = load_environment_topology()
        for env_name, environment in topology["environments"].items():
            with self.subTest(environment=env_name):
                self.assertEqual(
                    set(environment["subnets"]),
                    {"edge", "media", "service", "data"},
                )

    def test_local_import_without_user_postgres_port_role_fails_closed(self) -> None:
        topology = copy.deepcopy(load_environment_topology())
        del topology["targets"]["alpha-local"]["dataRelease"]["userPostgresPortRole"]

        issues = validate_environment_topology(topology)

        self.assertTrue(
            any(
                "alpha-local: dataRelease.userPostgresPortRole must reference a port role"
                in issue
                for issue in issues
            ),
            issues,
        )

    def test_local_media_upload_role_rejects_non_object_storage_port(self) -> None:
        topology = copy.deepcopy(load_environment_topology())
        topology["targets"]["alpha-local"]["resolvedUrlRoles"]["mediaUpload"][
            "portRole"
        ] = "media-edge"

        issues = validate_environment_topology(topology)

        self.assertTrue(
            any(
                "alpha-local: resolvedUrlRoles.mediaUpload.portRole must be "
                "object-storage-edge" in issue
                for issue in issues
            ),
            issues,
        )

    def test_hosted_import_without_user_postgres_dsn_env_fails_closed(self) -> None:
        topology = copy.deepcopy(load_environment_topology())
        del topology["targets"]["prod-hosted"]["dataRelease"]["userPostgresDsnEnv"]

        issues = validate_environment_topology(topology)

        self.assertTrue(
            any(
                "prod-hosted: dataRelease.userPostgresDsnEnv must be an environment key name"
                in issue
                for issue in issues
            ),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
