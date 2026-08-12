// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-006
// readiness_case: list-service-configs-local
// readiness_case: resolve-effective-config-local
// readiness_case: resolve-effective-config-for-instance-local
// readiness_case: get-config-snapshot-local
// readiness_case: list-config-domains-local
// readiness_case: list-service-catalog-entries-local
// readiness_case: list-plane-bindings-local
// readiness_case: get-prod-plane-access-isolation-local
// readiness_case: get-gray-routing-policy-local
// readiness_case: list-environment-topologies-local
// readiness_case: list-runtime-clusters-local
package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	confighttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/adapters/inbound/http/config_layer"
	configapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/application/config_layer"
	configrepository "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/infrastructure/repository"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	"quwoquan_service/runtime/operation"
)

// seedSnapshotRepo 构造仓库模式的最小配置树：
// 一个云侧服务（content-service）+ 端侧 App + 数据工程 catalog。
func seedSnapshotRepo(t *testing.T) string {
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
  campaignId: release-test-001
  candidateDigest: sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
  allocationKeyId: rollout-test-001
  subjectKind: device_actor
  stage: "5"
  status: active
  candidateUpstream: http://candidate.internal
  assignmentTtlDaysAfterCampaign: 30
  internalCanary: {accountIds: [canary], deviceActorIds: []}
  stages:
    canary: {basisPoints: 0, appVersions: {mode: supported, values: []}, platforms: {mode: include, values: [android, ios, web]}, regions: {mode: all, values: []}, carriers: {mode: all, values: []}}
    "5": {basisPoints: 500, appVersions: {mode: supported, values: []}, platforms: {mode: include, values: [android, ios, web]}, regions: {mode: all, values: []}, carriers: {mode: all, values: []}}
    "20": {basisPoints: 2000, appVersions: {mode: supported, values: []}, platforms: {mode: include, values: [android, ios, web]}, regions: {mode: all, values: []}, carriers: {mode: all, values: []}}
    "50": {basisPoints: 5000, appVersions: {mode: supported, values: []}, platforms: {mode: include, values: [android, ios, web]}, regions: {mode: all, values: []}, carriers: {mode: all, values: []}}
    "100": {basisPoints: 10000, appVersions: {mode: supported, values: []}, platforms: {mode: include, values: [android, ios, web]}, regions: {mode: all, values: []}, carriers: {mode: all, values: []}}
`)
	mustWrite(filepath.Join(root, "quwoquan_ops", "environments", "prod", "access-isolation.yaml"), `schema: prod-plane-access-isolation
target: prod-hosted
relayAccount: {name: prod-ops}
planes:
  - {plane: edge, account: prod-edge-svc, sshKeySecret: PROD_EDGE_SSH_KEY, access: read-write, runtimeContainer: rootless-podman, appliesToStages: [canary, "5", "20", "50", "100"]}
  - {plane: media, account: prod-media-svc, sshKeySecret: PROD_MEDIA_SSH_KEY, access: read-write, runtimeContainer: rootless-podman, appliesToStages: [canary, "5", "20", "50", "100"]}
  - {plane: service, account: prod-service-svc, sshKeySecret: PROD_SERVICE_SSH_KEY, access: read-write, runtimeContainer: rootless-podman, appliesToStages: [canary, "5", "20", "50", "100"]}
  - {plane: data, account: prod-data-svc, sshKeySecret: PROD_DATA_SSH_KEY, access: read-only-audit, runtimeContainer: rootless-podman, appliesToStages: [canary, "5", "20", "50", "100"]}
`)
	mustWrite(filepath.Join(root, "quwoquan_app", "configs", "gamma", "app_runtime.yaml"),
		"gatewayBaseUrl: https://gamma.example.test\n")
	mustWrite(filepath.Join(root, "quwoquan_data", "control_plane", "_shared", "catalogs", "region_catalog.yaml"),
		"regions: []\n")
	return root
}

func newSnapshotTopologyHandler(t *testing.T, repoRoot string) http.Handler {
	t.Helper()
	source, err := configrepository.NewTopologySource(repoRoot, "")
	if err != nil {
		t.Fatal(err)
	}
	facade, err := configapp.NewTopologyFacade(source)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := confighttp.NewTopologyHandler(facade)
	if err != nil {
		t.Fatal(err)
	}
	return handler
}

func newSnapshotHandler(t *testing.T, repoRoot string) http.Handler {
	t.Helper()
	catalog, err := configapp.NewConfigKeyCatalog(map[string]any{
		"configs": []any{
			map[string]any{
				"key": "sys.content-service.embedding.enabled", "type": "bool", "owner": "platform-ops",
				"default": false, "scope": "workload", "reload": "restart", "risk_level": "medium",
				"ui_editable": false,
			},
			map[string]any{"key": "sys.error_message", "key_namespace": true, "type": "string"},
		},
	})
	if err != nil {
		t.Fatalf("build catalog: %v", err)
	}
	source, err := configapp.NewSnapshotSource("", repoRoot)
	if err != nil {
		t.Fatalf("build snapshot source: %v", err)
	}
	facade, err := configapp.NewFacade(source, catalog)
	if err != nil {
		t.Fatalf("build facade: %v", err)
	}
	handler, err := confighttp.NewHandler(facade)
	if err != nil {
		t.Fatalf("build handler: %v", err)
	}
	return handler
}

func TestConfigSnapshotResolveUsesReleasePackageOverrides(t *testing.T) {
	handler := newSnapshotHandler(t, seedSnapshotRepo(t))

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/control-plane/platform/configs/resolve?env=gamma&service=content-service", nil)
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("resolve status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var resolved controlplane.ConfigResolveResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &resolved); err != nil {
		t.Fatalf("decode resolve: %v", err)
	}
	if resolved.Source != "release-package" {
		t.Fatalf("resolve source=%q want release-package", resolved.Source)
	}
	if resolved.DesiredHash == "" || resolved.DesiredHash != resolved.EffectiveHash {
		t.Fatalf("central resolve must expose desired==effective hash: %+v", resolved)
	}
	var poolSize any
	var sourceLayer string
	for _, value := range resolved.Values {
		if value.Key == "sys.content-service.embedding.enabled" {
			poolSize = value.Value
			sourceLayer = value.SourceLayer
		}
	}
	if enabled, _ := poolSize.(bool); !enabled {
		t.Fatalf("env override must win: got %v (source=%s)", poolSize, sourceLayer)
	}
	if sourceLayer == "config_schema" {
		t.Fatalf("override source must be a release package file, got %s", sourceLayer)
	}

	missingEnv := httptest.NewRecorder()
	handler.ServeHTTP(missingEnv, httptest.NewRequest(http.MethodGet, "/control-plane/platform/configs/resolve", nil))
	if missingEnv.Code != http.StatusBadRequest {
		t.Fatalf("resolve without env status=%d want 400", missingEnv.Code)
	}
}

func TestInstanceResolveBindsServiceAndEnvironmentToMachinePrincipal(t *testing.T) {
	handler := newSnapshotHandler(t, seedSnapshotRepo(t))
	request := httptest.NewRequest(
		http.MethodGet,
		"/control-plane/platform/configs/resolve-for-instance?env=gamma&service=content-service",
		nil,
	)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{Roles: []string{"service"}},
		Actor:  operation.ActorContext{AccountID: "service:content-service@gamma"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("machine resolve status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	for _, query := range []string{
		"env=prod&service=content-service",
		"env=gamma&service=other-service",
	} {
		t.Run(query, func(t *testing.T) {
			forged := httptest.NewRequest(
				http.MethodGet,
				"/control-plane/platform/configs/resolve-for-instance?"+query,
				nil,
			)
			forged = forged.WithContext(rtauth.WithPrincipal(forged.Context(), rtauth.Principal{
				Claims: rtauth.Claims{Roles: []string{"service"}},
				Actor:  operation.ActorContext{AccountID: "service:content-service@gamma"},
			}))
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, forged)
			if response.Code == http.StatusOK {
				t.Fatalf("forged machine scope must be rejected: %s", response.Body.String())
			}
		})
	}
}

func TestConfigSnapshotViewCoversAllDomains(t *testing.T) {
	handler := newSnapshotHandler(t, seedSnapshotRepo(t))

	cases := []struct {
		query        string
		wantDomain   string
		wantFiles    int
		wantReleases int
	}{
		{"env=gamma&service=content-service", "cloud-service", 1, 0},
		{"env=gamma&service=app", "app", 1, 0},
		{"env=gamma&service=data", "data", 1, 0},
	}
	for _, testCase := range cases {
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/control-plane/platform/configs/snapshot?"+testCase.query, nil))
		if recorder.Code != http.StatusOK {
			t.Fatalf("%s status=%d body=%s", testCase.query, recorder.Code, recorder.Body.String())
		}
		var view configapp.ConfigSnapshotView
		if err := json.Unmarshal(recorder.Body.Bytes(), &view); err != nil {
			t.Fatalf("decode snapshot: %v", err)
		}
		if view.Domain != testCase.wantDomain {
			t.Fatalf("%s domain=%q want %q", testCase.query, view.Domain, testCase.wantDomain)
		}
		if len(view.Files) != testCase.wantFiles {
			t.Fatalf("%s files=%d want %d", testCase.query, len(view.Files), testCase.wantFiles)
		}
		if len(view.ReleaseVersions) != testCase.wantReleases {
			t.Fatalf("%s releases=%v want %d", testCase.query, view.ReleaseVersions, testCase.wantReleases)
		}
		for _, file := range view.Files {
			if file.SHA256 == "" || file.Content == "" || file.Path == "" {
				t.Fatalf("%s snapshot file must expose path/sha256/content: %+v", testCase.query, file)
			}
		}
		if view.MergedSha256 == "" {
			t.Fatalf("%s mergedSha256 must be present", testCase.query)
		}
	}

	unknown := httptest.NewRecorder()
	handler.ServeHTTP(unknown, httptest.NewRequest(http.MethodGet, "/control-plane/platform/configs/snapshot?env=gamma&service=nope-service", nil))
	if unknown.Code != http.StatusNotFound {
		t.Fatalf("unknown service status=%d want 404", unknown.Code)
	}
}

func TestConfigWriteRoutesRetired(t *testing.T) {
	handler := newSnapshotHandler(t, seedSnapshotRepo(t))

	update := httptest.NewRecorder()
	handler.ServeHTTP(update, httptest.NewRequest(
		http.MethodPost,
		"/control-plane/platform/configs/sys.content.mongo.max_pool_size:update",
		nil,
	))
	if update.Code != http.StatusBadRequest && update.Code != http.StatusNotFound {
		t.Fatalf("write route must be retired, status=%d", update.Code)
	}

	layers := httptest.NewRecorder()
	handler.ServeHTTP(layers, httptest.NewRequest(http.MethodGet, "/control-plane/platform/configs/layers", nil))
	if layers.Code != http.StatusBadRequest && layers.Code != http.StatusNotFound {
		t.Fatalf("layers route must be retired, status=%d", layers.Code)
	}
}

func TestConfigDomainsCatalog(t *testing.T) {
	handler := newSnapshotHandler(t, seedSnapshotRepo(t))
	catalog := httptest.NewRecorder()
	handler.ServeHTTP(catalog, httptest.NewRequest(
		http.MethodGet,
		"/control-plane/platform/configs",
		nil,
	))
	if catalog.Code != http.StatusOK {
		t.Fatalf("config catalog status=%d body=%s", catalog.Code, catalog.Body.String())
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/control-plane/platform/configs/domains", nil))
	if recorder.Code != http.StatusOK {
		t.Fatalf("domains status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var domains configapp.ConfigDomainSlice
	if err := json.Unmarshal(recorder.Body.Bytes(), &domains); err != nil {
		t.Fatalf("decode domains: %v", err)
	}
	got := map[string]bool{}
	for _, item := range domains.Items {
		got[item.Domain] = true
	}
	for _, want := range []string{"cloud-service", "app", "data"} {
		if !got[want] {
			t.Fatalf("domain catalog missing %q: %+v", want, domains.Items)
		}
	}
}

func TestConfigSnapshotTopologyOperationsUseRepositoryTruth(t *testing.T) {
	handler := newSnapshotTopologyHandler(t, seedSnapshotRepo(t))

	catalog := performTopologyRequest(t, handler, "/control-plane/platform/catalog/services")
	assertTopologyItems(t, catalog, 2)
	bindings := performTopologyRequest(t, handler, "/control-plane/platform/topology/planes")
	assertTopologyItems(t, bindings, 8)
	isolation := performTopologyRequest(t, handler, "/control-plane/platform/topology/prod-plane-access-isolation")
	if isolation["environment"] != "prod" || isolation["directAccessAllowed"] != false {
		t.Fatalf("isolation=%+v", isolation)
	}
	if planes, ok := isolation["plane"].([]any); !ok || len(planes) != 4 {
		t.Fatalf("isolation planes=%+v", isolation["plane"])
	}
	evidence := isolation["evidence"].(map[string]any)
	source := evidence["source"].(map[string]any)
	if source["path"] == "" || source["sha256"] == "" {
		t.Fatalf("isolation source=%+v", source)
	}
	gray := performTopologyRequest(t, handler, "/control-plane/platform/rollout/routing-policy")
	policy := gray["policy"].(map[string]any)
	if policy["enabled"] != true || policy["subjectKind"] != "device_actor" ||
		len(policy["stages"].(map[string]any)) != 5 {
		t.Fatalf("rollout policy=%+v", policy)
	}
	environments := performTopologyRequest(t, handler, "/control-plane/platform/topology/environments")
	assertTopologyItems(t, environments, 8)
	clusters := performTopologyRequest(t, handler, "/control-plane/platform/topology/clusters")
	assertTopologyItems(t, clusters, 4)
}

func performTopologyRequest(t *testing.T, handler http.Handler, path string) map[string]any {
	t.Helper()
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, path, nil))
	if response.Code != http.StatusOK {
		t.Fatalf("GET %s status=%d body=%s", path, response.Code, response.Body.String())
	}
	var payload map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("GET %s decode: %v", path, err)
	}
	return payload
}

func assertTopologyItems(t *testing.T, payload map[string]any, expected int) {
	t.Helper()
	items, ok := payload["items"].([]any)
	if !ok || len(items) != expected {
		t.Fatalf("items=%+v expected=%d", payload["items"], expected)
	}
}

func asInt(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case float64:
		return int(typed)
	default:
		return -1
	}
}
