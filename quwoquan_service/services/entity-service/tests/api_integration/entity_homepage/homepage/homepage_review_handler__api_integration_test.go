package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/testsupport"
	reviewapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/application"
	reviewmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/model"
	reviewports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/ports"
)

// memoryReviewStore 是 transport 层集成测试的内存 AggregateStore；
// CAS/receipt 语义与 Mongo store 同构（真实 Mongo CAS 由 store 层合同保证）。
type memoryReviewStore struct {
	mu       sync.Mutex
	reviews  map[string]reviewmodel.Snapshot
	receipts map[string]memoryReviewReceipt
	outbox   []reviewports.OutboxEvent
}

type memoryReviewReceipt struct {
	commandName   string
	commandDigest string
	snapshot      reviewmodel.Snapshot
}

func newMemoryReviewStore() *memoryReviewStore {
	return &memoryReviewStore{
		reviews:  map[string]reviewmodel.Snapshot{},
		receipts: map[string]memoryReviewReceipt{},
	}
}

var _ reviewports.AggregateStore = (*memoryReviewStore)(nil)
var _ reviewports.PageReader = (*memoryReviewStore)(nil)

func (s *memoryReviewStore) Load(
	_ context.Context,
	reviewID string,
) (*reviewmodel.HomepageReview, bool, error) {
	s.mu.Lock()
	snapshot, found := s.reviews[strings.TrimSpace(reviewID)]
	s.mu.Unlock()
	if !found {
		return nil, false, nil
	}
	aggregate, err := reviewmodel.Restore(snapshot)
	return aggregate, err == nil, err
}

func (s *memoryReviewStore) FindByAuthor(
	_ context.Context,
	homepageID string,
	authorPersonaID string,
) (*reviewmodel.HomepageReview, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, snapshot := range s.reviews {
		if snapshot.HomepageID == strings.TrimSpace(homepageID) &&
			snapshot.AuthorPersonaID == strings.TrimSpace(authorPersonaID) {
			aggregate, err := reviewmodel.Restore(snapshot)
			return aggregate, err == nil, err
		}
	}
	return nil, false, nil
}

