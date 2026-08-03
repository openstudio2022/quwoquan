// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-review-read-and-score-summary/spec.md#gwt-001
package api_integration

import (
	"context"
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
	store := reviewpersistence.NewMongoReviewStore(mongoRuntime.Database, true)
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
	events, err := store.ReadAfter(ctx, "", 10)
	if err != nil {
		t.Fatalf("read review outbox: %v", err)
	}
	if len(events) != 1 || events[0].EventType != reviewapp.EventReviewPublished {
		t.Fatalf("review transaction did not commit one typed outbox event: %+v", events)
	}
}
