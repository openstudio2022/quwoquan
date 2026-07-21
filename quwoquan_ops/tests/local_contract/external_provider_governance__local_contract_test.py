from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import external_provider_governance as governance


def test_registry_compiles_into_single_environment_selection_and_readiness() -> None:
    compiled, issues = governance.load_and_compile()

    assert issues == []
    assert compiled["capabilityCount"] >= 20
    assert compiled["adapterCount"] >= 50
    sms_readiness = compiled["readiness"]["prod"]["identity.sms.otp"]
    assert sms_readiness == {
        "required": True,
        "state": "blocked",
        "adapter_id": "ext.sms.aliyun",
        "adapter_preflight_ready": False,
        "adapter_ready": False,
        "capability_ready": False,
    }


def test_registry_rejects_literal_provider_endpoint() -> None:
    registry = deepcopy(governance.load_registry())
    registry["adapters"][0]["endpoint_ref"] = "https://credential-leak.invalid"

    issues = governance.registry_issues(registry)

    assert any(
        issue.location == "registry.adapters[0].endpoint_ref"
        and "literal endpoints are forbidden" in issue.message
        for issue in issues
    )


def test_provider_governance_sources_reject_versioned_contract_tracks() -> None:
    registry = deepcopy(governance.load_registry())
    registry["version"] = 2
    bindings = deepcopy(governance.load_bindings())
    bindings["schemaVersion"] = 1
    manifest = deepcopy(governance.load_conformance_manifest())
    manifest["version"] = 1

    registry_issues = governance.registry_issues(registry)
    binding_issues = governance.binding_issues(governance.load_registry(), bindings)
    manifest_issues = governance.conformance_manifest_issues(
        governance.load_registry(),
        manifest,
    )

    assert any("versioned field 'version' is forbidden" in issue.message for issue in registry_issues)
    assert any("versioned field 'schemaVersion' is forbidden" in issue.message for issue in binding_issues)
    assert any("versioned field 'version' is forbidden" in issue.message for issue in manifest_issues)


def test_implemented_sdk_adapters_register_the_real_boundary_and_dependency() -> None:
    registry = governance.load_registry()
    adapters = {
        adapter["adapter_id"]: adapter
        for adapter in registry["adapters"]
        if isinstance(adapter, dict)
    }

    assert adapters["ext.storage.s3_oss_media"]["implementation_path"].endswith(
        "runtime/media/s3_presigner.go"
    )
    assert "go:github.com/aws/aws-sdk-go-v2/service/s3" in adapters[
        "ext.storage.s3_oss_media"
    ]["sdk_dependencies"]
    assert "go:github.com/aliyun/aliyun-log-go-sdk" in adapters[
        "ext.observability.aliyun_sls"
    ]["sdk_dependencies"]
    assert adapters["cap.auth.one_tap_method_channel"]["sdk_dependencies"] == [
        "android:vendor/commercial_auth/aliyun/android",
        "ios:pod:QWQVendorAliyunPNVS",
    ]
    assert adapters["cap.os.video_editing"]["sdk_dependencies"] == [
        "pub:video_thumbnail",
        "ios:AVFoundation",
    ]
    assert adapters["cap.auth.native_bridge_social"]["implementation_path"].endswith(
        "core/platform/native_bridge.dart"
    )
    assert adapters["dev.cursor_sdk_api"]["sdk_dependencies"] == [
        "py:cursor-sdk==0.1.9"
    ]


def test_assistant_provider_adapters_bind_to_typed_infrastructure_ports() -> None:
    registry = governance.load_registry()
    capabilities = {
        capability["capability_id"]: capability
        for capability in registry["capabilities"]
        if isinstance(capability, dict)
    }
    adapters = {
        adapter["adapter_id"]: adapter
        for adapter in registry["adapters"]
        if isinstance(adapter, dict)
    }

    assert capabilities["assistant.model.generation"]["canonical_port"] == (
        "assistant.application.ModelCompletionProvider"
    )
    assert capabilities["assistant.public.search"]["canonical_port"] == (
        "assistant.application.PublicSearchProvider"
    )
    assert capabilities["assistant.weather.forecast"]["canonical_port"] == (
        "assistant.application.WeatherProvider"
    )
    assert capabilities["assistant.finance.quote"]["canonical_port"] == (
        "assistant.application.FinanceProvider"
    )
    assert "assistant.tool.data" not in capabilities
    assert adapters["ext.llm.xiaomi_mimo"]["implementation_path"].endswith(
        "internal/infrastructure/modelprovider/client.go"
    )
    assert adapters["ext.search.duckduckgo_html"]["implementation_path"].endswith(
        "internal/infrastructure/publicsearch/client.go"
    )
    assert adapters["ext.finance.yahoo_chart"]["implementation_path"].endswith(
        "internal/infrastructure/finance/client.go"
    )
    assert adapters["ext.weather.open_meteo"]["implementation_path"].endswith(
        "internal/infrastructure/weather/client.go"
    )
    assert "ext.weather.open_meteo_geocoding" not in adapters
    assert "ext.weather.open_meteo_forecast" not in adapters


