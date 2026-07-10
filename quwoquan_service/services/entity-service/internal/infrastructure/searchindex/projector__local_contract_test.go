package searchindex

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/entity-service/internal/application"
)

// fakeES simulates the subset of the ES HTTP API the writer/indexer uses, so the
// projector can be driven through the real es.Client transport (parallel to
// runtime/search/es.fakeCluster). writeFailStatus forces _doc writes to fail.
type fakeES struct {
	mu              sync.Mutex
	created         bool
	upserts         map[string]map[string]any
	deletes         []string
	writeFailStatus int
}

func newFakeES() *fakeES { return &fakeES{upserts: map[string]map[string]any{}} }

func (f *fakeES) handler() http.Handler {
	docPrefix := "/" + es.DefaultIndex + "/_doc/"
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/":
			writeJSON(w, http.StatusOK, map[string]any{"cluster_name": "fake"})
		case r.Method == http.MethodHead && r.URL.Path == "/"+es.DefaultIndex:
			if f.created {
				w.WriteHeader(http.StatusOK)
			} else {
				w.WriteHeader(http.StatusNotFound)
			}
		case r.Method == http.MethodPut && r.URL.Path == "/"+es.DefaultIndex:
			f.created = true
			writeJSON(w, http.StatusOK, map[string]any{"acknowledged": true})
		case r.Method == http.MethodPut && strings.HasPrefix(r.URL.Path, docPrefix):
			if f.writeFailStatus != 0 {
				w.WriteHeader(f.writeFailStatus)
				return
			}
			id := strings.TrimPrefix(r.URL.Path, docPrefix)
			body, _ := io.ReadAll(r.Body)
			var doc map[string]any
			_ = json.Unmarshal(body, &doc)
			f.upserts[id] = doc
			writeJSON(w, http.StatusCreated, map[string]any{"result": "created"})
		case r.Method == http.MethodDelete && strings.HasPrefix(r.URL.Path, docPrefix):
			if f.writeFailStatus != 0 {
				w.WriteHeader(f.writeFailStatus)
				return
			}
			id := strings.TrimPrefix(r.URL.Path, docPrefix)
			f.deletes = append(f.deletes, id)
			writeJSON(w, http.StatusOK, map[string]any{"result": "deleted"})
		case r.Method == http.MethodPost && r.URL.Path == "/_bulk":
			writeJSON(w, http.StatusOK, map[string]any{"errors": false, "items": []any{}})
		default:
			writeUnexpectedRequest(w, r)
		}
	})
}

func writeUnexpectedRequest(w http.ResponseWriter, r *http.Request) {
	rterr.WriteHTTPError(
		w,
		rterr.NewInvalidArgument(rterr.ModuleSearch, "请求无效", "unexpected "+r.Method+" "+r.URL.Path),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func publishedHomepage() application.Homepage {
	return application.Homepage{
		ID:                "hp_1",
		Title:             "洱海骑行主页",
		Subtitle:          "环湖骑行与露营攻略",
		HomepageType:      "sight",
		CanonicalEntityID: "entity:sight:erhai",
		Status:            "published",
		CategoryTags:      []string{"骑行", "洱海"},
		City:              "大理",
		Address:           "环海西路",
		RatingCount:       42,
		UpdatedAt:         time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
	}
}

func newProjectorWithFakeES(t *testing.T, f *fakeES) *Projector {
	t.Helper()
	srv := httptest.NewServer(f.handler())
	t.Cleanup(srv.Close)
	client, err := es.NewClient(es.Config{Endpoints: []string{srv.URL}})
	if err != nil {
		t.Fatalf("es.NewClient err=%v", err)
	}
	indexer := es.NewIndexer(client, client.IndexName())
	return NewProjector(indexer, WithLogger(slog.Default()))
}

func TestProjectorUpsertsOnPublish(t *testing.T) {
	hp := publishedHomepage()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f)

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: application.ProjectorEventHomepageUpserted, HomepageID: hp.ID, Homepage: &hp,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}

	id := "entity.homepage:hp_1"
	doc, ok := f.upserts[id]
	if !ok {
		t.Fatalf("expected upsert for %q, got %#v", id, f.upserts)
	}
	if doc["objectId"] != "hp_1" || doc["target"] != string(rtsearch.TargetEntity) {
		t.Fatalf("bad indexed doc: %#v", doc)
	}
	if doc["entityId"] != "entity:sight:erhai" {
		t.Fatalf("entity anchor missing: %#v", doc)
	}
}

