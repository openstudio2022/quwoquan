# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001.t3
from __future__ import annotations

import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from unittest import mock

import yaml

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib.external_provider_governance_lib import (
    compile_single_environment_bindings,
)
from quwoquan_ops.cli.lib.external_provider_governance_lib.derived_sources import (
    load_environment_bindings,
)
from quwoquan_ops.gate import verify_external_provider_governance as provider_gate

ROOT = Path(__file__).resolve().parents[4]


class ExternalProviderGovernanceContractTest(unittest.TestCase):
    def test_message_transport_roots_use_package_bound_generated_bindings(self) -> None:
        registry = governance.load_registry()
        self.assertEqual(provider_gate.message_transport_static_issues(registry), [])
        service_root = ROOT / "quwoquan_service" / "services"
        roots = sorted(service_root.glob("*/cmd/**/message_transport.go"))
        self.assertTrue(roots)
        for path in roots:
            source = path.read_text(encoding="utf-8")
            self.assertIn("CompiledBindingFor(", source, path)
            self.assertNotIn("ExternalProviderBindingFor(", source, path)

    def test_provider_runtime_has_one_package_bound_launch_track(self) -> None:
        sources = {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in provider_gate.PROVIDER_RUNTIME_SOURCE_REQUIREMENTS
        }
        self.assertEqual(
            provider_gate.provider_runtime_single_track_issues(sources),
            [],
        )

        stackctl_path = "quwoquan_ops/cli/commands/provider_runtime_binding.py"
        sources[stackctl_path] += "\nQWQ_DEBUG_SMS_SUBSTITUTE_ENABLED\n"
        self.assertTrue(
            any(
                "legacy Provider runtime selector is forbidden" in issue
                for issue in provider_gate.provider_runtime_single_track_issues(
                    sources
                )
            )
        )

    def test_generated_output_directory_is_not_a_service_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            services_root = Path(temporary)
            (services_root / "user-service").mkdir()
            (services_root / ".qwq_output").mkdir()

            with mock.patch.object(governance, "SERVICES_ROOT", services_root):
                self.assertEqual(
                    governance._service_roots(),
                    [services_root / "user-service"],
                )

    def test_governance_is_derived_without_registry_files(self) -> None:
        for relative in (
            "docs/external_service_registry.yaml",
            "docs/external_service_dependency_registry.md",
            "quwoquan_ops/environments/provider_conformance_manifest.yaml",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)

        registry = governance.load_registry()
        self.assertEqual(registry["schema"], "derived-external-capabilities")
        self.assertGreater(len(registry["capabilities"]), 0)
        self.assertGreaterEqual(
            len(registry["adapters"]),
            len(registry["capabilities"]),
        )

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

    def test_bindings_cover_exactly_four_environments_and_owned_capabilities(self) -> None:
        registry = governance.load_registry()
        bindings = governance.load_bindings()
        self.assertEqual(
            set(bindings["environments"]), {"alpha", "beta", "gamma", "prod"}
        )
        for environment, scope in bindings["environments"].items():
            self.assertTrue(scope, environment)
            for capability in registry["capabilities"]:
                owner_service = capability["service_id"]
                self.assertIn(
                    capability["capability_id"],
                    scope[owner_service],
                    (environment, owner_service, capability["capability_id"]),
                )
                for root in capability["binding_roots"]:
                    self.assertIn(root["descriptor_owner"], scope, environment)
                    if root["role"] != "owner":
                        self.assertNotIn(
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

    def test_non_prod_bindings_are_enabled_and_prod_forbids_substitutes(self) -> None:
        bindings = governance.load_bindings()
        registry = governance.load_registry()
        adapter_status = {
            (item["capability_id"], item["adapter_id"]): item["implementation_status"]
            for item in registry["adapters"]
        }
        self.assertEqual(
            governance.NONPROD_ENVIRONMENTS,
            ("alpha", "beta", "gamma"),
        )
        self.assertEqual(
            governance.RELEASE_ADAPTER_ENVIRONMENTS,
            ("prod",),
        )
        for environment in governance.NONPROD_ENVIRONMENTS:
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
                    self.assertIn(
                        adapter_status[(capability_id, binding["adapter"])],
                        governance.READY_IMPLEMENTATION_STATUSES | {"sandbox"},
                        (environment, service_id, capability_id),
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

    def test_enabled_binding_is_matched_by_an_enabled_capability_switch(self) -> None:
        """绑定为 enabled 却不打开能力开关，会让该能力在该环境静默缺席。

        这不是「环境按容量裁剪」——绑定已经声明这个环境要用该能力，开关关着
        只会让依赖它的读取面返回空结果，且没有任何失败信号。

        spec_ref: environment-topology-and-packaging GWT-001（四环境同一 composition）
        """
        # 能力标识 -> 决定它是否真正生效的服务配置开关。
        capability_switches = {
            "content.embedding.generation": (
                "content-service",
                "sys.content-service.embedding.enabled",
            ),
        }
        bindings = governance.load_bindings()
        missing: list[tuple[str, str, str]] = []
        for environment, service_map in bindings["environments"].items():
            for service_id, service_bindings in service_map.items():
                for capability_id, binding in service_bindings.items():
                    switch = capability_switches.get(capability_id)
                    if switch is None or switch[0] != service_id:
                        continue
                    if binding.get("state") != "enabled":
                        continue
                    config_path = (
                        ROOT
                        / "quwoquan_service"
                        / "services"
                        / service_id
                        / "environments"
                        / environment
                        / "config.yaml"
                    )
                    overrides = (
                        yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                    ).get("overrides") or {}
                    if overrides.get(switch[1]) is not True:
                        missing.append((environment, service_id, switch[1]))
        self.assertEqual(missing, [])

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

    def test_message_transport_owner_declares_fixed_observability_metrics(self) -> None:
        governance.load_registry.cache_clear()
        registry = governance.load_registry()
        runtime_transport = next(
            capability
            for capability in registry["capabilities"]
            if capability["capability_id"] == "runtime.message.transport"
        )
        self.assertEqual(
            tuple(runtime_transport.get("observability_metrics") or ()),
            governance.MESSAGE_TRANSPORT_REQUIRED_METRICS,
        )
        issues = governance.registry_issues(registry)
        self.assertFalse(
            any(
                "pending_lag/dead_letter/publish_p95/consume_p95" in issue.message
                for issue in issues
            )
        )

    def test_message_transport_p95_is_derived_from_histogram_samples(self) -> None:
        runtime_source = (
            ROOT
            / "quwoquan_service/runtime/messaging/redis_message_transport_binding.go"
        ).read_text(encoding="utf-8")
        rules_document = yaml.safe_load(
            (
                ROOT
                / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
            ).read_text(encoding="utf-8")
        )
        dashboard_source = yaml.safe_load(
            (
                ROOT
                / "quwoquan_ops/observability/monitoring/dashboards/l2_business_journey.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            provider_gate.message_transport_observability_issues(
                runtime_source,
                rules_document=rules_document,
                dashboard_source=dashboard_source,
            ),
            [],
        )

        gauge_source = runtime_source.replace(
            "messageTransportPublishLatency = promauto.NewHistogramVec",
            "messageTransportPublishLatency = promauto.NewGaugeVec",
            1,
        )
        self.assertTrue(
            any(
                "publish_duration_seconds must use HistogramVec" in issue
                for issue in provider_gate.message_transport_observability_issues(
                    gauge_source,
                    rules_document=rules_document,
                    dashboard_source=dashboard_source,
                )
            )
        )

        invalid_rules = deepcopy(rules_document)
        publish_rule = next(
            rule
            for group in invalid_rules["groups"]
            for rule in group["rules"]
            if rule.get("record") == "qwq_message_transport_publish_p95"
        )
        publish_rule["expr"] = (
            "qwq_message_transport_publish_duration_seconds_bucket"
        )
        self.assertTrue(
            any(
                "must calculate histogram_quantile(0.95" in issue
                for issue in provider_gate.message_transport_observability_issues(
                    runtime_source,
                    rules_document=invalid_rules,
                    dashboard_source=dashboard_source,
                )
            )
        )

    def test_shared_capability_use_is_local_and_cannot_shadow_owner_selection(self) -> None:
        governance.load_registry.cache_clear()
        registry = governance.load_registry()
        runtime_transport = next(
            capability
            for capability in registry["capabilities"]
            if capability["capability_id"] == "runtime.message.transport"
        )
        self.assertEqual(runtime_transport["owner"], "chat.chat.conversation")
        self.assertEqual(
            len(runtime_transport["binding_roots"]),
            len({root["root_id"] for root in runtime_transport["binding_roots"]}),
        )
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
                "integration-service",
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
        ] = {"state": "enabled"}
        issues = governance.binding_issues(registry, bindings)
        self.assertTrue(
            any(
                "consumer binding is generated from capability-use" in issue.message
                for issue in issues
            )
        )

    def test_phone_otp_consumer_is_bound_to_integration_owner_in_every_environment(self) -> None:
        registry = governance.load_registry()
        sms_otp = next(
            capability
            for capability in registry["capabilities"]
            if capability["capability_id"] == "identity.sms.otp"
        )
        self.assertEqual(
            sms_otp["owner"],
            "integration.external_integration.external_interaction",
        )
        self.assertEqual(
            {
                root["root_id"]
                for root in sms_otp["binding_roots"]
            },
            {
                "integration.external_integration.external_interaction",
                "user.account.authentication_challenge",
            },
        )
        self.assertEqual(
            [
                {
                    "port": "SmsDeliveryPort",
                    "operations": ["sendOtp"],
                    "scenes": ["phone_otp_delivery"],
                    "source": (
                        "quwoquan_service/services/user-service/contracts/"
                        "account/authentication_challenge/operations.yaml"
                    ),
                    "root": sms_otp["consumer_uses"][0]["root"],
                    "role": "use",
                }
            ],
            sms_otp["consumer_uses"],
        )

        bindings = governance.load_bindings()
        for environment in ("alpha", "beta", "gamma", "prod"):
            self.assertNotIn(
                "identity.sms.otp",
                bindings["environments"][environment]["user-service"],
            )
        compiled, issues = governance.load_and_compile()
        self.assertEqual(issues, [])
        for environment in ("alpha", "beta", "gamma", "prod"):
            self.assertEqual(
                compiled["selectedRootBindings"][environment][
                    "user.account.authentication_challenge"
                ]["identity.sms.otp"]["state"],
                compiled["selectedBindings"][environment]["identity.sms.otp"]["state"],
            )

    def test_compiler_and_composition_are_closed(self) -> None:
        compiled, issues = governance.load_and_compile()
        registry = governance.load_registry()
        self.assertEqual(issues, [])
        self.assertEqual(compiled["capabilityCount"], len(registry["capabilities"]))
        self.assertEqual(
            compiled["providerConformanceCapabilityCount"],
            len(compiled["providerConformanceCapabilityIds"]),
        )
        expected_conformance_capabilities = {
            capability_id
            for environment_bindings in compiled["selectedBindings"].values()
            for capability_id, binding in environment_bindings.items()
            if (
                binding["state"] != "not_required"
                and binding.get("adapter_id")
                and binding["adapter_id"]
                != governance.FIRST_PARTY_AUTHORITY_ADAPTER
            )
        }
        self.assertEqual(
            set(compiled["providerConformanceCapabilityIds"]),
            expected_conformance_capabilities,
        )
        # location.poi.search 已在四环境对齐为 not_required（nonprod 三环境必须
        # 与 prod 共享同一状态），与 route.read 一样保持在 conformance 集之外，
        # 待消费点落地再翻牌。
        self.assertNotIn(
            "location.poi.search", compiled["providerConformanceCapabilityIds"]
        )
        self.assertNotIn(
            "location.route.read", compiled["providerConformanceCapabilityIds"]
        )
        self.assertEqual(compiled["adapterCount"], len(registry["adapters"]))
        self.assertTrue(
            {
                "chat.conversation.membership.read",
                "circle.membership.self.read",
            }.issubset(compiled["capabilityOwners"])
        )
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
            descriptor_root_id="assistant.assistant.assistant_session",
        )
        self.assertIn('"runtime.message.transport"', assistant_transport)
        self.assertIn('RequiredRedisScenes: []string{', assistant_transport)
        self.assertIn('"general"', assistant_transport)
        self.assertIn("State                   string", assistant_transport)
        self.assertIn("EndpointEnvironmentKeys: map[string]string{}", assistant_transport)
        self.assertIn("if !ok {\n\t\treturn ExternalProviderBinding{}, false\n\t}", assistant_transport)

    def test_single_environment_compiler_is_candidate_scoped_and_environment_free_at_runtime(
        self,
    ) -> None:
        artifacts = {}
        for environment, target in (
            ("alpha", "alpha-local"),
            ("beta", "beta-local"),
            ("gamma", "gamma-local"),
            ("prod", "prod-hosted"),
        ):
            artifact = compile_single_environment_bindings(
                environment=environment,
                target=target,
                source_root=ROOT,
            )
            artifacts[environment] = artifact
            self.assertNotIn("selectedBindings", artifact)
            self.assertNotIn("selectedRootBindings", artifact)
            self.assertNotIn("readiness", artifact.get("bindings", {}))
            for other in {"alpha", "beta", "gamma", "prod"} - {environment}:
                self.assertNotIn(
                    other,
                    {artifact["environment"], artifact["target"]},
                )
            for generated in artifact["goSources"]:
                source = generated["source"]
                self.assertIn(
                    "func CompiledBindingFor(capabilityID string)",
                    source,
                )
                self.assertNotIn("environment, capabilityID", source)
                self.assertNotIn("func ExternalProviderBindingFor(", source)
                self.assertNotIn("map[string]map[string]ExternalProviderBinding", source)
        self.assertEqual(
            len(
                {
                    artifact["manifest"]["manifestDigest"]
                    for artifact in artifacts.values()
                }
            ),
            4,
        )

    def test_single_environment_compiler_does_not_read_other_environment_configs(
        self,
    ) -> None:
        original_read_text = Path.read_text

        def reject_other_environment(
            path: Path,
            *args: object,
            **kwargs: object,
        ) -> str:
            if (
                path.name == "config.yaml"
                and "environments" in path.parts
                and any(other in path.parts for other in ("beta", "gamma", "prod"))
            ):
                raise AssertionError(f"single-environment compile crossed scope: {path}")
            return original_read_text(path, *args, **kwargs)

        governance.load_registry.cache_clear()
        governance.load_conformance_manifest.cache_clear()
        load_environment_bindings.cache_clear()
        with mock.patch.object(Path, "read_text", reject_other_environment):
            artifact = compile_single_environment_bindings(
                environment="alpha",
                target="alpha-local",
                source_root=ROOT,
            )
        self.assertEqual(artifact["environment"], "alpha")

    def test_single_environment_compiler_concurrent_results_do_not_overwrite(self) -> None:
        requests = (
            ("alpha", "alpha-local"),
            ("beta", "beta-local"),
            ("gamma", "gamma-local"),
            ("prod", "prod-hosted"),
        )
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(
                    compile_single_environment_bindings,
                    environment=environment,
                    target=target,
                    source_root=ROOT,
                )
                for environment, target in requests
            ]
            artifacts = [future.result() for future in futures]
        self.assertEqual(
            [(item["environment"], item["target"]) for item in artifacts],
            list(requests),
        )
        self.assertEqual(
            len({item["manifest"]["manifestDigest"] for item in artifacts}),
            4,
        )

    def test_prod_targets_have_distinct_binding_artifact_identities(self) -> None:
        prod_sim = compile_single_environment_bindings(
            environment="prod",
            target="prod-sim",
            source_root=ROOT,
        )
        prod_hosted = compile_single_environment_bindings(
            environment="prod",
            target="prod-hosted",
            source_root=ROOT,
        )
        self.assertEqual(prod_sim["bindings"], prod_hosted["bindings"])
        self.assertNotEqual(
            prod_sim["manifest"]["manifestDigest"],
            prod_hosted["manifest"]["manifestDigest"],
        )

    def test_single_environment_compiler_reads_capsule_after_live_workspace_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capsule_root = Path(temporary) / "capsule"
            shutil.copytree(
                ROOT / "quwoquan_service",
                capsule_root / "quwoquan_service",
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".qwq_output",
                    "generated",
                    "tests",
                ),
            )
            shutil.copytree(
                ROOT / "quwoquan_ops" / "external",
                capsule_root / "quwoquan_ops" / "external",
            )
            baseline = compile_single_environment_bindings(
                environment="alpha",
                target="alpha-local",
                source_root=capsule_root,
            )
            governance.load_registry.cache_clear()
            governance.load_conformance_manifest.cache_clear()
            load_environment_bindings.cache_clear()
            live_root = ROOT.resolve()
            original_read_text = Path.read_text

            def reject_live_workspace_read(
                path: Path,
                *args: object,
                **kwargs: object,
            ) -> str:
                if path.resolve().is_relative_to(live_root):
                    raise AssertionError(f"capsule compile read live workspace: {path}")
                return original_read_text(path, *args, **kwargs)

            with mock.patch.object(Path, "read_text", reject_live_workspace_read):
                repeated = compile_single_environment_bindings(
                    environment="alpha",
                    target="alpha-local",
                    source_root=capsule_root,
                )
            self.assertEqual(repeated, baseline)

if __name__ == "__main__":
    unittest.main()