def test_assistant_bindings_compile_to_fixed_adapter_descriptors() -> None:
    compiled, issues = governance.load_and_compile()

    assert issues == []
    for environment in ("beta", "gamma", "prod"):
        selected = compiled["selectedBindings"][environment]
        assert selected["assistant.model.generation"] == {
            "state": "blocked",
            "adapter_id": "ext.llm.xiaomi_mimo",
            "endpoint_ref": "environment_binding:assistant.model",
            "secret_refs": ["runtime_secret:ASSISTANT_MODEL_API_KEY"],
            "endpoint_envs": {"completion": "ASSISTANT_MODEL_COMPLETION_URL"},
            "timeout_ms": 60000,
        }
        assert selected["assistant.public.search"]["adapter_id"] == "ext.search.duckduckgo_html"
        assert selected["assistant.weather.forecast"]["adapter_id"] == "ext.weather.open_meteo"
        assert selected["assistant.finance.quote"]["adapter_id"] == "ext.finance.yahoo_chart"
        for capability_id in (
            "assistant.public.search",
            "assistant.weather.forecast",
            "assistant.finance.quote",
        ):
            binding = selected[capability_id]
            assert binding["state"] == "blocked"
            assert binding["timeout_ms"] == 10000
            assert binding["endpoint_envs"]

    rendered = governance.render_go_bindings(
        compiled,
        descriptor_owner="assistant-service",
    )
    assert "ProviderConfig" not in rendered
    assert '"ext.llm.xiaomi_mimo"' in rendered
    assert '"assistant.model.generation"' in rendered
    assert '"assistant.public.search"' not in rendered


def test_assistant_binding_requires_endpoint_keys_and_timeout() -> None:
    registry = governance.load_registry()
    bindings = deepcopy(governance.load_bindings())
    binding = next(
        item
        for item in bindings["environments"]["beta"]["capabilities"]
        if item["capability_id"] == "assistant.public.search"
    )
    binding.pop("endpoint_envs")
    binding.pop("timeout_ms")

    issues = governance.binding_issues(registry, bindings)

    assert any(
        issue.location.endswith(".endpoint_envs")
        and "assistant bindings must declare" in issue.message
        for issue in issues
    )
    assert any(
        issue.location.endswith(".timeout_ms")
        and "assistant bindings must declare" in issue.message
        for issue in issues
    )


def test_content_embedding_adapter_registers_real_port_sdk_and_bindings() -> None:
    registry = governance.load_registry()
    capabilities = {
        capability["capability_id"]: capability
        for capability in registry["capabilities"]
        if isinstance(capability, dict)
    }
    adapters = {
        adapter["adapter_id"]: adapter
        for adapter in registry["adapters"]
        if isinstance(adapter, dict)
    }

    assert capabilities["content.embedding.generation"]["canonical_port"] == (
        "content.embedding.EmbeddingGateway"
    )
    assert capabilities["content.embedding.generation"]["required_environments"] == [
        "beta",
        "gamma",
        "prod",
    ]
    adapter = adapters["ext.embed.openai_compatible"]
    assert adapter["implementation_path"].endswith(
        "internal/infrastructure/embedding/openai_compatible_gateway.go"
    )
    assert adapter["implementation_status"] == "implemented_fail_closed"
    assert adapter["allowed_environments"] == ["beta", "gamma", "prod"]
    assert adapter["sdk_dependencies"] == ["go:stdlib/net/http"]

    bindings = governance.load_bindings()
    for environment in ("beta", "gamma", "prod"):
        binding = next(
            binding
            for binding in bindings["environments"][environment]["capabilities"]
            if binding["capability_id"] == "content.embedding.generation"
        )
        assert binding == {
            "capability_id": "content.embedding.generation",
            "state": "enabled",
            "adapter_id": "ext.embed.openai_compatible",
            "endpoint_ref": "environment_binding:content.embedding",
            "secret_refs": ["runtime_secret:CONTENT_EMBEDDING_API_KEY"],
            "endpoint_envs": {"endpoint": "CONTENT_EMBEDDING_ENDPOINT"},
            "timeout_ms": 10000,
        }


