// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package local_contract

import (
	"net/http"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
)

func TestGeneratedOperationGraphHasOneEdgeGuardAndOneOwner(t *testing.T) {
	descriptors := application.AllOperationDescriptors()
	if err := application.ValidateDescriptorOwners(descriptors); err != nil {
		t.Fatal(err)
	}

	seenRoutes := make(map[string]string, len(descriptors))
	for _, descriptor := range descriptors {
		key := descriptor.Method + " " + descriptor.PathTemplate
		if previous := seenRoutes[key]; previous != "" {
			t.Fatalf(
				"public route %s has two generated owners: %s and %s",
				key,
				previous,
				descriptor.CanonicalOperationID,
			)
		}
		seenRoutes[key] = descriptor.CanonicalOperationID
	}
	defer func() {
		if recovered := recover(); recovered != nil {
			t.Fatalf("generated edge guard cannot compile: %v", recovered)
		}
	}()
	guard := rtauth.RequireGeneratedOperationAuthorization(descriptors)
	if guard == nil {
		t.Fatal("generated edge guard is nil")
	}
	_ = guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
}
