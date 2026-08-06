"""Environment business-data boundaries.

spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
"""

from __future__ import annotations

import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.infrastructure_probe_plane import resolve_probe_response


ROOT = Path(__file__).resolve().parents[3]
BETA_MANUAL = ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app.sh"
BETA_STACK = ROOT / "quwoquan_ops/cli/beta/start_beta_stack.sh"
PROD_SIM = ROOT / "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh"
PORT_MANIFEST = ROOT / "quwoquan_ops/environments/local_env_port_manifest.yaml"
PORT_EXPORTS = ROOT / "quwoquan_ops/cli/print_local_port_profile.py"


class EnvironmentBusinessFixtureCutContractTest(unittest.TestCase):
    def test_retired_fixture_gateway_has_no_canonical_port_role(self) -> None:
        self.assertNotIn(
            "fixture-gateway",
            PORT_MANIFEST.read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "BETA_FIXTURE_GATEWAY_PORT",
            PORT_EXPORTS.read_text(encoding="utf-8"),
        )

    def test_beta_manual_has_one_release_consumer_path(self) -> None:
        script = BETA_MANUAL.read_text(encoding="utf-8")
        for retired in (
            "contracts/metadata/_shared/test_fixtures",
            "dev_assistant_beta_gateway.py",
            "beta_manual_start_fixture_gateway",
            "go run ./cmd/seed-fixture",
            "go run ./services/user-service/cmd/seed",
            "fixture_user_current",
            "fixture_photo_001",
        ):
            self.assertNotIn(retired, script)
        self.assertIn("ship apply is the only writer of this directory", script)
        self.assertIn('beta_manual_record_metadata "workload" "content-release"', script)
        self.assertIn("respond 404", script)

        stack = BETA_STACK.read_text(encoding="utf-8")
        self.assertIn("quwoquan_ops/cli/stackctl.py", stack)
        self.assertIn("--target beta-local", stack)
        self.assertNotIn("APP_BETA_CMD", stack)
        self.assertNotIn("go run", stack)
        self.assertNotIn("docker compose", stack)
        self.assertNotIn("--seed-verify", stack)
        self.assertNotIn("--media-mode", stack)
        self.assertNotIn("--full-matrix", stack)

    def test_prod_sim_requires_release_bound_media_before_mutation(self) -> None:
        script = PROD_SIM.read_text(encoding="utf-8")
        for retired in (
            "contracts/metadata/_shared/test_fixtures",
            "mock_public_plane.py",
            "fixture_photo_001",
            "video-primary-0001",
            "--enable-conversation-avatar-alias",
        ):
            self.assertNotIn(retired, script)
        for required in (
            "DATA_RELEASE_READINESS_RECEIPT",
            "load_release_content_identity",
            "load_release_video_binding",
            "resolve_readiness_path",
            "infrastructure_probe_plane.py",
        ):
            self.assertIn(required, script)
        for parallel_identity in (
            "QWQ_PROD_SIM_RELEASE_MEDIA_ROOT",
            "QWQ_PROD_SIM_RELEASE_ID",
            "QWQ_PROD_SIM_RELEASE_DIGEST",
            "VIDEO_PLAYBACK_CANARY_WORK_ID",
            "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY",
        ):
            self.assertNotIn(parallel_identity, script)
        up_body = script.split('  up)\n', 1)[1].split('  down)\n', 1)[0]
        self.assertIn("require_release_bound_media", up_body)
        self.assertNotIn('stackctl.py" package', up_body)
        self.assertIn('"status": "infrastructure_ready"', script)
        self.assertIn('"businessDataReady": False', script)


class InfrastructureProbePlaneContractTest(unittest.TestCase):
    PROBE_CONFIG = {
        "mode": "api",
        "runtime_env": "prod",
        "gateway_base_url": "https://api.sim.quwoquan.com",
        "legal_base_url": "https://sim.quwoquan.com/legal",
        "product_ops_base_url": "https://ops.sim.quwoquan.com",
        "media_avatar_base_url": "https://cdn.sim.quwoquan.com/media/avatar",
        "media_image_base_url": "https://cdn.sim.quwoquan.com/media/image",
        "media_video_base_url": "https://cdn.sim.quwoquan.com/media/video",
        "media_upload_base_url": "https://upload.sim.quwoquan.com",
    }

    def test_health_and_config_are_explicitly_not_business_ready(self) -> None:
        status, health = resolve_probe_response("GET", "/healthz", **self.PROBE_CONFIG)
        self.assertEqual(status, 200)
        self.assertEqual(health["boundary"], "infrastructure-probe")
        self.assertIs(health["businessDataReady"], False)

        status, config = resolve_probe_response(
            "GET", "/config/app", **self.PROBE_CONFIG
        )
        self.assertEqual(status, 200)
        self.assertEqual(config["appRuntimeEnv"], "prod")
        self.assertIs(config["businessDataReady"], False)

    def test_business_queries_and_commands_fail_closed(self) -> None:
        for path in (
            "/content/feed",
            "/homepages/search",
            "/chat/inbox",
            "/user/profile",
        ):
            status, payload = resolve_probe_response("GET", path, **self.PROBE_CONFIG)
            self.assertEqual(status, 503)
            self.assertEqual(payload["status"], "gate_block")
            self.assertIs(payload["businessDataReady"], False)

        status, payload = resolve_probe_response(
            "POST", "/auth/login/phone", **self.PROBE_CONFIG
        )
        self.assertEqual(status, 503)
        self.assertEqual(payload["status"], "gate_block")


if __name__ == "__main__":
    unittest.main()
