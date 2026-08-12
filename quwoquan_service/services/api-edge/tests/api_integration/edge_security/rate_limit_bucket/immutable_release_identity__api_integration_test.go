// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package api_integration

import (
	"net/http"
	"net/http/httptest"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
)

func TestImmutableReleaseIdentityUsesGeneratedCommercialBoundary(t *testing.T) {
	t.Parallel()
	values := map[string]string{
		"QWQ_RUNTIME_ENVIRONMENT":          "alpha",
		"QWQ_RUNTIME_TARGET":               "alpha-local",
		"QWQ_RUNTIME_CONFIGURATION_DIGEST": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
		"IMAGE_VERSION":                    "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		"CONFIG_VERSION":                   "sha256:2222222222222222222222222222222222222222222222222222222222222222",
	}
	lookup := func(name string) (string, bool) {
		value, ok := values[name]
		return value, ok
	}
	guard, err := rtauth.OperationAuthorizationForRuntime(
		application.AllOperationDescriptors(),
		"alpha",
		lookup,
	)
	if err != nil {
		t.Fatalf("immutable release selected mutable test-live boundary: %v", err)
	}
	ownerCalls := 0
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		ownerCalls++
		w.WriteHeader(http.StatusNoContent)
	}))

	blocked := httptest.NewRecorder()
	handler.ServeHTTP(
		blocked,
		httptest.NewRequest(http.MethodGet, "/assistant/preferences", nil),
	)
	if blocked.Code != http.StatusForbidden {
		t.Fatalf("blocked status=%d want=%d", blocked.Code, http.StatusForbidden)
	}

	ready := httptest.NewRecorder()
	handler.ServeHTTP(
		ready,
		httptest.NewRequest(http.MethodGet, "/assistant/entry", nil),
	)
	if ready.Code != http.StatusUnauthorized {
		t.Fatalf("ready status=%d want=%d", ready.Code, http.StatusUnauthorized)
	}
	if ownerCalls != 0 {
		t.Fatalf("unauthorized generated operations reached owner: %d", ownerCalls)
	}
}
