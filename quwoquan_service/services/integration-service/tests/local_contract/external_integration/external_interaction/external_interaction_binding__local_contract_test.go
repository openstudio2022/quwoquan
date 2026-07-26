package local_contract

import (
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	. "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/providerbinding"
)

func TestReleaseExternalInteractionBindingsFailClosedUntilEnabledAndMaterialized(t *testing.T) {
	config := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}}
	if _, err := ResolveSMSBinding("beta", config); err == nil ||
		!strings.Contains(err.Error(), "endpoint material is unavailable") {
		t.Fatalf("enabled SMS binding without materials must fail closed, err = %v", err)
	}
	if _, err := ResolvePushBinding("beta", config); err == nil ||
		!strings.Contains(err.Error(), "endpoint material is unavailable") {
		t.Fatalf("enabled Push binding without materials must fail closed, err = %v", err)
	}

	_, err := ResolveSMSBinding("beta", runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"INTEGRATION_SMS_FIXTURE_ENDPOINT": "https://fixture.local/integration/sms",
			"INTEGRATION_SMS_FIXTURE_TOKEN":    "test-token",
		},
	})
	if err != nil {
		t.Fatalf("enabled SMS local_capture binding resolution failed: %v", err)
	}
	_, err = ResolvePushBinding("beta", runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"INTEGRATION_PUSH_FIXTURE_USER_SERVICE_BASE_URL": "https://fixture.local/user",
			"INTEGRATION_PUSH_FIXTURE_HMAC_KEY":              "fixture-hmac",
		},
	})
	if err != nil {
		t.Fatalf("enabled Push local_recorder binding resolution failed: %v", err)
	}

	if _, err := ResolveSMSBinding("prod", config); err == nil {
		t.Fatal("blocked prod SMS binding must fail closed")
	}
}
