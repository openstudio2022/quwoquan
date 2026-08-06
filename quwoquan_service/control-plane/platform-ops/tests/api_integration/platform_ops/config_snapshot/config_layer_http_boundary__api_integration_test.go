// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-006
// readiness_case: list-service-configs-api
// readiness_case: resolve-effective-config-api
// readiness_case: resolve-effective-config-for-instance-api
// readiness_case: get-config-snapshot-api
// readiness_case: list-config-domains-api
// readiness_case: list-service-catalog-entries-api
// readiness_case: list-plane-bindings-api
// readiness_case: get-prod-plane-access-isolation-api
// readiness_case: get-gray-routing-policy-api
// readiness_case: list-environment-topologies-api
// readiness_case: list-runtime-clusters-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	confighttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/adapters/inbound/http/config_layer"
	configapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/application/config_layer"
	configrepository "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/infrastructure/repository"
	generatedcontrolplane "quwoquan_service/generated/control_plane"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
)

// TestConfigSnapshotHTTPBoundary 覆盖 tests/contract.yaml 的
// config_resolve_reads_release_package_only / config_snapshot_files_and_versions /
// config_domains_catalog：generated 授权 fail-closed + IaC 只读快照语义。
func TestConfigSnapshotHTTPBoundary(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	fixture, err := testinfra.StartPostgresFixture(t.TempDir()+"/postgres", 0)
	if err != nil {
		t.Fatalf("start embedded PostgreSQL: %v", err)
	}
	t.Cleanup(func() { _ = fixture.Close() })
	pool, err := pgxpool.New(ctx, fixture.DSN())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	store, err := controlplanepersistence.NewPostgresStore(pool, "platform-ops-config-snapshot")
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	var databaseReady int
	if err := pool.QueryRow(ctx, "SELECT 1").Scan(&databaseReady); err != nil || databaseReady != 1 {
		t.Fatalf("embedded PostgreSQL readiness=%d err=%v", databaseReady, err)
	}

	repoRoot := seedConfigSnapshotTree(t)
	rawHandler := newConfigSnapshotHandler(t, repoRoot)
	guarded := platformConfigAuthenticatedHandler(t, rawHandler)

	unauthorized := performPlatformConfigRequest(
		guarded, http.MethodGet, "/control-plane/platform/configs/resolve?env=gamma&service=content-service", "", "",
	)
	assertPlatformConfigError(t, unauthorized, http.StatusUnauthorized, "GATEWAY.USER.unauthorized")

	readToken := platformConfigAccessToken(t, "ops.platform.config.read")

	resolved := performPlatformConfigRequest(
		guarded, http.MethodGet,
		"/control-plane/platform/configs/resolve?env=gamma&service=content-service",
		"", readToken,
	)
	if resolved.Code != http.StatusOK {
		t.Fatalf("resolve status=%d body=%s", resolved.Code, resolved.Body.String())
	}
	var resolveResponse controlplane.ConfigResolveResponse
	if err := json.Unmarshal(resolved.Body.Bytes(), &resolveResponse); err != nil {
		t.Fatalf("decode resolve: %v", err)
	}
	if resolveResponse.Source != "release-package" || resolveResponse.DesiredHash == "" {
		t.Fatalf("resolve must read release package snapshot: %+v", resolveResponse)
	}
	foundOverride := false
	for _, value := range resolveResponse.Values {
		if value.Key == "sys.content-service.embedding.enabled" {
			foundOverride = true
			if got, _ := value.Value.(bool); !got {
				t.Fatalf("environment override must win: got %v want true", value.Value)
			}
			if value.SourceLayer == "config_schema" {
				t.Fatalf("override source must be a release package file: %+v", value)
			}
		}
	}
	if !foundOverride {
		t.Fatalf("resolve must include sys.content-service.embedding.enabled")
	}

	missingEnv := performPlatformConfigRequest(
		guarded, http.MethodGet, "/control-plane/platform/configs/resolve", "", readToken,
	)
	assertPlatformConfigError(t, missingEnv, http.StatusBadRequest, "OPS.USER.config_invalid")

	snapshot := performPlatformConfigRequest(
		guarded, http.MethodGet,
		"/control-plane/platform/configs/snapshot?env=gamma&service=content-service",
		"", readToken,
	)
	if snapshot.Code != http.StatusOK {
		t.Fatalf("snapshot status=%d body=%s", snapshot.Code, snapshot.Body.String())
	}
	var view configapp.ConfigSnapshotView
	if err := json.Unmarshal(snapshot.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode snapshot: %v", err)
	}
	if view.Domain != "cloud-service" || len(view.Files) == 0 || view.MergedSha256 == "" {
		t.Fatalf("snapshot must expose files and merged digest: %+v", view)
	}
	if len(view.ReleaseVersions) != 0 {
		t.Fatalf("repo mode must not invent release versions: %v", view.ReleaseVersions)
	}
	for _, file := range view.Files {
		if file.SHA256 == "" || file.Content == "" {
			t.Fatalf("snapshot file must expose sha256+content: %+v", file)
		}
	}

	unknown := performPlatformConfigRequest(
		guarded, http.MethodGet,
		"/control-plane/platform/configs/snapshot?env=gamma&service=missing-service",
		"", readToken,
	)
	assertPlatformConfigError(t, unknown, http.StatusNotFound, "OPS.USER.config_snapshot_not_found")

	domains := performPlatformConfigRequest(
		guarded, http.MethodGet, "/control-plane/platform/configs/domains", "", readToken,
	)
	if domains.Code != http.StatusOK {
		t.Fatalf("domains status=%d body=%s", domains.Code, domains.Body.String())
	}
	var domainSlice configapp.ConfigDomainSlice
	if err := json.Unmarshal(domains.Body.Bytes(), &domainSlice); err != nil {
		t.Fatalf("decode domains: %v", err)
	}
	domainSet := map[string]bool{}
	for _, item := range domainSlice.Items {
		domainSet[item.Domain] = true
	}
	for _, want := range []string{"cloud-service", "app", "data"} {
		if !domainSet[want] {
			t.Fatalf("domain catalog missing %q", want)
		}
	}

	catalog := performPlatformConfigRequest(
		guarded, http.MethodGet, "/control-plane/platform/configs", "", readToken,
	)
	if catalog.Code != http.StatusOK || !strings.Contains(catalog.Body.String(), `"uiEditable":false`) {
		t.Fatalf("config key catalog must be read-only (uiEditable=false): status=%d body=%s", catalog.Code, catalog.Body.String())
	}
	if strings.Contains(catalog.Body.String(), `"uiEditable":true`) {
		t.Fatalf("IaC catalog must not expose editable keys: %s", catalog.Body.String())
	}

	instanceRequest := httptest.NewRequest(
		http.MethodGet,
		"/control-plane/platform/configs/resolve-for-instance?env=gamma&service=content-service",
		nil,
	)
	instanceRequest = instanceRequest.WithContext(rtauth.WithPrincipal(
		instanceRequest.Context(),
		rtauth.Principal{
			Claims: rtauth.Claims{Roles: []string{"service"}},
			Actor:  operation.ActorContext{AccountID: "service:content-service@gamma"},
		},
	))
	instanceResponse := httptest.NewRecorder()
	rawHandler.ServeHTTP(instanceResponse, instanceRequest)
	if instanceResponse.Code != http.StatusOK {
		t.Fatalf(
			"instance resolve status=%d body=%s",
			instanceResponse.Code,
			instanceResponse.Body.String(),
		)
	}

	topologyToken := platformConfigAccessToken(t, "ops.platform.catalog.read ops.platform.dependency.read ops.platform.rollout.read")
	for _, testCase := range []struct {
		path      string
		itemCount int
	}{
		{"/control-plane/platform/catalog/services", 2},
		{"/control-plane/platform/topology/planes", 8},
		{"/control-plane/platform/topology/environments", 8},
		{"/control-plane/platform/topology/clusters", 4},
	} {
		response := performPlatformConfigRequest(guarded, http.MethodGet, testCase.path, "", topologyToken)
		if response.Code != http.StatusOK {
			t.Fatalf("GET %s status=%d body=%s", testCase.path, response.Code, response.Body.String())
		}
		var payload map[string]any
		if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
			t.Fatal(err)
		}
		if items, ok := payload["items"].([]any); !ok || len(items) != testCase.itemCount {
			t.Fatalf("GET %s items=%+v", testCase.path, payload["items"])
		}
	}
	isolation := performPlatformConfigRequest(
		guarded, http.MethodGet, "/control-plane/platform/topology/prod-plane-access-isolation", "", topologyToken,
	)
	if isolation.Code != http.StatusOK {
		t.Fatalf("isolation status=%d body=%s", isolation.Code, isolation.Body.String())
	}
	var isolationPayload map[string]any
	if err := json.Unmarshal(isolation.Body.Bytes(), &isolationPayload); err != nil {
		t.Fatal(err)
	}
	if isolationPayload["directAccessAllowed"] != false || len(isolationPayload["plane"].([]any)) != 4 {
		t.Fatalf("isolation=%+v", isolationPayload)
	}
	gray := performPlatformConfigRequest(
		guarded, http.MethodGet, "/control-plane/platform/rollout/routing-policy", "", topologyToken,
	)
	if gray.Code != http.StatusOK {
		t.Fatalf("gray policy status=%d body=%s", gray.Code, gray.Body.String())
	}
	var grayPayload map[string]any
	if err := json.Unmarshal(gray.Body.Bytes(), &grayPayload); err != nil {
		t.Fatal(err)
	}
	if grayPayload["policy"].(map[string]any)["enabled"] != true || grayPayload["source"].(map[string]any)["sha256"] == "" {
		t.Fatalf("gray policy=%+v", grayPayload)
	}
}

