package profile_interaction_activity_view_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	activityhttp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/adapters/inbound/http"
	activityapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	activitymodel "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/model"
	activitypersistence "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/infrastructure/persistence"
)

func TestListReceivedReadsObjectOwnedMongoProjectionThroughHTTP(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "profile_interaction_activity_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := activitypersistence.NewMongoActivityStore(runtime.Database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure ProfileInteractionActivityView indexes: %v", err)
	}
	activity := activitymodel.Activity{
		OwnerPersonaID:    "profile-owner",
		ActivityID:        "activity-like",
		ActivityType:      activitymodel.TypeLike,
		Direction:         activitymodel.DirectionReceived,
		SourceType:        "ContentReactionChanged",
		SourceEventID:     "reaction-event",
		SourceVersion:     1,
		Active:            true,
		ActorPersonaID:    "profile-actor",
		TargetPersonaID:   "profile-owner",
		TargetContentID:   "post-profile",
		TargetContentType: "post",
		OccurredAt:        time.Date(2026, 8, 2, 8, 30, 0, 0, time.UTC),
	}
	if err := store.Upsert(context.Background(), activity); err != nil {
		t.Fatalf("project activity: %v", err)
	}
	handler := activityhttp.NewHandler(activityapp.NewActivityQueryService(store))
	request := httptest.NewRequest(
		http.MethodGet,
		"/content/personas/profile-owner/interactions/received?type=like&limit=20",
		nil,
	)
	request.SetPathValue("personaId", "profile-owner")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "profile-owner"},
	}))
	recorder := httptest.NewRecorder()

	handler.ListReceived(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("ListReceived status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	if body := recorder.Body.String(); !containsAll(body, "activity-like", "profile-actor", "post-profile") {
		t.Fatalf("ProfileInteractionActivityView response missing projection fields: %s", body)
	}
}

func containsAll(value string, needles ...string) bool {
	for _, needle := range needles {
		if !strings.Contains(value, needle) {
			return false
		}
	}
	return true
}
