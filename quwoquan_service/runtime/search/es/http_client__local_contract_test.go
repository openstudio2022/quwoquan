package es

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

// fakeCluster simulates the subset of the ES/OpenSearch HTTP API the client uses.
type fakeCluster struct {
	created     bool
	createBody  map[string]any
	mappingBody map[string]any
	mappingCode int
	lastSearch  map[string]any
	upserts     map[string]map[string]any
	versions    map[string]int64
	versionHits []string
	deletes     []string
	bulkBody    string
	authHeader  string
	searchSrc   []map[string]any
	searchScore float64
}

func newFakeCluster() *fakeCluster {
	return &fakeCluster{
		upserts:     map[string]map[string]any{},
		versions:    map[string]int64{},
		searchScore: 1.5,
		mappingCode: http.StatusOK,
	}
}

func (f *fakeCluster) handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.authHeader = r.Header.Get("Authorization")
		physical := DefaultIndex + "-v1"
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/":
			writeJSON(w, http.StatusOK, map[string]any{"cluster_name": "fake"})
		case r.Method == http.MethodGet && r.URL.Path == "/_alias/"+DefaultIndex:
			if f.created {
				writeJSON(w, http.StatusOK, map[string]any{
					physical: map[string]any{"aliases": map[string]any{DefaultIndex: map[string]any{}}},
				})
			} else {
				writeJSON(w, http.StatusNotFound, map[string]any{"error": "alias missing"})
			}
		case r.Method == http.MethodHead && r.URL.Path == "/"+DefaultIndex:
			// The alias name never doubles as a legacy physical index here.
			w.WriteHeader(http.StatusNotFound)
		case r.Method == http.MethodPut && r.URL.Path == "/"+physical:
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &f.createBody)
			f.created = true
			writeJSON(w, http.StatusOK, map[string]any{"acknowledged": true})
		case r.Method == http.MethodPut && r.URL.Path == "/"+physical+"/_mapping":
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &f.mappingBody)
			if f.mappingCode == http.StatusOK {
				writeJSON(w, http.StatusOK, map[string]any{"acknowledged": true})
			} else {
				writeJSON(w, f.mappingCode, map[string]any{
					"error": "mapper conflict",
				})
			}
		case r.Method == http.MethodPost && r.URL.Path == "/"+DefaultIndex+"/_search":
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &f.lastSearch)
			writeJSON(w, http.StatusOK, f.searchPayload())
		case r.Method == http.MethodPut && strings.HasPrefix(r.URL.Path, "/"+DefaultIndex+"/_doc/"):
			id := strings.TrimPrefix(r.URL.Path, "/"+DefaultIndex+"/_doc/")
			body, _ := io.ReadAll(r.Body)
			var doc map[string]any
			_ = json.Unmarshal(body, &doc)
			if rawVersion := r.URL.Query().Get("version"); rawVersion != "" {
				version, _ := strconv.ParseInt(rawVersion, 10, 64)
				f.versionHits = append(f.versionHits, r.URL.RawQuery)
				if r.URL.Query().Get("version_type") != "external" || f.versions[id] >= version {
					writeJSON(w, http.StatusConflict, map[string]any{"error": "version_conflict_engine_exception"})
					return
				}
				f.versions[id] = version
			}
			f.upserts[id] = doc
			writeJSON(w, http.StatusCreated, map[string]any{"result": "created"})
		case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/"+DefaultIndex+"/_update/"):
			id := strings.TrimPrefix(r.URL.Path, "/"+DefaultIndex+"/_update/")
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
			stored, ok := f.upserts[id]
			currentVersion := f.versions[id]
			currentDigest, _ := stored["sourceDigest"].(string)
			switch {
			case !ok || currentVersion <= 0 || currentDigest == "":
				writeJSON(w, http.StatusBadRequest, map[string]any{"error": versionConflictStateMarker})
			case currentVersion > request.Script.Params.SourceVersion:
				writeJSON(w, http.StatusOK, map[string]any{"result": "noop"})
			case currentVersion == request.Script.Params.SourceVersion && currentDigest == request.Script.Params.SourceDigest:
				writeJSON(w, http.StatusOK, map[string]any{"result": "noop"})
			case currentVersion == request.Script.Params.SourceVersion:
				writeJSON(w, http.StatusBadRequest, map[string]any{"error": versionConflictDigestMarker})
			default:
				writeJSON(w, http.StatusBadRequest, map[string]any{"error": versionConflictStateMarker})
			}
		case r.Method == http.MethodDelete && strings.HasPrefix(r.URL.Path, "/"+DefaultIndex+"/_doc/"):
			id := strings.TrimPrefix(r.URL.Path, "/"+DefaultIndex+"/_doc/")
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