// TestConfigWriteRoutesRetiredAPI 覆盖 config_write_routes_retired：
// 写路径与 layers 视图在 HTTP 边界彻底退场。
func TestConfigWriteRoutesRetiredAPI(t *testing.T) {
	repoRoot := seedConfigSnapshotTree(t)
	guarded := platformConfigAuthenticatedHandler(t, newConfigSnapshotHandler(t, repoRoot))
	writeToken := platformConfigAccessToken(t, "ops.platform.config.read ops.platform.config.write")

	update := performPlatformConfigRequest(
		guarded, http.MethodPost,
		"/control-plane/platform/configs/sys.content-service.embedding.enabled:update",
		`{"value":{"kind":"int","intValue":130}}`, writeToken,
	)
	if update.Code == http.StatusOK {
		t.Fatalf("config write endpoint must be retired, got 200: %s", update.Body.String())
	}

	layers := performPlatformConfigRequest(
		guarded, http.MethodGet, "/control-plane/platform/configs/layers", "", writeToken,
	)
	if layers.Code == http.StatusOK {
		t.Fatalf("config layers endpoint must be retired, got 200: %s", layers.Body.String())
	}
}

func seedConfigSnapshotTree(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	mustWrite := func(path, content string) {
		t.Helper()
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("mkdir: %v", err)
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			t.Fatalf("write: %v", err)
		}
	}
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		content := "overrides: {}\nsecretRefs: {}\n"
		if environment == "gamma" {
			content = "overrides:\n  sys.content-service.embedding.enabled: true\nsecretRefs: {}\n"
		}
		mustWrite(filepath.Join(root, "quwoquan_service", "services", "content-service", "environments", environment, "config.yaml"), content)
		mustWrite(filepath.Join(root, "quwoquan_service", "services", "content-service", "environments", environment, "deploy", "kustomization.yaml"), "resources: []\n")
		target := environment + "-local"
		if environment == "prod" {
			target = "prod-hosted"
		}
		mustWrite(filepath.Join(root, "quwoquan_ops", "environments", environment, "runtime.yaml"),
			"targets:\n  "+target+":\n    env: "+environment+"\n")
	}
	if err := os.MkdirAll(filepath.Join(root, "quwoquan_ops", "external"), 0o755); err != nil {
		t.Fatal(err)
	}
	mustWrite(filepath.Join(root, "quwoquan_ops", "platform", "deploy", "base", "kustomization.yaml"), "resources: []\n")
	mustWrite(filepath.Join(root, "quwoquan_ops", "environments", "prod", "rollout", "routing_policy.yaml"), `policy:
  enabled: true
  grayUpstream: http://gray.internal
  grayUpstreamTlsInsecureSkipVerify: false
  stageDimensions:
    gray-initial: {appVersions: [], userIds: [canary], provinces: [], carriers: []}
    carry-on: {appVersions: ["1.1.0"], userIds: [canary], provinces: [], carriers: []}
    full: {appVersions: [], userIds: [], provinces: [], carriers: []}
`)
	mustWrite(filepath.Join(root, "quwoquan_ops", "environments", "prod", "access-isolation.yaml"), `schema: prod-plane-access-isolation
target: prod-hosted
relayAccount: {name: prod-ops}
planes:
  - {plane: edge, account: prod-edge-svc, sshKeySecret: PROD_EDGE_SSH_KEY, access: read-write, runtimeContainer: rootless-podman, appliesToStages: [gray-initial, carry-on, full]}
  - {plane: media, account: prod-media-svc, sshKeySecret: PROD_MEDIA_SSH_KEY, access: read-write, runtimeContainer: rootless-podman, appliesToStages: [gray-initial, carry-on, full]}
  - {plane: service, account: prod-service-svc, sshKeySecret: PROD_SERVICE_SSH_KEY, access: read-write, runtimeContainer: rootless-podman, appliesToStages: [gray-initial, carry-on, full]}
  - {plane: data, account: prod-data-svc, sshKeySecret: PROD_DATA_SSH_KEY, access: read-only-audit, runtimeContainer: rootless-podman, appliesToStages: [gray-initial, carry-on, full]}
`)
	mustWrite(filepath.Join(root, "quwoquan_app", "configs", "gamma", "app_runtime.yaml"),
		"gatewayBaseUrl: https://gamma.example.test\n")
	mustWrite(filepath.Join(root, "quwoquan_data", "control_plane", "_shared", "catalogs", "region_catalog.yaml"),
		"regions: []\n")
	return root
}

