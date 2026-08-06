package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/operation"
	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
	reviewhttp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/adapters/inbound/http"
	reviewapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/application"
	reviewports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/ports"
	reviewpersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/infrastructure/persistence"
)

func newReviewTestServer(
	t *testing.T,
) (*httptest.Server, *reviewpersistence.MongoReviewStore, string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	t.Cleanup(cancel)
	mongoRuntime, err := testinfra.StartRealMongo(
		ctx,
		fmt.Sprintf("entity_homepage_review_handler_%d", time.Now().UnixNano()),
	)
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if closeErr := mongoRuntime.Close(cleanupCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	homepageStore := homepagepersistence.NewMongoHomepageStore(mongoRuntime.Database)
	store := reviewpersistence.NewMongoReviewStore(mongoRuntime.Database)
	if err := homepageStore.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure Homepage indexes: %v", err)
	}
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure HomepageReview indexes: %v", err)
	}
	homepageService := homepageapp.NewHomepageServiceWithStore(ctx, homepageStore)
	seedContext := func(operationID, idempotencyKey string) context.Context {
		return operation.WithContext(ctx, operation.Context{
			OperationID:    operationID,
			RequestID:      "request-" + idempotencyKey,
			IdempotencyKey: idempotencyKey,
			Actor: operation.ActorContext{
				AccountID: "homepage-review-seed-account",
				PersonaID: "homepage-review-seed-persona",
			},
		})
	}
	candidate, err := homepageService.IntakeHomepageCandidate(
		seedContext("entity.homepage.IntakeHomepageCandidate", "homepage-review-intake"),
		homepageapp.HomepageInput{
			Title:        "Homepage review integration target",
			HomepageType: "sight",
			City:         "Hangzhou",
		},
		"owner_created",
	)
	if err != nil {
		t.Fatalf("intake Homepage review target: %v", err)
	}
	published, err := homepageService.PublishHomepageCandidate(
		seedContext("entity.homepage.PublishHomepageCandidate", "homepage-review-publish"),
		candidate.ID,
	)
	if err != nil || published.Status != "published" {
		t.Fatalf("publish Homepage review target: homepage=%+v err=%v", published, err)
	}
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
	handler := httpadapter.NewHandler(homepageService).WithReviewHandler(reviewhttp.NewHandler(facade))
	server := httptest.NewServer(reviewActorMiddleware(handler.Routes()))
	t.Cleanup(server.Close)
	return server, store, candidate.ID
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

func TestHomepageReviewHTTPLifecycle(t *testing.T) {
	server, store, homepageID := newReviewTestServer(t)
	basePath := "/homepages/" + homepageID + "/reviews"

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
	storedPage, err := store.ListByHomepage(
		context.Background(),
		homepageID,
		reviewports.PageRequest{Limit: 10},
	)
	if err != nil || len(storedPage.Items) != 1 {
		t.Fatalf("expected exactly one persisted review, page=%+v err=%v", storedPage, err)
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
	storedPage, err = store.ListByHomepage(
		context.Background(),
		homepageID,
		reviewports.PageRequest{Limit: 10},
	)
	if err != nil || len(storedPage.Items) != 1 {
		t.Fatalf("author+homepage must map to one active document, page=%+v err=%v", storedPage, err)
	}
	outbox, err := store.ReadAfter(context.Background(), "", 10)
	if err != nil || len(outbox) != 4 {
		t.Fatalf("expected 4 persisted outbox facts, outbox=%+v err=%v", outbox, err)
	}
}

func TestHomepageReviewRequiresActorAndIdempotencyKey(t *testing.T) {
	server, _, homepageID := newReviewTestServer(t)
	basePath := "/homepages/" + homepageID + "/reviews"

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
