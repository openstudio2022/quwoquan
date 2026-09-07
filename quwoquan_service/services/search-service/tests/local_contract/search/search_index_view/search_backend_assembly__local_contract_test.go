package local_contract

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	runtimees "quwoquan_service/runtime/search/es"
	searchbackend "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/searchbackend"
)

func TestBuildRejectsMissingRecallBackend(t *testing.T) {
	if _, err := searchbackend.Build(searchbackend.ESConfig{}); err == nil {
		t.Fatal("disabled Elasticsearch must fail")
	}
	if _, err := searchbackend.Build(searchbackend.ESConfig{Enabled: true}); err == nil {
		t.Fatal("enabled Elasticsearch without endpoints must fail")
	}
	if _, err := searchbackend.Build(searchbackend.ESConfig{
		Enabled: true, Endpoints: []string{"http://reader"}, Index: "objects",
	}); err == nil {
		t.Fatal("missing Search-owned writer binding must fail")
	}
}

func TestReadinessCheckRequiresElasticsearchQueryability(t *testing.T) {
	rootRequests := 0
	searchRequests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/":
			rootRequests++
			w.WriteHeader(http.StatusOK)
		case r.Method == http.MethodPost && r.URL.Path == "/"+runtimees.DefaultIndex+"/_search":
			searchRequests++
			http.Error(w, "shards unavailable", http.StatusServiceUnavailable)
		default:
			http.Error(w, "unexpected request", http.StatusTeapot)
		}
	}))
	defer server.Close()

	built, err := searchbackend.Build(searchbackend.ESConfig{
		Enabled:         true,
		Endpoints:       []string{server.URL},
		Index:           runtimees.DefaultIndex,
		APIKey:          "reader-key",
		WriterEnabled:   true,
		WriterEndpoints: []string{server.URL},
		WriterIndex:     runtimees.DefaultIndex,
		WriterAPIKey:    "writer-key",
	})
	if err != nil {
		t.Fatalf("Build err=%v", err)
	}
	check := built.ReadinessCheck()
	if check == nil {
		t.Fatal("enabled Elasticsearch must expose readiness check")
	}
	if err := check(context.Background()); !errors.Is(err, runtimees.ErrDependencyUnavailable) {
		t.Fatalf("readiness error=%v, want ErrDependencyUnavailable", err)
	}
	if rootRequests != 0 || searchRequests != 1 {
		t.Fatalf("readiness must query the read alias, root=%d search=%d", rootRequests, searchRequests)
	}
}

func TestReaderAndWriterUseOnlyTheirRoleCredentials(t *testing.T) {
	var credentials []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		credentials = append(credentials, r.Header.Get("Authorization"))
		switch r.URL.Path {
		case "/" + runtimees.DefaultIndex + "/_search":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"hits":{"hits":[]}}`))
		case "/" + runtimees.DefaultIndex + "-write/_doc/user.profile:user-1":
			w.WriteHeader(http.StatusCreated)
		default:
			http.Error(w, "unexpected request", http.StatusTeapot)
		}
	}))
	defer server.Close()

	built, err := searchbackend.Build(searchbackend.ESConfig{
		Enabled:         true,
		Endpoints:       []string{server.URL},
		Index:           runtimees.DefaultIndex,
		APIKey:          "reader-key",
		WriterEnabled:   true,
		WriterEndpoints: []string{server.URL},
		WriterIndex:     runtimees.DefaultIndex,
		WriterAPIKey:    "writer-key",
	})
	if err != nil {
		t.Fatalf("Build err=%v", err)
	}
	if _, err := built.Reader.Search(
		context.Background(),
		"",
		map[string]any{"query": map[string]any{"match_all": map[string]any{}}},
	); err != nil {
		t.Fatalf("reader search: %v", err)
	}
	if applied, err := built.Writer.UpsertVersioned(
		context.Background(),
		built.Writer.WriteIndexName(),
		"user.profile:user-1",
		1,
		map[string]any{"objectType": "user.profile"},
	); err != nil || !applied {
		t.Fatalf("writer versioned upsert applied=%v err=%v", applied, err)
	}
	if len(credentials) != 2 ||
		credentials[0] != "ApiKey reader-key" ||
		credentials[1] != "ApiKey writer-key" {
		t.Fatalf("role credentials crossed: %#v", credentials)
	}
}

func TestBuildRejectsMixedGenerationAndSharedRoleCredential(t *testing.T) {
	base := searchbackend.ESConfig{
		Enabled:         true,
		Endpoints:       []string{"http://search-es"},
		Index:           "quwoquan_objects-v1",
		APIKey:          "reader-key",
		WriterEnabled:   true,
		WriterEndpoints: []string{"http://search-es"},
		WriterIndex:     "quwoquan_objects-v2",
		WriterAPIKey:    "writer-key",
	}
	if _, err := searchbackend.Build(base); err == nil {
		t.Fatal("mixed reader/writer generation must fail")
	}
	base.WriterIndex = base.Index
	base.WriterAPIKey = base.APIKey
	if _, err := searchbackend.Build(base); err == nil {
		t.Fatal("shared reader/writer API key must fail")
	}
}
