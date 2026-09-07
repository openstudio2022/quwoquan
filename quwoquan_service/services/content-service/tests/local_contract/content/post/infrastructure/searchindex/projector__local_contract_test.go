// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/design.md#dec-002
package searchindex_test

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/searchindex"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
)

// fakeES simulates the subset of the ES HTTP API the versioned writer uses, so
// the projector can be driven through the real es.Client transport (parallel to
// runtime/search/es.fakeCluster). Every _doc write must carry
// version_type=external; a tombstone body (deleted=true) is recorded under
// tombstones, a live body under upserts. writeFailStatus forces writes to fail.
type fakeES struct {
	mu              sync.Mutex
	upserts         map[string]map[string]any
	tombstones      map[string]map[string]any
	versions        map[string]int64
	unversioned     []string
	hardDeletes     []string
	writeFailStatus int
}

func newFakeES() *fakeES {
	return &fakeES{
		upserts:    map[string]map[string]any{},
		tombstones: map[string]map[string]any{},
		versions:   map[string]int64{},
	}
}

func (f *fakeES) handler() http.Handler {
	docPrefix := "/" + es.DefaultIndex + "/_doc/"
	updatePrefix := "/" + es.DefaultIndex + "/_update/"
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/":
			writeJSON(w, http.StatusOK, map[string]any{"cluster_name": "fake"})
		case r.Method == http.MethodPut && strings.HasPrefix(r.URL.Path, docPrefix):
			if f.writeFailStatus != 0 {
				w.WriteHeader(f.writeFailStatus)
				return
			}
			id := strings.TrimPrefix(r.URL.Path, docPrefix)
			body, _ := io.ReadAll(r.Body)
			var doc map[string]any
			_ = json.Unmarshal(body, &doc)
			rawVersion := r.URL.Query().Get("version")
			if rawVersion == "" || r.URL.Query().Get("version_type") != "external" {
				f.unversioned = append(f.unversioned, id)
				writeJSON(w, http.StatusCreated, map[string]any{"result": "created"})
				return
			}
			version, _ := strconv.ParseInt(rawVersion, 10, 64)
			if f.versions[id] >= version {
				writeJSON(w, http.StatusConflict, map[string]any{"error": "version_conflict_engine_exception"})
				return
			}
			f.versions[id] = version
			if doc["deleted"] == true {
				f.tombstones[id] = doc
				delete(f.upserts, id)
			} else {
				f.upserts[id] = doc
				delete(f.tombstones, id)
			}
			writeJSON(w, http.StatusCreated, map[string]any{"result": "created"})
		case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, updatePrefix):
			// Conflict classification: the fake treats every conflict as a
			// stale/replayed write (noop) unless the digest differs at an equal
			// version, which the real script reports as a digest conflict.
			id := strings.TrimPrefix(r.URL.Path, updatePrefix)
			body, _ := io.ReadAll(r.Body)
			var request struct {
				Script struct {
					Params struct {
						SourceVersion int64  `json:"sourceVersion"`
						SourceDigest  string `json:"sourceDigest"`
					} `json:"params"`
				} `json:"script"`
			}
			_ = json.Unmarshal(body, &request)
			stored := f.upserts[id]
			if stored == nil {
				stored = f.tombstones[id]
			}
			storedDigest, _ := stored["sourceDigest"].(string)
			if f.versions[id] == request.Script.Params.SourceVersion && storedDigest != request.Script.Params.SourceDigest {
				writeJSON(w, http.StatusBadRequest, map[string]any{"error": "QWQ_SAME_VERSION_DIGEST_CONFLICT"})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{"result": "noop"})
		case r.Method == http.MethodDelete && strings.HasPrefix(r.URL.Path, docPrefix):
			f.hardDeletes = append(f.hardDeletes, strings.TrimPrefix(r.URL.Path, docPrefix))
			writeJSON(w, http.StatusOK, map[string]any{"result": "deleted"})
		default:
			writeUnexpectedRequest(w, r)
		}
	})
}

func (f *fakeES) tombstoneIDs() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]string, 0, len(f.tombstones))
	for id := range f.tombstones {
		out = append(out, id)
	}
	return out
}

func (f *fakeES) assertOnlyVersionedWrites(t *testing.T) {
	t.Helper()
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.unversioned) != 0 || len(f.hardDeletes) != 0 {
		t.Fatalf("projector must only issue versioned writes: unversioned=%v hardDeletes=%v", f.unversioned, f.hardDeletes)
	}
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

// fakeReader is an in-memory PostReader for projector/backfill tests.
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

