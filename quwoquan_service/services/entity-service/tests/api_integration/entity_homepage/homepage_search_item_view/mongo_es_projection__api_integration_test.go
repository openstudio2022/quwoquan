// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-search-and-picker/spec.md#gwt-001
// readiness_case: project-homepage-search-item-api
package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strconv"
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
	mu        sync.Mutex
	upserts   int
	versions  map[string]int64
	documents map[string]map[string]any
}

func (f *fakeSearchCluster) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.versions == nil {
		f.versions = map[string]int64{}
		f.documents = map[string]map[string]any{}
	}
	if r.Method == http.MethodPost && strings.Contains(r.URL.Path, "/_update/") {
		f.classifyVersionConflict(w, r)
		return
	}
	if r.Method != http.MethodPut || !strings.Contains(r.URL.Path, "/_doc/") {
		http.Error(w, "unexpected "+r.Method+" "+r.URL.Path, http.StatusBadRequest)
		return
	}
	id := r.URL.Path[strings.Index(r.URL.Path, "/_doc/")+len("/_doc/"):]
	version, _ := strconv.ParseInt(r.URL.Query().Get("version"), 10, 64)
	if r.URL.Query().Get("version_type") != "external" || f.versions[id] >= version {
		writeSearchJSON(w, http.StatusConflict, map[string]any{"error": "version_conflict_engine_exception"})
		return
	}
	var document map[string]any
	if err := json.NewDecoder(r.Body).Decode(&document); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	f.upserts++
	f.versions[id] = version
	f.documents[id] = document
	writeSearchJSON(w, http.StatusCreated, map[string]any{"result": "created"})
}

func (f *fakeSearchCluster) classifyVersionConflict(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Path[strings.Index(r.URL.Path, "/_update/")+len("/_update/"):]
	var body struct {
		Script struct {
			Params struct {
				SourceVersion int64  `json:"sourceVersion"`
				SourceDigest  string `json:"sourceDigest"`
			} `json:"params"`
		} `json:"script"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	winningVersion, exists := f.versions[id]
	winningDigest, _ := f.documents[id]["sourceDigest"].(string)
	switch {
	case !exists || winningVersion < body.Script.Params.SourceVersion || winningDigest == "":
		writeSearchJSON(w, http.StatusBadRequest, map[string]any{"error": "QWQ_VERSIONED_SOURCE_STATE_INVALID"})
	case winningVersion > body.Script.Params.SourceVersion:
		writeSearchJSON(w, http.StatusOK, map[string]any{"result": "noop"})
	case winningDigest == body.Script.Params.SourceDigest:
		writeSearchJSON(w, http.StatusOK, map[string]any{"result": "noop"})
	default:
		writeSearchJSON(w, http.StatusBadRequest, map[string]any{"error": "QWQ_SAME_VERSION_DIGEST_CONFLICT"})
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
	if applied, err := handler.Apply(ctx, published); err != nil || applied {
		t.Fatalf("equal-version replay must be an atomic no-op: applied=%v err=%v", applied, err)
	}
	conflicting := published
	conflicting.DisplayName = "conflicting title"
	if applied, err := handler.Apply(ctx, conflicting); applied || !errors.Is(err, es.ErrSameVersionDigestConflict) {
		t.Fatalf("divergent equal-version fact must fail closed: applied=%v err=%v", applied, err)
	}
	stale := published
	stale.SourceVersion = 1
	stale.DisplayName = "stale title"
	if applied, err := handler.Apply(ctx, stale); err != nil || applied {
		t.Fatalf("stale event must be ignored: applied=%v err=%v", applied, err)
	}

	// Simulate a backfill and realtime event racing for the same ES _id. The
	// provider fence, not the Mongo checkpoint order, must decide the winner.
	backfill := published
	backfill.SourceVersion = 4
	backfill.DisplayName = "backfill v4"
	realtime := published
	realtime.SourceVersion = 5
	realtime.DisplayName = "realtime v5"
	start := make(chan struct{})
	results := make(chan struct {
		applied bool
		err     error
	}, 2)
	for _, event := range []searchitemevent.HomepagePublicEvent{backfill, realtime} {
		event := event
		go func() {
			<-start
			applied, applyErr := handler.Apply(ctx, event)
			results <- struct {
				applied bool
				err     error
			}{applied: applied, err: applyErr}
		}()
	}
	close(start)
	for range 2 {
		result := <-results
		if result.err != nil {
			t.Fatalf("concurrent projection failed: %v", result.err)
		}
	}
	cluster.mu.Lock()
	concurrentDocument := cluster.documents["entity.homepage:"+published.HomepageID]
	cluster.mu.Unlock()
	if concurrentDocument["sourceVersion"] != float64(5) || concurrentDocument["title"] != "realtime v5" {
		t.Fatalf("backfill/realtime race did not converge to v5: %#v", concurrentDocument)
	}
	if applied, err := handler.Apply(ctx, searchitemevent.HomepagePublicEvent{
		EventType: "HomepageRetired", HomepageID: published.HomepageID, SourceVersion: 6,
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
	if checkpoint.SourceVersion != 6 || !checkpoint.Tombstone {
		t.Fatalf("unexpected checkpoint: %+v", checkpoint)
	}
	cluster.mu.Lock()
	upserts := cluster.upserts
	document := cluster.documents["entity.homepage:"+published.HomepageID]
	cluster.mu.Unlock()
	if upserts < 3 || upserts > 4 {
		t.Fatalf("v2, the race winner(s), and v6 should be the only mutations: upserts=%d", upserts)
	}
	digest, _ := document["sourceDigest"].(string)
	if document["deleted"] != true || document["sourceVersion"] != float64(6) ||
		!strings.HasPrefix(digest, "sha256:") || len(document) != 5 {
		t.Fatalf("persistent tombstone drifted: %#v", document)
	}
}
