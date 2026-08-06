// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-001
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestGetAppRecoveryVersionNeedsNoSyntheticDeviceActor(t *testing.T) {
	t.Parallel()

	var document struct {
		APIRoutes []struct {
			Operation   string `yaml:"operation"`
			Actor       string `yaml:"actor"`
			Application struct {
				Kind string `yaml:"kind"`
			} `yaml:"application"`
			Authorization struct {
				Principal       string `yaml:"principal"`
				OwnershipPolicy string `yaml:"ownership_policy"`
			} `yaml:"authorization"`
			Security struct {
				AuthMode        string `yaml:"auth_mode"`
				Principal       string `yaml:"principal"`
				TokenTransport  string `yaml:"token_transport"`
				AnonymousPolicy string `yaml:"anonymous_policy"`
				Visibility      string `yaml:"visibility"`
			} `yaml:"security"`
		} `yaml:"api_routes"`
	}
	payload, err := os.ReadFile(appReleaseOperationsSource(t))
	if err != nil {
		t.Fatalf("read AppRelease operations: %v", err)
	}
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatalf("parse AppRelease operations: %v", err)
	}
	if len(document.APIRoutes) != 1 {
		t.Fatalf("AppRelease routes=%d, want 1", len(document.APIRoutes))
	}
	route := document.APIRoutes[0]
	if route.Operation != "GetAppRecoveryVersion" ||
		route.Actor != "none" ||
		route.Application.Kind != "query" ||
		route.Authorization.Principal != "public" ||
		route.Authorization.OwnershipPolicy != "public_recovery_read" ||
		route.Security.AuthMode != "optional" ||
		route.Security.Principal != "public" ||
		route.Security.TokenTransport != "none" ||
		route.Security.AnonymousPolicy != "allow" ||
		route.Security.Visibility != "public" {
		t.Fatalf("GetAppRecoveryVersion anonymous/network admission contract drifted: %+v", route)
	}
}

func appReleaseOperationsSource(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Clean(filepath.Join(
		filepath.Dir(file),
		"..", "..", "..", "..",
		"contracts", "product_ops", "app_release", "operations.yaml",
	))
}
