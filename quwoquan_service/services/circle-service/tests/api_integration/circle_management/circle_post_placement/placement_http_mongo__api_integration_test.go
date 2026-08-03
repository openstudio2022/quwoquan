// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/application"
	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestPlacePostHTTPCommitsAggregateReceiptAndOutbox(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_post_placement_object_api")
	ctx := context.Background()
	if _, err := database.Collection("circles").InsertOne(ctx, bson.M{
		"_id": "circle-placement-object", "ownerId": "persona-placement-owner", "status": "active",
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_post_owner_views").InsertOne(ctx, bson.M{
		"_id": "post-placement-object", "ownerPersonaId": "persona-placement-owner", "state": "published",
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoPolicyReaders(database)
	if err := readers.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	handler := httpadapter.NewHandler(app.NewCommandFacade(store, ports.PolicyReaders{
		Circles: readers, Groups: readers, Posts: readers, Memberships: readers,
	}))
	request := testsupport.Request(t, http.MethodPost, "/circles/circle-placement-object/post-placements", map[string]any{
		"postId": "post-placement-object",
	}, "circle.circle_post_placement.PlacePostInCircle", "persona-placement-owner", "placement-object-1")
	recorder := httptest.NewRecorder()
	handler.ServeCircleRoute(recorder, request, "circle-placement-object", nil)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("place status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	testsupport.AssertCollectionCount(t, database, "circle_post_placements", 1)
	testsupport.AssertCollectionCount(t, database, "circle_post_placement_command_receipts", 1)
	testsupport.AssertCollectionCount(t, database, "circle_post_placement_outbox", 1)
}
