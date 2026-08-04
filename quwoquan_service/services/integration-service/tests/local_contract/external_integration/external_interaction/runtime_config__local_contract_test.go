package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"
	integrationsupport "quwoquan_service/services/integration-service/tests/support"
)

func TestLoadRuntimeConfigReadsCanonicalSnapshot(t *testing.T) {
	configRoot := t.TempDir()
	configDigest := integrationsupport.CanonicalTestSHA256(
		"integration-service:gamma-config",
	)
	writeRuntimeConfigFile(t, filepath.Join(configRoot, "integration-service.yaml"),
		"config:\n  version: "+configDigest+"\nservice:\n  http:\n    addr: :18086\nmongodb:\n  uri: mongodb://mongodb:27017\n  database: quwoquan_integration\nintegration:\n  location:\n    nearby_default_limit: 25\n")
	t.Setenv("SERVICE_NAME", "integration-service")
	t.Setenv("APP_ENV", "gamma")
	t.Setenv("CONFIG_ROOT", configRoot)
	t.Setenv("CONFIG_VERSION", configDigest)

	cfg, err := integrationconfig.Load()
	if err != nil {
		t.Fatalf("load canonical config snapshot: %v", err)
	}
	if cfg.Service.HTTP.Addr != ":18086" || cfg.MongoDB.Database != "quwoquan_integration" ||
		cfg.Integration.Location.NearbyDefaultLimit != 25 {
		t.Fatalf("canonical snapshot drift: %#v", cfg)
	}
}

func TestMergeConfigFileRejectsRetiredLocationProviderSelection(t *testing.T) {
	path := filepath.Join(t.TempDir(), "config.yaml")
	writeRuntimeConfigFile(t, path, "integration:\n  location:\n    primary_provider: baidu\n")
	if err := integrationconfig.MergeFile(&integrationconfig.Config{}, path); err == nil {
		t.Fatal("retired runtime provider selection must fail closed")
	}
}

func TestApplyEnvOverridesRejectsRetiredLocationProviderSelection(t *testing.T) {
	t.Setenv("INTEGRATION_LOCATION_PROVIDER", "baidu")
	if err := integrationconfig.ApplyEnvOverrides(&integrationconfig.Config{}); err == nil {
		t.Fatal("retired location provider environment selection must fail closed")
	}
}

func TestMergeConfigFileRejectsRetiredExternalProviderSelection(t *testing.T) {
	for _, key := range []string{"sms", "push"} {
		t.Run(key, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "config.yaml")
			writeRuntimeConfigFile(
				t,
				path,
				"integration:\n  external_interaction:\n    "+key+":\n      enabled: true\n",
			)
			err := integrationconfig.MergeFile(&integrationconfig.Config{}, path)
			if err == nil || !strings.Contains(err.Error(), "generated external provider binding") {
				t.Fatalf("retired %s config must fail closed: %v", key, err)
			}
		})
	}
}

func TestApplyEnvOverridesRejectsRetiredExternalProviderSelection(t *testing.T) {
	for _, key := range []string{"INTEGRATION_SMS_PROVIDER", "INTEGRATION_PUSH_MODE"} {
		t.Run(key, func(t *testing.T) {
			t.Setenv(key, "retired")
			err := integrationconfig.ApplyEnvOverrides(&integrationconfig.Config{})
			if err == nil || !strings.Contains(err.Error(), "generated external provider binding") {
				t.Fatalf("retired %s override must fail closed: %v", key, err)
			}
		})
	}
}

func writeRuntimeConfigFile(t *testing.T, path string, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir config parent %s: %v", path, err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("write config %s: %v", path, err)
	}
}
