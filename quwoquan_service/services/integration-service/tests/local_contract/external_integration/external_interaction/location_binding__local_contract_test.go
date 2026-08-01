package local_contract

import (
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	. "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/providerbinding"
)

func TestResolveLocationLookupFailsClosedForMissingMaterial(t *testing.T) {
	emptyConfig := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}}
	if _, err := ResolveLocationLookup("unknown", emptyConfig); err == nil {
		t.Fatal("unknown binding must fail closed")
	}
	if _, err := ResolveLocationLookup("gamma", emptyConfig); err == nil ||
		!strings.Contains(err.Error(), "endpoint material is unavailable") {
		t.Fatalf("enabled gamma binding without materials must fail closed, err = %v", err)
	}

	_, err := ResolveLocationLookup(
		"gamma",
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
		"gamma",
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
