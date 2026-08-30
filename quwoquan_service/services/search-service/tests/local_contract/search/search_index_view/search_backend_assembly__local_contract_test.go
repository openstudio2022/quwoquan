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
		Enabled:   true,
		Endpoints: []string{server.URL},
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
