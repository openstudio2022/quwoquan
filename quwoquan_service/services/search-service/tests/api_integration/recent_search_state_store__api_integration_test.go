package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/search-service/internal/adapters/http"
	"quwoquan_service/services/search-service/internal/application/recentsearch"
	"quwoquan_service/services/search-service/internal/domain/recentsearch/model"
	"quwoquan_service/services/search-service/internal/infrastructure/recentsearchstore"
)

func newRecentHandler(t *testing.T) http.Handler {
	t.Helper()
	store := recentsearchstore.NewStore(mongoDB)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure recent indexes: %v", err)
	}
	facade, err := recentsearch.NewFacade(store)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	mux := http.NewServeMux()
	httpadapter.NewRecentSearchHandler(facade).Register(mux)
	return mux
}

func recentRequest(t *testing.T, handler http.Handler, method, target, persona, idemKey string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var reader *strings.Reader
	if body != nil {
		payload, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal recent body: %v", err)
		}
		reader = strings.NewReader(string(payload))
	} else {
		reader = strings.NewReader("")
	}
	request := httptest.NewRequest(method, target, reader)
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if persona != "" {
		request.Header.Set("X-Client-Sub-Account-Id", persona)
	}
	if idemKey != "" {
		request.Header.Set("Idempotency-Key", idemKey)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func TestRecentSearchUpsertDedupesAndBounds(t *testing.T) {
	cleanSearchCollections(t)
	handler := newRecentHandler(t)

	first := recentRequest(t, handler, http.MethodPost, "/search/recent",
		"persona-recent-1", "up-1", map[string]any{"query": " Chengdu Travel ", "scope": "all"})
	if first.Code != http.StatusOK {
		t.Fatalf("first upsert status=%d body=%s", first.Code, first.Body.String())
	}
	var entry struct {
		EntryID string `json:"entryId"`
	}
	if err := json.Unmarshal(first.Body.Bytes(), &entry); err != nil || entry.EntryID == "" {
		t.Fatalf("first upsert must return server-derived entryId: body=%s err=%v", first.Body.String(), err)
	}
	if want := model.DeriveEntryID("all", "", "Chengdu Travel"); entry.EntryID != want {
		t.Fatalf("entryId must derive from semantic key: got=%s want=%s", entry.EntryID, want)
	}

	// 同语义键（大小写归一）第二次 upsert：目标状态已满足（同条目已在顶部），
	// 按 no-op receipt 处理——不递增 aggregate version、不产生第二条 entry。
	second := recentRequest(t, handler, http.MethodPost, "/search/recent",
		"persona-recent-1", "up-2", map[string]any{"query": "chengdu travel", "scope": "all"})
	if second.Code != http.StatusOK {
		t.Fatalf("second upsert status=%d body=%s", second.Code, second.Body.String())
	}
	count, err := mongoDB.Collection("recent_search_states").CountDocuments(
		context.Background(), bson.M{"personaId": "persona-recent-1"})
	if err != nil || count != 1 {
		t.Fatalf("state docs=%d err=%v", count, err)
	}
	var stateDoc struct {
		Entries []bson.M `bson:"entries"`
		Version int64    `bson:"version"`
	}
	if err := mongoDB.Collection("recent_search_states").FindOne(
		context.Background(), bson.M{"personaId": "persona-recent-1"}).Decode(&stateDoc); err != nil {
		t.Fatalf("load state: %v", err)
	}
	if len(stateDoc.Entries) != 1 || stateDoc.Version != 1 {
		t.Fatalf("top-entry noop must not advance version: entries=%d version=%d",
			len(stateDoc.Entries), stateDoc.Version)
	}

	// 超上限淘汰。
	for i := 0; i < model.MaxEntries+2; i++ {
		r := recentRequest(t, handler, http.MethodPost, "/search/recent",
			"persona-recent-1", "bound-"+strings.Repeat("k", i+1),
			map[string]any{"query": "q-" + strings.Repeat("x", i+1), "scope": "all"})
		if r.Code != http.StatusOK {
			t.Fatalf("bound upsert %d status=%d", i, r.Code)
		}
	}
	list := recentRequest(t, handler, http.MethodGet, "/search/recent", "persona-recent-1", "", nil)
	var listBody struct {
		Items []bson.M `json:"items"`
	}
	if err := json.Unmarshal(list.Body.Bytes(), &listBody); err != nil {
		t.Fatalf("decode list: %v", err)
	}
	if len(listBody.Items) != model.MaxEntries {
		t.Fatalf("entries must stay bounded: %d", len(listBody.Items))
	}
}

func TestRecentSearchIdempotencyReceiptReplay(t *testing.T) {
	cleanSearchCollections(t)
	handler := newRecentHandler(t)

	body := map[string]any{"query": "replay me", "scope": "all"}
	first := recentRequest(t, handler, http.MethodPost, "/search/recent", "persona-recent-2", "same-key", body)
	if first.Code != http.StatusOK {
		t.Fatalf("first status=%d", first.Code)
	}
	replay := recentRequest(t, handler, http.MethodPost, "/search/recent", "persona-recent-2", "same-key", body)
	if replay.Code != http.StatusOK {
		t.Fatalf("replay status=%d body=%s", replay.Code, replay.Body.String())
	}
	if first.Body.String() != replay.Body.String() {
		t.Fatalf("same Idempotency-Key must replay identical result: first=%s replay=%s",
			first.Body.String(), replay.Body.String())
	}
	receipts, err := mongoDB.Collection("recent_search_receipts").CountDocuments(context.Background(), bson.M{})
	if err != nil || receipts != 1 {
		t.Fatalf("receipts=%d err=%v", receipts, err)
	}
	ownedReceipts, err := mongoDB.Collection(
		"recent_search_receipts",
	).CountDocuments(
		context.Background(),
		bson.M{"personaId": "persona-recent-2"},
	)
	if err != nil || ownedReceipts != 1 {
		t.Fatalf(
			"lifecycle-owned receipts=%d err=%v",
			ownedReceipts,
			err,
		)
	}

	// 同 key 不同 payload → 幂等冲突 409。
	conflict := recentRequest(t, handler, http.MethodPost, "/search/recent", "persona-recent-2", "same-key",
		map[string]any{"query": "different", "scope": "all"})
	if conflict.Code != http.StatusConflict {
		t.Fatalf("digest conflict status=%d body=%s", conflict.Code, conflict.Body.String())
	}
	var failure struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(conflict.Body.Bytes(), &failure); err != nil ||
		failure.Code != "SEARCH.USER.recent_idempotency_conflict" {
		t.Fatalf("conflict must carry stable code: body=%s err=%v", conflict.Body.String(), err)
	}
}

func TestRecentSearchDeleteAndClear(t *testing.T) {
	cleanSearchCollections(t)
	handler := newRecentHandler(t)

	created := recentRequest(t, handler, http.MethodPost, "/search/recent",
		"persona-recent-3", "create", map[string]any{"query": "to delete", "scope": "all"})
	var entry struct {
		EntryID string `json:"entryId"`
	}
	if err := json.Unmarshal(created.Body.Bytes(), &entry); err != nil {
		t.Fatalf("decode created: %v", err)
	}

	// 删除不存在的 entry：no-op 重放安全（200，不递增版本）。
	missing := recentRequest(t, handler, http.MethodDelete,
		"/search/recent/recent_ffffffffffffffff", "persona-recent-3", "del-missing", nil)
	if missing.Code != http.StatusOK {
		t.Fatalf("missing delete status=%d body=%s", missing.Code, missing.Body.String())
	}

	real := recentRequest(t, handler, http.MethodDelete,
		"/search/recent/"+entry.EntryID, "persona-recent-3", "del-real", nil)
	if real.Code != http.StatusOK {
		t.Fatalf("real delete status=%d", real.Code)
	}
	list := recentRequest(t, handler, http.MethodGet, "/search/recent", "persona-recent-3", "", nil)
	var listBody struct {
		Items []bson.M `json:"items"`
	}
	_ = json.Unmarshal(list.Body.Bytes(), &listBody)
	if len(listBody.Items) != 0 {
		t.Fatalf("entries must be empty after delete: %d", len(listBody.Items))
	}

	// clear 已空状态：no-op 安全；重复 clear 重放。
	clear1 := recentRequest(t, handler, http.MethodDelete, "/search/recent", "persona-recent-3", "clear-1", nil)
	clear2 := recentRequest(t, handler, http.MethodDelete, "/search/recent", "persona-recent-3", "clear-1", nil)
	if clear1.Code != http.StatusOK || clear2.Code != http.StatusOK {
		t.Fatalf("clear must be replay safe: first=%d second=%d", clear1.Code, clear2.Code)
	}
}

func TestRecentSearchOwnerIsolation(t *testing.T) {
	cleanSearchCollections(t)
	handler := newRecentHandler(t)

	if r := recentRequest(t, handler, http.MethodPost, "/search/recent",
		"persona-owner-a", "a-1", map[string]any{"query": "mine", "scope": "all"}); r.Code != http.StatusOK {
		t.Fatalf("owner upsert status=%d", r.Code)
	}
	other := recentRequest(t, handler, http.MethodGet, "/search/recent", "persona-owner-b", "", nil)
	var listBody struct {
		Items []bson.M `json:"items"`
	}
	_ = json.Unmarshal(other.Body.Bytes(), &listBody)
	if other.Code != http.StatusOK || len(listBody.Items) != 0 {
		t.Fatalf("foreign persona must not read another state: status=%d items=%d", other.Code, len(listBody.Items))
	}

	anonymous := recentRequest(t, handler, http.MethodGet, "/search/recent", "", "", nil)
	if anonymous.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous must be 401: %d body=%s", anonymous.Code, anonymous.Body.String())
	}
}

