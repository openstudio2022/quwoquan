from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

import yaml

from quwoquan_ops.cli.lib import external_provider_governance as governance


ROOT = Path(__file__).resolve().parents[3]


class ExternalProviderGovernanceContractTest(unittest.TestCase):
    def test_governance_is_derived_without_registry_files(self) -> None:
        for relative in (
            "docs/external_service_registry.yaml",
            "docs/external_service_dependency_registry.md",
            "quwoquan_ops/environments/provider_conformance_manifest.yaml",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)

        registry = governance.load_registry()
        self.assertEqual(registry["schema"], "derived-external-capabilities")
        self.assertEqual(len(registry["capabilities"]), 14)
        self.assertGreaterEqual(len(registry["adapters"]), 14)

    def test_capability_identity_and_owner_come_from_object_operations(self) -> None:
        registry = governance.load_registry()
        capability_ids = set()
        for capability in registry["capabilities"]:
            capability_id = capability["capability_id"]
            self.assertNotIn(capability_id, capability_ids)
            capability_ids.add(capability_id)
            self.assertTrue(capability["canonical_port"])
            self.assertTrue(capability["operations"])
            self.assertTrue(capability["conformance_profile"])
            self.assertTrue(capability["binding_roots"])
            self.assertTrue((ROOT / capability["source"]).is_file())

        roots = {
            root["root_id"]: root["descriptor_output"]
            for capability in registry["capabilities"]
            for root in capability["binding_roots"]
        }
        self.assertEqual(
            roots["integration.external_integration.external_interaction"],
            "quwoquan_service/services/integration-service/generated/external_integration/external_interaction/external_provider_bindings.g.go",
        )
        self.assertEqual(
            roots["integration.external_integration.location"],
            "quwoquan_service/services/integration-service/generated/external_integration/location/external_provider_bindings.g.go",
        )

    def test_bindings_cover_exactly_four_environments_and_all_capabilities(self) -> None:
        registry = governance.load_registry()
        bindings = governance.load_bindings()
        self.assertEqual(
            set(bindings["environments"]), {"alpha", "beta", "gamma", "prod"}
        )
        for environment, scope in bindings["environments"].items():
            self.assertTrue(scope, environment)
            for capability in registry["capabilities"]:
                for root in capability["binding_roots"]:
                    self.assertIn(root["descriptor_owner"], scope, environment)
                    self.assertIn(
                        capability["capability_id"],
                        scope[root["descriptor_owner"]],
                        (environment, root),
                    )

    def test_prod_rejects_mock_or_fixture_adapter(self) -> None:
        bindings = governance.load_bindings()
        for service_id, service_bindings in bindings["environments"]["prod"].items():
            for capability_id, binding in service_bindings.items():
                if binding["state"] == "not_required":
                    continue
                if "adapter" not in binding:
                    continue
                adapter = binding["adapter"]
                self.assertFalse(
                    governance.is_prod_forbidden_adapter(adapter),
                    (service_id, capability_id, adapter),
                )

    def test_all_non_prod_environments_use_local_substitutes(self) -> None:
        bindings = governance.load_bindings()
        self.assertEqual(
            governance.SUBSTITUTE_ENVIRONMENTS,
            ("alpha", "beta", "gamma"),
        )
        self.assertEqual(
            governance.RELEASE_ADAPTER_ENVIRONMENTS,
            ("prod",),
        )
        for environment in governance.SUBSTITUTE_ENVIRONMENTS:
            for service_id, service_bindings in bindings["environments"][environment].items():
                for capability_id, binding in service_bindings.items():
                    if binding.get("state") == "not_required":
                        continue
                    if "adapter" not in binding:
                        continue
                    self.assertEqual(
                        binding["state"],
                        "enabled",
                        (environment, service_id, capability_id),
                    )
                    self.assertTrue(
                        governance.is_local_substitute_adapter(binding["adapter"]),
                        (environment, service_id, capability_id, binding["adapter"]),
                    )

        for environment in governance.RELEASE_ADAPTER_ENVIRONMENTS:
            for service_id, service_bindings in bindings["environments"][environment].items():
                for capability_id, binding in service_bindings.items():
                    if binding.get("state") == "not_required" or "adapter" not in binding:
                        continue
                    self.assertEqual(
                        binding["state"],
                        "enabled",
                        (environment, service_id, capability_id),
                    )
                    self.assertFalse(
                        governance.is_prod_forbidden_adapter(binding["adapter"]),
                        (environment, service_id, capability_id, binding["adapter"]),
                    )

    def test_adapter_paths_are_scanned_from_real_sources(self) -> None:
        for adapter in governance.load_registry()["adapters"]:
            self.assertTrue(adapter["implementation_path"], adapter["adapter_id"])
            source = ROOT / adapter["implementation_path"]
            self.assertTrue(source.exists(), adapter["adapter_id"])
            self.assertTrue(
                source.is_file() or any(source.rglob("*.go")),
                adapter["adapter_id"],
            )

    def test_first_party_tag_service_is_not_external_provider_governance(self) -> None:
        capability_id = "tag.taxonomy.active_leaf_validation"
        registry = governance.load_registry()
        self.assertNotIn(
            capability_id,
            {
                capability["capability_id"]
                for capability in registry["capabilities"]
            },
        )
        schema_path = (
            ROOT
            / "quwoquan_service/services/content-service/config/schema.yaml"
        )
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        timeout_config = next(
            item
            for item in schema["configs"]
            if item["key"] == "sys.content-service.tag_service.timeout_ms"
        )
        self.assertGreater(timeout_config["default"], 0)
        for environment in ("alpha", "beta", "gamma", "prod"):
            path = (
                ROOT
                / "quwoquan_service/services/content-service/environments"
                / environment
                / "config.yaml"
            )
            config = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertNotIn(capability_id, config["externalBindings"])
            overrides = config["overrides"]
            self.assertTrue(overrides["sys.content-service.tag_service.url"])

    def test_manual_registry_input_is_forbidden(self) -> None:
        with self.assertRaisesRegex(ValueError, "manual external provider registries"):
            governance.load_registry(ROOT / "registry.yaml")

    def test_binding_unknown_fields_fail_closed(self) -> None:
        registry = governance.load_registry()
        bindings = deepcopy(governance.load_bindings())
        bindings["environments"]["prod"]["chat-service"][
            "runtime.message.transport"
        ]["readiness"] = "ready"
        issues = governance.binding_issues(registry, bindings)
        self.assertTrue(
            any(
                issue.location.endswith("runtime.message.transport")
                and "unsupported fields" in issue.message
                for issue in issues
            )
        )

    def test_shared_capability_use_is_local_and_cannot_shadow_owner_selection(self) -> None:
        registry = governance.load_registry()
        runtime_transport = next(
            capability
            for capability in registry["capabilities"]
            if capability["capability_id"] == "runtime.message.transport"
        )
        self.assertEqual(runtime_transport["owner"], "chat.chat.conversation")
        self.assertEqual(len(runtime_transport["binding_roots"]), 12)
        self.assertEqual(
            {
                root["descriptor_owner"]
                for root in runtime_transport["binding_roots"]
            },
            {
                "assistant-service",
                "chat-service",
                "circle-service",
                "content-service",
                "entity-service",
                "notification-service",
                "product-ops-service",
                "realtime-gateway",
                "rtc-service",
                "search-service",
                "tag-service",
                "user-service",
            },
        )
        self.assertTrue(runtime_transport["consumer_uses"])
        self.assertTrue(
            all(
                set(use) == {"port", "operations", "scenes", "source", "root", "role"}
                for use in runtime_transport["consumer_uses"]
            )
        )

        bindings = deepcopy(governance.load_bindings())
        bindings["environments"]["beta"]["assistant-service"][
            "runtime.message.transport"
        ]["adapter"] = "infra.redis.message_transport"
        issues = governance.binding_issues(registry, bindings)
        self.assertTrue(
            any("consumer binding may only declare local state" in issue.message for issue in issues)
        )

        bindings = deepcopy(governance.load_bindings())
        bindings["environments"]["beta"]["assistant-service"][
            "runtime.message.transport"
        ]["state"] = "blocked"
        issues = governance.binding_issues(registry, bindings)
        self.assertTrue(
            any("consumer local state must match" in issue.message for issue in issues)
        )

    def test_compiler_and_composition_are_closed(self) -> None:
        compiled, issues = governance.load_and_compile()
        self.assertEqual(issues, [])
        self.assertEqual(compiled["capabilityCount"], 14)
        self.assertEqual(compiled["adapterCount"], 29)
        self.assertEqual(
            governance.composition_issues(governance.load_registry(), compiled), []
        )
        integration_location = governance.render_go_bindings(
            compiled,
            descriptor_owner="integration-service",
            descriptor_root_id="integration.external_integration.location",
        )
        self.assertIn(
            "from integration/external_integration/location/operations.yaml",
            integration_location,
        )
        self.assertIn('"integration.location.lookup"', integration_location)
        self.assertNotIn('"identity.sms.otp"', integration_location)
        assistant_transport = governance.render_go_bindings(
            compiled,
            descriptor_owner="assistant-service",
            descriptor_root_id="assistant.assistant.assistant_conversation",
        )
        self.assertIn('"runtime.message.transport"', assistant_transport)
        self.assertIn('RequiredRedisScenes: []string{', assistant_transport)
        self.assertIn('"general"', assistant_transport)


if __name__ == "__main__":
    unittest.main()
