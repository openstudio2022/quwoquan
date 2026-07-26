package placeindex_test

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/placeindex"
	"strings"
	"sync"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
)

// fakeES simulates the subset of the ES HTTP API the indexer uses so the place
// projector runs through the real es.Client transport.
type fakeES struct {
	mu      sync.Mutex
	created bool
	upserts map[string]map[string]any
	deletes []string
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
			id := strings.TrimPrefix(r.URL.Path, docPrefix)
			body, _ := io.ReadAll(r.Body)
			var doc map[string]any
			_ = json.Unmarshal(body, &doc)
			f.upserts[id] = doc
			writeJSON(w, http.StatusCreated, map[string]any{"result": "created"})
		case r.Method == http.MethodDelete && strings.HasPrefix(r.URL.Path, docPrefix):
			id := strings.TrimPrefix(r.URL.Path, docPrefix)
			f.deletes = append(f.deletes, id)
			writeJSON(w, http.StatusOK, map[string]any{"result": "deleted"})
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

// fakeReader is an in-memory PostReader for projector tests.
type fakeReader struct {
	byID    map[string]postmodel.Post
	all     []postmodel.Post
	loadErr error
	listErr error
}

func (r fakeReader) Load(_ context.Context, id string) (*postmodel.Post, bool, error) {
	if r.loadErr != nil {
		return nil, false, r.loadErr
	}
	p, ok := r.byID[id]
	if !ok {
		return nil, false, nil
	}
	cp := p
	return &cp, true, nil
}

func (r fakeReader) ListAll(_ context.Context) ([]postmodel.Post, error) { return r.all, r.listErr }

func placePost(id, name string) postmodel.Post {
	return postmodel.Post{
		ID: id, Title: id, ContentType: "article", Status: "published", Visibility: "public",
		AuthorId: "u1", LocationName: name,
		Location: postmodel.GeoPoint{Latitude: 30.6571, Longitude: 104.0648},
	}
}

func newProjector(t *testing.T, f *fakeES, reader PostReader, store PlaceStore) *PlaceProjector {
	t.Helper()
	srv := httptest.NewServer(f.handler())
	t.Cleanup(srv.Close)
	client, err := es.NewClient(es.Config{Endpoints: []string{srv.URL}})
	if err != nil {
		t.Fatalf("es.NewClient err=%v", err)
	}
	indexer := es.NewIndexer(client, client.IndexName())
	return NewProjector(indexer, reader, store, WithLogger(slog.Default()))
}

func docID(name string, post postmodel.Post) string {
	geo := &rtsearch.GeoPoint{Lat: post.Location.Latitude, Lng: post.Location.Longitude}
	return rtsearch.ObjectTypeLocation + ":" + searchprojection.CanonicalPlaceID(name, geo)
}

func TestPlaceProjectorUpsertsOnPublish(t *testing.T) {
	post := placePost("p1", "宽窄巷子")
	f := newFakeES()
	store := NewInMemoryPlaceStore()
	proj := newProjector(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}}, store)

	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostPublished", AggregateID: post.ID}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	id := docID("宽窄巷子", post)
	doc, ok := f.upserts[id]
	if !ok {
		t.Fatalf("expected place upsert for %q, got %#v", id, f.upserts)
	}
	if doc["objectType"] != rtsearch.ObjectTypeLocation || doc["target"] != string(rtsearch.TargetLocation) {
		t.Fatalf("bad place doc: %#v", doc)
	}
	if doc["placeName"] != "宽窄巷子" || doc["title"] != "宽窄巷子" {
		t.Fatalf("place doc must carry placeName + title: %#v", doc)
	}
}

