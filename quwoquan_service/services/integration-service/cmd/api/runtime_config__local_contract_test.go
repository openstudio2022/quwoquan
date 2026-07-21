package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadRuntimeConfigReadsCanonicalVersionedSnapshot(t *testing.T) {
	configRoot := t.TempDir()
	writeRuntimeConfigFile(
		t,
		filepath.Join(
			configRoot,
			"configs",
			"integration-service",
			"default",
			"config.yaml",
		),
		"mongodb:\n  uri: mongodb://mongodb:27017\n  database: quwoquan_integration\n",
	)
	writeRuntimeConfigFile(
		t,
		filepath.Join(
			configRoot,
			"configs",
			"integration-service",
			"gamma",
			"config.yaml",
		),
		"integration:\n  location:\n    nearby_default_limit: 25\n",
	)
	writeRuntimeConfigFile(
		t,
		filepath.Join(
			configRoot,
			"releases",
			"config",
			"integration-service",
			"local-gamma-v1.yaml",
		),
		"service:\n  http:\n    addr: :18086\n",
	)

	t.Setenv("SERVICE_NAME", "integration-service")
	t.Setenv("APP_ENV", "gamma")
	t.Setenv("CONFIG_ROOT", configRoot)
	t.Setenv("CONFIG_VERSION", "local-gamma-v1")

	cfg, err := loadRuntimeConfig()
	if err != nil {
		t.Fatalf("load canonical versioned config snapshot: %v", err)
	}
	if cfg.Service.HTTP.Addr != ":18086" {
		t.Fatalf("service.http.addr = %q, want :18086", cfg.Service.HTTP.Addr)
	}
	if cfg.MongoDB.Database != "quwoquan_integration" {
		t.Fatalf("mongodb.database = %q, want quwoquan_integration", cfg.MongoDB.Database)
	}
	if cfg.Integration.Location.NearbyDefaultLimit != 25 {
		t.Fatalf(
			"integration.location.nearby_default_limit = %d, want 25",
			cfg.Integration.Location.NearbyDefaultLimit,
		)
	}
}

func TestMergeConfigFileRejectsRetiredLocationProviderSelection(t *testing.T) {
	path := filepath.Join(t.TempDir(), "config.yaml")
	writeRuntimeConfigFile(
		t,
		path,
		"integration:\n  location:\n    primary_provider: baidu\n",
	)

	if err := mergeConfigFile(&config{}, path); err == nil {
		t.Fatal("legacy runtime provider selection must fail closed")
	}
}

func TestApplyEnvOverridesRejectsRetiredLocationProviderSelection(t *testing.T) {
	t.Setenv("INTEGRATION_LOCATION_PROVIDER", "baidu")

	if err := applyEnvOverrides(&config{}); err == nil {
		t.Fatal("legacy location provider environment selection must fail closed")
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
