package local_contract

import (
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"

	serviceclients "quwoquan_service/generated/serviceclients"
	externalprovider "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
	integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"
)

func TestPushConfigAcceptsProtocolSubstituteOnlyOnNonprod(t *testing.T) {
	cfg := validBaseConfigForPushTest()
	cfg.Integration.ExternalInteraction.Push.Enabled = true
	cfg.Integration.ExternalInteraction.Push.Mode = "protocol_substitute"
	cfg.Integration.ExternalInteraction.Push.TimeoutMs = 1000
	cfg.Integration.ExternalInteraction.Push.Endpoint =
		"https://provider-protocol-substitute:18089/push/send"
	for _, appEnv := range []string{"alpha", "beta", "gamma"} {
		cfg.Environment = appEnv
		if err := integrationconfig.Validate(cfg); err != nil {
			t.Fatalf("%s protocol_substitute must be accepted: %v", appEnv, err)
		}
	}
	for _, appEnv := range []string{"prod"} {
		cfg.Environment = appEnv
		if err := integrationconfig.Validate(cfg); err == nil ||
			!strings.Contains(err.Error(), "only permitted in alpha/beta/gamma") {
			t.Fatalf("%s protocol_substitute must fail closed: %v", appEnv, err)
		}
	}
}

func TestPushConfigRealModeFailsFastWithoutSecretFiles(t *testing.T) {
	cfg := validBaseConfigForPushTest()
	cfg.Environment = "prod"
	push := &cfg.Integration.ExternalInteraction.Push
	push.Enabled, push.Mode, push.TimeoutMs = true, "real", 1000
	push.UserServiceBaseURL = "http://user-service:18082"
	push.APNs.Environment = "production"
	push.APNs.KeyFile = filepath.Join(t.TempDir(), "missing-apns.p8")
	push.APNs.KeyID, push.APNs.TeamID, push.APNs.Topic = "APNSKEY01", "TEAM000001", "com.quwoquan.app.voip"
	push.FCM.ServiceAccountFile = filepath.Join(t.TempDir(), "missing-fcm.json")
	push.FCM.ProjectID = "qwq-prod"
	if err := integrationconfig.Validate(cfg); err == nil || !strings.Contains(err.Error(), "APNs key secret file is required") {
		t.Fatalf("prod missing secret file must fail before runtime dependencies: %v", err)
	}
}

func TestPushConfigRealModeRequiresExplicitProductionAPNs(t *testing.T) {
	cfg := validBaseConfigForPushTest()
	cfg.Environment = "prod"
	push := &cfg.Integration.ExternalInteraction.Push
	push.Enabled, push.Mode, push.TimeoutMs = true, "real", 1000
	push.UserServiceBaseURL, push.APNs.Environment = "https://user-service.internal", "sandbox"
	push.APNs.KeyFile = writeNonEmptyConfigSecret(t, "apns.p8")
	push.APNs.KeyID, push.APNs.TeamID, push.APNs.Topic = "APNSKEY01", "TEAM000001", "com.quwoquan.app.voip"
	push.FCM.ServiceAccountFile = writeNonEmptyConfigSecret(t, "fcm.json")
	push.FCM.ProjectID = "qwq-prod"
	if err := integrationconfig.Validate(cfg); err == nil || !strings.Contains(err.Error(), "must be production in prod") {
		t.Fatalf("prod sandbox APNs must fail closed: %v", err)
	}
}

func TestPushObservedEndpointsRedactTokenAndEndpointRef(t *testing.T) {
	apnsRequest := httptest.NewRequest("POST", "https://api.push.apple.com/3/device/plaintext-device-token", nil)
	if got := externalprovider.ObservedEndpoint(apnsRequest); got != "/3/device/{token}" {
		t.Fatalf("APNs log endpoint leaked token: %s", got)
	}
	secretRequest := httptest.NewRequest("GET", "https://user-service.internal"+
		strings.ReplaceAll(serviceclients.UserPushEndpointSecretPathTemplate, "{endpointRef}", strings.Repeat("a", 64)), nil)
	if got := externalprovider.ObservedEndpoint(secretRequest); got != serviceclients.UserPushEndpointSecretPathTemplate {
		t.Fatalf("user secret log endpoint leaked endpointRef: %s", got)
	}
}

func validBaseConfigForPushTest() integrationconfig.Config {
	cfg := integrationconfig.Config{}
	cfg.MongoDB.URI = "mongodb://127.0.0.1:27017"
	cfg.MongoDB.Database = "integration_test"
	cfg.UserAccountSecurityAuthority.BaseURL = "http://user-service:18081"
	cfg.UserAccountSecurityAuthority.TimeoutMs = 300
	return cfg
}

func loadPushEnvironmentConfigForTest(t *testing.T, appEnv string) integrationconfig.Config {
	t.Helper()
	cfg := validBaseConfigForPushTest()
	cfg.Environment = appEnv
	repoRoot := integrationRepositoryRoot(t)
	output := filepath.Join(t.TempDir(), "integration-service.yaml")
	command := exec.Command("python3", filepath.Join(repoRoot, "quwoquan_ops", "cli", "render_runtime_config.py"),
		"--env", appEnv, "--workload", "integration-service", "--output", output)
	command.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
	if combined, err := command.CombinedOutput(); err != nil {
		t.Fatalf("render %s canonical config: %v\n%s", appEnv, err, combined)
	}
	raw, err := os.ReadFile(output)
	if err != nil {
		t.Fatalf("read %s canonical config %s: %v", appEnv, output, err)
	}
	if err := integrationconfig.SnapshotGuard(raw); err != nil {
		t.Fatalf("%s canonical config rejected: %v", appEnv, err)
	}
	if err := yaml.Unmarshal(raw, &cfg); err != nil {
		t.Fatalf("parse %s canonical config %s: %v", appEnv, output, err)
	}
	integrationconfig.NormalizeDefaults(&cfg)
	cfg.MongoDB.URI, cfg.MongoDB.Database = "mongodb://127.0.0.1:27017", "integration_test"
	cfg.Integration.ExternalInteraction.SMS.Enabled = false
	return cfg
}

func writeNonEmptyConfigSecret(t *testing.T, name string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(path, []byte("secret-file-placeholder"), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func integrationRepositoryRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "quwoquan_ops", "cli", "render_runtime_config.py")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("repository root not found above test directory")
		}
		dir = parent
	}
}
