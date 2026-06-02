from __future__ import annotations

import io
import unittest
from unittest import mock

from agent_ops.deploy.lib.dev_up import (
    app_target_for_env,
    pick_dev_up_env,
    resolve_app_endpoint_overrides,
    runtime_env_for_dev_env,
)
from agent_ops.deploy.lib.environment_topology import load_environment_topology


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class DevUpTest(unittest.TestCase):
    def test_beta_android_emulator_uses_android_loopback(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "beta",
            "android_emulator",
            topology=topology,
        )
        self.assertEqual(app_target_for_env("beta"), "beta-local")
        self.assertEqual(overrides["gatewayBaseUrl"], "http://10.0.2.2:18000")
        self.assertEqual(overrides["mediaImageBaseUrl"], "http://10.0.2.2:18100")

    def test_gamma_web_uses_local_gamma_public_bases(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "gamma",
            "web",
            topology=topology,
        )
        self.assertEqual(app_target_for_env("gamma"), "gamma-local")
        self.assertEqual(overrides["gatewayBaseUrl"], "http://127.0.0.1:19000")
        self.assertEqual(overrides["mediaImageBaseUrl"], "http://127.0.0.1:19100")

    def test_prod_sim_maps_to_prod_runtime_env(self) -> None:
        self.assertEqual(runtime_env_for_dev_env("prod-sim"), "prod")

    def test_pick_dev_up_env_requires_tty_when_missing(self) -> None:
        with (
            mock.patch("sys.stdin.isatty", return_value=False),
            mock.patch("sys.stderr.isatty", return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "dev-up environment is missing"):
                pick_dev_up_env()

    def test_pick_dev_up_env_accepts_numeric_choice(self) -> None:
        with (
            mock.patch("sys.stdin", new=_TtyStringIO("2\n")),
            mock.patch("sys.stderr", new=_TtyStringIO()),
        ):
            self.assertEqual(
                pick_dev_up_env(("alpha", "beta", "gamma")),
                "beta",
            )


if __name__ == "__main__":
    unittest.main()
