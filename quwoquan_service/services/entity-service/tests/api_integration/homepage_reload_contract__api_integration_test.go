package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"sync"
	"testing"

	httpadapter "quwoquan_service/services/entity-service/internal/adapters/http"
	"quwoquan_service/services/entity-service/internal/application"
)

// memoryStateStore 模拟 homepage_state 运行库：importer 直写后 Load 返回新快照。
type memoryStateStore struct {
	mu       sync.Mutex
	snapshot *application.HomepageStateSnapshot
}

func (s *memoryStateStore) Load(ctx context.Context) (*application.HomepageStateSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.snapshot, nil
}

func (s *memoryStateStore) Save(ctx context.Context, snapshot application.HomepageStateSnapshot) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.snapshot = &snapshot
	return nil
}

// TestReloadHomepageStateMergesImporterWrites 验证免停服重载契约：
// importer 直写运行库（模拟为直接替换 store 快照）后 POST /homepages:reload，
// 新主页无需重启即可被搜索读到，运行期已有主页不丢失。
func TestReloadHomepageStateMergesImporterWrites(t *testing.T) {
	store := &memoryStateStore{}
	service := application.NewHomepageServiceWithStore(context.Background(), store)
	server := httptest.NewServer(httpadapter.NewHandler(service).Routes())
	defer server.Close()

	// 运行期先入一个候选并发布（这些状态在 reload 后必须保留）。
	candidate := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/homepages/candidates", map[string]any{
		"title":        "重载前运行期主页",
		"homepageType": "sight",
		"city":         "杭州",
	}, http.StatusCreated)
	runtimeID := stringField(t, candidate, "homepageId")

	// 模拟离线 importer：在 store 侧快照追加一个新主页（不经运行中服务）。
	store.mu.Lock()
	base := store.snapshot
	if base == nil {
		t.Fatalf("expected persisted snapshot after candidate intake")
	}
	imported := *base
	imported.Homepages = append(imported.Homepages, application.Homepage{
		ID:           "homepage-imported-001",
		Title:        "导入的乐山大佛主页",
		HomepageType: "sight",
		City:         "乐山",
		Status:       "published",
	})
	store.snapshot = &imported
	store.mu.Unlock()

	reload := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/homepages:reload", nil, http.StatusOK)
	after, ok := reload["homepagesAfter"].(float64)
	if !ok || int(after) <= 0 {
		t.Fatalf("expected homepagesAfter > 0, got %v", reload["homepagesAfter"])
	}
	if int(reload["homepagesAfter"].(float64)) < int(reload["homepagesBefore"].(float64))+1 {
		t.Fatalf("expected reload to add imported homepage: %v", reload)
	}

	// 新导入主页免重启可读。
	detail := requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/homepage-imported-001", nil, http.StatusOK)
	if got := stringField(t, detail, "title"); got != "导入的乐山大佛主页" {
		t.Fatalf("expected imported homepage title, got %q", got)
	}

	// 运行期主页不因 reload 丢失。
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+runtimeID, nil, http.StatusOK)
}

