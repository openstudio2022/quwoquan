package profile_interaction_read_fact_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/runtime/commandmeta"
	activitymodel "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/model"
	activitypersistence "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/infrastructure/persistence"
	readfacthttp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/adapters/inbound/http"
	readfactapp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/application"
	readfactpersistence "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/infrastructure/persistence"
)

func TestAppendReadFactHTTPCommitsFactAndOutboxInRealMongoTransaction(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "profile_interaction_read_fact_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	activityStore := activitypersistence.NewMongoActivityStore(runtime.Database)
	if err := activityStore.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure activity indexes: %v", err)
	}
	if err := activityStore.Upsert(context.Background(), activitymodel.Activity{
		OwnerPersonaID:    "profile-owner",
		ActivityID:        "activity-read",
		ActivityType:      activitymodel.TypeComment,
		Direction:         activitymodel.DirectionReceived,
		SourceType:        "CommentCreated",
		SourceEventID:     "comment-event",
		SourceVersion:     1,
		Active:            true,
		ActorPersonaID:    "comment-author",
		TargetPersonaID:   "profile-owner",
		TargetContentID:   "post-profile",
		TargetContentType: "post",
		OccurredAt:        time.Date(2026, 8, 2, 8, 45, 0, 0, time.UTC),
	}); err != nil {
		t.Fatalf("project activity: %v", err)
	}
	store := readfactpersistence.NewMongoReadFactStore(runtime.Database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure ProfileInteractionReadFact indexes: %v", err)
	}
	handler := readfacthttp.NewHandler(readfactapp.NewReadFactService(activityStore, store))

	request := httptest.NewRequest(
		http.MethodPost,
		"/content/personas/profile-owner/interactions/activity-read/read-facts",
		strings.NewReader(`{"state":"read"}`),
	)
	request.SetPathValue("personaId", "profile-owner")
	request.SetPathValue("interactionId", "activity-read")
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{Subject: "account-owner", Persona: "profile-owner"},
		Actor:  operation.ActorContext{AccountID: "account-owner", PersonaID: "profile-owner"},
	}))
	request = request.WithContext(commandmeta.WithIdempotencyKey(request.Context(), "read-fact-once"))
	recorder := httptest.NewRecorder()

	handler.Append(recorder, request)
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("Append read fact status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	for _, collection := range []string{
		"profile_interaction_read_facts",
		"profile_interaction_read_fact_outbox",
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(context.Background(), bson.M{})
		if countErr != nil || count != 1 {
			t.Fatalf("%s count=%d err=%v", collection, count, countErr)
		}
	}
}
