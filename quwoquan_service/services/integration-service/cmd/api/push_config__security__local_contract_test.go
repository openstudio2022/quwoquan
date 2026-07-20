package main

import (
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	serviceclients "quwoquan_service/generated/serviceclients"
)

func TestPushConfigScopesFakeToAlpha(t *testing.T) {
	cfg := validBaseConfigForPushTest()
	cfg.Environment = "alpha"
	cfg.Integration.ExternalInteraction.Push.Enabled = true
	cfg.Integration.ExternalInteraction.Push.Mode = "fake"
	cfg.Integration.ExternalInteraction.Push.TimeoutMs = 1000
	if err := validateRuntimeConfig(cfg); err != nil {
		t.Fatalf("alpha fake must be accepted: %v", err)
	}
	for _, appEnv := range []string{"beta", "gamma", "prod"} {
		cfg.Environment = appEnv
		if err := validateRuntimeConfig(cfg); err == nil ||
			!strings.Contains(err.Error(), "mode must be real") {
			t.Fatalf("%s must reject fake push mode, got %v", appEnv, err)
		}
	}
}

func TestPushEnvironmentConfigsEnableExpectedProviderMode(t *testing.T) {
	testCases := []struct {
		environment     string
		mode            string
		apnsEnvironment string
	}{
		{environment: "alpha", mode: "fake"},
		{environment: "beta", mode: "real", apnsEnvironment: "sandbox"},
		{environment: "gamma", mode: "real", apnsEnvironment: "sandbox"},
		{environment: "prod", mode: "real", apnsEnvironment: "production"},
	}
	for _, testCase := range testCases {
		t.Run(testCase.environment, func(t *testing.T) {
			cfg := loadPushEnvironmentConfigForTest(t, testCase.environment)
			push := cfg.Integration.ExternalInteraction.Push
			if !push.Enabled ||
				push.Mode != testCase.mode ||
				push.TimeoutMs <= 0 ||
				push.APNs.Environment != testCase.apnsEnvironment {
				t.Fatalf(
					"unexpected %s push config enabled=%t mode=%q timeout=%d apnsEnvironment=%q",
					testCase.environment,
					push.Enabled,
					push.Mode,
					push.TimeoutMs,
					push.APNs.Environment,
				)
			}
			err := validateRuntimeConfig(cfg)
			if testCase.environment == "alpha" {
				if err != nil {
					t.Fatalf("alpha fake config must be self-contained: %v", err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), "integration push") {
				t.Fatalf(
					"%s real config must fail fast until credentials are injected: %v",
					testCase.environment,
					err,
				)
			}
		})
	}
}

func TestPushConfigRealModeFailsFastWithoutSecretFiles(t *testing.T) {
	for _, appEnv := range []string{"beta", "gamma", "prod"} {
		t.Run(appEnv, func(t *testing.T) {
			cfg := validBaseConfigForPushTest()
			cfg.Environment = appEnv
			push := &cfg.Integration.ExternalInteraction.Push
			push.Enabled = true
			push.Mode = "real"
			push.TimeoutMs = 1000
			push.UserServiceBaseURL = "http://user-service:18082"
			push.APNs.Environment = "sandbox"
			if appEnv == "prod" {
				push.APNs.Environment = "production"
			}
			push.APNs.KeyFile = t.TempDir() + "/missing-apns.p8"
			push.APNs.KeyID = "APNSKEY01"
			push.APNs.TeamID = "TEAM000001"
			push.APNs.Topic = "com.quwoquan.app.voip"
			push.FCM.ServiceAccountFile = t.TempDir() + "/missing-fcm.json"
			push.FCM.ProjectID = "qwq-" + appEnv
			err := validateRuntimeConfig(cfg)
			if err == nil || !strings.Contains(err.Error(), "APNs key secret file is required") {
				t.Fatalf("missing secret file must fail before runtime dependencies: %v", err)
			}
		})
	}
}

func TestPushConfigRealModeRequiresExplicitProductionAPNs(t *testing.T) {
	cfg := validBaseConfigForPushTest()
	cfg.Environment = "prod"
	push := &cfg.Integration.ExternalInteraction.Push
	push.Enabled = true
	push.Mode = "real"
	push.TimeoutMs = 1000
	push.UserServiceBaseURL = "https://user-service.internal"
	push.APNs.Environment = "sandbox"
	push.APNs.KeyFile = writeNonEmptyConfigSecret(t, "apns.p8")
	push.APNs.KeyID = "APNSKEY01"
	push.APNs.TeamID = "TEAM000001"
	push.APNs.Topic = "com.quwoquan.app.voip"
	push.FCM.ServiceAccountFile = writeNonEmptyConfigSecret(t, "fcm.json")
	push.FCM.ProjectID = "qwq-prod"
	err := validateRuntimeConfig(cfg)
	if err == nil || !strings.Contains(err.Error(), "must be production in prod") {
		t.Fatalf("prod sandbox APNs must fail closed: %v", err)
	}
}

func TestPushObservedEndpointsRedactTokenAndEndpointRef(t *testing.T) {
	apnsRequest := httptest.NewRequest(
		"POST",
		"https://api.push.apple.com/3/device/plaintext-device-token",
		nil,
	)
	if got := externalProviderLogEndpoint(apnsRequest); got != "/3/device/{token}" {
		t.Fatalf("APNs log endpoint leaked token: %s", got)
	}
	secretRequest := httptest.NewRequest(
		"GET",
		"https://user-service.internal"+
			strings.ReplaceAll(
				serviceclients.UserPushEndpointSecretPathTemplate,
				"{endpointRef}",
				strings.Repeat("a", 64),
			),
		nil,
	)
	if got := externalProviderLogEndpoint(secretRequest); got !=
		serviceclients.UserPushEndpointSecretPathTemplate {
		t.Fatalf("user secret log endpoint leaked endpointRef: %s", got)
	}
}

func validBaseConfigForPushTest() config {
	cfg := config{}
	cfg.MongoDB.URI = "mongodb://127.0.0.1:27017"
	cfg.MongoDB.Database = "integration_test"
	return cfg
}

func loadPushEnvironmentConfigForTest(t *testing.T, appEnv string) config {
	t.Helper()
	cfg := validBaseConfigForPushTest()
	cfg.Environment = appEnv
	for _, path := range []string{
		filepath.Join("..", "..", "configs", "default", "config.yaml"),
		filepath.Join("..", "..", "configs", appEnv, "config.yaml"),
	} {
		if err := mergeConfigFile(&cfg, path); err != nil {
			t.Fatalf("load %s config %s: %v", appEnv, path, err)
		}
	}
	normalizeDefaults(&cfg)
	cfg.MongoDB.URI = "mongodb://127.0.0.1:27017"
	cfg.MongoDB.Database = "integration_test"
	cfg.Integration.ExternalInteraction.SMS.Enabled = false
	return cfg
}

func writeNonEmptyConfigSecret(t *testing.T, name string) string {
	t.Helper()
	path := t.TempDir() + "/" + name
	if err := os.WriteFile(path, []byte("secret-file-placeholder"), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}