func TestPlaceProjectorDedupAcrossPosts(t *testing.T) {
	p1 := placePost("p1", "锦里")
	p2 := placePost("p2", "锦里") // same name + same coarse cell
	f := newFakeES()
	store := NewInMemoryPlaceStore()
	reader := fakeReader{byID: map[string]postmodel.Post{p1.ID: p1, p2.ID: p2}}
	proj := newProjector(t, f, reader, store)

	for _, id := range []string{p1.ID, p2.ID} {
		if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostPublished", AggregateID: id}); err != nil {
			t.Fatalf("Project(%s) err=%v", id, err)
		}
	}
	id := docID("锦里", p1)
	places, _ := store.PlacesReferencing(context.Background(), "p1")
	if len(places) != 1 || len(places[0].RefPostIDs) != 2 {
		t.Fatalf("two posts on one place must converge to a single 2-ref snapshot: %#v", places)
	}
	if doc := f.upserts[id]; doc == nil {
		t.Fatalf("dedup place must be indexed once under %q: %#v", id, f.upserts)
	}
}

func TestPlaceProjectorSingleSourceOnEntityBinding(t *testing.T) {
	post := placePost("p1", "茶马古道")
	f := newFakeES()
	store := NewInMemoryPlaceStore()
	reader := fakeReader{byID: map[string]postmodel.Post{post.ID: post}}
	proj := newProjector(t, f, reader, store)

	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostPublished", AggregateID: post.ID}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	id := docID("茶马古道", post)
	if f.upserts[id] == nil {
		t.Fatalf("place must be indexed before binding: %#v", f.upserts)
	}

	// The place is promoted to a canonical entity: it must drop from location.place
	// (entity.homepage carries it now) — single source of truth.
	bound := post
	bound.PrimaryHomepageId = "homepage_777"
	reader.byID[post.ID] = bound
	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostUpdated", AggregateID: post.ID}); err != nil {
		t.Fatalf("Project(update) err=%v", err)
	}
	if len(f.deletes) != 1 || f.deletes[0] != id {
		t.Fatalf("bound place must be deleted from location.place, deletes=%#v", f.deletes)
	}
	if places, _ := store.PlacesReferencing(context.Background(), post.ID); len(places) != 0 {
		t.Fatalf("store must no longer reference the bound post: %#v", places)
	}
}

func TestPlaceProjectorDeleteOnPostDeleted(t *testing.T) {
	post := placePost("p1", "玉龙雪山")
	f := newFakeES()
	store := NewInMemoryPlaceStore()
	reader := fakeReader{byID: map[string]postmodel.Post{post.ID: post}}
	proj := newProjector(t, f, reader, store)

	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostPublished", AggregateID: post.ID}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostDeleted", AggregateID: post.ID}); err != nil {
		t.Fatalf("Project(delete) err=%v", err)
	}
	id := docID("玉龙雪山", post)
	if len(f.deletes) != 1 || f.deletes[0] != id {
		t.Fatalf("deleted post's last reference must remove the place doc, deletes=%#v", f.deletes)
	}
}

func TestPlaceProjectorIneligibleNotIndexed(t *testing.T) {
	post := placePost("p1", "无名地")
	post.Visibility = "private"
	f := newFakeES()
	store := NewInMemoryPlaceStore()
	proj := newProjector(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}}, store)

	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostSettingsUpdated", AggregateID: post.ID}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if len(f.upserts) != 0 {
		t.Fatalf("ineligible post must not index a place: %#v", f.upserts)
	}
}

func TestPlaceProjectorReadFailureKeepsCheckpointReplayable(t *testing.T) {
	f := newFakeES()
	store := NewInMemoryPlaceStore()
	proj := newProjector(
		t,
		f,
		fakeReader{loadErr: errors.New("malformed Mongo Post")},
		store,
	)

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostSettingsUpdated", AggregateID: "post-corrupt",
	}); err == nil {
		t.Fatal("Post read failure must fail place projection")
	}
	if len(f.upserts) != 0 || len(f.deletes) != 0 {
		t.Fatalf("read failure must not mutate place index: upserts=%#v deletes=%#v", f.upserts, f.deletes)
	}
}

func TestPlaceProjectorMissingDependenciesFailFast(t *testing.T) {
	var proj *PlaceProjector
	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostPublished", AggregateID: "x"}); err == nil {
		t.Fatal("nil projector must fail")
	}
	proj = NewProjector(nil, fakeReader{}, NewInMemoryPlaceStore())
	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostPublished", AggregateID: "x"}); err == nil {
		t.Fatal("nil indexer must fail")
	}
}
