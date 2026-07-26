package local_contract

import (
	"net/http"
	. "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
	"testing"
	"time"

	locationgenerated "quwoquan_service/services/integration-service/generated/external_integration/location"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/providerbinding"
)

func TestNewLocationProviderBuildsOnlyTheSelectedAdapter(t *testing.T) {
	binding := resolvedLocationBindingForTest(t)
	binding.Timeout = time.Second

	resolved, err := NewLocationProvider(binding, &http.Client{})
	if err != nil {
		t.Fatalf("NewLocationProvider() error = %v", err)
	}
	if _, ok := resolved.(ProtocolFixtureLocationProvider); !ok {
		t.Fatalf(
			"selected provider type = %T, want ProtocolFixtureLocationProvider",
			resolved,
		)
	}
}

func TestNewLocationProviderRejectsUnregisteredAdapterAndInsecureEndpoint(t *testing.T) {
	baseBinding := resolvedLocationBindingForTest(t)
	unknown := baseBinding
	unknown.AdapterID = "ext.map.unknown"
	if _, err := NewLocationProvider(unknown, &http.Client{}); err == nil {
		t.Fatal("unregistered adapter must fail closed")
	}

	// Vendor adapters must reject non-HTTPS endpoints; protocol fixtures do not dial.
	insecure := baseBinding
	insecure.AdapterID = LocationAdapterBaiduID
	insecure.Endpoints = map[string]string{"base": "http://map.example.test"}
	insecure.Secrets = map[string]string{"INTEGRATION_LOCATION_BAIDU_AK": "test-ak"}
	if _, err := NewLocationProvider(insecure, &http.Client{}); err == nil {
		t.Fatal("non-HTTPS endpoint must fail closed")
	}
}

func resolvedLocationBindingForTest(t *testing.T) providerbinding.ResolvedLocationBinding {
	t.Helper()
	spec, found := locationgenerated.ExternalProviderBindingFor(
		"gamma",
		providerbinding.LocationLookupCapabilityID,
	)
	if !found {
		t.Fatal("generated location binding missing for gamma")
	}
	endpoints := make(map[string]string, len(spec.EndpointEnvironmentKeys))
	for role := range spec.EndpointEnvironmentKeys {
		endpoints[role] = "https://map.example.test"
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