func publishedPost() postmodel.Post {
	return postmodel.Post{
		ID: "post_1", Version: 3, Title: "洱海骑行攻略", Summary: "环湖一日", Body: "正文",
		ContentType: "video", Status: "published", Visibility: "public", ModerationStatus: "approved",
		ContentIdentity: "work", CoverUrl: "https://cdn.example/post.webp",
		Width: 1280, Height: 720,
		AuthorId: "user_9", AuthorDisplayNameSnapshot: "alice",
		AuthorAvatarUrlSnapshot: "https://cdn.example/alice.webp",
		TagRefs:                 []string{"骑行", "洱海"}, EntityRefs: []string{"洱海"},
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

func TestProjectorUpsertsOnPublishUnderPostVersion(t *testing.T) {
	post := publishedPost()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostPublished", AggregateType: "Post", AggregateID: post.ID, AggregateVersion: post.Version,
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
	if doc["sourceVersion"] != float64(post.Version) || doc["deleted"] != false || f.versions[id] != post.Version {
		t.Fatalf("document must be fenced by the Post's own version: doc=%#v versions=%v", doc, f.versions)
	}
	payload, ok := doc["payload"].(map[string]any)
	if !ok ||
		payload["authorAvatarUrl"] != post.AuthorAvatarUrlSnapshot ||
		payload["contentIdentity"] != "work" ||
		payload["coverUrl"] != post.CoverUrl ||
		payload["coverWidth"] != "1280" ||
		payload["coverHeight"] != "720" ||
		payload["likeCount"] != "3" ||
		payload["publishedAt"] != post.PublishedAt.Format(time.RFC3339Nano) {
		t.Fatalf("post presentation payload incomplete: %#v", doc["payload"])
	}
	f.assertOnlyVersionedWrites(t)
}

// TestProjectorSharesProjectionWithCandidateSource proves the projector indexes
// exactly what searchprojection.ProjectPostToSearchDocument produces (the same function
// PostCandidateSource uses) — a single projection truth source.
func TestProjectorSharesProjectionWithCandidateSource(t *testing.T) {
	post := publishedPost()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})
	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostPublished", AggregateID: post.ID, AggregateVersion: post.Version,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}

	want, err := es.WithCanonicalSourceDigest(es.DocumentToIndex(searchprojection.ProjectPostToSearchDocument(post), post.Version))
	if err != nil {
		t.Fatal(err)
	}
	// Normalize through JSON because the fake ES decodes the stored doc from JSON.
	raw, _ := json.Marshal(want)
	var wantJSON map[string]any
	_ = json.Unmarshal(raw, &wantJSON)

	got := f.upserts["content.post:post_1"]
	if !reflect.DeepEqual(got, wantJSON) {
		t.Fatalf("indexed doc diverged from shared projection:\n got=%#v\nwant=%#v", got, wantJSON)
	}
}

// TestProjectorStaleEventDoesNotRegressNewerDocument 固定 DEC-002 的核心保证：
// 迟到的低版本事件不能覆盖索引里已经存在的更高版本文档。
func TestProjectorStaleEventDoesNotRegressNewerDocument(t *testing.T) {
	newer := publishedPost()
	newer.Version = 5
	newer.Title = "版本五"
	f := newFakeES()
	reader := fakeReader{byID: map[string]postmodel.Post{newer.ID: newer}}
	proj := newProjectorWithFakeES(t, f, reader)
	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostUpdated", AggregateID: newer.ID, AggregateVersion: 5,
	}); err != nil {
		t.Fatalf("Project(v5) err=%v", err)
	}
	// 权威存储回退到更低版本只会发生在测试里；这里用它模拟一个迟到的旧读回。
	older := newer
	older.Version = 4
	older.Title = "版本四"
	reader.byID[newer.ID] = older
	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostUpdated", AggregateID: newer.ID, AggregateVersion: 4,
	}); err != nil {
		t.Fatalf("stale replay must be a silent success, err=%v", err)
	}
	if got := f.upserts["content.post:post_1"]; got["title"] != "版本五" || f.versions["content.post:post_1"] != 5 {
		t.Fatalf("stale write regressed the newer document: %#v versions=%v", got, f.versions)
	}
}

func TestProjectorTombstonesDeletedPostUnderItsVersion(t *testing.T) {
	post := publishedPost()
	post.Status = "deleted"
	post.Version = 4
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostDeleted", AggregateID: post.ID, AggregateVersion: 4,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if ids := f.tombstoneIDs(); len(ids) != 1 || ids[0] != "content.post:post_1" {
		t.Fatalf("expected tombstone of content.post:post_1, got %#v", ids)
	}
	if f.versions["content.post:post_1"] != 4 || f.tombstones["content.post:post_1"]["deleted"] != true {
		t.Fatalf("tombstone must be fenced by the deleted Post's version: %#v", f.tombstones)
	}
	f.assertOnlyVersionedWrites(t)
}