func (s *memoryReviewStore) FindReceipt(
	_ context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (reviewports.CommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found := s.receipts[idempotencyKey]
	if !found {
		return reviewports.CommitResult{}, false, nil
	}
	if receipt.commandName != commandName || receipt.commandDigest != commandDigest {
		return reviewports.CommitResult{}, false,
			generated.AppErrorFromIdempotencyConflict("digest mismatch")
	}
	aggregate, err := reviewmodel.Restore(receipt.snapshot)
	if err != nil {
		return reviewports.CommitResult{}, false, err
	}
	return reviewports.CommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *memoryReviewStore) RecordNoopReceipt(
	_ context.Context,
	noop reviewports.NoopReceipt,
) (reviewports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	snapshot := noop.Aggregate.Snapshot()
	s.receipts[noop.IdempotencyKey] = memoryReviewReceipt{
		commandName:   noop.CommandName,
		commandDigest: noop.CommandDigest,
		snapshot:      snapshot,
	}
	aggregate, err := reviewmodel.Restore(snapshot)
	return reviewports.CommitResult{Aggregate: aggregate}, err
}

func (s *memoryReviewStore) Commit(
	_ context.Context,
	commit reviewports.Commit,
) (reviewports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	snapshot := commit.Aggregate.Snapshot()
	current, exists := s.reviews[snapshot.ID]
	if commit.ExpectedVersion == 0 {
		if exists {
			return reviewports.CommitResult{},
				generated.AppErrorFromVersionConflict("review already exists")
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return reviewports.CommitResult{},
			generated.AppErrorFromVersionConflict("review version changed")
	}
	s.reviews[snapshot.ID] = snapshot
	s.receipts[commit.IdempotencyKey] = memoryReviewReceipt{
		commandName:   commit.CommandName,
		commandDigest: commit.CommandDigest,
		snapshot:      snapshot,
	}
	s.outbox = append(s.outbox, commit.Events...)
	aggregate, err := reviewmodel.Restore(snapshot)
	return reviewports.CommitResult{Aggregate: aggregate}, err
}

func (s *memoryReviewStore) ListByHomepage(
	_ context.Context,
	homepageID string,
	request reviewports.PageRequest,
) (reviewports.Page, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := make([]reviewmodel.Snapshot, 0)
	for _, snapshot := range s.reviews {
		if snapshot.HomepageID == strings.TrimSpace(homepageID) &&
			snapshot.Status == reviewmodel.StatusActive {
			items = append(items, snapshot)
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	limit := request.Limit
	if limit <= 0 {
		limit = 20
	}
	if len(items) > limit {
		items = items[:limit]
	}
	return reviewports.Page{Items: items}, nil
}

func newReviewTestServer(t *testing.T) (*httptest.Server, *memoryReviewStore) {
	t.Helper()
	store := newMemoryReviewStore()
	homepageService := testsupport.NewFixtureHomepageService()
	facade, err := reviewapp.NewFacade(reviewapp.DataPorts{
		Aggregate: store,
		Page:      store,
		Homepage:  homepageService,
	})
	if err != nil {
		t.Fatalf("new review facade: %v", err)
	}
	base := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	step := 0
	facade.SetClock(func() time.Time {
		step++
		return base.Add(time.Duration(step) * time.Second)
	})
	handler := httpadapter.NewHandler(homepageService).WithReviewFacade(facade)
	server := httptest.NewServer(reviewActorMiddleware(handler.Routes()))
	t.Cleanup(server.Close)
	return server, store
}

// reviewActorMiddleware 模拟 generated guard：从测试 header 注入可信 actor
// 与 Idempotency-Key（生产链路由 guard 校验后注入 operation.Context）。
func reviewActorMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		persona := r.Header.Get("X-Test-Persona")
		ctx := operation.WithContext(r.Context(), operation.Context{
			OperationID:    "review-api-test",
			RequestID:      "req-review",
			IdempotencyKey: r.Header.Get("Idempotency-Key"),
			Actor: operation.ActorContext{
				AccountID: persona,
				PersonaID: persona,
			},
		})
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func reviewRequest(
	t *testing.T,
	server *httptest.Server,
	method string,
	path string,
	persona string,
	idempotencyKey string,
	body map[string]any,
	wantStatus int,
) map[string]any {
	t.Helper()
	var reader *bytes.Reader
	if body != nil {
		payload, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		reader = bytes.NewReader(payload)
	} else {
		reader = bytes.NewReader(nil)
	}
	req, err := http.NewRequest(method, server.URL+path, reader)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if persona != "" {
		req.Header.Set("X-Test-Persona", persona)
	}
	if idempotencyKey != "" {
		req.Header.Set("Idempotency-Key", idempotencyKey)
	}
	resp, err := server.Client().Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()
	var decoded map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&decoded); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.StatusCode != wantStatus {
		t.Fatalf(
			"expected status %d for %s %s, got %d: %v",
			wantStatus, method, path, resp.StatusCode, decoded,
		)
	}
	return decoded
}

const reviewFixtureHomepage = "homepage_sight_west_lake"

func TestHomepageReviewHTTPLifecycle(t *testing.T) {
	server, store := newReviewTestServer(t)
	basePath := "/homepages/" + reviewFixtureHomepage + "/reviews"

	created := reviewRequest(t, server, http.MethodPost, basePath,
		"persona-author", "key-create-1",
		map[string]any{
			"rating":  5,
			"body":    "很棒的地方",
			"tagRefs": []string{"publish/tags/scenery"},
		}, http.StatusCreated)
	reviewID := created["id"].(string)
	if created["status"] != "active" || created["version"].(float64) != 1 {
		t.Fatalf("unexpected created review: %v", created)
	}

	// 幂等重放：相同 key 返回首次结果，不产生第二条。
	replayed := reviewRequest(t, server, http.MethodPost, basePath,
		"persona-author", "key-create-1",
		map[string]any{
			"rating":  5,
			"body":    "很棒的地方",
			"tagRefs": []string{"publish/tags/scenery"},
		}, http.StatusCreated)
	if replayed["id"] != reviewID || replayed["version"].(float64) != 1 {
		t.Fatalf("idempotent replay mismatch: %v", replayed)
	}
	if len(store.reviews) != 1 {
		t.Fatalf("expected exactly one review, got %d", len(store.reviews))
	}

	// 列表可见。
	page := reviewRequest(t, server, http.MethodGet, basePath, "", "", nil, http.StatusOK)
	if items := page["items"].([]any); len(items) != 1 {
		t.Fatalf("expected 1 review in list, got %v", page)
	}

	// mine 返回本人评价。
	mine := reviewRequest(t, server, http.MethodGet, basePath+"/mine",
		"persona-author", "", nil, http.StatusOK)
	if mine["id"] != reviewID {
		t.Fatalf("mine mismatch: %v", mine)
	}

	// 作者更新。
	updated := reviewRequest(t, server, http.MethodPatch, "/homepage-reviews/"+reviewID,
		"persona-author", "key-update-1",
		map[string]any{"rating": 4, "body": "还不错"}, http.StatusOK)
	if updated["rating"].(float64) != 4 || updated["version"].(float64) != 2 {
		t.Fatalf("unexpected updated review: %v", updated)
	}

	// BOLA 负例：非作者更新被拒。
	intruder := reviewRequest(t, server, http.MethodPatch, "/homepage-reviews/"+reviewID,
		"persona-intruder", "key-intruder-1",
		map[string]any{"rating": 1}, http.StatusForbidden)
	if intruder["error"] == nil && intruder["code"] == nil {
		t.Fatalf("expected structured error body, got %v", intruder)
	}

	// 作者软删；再次删除（新 key）为 no-op receipt。
	deleted := reviewRequest(t, server, http.MethodDelete, "/homepage-reviews/"+reviewID,
		"persona-author", "key-delete-1", nil, http.StatusOK)
	if deleted["status"] != "deleted" {
		t.Fatalf("unexpected deleted review: %v", deleted)
	}
	noop := reviewRequest(t, server, http.MethodDelete, "/homepage-reviews/"+reviewID,
		"persona-author", "key-delete-2", nil, http.StatusOK)
	if noop["version"] != deleted["version"] {
		t.Fatalf("delete no-op must not advance version: %v vs %v", noop, deleted)
	}

	// 软删后列表为空、mine 仍可取回（供复活预填）。
	emptyPage := reviewRequest(t, server, http.MethodGet, basePath, "", "", nil, http.StatusOK)
	if items := emptyPage["items"].([]any); len(items) != 0 {
		t.Fatalf("deleted review must be hidden from list: %v", emptyPage)
	}
	mineDeleted := reviewRequest(t, server, http.MethodGet, basePath+"/mine",
		"persona-author", "", nil, http.StatusOK)
	if mineDeleted["status"] != "deleted" {
		t.Fatalf("mine must return deleted review: %v", mineDeleted)
	}

	// 复活：再次创建复用同一聚合。
	revived := reviewRequest(t, server, http.MethodPost, basePath,
		"persona-author", "key-create-2",
		map[string]any{"rating": 3, "body": "重新评价"}, http.StatusCreated)
	if revived["id"] != reviewID || revived["status"] != "active" {
		t.Fatalf("revive must reuse aggregate: %v", revived)
	}
	if len(store.reviews) != 1 {
		t.Fatalf("author+homepage must map to one document, got %d", len(store.reviews))
	}
	if len(store.outbox) != 4 {
		t.Fatalf("expected 4 outbox facts, got %d", len(store.outbox))
	}
}

func TestHomepageReviewRequiresActorAndIdempotencyKey(t *testing.T) {
	server, _ := newReviewTestServer(t)
	basePath := "/homepages/" + reviewFixtureHomepage + "/reviews"

	// 无 persona actor：结构化 403。
	reviewRequest(t, server, http.MethodPost, basePath,
		"", "key-anon", map[string]any{"rating": 5}, http.StatusForbidden)

	// 无 Idempotency-Key：结构化 400。
	reviewRequest(t, server, http.MethodPost, basePath,
		"persona-author", "", map[string]any{"rating": 5}, http.StatusBadRequest)

	// 主页不存在：404。
	reviewRequest(t, server, http.MethodPost, "/homepages/hp-missing/reviews",
		"persona-author", "key-missing", map[string]any{"rating": 5}, http.StatusNotFound)
}
