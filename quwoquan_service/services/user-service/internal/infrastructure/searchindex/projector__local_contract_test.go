package searchindex

import (
	"context"
	"encoding/json"
	"errors"
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
	"quwoquan_service/services/user-service/internal/application"
	event "quwoquan_service/services/user-service/internal/domain/user/event"
	"quwoquan_service/services/user-service/internal/domain/user/model"
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

// fakeReader is an in-memory ProfileReader for projector tests.
type fakeReader struct {
	byID map[string]model.UserProfile
	err  error
}

func (r fakeReader) FindByID(_ context.Context, userID string) (*model.UserProfile, error) {
	if r.err != nil {
		return nil, r.err
	}
	p, ok := r.byID[userID]
	if !ok {
		return nil, nil
	}
	cp := p
	return &cp, nil
}

func activeProfile() model.UserProfile {
	return model.UserProfile{
		UserID: "user_1", AccountState: "active", Status: "active",
		Nickname: "山野阿洱", Bio: "环洱海骑行 / 露营记录",
		IdentityTags: "{骑行,摄影}", FollowerCount: 320, PostCount: 48,
		UpdatedAt: time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
	}
}

func newProjectorWithFakeES(t *testing.T, f *fakeES, reader ProfileReader) *Projector {
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

func TestProjectorUpsertsOnProfileUpdated(t *testing.T) {
	profile := activeProfile()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.UserProfile{profile.UserID: profile}})

	if err := proj.PublishUserEvent(context.Background(), event.UserProfileUpdated, profile.UserID, profile.UserID, nil); err != nil {
		t.Fatalf("PublishUserEvent err=%v", err)
	}

	id := "user.profile:user_1"
	doc, ok := f.upserts[id]
	if !ok {
		t.Fatalf("expected upsert for %q, got %#v", id, f.upserts)
	}
	if doc["objectId"] != "user_1" || doc["target"] != string(rtsearch.TargetUser) {
		t.Fatalf("bad indexed doc: %#v", doc)
	}
	if doc["authorId"] != "user_1" || doc["authorName"] != "山野阿洱" {
		t.Fatalf("author anchors missing: %#v", doc)
	}
}

// TestProjectorSharesProjection proves the projector indexes exactly what
// application.ProjectUserProfileToSearchDocument produces — a single projection
// truth source.
func TestProjectorSharesProjection(t *testing.T) {
	profile := activeProfile()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.UserProfile{profile.UserID: profile}})
	if err := proj.PublishUserEvent(context.Background(), event.UserAvatarUpdated, profile.UserID, profile.UserID, nil); err != nil {
		t.Fatalf("PublishUserEvent err=%v", err)
	}

	want := es.DocumentToIndex(application.ProjectUserProfileToSearchDocument(profile))
	raw, _ := json.Marshal(want)
	var wantJSON map[string]any
	_ = json.Unmarshal(raw, &wantJSON)

	got := f.upserts["user.profile:user_1"]
	if !reflect.DeepEqual(got, wantJSON) {
		t.Fatalf("indexed doc diverged from shared projection:\n got=%#v\nwant=%#v", got, wantJSON)
	}
}

func TestProjectorDeletesWhenNoLongerEligible(t *testing.T) {
	profile := activeProfile()
	profile.Status = "suspended" // suspended => drop from index
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.UserProfile{profile.UserID: profile}})

	if err := proj.PublishUserEvent(context.Background(), event.UserProfileUpdated, profile.UserID, profile.UserID, nil); err != nil {
		t.Fatalf("PublishUserEvent err=%v", err)
	}
	if len(f.upserts) != 0 {
		t.Fatalf("suspended profile must not be upserted: %#v", f.upserts)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "user.profile:user_1" {
		t.Fatalf("expected delete for ineligible profile, got %#v", f.deletes)
	}
}

