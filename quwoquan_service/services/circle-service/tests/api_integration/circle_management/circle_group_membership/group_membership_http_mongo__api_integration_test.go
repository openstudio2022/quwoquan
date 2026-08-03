// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-002
package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestApplyCircleGroupMembershipHTTPCommitsAggregateReceiptAndOutbox(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_group_membership_object_api")
	ctx := context.Background()
	if _, err := database.Collection("circle_groups").InsertOne(ctx, bson.M{
		"_id": "group-membership-object", "circleId": "circle-membership-object",
		"status": "active", "joinPolicy": "apply_only", "createdByPersonaId": "persona-group-owner",
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_memberships").InsertOne(ctx, bson.M{
		"_id": "circle-member-applicant", "circleId": "circle-membership-object",
		"personaId": "persona-group-applicant", "role": "member", "state": "active",
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoReaders(database)
	handler := httpadapter.NewHandler(
		app.NewCommandFacade(store, readers, readers, readers),
		app.NewQueryFacade(readers, readers),
	)
	request := testsupport.Request(t, http.MethodPost,
		"/circles/circle-membership-object/groups/group-membership-object/memberships", nil,
		"circle.circle_group_membership.ApplyJoinCircleGroup", "persona-group-applicant", "group-membership-object-1")
	recorder := httptest.NewRecorder()
	handler.ServeCircleGroupRoute(recorder, request, "circle-membership-object", "group-membership-object", nil)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("apply status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	testsupport.AssertCollectionCount(t, database, "circle_group_memberships", 1)
	testsupport.AssertCollectionCount(t, database, "circle_group_membership_command_receipts", 1)
	testsupport.AssertCollectionCount(t, database, "circle_group_membership_outbox", 1)
}
