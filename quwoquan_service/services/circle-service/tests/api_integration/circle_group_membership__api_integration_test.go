package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	groupapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group"
	groupmembershipapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group_membership"
	grouppersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_group/persistence"
	groupmembershippersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_group_membership/persistence"
	"quwoquan_service/services/circle-service/internal/infrastructure/messaging"
)

func TestCircleGroupMembershipRealTransactionLifecycleBOLAAndStream(t *testing.T) {
	cleanCollections(t)
	seedGroupCirclePolicy(t, "circle-group-membership", "persona-owner", "persona-member")

	groupBody := map[string]any{
		"groupType": "self_built", "name": "同行群", "description": "真实群成员链",
		"visibility": "private", "joinPolicy": "apply_only", "storageEnabled": true, "noticeEnabled": true,
	}
	createdRecorder := executeGroupCommand(t, http.MethodPost, "/v1/circles/circle-group-membership/groups", groupBody, "group-membership-group-create", "", "persona-owner", "CreateCircleGroup")
	if createdRecorder.Code != http.StatusCreated {
		t.Fatalf("create group failed: status=%d body=%s", createdRecorder.Code, createdRecorder.Body.String())
	}
	groupID := decodeBody(t, createdRecorder)["groupId"].(string)

	groupStore := grouppersistence.NewMongoAggregateStore(mongoDB)
	groupMembershipStore := groupmembershippersistence.NewMongoAggregateStore(mongoDB)
	groupMembershipReaders := groupmembershippersistence.NewMongoReaders(mongoDB)
	groupMembershipCommands := groupmembershipapp.NewCommandFacade(
		groupMembershipStore, groupMembershipReaders, groupMembershipReaders, groupMembershipReaders,
	)
	ownerRelay := groupapp.NewOutboxRelay(
		groupStore, groupStore, groupmembershipapp.NewCircleGroupOwnerProjector(groupMembershipCommands), "owner-membership-api-test",
	)
	if count, err := ownerRelay.Drain(context.Background(), 10); err != nil || count != 1 {
		t.Fatalf("owner membership projection count=%d err=%v", count, err)
	}

	applyPath := "/v1/circles/circle-group-membership/groups/" + groupID + "/memberships"
	first := executeGroupMembershipCommand(t, http.MethodPost, applyPath, nil, "group-member-apply", "", "persona-member", "ApplyJoinCircleGroup")
	if first.Code != http.StatusCreated {
		t.Fatalf("apply group membership failed: status=%d body=%s", first.Code, first.Body.String())
	}
	applied := decodeBody(t, first)
	if applied["version"] != float64(1) || applied["state"] != "pending" || applied["role"] != "member" {
		t.Fatalf("apply receipt drift: %#v", applied)
	}
	replay := executeGroupMembershipCommand(t, http.MethodPost, applyPath, nil, "group-member-apply", "", "persona-member", "ApplyJoinCircleGroup")
	if replay.Code != http.StatusCreated || decodeBody(t, replay)["idempotentReplay"] != true {
		t.Fatalf("apply replay drift: status=%d body=%s", replay.Code, replay.Body.String())
	}

	self := executeGroupMembershipQuery(t, applyPath+"/self", "persona-member", "GetMyCircleGroupMembership")
	if self.Code != http.StatusOK {
		t.Fatalf("get self group membership failed: status=%d body=%s", self.Code, self.Body.String())
	}
	selfBody := decodeBody(t, self)
	if selfBody["personaId"] != "persona-member" || selfBody["state"] != "pending" {
		t.Fatalf("self group membership drift: %#v", selfBody)
	}
	if _, leaked := selfBody["_id"]; leaked {
		t.Fatalf("Reader leaked _id: %#v", selfBody)
	}
	if _, leaked := selfBody["decidedByPersonaId"]; leaked {
		t.Fatalf("Reader leaked decision actor: %#v", selfBody)
	}

	selfApprove := executeGroupMembershipCommand(t, http.MethodPost, applyPath+"/persona-member:approve", nil, "self-approve", "1", "persona-member", "ApproveCircleGroupMember")
	if selfApprove.Code != http.StatusForbidden || decodeBody(t, selfApprove)["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("self approval must fail closed: status=%d body=%s", selfApprove.Code, selfApprove.Body.String())
	}

	approve := executeGroupMembershipCommand(t, http.MethodPost, applyPath+"/persona-member:approve", nil, "owner-approve", "1", "persona-owner", "ApproveCircleGroupMember")
	approveBody := decodeBody(t, approve)
	if approve.Code != http.StatusOK || approveBody["state"] != "active" || approveBody["version"] != float64(2) {
		t.Fatalf("approve drift: status=%d body=%s", approve.Code, approve.Body.String())
	}
	role := executeGroupMembershipCommand(t, http.MethodPatch, applyPath+"/persona-member/role", map[string]any{"role": "manager"}, "owner-role", "2", "persona-owner", "UpdateCircleGroupMemberRole")
	roleBody := decodeBody(t, role)
	if role.Code != http.StatusOK || roleBody["role"] != "manager" || roleBody["version"] != float64(3) {
		t.Fatalf("role update drift: status=%d body=%s", role.Code, role.Body.String())
	}

	list := executeGroupMembershipQuery(t, applyPath+"?limit=10", "persona-owner", "ListCircleGroupMemberships")
	if list.Code != http.StatusOK || len(decodeBody(t, list)["items"].([]any)) != 2 {
		t.Fatalf("group roster drift: status=%d body=%s", list.Code, list.Body.String())
	}
	denied := executeGroupMembershipQuery(t, applyPath+"?limit=10", "persona-outsider", "ListCircleGroupMemberships")
	if denied.Code != http.StatusForbidden || decodeBody(t, denied)["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("group roster BOLA drift: status=%d body=%s", denied.Code, denied.Body.String())
	}

	leave := executeGroupMembershipCommand(t, http.MethodDelete, applyPath+"/self", nil, "member-leave", "3", "persona-member", "LeaveCircleGroup")
	leaveBody := decodeBody(t, leave)
	if leave.Code != http.StatusOK || leaveBody["state"] != "left" || leaveBody["version"] != float64(4) {
		t.Fatalf("leave drift: status=%d body=%s", leave.Code, leave.Body.String())
	}
	conflict := executeGroupMembershipCommand(t, http.MethodDelete, applyPath+"/self", nil, "group-member-apply", "4", "persona-member", "LeaveCircleGroup")
	if conflict.Code != http.StatusConflict || decodeBody(t, conflict)["code"] != "CIRCLE.USER.group_membership_idempotency_conflict" {
		t.Fatalf("idempotency conflict drift: status=%d body=%s", conflict.Code, conflict.Body.String())
	}

	for collection, want := range map[string]int64{
		"circle_group_memberships": 2, "circle_group_membership_command_receipts": 5, "circle_group_membership_outbox": 5,
	} {
		count, err := mongoDB.Collection(collection).CountDocuments(context.Background(), bson.M{})
		if err != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, err)
		}
	}

	streamRelay := groupmembershipapp.NewOutboxRelay(
		groupMembershipStore, groupMembershipStore,
		messaging.NewCircleGroupMembershipStreamPublisher(redisRouter.Scene("general")), "group-membership-stream-api-test",
	)
	if count, err := streamRelay.Drain(context.Background(), 10); err != nil || count != 5 {
		t.Fatalf("group membership stream count=%d err=%v", count, err)
	}
}

