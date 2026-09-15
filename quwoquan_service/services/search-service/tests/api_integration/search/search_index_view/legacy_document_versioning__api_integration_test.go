// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/design.md#dec-002
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md#open-004
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-032
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/search-service/tests/support"
)

// TestLegacyDocumentVersioning 保留历史损坏 bytes 的恢复专项：旧形状不公开，
// 版本冲突仍 fail-closed；当前正例由生产 Indexer/VersionedWriter 生成。
// 不代表任何环境已完成 owner 重投或重建。
func TestLegacyDocumentVersioning(t *testing.T) {
	t.Setenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT", "")
	ctx := t.Context()
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	t.Cleanup(stop)

	client, err := es.NewClient(es.Config{
		Endpoints:      []string{endpoint},
		Index:          "quwoquan_objects_legacy",
		RequestTimeout: 30 * time.Second,
		Schema:         es.IndexSchemaConfig{EmbeddingDims: 2},
	})
	if err != nil {
		t.Fatalf("es client: %v", err)
	}
	if err := client.EnsureIndex(ctx); err != nil {
		t.Fatalf("EnsureIndex: %v", err)
	}
	writeIndex := client.WriteIndexName()
	raw := legacyElasticsearchHTTP{endpoint: endpoint, client: &http.Client{Timeout: 30 * time.Second}}

	const legacyID = "content.post:legacy-1"
	legacyDoc := map[string]any{
		"target":     "article",
		"objectType": "content.post",
		"objectID":   "legacy-1",
		"title":      "存量文档 无版本字段",
		"summary":    "版本化写入面之前写入的文档",
		"visibility": "public",
		"quality":    1,
	}
	// 写两次，让 ES 内部 _version 前进到 2：模拟存量文档在旧写入面上被更新过。
	for i := 0; i < 2; i++ {
		raw.put(t, ctx, "/"+writeIndex+"/_doc/"+legacyID, legacyDoc)
	}
	if err := client.Refresh(ctx); err != nil {
		t.Fatalf("refresh: %v", err)
	}

	t.Run("legacy document without current fields is hidden without mutating bytes", func(t *testing.T) {
		body := map[string]any{
			"query": map[string]any{"bool": map[string]any{
				"filter": []any{map[string]any{"term": map[string]any{"objectType": "content.post"}}},
			}},
		}
		es.EnsureCurrentSearchBody(body)
		hits := raw.searchIDs(t, ctx, "/"+client.IndexName()+"/_search", body)
		if _, ok := hits[legacyID]; ok {
			t.Fatalf("legacy document must be hidden; hits=%v", hits)
		}
	})

	t.Run("versioned upsert not newer than legacy internal version fails closed with typed state error", func(t *testing.T) {
		applied, err := client.UpsertVersioned(ctx, writeIndex, legacyID, 1, legacyDoc)
		if err == nil {
			t.Fatalf("expected typed rejection for legacy document, got applied=%v", applied)
		}
		if !errors.Is(err, es.ErrVersionedWriteRejected) {
			t.Fatalf("expected ErrVersionedWriteRejected, got %v", err)
		}
		if !errors.Is(err, es.ErrVersionedSourceStateInvalid) {
			t.Fatalf("expected ErrVersionedSourceStateInvalid, got %v", err)
		}
		if !strings.Contains(err.Error(), "QWQ_VERSIONED_SOURCE_STATE_INVALID") {
			t.Fatalf("expected QWQ_VERSIONED_SOURCE_STATE_INVALID marker, got %v", err)
		}
		source := raw.getSource(t, ctx, "/"+writeIndex+"/_doc/"+legacyID)
		if _, has := source["sourceVersion"]; has {
			t.Fatalf("rejected write must not mutate the legacy document: %v", source)
		}
	})

	t.Run("explicit current owner event and replay retain external version ordering", func(t *testing.T) {
		current := rtsearch.Document{ObjectType: "content.post", ObjectID: "legacy-1", Title: "当前露营文档", ContentType: "article", Visibility: "public"}
		indexer := es.NewIndexer(client, writeIndex)
		event := es.VersionedChangeEvent{Op: es.OpUpsert, Doc: current, SourceVersion: 3}
		applied, err := indexer.ApplyVersioned(ctx, event)
		if err != nil {
			t.Fatalf("backfill upsert: %v", err)
		}
		if !applied {
			t.Fatalf("backfill upsert must apply over legacy document")
		}
		source := raw.getSource(t, ctx, "/"+writeIndex+"/_doc/"+legacyID)
		if got, _ := source["sourceVersion"].(float64); int64(got) != 3 {
			t.Fatalf("sourceVersion must be 3 after backfill, got %v", source["sourceVersion"])
		}
		if deleted, _ := source["deleted"].(bool); deleted {
			t.Fatalf("backfilled document must not be tombstoned: %v", source)
		}
		if digest, _ := source["sourceDigest"].(string); strings.TrimSpace(digest) == "" {
			t.Fatalf("backfilled document must carry sourceDigest: %v", source)
		}
		replayed, err := indexer.ApplyVersioned(ctx, event)
		if err != nil {
			t.Fatalf("same-version replay must be idempotent noop, got %v", err)
		}
		if replayed {
			t.Fatalf("same-version replay must not report applied")
		}
		event.Doc.Title = "同版本冲突"
		if _, e := indexer.ApplyVersioned(ctx, event); !errors.Is(e, es.ErrSameVersionDigestConflict) {
			t.Fatalf("digest conflict: %v", e)
		}
		event.Op, event.SourceVersion = es.OpDelete, 4
		if _, e := indexer.ApplyVersioned(ctx, event); e != nil {
			t.Fatal(e)
		}
		event.Op, event.SourceVersion = es.OpUpsert, 3
		if applied, e := indexer.ApplyVersioned(ctx, event); applied || e != nil {
			t.Fatalf("stale resurrection %v %v", applied, e)
		}
	})

	t.Run("current multi object positives and corrupted field negatives across queries", func(t *testing.T) {
		indexer := es.NewIndexer(client, writeIndex)
		positive := map[string]struct{}{}
		for _, kind := range []string{"content.post", "user.profile", "entity.homepage", "circle.circle", "location.place"} {
			doc := rtsearch.Document{ObjectType: kind, ObjectID: "current-" + kind, Title: "当前露营", Visibility: "public", ContentType: "article"}
			event := es.VersionedChangeEvent{Op: es.OpUpsert, Doc: doc, SourceVersion: 7}
			if _, e := indexer.ApplyVersioned(ctx, event); e != nil {
				t.Fatal(e)
			}
			id := es.IndexID(doc)
			positive[id] = struct{}{}
			// 向量通过同一生产 writer 形成完整摘要，不给 fixture 手补版本或来源。
			src := raw.getSource(t, ctx, "/"+writeIndex+"/_doc/"+id)
			src["embedding"] = []float64{1, 0}
			if _, e := client.UpsertVersioned(ctx, writeIndex, id, 8, src); e != nil {
				t.Fatal(e)
			}
		}
		base := raw.getSource(t, ctx, "/"+writeIndex+"/_doc/content.post:current-content.post")
		for _, field := range []string{"deleted", "sourceVersion", "sourceDigest", "sourceKind", "target", "objectType", "objectId", "visibility"} {
			for _, mode := range []string{"missing", "null"} {
				corrupt := map[string]any{}
				for k, v := range base {
					corrupt[k] = v
				}
				if mode == "missing" {
					delete(corrupt, field)
				} else {
					corrupt[field] = nil
				}
				raw.put(t, ctx, "/"+writeIndex+"/_doc/broken-"+field+"-"+mode, corrupt)
			}
		}
		for name, mutation := range map[string]map[string]any{
			"zero": {"sourceVersion": 0}, "negative": {"sourceVersion": -1},
			"empty-digest": {"sourceDigest": ""}, "short-digest": {"sourceDigest": "sha256:a"},
			"bad-digest":     {"sourceDigest": "sha256:" + strings.Repeat("z", 64)},
			"unknown-source": {"sourceKind": "unknown"}, "tombstone": {"deleted": true},
		} {
			corrupt := map[string]any{}
			for k, v := range base {
				corrupt[k] = v
			}
			for k, v := range mutation {
				corrupt[k] = v
			}
			raw.put(t, ctx, "/"+writeIndex+"/_doc/broken-"+name, corrupt)
		}
		for _, bad := range []any{1.5, "illegal"} {
			corrupt := map[string]any{}
			for k, v := range base {
				corrupt[k] = v
			}
			corrupt["sourceVersion"] = bad
			status, _ := raw.do(t, ctx, http.MethodPut, "/"+writeIndex+"/_doc/invalid-version", corrupt)
			if status < 400 {
				t.Fatalf("mapping accepted invalid version %v", bad)
			}
		}
		if e := client.Refresh(ctx); e != nil {
			t.Fatal(e)
		}
		for _, class := range []string{"all", "term", "ids", "facet", "count", "vector", "pit"} {
			body := map[string]any{"size": 100, "query": map[string]any{"match_all": map[string]any{}}}
			switch class {
			case "term":
				body["query"] = map[string]any{"match": map[string]any{"title": "露营"}}
			case "ids":
				body["query"] = map[string]any{"prefix": map[string]any{"objectId": "current-"}}
			case "facet":
				body["aggs"] = map[string]any{"objects": map[string]any{"terms": map[string]any{"field": "objectId", "size": 100}}}
			case "count":
				body["track_total_hits"] = true
			case "vector":
				body["query"] = map[string]any{"match_none": map[string]any{}}
				body["knn"] = map[string]any{"field": "embedding", "query_vector": []float64{1, 0}, "k": 100, "num_candidates": 100}
			}
			path := "/" + client.IndexName() + "/_search"
			if class == "pit" {
				status, data := raw.do(t, ctx, http.MethodPost, "/"+client.IndexName()+"/_pit?keep_alive=1m", nil)
				if status != 200 {
					t.Fatalf("pit %d %s", status, data)
				}
				var pit struct {
					ID string `json:"id"`
				}
				if e := json.Unmarshal(data, &pit); e != nil {
					t.Fatal(e)
				}
				body["pit"] = map[string]any{"id": pit.ID, "keep_alive": "1m"}
				path = "/_search"
				defer raw.do(t, ctx, http.MethodDelete, "/_pit", map[string]any{"id": pit.ID})
			}
			es.EnsureCurrentSearchBody(body)
			hits := raw.searchIDs(t, ctx, path, body)
			if len(hits) != len(positive) {
				t.Fatalf("%s hits=%v expected=%v", class, hits, positive)
			}
			for id := range hits {
				if _, ok := positive[id]; !ok {
					t.Fatalf("%s leaked %s", class, id)
				}
			}
		}
	})
	t.Run("Data Creator binding completeness and vector fence", func(t *testing.T) {
		digest := "sha256:" + strings.Repeat("a", 64)
		a := rtsearch.ReleaseQueryPreparationBinding{Release: rtsearch.ReleaseCandidateBinding{"alpha", "qwq_data", "current-a", digest}, Slice: "creator_search", ProviderBindingGeneration: digest, SchemaGeneration: client.SchemaGeneration()}
		b := a
		b.Release.ReleaseID = "current-b"
		for _, binding := range []rtsearch.ReleaseQueryPreparationBinding{a, b} {
			creator := rtsearch.CreatorSearchCandidateSnapshot{Release: binding.Release, SourceClosureDigest: digest, Profiles: []rtsearch.CreatorSearchPublicSnapshot{{ObjectType: "user.profile", ObjectID: "data-creator", PersonaID: "data-creator", CreatorID: "creator", AuthorID: "author", UserHandle: "handle", DisplayName: binding.Release.ReleaseID, IdentityTags: []string{}, SourceVersion: 9, ProfileDigest: digest, UpdatedAt: "2026-09-13T00:00:00Z"}}}
			if e := creator.Seal(); e != nil {
				t.Fatal(e)
			}
			snapshot := rtsearch.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &creator}
			if _, e := client.WriteReleaseCandidate(ctx, binding, snapshot); e != nil {
				t.Fatal(e)
			}
			id := es.ReleaseDocumentID(binding, snapshot.Identities()[0])
			src := raw.getSource(t, ctx, "/"+writeIndex+"/_doc/"+id)
			src["embedding"] = []float64{1, 0}
			if _, e := client.UpsertVersioned(ctx, writeIndex, id, 10, src); e != nil {
				t.Fatal(e)
			}
			for _, field := range []string{"releaseSliceBinding", "releaseSourceIdentity", "releaseBindingId"} {
				for _, mode := range []string{"missing", "null"} {
					corrupt := map[string]any{}
					for k, v := range src {
						corrupt[k] = v
					}
					if mode == "missing" {
						delete(corrupt, field)
					} else {
						corrupt[field] = nil
					}
					raw.put(t, ctx, "/"+writeIndex+"/_doc/data-broken-"+binding.Release.ReleaseID+field+mode, corrupt)
				}
			}
		}
		if e := client.Refresh(ctx); e != nil {
			t.Fatal(e)
		}
		for _, binding := range []*rtsearch.ReleaseQueryPreparationBinding{nil, &a, &b} {
			for _, vector := range []bool{false, true} {
				body := map[string]any{"size": 100, "query": map[string]any{"term": map[string]any{"objectId": "data-creator"}}}
				if vector {
					body["query"] = map[string]any{"match_none": map[string]any{}}
					body["knn"] = map[string]any{"field": "embedding", "query_vector": []float64{1, 0}, "k": 100, "num_candidates": 100, "filter": map[string]any{"term": map[string]any{"objectId": "data-creator"}}}
				}
				rows, e := client.Search(es.WithReleaseBinding(ctx, binding), client.IndexName(), body)
				if e != nil {
					t.Fatal(e)
				}
				want := 0
				if binding != nil {
					want = 1
				}
				if len(rows) != want {
					t.Fatalf("binding=%v vector=%v leaked/missing rows=%v", binding, vector, rows)
				}
				if want == 1 && rows[0].Document.Title != binding.Release.ReleaseID {
					t.Fatalf("wrong fence: %v", rows)
				}
			}
		}
	})
}

