package bootstrap

import (
	"testing"

	"quwoquan_service/runtime/servicekit"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md
func TestResolveContentReleaseFenceBaseURL(t *testing.T) {
	const configuredBaseURL = "http://content-service:18080"
	identity := servicekit.Identity{ServiceName: "tag-service", AppEnv: "gamma"}

	t.Run("service-core projected URL takes precedence", func(t *testing.T) {
		t.Setenv(servicekit.ServiceBaseURLKey("content-service"), "http://127.0.0.1:28080")

		got := resolveContentReleaseFenceBaseURL(identity, configuredBaseURL)
		if got != "http://127.0.0.1:28080" {
			t.Fatalf("content release fence base URL = %q, want projected service-core URL", got)
		}
	})

	t.Run("standalone config remains the fallback", func(t *testing.T) {
		t.Setenv(servicekit.ServiceBaseURLKey("content-service"), "")

		got := resolveContentReleaseFenceBaseURL(identity, configuredBaseURL)
		if got != configuredBaseURL {
			t.Fatalf("content release fence base URL = %q, want standalone config fallback", got)
		}
	})
}