func (f *fakeCluster) searchPayload() map[string]any {
	hits := make([]map[string]any, 0, len(f.searchSrc))
	for _, src := range f.searchSrc {
		hits = append(hits, map[string]any{"_id": src["objectId"], "_score": f.searchScore, "_source": src})
	}
	return map[string]any{"hits": map[string]any{"hits": hits}}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func newTestClient(t *testing.T, srv *httptest.Server) *Client {
	t.Helper()
	c, err := NewClient(Config{
		Endpoints: []string{srv.URL},
		Username:  "elastic",
		Password:  "secret",
		Schema:    IndexSchemaConfig{Synonyms: []string{"民宿,客栈"}},
	})
	if err != nil {
		t.Fatalf("NewClient err=%v", err)
	}
	return c
}

func TestClientEnsureIndexCreatesWithAnalyzer(t *testing.T) {
	fc := newFakeCluster()
	srv := httptest.NewServer(fc.handler())
	defer srv.Close()
	c := newTestClient(t, srv)

	if err := c.EnsureIndex(context.Background()); err != nil {
		t.Fatalf("EnsureIndex err=%v", err)
	}
	if !fc.created {
		t.Fatalf("index was not created")
	}
	settings, _ := fc.createBody["settings"].(map[string]any)
	analysis, _ := settings["analysis"].(map[string]any)
	analyzers, _ := analysis["analyzer"].(map[string]any)
	if _, ok := analyzers[analyzerSearch]; !ok {
		t.Fatalf("search analyzer missing: %#v", analyzers)
	}
	mappings, _ := fc.createBody["mappings"].(map[string]any)
	props, _ := mappings["properties"].(map[string]any)
	target, _ := props["target"].(map[string]any)
	if target["type"] != "keyword" {
		t.Fatalf("target field should be keyword, got %#v", target)
	}
	sourceVersion, _ := props["sourceVersion"].(map[string]any)
	sourceDigest, _ := props["sourceDigest"].(map[string]any)
	deleted, _ := props["deleted"].(map[string]any)
	if sourceVersion["type"] != "long" || sourceDigest["type"] != "keyword" || deleted["type"] != "boolean" {
		t.Fatalf("version/digest/tombstone mappings missing: sourceVersion=%#v sourceDigest=%#v deleted=%#v", sourceVersion, sourceDigest, deleted)
	}

	// Existing indexes must reconcile mappings without re-creating the index.
	fc.createBody = nil
	if err := c.EnsureIndex(context.Background()); err != nil {
		t.Fatalf("EnsureIndex(2) err=%v", err)
	}
	if fc.createBody != nil {
		t.Fatalf("EnsureIndex should be idempotent, re-created index")
	}
	mappingProperties, _ := fc.mappingBody["properties"].(map[string]any)
	payload, _ := mappingProperties["payload"].(map[string]any)
	if payload["type"] != "object" || payload["enabled"] != false {
		t.Fatalf("existing index did not receive disabled payload mapping: %#v", payload)
	}
}

func TestClientEnsureIndexRejectsIncompatibleExistingMapping(t *testing.T) {
	cluster := newFakeCluster()
	cluster.created = true
	cluster.mappingCode = http.StatusBadRequest
	server := httptest.NewServer(cluster.handler())
	defer server.Close()
	client := newTestClient(t, server)

	err := client.EnsureIndex(context.Background())
	if !errors.Is(err, ErrIndexSchemaIncompatible) {
		t.Fatalf("incompatible mapping error=%v", err)
	}
}

func TestClientSearchMapsHitsToCandidates(t *testing.T) {
	fc := newFakeCluster()
	fc.searchScore = 2.25
	fc.searchSrc = []map[string]any{{
		"objectType":  rtsearch.ObjectTypeContentPost,
		"objectId":    "post_1",
		"title":       "洱海骑行攻略",
		"summary":     "环湖一日",
		"contentType": "video",
		"target":      string(rtsearch.TargetVideo),
		"visibility":  "public",
		"tags":        []any{"骑行", "洱海"},
		"authorId":    "user_9",
		"authorName":  "alice",
	}}
	srv := httptest.NewServer(fc.handler())
	defer srv.Close()
	c := newTestClient(t, srv)

	cands, err := c.Search(context.Background(), "", map[string]any{"size": 10})
	if err != nil {
		t.Fatalf("Search err=%v", err)
	}
	if len(cands) != 1 {
		t.Fatalf("want 1 candidate, got %d", len(cands))
	}
	got := cands[0]
	if got.Source != "elasticsearch" || got.BaseScore != 2.25 {
		t.Fatalf("bad candidate meta: %#v", got)
	}
	doc := got.Document
	if doc.ObjectID != "post_1" || doc.Title != "洱海骑行攻略" {
		t.Fatalf("bad doc: %#v", doc)
	}
	// ContentType 必须来自索引字段，禁止从 target 推导。
	if doc.ContentType != "video" {
		t.Fatalf("contentType not preserved: %q", doc.ContentType)
	}
	if rtsearch.TargetForDocument(doc) != rtsearch.TargetVideo {
		t.Fatalf("target not preserved, contentType=%q", doc.ContentType)
	}
	if doc.Fields["authorName"] != "alice" || len(doc.Tags) != 2 {
		t.Fatalf("anchors/tags lost: %#v", doc)
	}
}

func TestClientCheckSearchReadyRejectsRootOnlyLiveness(t *testing.T) {
	var readinessBody map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/":
			writeJSON(w, http.StatusOK, map[string]any{"cluster_name": "root-only"})
		case r.Method == http.MethodPost && r.URL.Path == "/"+DefaultIndex+"/_search":
			if err := json.NewDecoder(r.Body).Decode(&readinessBody); err != nil {
				t.Fatalf("decode readiness body: %v", err)
			}
			writeJSON(w, http.StatusServiceUnavailable, map[string]any{"error": "shards unavailable"})
		default:
			http.Error(w, "unexpected "+r.Method+" "+r.URL.Path, http.StatusTeapot)
		}
	}))
	defer server.Close()
	client := newTestClient(t, server)

	if err := client.Ping(context.Background()); err != nil {
		t.Fatalf("root liveness should pass: %v", err)
	}
	err := client.CheckSearchReady(context.Background())
	if !errors.Is(err, ErrDependencyUnavailable) {
		t.Fatalf("query readiness error=%v, want ErrDependencyUnavailable", err)
	}
	if readinessBody["size"] != float64(1) || readinessBody["track_total_hits"] != false {
		t.Fatalf("readiness query must exercise one bounded hit: %#v", readinessBody)
	}
}

