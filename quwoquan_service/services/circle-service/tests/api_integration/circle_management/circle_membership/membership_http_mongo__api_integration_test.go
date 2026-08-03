// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-002
package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/application"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_membership/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestJoinCircleMembershipHTTPCommitsAggregateReceiptAndOutbox(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_membership_object_api")
	ctx := context.Background()
	if _, err := database.Collection("circles").InsertOne(ctx, bson.M{
		"_id": "circle-membership-object", "ownerId": "persona-circle-owner",
		"status": "active", "joinPolicy": "open",
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoReaders(database)
	handler := httpadapter.NewHandler(
		app.NewCommandFacade(store, readers, readers),
		app.NewQueryFacade(readers, readers, readers),
	)
	request := testsupport.Request(t, http.MethodPost, "/circles/circle-membership-object/memberships", nil,
		"circle.circle_membership.JoinCircle", "persona-circle-member", "membership-object-1")
	recorder := httptest.NewRecorder()
	handler.ServeCircleRoute(recorder, request, "circle-membership-object", nil)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("join status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	testsupport.AssertCollectionCount(t, database, "circle_memberships", 1)
	testsupport.AssertCollectionCount(t, database, "circle_membership_command_receipts", 1)
	testsupport.AssertCollectionCount(t, database, "circle_membership_outbox", 1)
}
