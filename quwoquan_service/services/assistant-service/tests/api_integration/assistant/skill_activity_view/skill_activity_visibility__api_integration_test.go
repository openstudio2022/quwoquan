// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
// readiness_case: list-skill-activities-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	activityhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/infrastructure/persistence"
)

type apiActivitySource struct{ items []model.Item }

func (source apiActivitySource) ListSkillActivities(
	context.Context,
	string,
	string,
	int,
) ([]model.Item, error) {
	return append([]model.Item(nil), source.items...), nil
}

func TestSkillActivityVisibilityWatermarkIsOwnerScopedAndMonotonic(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(
		startupCtx, "assistant_skill_activity_api_integration",
	)
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := persistence.NewMongoVisibilityStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("EnsureIndexes() error=%v", err)
	}
	first := time.Date(2026, 8, 4, 10, 0, 0, 0, time.UTC)
	if err := store.HideBefore(
		startupCtx, "account-a", "travel_companion", first,
	); err != nil {
		t.Fatalf("HideBefore(first) error=%v", err)
	}
	if err := store.HideBefore(
		startupCtx, "account-a", "travel_companion", first.Add(-time.Hour),
	); err != nil {
		t.Fatalf("HideBefore(older) error=%v", err)
	}
	watermark, err := store.HiddenBefore(
		startupCtx, "account-a", "travel_companion",
	)
	if err != nil || watermark == nil || !watermark.Equal(first) {
		t.Fatalf("HiddenBefore()=%v error=%v", watermark, err)
	}
	foreign, err := store.HiddenBefore(
		startupCtx, "account-b", "travel_companion",
	)
	if err != nil || foreign != nil {
		t.Fatalf("foreign HiddenBefore()=%v error=%v", foreign, err)
	}

	mux := http.NewServeMux()
	activityhttp.NewHandler(application.NewQueryFacade(
		store,
		apiActivitySource{items: []model.Item{
			{
				ActivityID: "run-visible", AccountID: "account-a", SkillID: "travel_companion",
				ActivityKind: model.KindRun, Status: "completed", DisplayKey: model.DisplayRunCompleted,
				SourceObjectRef: "assistant.AssistantRun:run-visible", SourceRevision: 2,
				OccurredAt: first.Add(time.Hour),
			},
			{
				ActivityID: "run-hidden", AccountID: "account-a", SkillID: "travel_companion",
				ActivityKind: model.KindRun, Status: "completed", DisplayKey: model.DisplayRunCompleted,
				SourceObjectRef: "assistant.AssistantRun:run-hidden", SourceRevision: 1,
				OccurredAt: first.Add(-time.Minute),
			},
		}},
	)).RegisterRoutes(mux)
	request := httptest.NewRequest(
		http.MethodGet,
		"/assistant/skills/travel_companion/activities?limit=20",
		nil,
	)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-a"},
	}))
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("activity query status=%d body=%s", response.Code, response.Body.String())
	}
	var slice model.Slice
	if err := json.Unmarshal(response.Body.Bytes(), &slice); err != nil {
		t.Fatalf("decode activity response: %v", err)
	}
	if len(slice.Items) != 1 || slice.Items[0].ActivityID != "run-visible" ||
		slice.Items[0].AccountID != "" {
		t.Fatalf("visibility-filtered activity response=%+v", slice)
	}

	unauthorized := httptest.NewRecorder()
	mux.ServeHTTP(unauthorized, httptest.NewRequest(
		http.MethodGet,
		"/assistant/skills/travel_companion/activities",
		nil,
	))
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("untrusted activity query status=%d body=%s", unauthorized.Code, unauthorized.Body.String())
	}
}
