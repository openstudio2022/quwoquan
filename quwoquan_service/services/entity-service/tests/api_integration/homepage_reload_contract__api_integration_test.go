package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
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
// importer 直写运行库（模拟为直接替换 store 快照）后 POST /v1/homepages:reload，
// 新主页无需重启即可被搜索读到，运行期已有主页不丢失。
func TestReloadHomepageStateMergesImporterWrites(t *testing.T) {
	store := &memoryStateStore{}
	service := application.NewHomepageServiceWithStore(context.Background(), store)
	server := httptest.NewServer(httpadapter.NewHandler(service).Routes())
	defer server.Close()

	// 运行期先入一个候选并发布（这些状态在 reload 后必须保留）。
	candidate := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/v1/homepages/candidates", map[string]any{
		"title":        "重载前运行期主页",
		"homepageType": "sight",
		"city":         "杭州",
	}, http.StatusCreated)
	runtimeID := stringField(t, candidate, "_id")

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

	reload := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/v1/homepages:reload", nil, http.StatusOK)
	after, ok := reload["homepagesAfter"].(float64)
	if !ok || int(after) <= 0 {
		t.Fatalf("expected homepagesAfter > 0, got %v", reload["homepagesAfter"])
	}
	if int(reload["homepagesAfter"].(float64)) < int(reload["homepagesBefore"].(float64))+1 {
		t.Fatalf("expected reload to add imported homepage: %v", reload)
	}

	// 新导入主页免重启可读。
	detail := requestJSON(t, server.Client(), http.MethodGet, server.URL+"/v1/homepages/homepage-imported-001", nil, http.StatusOK)
	if got := stringField(t, detail, "title"); got != "导入的乐山大佛主页" {
		t.Fatalf("expected imported homepage title, got %q", got)
	}

	// 运行期主页不因 reload 丢失。
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/v1/homepages/"+runtimeID, nil, http.StatusOK)
}

// TestReloadHomepageStateWithoutStoreFails 无运行库配置时 reload 必须显式报错，
// 不得静默成功掩盖导入链路断点。
func TestReloadHomepageStateWithoutStoreFails(t *testing.T) {
	server := httptest.NewServer(
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	resp, err := server.Client().Post(server.URL+"/v1/homepages:reload", "application/json", nil)
	if err != nil {
		t.Fatalf("reload request failed: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusOK {
		t.Fatalf("expected non-200 when state store is not configured")
	}
}
