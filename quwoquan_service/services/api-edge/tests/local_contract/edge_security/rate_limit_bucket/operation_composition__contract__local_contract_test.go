// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package local_contract

import (
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
)

func TestGeneratedRESTOperationGraphHasOneEdgeGuardAndOneOwner(t *testing.T) {
	descriptors := application.AllOperationDescriptors()
	if err := application.ValidateDescriptorOwners(descriptors); err != nil {
		t.Fatal(err)
	}

	seenRoutes := make(map[string]string, len(descriptors))
	graphqlOperations := 0
	for _, descriptor := range descriptors {
		if descriptor.Transport == "graphql" {
			graphqlOperations++
			continue
		}
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
	if graphqlOperations < 2 {
		t.Fatalf("expected shared persisted GraphQL route, operations=%d", graphqlOperations)
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

func TestImmutableReleaseIdentityPrecedesOptionalMutableTestLiveSentinel(t *testing.T) {
	t.Parallel()
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	mainSource, err := os.ReadFile(filepath.Join(serviceRoot, "cmd", "api", "main.go"))
	if err != nil {
		t.Fatal(err)
	}
	attestation := strings.Index(string(mainSource), "controlplane.StartReleaseConfigAttestation(")
	authorization := strings.Index(string(mainSource), "rtauth.OperationAuthorizationForRuntime(")
	if attestation < 0 || authorization < 0 || attestation >= authorization {
		t.Fatal("immutable release identity must be validated before operation authorization selection")
	}

	compose, err := os.ReadFile(filepath.Join(serviceRoot, "deploy", "compose.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	text := string(compose)
	for _, required := range []string{
		`CONFIG_VERSION: "${QWQ_COMPOSE_API_EDGE_CONFIG_VERSION:?api-edge config version is required}"`,
		`IMAGE_VERSION: "${QWQ_COMPOSE_IMAGE_VERSION:?immutable image version is required}"`,
		`QWQ_RUNTIME_IDENTITY_SCHEMA: "${QWQ_RUNTIME_IDENTITY_SCHEMA:-}"`,
	} {
		if !strings.Contains(text, required) {
			t.Fatalf("api-edge release/mutable identity composition drifted: missing %s", required)
		}
	}
}
