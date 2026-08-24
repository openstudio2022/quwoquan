package local_contract

import (
	"slices"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	locationgenerated "quwoquan_service/services/integration-service/generated/external_integration/location"
	. "quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/providerbinding"
)

// 环境隔离由多环境声明拥有：非生产三环境只声明协议替身地图 Provider，prod 只声明
// 真实厂商 Provider 并携带其密钥材料键。断言取相等而非不等，因此「prod 不得落到
// 协议替身」与「非生产不得落到真实厂商」两个方向都被钉住。
func TestLocationLookupDeclarationsUseNonprodProtocolSubstituteAndProdRealProvider(
	t *testing.T,
) {
	for _, environment := range []string{"alpha", "beta", "gamma"} {
		binding := declaredLocationBinding(t, environment, LocationLookupCapabilityID)
		if binding.State != "enabled" || binding.AdapterID != "ext.map.protocol_fixture" {
			t.Fatalf("%s 位置查找声明必须是协议替身: %+v", environment, binding)
		}
		if len(binding.EndpointEnvironmentKeys) != 1 ||
			binding.EndpointEnvironmentKeys["base"] !=
				"INTEGRATION_LOCATION_FIXTURE_BASE_URL" ||
			len(binding.SecretEnvironmentKeys) != 0 ||
			binding.TimeoutMilliseconds <= 0 {
			t.Fatalf("%s 协议替身声明漂移: %+v", environment, binding)
		}
	}

	prod := declaredLocationBinding(t, "prod", LocationLookupCapabilityID)
	if prod.State != "enabled" || prod.AdapterID != "ext.map.baidu" {
		t.Fatalf("prod 位置查找声明必须是真实厂商 Provider: %+v", prod)
	}
	if prod.EndpointEnvironmentKeys["base"] != "INTEGRATION_LOCATION_BAIDU_BASE_URL" {
		t.Fatalf("prod endpoint 材料键漂移: %+v", prod.EndpointEnvironmentKeys)
	}
	if !slices.Contains(prod.SecretEnvironmentKeys, "INTEGRATION_LOCATION_BAIDU_AK") {
		t.Fatalf("prod 缺少厂商密钥材料键: %+v", prod.SecretEnvironmentKeys)
	}
}

// 未打包源码树不固化任何环境：多环境发射器只写出恒 false 的 CompiledBindingFor，
// 单环境实现由 stackctl package 的 provider binding overlay 在构建期覆盖写入。
// 因此四环境加未知环境、任何材料组合都必须 fail closed。
func TestResolveLocationLookupFailsClosedWithoutCompiledEnvironmentBinding(t *testing.T) {
	if _, found := locationgenerated.CompiledBindingFor(LocationLookupCapabilityID); found {
		t.Fatalf(
			"源码树编译进了环境绑定 capability=%s；环境只能由打包期 overlay 固化",
			LocationLookupCapabilityID,
		)
	}
	materials := []struct {
		name   string
		config runtimeconfig.MapRuntimeConfigProvider
	}{
		{
			name:   "no material",
			config: runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}},
		},
		{
			name: "complete material",
			config: runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{
				"INTEGRATION_LOCATION_FIXTURE_BASE_URL": "https://provider-protocol-substitute:18089/map",
				"INTEGRATION_LOCATION_BAIDU_BASE_URL":   "https://api.map.baidu.com",
				"INTEGRATION_LOCATION_BAIDU_AK":         "test-ak",
			}},
		},
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod", "unknown"} {
		for _, material := range materials {
			_, err := ResolveLocationLookup(environment, material.config)
			if err == nil || !strings.Contains(err.Error(), "binding is missing") {
				t.Fatalf(
					"环境 %s（%s）未打包时必须 fail closed，got %v",
					environment,
					material.name,
					err,
				)
			}
		}
	}
}