func TestProjectorDeletesWhenProfileMissing(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{}) // store returns nil, nil

	if err := proj.PublishUserEvent(context.Background(), event.UserProfileUpdated, "user_gone", "user_gone", nil); err != nil {
		t.Fatalf("PublishUserEvent err=%v", err)
	}
	if len(f.deletes) != 1 || f.deletes[0] != "user.profile:user_gone" {
		t.Fatalf("missing profile should be deleted from index, got %#v", f.deletes)
	}
}

// TestProjectorReadBackErrorDoesNotMutate asserts a transient read-back error
// neither upserts nor deletes (so a DB blip never drops a live profile).
func TestProjectorReadBackErrorDoesNotMutate(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{err: errors.New("db down")})

	if err := proj.PublishUserEvent(context.Background(), event.UserProfileUpdated, "user_1", "user_1", nil); err != nil {
		t.Fatalf("PublishUserEvent err=%v", err)
	}
	if len(f.upserts) != 0 || len(f.deletes) != 0 {
		t.Fatalf("read-back error must not touch the index: upserts=%#v deletes=%#v", f.upserts, f.deletes)
	}
}

func TestProjectorIgnoresUnrelatedEvents(t *testing.T) {
	profile := activeProfile()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.UserProfile{profile.UserID: profile}})

	for _, et := range []string{"PersonaFollowStateChanged", "PersonaBlocked", "SomethingElse"} {
		if err := proj.PublishUserEvent(context.Background(), et, profile.UserID, profile.UserID, nil); err != nil {
			t.Fatalf("PublishUserEvent(%s) err=%v", et, err)
		}
	}
	if len(f.upserts) != 0 || len(f.deletes) != 0 {
		t.Fatalf("unrelated events must not touch the index: upserts=%#v deletes=%#v", f.upserts, f.deletes)
	}
}

// TestProjectorESOutageDoesNotBlock asserts an ES write failure is swallowed
// (recorded, returns nil) so the primary profile write path is never blocked.
func TestProjectorESOutageDoesNotBlock(t *testing.T) {
	profile := activeProfile()
	f := newFakeES()
	f.writeFailStatus = http.StatusServiceUnavailable
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]model.UserProfile{profile.UserID: profile}})

	if err := proj.PublishUserEvent(context.Background(), event.UserProfileUpdated, profile.UserID, profile.UserID, nil); err != nil {
		t.Fatalf("ES outage must not propagate to the write path, got err=%v", err)
	}
}

func TestProjectorNilIndexerIsNoOp(t *testing.T) {
	var proj *Projector // nil receiver
	if err := proj.PublishUserEvent(context.Background(), event.UserProfileUpdated, "x", "x", nil); err != nil {
		t.Fatalf("nil projector must be a no-op, got %v", err)
	}
	proj = NewProjector(nil, fakeReader{}) // nil indexer
	if err := proj.PublishUserEvent(context.Background(), event.UserProfileUpdated, "x", "x", nil); err != nil {
		t.Fatalf("nil indexer must be a no-op, got %v", err)
	}
}

// recordingPublisher records PublishUserEvent calls for the composite test.
type recordingPublisher struct {
	calls int
	err   error
}

func (r *recordingPublisher) PublishUserEvent(context.Context, string, string, string, map[string]any) error {
	r.calls++
	return r.err
}

// TestComposePublisherFansOutAndPropagatesPrimaryError asserts the composite
// calls every publisher and returns the primary's error (search is best-effort).
func TestComposePublisherFansOutAndPropagatesPrimaryError(t *testing.T) {
	primary := &recordingPublisher{err: errors.New("mq down")}
	search := &recordingPublisher{}
	composite := ComposePublisher(primary, nil, search)

	err := composite.PublishUserEvent(context.Background(), event.UserProfileUpdated, "user_1", "user_1", nil)
	if err == nil || err.Error() != "mq down" {
		t.Fatalf("expected primary error to propagate, got %v", err)
	}
	if primary.calls != 1 || search.calls != 1 {
		t.Fatalf("composite must fan out to both: primary=%d search=%d", primary.calls, search.calls)
	}
}
