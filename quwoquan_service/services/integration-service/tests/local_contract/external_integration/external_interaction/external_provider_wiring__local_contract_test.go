package local_contract

import (
	"strings"
	"testing"

	platformconfig "quwoquan_service/runtime/config"
	integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"
)

func TestMaterializeProdReleaseBindingsEnableRealProvidersWhenMaterialsPresent(t *testing.T) {
	cfg := integrationconfig.Config{Environment: "prod"}
	cfg.Integration.ExternalInteraction.SMS.Enabled = false
	cfg.Integration.ExternalInteraction.Push.Enabled = false

	if _, err := integrationconfig.MaterializeReleaseExternalInteractionBindings(
		cfg,
		platformconfig.MapRuntimeConfigProvider{Values: map[string]string{}},
	); err == nil || !strings.Contains(err.Error(), "material is unavailable") {
		t.Fatalf("missing materials must fail closed: %v", err)
	}

	resolved, err := integrationconfig.MaterializeReleaseExternalInteractionBindings(
		cfg,
		platformconfig.MapRuntimeConfigProvider{Values: map[string]string{
			"INTEGRATION_SMS_ENDPOINT":                  "https://sms.example.com",
			"INTEGRATION_SMS_TOKEN":                     "token",
			"OTP_CODE_REF_KEYS_JSON":                    `{"active":"test-key"}`,
			"INTEGRATION_SERVICE_MTLS_CA_FILE":          "/run/secrets/sms-ca.pem",
			"INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE": "/run/secrets/sms-client.pem",
			"INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE":  "/run/secrets/sms-client-key.pem",
			"INTEGRATION_PUSH_USER_SERVICE_BASE_URL":    "http://user-service:18081",
			"INTEGRATION_PUSH_APNS_ENVIRONMENT":         "production",
			"INTEGRATION_PUSH_APNS_KEY_ID":              "APNSKEY01",
			"INTEGRATION_PUSH_APNS_TEAM_ID":             "TEAM000001",
			"INTEGRATION_PUSH_APNS_TOPIC":               "com.quwoquan.app.voip",
			"INTEGRATION_PUSH_FCM_PROJECT_ID":           "quwoquan-gamma",
			"INTEGRATION_PUSH_APNS_KEY_FILE":            "/run/secrets/apns-key.p8",
			"INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE": "/run/secrets/fcm.json",
		}},
	)
	if err != nil {
		t.Fatalf("release Provider materialization failed: %v", err)
	}
	if !resolved.Integration.ExternalInteraction.SMS.Enabled {
		t.Fatal("SMS real Provider must be enabled")
	}
	if !resolved.Integration.ExternalInteraction.Push.Enabled ||
		resolved.Integration.ExternalInteraction.Push.Mode != "remote" {
		t.Fatalf("Push remote Provider must be enabled: %#v", resolved.Integration.ExternalInteraction.Push)
	}
}
