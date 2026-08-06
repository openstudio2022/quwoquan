// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-review-read-and-score-summary/spec.md#gwt-001
// readiness_case: create-homepage-review-api
// readiness_case: update-homepage-review-api
// readiness_case: delete-homepage-review-api
// readiness_case: list-homepage-reviews-api
// readiness_case: get-my-homepage-review-api
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/operation"
	reviewhttp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/adapters/inbound/http"
	reviewapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/application"
	reviewpersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/infrastructure/persistence"
)

type publishedHomepageGate struct{}

func (publishedHomepageGate) FindHomepageStatus(
	context.Context,
	string,
) (string, bool, error) {
	return "published", true, nil
}

func TestHomepageReviewHTTPCommitsStateReceiptAndOutbox(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	mongoRuntime, err := testinfra.StartRealMongo(
		ctx,
		fmt.Sprintf("homepage_review_http_%d", time.Now().UnixNano()),
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
	store := reviewpersistence.NewMongoReviewStore(mongoRuntime.Database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure HomepageReview indexes: %v", err)
	}
	facade, err := reviewapp.NewFacade(reviewapp.DataPorts{
		Aggregate: store, Page: store, Homepage: publishedHomepageGate{},
	})
	if err != nil {
		t.Fatalf("new HomepageReview facade: %v", err)
	}
	handler := reviewhttp.NewHandler(facade)
	request := httptest.NewRequest(
		http.MethodPost,
		"/homepages/homepage-review-1/reviews",
		strings.NewReader(`{"rating":5,"body":"真实游览体验"}`),
	)
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID: "CreateHomepageReview", RequestID: "review-request-1",
		TraceID: "review-trace-1", IdempotencyKey: "review-idempotency-1",
		Actor: operation.ActorContext{PersonaID: "persona-review-author"},
	}))
	recorder := httptest.NewRecorder()
	handler.Create(recorder, request, "homepage-review-1")
	if recorder.Code != http.StatusCreated {
		t.Fatalf("create review status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var created struct {
		ReviewID string `json:"id"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &created); err != nil || created.ReviewID == "" {
		t.Fatalf("decode created review: %+v err=%v", created, err)
	}

	updateRequest := httptest.NewRequest(
		http.MethodPatch,
		"/homepage-reviews/"+created.ReviewID,
		strings.NewReader(`{"rating":4,"body":"真实游览体验更新"}`),
	)
	updateRequest = updateRequest.WithContext(operation.WithContext(
		updateRequest.Context(), operation.Context{
			OperationID: "UpdateHomepageReview", RequestID: "review-request-2",
			TraceID: "review-trace-2", IdempotencyKey: "review-idempotency-2",
			Actor: operation.ActorContext{PersonaID: "persona-review-author"},
		},
	))
	updateRecorder := httptest.NewRecorder()
	handler.Update(updateRecorder, updateRequest, created.ReviewID)
	if updateRecorder.Code != http.StatusOK {
		t.Fatalf("update review status=%d body=%s", updateRecorder.Code, updateRecorder.Body.String())
	}

	listRequest := httptest.NewRequest(
		http.MethodGet,
		"/homepages/homepage-review-1/reviews?limit=20",
		nil,
	)
	listRecorder := httptest.NewRecorder()
	handler.List(listRecorder, listRequest, "homepage-review-1")
	if listRecorder.Code != http.StatusOK ||
		!strings.Contains(listRecorder.Body.String(), created.ReviewID) {
		t.Fatalf("list reviews status=%d body=%s", listRecorder.Code, listRecorder.Body.String())
	}

	mineRequest := httptest.NewRequest(
		http.MethodGet,
		"/homepages/homepage-review-1/reviews/mine",
		nil,
	)
	mineRequest = mineRequest.WithContext(operation.WithContext(
		mineRequest.Context(), operation.Context{
			OperationID: "GetMyHomepageReview", RequestID: "review-request-3",
			TraceID: "review-trace-3",
			Actor:   operation.ActorContext{PersonaID: "persona-review-author"},
		},
	))
	mineRecorder := httptest.NewRecorder()
	handler.GetMine(mineRecorder, mineRequest, "homepage-review-1")
	if mineRecorder.Code != http.StatusOK ||
		!strings.Contains(mineRecorder.Body.String(), created.ReviewID) {
		t.Fatalf("get mine status=%d body=%s", mineRecorder.Code, mineRecorder.Body.String())
	}

	deleteRequest := httptest.NewRequest(
		http.MethodDelete,
		"/homepage-reviews/"+created.ReviewID,
		nil,
	)
	deleteRequest = deleteRequest.WithContext(operation.WithContext(
		deleteRequest.Context(), operation.Context{
			OperationID: "DeleteHomepageReview", RequestID: "review-request-4",
			TraceID: "review-trace-4", IdempotencyKey: "review-idempotency-4",
			Actor: operation.ActorContext{PersonaID: "persona-review-author"},
		},
	))
	deleteRecorder := httptest.NewRecorder()
	handler.Delete(deleteRecorder, deleteRequest, created.ReviewID)
	if deleteRecorder.Code != http.StatusOK {
		t.Fatalf("delete review status=%d body=%s", deleteRecorder.Code, deleteRecorder.Body.String())
	}
	events, err := store.ReadAfter(ctx, "", 10)
	if err != nil {
		t.Fatalf("read review outbox: %v", err)
	}
	if len(events) != 3 || events[0].EventType != reviewapp.EventReviewPublished ||
		events[1].EventType != reviewapp.EventReviewUpdated ||
		events[2].EventType != reviewapp.EventReviewRemoved {
		t.Fatalf("review lifecycle did not commit three typed outbox events: %+v", events)
	}
}