func TestClientCheckSearchReadyAcceptsQueryableAlias(t *testing.T) {
	cluster := newFakeCluster()
	server := httptest.NewServer(cluster.handler())
	defer server.Close()
	client := newTestClient(t, server)

	if err := client.CheckSearchReady(context.Background()); err != nil {
		t.Fatalf("CheckSearchReady err=%v", err)
	}
	if cluster.lastSearch["size"] != float64(1) || cluster.lastSearch["_source"] != false {
		t.Fatalf("unexpected readiness query: %#v", cluster.lastSearch)
	}
}

func TestClientVersionedWriteSendsAuthAndExternalVersion(t *testing.T) {
	fc := newFakeCluster()
	srv := httptest.NewServer(fc.handler())
	defer srv.Close()
	c := newTestClient(t, srv)

	applied, err := c.UpsertVersioned(context.Background(), "", "content.post:post_1", 1, map[string]any{"title": "x"})
	if err != nil || !applied {
		t.Fatalf("UpsertVersioned applied=%v err=%v", applied, err)
	}
	if _, ok := fc.upserts["content.post:post_1"]; !ok {
		t.Fatalf("upsert not recorded: %#v", fc.upserts)
	}
	if fc.authHeader == "" {
		t.Fatalf("basic auth header not sent")
	}
	if len(fc.versionHits) != 1 || !strings.Contains(fc.versionHits[0], "version=1") || !strings.Contains(fc.versionHits[0], "version_type=external") {
		t.Fatalf("every write must carry the external version fence: %#v", fc.versionHits)
	}
	if len(fc.deletes) != 0 || fc.bulkBody != "" {
		t.Fatalf("no unversioned DELETE or _bulk transport may remain: deletes=%#v bulk=%q", fc.deletes, fc.bulkBody)
	}
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/design.md#dec-002
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#req-006
// TestClientVersionedUpsertOverLegacyDocumentWithoutSourceVersion 固定存量文档
// （无 sourceVersion/sourceDigest/deleted 字段、Elasticsearch 内部 _version 为 1）
// 的行为：第一笔 versioned 写入只要 sourceVersion 高于 _version 就会被外部版本
// 直接接受并补齐 sourceVersion/deleted；若存量 _version 已不低于 sourceVersion，
// 冲突分类脚本会因缺字段抛出 QWQ_VERSIONED_SOURCE_STATE_INVALID 并 fail closed，
// 而不是把存量文档伪装成过期写入静默吞掉。这两条共同要求存量索引在切到
// alias_replace 重建前完成 sourceVersion 回填（OPEN 见 storage topology spec）。
func TestClientVersionedUpsertOverLegacyDocumentWithoutSourceVersion(t *testing.T) {
	cluster := newFakeCluster()
	server := httptest.NewServer(cluster.handler())
	defer server.Close()
	client := newTestClient(t, server)
	id := "content.post:legacy-1"
	// 存量文档：由旧轨无版本写入，Elasticsearch 内部 _version=1，且没有任何
	// versioned 元字段。
	cluster.upserts[id] = map[string]any{"objectType": "content.post", "objectId": "legacy-1", "title": "legacy"}
	cluster.versions[id] = 1

	applied, err := client.UpsertVersioned(context.Background(), "", id, 2, map[string]any{
		"objectType": "content.post", "objectId": "legacy-1", "title": "versioned",
	})
	if err != nil || !applied {
		t.Fatalf("higher sourceVersion over legacy document applied=%v err=%v", applied, err)
	}
	stored := cluster.upserts[id]
	if stored["title"] != "versioned" || stored["sourceVersion"] != float64(2) || stored["deleted"] != false {
		t.Fatalf("legacy document must be replaced by the versioned source: %#v", stored)
	}
	if _, hasDigest := stored["sourceDigest"].(string); !hasDigest {
		t.Fatalf("versioned write must backfill sourceDigest: %#v", stored)
	}

	legacyID := "content.post:legacy-2"
	cluster.upserts[legacyID] = map[string]any{"objectType": "content.post", "objectId": "legacy-2", "title": "legacy"}
	cluster.versions[legacyID] = 3
	applied, err = client.UpsertVersioned(context.Background(), "", legacyID, 1, map[string]any{
		"objectType": "content.post", "objectId": "legacy-2", "title": "late",
	})
	if applied || err == nil || errors.Is(err, ErrSameVersionDigestConflict) || IsDependencyUnavailable(err) {
		t.Fatalf("legacy document without sourceVersion must fail closed on conflict, applied=%v err=%v", applied, err)
	}
	if !errors.Is(err, ErrVersionedWriteRejected) || !strings.Contains(err.Error(), versionConflictStateMarker) {
		t.Fatalf("conflict over legacy document must surface QWQ_VERSIONED_SOURCE_STATE_INVALID, got %v", err)
	}
	if cluster.upserts[legacyID]["title"] != "legacy" {
		t.Fatalf("rejected write must not mutate the legacy document: %#v", cluster.upserts[legacyID])
	}
}

func TestIndexToDocumentRoundTrip(t *testing.T) {
	orig := rtsearch.Document{
		ObjectType:  rtsearch.ObjectTypeContentPost,
		ObjectID:    "post_42",
		Title:       "大理三日",
		Summary:     "古城+洱海+苍山",
		Body:        "正文",
		ContentType: "article",
		Visibility:  "public",
		Tags:        []string{"大理", "旅行"},
		Entities:    []string{"洱海"},
		Popularity:  3.5,
		Freshness:   time.Date(2026, 5, 1, 0, 0, 0, 0, time.UTC),
		Fields: map[string]string{
			"authorId": "u7", "authorName": "bob", "entityName": "洱海",
			"coverUrl": "https://cdn.example/cover.webp", "likeCount": "12",
		},
	}
	indexed := DocumentToIndex(orig)
	// JSON round-trip to mimic ES storing/returning _source ([]string -> []any).
	raw, _ := json.Marshal(indexed)
	var source map[string]any
	if err := json.Unmarshal(raw, &source); err != nil {
		t.Fatalf("unmarshal source err=%v", err)
	}
	got := IndexToDocument(source)
	if got.ObjectID != orig.ObjectID || got.Title != orig.Title || got.ContentType != "article" {
		t.Fatalf("scalar round-trip mismatch: %#v", got)
	}
	if len(got.Tags) != 2 || got.Tags[0] != "大理" {
		t.Fatalf("tags round-trip mismatch: %#v", got.Tags)
	}
	if got.Fields["authorName"] != "bob" || got.Fields["entityName"] != "洱海" {
		t.Fatalf("anchor round-trip mismatch: %#v", got.Fields)
	}
	if got.Fields["coverUrl"] != "https://cdn.example/cover.webp" ||
		got.Fields["likeCount"] != "12" {
		t.Fatalf("presentation payload round-trip mismatch: %#v", got.Fields)
	}
	if !got.Freshness.Equal(orig.Freshness) {
		t.Fatalf("freshness round-trip mismatch: %v", got.Freshness)
	}
}

func TestClientVersionedWritesClassifyConflictByVersionAndDigest(t *testing.T) {
	cluster := newFakeCluster()
	server := httptest.NewServer(cluster.handler())
	defer server.Close()
	client := newTestClient(t, server)
	id := "entity.homepage:homepage-1"
	v2 := map[string]any{
		"objectType": "entity.homepage", "objectId": "homepage-1", "title": "version two",
	}

	applied, err := client.UpsertVersioned(context.Background(), "", id, 2, v2)
	if err != nil || !applied {
		t.Fatalf("versioned upsert applied=%v err=%v", applied, err)
	}
	storedV2 := cluster.upserts[id]
	digestV2, _ := storedV2["sourceDigest"].(string)
	if !strings.HasPrefix(digestV2, "sha256:") || storedV2["sourceVersion"] != float64(2) {
		t.Fatalf("versioned source lacks canonical digest: %#v", storedV2)
	}
	if applied, err = client.UpsertVersioned(context.Background(), "", id, 1, map[string]any{"title": "stale"}); err != nil || applied {
		t.Fatalf("stale upsert applied=%v err=%v", applied, err)
	}
	if applied, err = client.UpsertVersioned(context.Background(), "", id, 2, v2); err != nil || applied {
		t.Fatalf("same-digest replay applied=%v err=%v", applied, err)
	}
	if applied, err = client.UpsertVersioned(context.Background(), "", id, 2, map[string]any{"title": "different facts"}); applied || !errors.Is(err, ErrSameVersionDigestConflict) {
		t.Fatalf("same-version different-digest applied=%v err=%v", applied, err)
	}
	if cluster.upserts[id]["title"] != "version two" {
		t.Fatalf("same-version conflict changed winner: %#v", cluster.upserts[id])
	}

	if applied, err = client.TombstoneVersioned(context.Background(), "", id, "entity.homepage", "homepage-1", 3); err != nil || !applied {
		t.Fatalf("tombstone applied=%v err=%v", applied, err)
	}
	if applied, err = client.TombstoneVersioned(context.Background(), "", id, "entity.homepage", "homepage-1", 3); err != nil || applied {
		t.Fatalf("tombstone replay applied=%v err=%v", applied, err)
	}
	if applied, err = client.UpsertVersioned(context.Background(), "", id, 3, map[string]any{"title": "same-version resurrection"}); applied || !errors.Is(err, ErrSameVersionDigestConflict) {
		t.Fatalf("same-version resurrection applied=%v err=%v", applied, err)
	}
	stored := cluster.upserts[id]
	if stored["deleted"] != true || stored["sourceVersion"] != float64(3) || !strings.HasPrefix(stored["sourceDigest"].(string), "sha256:") || len(stored) != 5 {
		t.Fatalf("tombstone body=%#v", stored)
	}
	if len(cluster.deletes) != 0 {
		t.Fatalf("versioned tombstone must not issue DELETE: %#v", cluster.deletes)
	}
	if len(cluster.versionHits) != 7 || !strings.Contains(cluster.versionHits[0], "version_type=external") {
		t.Fatalf("version query params=%#v", cluster.versionHits)
	}
}

func TestClientSearchAddsTombstoneFilterToAdHocAndHybridBodies(t *testing.T) {
	cluster := newFakeCluster()
	server := httptest.NewServer(cluster.handler())
	defer server.Close()
	client := newTestClient(t, server)

	body := map[string]any{"size": 5, "pit": map[string]any{"id": "pit-1"}, "knn": map[string]any{
		"field": "embedding", "query_vector": []float64{0.1}, "k": 1,
	}}
	// The fake only exposes indexed search, so omit PIT for transport while still
	// exercising PIT-compatible body mutation directly.
	EnsureNotDeletedSearchBody(body)
	if !queryExcludesDeleted(body["query"].(map[string]any)) {
		t.Fatalf("PIT body lacks tombstone exclusion: %#v", body)
	}
	knn := body["knn"].(map[string]any)
	if _, ok := knn["filter"].(map[string]any); !ok {
		t.Fatalf("hybrid kNN lacks tombstone filter: %#v", knn)
	}

	searchBody := map[string]any{"size": 5}
	if _, err := client.Search(context.Background(), "", searchBody); err != nil {
		t.Fatal(err)
	}
	if !queryExcludesDeleted(cluster.lastSearch["query"].(map[string]any)) {
		t.Fatalf("client Search did not enforce tombstone exclusion: %#v", cluster.lastSearch)
	}
}