type legacyElasticsearchHTTP struct {
	endpoint string
	client   *http.Client
}

func (h legacyElasticsearchHTTP) do(t *testing.T, ctx context.Context, method, path string, body any) (int, []byte) {
	t.Helper()
	var payload io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("encode %s %s: %v", method, path, err)
		}
		payload = bytes.NewReader(encoded)
	}
	request, err := http.NewRequestWithContext(ctx, method, h.endpoint+path, payload)
	if err != nil {
		t.Fatalf("build %s %s: %v", method, path, err)
	}
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	response, err := h.client.Do(request)
	if err != nil {
		t.Fatalf("%s %s: %v", method, path, err)
	}
	defer response.Body.Close()
	data, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatalf("read %s %s: %v", method, path, err)
	}
	return response.StatusCode, data
}

func (h legacyElasticsearchHTTP) put(t *testing.T, ctx context.Context, path string, body any) {
	t.Helper()
	status, data := h.do(t, ctx, http.MethodPut, path+"?refresh=true", body)
	if status < 200 || status >= 300 {
		t.Fatalf("PUT %s status %d: %s", path, status, string(data))
	}
}

func (h legacyElasticsearchHTTP) getSource(t *testing.T, ctx context.Context, path string) map[string]any {
	t.Helper()
	status, data := h.do(t, ctx, http.MethodGet, path, nil)
	if status != http.StatusOK {
		t.Fatalf("GET %s status %d: %s", path, status, string(data))
	}
	var envelope struct {
		Source map[string]any `json:"_source"`
	}
	if err := json.Unmarshal(data, &envelope); err != nil {
		t.Fatalf("decode GET %s: %v", path, err)
	}
	return envelope.Source
}

