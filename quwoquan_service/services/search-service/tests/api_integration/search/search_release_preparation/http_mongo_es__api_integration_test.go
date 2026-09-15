package preparation_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"quwoquan_service/internal/platform/testinfra"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	indexapp "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	provider "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/creatorprojection"
	inbound "quwoquan_service/services/search-service/internal/search/search_release_preparation/adapters/inbound/http"
	app "quwoquan_service/services/search-service/internal/search/search_release_preparation/application"
	"quwoquan_service/services/search-service/internal/search/search_release_preparation/domain"
	persistence "quwoquan_service/services/search-service/internal/search/search_release_preparation/infrastructure/persistence"
	"quwoquan_service/services/search-service/tests/support"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t7
func TestHTTPPreparationWithRealMongoAndElasticsearch(t *testing.T) {
	t.Setenv("TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_MONGO_URI", "")
	t.Setenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT", "")
	ctx, cancel := context.WithTimeout(t.Context(), 3*time.Minute)
	defer cancel()
	db, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("creator_http"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		_ = db.Close(c)
	}()
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	defer stop()
	client, err := es.NewClient(es.Config{Endpoints: []string{endpoint}, Index: "creator_http_isolated", RequestTimeout: 5 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if err = client.EnsureIndex(ctx); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoStore(db.Database)
	if err = store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	generation := "sha256:" + strings.Repeat("a", 64)
	service, err := app.NewService(store, indexapp.NewReleaseCandidateProjector(provider.NewProvider(client, client, "creator_http_isolated-v1")), "gamma", generation, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	inbound.NewHandler(service).Register(mux)
	handler, authConfig := preparationAuthStack(t, mux)
	binding := rt.ReleaseQueryPreparationBinding{Release: rt.ReleaseCandidateBinding{"gamma", "qwq_data", "http-candidate", generation}, Slice: "creator_search", SchemaGeneration: client.SchemaGeneration(), ProviderBindingGeneration: generation}
	snapshot := rt.CreatorSearchCandidateSnapshot{Release: binding.Release, SourceClosureDigest: generation, Profiles: []rt.CreatorSearchPublicSnapshot{}}
	_ = snapshot.Seal()
	command := domain.Command{Binding: binding, Snapshot: rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &snapshot}, IdempotencyKey: "http-first"}
	raw, _ := json.Marshal(command)
	request := httptest.NewRequest(http.MethodPost, "/internal/search/release-preparations:prepare", bytes.NewReader(raw))
	denied := httptest.NewRecorder()
	handler.ServeHTTP(denied, request)
	if denied.Code != 401 {
		t.Fatal("untrusted prepare accepted", denied.Code)
	}
	request = httptest.NewRequest(http.MethodPost, "/internal/search/release-preparations:prepare", bytes.NewReader(raw))
	request.Header.Set("Authorization", preparationServiceToken(t, authConfig, "content-service", "search.release.prepare"))
	request.Header.Set("Idempotency-Key", command.IdempotencyKey)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != 200 {
		t.Fatal(response.Code, response.Body.String())
	}
	var view domain.View
	if err = rt.DecodeCreatorValue(response.Body, &view); err != nil {
		t.Fatal(err)
	}
	if view.Status != "completed" {
		t.Fatal("empty exact closure should complete", view.Status)
	}
	query, _ := json.Marshal(domain.Query{Binding: binding, SnapshotDigest: snapshot.SnapshotDigest})
	request = httptest.NewRequest(http.MethodPost, "/internal/search/release-preparations:query", bytes.NewReader(query))
	request.Header.Set("Authorization", preparationServiceToken(t, authConfig, "content-service", "search.release.read"))
	response = httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != 200 {
		t.Fatal(response.Code, response.Body.String())
	}
}
