// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-009
// readiness_case: project-profile-interaction-activity-api
// readiness_case: list-profile-interaction-activities-received-api
// readiness_case: list-profile-interaction-activities-sent-api
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
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	activityhttp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/adapters/inbound/http"
	activityapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	activityports "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/ports"
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
	now := time.Date(2026, 8, 2, 8, 30, 0, 0, time.UTC)
	projector := activityapp.NewReactionProjector(activityapp.NewProfileInteractionActivityViewProjector(
		fixedProjectionSource{post: activityports.PostSlice{
			ID: "post-profile", Version: 1, AuthorPersonaID: "profile-owner",
			ContentType: "image", Title: "profile projection", Status: "published", Visibility: "public",
		}},
		store,
	))
	if err := projector.Publish(context.Background(), reactionports.OutboxFact{
		EventID: "reaction-event", EventType: "ContentReactionSet",
		AggregateID: "activity-like", AggregateVersion: 1,
		Payload:    []byte(`{"reactionId":"activity-like","version":1,"targetKind":"post","targetId":"post-profile","targetAuthorId":"profile-owner","actorDimension":"persona","actorId":"profile-actor","reaction":"like","occurredAt":"2026-08-02T08:30:00Z","idempotencyKey":"profile-like"}`),
		OccurredAt: now,
	}); err != nil {
		t.Fatalf("project durable ContentReaction event: %v", err)
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

	sentRequest := httptest.NewRequest(
		http.MethodGet,
		"/content/personas/profile-actor/interactions/sent?type=like&limit=20",
		nil,
	)
	sentRequest.SetPathValue("personaId", "profile-actor")
	sentRequest = sentRequest.WithContext(rtauth.WithPrincipal(sentRequest.Context(), rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "profile-actor"},
	}))
	sentRecorder := httptest.NewRecorder()
	handler.ListSent(sentRecorder, sentRequest)
	if sentRecorder.Code != http.StatusOK {
		t.Fatalf("ListSent status=%d body=%s", sentRecorder.Code, sentRecorder.Body.String())
	}
	if body := sentRecorder.Body.String(); !containsAll(body, "activity-like", "profile-owner", "post-profile", `"direction":"sent"`) {
		t.Fatalf("sent ProfileInteractionActivityView response missing projection fields: %s", body)
	}
}

type fixedProjectionSource struct {
	post activityports.PostSlice
}

func (source fixedProjectionSource) FindPost(
	_ context.Context,
	postID string,
) (activityports.PostSlice, bool, error) {
	if source.post.ID != postID {
		return activityports.PostSlice{}, false, nil
	}
	return source.post, true, nil
}

func (fixedProjectionSource) FindComment(
	context.Context,
	string,
) (activityports.CommentSlice, bool, error) {
	return activityports.CommentSlice{}, false, nil
}

func containsAll(value string, needles ...string) bool {
	for _, needle := range needles {
		if !strings.Contains(value, needle) {
			return false
		}
	}
	return true
}
