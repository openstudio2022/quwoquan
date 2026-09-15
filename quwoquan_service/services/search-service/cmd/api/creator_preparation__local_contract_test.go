package bootstrap

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/auth"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/runtime/servicekit"
	indexapp "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	preparation "quwoquan_service/services/search-service/internal/search/search_release_preparation/domain"
	"quwoquan_service/services/search-service/tests/support"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t7
// 生产组合seam+真实Mongo/ES与JWT；命名为白盒local_contract，证据层实际包含隔离Provider边界。
func TestCreatorPreparationProductionAssembly(t *testing.T) {
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT", "")
	ctx, cancel := context.WithTimeout(t.Context(), 3*time.Minute)
	defer cancel()
	db, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("creator_bootstrap"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		shutdown, c := context.WithTimeout(context.Background(), 30*time.Second)
		defer c()
		_ = db.Close(shutdown)
	}()
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	defer stop()
	provider, err := es.NewClient(es.Config{Endpoints: []string{endpoint}, Index: "creator_bootstrap", RequestTimeout: 30 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if err = provider.EnsureIndex(ctx); err != nil {
		t.Fatal(err)
	}
	cfg := auth.TokenConfig{Secret: []byte("0123456789abcdef0123456789abcdef"), Issuer: "https://auth.quwoquan.test", Audience: "quwoquan-api", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	verifier, _ := auth.NewHS256Verifier(cfg)
	credential, _ := auth.NewHS256ServiceAuthorizationProvider(cfg, "search-service", []string{"content.release.fence.read"})
	caller, _ := auth.NewHS256ServiceAuthorizationProvider(cfg, "content-service", []string{"search.release.prepare", "search.release.read"})
	generation := "sha256:" + strings.Repeat("a", 64)
	binding := rt.ReleaseQueryPreparationBinding{Release: rt.ReleaseCandidateBinding{Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: "already-active", ManifestDigest: generation}, Slice: "creator_search", SchemaGeneration: provider.SchemaGeneration(), ProviderBindingGeneration: generation}
	snapshot := rt.CreatorSearchCandidateSnapshot{Release: binding.Release, SourceClosureDigest: generation, Profiles: []rt.CreatorSearchPublicSnapshot{{ObjectType: "user.profile", ObjectID: "builtin_author", CreatorID: "creator", PersonaID: "builtin_author", AuthorID: "author", UserHandle: "creator-handle", DisplayName: "旅行作者", IdentityTags: []string{}, SourceVersion: 1, ProfileDigest: generation, UpdatedAt: "2026-09-12T00:00:00Z"}}}
	_ = snapshot.Seal()
	active := indexapp.ContentCreatorFence{Found: true, Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: binding.Release.ReleaseID, ManifestDigest: generation, Revision: 7, ProjectionVersion: 1}
	activated := time.Now().UTC()
	active.ActivatedAt = &activated
	content := httptest.NewServer(auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p, ok := auth.PrincipalFromContext(r.Context())
		if !ok || p.Subject != "service:search-service" {
			http.Error(w, "unauthorized", 403)
			return
		}
		_ = json.NewEncoder(w).Encode(active)
	})))
	defer content.Close()
	mux := http.NewServeMux()
	fence, err := RegisterCreatorPreparation(ctx, mux, db.Database, provider, provider, "gamma", generation, "creator_bootstrap-v1", content.URL, credential)
	if err != nil {
		t.Fatal(err)
	}
	guard, err := searchOwnerRuntimeGuard(servicekit.Identity{AppEnv: "gamma"})
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(guard(mux)))
	defer server.Close()
	body, _ := json.Marshal(struct {
		Binding         rt.ReleaseQueryPreparationBinding `json:"binding"`
		Snapshot        rt.SearchReleaseCandidateSnapshot `json:"snapshot"`
		ExpectedVersion int64                             `json:"expectedVersion"`
		IdempotencyKey  string                            `json:"idempotencyKey"`
	}{binding, rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &snapshot}, 0, "first"})
	req, _ := http.NewRequestWithContext(ctx, "POST", server.URL+"/internal/search/release-preparations:prepare", bytes.NewReader(body))
	header, _ := caller.AuthorizationHeader(ctx)
	req.Header.Set("Authorization", header)
	req.Header.Set("Idempotency-Key", "first")
	resp, err := server.Client().Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		t.Fatal("real blocked owner operation failed", resp.StatusCode)
	}
	var state preparation.View
	if err = rt.DecodeCreatorValue(resp.Body, &state); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(10 * time.Second)
	for state.Status != "completed" {
		if time.Now().After(deadline) {
			t.Fatal("candidate did not converge", state.Status)
		}
		time.Sleep(100 * time.Millisecond)
		retryBody, _ := json.Marshal(preparation.Command{Binding: binding, Snapshot: rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &snapshot}, ExpectedVersion: state.Version, IdempotencyKey: fmt.Sprintf("resume-%d", state.Version)})
		request, _ := http.NewRequestWithContext(ctx, "POST", server.URL+"/internal/search/release-preparations:prepare", bytes.NewReader(retryBody))
		request.Header.Set("Authorization", header)
		request.Header.Set("Idempotency-Key", fmt.Sprintf("resume-%d", state.Version))
		res, e := server.Client().Do(request)
		if e != nil {
			t.Fatal(e)
		}
		e = rt.DecodeCreatorValue(res.Body, &state)
		_ = res.Body.Close()
		if e != nil {
			t.Fatal(e)
		}
	}
	pinned, _, err := fence.Pin(ctx)
	if err != nil {
		t.Fatal(err)
	}
	hits, err := es.NewBackend(provider, provider.IndexName()).Recall(pinned, rt.RetrievePlan{Terms: []string{"旅行作者"}, Limit: 20})
	if err != nil || len(hits) != 1 || hits[0].Document.ObjectID != "builtin_author" {
		t.Fatal("active tuple not queryable", hits, err)
	}
	proofQuery, _ := json.Marshal(preparation.Query{Binding: binding, SnapshotDigest: snapshot.SnapshotDigest})
	readProof := func() int {
		request, _ := http.NewRequestWithContext(ctx, "POST", server.URL+"/internal/search/release-preparations:query", bytes.NewReader(proofQuery))
		request.Header.Set("Authorization", header)
		res, e := server.Client().Do(request)
		if e != nil {
			t.Fatal(e)
		}
		_ = res.Body.Close()
		return res.StatusCode
	}
	if status := readProof(); status != 200 {
		t.Fatal(status)
	}
	// 同一generation重启只读对账，不创建新release或更改pointer。
	if _, err = RegisterCreatorPreparation(ctx, http.NewServeMux(), db.Database, provider, provider, "gamma", generation, "creator_bootstrap-v1", "http://127.0.0.1:1", credential); err != nil {
		t.Fatal(err)
	}
	if _, err = RegisterCreatorPreparation(ctx, http.NewServeMux(), db.Database, provider, provider, "gamma", generation, "creator_bootstrap-v2", "http://127.0.0.1:1", credential); err == nil {
		t.Fatal("wrong physical generation accepted")
	}
	// 删除仅限独立测试索引；证明query必须识别丢库，不自动重建。
	remove, _ := http.NewRequestWithContext(ctx, "DELETE", endpoint+"/creator_bootstrap-v1", nil)
	deleted, e := http.DefaultClient.Do(remove)
	if e != nil {
		t.Fatal(e)
	}
	_ = deleted.Body.Close()
	if status := readProof(); status == 200 {
		t.Fatal("missing Provider returned old proof")
	}
}
