package local_contract

import (
	"errors"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	. "quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/providerbinding"
)

func TestResolveLocationLookupUsesNonprodProtocolSubstituteAndProdRealProvider(t *testing.T) {
	emptyConfig := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}}
	if _, err := ResolveLocationLookup("unknown", emptyConfig); err == nil {
		t.Fatal("unknown binding must fail closed")
	}
	for _, environment := range []string{"alpha", "beta", "gamma"} {
		binding, err := ResolveLocationLookup(
			environment,
			runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{
				"INTEGRATION_LOCATION_FIXTURE_BASE_URL": "https://provider-protocol-substitute:18089/map",
			}},
		)
		if err != nil {
			t.Fatalf("%s protocol substitute binding failed: %v", environment, err)
		}
		if binding.AdapterID != "ext.map.protocol_fixture" ||
			len(binding.Endpoints) != 1 || len(binding.Secrets) != 0 {
			t.Fatalf("%s protocol substitute binding drift: %+v", environment, binding)
		}
	}

	_, err := ResolveLocationLookup(
		"prod",
		runtimeconfig.MapRuntimeConfigProvider{
			Values: map[string]string{
				"INTEGRATION_LOCATION_BAIDU_BASE_URL": "https://api.map.baidu.com",
			},
		},
	)
	if err == nil || !strings.Contains(err.Error(), "secret material is unavailable") {
		t.Fatalf("missing secret material error = %v", err)
	}

	binding, err := ResolveLocationLookup(
		"prod",
		runtimeconfig.MapRuntimeConfigProvider{
			Values: map[string]string{
				"INTEGRATION_LOCATION_BAIDU_BASE_URL": "https://api.map.baidu.com",
				"INTEGRATION_LOCATION_BAIDU_AK":       "test-ak",
			},
		},
	)
	if err != nil {
		t.Fatalf("enabled location binding resolution failed: %v", err)
	}
	if binding.AdapterID != "ext.map.baidu" {
		t.Fatalf("unexpected adapter: %s", binding.AdapterID)
	}
}

func TestPublicLocationBindingsAlphaSubstituteAndOtherEnvironmentsBlocked(
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
	binding, err := ResolvePublicLocationCapability(
		"alpha",
		LocationPOISearchCapabilityID,
		values,
		policy,
	)
	if err != nil {
		t.Fatalf("alpha POI substitute binding failed: %v", err)
	}
	if binding.AdapterID != "ext.map.nominatim.protocol_substitute" ||
		len(binding.Secrets) != 0 {
		t.Fatalf("alpha POI binding drift: %+v", binding)
	}
	// route.read 在四环境保持未启用：App 无路线消费页面，UAT journey 无法闭环。
	if _, routeErr := ResolvePublicLocationCapability(
		"alpha",
		LocationRouteReadCapabilityID,
		values,
		policy,
	); !errors.Is(routeErr, ErrPublicLocationCapabilityBlocked) {
		t.Fatalf("alpha route.read error = %v, want blocked", routeErr)
	}
	for _, environment := range []string{"beta", "gamma", "prod"} {
		for _, capability := range []string{
			LocationPOISearchCapabilityID,
			LocationRouteReadCapabilityID,
		} {
			_, err := ResolvePublicLocationCapability(
				environment,
				capability,
				values,
				policy,
			)
			if !errors.Is(err, ErrPublicLocationCapabilityBlocked) {
				t.Fatalf(
					"%s %s error = %v, want blocked",
					environment,
					capability,
					err,
				)
			}
		}
	}
}
