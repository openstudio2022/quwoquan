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

	smsBinding, err := ResolveSMSBinding("beta", runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"INTEGRATION_SMS_ENDPOINT":                  "https://sms.example.test",
			"INTEGRATION_SMS_TOKEN":                     "test-token",
			"OTP_CODE_REF_KEYS_JSON":                    "test-code-ref-key",
			"INTEGRATION_SERVICE_MTLS_CA_FILE":          "/test/ca.pem",
			"INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE": "/test/client.pem",
			"INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE":  "/test/client.key",
		},
	})
	if err != nil {
		t.Fatalf("enabled SMS binding resolution failed: %v", err)
	}
	if smsBinding.AdapterID != SMSAdapterAliyun {
		t.Fatalf("SMS adapter=%q, want=%q", smsBinding.AdapterID, SMSAdapterAliyun)
	}
	pushBinding, err := ResolvePushBinding("beta", runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"INTEGRATION_PUSH_USER_SERVICE_BASE_URL":    "https://user.example.test",
			"INTEGRATION_PUSH_APNS_ENVIRONMENT":         "sandbox",
			"INTEGRATION_PUSH_APNS_KEY_ID":              "test-key-id",
			"INTEGRATION_PUSH_APNS_TEAM_ID":             "test-team-id",
			"INTEGRATION_PUSH_APNS_TOPIC":               "com.example.app.voip",
			"INTEGRATION_PUSH_FCM_PROJECT_ID":           "test-project",
			"INTEGRATION_PUSH_APNS_KEY_FILE":            "/test/AuthKey.p8",
			"INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE": "/test/fcm.json",
		},
	})
	if err != nil {
		t.Fatalf("enabled Push binding resolution failed: %v", err)
	}
	if pushBinding.AdapterID != PushAdapterDispatch {
		t.Fatalf("Push adapter=%q, want=%q", pushBinding.AdapterID, PushAdapterDispatch)
	}

	if _, err := ResolveSMSBinding("prod", config); err == nil {
		t.Fatal("blocked prod SMS binding must fail closed")
	}
}
