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

	// 迁移到声明式骨架之前，这条判据是「cmd/api/main.go 里
	// controlplane.StartReleaseConfigAttestation( 的文本位置早于
	// rtauth.OperationAuthorizationForRuntime(」。骨架接手镜像身份校验之后，那
	// 两个字面量不再共存于服务源码，但不变量本身存续：servicekit.Bootstrap 在
	// ValidateConfigIdentity 通过之后才调用 OperationGuard 工厂，缺一即拒绝装配。
	//
	// 因此判据从「同一文件里两个调用的先后」迁到「装配确实经过承担该校验的骨架
	// 入口」——依然是不可绕过的文本证据，只是校验发生在骨架而非服务里。api-edge
	// 若改回自建 http.Server 或自行选 guard，本断言立刻变红。
	bootstrapSource, err := os.ReadFile(
		filepath.Join(serviceRoot, "cmd", "api", "bootstrap.go"),
	)
	if err != nil {
		t.Fatal(err)
	}
	source := string(bootstrapSource)
	if !strings.Contains(source, "servicekit.Bootstrap(serviceName, newBootstrapSpec())") {
		t.Fatal(
			"api-edge must assemble through servicekit.Bootstrap, which validates " +
				"the immutable release identity before selecting the operation guard",
		)
	}
	if !strings.Contains(source, "rtauth.OperationAuthorizationForRuntime(") {
		t.Fatal("api-edge must keep selecting the runtime-aware operation boundary")
	}
	if strings.Contains(source, "http.Server{") {
		t.Fatal(
			"api-edge must not build its own HTTP server: that bypasses the " +
				"skeleton's release identity validation",
		)
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
