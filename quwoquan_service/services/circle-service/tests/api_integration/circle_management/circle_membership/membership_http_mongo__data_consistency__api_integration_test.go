// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/spec.md#sit-002
// readiness_case: join-circle-api
// readiness_case: list-persona-circles-api
// readiness_case: leave-circle-api
// readiness_case: get-my-circle-membership-api
// readiness_case: list-circle-memberships-api
// readiness_case: list-pending-circle-memberships-api
// readiness_case: approve-circle-member-api
// readiness_case: reject-circle-member-api
// readiness_case: update-circle-membership-role-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

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

func TestCircleMembershipHTTPExecutesQueriesModerationRoleAndLeave(t *testing.T) {
	database := testsupport.StartRealMongo(t, "circle_membership_operation_api")
	ctx := context.Background()
	now := time.Now().UTC()
	if _, err := database.Collection("circles").InsertOne(ctx, bson.M{
		"_id": "circle-membership-operations", "name": "Membership Operations",
		"description": "object-local HTTP contract", "ownerId": "persona-owner",
		"status": "active", "visibility": "public", "joinPolicy": "approval",
		"memberCount": int64(0), "createdAt": now, "updatedAt": now,
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

	serveCircle := func(method, path string, rest []string, operationID, personaID, key string, body any) *httptest.ResponseRecorder {
		t.Helper()
		request := testsupport.Request(t, method, path, body, operationID, personaID, key)
		recorder := httptest.NewRecorder()
		handler.ServeCircleRoute(recorder, request, "circle-membership-operations", rest)
		return recorder
	}
	assertState := func(recorder *httptest.ResponseRecorder, wantStatus int, wantState string) map[string]any {
		t.Helper()
		if recorder.Code != wantStatus {
			t.Fatalf("status=%d want=%d body=%s", recorder.Code, wantStatus, recorder.Body.String())
		}
		var body map[string]any
		if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
			t.Fatalf("decode response: %v body=%s", err, recorder.Body.String())
		}
		if wantState != "" && body["state"] != wantState {
			t.Fatalf("state=%v want=%s body=%#v", body["state"], wantState, body)
		}
		return body
	}

	ownerJoin := serveCircle(
		http.MethodPost, "/circles/circle-membership-operations/memberships", nil,
		"circle.circle_membership.JoinCircle", "persona-owner", "owner-join", nil,
	)
	owner := assertState(ownerJoin, http.StatusCreated, "active")
	if owner["role"] != "owner" {
		t.Fatalf("owner role drift: %#v", owner)
	}

	applicantJoin := serveCircle(
		http.MethodPost, "/circles/circle-membership-operations/memberships", nil,
		"circle.circle_membership.JoinCircle", "persona-applicant", "applicant-join", nil,
	)
	assertState(applicantJoin, http.StatusCreated, "pending")

	self := serveCircle(
		http.MethodGet, "/circles/circle-membership-operations/memberships/self", []string{"self"},
		"circle.circle_membership.GetMyCircleMembership", "persona-applicant", "self-query", nil,
	)
	selfBody := assertState(self, http.StatusOK, "pending")
	if selfBody["personaId"] != "persona-applicant" {
		t.Fatalf("self identity drift: %#v", selfBody)
	}

	pending := serveCircle(
		http.MethodGet, "/circles/circle-membership-operations/memberships/pending?limit=10", []string{"pending"},
		"circle.circle_membership.ListPendingCircleMemberships", "persona-owner", "pending-query", nil,
	)
	pendingBody := assertState(pending, http.StatusOK, "")
	if items, ok := pendingBody["items"].([]any); !ok || len(items) != 1 {
		t.Fatalf("pending queue drift: %#v", pendingBody)
	}

	approve := serveCircle(
		http.MethodPost, "/circles/circle-membership-operations/memberships/persona-applicant:approve", []string{"persona-applicant:approve"},
		"circle.circle_membership.ApproveCircleMember", "persona-owner", "approve-applicant", nil,
	)
	assertState(approve, http.StatusOK, "active")

	roster := serveCircle(
		http.MethodGet, "/circles/circle-membership-operations/memberships?limit=10", nil,
		"circle.circle_membership.ListCircleMemberships", "", "roster-query", nil,
	)
	rosterBody := assertState(roster, http.StatusOK, "")
	if items, ok := rosterBody["items"].([]any); !ok || len(items) != 2 {
		t.Fatalf("active roster drift: %#v", rosterBody)
	}

	role := serveCircle(
		http.MethodPatch, "/circles/circle-membership-operations/memberships/persona-applicant/role", []string{"persona-applicant", "role"},
		"circle.circle_membership.UpdateCircleMembershipRole", "persona-owner", "promote-applicant",
		map[string]any{"role": "admin"},
	)
	roleBody := assertState(role, http.StatusOK, "active")
	if roleBody["role"] != "admin" {
		t.Fatalf("role update drift: %#v", roleBody)
	}

	personaRequest := testsupport.Request(
		t, http.MethodGet, "/personas/persona-applicant/circles?limit=10", nil,
		"circle.circle_membership.ListPersonaCircles", "persona-applicant", "persona-circles-query",
	)
	personaRecorder := httptest.NewRecorder()
	handler.ServePersonaCircles(personaRecorder, personaRequest)
	personaBody := assertState(personaRecorder, http.StatusOK, "")
	if items, ok := personaBody["items"].([]any); !ok || len(items) != 1 ||
		items[0].(map[string]any)["circleId"] != "circle-membership-operations" {
		t.Fatalf("persona circles drift: %#v", personaBody)
	}

	leave := serveCircle(
		http.MethodDelete, "/circles/circle-membership-operations/memberships/self", []string{"self"},
		"circle.circle_membership.LeaveCircle", "persona-applicant", "leave-applicant", nil,
	)
	assertState(leave, http.StatusOK, "left")

	secondJoin := serveCircle(
		http.MethodPost, "/circles/circle-membership-operations/memberships", nil,
		"circle.circle_membership.JoinCircle", "persona-second", "second-join", nil,
	)
	assertState(secondJoin, http.StatusCreated, "pending")
	reject := serveCircle(
		http.MethodPost, "/circles/circle-membership-operations/memberships/persona-second:reject", []string{"persona-second:reject"},
		"circle.circle_membership.RejectCircleMember", "persona-owner", "reject-second", nil,
	)
	assertState(reject, http.StatusOK, "rejected")

	for eventType, want := range map[string]int64{
		"CircleMembershipJoined":      1,
		"CircleMembershipRequested":   2,
		"CircleMembershipApproved":    1,
		"CircleMembershipRoleChanged": 1,
		"CircleMembershipLeft":        1,
		"CircleMembershipRejected":    1,
	} {
		count, err := database.Collection("circle_membership_outbox").CountDocuments(ctx, bson.M{"eventType": eventType})
		if err != nil || count != want {
			t.Fatalf("outbox %s count=%d want=%d err=%v", eventType, count, want, err)
		}
	}
}
