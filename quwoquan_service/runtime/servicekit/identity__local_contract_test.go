package servicekit

import (
	"strings"
	"testing"
)

func clearIdentityEnvironment(t *testing.T) {
	t.Helper()
	for _, key := range []string{
		"SERVICE_CORE_MODE", "APP_ENV", "CONFIG_VERSION", "CONFIG_ROOT",
		"IMAGE_VERSION", "SERVICE_INSTANCE_ID",
	} {
		t.Setenv(key, "")
	}
}

func TestResolveIdentityRequiresServiceName(t *testing.T) {
	clearIdentityEnvironment(t)
	if _, err := ResolveIdentity("  "); err == nil {
		t.Fatal("expected error for blank service name")
	}
}

func TestResolveIdentityRejectsUnknownEnvironment(t *testing.T) {
	clearIdentityEnvironment(t)
	t.Setenv("APP_ENV", "staging")
	_, err := ResolveIdentity("circle-service")
	if err == nil || !strings.Contains(err.Error(), "APP_ENV") {
		t.Fatalf("expected APP_ENV whitelist error, got %v", err)
	}
}

func TestResolveIdentityDefaultsToAlpha(t *testing.T) {
	clearIdentityEnvironment(t)
	identity, err := ResolveIdentity("circle-service")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if identity.AppEnv != "alpha" {
		t.Fatalf("expected alpha default, got %s", identity.AppEnv)
	}
	if identity.ServiceName != "circle-service" {
		t.Fatalf("expected declared service name, got %s", identity.ServiceName)
	}
	if identity.InstanceID == "" {
		t.Fatal("expected a derived instance ID")
	}
}

func TestResolveIdentityRequiresConfigVersionInPinnedEnvironments(t *testing.T) {
	for _, environment := range []string{"gamma", "prod"} {
		t.Run(environment, func(t *testing.T) {
			clearIdentityEnvironment(t)
			t.Setenv("APP_ENV", environment)
			_, err := ResolveIdentity("circle-service")
			if err == nil || !strings.Contains(err.Error(), "CONFIG_VERSION") {
				t.Fatalf("expected CONFIG_VERSION requirement, got %v", err)
			}
			t.Setenv("CONFIG_VERSION", "sha256:abc")
			identity, err := ResolveIdentity("circle-service")
			if err != nil {
				t.Fatalf("unexpected error with CONFIG_VERSION set: %v", err)
			}
			if identity.ConfigVersion != "sha256:abc" {
				t.Fatalf("unexpected config version %s", identity.ConfigVersion)
			}
		})
	}
}

func TestResolveIdentityPrefersInjectedInstanceID(t *testing.T) {
	clearIdentityEnvironment(t)
	t.Setenv("SERVICE_INSTANCE_ID", "pod-7")
	identity, err := ResolveIdentity("circle-service")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if identity.InstanceID != "pod-7" {
		t.Fatalf("expected injected instance ID, got %s", identity.InstanceID)
	}
}

func TestServiceBaseURLKeyNormalization(t *testing.T) {
	cases := map[string]string{
		"content-service": "CONTENT_SERVICE_BASE_URL",
		"platform-ops":    "PLATFORM_OPS_BASE_URL",
		"user-service":    "USER_SERVICE_BASE_URL",
	}
	for input, expected := range cases {
		if actual := ServiceBaseURLKey(input); actual != expected {
			t.Fatalf("ServiceBaseURLKey(%s)=%s, expected %s", input, actual, expected)
		}
	}
}

func TestServiceBaseURLReadsInjectedAddress(t *testing.T) {
	clearIdentityEnvironment(t)
	t.Setenv("CONTENT_SERVICE_BASE_URL", "http://content.internal:18080")
	identity, err := ResolveIdentity("circle-service")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if url := identity.ServiceBaseURL("content-service"); url != "http://content.internal:18080" {
		t.Fatalf("unexpected base URL %q", url)
	}
	if url := identity.ServiceBaseURL("tag-service"); url != "" {
		t.Fatalf("expected empty URL for uninjected dependency, got %q", url)
	}
}
