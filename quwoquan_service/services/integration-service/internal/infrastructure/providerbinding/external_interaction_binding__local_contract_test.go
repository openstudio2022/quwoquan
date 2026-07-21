package providerbinding

import (
	"errors"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	integrationgenerated "quwoquan_service/services/integration-service/internal/generated"
)

func TestReleaseExternalInteractionBindingsFailClosedUntilEnabledAndMaterialized(t *testing.T) {
	config := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}}
	if _, err := ResolveSMSBinding("beta", config); err == nil ||
		!errors.Is(err, ErrExternalInteractionCapabilityBlocked) {
		t.Fatalf("blocked SMS binding must be identifiable for controlled degradation, err = %v", err)
	}
	if _, err := ResolvePushBinding("beta", config); err == nil ||
		!errors.Is(err, ErrExternalInteractionCapabilityBlocked) {
		t.Fatalf("blocked Push binding must be identifiable for controlled degradation, err = %v", err)
	}

	original := integrationgenerated.ExternalProviderBindings["beta"][smsCapabilityID]
	enabled := original
	enabled.State = "enabled"
	integrationgenerated.ExternalProviderBindings["beta"][smsCapabilityID] = enabled
	t.Cleanup(func() {
		integrationgenerated.ExternalProviderBindings["beta"][smsCapabilityID] = original
	})

	if _, err := ResolveSMSBinding("beta", config); err == nil ||
		!strings.Contains(err.Error(), "endpoint material is unavailable") {
		t.Fatalf("missing SMS endpoint error = %v", err)
	}
	_, err := ResolveSMSBinding("beta", runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"INTEGRATION_SMS_ENDPOINT":                  "https://sms.example.test",
			"INTEGRATION_SMS_TOKEN":                     "test-token",
			"OTP_CODE_REF_KEYS_JSON":                    "test-reference-keys",
			"INTEGRATION_SERVICE_MTLS_CA_FILE":          "/tmp/ca.pem",
			"INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE": "/tmp/client.pem",
			"INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE":  "/tmp/client-key.pem",
		},
	})
	if err != nil {
		t.Fatalf("enabled SMS binding resolution failed: %v", err)
	}
}
