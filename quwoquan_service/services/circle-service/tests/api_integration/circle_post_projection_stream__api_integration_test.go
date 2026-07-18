package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	placementapp "quwoquan_service/services/circle-service/internal/application/circle/circle_post_placement"
	placementpersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_post_placement/persistence"
	"quwoquan_service/services/circle-service/internal/infrastructure/messaging"
)

func TestContentPostStreamToPlacementAndPlacementOutboxConvergeOnRealStores(t *testing.T) {
	cleanCollections(t)
	ctx := context.Background()
	if _, err := mongoDB.Collection("circles").InsertOne(ctx, bson.M{
		"_id": "circle-stream", "ownerId": "persona-moderator", "status": "active", "postCount": int64(0),
	}); err != nil {
		t.Fatal(err)
	}

	projection := placementpersistence.NewMongoPostLifecycleProjection(mongoDB)
	if err := projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	consumer := messaging.NewContentPostConsumer(
		redisRouter.Scene("general"), projection, projection, "circle-api-integration", nil,
	)
	values := map[string]string{
		"eventId": "post-stream:PostPublished:2", "eventType": "PostPublished",
		"aggregateType": "Post", "aggregateId": "post-stream", "aggregateVersion": "2",
		"payload":    "{\"_id\":\"post-stream\",\"authorId\":\"persona-owner\",\"status\":\"published\"}",
		"occurredAt": time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC).Format(time.RFC3339Nano),
	}
	for duplicate := 0; duplicate < 2; duplicate++ {
		if _, err := redisRouter.Scene("general").XAdd(ctx, messaging.ContentPostLifecycleStream, values); err != nil {
			t.Fatal(err)
		}
	}
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 2 {
		t.Fatalf("consume Content Post lifecycle count=%d err=%v", count, err)
	}
	if count, err := mongoDB.Collection("circle_post_owner_views").CountDocuments(ctx, bson.M{
		"_id": "post-stream", "ownerPersonaId": "persona-owner", "state": "published", "postVersion": int64(2),
	}); err != nil || count != 1 {
		t.Fatalf("Post owner view count=%d err=%v", count, err)
	}
	if count, err := mongoDB.Collection("circle_content_post_inbox").CountDocuments(ctx, bson.M{
		"_id": "post-stream:PostPublished:2",
	}); err != nil || count != 1 {
		t.Fatalf("Content Post inbox count=%d err=%v", count, err)
	}

	request := placementRequestForCircle(t, "circle-stream", "post-stream", "placement-stream-key")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-owner", PersonaID: "persona-owner"},
	}))
	recorder := httptest.NewRecorder()
	placementGuard := rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle_post_placement.PlacePostInCircle",
			ContractGraphSHA256:  "circle-placement-stream-api-integration",
			Method:               http.MethodPost, PathTemplate: "/circles/{circleId}/post-placements",
			OperationKind: "command", MutationTarget: "CirclePostPlacement", InvariantTarget: "CirclePostPlacement",
			AuthMode: "required", ActorRequirement: "persona", Principal: "persona",
			CommercialStatus: "ready", TimeoutMilliseconds: 1500,
		}},
		http.MethodPost,
		"/circles/{circleId}/post-placements",
	)(testHandler)
	placementGuard.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("place projected Post failed: status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	store := placementpersistence.NewMongoAggregateStore(mongoDB)
	countProjector := placementpersistence.NewMongoPostCountProjector(mongoDB, redisRouter.Scene("general"))
	countRelay := placementapp.NewOutboxRelay(store, store, countProjector, "circle-count-primary")
	if count, err := countRelay.Drain(ctx, 10); err != nil || count != 1 {
		t.Fatalf("drain placement count projection count=%d err=%v", count, err)
	}
	// A fresh checkpoint deliberately replays the same outbox event. The Mongo
	// inbox must suppress a second increment.
	replayRelay := placementapp.NewOutboxRelay(store, store, countProjector, "circle-count-rebuild-proof")
	if count, err := replayRelay.Drain(ctx, 10); err != nil || count != 1 {
		t.Fatalf("replay placement count projection count=%d err=%v", count, err)
	}
	var circle struct {
		PostCount int64 `bson:"postCount"`
	}
	if err := mongoDB.Collection("circles").FindOne(ctx, bson.M{"_id": "circle-stream"}).Decode(&circle); err != nil {
		t.Fatal(err)
	}
	if circle.PostCount != 1 {
		t.Fatalf("idempotent placement count=%d want=1", circle.PostCount)
	}

	streamRelay := placementapp.NewOutboxRelay(
		store, store,
		messaging.NewCirclePostPlacementStreamPublisher(redisRouter.Scene("general")),
		"circle-placement-api-integration-stream",
	)
	if count, err := streamRelay.Drain(ctx, 10); err != nil || count != 1 {
		t.Fatalf("drain placement stream count=%d err=%v", count, err)
	}
	group := "placement-downstream-" + strconv.FormatInt(time.Now().UnixNano(), 10)
	if err := redisRouter.Scene("general").XGroupCreateMkStream(ctx, messaging.CirclePostPlacementStream, group, "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := redisRouter.Scene("general").XReadGroup(ctx, group, "reader",
		map[string]string{messaging.CirclePostPlacementStream: ">"}, 10, 0)
	if err != nil || len(messages) != 1 {
		t.Fatalf("placement stream messages=%d err=%v", len(messages), err)
	}
	if messages[0].Values["eventType"] != "CirclePostPlaced" ||
		messages[0].Values["aggregateVersion"] != "1" ||
		messages[0].Values["eventId"] == "" {
		t.Fatalf("placement stream identity drift: %#v", messages[0].Values)
	}
}

func placementRequestForCircle(t *testing.T, circleID, postID, idempotencyKey string) *http.Request {
	t.Helper()
	request := placementRequest(t, postID, idempotencyKey)
	request.URL.Path = "/circles/" + circleID + "/post-placements"
	return request
}