func newConfigSnapshotHandler(t *testing.T, repoRoot string) http.Handler {
	t.Helper()
	catalog, err := configapp.NewConfigKeyCatalog(generatedcontrolplane.MustLoadPlatformConfig())
	if err != nil {
		t.Fatalf("build generated config catalog: %v", err)
	}
	source, err := configapp.NewSnapshotSource("", repoRoot)
	if err != nil {
		t.Fatalf("build snapshot source: %v", err)
	}
	facade, err := configapp.NewFacade(source, catalog)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := confighttp.NewHandler(facade)
	if err != nil {
		t.Fatal(err)
	}
	topologySource, err := configrepository.NewTopologySource(repoRoot, "")
	if err != nil {
		t.Fatal(err)
	}
	topologyFacade, err := configapp.NewTopologyFacade(topologySource)
	if err != nil {
		t.Fatal(err)
	}
	topologyHandler, err := confighttp.NewTopologyHandler(topologyFacade)
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	for _, path := range []string{
		"/control-plane/platform/configs", "/control-plane/platform/configs/resolve",
		"/control-plane/platform/configs/resolve-for-instance", "/control-plane/platform/configs/snapshot",
		"/control-plane/platform/configs/domains",
	} {
		mux.Handle(path, handler)
	}
	for _, path := range []string{
		"/control-plane/platform/catalog/services", "/control-plane/platform/topology/planes",
		"/control-plane/platform/topology/prod-plane-access-isolation", "/control-plane/platform/rollout/routing-policy",
		"/control-plane/platform/topology/environments", "/control-plane/platform/topology/clusters",
	} {
		mux.Handle(path, topologyHandler)
	}
	return mux
}

