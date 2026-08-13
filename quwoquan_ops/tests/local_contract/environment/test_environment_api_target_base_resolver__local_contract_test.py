from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENT_CANONICAL_TARGET,
    get_target,
    load_environment_topology,
    resolve_environment_target_base,
)
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports


class EnvironmentApiTargetBaseResolverTest(unittest.TestCase):
    def test_alpha_beta_gamma_resolve_from_canonical_runtime_topology(self) -> None:
        topology = load_environment_topology()
        port_manifest = load_port_manifest()

        for environment in ("alpha", "beta", "gamma"):
            target_name = ENVIRONMENT_CANONICAL_TARGET[environment]
            target = get_target(topology, target_name)
            resolved = resolve_environment_target_base(topology, environment)

            self.assertEqual(resolved.environment, environment)
            self.assertEqual(resolved.target, target_name)
            self.assertEqual(
                resolved.api_base,
                target["publicBases"]["api"].rstrip("/"),
            )
            expected_port = profile_ports(
                port_manifest,
                str(target["portProfile"]),
            )["api-edge"]
            self.assertEqual(urlparse(resolved.api_base).port, expected_port)

    def test_explicit_noncanonical_target_is_rejected(self) -> None:
        topology = load_environment_topology()

        with self.assertRaisesRegex(
            ValueError,
            "gamma API integration requires canonical target gamma-local",
        ):
            resolve_environment_target_base(
                topology,
                "gamma",
                target_name="beta-local",
            )

    def test_missing_runtime_tree_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with self.assertRaises(FileNotFoundError):
                load_environment_topology(Path(temporary_dir))


if __name__ == "__main__":
    unittest.main()
