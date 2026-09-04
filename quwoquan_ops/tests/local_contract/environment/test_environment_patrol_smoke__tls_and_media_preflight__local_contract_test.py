"""Environment patrol TLS and media preflight contracts.

Mechanically split from
``test_environment_patrol_smoke__device_env_tls_and_runtime__local_contract_test.py``.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


class EnvironmentPatrolTlsAndMediaPreflightTest(EnvironmentPatrolSmokeCaseBase):
    def test_prod_sim_tls_uses_canonical_hosts_and_public_certificate(self) -> None:
        prod_sim = (
            ROOT / "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh"
        ).read_text(encoding="utf-8")

        for token in (
            'public_domain_tls.py" paths',
            "https://${PUBLIC_API_HOST}:${API_EDGE_PORT}",
            "https://${PUBLIC_PRODUCT_OPS_HOST}:${PRODUCT_OPS_PORT}",
            "https://${PUBLIC_CDN_HOST}:${MEDIA_EDGE_PORT}",
            "$QWQ_PUBLIC_TLS_CERT_FILE:/etc/caddy/tls/fullchain.pem:ro",
            '-p "${API_EDGE_PORT}:${API_EDGE_PORT}"',
            '-p "${PRODUCT_OPS_PORT}:${PRODUCT_OPS_PORT}"',
            '-p "${MEDIA_EDGE_PORT}:${MEDIA_EDGE_PORT}"',
        ):
            self.assertIn(token, prod_sim)

    def test_local_gamma_tls_uses_canonical_hosts_and_public_certificate(self) -> None:
        caddyfile = (
            ROOT / "quwoquan_ops/environments/gamma/local/Caddyfile"
        ).read_text(encoding="utf-8")
        compose = (
            ROOT / "quwoquan_service/services/content-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        infrastructure_compose = (
            ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        ports = (ROOT / "quwoquan_ops/cli/print_local_port_profile.py").read_text(
            encoding="utf-8"
        )

        for token in (
            "https://{$QWQ_PUBLIC_API_HOST}:{$LOCAL_GAMMA_HTTP_PORT:",
            "https://{$QWQ_PUBLIC_OPS_HOST}:{$LOCAL_GAMMA_PRODUCT_OPS_PORT:",
            "https://{$QWQ_PUBLIC_CDN_HOST}:{$LOCAL_GAMMA_MEDIA_EDGE_PORT:",
            "tls {$QWQ_PUBLIC_TLS_CERT_FILE} {$QWQ_PUBLIC_TLS_KEY_FILE}",
        ):
            self.assertIn(token, caddyfile)
        self.assertIn(
            "reverse_proxy @object_store_public_slice "
            "https://object-storage:{$LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT}",
            caddyfile,
        )
        self.assertIn(
            "tls_trust_pool file /etc/caddy/tls/object-storage-ca.pem",
            caddyfile,
        )
        # object-storage-edge 由带 TLS 的 MinIO workload 独占宿主端口；
        # Caddy 只通过 Compose 内网把缺失的 public slice 转发给该 workload。
        self.assertIn(
            '"${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:?LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT is required}:${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:?LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT is required}"',
            infrastructure_compose,
        )
        self.assertNotIn(
            '"${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:-19130}:${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:-19130}"',
            infrastructure_compose,
        )
        self.assertIn(
            '"LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT": "object-storage-edge"',
            ports,
        )
        gamma_start = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('public_domain_tls.py" paths', gamma_start)
        self.assertIn('--target "$QWQ_LOCAL_RELEASE_TARGET"', gamma_start)
        self.assertIn(
            'QWQ_LOCAL_RELEASE_TARGET="${QWQ_LOCAL_RELEASE_TARGET:-${QWQ_LOCAL_RELEASE_ENV}-local}"',
            gamma_start,
        )
        self.assertIn(
            'CONTENT_EMBEDDING_ENDPOINT: "${QWQ_COMPOSE_EMBEDDING_ENDPOINT:-}"',
            compose,
        )
        self.assertIn(
            'CONTENT_EMBEDDING_API_KEY: "${QWQ_COMPOSE_EMBEDDING_API_KEY:-}"',
            compose,
        )
        self.assertIn(
            'case "$WORKLOAD" in',
            gamma_start,
        )
        self.assertIn("  content-release)", gamma_start)
        self.assertIn("export_service_compose_environment", gamma_start)
        self.assertIn('export "$source_name"', gamma_start)
        self.assertIn("QWQ_COMPOSE_${source_name#LOCAL_GAMMA_}", gamma_start)
        self.assertNotIn("--write-report-account-backfill", gamma_start)

    def test_video_range_mime_preflight_precedes_patrol(self) -> None:
        commands = stackctl._selected_profile_commands(
            "gamma",
            "gamma-local",
            VerificationProfile.RELEASE,
            Path("/tmp/gamma-report"),
        )

        names = [item["name"] for item in commands]
        preflight_index = names.index("gamma-local-release-video-canary-preflight")
        patrol_index = names.index("gamma-local-environment-page-smoke")
        search_patrol_index = names.index("gamma-local-search-remote-patrol")
        self.assertLess(preflight_index, patrol_index)
        self.assertLess(patrol_index, search_patrol_index)
        self.assertTrue(commands[preflight_index]["stopOnFailure"])
        self.assertTrue(
            any(
                "verify_video_playback_canary.py" in value
                for value in commands[preflight_index]["argv"]
            ),
        )
        self.assertNotIn("seeded-media-surface", names)

        search_patrol = commands[search_patrol_index]
        self.assertEqual(
            search_patrol["argv"][search_patrol["argv"].index("--target") + 1],
            (
                "test/user_acceptance/journeys/cross_domain_search/"
                "cross_domain_search_journey__user_acceptance_test.dart"
            ),
        )
        self.assertNotIn("--video-playback-canary-work-id", search_patrol["argv"])

    def test_prod_hosted_patrol_requires_release_video_canary_preflight(self) -> None:
        command = stackctl._target_media_preflight_profile_command(
            "prod-hosted",
            Path("/tmp/prod-report"),
        )

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command["name"], "prod-hosted-release-video-canary-preflight")
        self.assertTrue(
            any("verify_video_playback_canary.py" in value for value in command["argv"])
        )
        self.assertIn("--report", command["argv"])
        self.assertEqual(
            command["reportPath"],
            "/tmp/prod-report/video-range-mime-preflight/report.json",
        )
        self.assertTrue(command["stopOnFailure"])

    def test_prod_sim_is_not_part_of_the_local_release_profile(self) -> None:
        readiness_path = Path(
            "/tmp/prod-runs/data-release/release-a/verify-a/release-readiness.json"
        )
        commands = stackctl._selected_profile_commands(
            "prod",
            "prod-sim",
            VerificationProfile.RELEASE,
            Path("/tmp/prod-report"),
            data_readiness_path=readiness_path,
        )

        self.assertNotIn("prod-sim-up", {item["name"] for item in commands})

    def test_prod_playback_canary_rejects_fixture_identity(self) -> None:
        args = self._args(
            env_name="prod-sim",
            runtime_env="prod",
            video_playback_canary_work_id="fixture_video_001",
        )

        with self.assertRaisesRegex(ValueError, "published release work"):
            smoke._validate_video_playback_canary_work_id(args, "prod")


if __name__ == "__main__":
    unittest.main()