def test_release_capabilities_have_root_scoped_descriptors_and_static_consumption() -> None:
    registry = governance.load_registry()
    compiled, issues = governance.load_and_compile()

    assert issues == []
    assert governance.composition_issues(registry, compiled) == []
    release_capabilities = {
        capability["capability_id"]: capability
        for capability in registry["capabilities"]
        if isinstance(capability, dict) and capability["required_environments"]
    }
    assert release_capabilities
    for capability_id, capability in release_capabilities.items():
        assert "composition" not in capability
        assert capability["binding_scope"] in {
            "root_composed",
            "shared_multi_consumer",
        }
        roots = capability["binding_roots"]
        assert roots
        assert compiled["capabilityBindingRoots"][capability_id] == roots
        for descriptor_owner in {root["descriptor_owner"] for root in roots}:
            rendered = governance.render_go_bindings(
                compiled,
                descriptor_owner=descriptor_owner,
            )
            assert (
                f'const ExternalProviderBindingOwner = "{descriptor_owner}"' in rendered
            )
            assert f'"{capability_id}"' in rendered


def test_release_binding_roots_are_single_or_shared_and_deduplicated() -> None:
    registry = governance.load_registry()
    release_capabilities = {
        capability["capability_id"]: capability
        for capability in registry["capabilities"]
        if isinstance(capability, dict) and capability["required_environments"]
    }

    for capability in release_capabilities.values():
        roots = capability["binding_roots"]
        root_ids = [root["root_id"] for root in roots]
        assert len(root_ids) == len(set(root_ids))
        if capability["binding_scope"] == "root_composed":
            assert len(roots) == 1
        else:
            assert capability["binding_scope"] == "shared_multi_consumer"
            assert len(roots) > 1
            for root in roots:
                assert root["usage"]
                assert root["required_redis_scenes"]

    duplicated_registry = deepcopy(registry)
    shared_capability = next(
        capability
        for capability in duplicated_registry["capabilities"]
        if capability["capability_id"] == "runtime.message.transport"
    )
    duplicate_root_index = len(shared_capability["binding_roots"])
    shared_capability["binding_roots"].append(
        deepcopy(shared_capability["binding_roots"][0])
    )

    issues = governance.registry_issues(duplicated_registry)

    assert any(
        issue.location.endswith(f".binding_roots[{duplicate_root_index}].root_id")
        and "must be unique" in issue.message
        for issue in issues
    )


def test_shared_redis_binding_projects_to_each_descriptor_owner() -> None:
    registry = governance.load_registry()
    compiled, issues = governance.load_and_compile()

    assert issues == []
    runtime_message_transport = next(
        capability
        for capability in registry["capabilities"]
        if capability["capability_id"] == "runtime.message.transport"
    )
    assert runtime_message_transport["binding_scope"] == "shared_multi_consumer"
    assert {
        root["root_id"] for root in runtime_message_transport["binding_roots"]
    } == {
        "assistant-service-api",
        "assistant-service-seed",
        "chat-service-api",
        "circle-service-api",
        "content-service-api",
        "entity-service-api",
        "notification-service-api",
        "product-ops-service-api",
        "realtime-gateway-api",
        "rtc-service-api",
        "search-service-api",
        "user-service-api",
    }
    descriptor_owners = {
        root["descriptor_owner"]
        for root in runtime_message_transport["binding_roots"]
    }
    assert len(descriptor_owners) > 1
    selected_adapter = compiled["selectedBindings"]["prod"]["runtime.message.transport"][
        "adapter_id"
    ]
    for descriptor_owner in descriptor_owners:
        rendered = governance.render_go_bindings(
            compiled,
            descriptor_owner=descriptor_owner,
        )

        assert '"runtime.message.transport"' in rendered
        assert f'"{selected_adapter}"' in rendered


