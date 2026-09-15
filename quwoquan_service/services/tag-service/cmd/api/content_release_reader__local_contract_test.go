package bootstrap

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/auth"
	nodehttp "quwoquan_service/services/tag-service/internal/tag/tag_node_view/adapters/inbound/http"
	nodemodel "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/ports"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-002
func TestContentFencedTagBootstrapStageSwitchRollback(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("tag_fence_bootstrap"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		cleanup, stop := context.WithTimeout(context.Background(), 30*time.Second)
		defer stop()
		_ = runtime.Close(cleanup)
	})
	nodes := persistence.NewMongoTagNodeStore(runtime.Database.Collection("tag_nodes"))
	if err := nodes.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	candidates := taxonomyreleasestore.NewContentCandidateStore(runtime.Database)
	if err := candidates.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	stage := func(id, label string) taxonomyreleasestore.ContentCandidate {
		t.Helper()
		_, err := nodes.Create(ctx, &nodemodel.TagNode{TagRef: "Topic/旅行", Group: "Topic", Label: label, DisplayLabel: label, LabelEn: "Travel", ReleaseID: id, Depth: 1, ParentTagRef: "Topic", LifecycleStatus: "active"})
		if err != nil {
			t.Fatal(err)
		}
		candidate, err := candidates.BuildContentCandidate(ctx, "gamma", "qwq_data", id, "sha256:"+strings.Repeat(id, 64), "content", 1, time.Now().UTC())
		if err != nil {
			t.Fatal(err)
		}
		if _, _, err := candidates.StageVerified(ctx, candidate); err != nil {
			t.Fatal(err)
		}
		return candidate
	}
	a := stage("a", "旧旅行")
	// Content HTTP provider state 只实现 fence 的可控 CAS，真正 Content Mongo adapter 的 bootstrap 测试在 owning 服务。
	var mu sync.Mutex
	var calls int
	var fence = ports.ContentFence{Environment: "gamma", SourceOwner: "qwq_data"}
	cfg := auth.TokenConfig{Secret: []byte("0123456789abcdef0123456789abcdef"), Issuer: "https://auth.quwoquan.test", Audience: "quwoquan-api", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute, ClockSkew: time.Second}
	verifier, err := auth.NewHS256Verifier(cfg)
	if err != nil {
		t.Fatal(err)
	}
	provider := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("environment") != "gamma" || r.URL.Query().Get("sourceOwner") != "qwq_data" {
			t.Error("non-exact fence query")
		}
		mu.Lock()
		defer mu.Unlock()
		calls++
		_ = json.NewEncoder(w).Encode(fence)
	})
	server := httptest.NewServer(auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.RequireGeneratedOperationAuthorization(operationsecurity.ForDomain("content"))(provider)))
	defer server.Close()
	credentials, err := auth.NewHS256ServiceAuthorizationProvider(cfg, "tag-service", []string{"content.release.fence.read"})
	if err != nil {
		t.Fatal(err)
	}
	service, active, err := newContentFencedTagService(runtime.Database, "gamma", server.URL, 500*time.Millisecond, credentials)
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	nodehttp.NewTagHandler(service).Register(mux)
	resolve := func(status int, label string) {
		t.Helper()
		recorder := httptest.NewRecorder()
		mux.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/tag/resolve?tagRef=Topic/旅行", nil))
		if recorder.Code != status {
			t.Fatalf("resolve status=%d body=%s", recorder.Code, recorder.Body.String())
		}
		if label != "" && !strings.Contains(recorder.Body.String(), label) {
			t.Fatalf("resolve=%s", recorder.Body.String())
		}
	}
	cas := func(expected int64, candidate taxonomyreleasestore.ContentCandidate) {
		t.Helper()
		mu.Lock()
		defer mu.Unlock()
		if fence.Revision != expected {
			t.Fatalf("provider CAS conflict")
		}
		now := time.Now().UTC()
		fence = ports.ContentFence{Found: true, Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: candidate.ReleaseID, ManifestDigest: candidate.ManifestDigest, Revision: expected + 1, ProjectionVersion: expected + 1, ActivatedAt: &now}
	}
	resolve(http.StatusNotFound, "")
	cas(0, a)
	resolve(http.StatusOK, "旧旅行")
	b := stage("b", "新旅行")
	resolve(http.StatusOK, "旧旅行")
	cas(1, b)
	resolve(http.StatusOK, "新旅行")
	cas(2, a)
	resolve(http.StatusOK, "旧旅行")
	if fence.Revision != 3 {
		t.Fatal("rollback did not advance revision")
	}
	// 每个共享 reader 调用都一次 pin，内部查询与 feedback validator 不再走 prior reader。
	probes := []struct {
		name string
		run  func() error
	}{
		{"resolve", func() error { _, e := service.Resolve(ctx, "Topic/旅行"); return e }},
		{"children", func() error { _, e := service.ListChildren(ctx, "Topic/旅行", 10); return e }},
		{"dimensions", func() error { _, e := service.ListDimensions(ctx); return e }},
		{"suggest", func() error { _, e := service.Suggest(ctx, "旅行", "", 10); return e }},
		{"validate", func() error { _, e := service.ValidateTagRefs(ctx, "a", []string{"Topic/旅行"}); return e }},
		{"feedback", func() error { _, e := service.TagRefExists(ctx, "Topic/旅行"); return e }},
		{"shared", func() error { _, e := service.SharedTags(ctx, "a", "post", "b", "post", 10); return e }},
		{"inverted", func() error { _, e := service.Inverted(ctx, "Topic/旅行", "post", 10, false); return e }},
		{"health", func() error { _, _, e := active.ActiveReleaseID(ctx); return e }},
		{"search", func() error { _, e := service.SearchTags(ctx, "旅行", "", 10); return e }},
		{"relatedTags", func() error { _, e := service.RelatedTags(ctx, "Topic/旅行", 10); return e }},
		{"cooccurrence", func() error { _, e := service.TagCooccurrence(ctx, "Topic/旅行", 1, 10); return e }},
		{"searchByTags", func() error { _, e := service.SearchByTags(ctx, []string{"Topic/旅行"}, "post", 10); return e }},
		{"relatedObjects", func() error { _, e := service.RelatedObjects(ctx, "a", "post", 10); return e }},
	}
	for _, probe := range probes {
		t.Run(probe.name, func(t *testing.T) {
			mu.Lock()
			before := calls
			mu.Unlock()
			if err := probe.run(); err != nil {
				t.Fatal(err)
			}
			mu.Lock()
			defer mu.Unlock()
			if calls-before != 1 {
				t.Fatalf("pin count=%d", calls-before)
			}
		})
	}
	mu.Lock()
	fence.ManifestDigest = "sha256:" + strings.Repeat("c", 64)
	mu.Unlock()
	resolve(http.StatusInternalServerError, "")
	mu.Lock()
	fence.ManifestDigest = a.ManifestDigest
	mu.Unlock()
	// 独立 Tag persistence corruption 专项验证 candidate closure drift fail closed。
	if _, err := runtime.Database.Collection("tag_nodes").UpdateOne(ctx, bson.M{"releaseId": "a"}, bson.M{"$set": bson.M{"label": "损坏"}}); err != nil {
		t.Fatal(err)
	}
	resolve(http.StatusInternalServerError, "")
}
