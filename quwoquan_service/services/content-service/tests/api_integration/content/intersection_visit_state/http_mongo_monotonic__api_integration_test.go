// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
// readiness_case: mark-intersections-visited-api
package intersection_visit_state_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	intersectionhttp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/adapters/inbound/http"
	intersectioncommands "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application"
	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	intersectionpersistence "quwoquan_service/services/content-service/internal/content/intersection_visit_state/infrastructure/persistence"
)

func TestMarkVisitedHTTPAdvancesObjectOwnedMongoWatermarksMonotonically(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "intersection_visit_state_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	store := intersectionpersistence.NewMongoWatermarkStore(runtime.Database, nil)
	service := intersectionapp.NewIntersectionService(
		nil,
		intersectionapp.WithIntersectionWatermarkStore(store),
	)
	handler := intersectionhttp.NewHandler(
		intersectioncommands.NewCommands(service),
		service,
	)

	perform := func(body string) int {
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/intersections/visit",
			strings.NewReader(body),
		)
		request.Header.Set("Content-Type", "application/json")
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Actor: operation.ActorContext{
				AccountID: "account-intersection",
				PersonaID: "persona-intersection",
			},
		}))
		recorder := httptest.NewRecorder()
		handler.MarkVisited(recorder, request)
		return recorder.Code
	}
	if status := perform(`{"dimension":"relationship"}`); status != http.StatusOK {
		t.Fatalf("mark relationship status=%d", status)
	}
	first, err := store.LoadWatermarks(context.Background(), "persona-intersection")
	if err != nil || first["relationship"] <= 0 {
		t.Fatalf("first watermark=%v err=%v", first, err)
	}
	if err := store.SaveWatermarks(context.Background(), "persona-intersection", map[string]int64{
		"relationship": first["relationship"] - 1,
	}); err != nil {
		t.Fatalf("write late watermark: %v", err)
	}
	afterLate, err := store.LoadWatermarks(context.Background(), "persona-intersection")
	if err != nil || afterLate["relationship"] != first["relationship"] {
		t.Fatalf("late watermark regressed state first=%v after=%v err=%v", first, afterLate, err)
	}
	if status := perform(`{"dimension":"unknown"}`); status != http.StatusBadRequest {
		t.Fatalf("invalid dimension status=%d", status)
	}
}
