"""媒体发布 Remote Patrol 必须进入 release 与 beta 设备矩阵。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPT = (
    ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "user_acceptance"
    / "service_ops"
    / "content-service"
    / "ci"
    / "run_media_publication_device_matrix_ci.py"
)
SUITES_PATH = ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"
MATRIX_RUNNER_PATH = ROOT / "quwoquan_ops/ci/run_mobile_platform_matrix.sh"
BETA_STARTUP_PATH = ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app.sh"
SPEC = importlib.util.spec_from_file_location(
    "run_media_publication_device_matrix_ci",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load media publication device matrix runner")
matrix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matrix)

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli import stackctl  # noqa: E402


class MediaPublicationDeviceMatrixContractTest(unittest.TestCase):
    def test_lifecycle_probe_uses_topology_declared_internal_moderation_origin(
        self,
    ) -> None:
        topology = load_environment_topology()
        cases = (
            ("beta", "beta-local", stackctl.VerificationProfile.INTEGRATION),
            ("gamma", "gamma-local", stackctl.VerificationProfile.RELEASE),
            ("prod", "prod-sim", stackctl.VerificationProfile.INTEGRATION),
        )
        for environment, target_name, profile in cases:
            with self.subTest(target=target_name):
                command = stackctl._media_publication_lifecycle_profile_command(
                    environment,
                    target_name,
                    profile,
                    None,
                )
                self.assertIsNotNone(command)
                argv = command["argv"]
                self.assertEqual(
                    argv[argv.index("--moderation-base-url") + 1],
                    get_target(topology, target_name)["origins"]["contentService"],
                )

    def test_beta_startup_never_seeds_business_users(self) -> None:
        startup = BETA_STARTUP_PATH.read_text(encoding="utf-8")
        for retired in (
            "app_beta_seed_manifest.json",
            "beta_manual_seed_user_fixtures",
            "go run ./services/user-service/cmd/seed",
            "fixture_user_current",
            'entry.get("resetScope")',
        ):
            self.assertNotIn(retired, startup)
        user_health = startup.index(
            'beta_manual_wait_http_ok "http://127.0.0.1:${USER_PORT}/healthz"',
        )
        ready = startup.index(
            "beta Mongo/Redis/content/user runtime OK",
            user_health,
        )
        self.assertLess(user_health, ready)
        self.assertIn(
            "@creator_profile_release path /auth /auth/* /user /user/* /users /users/*",
            startup,
        )
        self.assertIn(
            "reverse_proxy ${CONTAINER_HOST_ALIAS}:${USER_PORT}",
            startup,
        )
        self.assertIn("ship apply is the only writer of this directory", startup)

    def test_supported_environments_use_topology_and_runtime_anonymous_login(
        self,
    ) -> None:
        topology = load_environment_topology()
        cases = (
            ("beta", "beta-local", "local-beta", "beta"),
            ("gamma", "gamma-local", "local-gamma", "gamma"),
            ("prod-sim", "prod-sim", "local-prod-sim", "prod"),
        )
        for environment, target_name, alias, runtime_env in cases:
            with self.subTest(environment=environment):
                args = argparse.Namespace(
                    environment=environment,
                    platform="ios",
                    device_id=[],
                    report="",
                    dry_run=True,
                )
                command = matrix.build_command(args)
                target = get_target(topology, target_name)
                public_bases = target["publicBases"]

                self.assertEqual(
                    command[command.index("--env-name") + 1],
                    alias,
                )
                self.assertEqual(
                    command[command.index("--runtime-env") + 1],
                    runtime_env,
                )
                self.assertNotIn("--data-source", command)
                self.assertEqual(
                    command[command.index("--gateway-base-url") + 1],
                    public_bases["api"],
                )
                self.assertEqual(
                    command[command.index("--media-upload-base-url") + 1],
                    public_bases["mediaUpload"],
                )
                self.assertEqual(
                    command[command.index("--target") + 1],
                    matrix.PATROL_TARGET,
                )
                self.assertIn("--dry-run", command)
                joined = " ".join(command)
                self.assertNotIn("AUTH_TOKEN", joined)
                self.assertNotIn("fixture", joined.lower())

    def test_registered_patrol_target_is_a_real_file(self) -> None:
        self.assertTrue((ROOT / "quwoquan_app" / matrix.PATROL_TARGET).is_file())

    def test_release_and_beta_profiles_schedule_media_publication(self) -> None:
        suites = json.loads(SUITES_PATH.read_text(encoding="utf-8"))
        journey = suites["uiJourneys"]["content_media_publication_patrol"]
        self.assertEqual(journey["runner"], "patrol")
        self.assertEqual(journey["target"], matrix.PATROL_TARGET)

        for profile_name in ("nightly_full", "release_candidate"):
            profile = suites["profiles"][profile_name]
            self.assertIn(
                "content_media_publication_patrol",
                profile["uiJourneys"],
            )
            self.assertIn(
                "media-publication",
                profile["deviceMatrix"]["matrixKinds"],
            )
        mainline = suites["profiles"]["mainline_auto_prod"]["deviceMatrix"]
        self.assertEqual(mainline["envs"], ["beta"])
        self.assertTrue(mainline["requireAllPlatforms"])
        self.assertIn("media-publication", mainline["matrixKinds"])

    def test_local_environment_runner_uses_dedicated_media_runner(self) -> None:
        workflow = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (MATRIX_RUNNER_PATH,)
        )
        self.assertIn('[[ "$matrix_kind" == "media-publication" ]]', workflow)
        self.assertIn(
            "run_media_publication_device_matrix_ci.py",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