// TestReloadHomepageStateWithoutStoreFails 无运行库配置时 reload 必须显式报错，
// 不得静默成功掩盖导入链路断点。
func TestReloadHomepageStateWithoutStoreFails(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	resp, err := server.Client().Post(server.URL+"/homepages:reload", "application/json", nil)
	if err != nil {
		t.Fatalf("reload request failed: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusOK {
		t.Fatalf("expected non-200 when state store is not configured")
	}
}

func TestReloadHomepageStateAppliesDataSyncRollbackAndReplay(t *testing.T) {
	ctx := context.Background()
	store := &memoryStateStore{}
	runtimeService := application.NewHomepageServiceWithStore(ctx, store)
	server := httptest.NewServer(httpadapter.NewHandler(runtimeService).Routes())
	defer server.Close()

	// 独立主页没有 qwq_data provenance；data release 的 sync 绝不能将其下线。
	independent := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/homepages/candidates", map[string]any{
		"title":        "运营独立主页",
		"homepageType": "sight",
		"city":         "杭州",
	}, http.StatusCreated)
	independentID := stringField(t, independent, "homepageId")

	// importer 是独立进程视角：它从同一个运行库加载快照、写 desired state，在线服务
	// 只能在 reload 后看到变化。
	importerService := application.NewHomepageServiceWithStore(ctx, store)
	input := importedHomepageInput("地点/景区/回滚验证景点", "回滚验证景点")
	releaseOne, err := importerService.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "20260715--travel-homepage-coverage--cn-zhejiang-sichuan--canary-005",
		Inputs:          []application.ImportedHomepageInput{input},
	})
	if err != nil {
		t.Fatalf("apply data release: %v", err)
	}
	dataHomepageID := releaseOne.EntityRefToHomepageID[input.EntityRef]
	if dataHomepageID == "" {
		t.Fatalf("data release did not report homepage identity: %+v", releaseOne)
	}
	requestJSON(t, server.Client(), http.MethodPost, server.URL+"/homepages:reload", nil, http.StatusOK)
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+dataHomepageID, nil, http.StatusOK)
	if !searchContainsHomepage(t, server, input.Title, dataHomepageID) {
		t.Fatalf("published data homepage must appear in search after reload")
	}

	baseline, err := importerService.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "20260715--travel-homepage-coverage--cn-zhejiang-sichuan--baseline-001",
		Inputs:          []application.ImportedHomepageInput{},
	})
	if err != nil {
		t.Fatalf("apply empty baseline: %v", err)
	}
	if len(baseline.Offlined) != 1 || baseline.Offlined[0] != dataHomepageID {
		t.Fatalf("baseline must offline only the prior data-owned homepage: %+v", baseline)
	}
	requestJSON(t, server.Client(), http.MethodPost, server.URL+"/homepages:reload", nil, http.StatusOK)
	offline := requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+dataHomepageID, nil, http.StatusGone)
	if got := stringField(t, offline, "code"); got != "ENTITY.USER.homepage_offline" {
		t.Fatalf("offline homepage code = %q", got)
	}
	if searchContainsHomepage(t, server, input.Title, dataHomepageID) {
		t.Fatalf("offline data homepage must be removed from search after reload")
	}
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+independentID, nil, http.StatusOK)

	replay, err := importerService.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "20260715--travel-homepage-coverage--cn-zhejiang-sichuan--canary-005",
		Inputs:          []application.ImportedHomepageInput{input},
	})
	if err != nil {
		t.Fatalf("replay data release: %v", err)
	}
	if got := replay.EntityRefToHomepageID[input.EntityRef]; got != dataHomepageID {
		t.Fatalf("replay must retain homepage identity: got %q want %q", got, dataHomepageID)
	}
	requestJSON(t, server.Client(), http.MethodPost, server.URL+"/homepages:reload", nil, http.StatusOK)
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+dataHomepageID, nil, http.StatusOK)
	if !searchContainsHomepage(t, server, input.Title, dataHomepageID) {
		t.Fatalf("replayed data homepage must return to search after reload")
	}
}

func importedHomepageInput(entityRef string, title string) application.ImportedHomepageInput {
	return application.ImportedHomepageInput{
		EntityRef:    entityRef,
		Title:        title,
		HomepageType: "sight",
		City:         "杭州",
	}
}

func searchContainsHomepage(t *testing.T, server *httptest.Server, query string, homepageID string) bool {
	t.Helper()
	payload := requestJSON(
		t,
		server.Client(),
		http.MethodGet,
		server.URL+"/homepages/search?query="+url.QueryEscape(query),
		nil,
		http.StatusOK,
	)
	items, ok := payload["items"].([]any)
	if !ok {
		t.Fatalf("search items has unexpected shape: %#v", payload["items"])
	}
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("search item has unexpected shape: %#v", raw)
		}
		if item["homepageId"] == homepageID {
			return true
		}
	}
	return false
}
