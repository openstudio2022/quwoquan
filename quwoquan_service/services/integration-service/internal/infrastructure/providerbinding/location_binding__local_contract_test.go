package providerbinding

import (
	"errors"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	integrationgenerated "quwoquan_service/services/integration-service/internal/generated"
)

func TestResolveLocationLookupFailsClosedForBlockedAndMissingMaterial(t *testing.T) {
	emptyConfig := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}}
	if _, err := ResolveLocationLookup("unknown", emptyConfig); err == nil {
		t.Fatal("unknown binding must fail closed")
	}
	if _, err := ResolveLocationLookup("gamma", emptyConfig); err == nil ||
		!errors.Is(err, ErrLocationLookupCapabilityBlocked) {
		t.Fatalf("blocked binding must be identifiable for structured degradation, err = %v", err)
	}

	original := integrationgenerated.ExternalProviderBindings["gamma"][LocationLookupCapabilityID]
	enabled := original
	enabled.State = "enabled"
	integrationgenerated.ExternalProviderBindings["gamma"][LocationLookupCapabilityID] = enabled
	t.Cleanup(func() {
		integrationgenerated.ExternalProviderBindings["gamma"][LocationLookupCapabilityID] = original
	})

	if _, err := ResolveLocationLookup("gamma", emptyConfig); err == nil ||
		!strings.Contains(err.Error(), "endpoint material is unavailable") {
		t.Fatalf("missing endpoint material error = %v", err)
	}

	_, err := ResolveLocationLookup(
		"gamma",
		runtimeconfig.MapRuntimeConfigProvider{
			Values: map[string]string{
				"INTEGRATION_LOCATION_BAIDU_BASE_URL": "https://map.example.test",
			},
		},
	)
	if err == nil || !strings.Contains(err.Error(), "secret material is unavailable") {
		t.Fatalf("missing secret material error = %v", err)
	}
}