def test_commercial_redis_message_transport_is_enabled_without_secrets() -> None:
    bindings = governance.load_bindings()

    for environment in ("beta", "gamma", "prod"):
        binding = next(
            item
            for item in bindings["environments"][environment]["capabilities"]
            if item["capability_id"] == "runtime.message.transport"
        )
        assert binding["state"] == "enabled"
        assert binding["adapter_id"] == "infra.redis.message_transport"
        assert binding["secret_refs"] == []


def test_runtime_shared_adapter_consumers_and_asset_only_dns_are_exact() -> None:
    registry = governance.load_registry()
    capability_by_id = {
        capability["capability_id"]: capability
        for capability in registry["capabilities"]
        if isinstance(capability, dict)
    }
    adapters = [
        adapter
        for adapter in registry["adapters"]
        if isinstance(adapter, dict)
    ]
    message_root_ids = {
        root["root_id"]
        for root in capability_by_id["runtime.message.transport"]["binding_roots"]
    }
    message_adapters = [
        adapter
        for adapter in adapters
        if adapter["capability_id"] == "runtime.message.transport"
    ]
    assert message_adapters
    for adapter in message_adapters:
        assert set(adapter["consumers"]) == message_root_ids
        assert adapter["production_consumption"] in {"required", "none"}
    dns_adapters = [
        adapter
        for adapter in adapters
        if adapter["capability_id"] == "runtime.dns.resolution"
    ]
    assert dns_adapters
    assert {adapter["production_consumption"] for adapter in dns_adapters} == {"none"}


def test_unimplemented_dns_is_not_release_required_or_bound() -> None:
    registry = governance.load_registry()
    capabilities = {
        capability["capability_id"]: capability
        for capability in registry["capabilities"]
        if isinstance(capability, dict)
    }
    bindings = governance.load_bindings()

    assert capabilities["runtime.dns.resolution"]["required_environments"] == []
    for environment in ("beta", "gamma", "prod"):
        bound_ids = {
            binding["capability_id"]
            for binding in bindings["environments"][environment]["capabilities"]
        }
        assert "runtime.dns.resolution" not in bound_ids


def test_wave_one_alpha_bindings_use_isolated_protocol_fixtures() -> None:
    compiled, issues = governance.load_and_compile()

    assert issues == []
    capability_by_id = {
        capability["capability_id"]: capability
        for capability in governance.load_registry()["capabilities"]
    }
    assert (
        capability_by_id["runtime.log.sink"]["canonical_port"]
        == "product_ops.application.ObservabilityLogSink"
    )
    alpha = compiled["readiness"]["alpha"]
    assert alpha["assistant.model.generation"]["adapter_id"] == "ext.llm.protocol_fixture"
    assert alpha["runtime.log.sink"]["adapter_id"] == "infra.observability.sls_fixture"
    assert alpha["assistant.model.generation"]["adapter_preflight_ready"] is True
    assert alpha["runtime.log.sink"]["adapter_preflight_ready"] is True


def test_release_capability_rejects_legacy_composition_and_missing_binding_roots() -> None:
    registry = deepcopy(governance.load_registry())
    capability = next(
        item
        for item in registry["capabilities"]
        if item["capability_id"] == "content.embedding.generation"
    )
    capability["composition"] = {
        "descriptor_owner": "content-service",
    }
    del capability["binding_roots"]

    issues = governance.registry_issues(registry)

    assert any(
        issue.location.endswith(".composition")
        and "retired composition field is forbidden" in issue.message
        for issue in issues
    )
    assert any(
        issue.location.endswith(".binding_roots")
        and "must declare non-empty binding_roots" in issue.message
        for issue in issues
    )


def test_shared_redis_binding_root_requires_usage_and_preflight_scenes() -> None:
    registry = deepcopy(governance.load_registry())
    capability = next(
        item
        for item in registry["capabilities"]
        if item["capability_id"] == "runtime.message.transport"
    )
    capability["binding_roots"][0].pop("usage")
    capability["binding_roots"][0].pop("required_redis_scenes")

    issues = governance.registry_issues(registry)

    assert any(
        issue.location.endswith(".binding_roots[0]")
        and "missing required field 'usage'" in issue.message
        for issue in issues
    )
    assert any(
        issue.location.endswith(".binding_roots[0]")
        and "missing required field 'required_redis_scenes'" in issue.message
        for issue in issues
    )


