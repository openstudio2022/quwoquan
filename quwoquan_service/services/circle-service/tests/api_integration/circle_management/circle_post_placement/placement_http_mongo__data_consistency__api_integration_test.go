// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// readiness_case: place-post-in-circle-api
// readiness_case: remove-post-from-circle-api
// readiness_case: pin-circle-post-api
// readiness_case: feature-circle-post-api
package api_integration

import (
	"context"
	"encoding/json"
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
	var placed app.CommandResult
	if err := json.NewDecoder(recorder.Body).Decode(&placed); err != nil {
		t.Fatal(err)
	}
	if placed.PlacementID == "" || placed.Version != 1 {
		t.Fatalf("place result=%+v", placed)
	}

	pin := testsupport.Request(
		t, http.MethodPatch,
		"/circles/circle-placement-object/post-placements/"+placed.PlacementID+"/pin",
		map[string]any{"enabled": true},
		"circle.circle_post_placement.PinCirclePost",
		"persona-placement-owner",
		"placement-object-pin",
	)
	pinRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(
		pinRecorder, pin, "circle-placement-object", []string{placed.PlacementID, "pin"},
	)
	if pinRecorder.Code != http.StatusOK {
		t.Fatalf("pin status=%d body=%s", pinRecorder.Code, pinRecorder.Body.String())
	}
	var pinned app.CommandResult
	if err := json.NewDecoder(pinRecorder.Body).Decode(&pinned); err != nil {
		t.Fatal(err)
	}
	if pinned.Version != 2 || pinned.State != "active" {
		t.Fatalf("pin result=%+v", pinned)
	}

	feature := testsupport.Request(
		t, http.MethodPatch,
		"/circles/circle-placement-object/post-placements/"+placed.PlacementID+"/feature",
		map[string]any{"enabled": true},
		"circle.circle_post_placement.FeatureCirclePost",
		"persona-placement-owner",
		"placement-object-feature",
	)
	featureRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(
		featureRecorder, feature, "circle-placement-object", []string{placed.PlacementID, "feature"},
	)
	if featureRecorder.Code != http.StatusOK {
		t.Fatalf("feature status=%d body=%s", featureRecorder.Code, featureRecorder.Body.String())
	}
	var featured app.CommandResult
	if err := json.NewDecoder(featureRecorder.Body).Decode(&featured); err != nil {
		t.Fatal(err)
	}
	if featured.Version != 3 || featured.State != "active" {
		t.Fatalf("feature result=%+v", featured)
	}

	remove := testsupport.Request(
		t, http.MethodDelete,
		"/circles/circle-placement-object/post-placements/"+placed.PlacementID,
		nil,
		"circle.circle_post_placement.RemovePostFromCircle",
		"persona-placement-owner",
		"placement-object-remove",
	)
	removeRecorder := httptest.NewRecorder()
	handler.ServeCircleRoute(
		removeRecorder, remove, "circle-placement-object", []string{placed.PlacementID},
	)
	if removeRecorder.Code != http.StatusOK {
		t.Fatalf("remove status=%d body=%s", removeRecorder.Code, removeRecorder.Body.String())
	}
	var stored struct {
		Version int64  `bson:"version"`
		State   string `bson:"state"`
	}
	if err := database.Collection("circle_post_placements").FindOne(
		ctx, bson.M{"_id": placed.PlacementID},
	).Decode(&stored); err != nil {
		t.Fatal(err)
	}
	if stored.Version != 4 || stored.State != "removed" {
		t.Fatalf("stored placement=%+v", stored)
	}
	testsupport.AssertCollectionCount(t, database, "circle_post_placements", 1)
	testsupport.AssertCollectionCount(t, database, "circle_post_placement_command_receipts", 4)
	testsupport.AssertCollectionCount(t, database, "circle_post_placement_outbox", 4)
}