func (h legacyElasticsearchHTTP) searchIDs(t *testing.T, ctx context.Context, path string, body map[string]any) map[string]struct{} {
	t.Helper()
	status, data := h.do(t, ctx, http.MethodPost, path, body)
	if status != http.StatusOK {
		t.Fatalf("POST %s status %d: %s", path, status, string(data))
	}
	var envelope struct {
		Hits struct {
			Total struct {
				Value int `json:"value"`
			} `json:"total"`
			Hits []struct {
				ID string `json:"_id"`
			} `json:"hits"`
		} `json:"hits"`
		Aggregations struct {
			Objects struct {
				Buckets []struct {
					Key   string `json:"key"`
					Count int    `json:"doc_count"`
				} `json:"buckets"`
			} `json:"objects"`
		} `json:"aggregations"`
	}
	if err := json.Unmarshal(data, &envelope); err != nil {
		t.Fatalf("decode search %s: %v", path, err)
	}
	if body["track_total_hits"] == true && envelope.Hits.Total.Value != len(envelope.Hits.Hits) {
		t.Fatalf("count leaks hidden documents: %s", data)
	}
	if _, ok := body["aggs"]; ok {
		if len(envelope.Aggregations.Objects.Buckets) != len(envelope.Hits.Hits) {
			t.Fatalf("facet leaks hidden documents: %s", data)
		}
		for _, bucket := range envelope.Aggregations.Objects.Buckets {
			if bucket.Count != 1 {
				t.Fatalf("facet count invalid: %s", data)
			}
		}
	}
	out := map[string]struct{}{}
	for _, hit := range envelope.Hits.Hits {
		out[hit.ID] = struct{}{}
	}
	if len(out) == 0 {
		t.Logf("search %s returned no hits: %s", path, string(data))
	}
	return out
}
