// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-search-and-picker/spec.md#gwt-001
// readiness_case: project-homepage-search-item-api
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/search/es"
	searchitemevent "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/adapters/inbound/event"
	searchitemapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/application"
	searchitempersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/infrastructure/persistence"
)

type fakeSearchCluster struct {
	mu      sync.Mutex
	upserts int
	deletes int
}

func (f *fakeSearchCluster) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	switch {
	case r.Method == http.MethodPut && strings.Contains(r.URL.Path, "/_doc/"):
		f.upserts++
		writeSearchJSON(w, http.StatusCreated, map[string]any{"result": "created"})
	case r.Method == http.MethodDelete && strings.Contains(r.URL.Path, "/_doc/"):
		f.deletes++
		writeSearchJSON(w, http.StatusOK, map[string]any{"result": "deleted"})
	default:
		http.Error(w, "unexpected "+r.Method+" "+r.URL.Path, http.StatusBadRequest)
	}
}

func writeSearchJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func TestHomepageSearchItemViewPersistsMonotonicCheckpointAndTombstone(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	mongoRuntime, err := testinfra.StartRealMongo(
		ctx,
		fmt.Sprintf("homepage_search_item_%d", time.Now().UnixNano()),
	)
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if closeErr := mongoRuntime.Close(cleanupCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	cluster := &fakeSearchCluster{}
	server := httptest.NewServer(cluster)
	defer server.Close()
	client, err := es.NewClient(es.Config{Endpoints: []string{server.URL}})
	if err != nil {
		t.Fatalf("new Elasticsearch client: %v", err)
	}
	index := searchitempersistence.NewESIndex(
		es.NewIndexer(client, client.IndexName()),
		mongoRuntime.Database,
	)
	if err := index.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure checkpoint indexes: %v", err)
	}
	handler := searchitemevent.NewHandler(searchitemapp.NewProjector(index))

	published := searchitemevent.HomepagePublicEvent{
		EventType: "HomepagePublished", HomepageID: "homepage-search-1",
		EntityID: "entity-search-1", DisplayName: "洱海主页", EntityType: "sight",
		SourceVersion: 2, UpdatedAt: time.Now().UTC(),
	}
	if applied, err := handler.Apply(ctx, published); err != nil || !applied {
		t.Fatalf("project published event: applied=%v err=%v", applied, err)
	}
	stale := published
	stale.SourceVersion = 1
	stale.DisplayName = "stale title"
	if applied, err := handler.Apply(ctx, stale); err != nil || applied {
		t.Fatalf("stale event must be ignored: applied=%v err=%v", applied, err)
	}
	if applied, err := handler.Apply(ctx, searchitemevent.HomepagePublicEvent{
		EventType: "HomepageRetired", HomepageID: published.HomepageID, SourceVersion: 3,
	}); err != nil || !applied {
		t.Fatalf("project tombstone: applied=%v err=%v", applied, err)
	}
	if applied, err := handler.Apply(ctx, published); err != nil || applied {
		t.Fatalf("pre-tombstone replay must be ignored: applied=%v err=%v", applied, err)
	}

	var checkpoint struct {
		SourceVersion int64 `bson:"sourceVersion"`
		Tombstone     bool  `bson:"tombstone"`
	}
	if err := mongoRuntime.Database.Collection(searchitempersistence.VersionCollection).
		FindOne(ctx, bson.M{"_id": published.HomepageID}).Decode(&checkpoint); err != nil {
		t.Fatalf("read projection checkpoint: %v", err)
	}
	if checkpoint.SourceVersion != 3 || !checkpoint.Tombstone {
		t.Fatalf("unexpected checkpoint: %+v", checkpoint)
	}
	cluster.mu.Lock()
	upserts, deletes := cluster.upserts, cluster.deletes
	cluster.mu.Unlock()
	if upserts != 1 || deletes != 1 {
		t.Fatalf("stale events touched Elasticsearch: upserts=%d deletes=%d", upserts, deletes)
	}
}
