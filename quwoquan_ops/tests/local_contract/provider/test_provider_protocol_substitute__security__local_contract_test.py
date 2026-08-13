from __future__ import annotations

from pathlib import Path
import unittest

from quwoquan_ops.cli.lib.provider_endpoint_contract import (
    load_provider_endpoint_environment,
)


ROOT = Path(__file__).resolve().parents[4]
WORKLOAD = ROOT / "quwoquan_ops/external/provider-protocol-substitute"


class ProviderProtocolSubstituteSecurityTest(unittest.TestCase):
    def test_substitute_is_external_and_prod_bindings_cannot_reach_it(self) -> None:
        self.assertTrue((WORKLOAD / "deploy/compose.yaml").is_file())
        self.assertFalse((WORKLOAD / "environments/prod").exists())
        self.assertFalse(
            (
                ROOT
                / "quwoquan_service/services/integration-service/cmd/api/"
                "nonprod_provider_substitute.go"
            ).exists()
        )

        for config in (
            ROOT / "quwoquan_service/services"
        ).glob("*/environments/prod/config.yaml"):
            source = config.read_text(encoding="utf-8")
            self.assertNotIn("provider-protocol-substitute", source, config)
            self.assertNotIn("protocol_substitute", source, config)

        prod_renderer = (
            ROOT / "quwoquan_ops/cli/prod/render_prod_plane_stack.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("provider-protocol-substitute", prod_renderer)
        self.assertNotIn("debug-provider-substitute", prod_renderer)
        generated = (
            ROOT
            / "quwoquan_service/services/integration-service/generated/"
            "external_integration/external_interaction/external_provider_bindings.g.go"
        ).read_text(encoding="utf-8")
        prod_scope = generated.split('"prod": {', 1)[1]
        self.assertNotIn("ext.push.protocol_substitute", prod_scope)
        for compose in (
            ROOT / "quwoquan_service/services"
        ).glob("*/deploy/compose.yaml"):
            self.assertNotIn(
                "provider-protocol-substitute/ca.crt",
                compose.read_text(encoding="utf-8"),
                compose,
            )
        debug_compose = (WORKLOAD / "deploy/compose.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("PROVIDER_SUBSTITUTE_TLS_CERT_FILE", debug_compose)
        self.assertIn("/usr/local/bin/provider-protocol-substitute", debug_compose)
        self.assertIn('"healthcheck"', debug_compose)
        self.assertNotIn("--no-check-certificate", debug_compose)
        healthcheck_source = (
            WORKLOAD
            / "cmd/provider-protocol-substitute/main.go"
        ).read_text(encoding="utf-8")
        self.assertIn("https://127.0.0.1:18089/healthz", healthcheck_source)
        self.assertIn(
            "/run/secrets/provider-protocol-substitute/ca.crt",
            healthcheck_source,
        )
        healthcheck_impl = (
            WORKLOAD
            / "cmd/provider-protocol-substitute/healthcheck.go"
        ).read_text(encoding="utf-8")
        self.assertIn("tls.VersionTLS13", healthcheck_impl)
        self.assertNotIn("InsecureSkipVerify", healthcheck_impl)
        local_runtime = (
            ROOT
            / "quwoquan_ops/environments/compose/"
            "docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("internal: true", local_runtime)
        # Host/Colima publish plane must stay separate from the internal mesh.
        self.assertIn("\n  edge:\n", local_runtime)
        self.assertIn("networks:\n      - default\n      - edge", local_runtime)

    def test_endpoint_values_are_topology_and_workload_contract_derived(self) -> None:
        endpoints = load_provider_endpoint_environment()
        self.assertEqual(
            endpoints["ASSISTANT_MODEL_COMPLETION_URL"],
            "https://provider-protocol-substitute:18089/v1/chat/completions",
        )
        self.assertEqual(
            endpoints["INTEGRATION_SMS_ENDPOINT"],
            "https://sms-provider-substitute:9443/v1/provider/sms/send",
        )
        self.assertEqual(
            endpoints["RTC_MEDIA_CONNECTION_URL"],
            "http://livekit-sfu:7880",
        )

        credentials = (
            ROOT / "quwoquan_ops/cli/lib/local_provider_credentials.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("http://integration-service:18089", credentials)
        self.assertNotIn("https://sms-provider-substitute:9443", credentials)

    def test_first_party_runtime_contains_clients_not_substitute_responses(self) -> None:
        integration_source = (
            ROOT / "quwoquan_service/services/integration-service"
        )
        user_source = ROOT / "quwoquan_service/services/user-service"
        for root in (integration_source, user_source):
            for source_file in root.rglob("*.go"):
                if "_test.go" in source_file.name or "generated" in source_file.parts:
                    continue
                source = source_file.read_text(encoding="utf-8")
                self.assertNotIn("LocalRecorderPushProvider", source, source_file)
                self.assertNotIn("ProtocolFixtureLocationProvider", source, source_file)
                self.assertNotIn(
                    "ProtocolFixtureFederatedIdentityVerifier",
                    source,
                    source_file,
                )


if __name__ == "__main__":
    unittest.main()
