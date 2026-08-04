// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-006
package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	confighttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/adapters/inbound/http/config_layer"
	configapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/application/config_layer"
	generatedcontrolplane "quwoquan_service/generated/control_plane"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
)

// TestConfigSnapshotHTTPBoundary 覆盖 tests/contract.yaml 的
// config_resolve_reads_release_package_only / config_snapshot_files_and_versions /
// config_domains_catalog：generated 授权 fail-closed + IaC 只读快照语义。
func TestConfigSnapshotHTTPBoundary(t *testing.T) {
	repoRoot := seedConfigSnapshotTree(t)
	guarded := platformConfigAuthenticatedHandler(t, newConfigSnapshotHandler(t, repoRoot))

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
	}
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
	return handler
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