func platformConfigAuthenticatedHandler(t *testing.T, next http.Handler) http.Handler {
	t.Helper()
	verifier, err := rtauth.NewHS256Verifier(platformConfigTokenConfig())
	if err != nil {
		t.Fatal(err)
	}
	next = rtauth.RequireGeneratedOperationAuthorization(operationsecurity.ForDomain("ops"))(next)
	return rtauth.Middleware(rtauth.MiddlewareConfig{AccessTokenVerifier: verifier})(next)
}

func platformConfigAccessToken(t *testing.T, scopes string) string {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(platformConfigTokenConfig())
	if err != nil {
		t.Fatal(err)
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "platform-operator", Scopes: strings.Fields(scopes), Roles: []string{"operator"},
	})
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func platformConfigTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret: []byte("platform-ops-api-integration-secret-32bytes"),
		Issuer: "platform-ops-api-integration", Audience: "quwoquan-api",
		Type: rtauth.TokenTypeAccess, TokenVersion: 1, TTL: 5 * time.Minute, ClockSkew: time.Second,
	}
}

func performPlatformConfigRequest(
	handler http.Handler,
	method, path, body, token string,
) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	if token != "" {
		request.Header.Set("Authorization", "Bearer "+token)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertPlatformConfigError(t *testing.T, recorder *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("error status=%d want=%d body=%s", recorder.Code, status, recorder.Body.String())
	}
	var response rterr.ErrorResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response: %v body=%s", err, recorder.Body.String())
	}
	if response.Code != code {
		t.Fatalf("error code=%q want=%q body=%s", response.Code, code, recorder.Body.String())
	}
}

func asFloat(value any) float64 {
	switch typed := value.(type) {
	case float64:
		return typed
	case int:
		return float64(typed)
	default:
		return -1
	}
}