func TestProjectorTombstonesWhenNoLongerEligible(t *testing.T) {
	post := publishedPost()
	post.Visibility = "private" // turned private => must drop from the index
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostSettingsUpdated", AggregateID: post.ID, AggregateVersion: post.Version,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if len(f.upserts) != 0 {
		t.Fatalf("private post must not be upserted: %#v", f.upserts)
	}
	if ids := f.tombstoneIDs(); len(ids) != 1 || ids[0] != "content.post:post_1" {
		t.Fatalf("expected tombstone for ineligible post, got %#v", ids)
	}
}

func TestProjectorTombstonesModerationRejectedPost(t *testing.T) {
	post := publishedPost()
	post.ModerationStatus = "rejected"
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostSettingsUpdated", AggregateID: post.ID, AggregateVersion: post.Version,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if len(f.upserts) != 0 {
		t.Fatalf("moderation rejected post must not be upserted: %#v", f.upserts)
	}
	if ids := f.tombstoneIDs(); len(ids) != 1 || ids[0] != "content.post:post_1" {
		t.Fatalf("expected rejected post tombstone, got %#v", ids)
	}
}

// TestProjectorTombstonesMissingPostUnderEventVersion 固定权威对象已不可读时的
// 版本来源：outbox 事实的 AggregateVersion。没有版本就必须 fail closed，
// 禁止退回无版本删除。
func TestProjectorTombstonesMissingPostUnderEventVersion(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{}) // store returns not-found

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostPublished", AggregateID: "post_gone", AggregateVersion: 9,
	}); err != nil {
		t.Fatalf("Project err=%v", err)
	}
	if ids := f.tombstoneIDs(); len(ids) != 1 || ids[0] != "content.post:post_gone" || f.versions["content.post:post_gone"] != 9 {
		t.Fatalf("missing post must be tombstoned under the event version, got %#v versions=%v", ids, f.versions)
	}

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostDeleted", AggregateID: "post_gone_unversioned",
	}); err == nil {
		t.Fatal("missing post without an event version must fail closed instead of deleting unversioned")
	}
	f.assertOnlyVersionedWrites(t)
}

func TestProjectorRejectsPostWithoutVersion(t *testing.T) {
	post := publishedPost()
	post.Version = 0
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostPublished", AggregateID: post.ID, AggregateVersion: 1,
	}); err == nil {
		t.Fatal("a Post without a positive version must not be projected")
	}
	if len(f.upserts) != 0 || len(f.tombstones) != 0 {
		t.Fatalf("no write may happen without a version: upserts=%#v tombstones=%#v", f.upserts, f.tombstones)
	}
}

func TestProjectorReadFailureKeepsOutboxCheckpointReplayable(t *testing.T) {
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{loadErr: errors.New("malformed Mongo Post")})

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostSettingsUpdated", AggregateID: "post-corrupt", AggregateVersion: 1,
	}); err == nil {
		t.Fatal("Post read failure must fail search projection")
	}
	if len(f.upserts) != 0 || len(f.tombstones) != 0 {
		t.Fatalf("read failure must not mutate search index: upserts=%#v tombstones=%#v", f.upserts, f.tombstones)
	}
}

func TestProjectorIgnoresCounterOnlyEvents(t *testing.T) {
	post := publishedPost()
	f := newFakeES()
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	for _, et := range []string{"ContentReactionSet", "BehaviorBatchReported", "SomethingElse"} {
		if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: et, AggregateID: post.ID, AggregateVersion: post.Version}); err != nil {
			t.Fatalf("Project(%s) err=%v", et, err)
		}
	}
	if len(f.upserts) != 0 || len(f.tombstones) != 0 {
		t.Fatalf("counter-only events must not touch the index: upserts=%#v tombstones=%#v", f.upserts, f.tombstones)
	}
}

// TestProjectorESOutageKeepsOutboxConsumerReplayable asserts an ES failure is
// returned to the dedicated relay. The primary write has already committed;
// this error only prevents the search consumer checkpoint from advancing.
func TestProjectorESOutageKeepsOutboxConsumerReplayable(t *testing.T) {
	post := publishedPost()
	f := newFakeES()
	f.writeFailStatus = http.StatusServiceUnavailable
	proj := newProjectorWithFakeES(t, f, fakeReader{byID: map[string]postmodel.Post{post.ID: post}})

	if err := proj.Project(context.Background(), ports.ProjectorEvent{
		Type: "PostPublished", AggregateID: post.ID, AggregateVersion: post.Version,
	}); err == nil {
		t.Fatal("ES outage must fail the search outbox consumer")
	}
}

func TestProjectorMissingIndexerFailsFast(t *testing.T) {
	var proj *Projector // nil receiver
	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostPublished", AggregateID: "x"}); err == nil {
		t.Fatal("nil projector must fail")
	}
	proj = NewProjector(nil, fakeReader{}) // nil indexer
	if err := proj.Project(context.Background(), ports.ProjectorEvent{Type: "PostPublished", AggregateID: "x"}); err == nil {
		t.Fatal("nil indexer must fail")
	}
}
