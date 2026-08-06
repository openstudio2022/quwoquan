// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-002
// readiness_case: apply-join-circle-group-api
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#sit-001
// readiness_case: list-circle-group-memberships-api
// readiness_case: get-my-circle-group-membership-api
// readiness_case: leave-circle-group-api
// readiness_case: approve-circle-group-member-api
// readiness_case: reject-circle-group-member-api
// readiness_case: remove-circle-group-member-api
// readiness_case: update-circle-group-member-role-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/operation"
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
	if _, err := database.Collection("circle_memberships").InsertMany(ctx, []any{
		bson.M{
			"_id": "circle-member-applicant", "circleId": "circle-membership-object",
			"personaId": "persona-group-applicant", "role": "member", "state": "active",
		},
		bson.M{
			"_id": "circle-member-reject", "circleId": "circle-membership-object",
			"personaId": "persona-group-reject", "role": "member", "state": "active",
		},
		bson.M{
			"_id": "circle-member-remove", "circleId": "circle-membership-object",
			"personaId": "persona-group-remove", "role": "member", "state": "active",
		},
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoReaders(database)
	commands := app.NewCommandFacade(store, readers, readers, readers)
	queries := app.NewQueryFacade(readers, readers)
	handler := httpadapter.NewHandler(commands, queries)
	ownerContext := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "circle.circle_group_membership.ActivateOwner",
		IdempotencyKey: "activate-owner", Actor: operation.ActorContext{PersonaID: "persona-group-owner"},
	})
	if _, err := commands.ActivateOwner(
		ownerContext, "circle-membership-object", "group-membership-object", "persona-group-owner",
	); err != nil {
		t.Fatalf("activate CircleGroup owner: %v", err)
	}
	request := testsupport.Request(t, http.MethodPost,
		"/circles/circle-membership-object/groups/group-membership-object/memberships", nil,
		"circle.circle_group_membership.ApplyJoinCircleGroup", "persona-group-applicant", "group-membership-object-1")
	recorder := httptest.NewRecorder()
	handler.ServeCircleGroupRoute(recorder, request, "circle-membership-object", "group-membership-object", nil)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("apply status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	testsupport.AssertCollectionCount(t, database, "circle_group_memberships", 2)

	getRequest := testsupport.Request(t, http.MethodGet,
		"/circles/circle-membership-object/groups/group-membership-object/memberships/self", nil,
		"circle.circle_group_membership.GetMyCircleGroupMembership", "persona-group-applicant", "group-get-self")
	getRecorder := httptest.NewRecorder()
	handler.ServeCircleGroupRoute(getRecorder, getRequest, "circle-membership-object", "group-membership-object", []string{"self"})
	if getRecorder.Code != http.StatusOK || decodeGroupMembershipResponse(t, getRecorder)["state"] != "pending" {
		t.Fatalf("get self status=%d body=%s", getRecorder.Code, getRecorder.Body.String())
	}

	listRequest := testsupport.Request(t, http.MethodGet,
		"/circles/circle-membership-object/groups/group-membership-object/memberships?limit=20", nil,
		"circle.circle_group_membership.ListCircleGroupMemberships", "persona-group-owner", "group-list-members")
	listRecorder := httptest.NewRecorder()
	handler.ServeCircleGroupRoute(listRecorder, listRequest, "circle-membership-object", "group-membership-object", nil)
	if listRecorder.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listRecorder.Code, listRecorder.Body.String())
	}
	items, _ := decodeGroupMembershipResponse(t, listRecorder)["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("group membership roster=%#v", items)
	}

	approveRequest := testsupport.Request(t, http.MethodPost,
		"/circles/circle-membership-object/groups/group-membership-object/memberships/persona-group-applicant:approve", nil,
		"circle.circle_group_membership.ApproveCircleGroupMember", "persona-group-owner", "group-approve-member")
	approveRecorder := httptest.NewRecorder()
	handler.ServeCircleGroupRoute(approveRecorder, approveRequest, "circle-membership-object", "group-membership-object", []string{"persona-group-applicant:approve"})
	if approveRecorder.Code != http.StatusOK || decodeGroupMembershipResponse(t, approveRecorder)["state"] != "active" {
		t.Fatalf("approve status=%d body=%s", approveRecorder.Code, approveRecorder.Body.String())
	}

	roleRequest := testsupport.Request(t, http.MethodPatch,
		"/circles/circle-membership-object/groups/group-membership-object/memberships/persona-group-applicant/role",
		map[string]any{"role": "manager"},
		"circle.circle_group_membership.UpdateCircleGroupMemberRole", "persona-group-owner", "group-role-member")
	roleRecorder := httptest.NewRecorder()
	handler.ServeCircleGroupRoute(roleRecorder, roleRequest, "circle-membership-object", "group-membership-object", []string{"persona-group-applicant", "role"})
	if roleRecorder.Code != http.StatusOK || decodeGroupMembershipResponse(t, roleRecorder)["role"] != "manager" {
		t.Fatalf("role status=%d body=%s", roleRecorder.Code, roleRecorder.Body.String())
	}

	leaveRequest := testsupport.Request(t, http.MethodDelete,
		"/circles/circle-membership-object/groups/group-membership-object/memberships/self", nil,
		"circle.circle_group_membership.LeaveCircleGroup", "persona-group-applicant", "group-leave-self")
	leaveRecorder := httptest.NewRecorder()
	handler.ServeCircleGroupRoute(leaveRecorder, leaveRequest, "circle-membership-object", "group-membership-object", []string{"self"})
	if leaveRecorder.Code != http.StatusOK || decodeGroupMembershipResponse(t, leaveRecorder)["state"] != "left" {
		t.Fatalf("leave status=%d body=%s", leaveRecorder.Code, leaveRecorder.Body.String())
	}

	applyAndDecide := func(personaID, suffix, action, operationID string, method string) *httptest.ResponseRecorder {
		t.Helper()
		applyRequest := testsupport.Request(t, http.MethodPost,
			"/circles/circle-membership-object/groups/group-membership-object/memberships", nil,
			"circle.circle_group_membership.ApplyJoinCircleGroup", personaID, "group-apply-"+suffix)
		applyRecorder := httptest.NewRecorder()
		handler.ServeCircleGroupRoute(applyRecorder, applyRequest, "circle-membership-object", "group-membership-object", nil)
		if applyRecorder.Code != http.StatusCreated {
			t.Fatalf("apply %s status=%d body=%s", suffix, applyRecorder.Code, applyRecorder.Body.String())
		}
		decisionRequest := testsupport.Request(t, method,
			"/circles/circle-membership-object/groups/group-membership-object/memberships/"+personaID+action, nil,
			operationID, "persona-group-owner", "group-decision-"+suffix)
		decisionRecorder := httptest.NewRecorder()
		handler.ServeCircleGroupRoute(decisionRecorder, decisionRequest, "circle-membership-object", "group-membership-object", []string{personaID + action})
		return decisionRecorder
	}
	rejected := applyAndDecide("persona-group-reject", "reject", ":reject", "circle.circle_group_membership.RejectCircleGroupMember", http.MethodPost)
	if rejected.Code != http.StatusOK || decodeGroupMembershipResponse(t, rejected)["state"] != "rejected" {
		t.Fatalf("reject status=%d body=%s", rejected.Code, rejected.Body.String())
	}
	removed := applyAndDecide("persona-group-remove", "remove", "", "circle.circle_group_membership.RemoveCircleGroupMember", http.MethodDelete)
	if removed.Code != http.StatusOK || decodeGroupMembershipResponse(t, removed)["state"] != "removed" {
		t.Fatalf("remove status=%d body=%s", removed.Code, removed.Body.String())
	}
}

func decodeGroupMembershipResponse(t *testing.T, recorder *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var value map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode CircleGroupMembership response: %v body=%s", err, recorder.Body.String())
	}
	return value
}
