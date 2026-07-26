package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	confighttp "quwoquan_service/control-plane/platform-ops/internal/ops/platform_ops/config_snapshot/adapters/inbound/http/config_layer"
	configapp "quwoquan_service/control-plane/platform-ops/internal/ops/platform_ops/config_snapshot/application/platform_ops/config_layer"
	"quwoquan_service/runtime/controlplane"
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
	}
	mustWrite(filepath.Join(root, "quwoquan_app", "configs", "gamma", "app_runtime.yaml"),
		"gatewayBaseUrl: https://gamma.example.test\n")
	mustWrite(filepath.Join(root, "quwoquan_data", "control_plane", "_shared", "catalogs", "region_catalog.yaml"),
		"regions: []\n")
	return root
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
