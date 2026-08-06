package local_contract

import (
	"net/http"
	"testing"
	"time"

	locationgenerated "quwoquan_service/services/integration-service/generated/external_integration/location"
	. "quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/provider"
	"quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/providerbinding"
)

func TestNewLocationProviderBuildsOnlyTheEnvironmentSelectedAdapter(t *testing.T) {
	binding := resolvedLocationBindingForTest(t, "gamma")
	binding.Timeout = time.Second

	resolved, err := NewLocationProvider(binding, &http.Client{})
	if err != nil {
		t.Fatalf("NewLocationProvider() error = %v", err)
	}
	if _, ok := resolved.(*BaiduClient); !ok {
		t.Fatalf(
			"gamma provider type = %T, want external protocol *BaiduClient",
			resolved,
		)
	}

	prodBinding := resolvedLocationBindingForTest(t, "prod")
	prodBinding.Timeout = time.Second
	resolved, err = NewLocationProvider(prodBinding, &http.Client{})
	if err != nil {
		t.Fatalf("NewLocationProvider(prod) error = %v", err)
	}
	if _, ok := resolved.(*BaiduClient); !ok {
		t.Fatalf("prod provider type = %T, want *BaiduClient", resolved)
	}
}

func TestNewLocationProviderRejectsUnregisteredAdapterAndInsecureEndpoint(t *testing.T) {
	baseBinding := resolvedLocationBindingForTest(t, "prod")
	unknown := baseBinding
	unknown.AdapterID = "ext.map.unknown"
	if _, err := NewLocationProvider(unknown, &http.Client{}); err == nil {
		t.Fatal("unregistered adapter must fail closed")
	}

	// Vendor adapters must reject non-HTTPS endpoints; nonprod protocol substitutes
	// are allowed to use the isolated Compose network.
	insecure := baseBinding
	insecure.AdapterID = LocationAdapterBaiduID
	insecure.Endpoints = map[string]string{"base": "http://map.example.test"}
	insecure.Secrets = map[string]string{"INTEGRATION_LOCATION_BAIDU_AK": "test-ak"}
	if _, err := NewLocationProvider(insecure, &http.Client{}); err == nil {
		t.Fatal("non-HTTPS endpoint must fail closed")
	}
}

func TestPublicProviderFactoryRequiresPassedProbeAndInjectedPolicy(t *testing.T) {
	binding := providerbinding.ResolvedLocationBinding{
		AdapterID:          LocationAdapterNominatimID,
		ConfigRef:          "config:integration.public_provider.poi",
		RatePolicyRef:      "config:integration.public_provider.poi",
		RateLimitPerSecond: 1,
		Endpoints:          map[string]string{"base": "https://nominatim.example.test"},
		Timeout:            time.Second,
	}
	if _, err := NewPOISearchProvider(binding, &http.Client{}); err == nil {
		t.Fatal("POI provider without passed probe must fail closed")
	}
	binding.ProbePassed = true
	resolved, err := NewPOISearchProvider(binding, &http.Client{})
	if err != nil {
		t.Fatalf("construct ready POI provider: %v", err)
	}
	if _, ok := resolved.(*NominatimClient); !ok {
		t.Fatalf("POI provider type = %T, want *NominatimClient", resolved)
	}

	binding.AdapterID = LocationAdapterOSRMID
	binding.RateLimitPerSecond = 5
	binding.Endpoints["base"] = "https://osrm.example.test"
	route, err := NewRouteReadProvider(binding, &http.Client{})
	if err != nil {
		t.Fatalf("construct ready route provider: %v", err)
	}
	if _, ok := route.(*OSRMClient); !ok {
		t.Fatalf("route provider type = %T, want *OSRMClient", route)
	}
}

func resolvedLocationBindingForTest(
	t *testing.T,
	environment string,
) providerbinding.ResolvedLocationBinding {
	t.Helper()
	spec, found := locationgenerated.ExternalProviderBindingFor(
		environment,
		providerbinding.LocationLookupCapabilityID,
	)
	if !found {
		t.Fatalf("generated location binding missing for %s", environment)
	}
	endpoints := make(map[string]string, len(spec.EndpointEnvironmentKeys))
	for role := range spec.EndpointEnvironmentKeys {
		endpoints[role] = "https://map.example.test"
	}
	if spec.AdapterID == LocationAdapterProtocolFixtureID {
		endpoints["base"] = "https://provider-protocol-substitute:18089/map"
	}
	secrets := make(map[string]string, len(spec.SecretEnvironmentKeys))
	for _, environmentKey := range spec.SecretEnvironmentKeys {
		secrets[environmentKey] = "test-ak"
	}
	return providerbinding.ResolvedLocationBinding{
		AdapterID: spec.AdapterID,
		Endpoints: endpoints,
		Secrets:   secrets,
	}
}