func TestRecentSearchConcurrentUpsertSingleWinnerPerSemanticKey(t *testing.T) {
	cleanSearchCollections(t)
	handler := newRecentHandler(t)

	const workers = 8
	var group sync.WaitGroup
	codes := make(chan int, workers)
	for i := 0; i < workers; i++ {
		group.Add(1)
		go func(worker int) {
			defer group.Done()
			r := recentRequest(t, handler, http.MethodPost, "/search/recent",
				"persona-concurrent", "concurrent-"+strings.Repeat("w", worker+1),
				map[string]any{"query": "same query", "scope": "all"})
			codes <- r.Code
		}(i)
	}
	group.Wait()
	close(codes)
	for code := range codes {
		if code != http.StatusOK {
			t.Fatalf("concurrent upsert must converge via CAS retry: status=%d", code)
		}
	}
	var stateDoc struct {
		Entries []bson.M `bson:"entries"`
	}
	if err := mongoDB.Collection("recent_search_states").FindOne(
		context.Background(), bson.M{"personaId": "persona-concurrent"}).Decode(&stateDoc); err != nil {
		t.Fatalf("load state: %v", err)
	}
	if len(stateDoc.Entries) != 1 {
		t.Fatalf("concurrent same-semantic-key upserts must keep one entry: %d", len(stateDoc.Entries))
	}
}
