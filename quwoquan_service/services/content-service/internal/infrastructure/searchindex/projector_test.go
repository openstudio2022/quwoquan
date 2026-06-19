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

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/application"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// fakeES simulates the subset of the ES HTTP API the writer/indexer uses, so the
// projector can be driven through the real es.Client transport (parallel to
// runtime/search/es.fakeCluster). writeFailStatus forces _doc writes to fail.
type fakeES struct {
	mu              sync.Mutex
	created         bool
	upserts         map[string]map[string]any
	deletes         []string
	bulkBody        string
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
			body, _ := io.ReadAll(r.Body)
			f.bulkBody = string(body)
			writeJSON(w, http.StatusOK, map[string]any{"errors": false, "items": []any{}})
		default:
			http.Error(w, "unexpected "+r.Method+" "+r.URL.Path, http.StatusTeapot)
		}
	})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// fakeReader is an in-memory PostReader for projector/backfill tests.
type fakeReader struct {
	byID map[string]postmodel.Post
	all  []postmodel.Post
}

func (r fakeReader) FindByID(_ context.Context, id string) (*postmodel.Post, bool) {
	p, ok := r.byID[id]
	if !ok {
		return nil, false
	}
	cp := p
	return &cp, true
}

func (r fakeReader) ListAll(_ context.Context) []postmodel.Post { return r.all }

func publishedPost() postmodel.Post {
	return postmodel.Post{
		ID: "post_1", Title: "洱海骑行攻略", Summary: "环湖一日", Body: "正文",
		ContentType: "video", Status: "published", Visibility: "public",
		AuthorId: "user_9", AuthorDisplayNameSnapshot: "alice",
		TagRefs: []string{"骑行", "洱海"}, EntityRefs: []string{"洱海"},
		LikeCount: 3, CommentCount: 1,
		PublishedAt: time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
	}
}

func newProjectorWithFakeES(t *testing.T, f *fakeES, reader PostReader) *Projector {
	t.Helper()
	srv := httptest.NewServer(f.handler())
	t.Cleanup(srv.Close)
	client, err := es.NewClient(es.Config{Endpoints: []string{srv.URL}})
	if err != nil {
		t.Fatalf("es.NewClient err=%v", err)
	}
	indexer := es.NewIndexer(client, client.IndexName())
	return NewProjector(indexer, reader, WithLogger(slog.Default()))
}

func TestProjectorUpsertsOnPublish(t *testing.T) {
	post := publishedPost()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: "PostPublished", AggregateType: "Post", AggregateID: post.ID,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}

	id := "content.post:post_1"
	doc, ok := f.upserts[id]
	if !ok {
		t.Fatalf("expected upsert for %q, got %#v", id, f.upserts)
	}
	if doc["objectId"] != "post_1" || doc["target"] != string(rtsearch.TargetVideo) {
		t.Fatalf("bad indexed doc: %#v", doc)
	}
	if doc["authorId"] != "user_9" {
		t.Fatalf("author anchor missing: %#v", doc)
	}
}

// TestProjectorSharesProjectionWithCandidateSource proves the projector indexes
// exactly what application.ProjectPostToSearchDocument produces (the same function
// PostCandidateSource uses) — a single projection truth source.
func TestProjectorSharesProjectionWithCandidateSource(t *testing.T) {
	post := publishedPost()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})
	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: "PostPublished", AggregateID: post.ID,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}

	want := es.DocumentToIndex(application.ProjectPostToSearchDocument(post))
	// Normalize through JSON because the fake ES decodes the stored doc from JSON.
	raw, _ := json.Marshal(want)
	var wantJSON map[string]any
	_ = json.Unmarshal(raw, &wantJSON)

	got := f.upserts["content.post:post_1"]
	if !reflect.DeepEqual(got, wantJSON) {
		t.Fatalf("indexed doc diverged from shared projection:\n got=%#v\nwant=%#v", got, wantJSON)
	}
}

func TestProjectorDeletesOnDelete(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{})

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: "PostDeleted", AggregateID: "post_1",
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "content.post:post_1" {
		t.Fatalf("expected delete of content.post:post_1, got %#v", f.deletes)
	}
}

func TestProjectorDeletesWhenNoLongerEligible(t *testing.T) {
	post := publishedPost()
	post.Visibility = "private" // turned private => must drop from the index
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: "PostSettingsUpdated", AggregateID: post.ID,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if len(f.upserts) != 0 {
		t.Fatalf("private post must not be upserted: %#v", f.upserts)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "content.post:post_1" {
		t.Fatalf("expected delete for ineligible post, got %#v", f.deletes)
	}
}

func TestProjectorDeletesWhenPostMissing(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{}) // store returns not-found

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: "PostPublished", AggregateID: "post_gone",
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "content.post:post_gone" {
		t.Fatalf("missing post should be deleted from index, got %#v", f.deletes)
	}
}

func TestProjectorIgnoresCounterOnlyEvents(t *testing.T) {
	post := publishedPost()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	for _, et := range []string{"ContentReacted", "BehaviorBatchReported", "SomethingElse"} {
		if err := proj.Project(context.Background(), application.ProjectorEvent{Type: et, AggregateID: post.ID}); err != nil {
			t.Fatalf("Project(%s) err=%v", et, err)
		}
	}
	if len(f.upserts) != 0 || len(f.deletes) != 0 {
		t.Fatalf("counter-only events must not touch the index: upserts=%#v deletes=%#v", f.upserts, f.deletes)
	}
}

// TestProjectorESOutageDoesNotBlock asserts an ES write failure is swallowed
// (recorded, returns nil) so the primary post write path is never blocked.
func TestProjectorESOutageDoesNotBlock(t *testing.T) {
	post := publishedPost()
	f := newFakeES()
	f.writeFailStatus = http.StatusServiceUnavailable
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	if err := proj.Project(context.Background(), application.ProjectorEvent{
		Type: "PostPublished", AggregateID: post.ID,
	}); err != nil {
		t.Fatalf("ES outage must not propagate to the write path, got err=%v", err)
	}
}

func TestProjectorNilIndexerIsNoOp(t *testing.T) {
	var proj *Projector // nil receiver
	if err := proj.Project(context.Background(), application.ProjectorEvent{Type: "PostPublished", AggregateID: "x"}); err != nil {
		t.Fatalf("nil projector must be a no-op, got %v", err)
	}
	proj = NewProjector(nil, fakeReader{}) // nil indexer
	if err := proj.Project(context.Background(), application.ProjectorEvent{Type: "PostPublished", AggregateID: "x"}); err != nil {
		t.Fatalf("nil indexer must be a no-op, got %v", err)
	}
}