// TestProjectorSharesProjectionWithNativeSurface proves the projector indexes
// exactly what application.ProjectHomepageToSearchDocument produces (the same
// function SearchHomepages uses) — a single projection truth source.
func TestProjectorSharesProjectionWithNativeSurface(t *testing.T) {
	hp := publishedHomepage()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f)
	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: application.ProjectorEventHomepageUpserted, HomepageID: hp.ID, Homepage: &hp,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}

	want := es.DocumentToIndex(application.ProjectHomepageToSearchDocument(hp))
	raw, _ := json.Marshal(want)
	var wantJSON map[string]any
	_ = json.Unmarshal(raw, &wantJSON)

	got := f.upserts["entity.homepage:hp_1"]
	if !reflect.DeepEqual(got, wantJSON) {
		t.Fatalf("indexed doc diverged from shared projection:\n got=%#v\nwant=%#v", got, wantJSON)
	}
}

func TestProjectorDeletesOnRemove(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f)

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: application.ProjectorEventHomepageRemoved, HomepageID: "hp_1",
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "entity.homepage:hp_1" {
		t.Fatalf("expected delete of entity.homepage:hp_1, got %#v", f.deletes)
	}
}

func TestProjectorDeletesWhenNoLongerEligible(t *testing.T) {
	hp := publishedHomepage()
	hp.Status = "offline" // taken offline => must drop from the index
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f)

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: application.ProjectorEventHomepageUpserted, HomepageID: hp.ID, Homepage: &hp,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if len(f.upserts) != 0 {
		t.Fatalf("offline homepage must not be upserted: %#v", f.upserts)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "entity.homepage:hp_1" {
		t.Fatalf("expected delete for ineligible homepage, got %#v", f.deletes)
	}
}

func TestProjectorDeletesWhenSnapshotMissing(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f)

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: application.ProjectorEventHomepageUpserted, HomepageID: "hp_gone", Homepage: nil,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "entity.homepage:hp_gone" {
		t.Fatalf("missing snapshot should be deleted from index, got %#v", f.deletes)
	}
}

func TestProjectorIgnoresUnrelatedEvents(t *testing.T) {
	hp := publishedHomepage()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f)

	for _, et := range []string{"HomepageFollowed", "HomepageRated", "SomethingElse"} {
		if err := proj.Project(context.Background(), application.ProjectorEvent{Type: et, HomepageID: hp.ID, Homepage: &hp}); err != nil {
			t.Fatalf("Project(%s) err=%v", et, err)
		}
	}
	if len(f.upserts) != 0 || len(f.deletes) != 0 {
		t.Fatalf("unrelated events must not touch the index: upserts=%#v deletes=%#v", f.upserts, f.deletes)
	}
}

// TestProjectorESOutageDoesNotBlock asserts an ES write failure is swallowed
// (recorded, returns nil) so the primary homepage write path is never blocked.
func TestProjectorESOutageDoesNotBlock(t *testing.T) {
	hp := publishedHomepage()
	f := newFakeES()
	f.writeFailStatus = http.StatusServiceUnavailable
	proj := newProjectorWithFakeES(t, f)

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: application.ProjectorEventHomepageUpserted, HomepageID: hp.ID, Homepage: &hp,
	}); err != nil {
		t.Fatalf("ES outage must not propagate to the write path, got err=%v", err)
	}
}

func TestProjectorNilIndexerIsNoOp(t *testing.T) {
	var proj *Projector // nil receiver
	if err := proj.Project(context.Background(), application.ProjectorEvent{Type: application.ProjectorEventHomepageUpserted, HomepageID: "x"}); err != nil {
		t.Fatalf("nil projector must be a no-op, got %v", err)
	}
	proj = NewProjector(nil) // nil indexer
	if err := proj.Project(context.Background(), application.ProjectorEvent{Type: application.ProjectorEventHomepageUpserted, HomepageID: "x"}); err != nil {
		t.Fatalf("nil indexer must be a no-op, got %v", err)
	}
}
