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
	"quwoquan_service/runtime/repository"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/circle-service/internal/application"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
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

// fakeReader is an in-memory CircleReader for projector tests.
type fakeReader struct {
	byID map[string]model.Circle
}

func (r fakeReader) FindByID(_ context.Context, id string) (*model.Circle, bool) {
	c, ok := r.byID[id]
	if !ok {
		return nil, false
	}
	cp := c
	return &cp, true
}

func publicCircle() model.Circle {
	return model.Circle{
		ID: "circle_1", Name: "洱海骑行圈", Description: "环湖骑行与露营交流",
		Category: "outdoor", DomainID: "travel", Kind: model.CircleKindInterest,
		Tags: []string{"骑行", "洱海"}, MemberCount: 120, PostCount: 30,
		Status: model.CircleStatusActive, Visibility: model.CircleVisibilityPublic,
		UpdatedAt: time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
	}
}

func newProjectorWithFakeES(t *testing.T, f *fakeES, reader CircleReader) *Projector {
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

func TestProjectorUpsertsOnCreate(t *testing.T) {
	circle := publicCircle()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.Circle{circle.ID: circle}})

	if err := proj.Publish(context.Background(), repository.DomainEvent{
		Type: "CircleCreated", AggregateType: "Circle", AggregateID: circle.ID,
	}); err != nil {
		t.Fatalf("Publish err=%v", err)
	}

	id := "circle.circle:circle_1"
	doc, ok := f.upserts[id]
	if !ok {
		t.Fatalf("expected upsert for %q, got %#v", id, f.upserts)
	}
	if doc["objectId"] != "circle_1" || doc["target"] != string(rtsearch.TargetCircle) {
		t.Fatalf("bad indexed doc: %#v", doc)
	}
}

// TestProjectorSharesProjectionWithNativeSurface proves the projector indexes
// exactly what application.ProjectCircleToSearchDocument produces (the same
// function SearchCircles uses) — a single projection truth source.
func TestProjectorSharesProjectionWithNativeSurface(t *testing.T) {
	circle := publicCircle()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.Circle{circle.ID: circle}})
	if err := proj.Publish(context.Background(), repository.DomainEvent{
		Type: "CircleUpdated", AggregateID: circle.ID,
	}); err != nil {
		t.Fatalf("Publish err=%v", err)
	}

	want := es.DocumentToIndex(application.ProjectCircleToSearchDocument(circle))
	raw, _ := json.Marshal(want)
	var wantJSON map[string]any
	_ = json.Unmarshal(raw, &wantJSON)

	got := f.upserts["circle.circle:circle_1"]
	if !reflect.DeepEqual(got, wantJSON) {
		t.Fatalf("indexed doc diverged from shared projection:\n got=%#v\nwant=%#v", got, wantJSON)
	}
}

func TestProjectorDeletesOnArchive(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{})

	if err := proj.Publish(context.Background(), repository.DomainEvent{
		Type: "CircleArchived", AggregateID: "circle_1",
	}); err != nil {
		t.Fatalf("Publish err=%v", err)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "circle.circle:circle_1" {
		t.Fatalf("expected delete of circle.circle:circle_1, got %#v", f.deletes)
	}
}

func TestProjectorDeletesWhenNoLongerEligible(t *testing.T) {
	circle := publicCircle()
	circle.Visibility = model.CircleVisibilityPrivate // turned private => drop from index
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.Circle{circle.ID: circle}})

	if err := proj.Publish(context.Background(), repository.DomainEvent{
		Type: "CircleUpdated", AggregateID: circle.ID,
	}); err != nil {
		t.Fatalf("Publish err=%v", err)
	}
	if len(f.upserts) != 0 {
		t.Fatalf("private circle must not be upserted: %#v", f.upserts)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "circle.circle:circle_1" {
		t.Fatalf("expected delete for ineligible circle, got %#v", f.deletes)
	}
}

func TestProjectorDeletesWhenCircleMissing(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{}) // store returns not-found

	if err := proj.Publish(context.Background(), repository.DomainEvent{
		Type: "CircleCreated", AggregateID: "circle_gone",
	}); err != nil {
		t.Fatalf("Publish err=%v", err)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "circle.circle:circle_gone" {
		t.Fatalf("missing circle should be deleted from index, got %#v", f.deletes)
	}
}

func TestProjectorIgnoresCounterOnlyEvents(t *testing.T) {
	circle := publicCircle()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.Circle{circle.ID: circle}})

	for _, et := range []string{"CircleMemberJoined", "CircleMemberLeft", "CircleBehaviorReported", "SomethingElse"} {
		if err := proj.Publish(context.Background(), repository.DomainEvent{Type: et, AggregateID: circle.ID}); err != nil {
			t.Fatalf("Publish(%s) err=%v", et, err)
		}
	}
	if len(f.upserts) != 0 || len(f.deletes) != 0 {
		t.Fatalf("counter-only events must not touch the index: upserts=%#v deletes=%#v", f.upserts, f.deletes)
	}
}

// TestProjectorESOutageDoesNotBlock asserts an ES write failure is swallowed
// (recorded, returns nil) so the primary circle write path is never blocked.
func TestProjectorESOutageDoesNotBlock(t *testing.T) {
	circle := publicCircle()
	f := newFakeES()
	f.writeFailStatus = http.StatusServiceUnavailable
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.Circle{circle.ID: circle}})

	if err := proj.Publish(context.Background(), repository.DomainEvent{
		Type: "CircleCreated", AggregateID: circle.ID,
	}); err != nil {
		t.Fatalf("ES outage must not propagate to the write path, got err=%v", err)
	}
}

func TestProjectorNilIndexerIsNoOp(t *testing.T) {
	var proj *Projector // nil receiver
	if err := proj.Publish(context.Background(), repository.DomainEvent{Type: "CircleCreated", AggregateID: "x"}); err != nil {
		t.Fatalf("nil projector must be a no-op, got %v", err)
	}
	proj = NewProjector(nil, fakeReader{}) // nil indexer
	if err := proj.Publish(context.Background(), repository.DomainEvent{Type: "CircleCreated", AggregateID: "x"}); err != nil {
		t.Fatalf("nil indexer must be a no-op, got %v", err)
	}
}
