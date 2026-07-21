package provider

import (
	"net/http"
	"testing"
	"time"

	"quwoquan_service/services/integration-service/internal/infrastructure/providerbinding"
)

func TestNewLocationProviderBuildsOnlyTheSelectedAdapter(t *testing.T) {
	binding := providerbinding.ResolvedLocationBinding{
		AdapterID: LocationAdapterBaiduID,
		Endpoints: map[string]string{
			locationEndpointRoleBase: "https://map.example.test",
		},
		Secrets: map[string]string{
			locationBaiduAKSecret: "test-ak",
		},
		Timeout: time.Second,
	}

	resolved, err := NewLocationProvider(binding, &http.Client{})
	if err != nil {
		t.Fatalf("NewLocationProvider() error = %v", err)
	}
	if _, ok := resolved.(*BaiduClient); !ok {
		t.Fatalf("selected provider type = %T, want *BaiduClient", resolved)
	}
}

func TestNewLocationProviderRejectsUnregisteredAdapterAndInsecureEndpoint(t *testing.T) {
	baseBinding := providerbinding.ResolvedLocationBinding{
		AdapterID: LocationAdapterBaiduID,
		Endpoints: map[string]string{
			locationEndpointRoleBase: "https://map.example.test",
		},
		Secrets: map[string]string{
			locationBaiduAKSecret: "test-ak",
		},
	}
	unknown := baseBinding
	unknown.AdapterID = "ext.map.unknown"
	if _, err := NewLocationProvider(unknown, &http.Client{}); err == nil {
		t.Fatal("unregistered adapter must fail closed")
	}

	insecure := baseBinding
	insecure.Endpoints = map[string]string{
		locationEndpointRoleBase: "http://map.example.test",
	}
	if _, err := NewLocationProvider(insecure, &http.Client{}); err == nil {
		t.Fatal("non-HTTPS endpoint must fail closed")
	}
}
