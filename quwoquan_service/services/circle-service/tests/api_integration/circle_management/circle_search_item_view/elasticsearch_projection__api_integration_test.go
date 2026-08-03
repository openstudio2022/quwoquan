// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
package api_integration

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"quwoquan_service/runtime/search/es"
	viewapp "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/application"
	viewes "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/infrastructure/elasticsearch"
)

type searchCluster struct {
	mu      sync.Mutex
	created bool
	docs    map[string]map[string]any
}

func (cluster *searchCluster) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	cluster.mu.Lock()
	defer cluster.mu.Unlock()
	prefix := "/" + es.DefaultIndex + "/_doc/"
	switch {
	case request.Method == http.MethodHead && request.URL.Path == "/"+es.DefaultIndex:
		if cluster.created {
			writer.WriteHeader(http.StatusOK)
		} else {
			writer.WriteHeader(http.StatusNotFound)
		}
	case request.Method == http.MethodPut && request.URL.Path == "/"+es.DefaultIndex:
		cluster.created = true
		_ = json.NewEncoder(writer).Encode(map[string]any{"acknowledged": true})
	case request.Method == http.MethodPut && strings.HasPrefix(request.URL.Path, prefix):
		payload, _ := io.ReadAll(request.Body)
		var document map[string]any
		_ = json.Unmarshal(payload, &document)
		cluster.docs[strings.TrimPrefix(request.URL.Path, prefix)] = document
		writer.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(writer).Encode(map[string]any{"result": "created"})
	case request.Method == http.MethodDelete && strings.HasPrefix(request.URL.Path, prefix):
		delete(cluster.docs, strings.TrimPrefix(request.URL.Path, prefix))
		_ = json.NewEncoder(writer).Encode(map[string]any{"result": "deleted"})
	default:
		writer.WriteHeader(http.StatusNotFound)
	}
}

func TestCircleSearchItemViewElasticsearchAdapterOwnsCanonicalDocument(t *testing.T) {
	cluster := &searchCluster{docs: map[string]map[string]any{}}
	server := httptest.NewServer(cluster)
	defer server.Close()
	built, err := viewes.Build(viewes.Config{Enabled: true, Endpoints: []string{server.URL}})
	if err != nil {
		t.Fatal(err)
	}
	if err := built.EnsureIndex(context.Background()); err != nil {
		t.Fatal(err)
	}
	projector := viewapp.NewProjector(built.Index)
	if _, err := projector.Upsert(context.Background(), viewapp.SearchItem{
		CircleID: "circle-1", DisplayName: "洱海骑行圈", Description: "环湖骑行",
		CategoryID: "outdoor", MemberCount: 120, PostCount: 30,
		Visibility: "public", SourceVersion: 7,
	}); err != nil {
		t.Fatal(err)
	}
	document := cluster.docs["circle.circle:circle-1"]
	payload, _ := document["payload"].(map[string]any)
	if document["objectId"] != "circle-1" || payload["sourceVersion"] != "7" || payload["memberCount"] != "120" {
		t.Fatalf("canonical search document drifted: %#v", document)
	}
	if _, err := projector.Delete(context.Background(), "circle-1", 8); err != nil {
		t.Fatal(err)
	}
	if _, found := cluster.docs["circle.circle:circle-1"]; found {
		t.Fatal("tombstone must remove the canonical search document")
	}
}
