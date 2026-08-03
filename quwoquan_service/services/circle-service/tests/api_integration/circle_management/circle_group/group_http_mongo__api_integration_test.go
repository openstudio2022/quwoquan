// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#sit-001
package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_group/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestCreateCircleGroupHTTPCommitsAggregateReceiptAndOutbox(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_group_object_api")
	ctx := context.Background()
	if _, err := database.Collection("circles").InsertOne(ctx, bson.M{
		"_id": "circle-group-object", "status": "active",
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_memberships").InsertOne(ctx, bson.M{
		"_id": "membership-group-owner", "circleId": "circle-group-object",
		"personaId": "persona-group-owner", "role": "owner", "state": "active",
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoReaders(database)
	handler := httpadapter.NewHandler(app.NewCommandFacade(store, readers), app.NewQueryFacade(readers, readers))
	request := testsupport.Request(t, http.MethodPost, "/circles/circle-group-object/groups", map[string]any{
		"groupType": "self_built", "name": "周末同行", "description": "同行协作",
		"visibility": "public", "joinPolicy": "apply_only",
		"storageEnabled": true, "noticeEnabled": true,
	}, "circle.circle_group.CreateCircleGroup", "persona-group-owner", "group-object-1")
	recorder := httptest.NewRecorder()
	handler.ServeCircleRoute(recorder, request, "circle-group-object", nil)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	testsupport.AssertCollectionCount(t, database, "circle_groups", 1)
	testsupport.AssertCollectionCount(t, database, "circle_group_command_receipts", 1)
	testsupport.AssertCollectionCount(t, database, "circle_group_outbox", 1)
}
