package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/runtime/servicekit"
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

	cfg := loadIntegrationSnapshot(t)
	if cfg.Service.HTTP.Addr != ":18086" || cfg.MongoDB.Database != "quwoquan_integration" ||
		cfg.Integration.Location.NearbyDefaultLimit != 25 {
		t.Fatalf("canonical snapshot drift: %#v", cfg)
	}
}

func TestSnapshotGuardRejectsRetiredLocationProviderSelection(t *testing.T) {
	if err := integrationconfig.SnapshotGuard(
		[]byte("integration:\n  location:\n    primary_provider: baidu\n"),
	); err == nil {
		t.Fatal("retired runtime provider selection must fail closed")
	}
}

func TestRetiredEnvKeysRejectRetiredLocationProviderSelection(t *testing.T) {
	t.Setenv("INTEGRATION_LOCATION_PROVIDER", "baidu")
	err := servicekit.RejectRetiredEnvKeys(integrationconfig.RetiredEnvKeys())
	if err == nil || !strings.Contains(err.Error(), "INTEGRATION_LOCATION_PROVIDER is retired") {
		t.Fatalf("retired location provider environment selection must fail closed: %v", err)
	}
}

func TestSnapshotGuardRejectsRetiredExternalProviderSelection(t *testing.T) {
	for _, key := range []string{"sms", "push"} {
		t.Run(key, func(t *testing.T) {
			err := integrationconfig.SnapshotGuard(
				[]byte("integration:\n  external_interaction:\n    " + key + ":\n      enabled: true\n"),
			)
			if err == nil || !strings.Contains(err.Error(), "generated external provider binding") {
				t.Fatalf("retired %s config must fail closed: %v", key, err)
			}
		})
	}
}

func TestRetiredEnvKeysRejectRetiredExternalProviderSelection(t *testing.T) {
	for _, key := range []string{"INTEGRATION_SMS_PROVIDER", "INTEGRATION_PUSH_MODE"} {
		t.Run(key, func(t *testing.T) {
			t.Setenv(key, "retired")
			err := servicekit.RejectRetiredEnvKeys(integrationconfig.RetiredEnvKeys())
			if err == nil || !strings.Contains(err.Error(), key+" is retired") {
				t.Fatalf("retired %s override must fail closed: %v", key, err)
			}
		})
	}
}

// loadIntegrationSnapshot 走服务启动的同一条加载路径：身份解析 → 唯一渲染
// 快照 → 退役段守卫。测试不允许存在第二条读取实现。
func loadIntegrationSnapshot(t *testing.T) integrationconfig.Config {
	t.Helper()
	identity, err := servicekit.ResolveIdentity("integration-service")
	if err != nil {
		t.Fatalf("resolve runtime identity: %v", err)
	}
	cfg := integrationconfig.Config{}
	raw, err := servicekit.LoadYAMLConfigRaw(identity, &cfg)
	if err != nil {
		t.Fatalf("load canonical config snapshot: %v", err)
	}
	if err := integrationconfig.SnapshotGuard(raw); err != nil {
		t.Fatalf("canonical snapshot rejected: %v", err)
	}
	cfg.Environment = identity.AppEnv
	return cfg
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
