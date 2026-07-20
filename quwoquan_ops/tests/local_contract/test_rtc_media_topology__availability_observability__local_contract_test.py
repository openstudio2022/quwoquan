from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.environment_topology import (
    URL_FIELDS,
    load_environment_topology,
)
from quwoquan_ops.cli.print_local_port_profile import ENV_EXPORTS
from quwoquan_ops.cli.stackctl import (
    _expected_local_roles,
    _service_health_checks_for_target,
)


class RtcMediaTopologyContractTest(unittest.TestCase):
    def test_gamma_realtime_media_ports_are_manifest_driven_and_collision_free(self) -> None:
        ports = profile_ports(load_port_manifest(), "gamma-local")
        roles = (
            "search-service",
            "realtime-gateway",
            "rtc-service",
            "livekit-http",
            "livekit-rtc-tcp",
            "livekit-rtc-udp",
            "livekit-metrics",
            "coturn",
        )
        allocated = [ports[role] for role in roles]
        self.assertEqual(len(allocated), len(set(allocated)))

        exports = ENV_EXPORTS["gamma-local"]
        self.assertEqual(exports["LOCAL_GAMMA_LIVEKIT_HTTP_PORT"], "livekit-http")
        self.assertEqual(exports["LOCAL_GAMMA_LIVEKIT_RTC_UDP_PORT"], "livekit-rtc-udp")
        self.assertEqual(exports["LOCAL_GAMMA_LIVEKIT_METRICS_PORT"], "livekit-metrics")
        self.assertEqual(exports["LOCAL_GAMMA_RTC_PORT"], "rtc-service")
        self.assertEqual(exports["LOCAL_GAMMA_REALTIME_PORT"], "realtime-gateway")

    def test_livekit_config_exposes_single_udp_mux_and_prometheus(self) -> None:
        config = (
            ROOT
            / "quwoquan_service/services/livekit-sfu/deploy/kustomize/base/livekit.yaml"
        ).read_text(encoding="utf-8")
        compose = (
            ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        compose_model = load_json_yaml(
            ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        )

        self.assertIn("prometheus_port: 6789", config)
        self.assertIn("udp_port: 7882", config)
        self.assertIn("max_participants: 32", config)
        self.assertIn("${LOCAL_GAMMA_LIVEKIT_RTC_UDP_PORT:-19160}:7882/udp", compose)
        self.assertIn("${LOCAL_GAMMA_LIVEKIT_METRICS_PORT:-19170}:6789", compose)
        self.assertIn(
            "livekit/livekit-server:v1.7.2@sha256:"
            "27d72fa264baa4db4e635b3b6df12d185b4a95fee5f2ddce03e06d150d599e0e",
            compose,
        )
        self.assertIn(
            "coturn/coturn:4.6-alpine@sha256:"
            "e2bca2f79a4269d7240de5872ab60a9305013ad37296d2acf14f9510874346be",
            compose,
        )
        self.assertIn(
            'LIVEKIT_URL: "${LOCAL_GAMMA_LIVEKIT_PUBLIC_URL:-'
            'wss://gamma-rtc.quwoquan-env.test:19000}"',
            compose,
        )
        self.assertNotIn("LIVEKIT_URL: ws://livekit-sfu:7880", compose)
        for service_name in ("realtime-gateway", "rtc-service"):
            service = compose_model["services"][service_name]
            self.assertNotIn("build", service)
            self.assertIn("fixed", service["image"])

    def test_rtc_public_base_is_a_canonical_topology_field(self) -> None:
        topology = load_environment_topology()
        self.assertIn("rtc", URL_FIELDS)
        self.assertEqual(
            topology["targets"]["gamma-local"]["publicBases"]["rtc"],
            "wss://gamma-rtc.quwoquan-env.test:19000",
        )
        self.assertEqual(
            topology["targets"]["prod-hosted"]["publicBases"]["rtc"],
            "wss://rtc.quwoquan.com",
        )

    def test_gamma_health_evidence_covers_realtime_rtc_and_livekit(self) -> None:
        roles = set(_expected_local_roles("gamma-local"))
        self.assertTrue(
            {
                "realtime-gateway",
                "rtc-service",
                "livekit-http",
                "livekit-rtc-tcp",
                "livekit-metrics",
                "coturn",
            }.issubset(roles)
        )
        checks = {
            check["name"]: check["url"]
            for check in _service_health_checks_for_target("gamma-local")
        }
        self.assertTrue(checks["realtime-gateway"].endswith(":19340/healthz"))
        self.assertTrue(checks["rtc-service"].endswith(":19350/healthz"))
        self.assertTrue(checks["livekit-http"].endswith(":19140/"))
        self.assertTrue(checks["livekit-metrics"].endswith(":19170/metrics"))


if __name__ == "__main__":
    unittest.main()