func executeGroupMembershipCommand(t *testing.T, method, path string, body any, idempotencyKey, ifMatch, personaID, operationName string) *httptest.ResponseRecorder {
	t.Helper()
	request := groupMembershipRequest(t, method, path, body, idempotencyKey, ifMatch)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	template := "/v1/circles/{circleId}/groups/{groupId}/memberships"
	switch operationName {
	case "LeaveCircleGroup":
		template += "/self"
	case "ApproveCircleGroupMember":
		template += "/{personaId}:approve"
	case "RejectCircleGroupMember":
		template += "/{personaId}:reject"
	case "RemoveCircleGroupMember":
		template += "/{personaId}"
	case "UpdateCircleGroupMemberRole":
		template += "/{personaId}/role"
	}
	groupMembershipGuard(method, template, operationName).ServeHTTP(recorder, request)
	return recorder
}

func executeGroupMembershipQuery(t *testing.T, path, personaID, operationName string) *httptest.ResponseRecorder {
	t.Helper()
	request := groupMembershipRequest(t, http.MethodGet, path, nil, "query-"+personaID, "")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	template := "/v1/circles/{circleId}/groups/{groupId}/memberships"
	if operationName == "GetMyCircleGroupMembership" {
		template += "/self"
	}
	recorder := httptest.NewRecorder()
	groupMembershipGuard(http.MethodGet, template, operationName).ServeHTTP(recorder, request)
	return recorder
}

func groupMembershipGuard(method, pathTemplate, operationName string) http.Handler {
	operationKind, mutationTarget, invariantTarget := generatedTestOperationSemantics(
		method,
		"CircleGroupMembership",
	)
	return rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle_group_membership." + operationName,
			ContractGraphSHA256:  "circle-group-membership-api-integration", Method: method, PathTemplate: pathTemplate,
			OperationKind: operationKind, MutationTarget: mutationTarget, InvariantTarget: invariantTarget,
			AuthMode: "required", ActorRequirement: "persona", Principal: "persona",
			CommercialStatus: "ready", TimeoutMilliseconds: 1500,
		}}, method, pathTemplate,
	)(testHandler)
}

func groupMembershipRequest(t *testing.T, method, path string, body any, idempotencyKey, ifMatch string) *http.Request {
	t.Helper()
	var buffer bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buffer).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	request := httptest.NewRequest(method, path, &buffer)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request.Header.Set("X-Request-Id", "request-"+idempotencyKey)
	request.Header.Set("X-Trace-Id", "trace-"+idempotencyKey)
	request.Header.Set("X-Client-Surface-Id", "circleDetail")
	if ifMatch != "" {
		request.Header.Set("If-Match", ifMatch)
	}
	return request
}