// 公共 Provider 的环境准入完全由声明层拥有：poi.search 与 route.read 在四环境
// 一致保持 not_required——nonprod 三环境必须共享同一 binding 档（DEC-005 信任域
// 裁决），启用任一项都要求四环境同步声明，不允许单环境先行。
func TestPublicLocationBindingsAlphaSubstituteAndOtherEnvironmentsBlocked(
	t *testing.T,
) {
	alphaPOI := declaredLocationBinding(t, "alpha", LocationPOISearchCapabilityID)
	if alphaPOI.State != "not_required" || alphaPOI.AdapterID != "" {
		t.Fatalf("alpha POI 必须与其余环境同档保持未启用: %+v", alphaPOI)
	}

	alphaRoute := declaredLocationBinding(t, "alpha", LocationRouteReadCapabilityID)
	if alphaRoute.State != "not_required" || alphaRoute.AdapterID != "" {
		t.Fatalf("alpha route.read 必须保持未启用: %+v", alphaRoute)
	}
	for _, environment := range []string{"beta", "gamma", "prod"} {
		for _, capabilityID := range []string{
			LocationPOISearchCapabilityID,
			LocationRouteReadCapabilityID,
		} {
			binding := declaredLocationBinding(t, environment, capabilityID)
			if binding.State != "not_required" || binding.AdapterID != "" {
				t.Fatalf(
					"环境 %s 的 %s 必须保持未启用: %+v",
					environment,
					capabilityID,
					binding,
				)
			}
		}
	}
}

// 未打包树里公共能力同样只能 fail closed；能力名未登记是纯守卫子句，与编译期绑定无关。
func TestResolvePublicLocationCapabilityFailsClosedWithoutCompiledEnvironmentBinding(
	t *testing.T,
) {
	values := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{
		"INTEGRATION_LOCATION_NOMINATIM_BASE_URL": "https://nominatim.example.test",
		"INTEGRATION_LOCATION_OSRM_BASE_URL":      "https://osrm.example.test",
	}}
	policy := PublicProviderRuntimePolicy{
		ConfigRef:          "config:integration.public_provider",
		RatePolicyRef:      "config:integration.public_provider",
		ProbePassed:        true,
		RateLimitPerSecond: 1,
	}
	for _, capabilityID := range []string{
		LocationPOISearchCapabilityID,
		LocationRouteReadCapabilityID,
	} {
		if _, found := locationgenerated.CompiledBindingFor(capabilityID); found {
			t.Fatalf(
				"源码树编译进了环境绑定 capability=%s；环境只能由打包期 overlay 固化",
				capabilityID,
			)
		}
		for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
			_, err := ResolvePublicLocationCapability(
				environment,
				capabilityID,
				values,
				policy,
			)
			if err == nil || !strings.Contains(err.Error(), "binding is missing") {
				t.Fatalf(
					"环境 %s 的 %s 未打包时必须 fail closed，got %v",
					environment,
					capabilityID,
					err,
				)
			}
		}
	}

	if _, err := ResolvePublicLocationCapability(
		"alpha",
		"location.unregistered.capability",
		values,
		policy,
	); err == nil || !strings.Contains(err.Error(), "is not registered") {
		t.Fatalf("未登记的公共能力必须 fail closed，got %v", err)
	}
}

// 纯守卫子句不依赖编译期绑定，未打包树里同样必须 fail closed。
func TestLocationBindingResolutionRequiresRuntimeConfigProvider(t *testing.T) {
	if _, err := ResolveLocationLookup("prod", nil); err == nil ||
		!strings.Contains(err.Error(), "no runtime config provider") {
		t.Fatalf("location lookup missing config provider must fail closed, got %v", err)
	}
	if _, err := ResolvePublicLocationCapability(
		"alpha",
		LocationPOISearchCapabilityID,
		nil,
		PublicProviderRuntimePolicy{},
	); err == nil || !strings.Contains(err.Error(), "no runtime config provider") {
		t.Fatalf("public location missing config provider must fail closed, got %v", err)
	}
}

func declaredLocationBinding(
	t *testing.T,
	environment string,
	capabilityID string,
) locationgenerated.ExternalProviderBinding {
	t.Helper()
	binding, found := locationgenerated.ExternalProviderBindingFor(
		environment,
		capabilityID,
	)
	if !found {
		t.Fatalf("环境 %s 缺少 %s 声明，打包期无可固化输入", environment, capabilityID)
	}
	return binding
}
