package es

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
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
	deletes     []string
	bulkBody    string
	authHeader  string
	searchSrc   []map[string]any
	searchScore float64
}

func newFakeCluster() *fakeCluster {
	return &fakeCluster{
		upserts:     map[string]map[string]any{},
		searchScore: 1.5,
		mappingCode: http.StatusOK,
	}
}

func (f *fakeCluster) handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f.authHeader = r.Header.Get("Authorization")
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/":
			writeJSON(w, http.StatusOK, map[string]any{"cluster_name": "fake"})
		case r.Method == http.MethodHead && r.URL.Path == "/"+DefaultIndex:
			if f.created {
				w.WriteHeader(http.StatusOK)
			} else {
				w.WriteHeader(http.StatusNotFound)
			}
		case r.Method == http.MethodPut && r.URL.Path == "/"+DefaultIndex:
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &f.createBody)
			f.created = true
			writeJSON(w, http.StatusOK, map[string]any{"acknowledged": true})
		case r.Method == http.MethodPut && r.URL.Path == "/"+DefaultIndex+"/_mapping":
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
			f.upserts[id] = doc
			writeJSON(w, http.StatusCreated, map[string]any{"result": "created"})
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

func TestClientUpsertAndDelete(t *testing.T) {
	fc := newFakeCluster()
	srv := httptest.NewServer(fc.handler())
	defer srv.Close()
	c := newTestClient(t, srv)

	if err := c.Upsert(context.Background(), "", "content.post:post_1", map[string]any{"title": "x"}); err != nil {
		t.Fatalf("Upsert err=%v", err)
	}
	if _, ok := fc.upserts["content.post:post_1"]; !ok {
		t.Fatalf("upsert not recorded: %#v", fc.upserts)
	}
	if fc.authHeader == "" {
		t.Fatalf("basic auth header not sent")
	}
	if err := c.Delete(context.Background(), "", "content.post:post_1"); err != nil {
		t.Fatalf("Delete err=%v", err)
	}
	if len(fc.deletes) != 1 {
		t.Fatalf("delete not recorded: %#v", fc.deletes)
	}
}

func TestClientBulkEmitsNDJSON(t *testing.T) {
	fc := newFakeCluster()
	srv := httptest.NewServer(fc.handler())
	defer srv.Close()
	c := newTestClient(t, srv)

	events := []ChangeEvent{
		{Op: OpUpsert, Doc: rtsearch.Document{ObjectType: rtsearch.ObjectTypeUserProfile, ObjectID: "u1", Title: "alice", Freshness: time.Now()}},
		{Op: OpDelete, Doc: rtsearch.Document{ObjectType: rtsearch.ObjectTypeUserProfile, ObjectID: "u2"}},
	}
	if err := c.Bulk(context.Background(), "", events); err != nil {
		t.Fatalf("Bulk err=%v", err)
	}
	lines := strings.Split(strings.TrimSpace(fc.bulkBody), "\n")
	// upsert => 2 lines (action + doc), delete => 1 line => total 3.
	if len(lines) != 3 {
		t.Fatalf("want 3 ndjson lines, got %d: %q", len(lines), fc.bulkBody)
	}
	if !strings.Contains(lines[0], "\"index\"") || !strings.Contains(lines[0], "user.profile:u1") {
		t.Fatalf("bad index action line: %q", lines[0])
	}
	if !strings.Contains(lines[2], "\"delete\"") || !strings.Contains(lines[2], "user.profile:u2") {
		t.Fatalf("bad delete action line: %q", lines[2])
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
