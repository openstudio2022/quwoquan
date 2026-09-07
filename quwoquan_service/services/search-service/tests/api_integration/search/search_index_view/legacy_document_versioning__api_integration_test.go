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

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/search-service/tests/support"
)

// TestLegacyDocumentVersioning 在真实 Elasticsearch 上固定「存量文档」的行为：
// 版本化写入面落地前写进索引的文档没有 sourceVersion / sourceDigest / deleted。
//
//   - 读面：缺 deleted 的存量文档必须仍然可见（NotDeletedQuery 只排除显式 tombstone），
//     否则切换写入面会让存量语料整体消失；
//   - 写面：UpsertVersioned 撞上存量文档且外部版本不高于 ES 内部 _version 时，
//     必须以 typed 错误 fail-closed（QWQ_VERSIONED_SOURCE_STATE_INVALID），不能被
//     当成「已是更新版本」的幂等 noop 静默吞掉；
//   - 收敛：backfill 以更高的 sourceVersion 重写后，文档携带完整版本化字段，
//     再次以同版本重放为幂等 noop。
//
// 这条测试是 OPEN-004（存量文档 reindex/backfill 证据）的验收锚点；只要仓内还
// 没有存量文档回填回执，它就同时是防止「静默丢文档」与「静默吞写」的回归线。
func TestLegacyDocumentVersioning(t *testing.T) {
	ctx := context.Background()
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	t.Cleanup(stop)

	client, err := es.NewClient(es.Config{
		Endpoints:      []string{endpoint},
		Index:          "quwoquan_objects_legacy",
		RequestTimeout: 30 * time.Second,
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

	t.Run("legacy document without deleted field stays visible under canonical tombstone filter", func(t *testing.T) {
		body := map[string]any{
			"query": map[string]any{"bool": map[string]any{
				"filter": []any{map[string]any{"term": map[string]any{"objectType": "content.post"}}},
			}},
		}
		es.EnsureNotDeletedSearchBody(body)
		hits := raw.searchIDs(t, ctx, "/"+client.IndexName()+"/_search", body)
		if _, ok := hits[legacyID]; !ok {
			t.Fatalf("legacy document must remain visible; hits=%v", hits)
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

	t.Run("backfill with higher sourceVersion converges legacy document and replay is idempotent", func(t *testing.T) {
		applied, err := client.UpsertVersioned(ctx, writeIndex, legacyID, 3, legacyDoc)
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
		replayed, err := client.UpsertVersioned(ctx, writeIndex, legacyID, 3, legacyDoc)
		if err != nil {
			t.Fatalf("same-version replay must be idempotent noop, got %v", err)
		}
		if replayed {
			t.Fatalf("same-version replay must not report applied")
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
			Hits []struct {
				ID string `json:"_id"`
			} `json:"hits"`
		} `json:"hits"`
	}
	if err := json.Unmarshal(data, &envelope); err != nil {
		t.Fatalf("decode search %s: %v", path, err)
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