def test_non_alpha_binding_cannot_enable_fixture_only_adapter() -> None:
    registry = governance.load_registry()
    bindings = deepcopy(governance.load_bindings())
    bindings["environments"]["beta"]["capabilities"][0].update(
        state="enabled",
        adapter_id="ext.sms.mock",
        endpoint_ref="not_configured",
        secret_refs=[],
    )

    issues = governance.binding_issues(registry, bindings)

    assert any(
        issue.location.endswith(".adapter_id")
        and "non-alpha enabled bindings require a real fail-closed adapter" in issue.message
        for issue in issues
    )


def test_evidence_schema_requires_disposable_run_artifact_reference() -> None:
    schema = governance.CONFORMANCE_PATH.parent / "provider_conformance_evidence.schema.json"
    content = schema.read_text(encoding="utf-8")

    assert '"provider-conformance-evidence"' in content
    assert '"artifactRef"' in content
    assert '"^\\\\.qwq_output/env/(?:alpha|beta|gamma)/runs/"' in content


def test_manifest_requires_specialized_assertions_for_each_registered_profile() -> None:
    manifest = deepcopy(governance.load_conformance_manifest())
    del manifest["profile_assertion_ids"]["dns_resolver"]

    issues = governance.conformance_manifest_issues(
        governance.load_registry(),
        manifest,
    )

    assert any(
        issue.location == "conformance.profile_assertion_ids.dns_resolver"
        and "must be a non-empty unique list" in issue.message
        for issue in issues
    )


def test_wave_one_profiles_reference_provider_specific_contracts() -> None:
    profiles = governance.load_conformance_manifest()["profiles"]

    assert profiles["model_gateway"]["local_contract"].endswith(
        "assistant-service/internal/infrastructure/modelprovider/"
        "client__local_contract_test.go"
    )
    assert profiles["rtc_provider"]["local_contract"].endswith(
        "rtc-service/internal/infrastructure/livekit/room_adapter__local_contract_test.go"
    )
    assert profiles["observability_log"]["local_contract"].endswith(
        "product-ops-service/tests/local_contract/"
        "visit_event_contract__local_contract_test.go"
    )
    assert profiles["observability_log"]["api_integration"].endswith(
        "product-ops-service/tests/api_integration/"
        "rtc_media_qoe_summary__observability__api_integration_test.go"
    )


def test_message_transport_uat_source_is_a_controlled_remote_prerequisite() -> None:
    manifest = governance.load_conformance_manifest()
    source = manifest["profiles"]["message_transport"]["user_acceptance"]

    assert source == (
        "quwoquan_ops/environments/provider_conformance_prerequisites/"
        "message_transport_chat_assistant_remote_uat.yaml"
    )
    assert "chat_assistant_journey__user_acceptance_test.dart" not in source
    assert not governance.conformance_manifest_issues(
        governance.load_registry(),
        manifest,
    )


if __name__ == "__main__":
    test_registry_compiles_into_single_environment_selection_and_readiness()
    test_registry_rejects_literal_provider_endpoint()
    test_provider_governance_sources_reject_versioned_contract_tracks()
    test_implemented_sdk_adapters_register_the_real_boundary_and_dependency()
    test_assistant_provider_adapters_bind_to_typed_infrastructure_ports()
    test_assistant_bindings_compile_to_fixed_adapter_descriptors()
    test_assistant_binding_requires_endpoint_keys_and_timeout()
    test_content_embedding_adapter_registers_real_port_sdk_and_bindings()
    test_release_capabilities_have_root_scoped_descriptors_and_static_consumption()
    test_release_binding_roots_are_single_or_shared_and_deduplicated()
    test_shared_redis_binding_projects_to_each_descriptor_owner()
    test_unimplemented_dns_is_not_release_required_or_bound()
    test_wave_one_alpha_bindings_use_isolated_protocol_fixtures()
    test_release_capability_rejects_legacy_composition_and_missing_binding_roots()
    test_shared_redis_binding_root_requires_usage_and_preflight_scenes()
    test_non_alpha_binding_cannot_enable_fixture_only_adapter()
    test_evidence_schema_requires_disposable_run_artifact_reference()
    test_manifest_requires_specialized_assertions_for_each_registered_profile()
    test_wave_one_profiles_reference_provider_specific_contracts()
    test_message_transport_uat_source_is_a_controlled_remote_prerequisite()
