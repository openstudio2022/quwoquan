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

func TestPublicLocationBindingsDefaultUnavailableInAllEnvironments(
	t *testing.T,
) {
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		for _, capability := range []string{
			LocationPOISearchCapabilityID,
			LocationRouteReadCapabilityID,
		} {
			_, err := ResolvePublicLocationCapability(
				environment,
				capability,
				runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{
					"INTEGRATION_LOCATION_NOMINATIM_BASE_URL": "https://nominatim.example.test",
					"INTEGRATION_LOCATION_OSRM_BASE_URL":      "https://osrm.example.test",
				}},
				PublicProviderRuntimePolicy{
					ConfigRef:          "config:integration.public_provider",
					RatePolicyRef:      "config:integration.public_provider",
					ProbePassed:        true,
					RateLimitPerSecond: 1,
				},
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
