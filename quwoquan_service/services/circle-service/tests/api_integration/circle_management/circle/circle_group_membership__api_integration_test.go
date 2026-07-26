package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	grouppersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
	groupmembershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	groupmembershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/persistence"
)

func TestCircleGroupMembershipRealTransactionLifecycleBOLAAndStream(t *testing.T) {
	cleanCollections(t)
	seedGroupCirclePolicy(t, "circle-group-membership", "persona-owner", "persona-member")

	groupBody := map[string]any{
		"groupType": "self_built", "name": "同行群", "description": "真实群成员链",
		"visibility": "private", "joinPolicy": "apply_only", "storageEnabled": true, "noticeEnabled": true,
	}
	createdRecorder := executeGroupCommand(t, http.MethodPost, "/circles/circle-group-membership/groups", groupBody, "group-membership-group-create", "", "persona-owner", "CreateCircleGroup")
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

	applyPath := "/circles/circle-group-membership/groups/" + groupID + "/memberships"
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

	selfApprove := executeGroupMembershipCommand(t, http.MethodPost, applyPath+"/persona-member:approve", nil, "self-approve", "", "persona-member", "ApproveCircleGroupMember")
	if selfApprove.Code != http.StatusForbidden || decodeBody(t, selfApprove)["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("self approval must fail closed: status=%d body=%s", selfApprove.Code, selfApprove.Body.String())
	}

	approve := executeGroupMembershipCommand(t, http.MethodPost, applyPath+"/persona-member:approve", nil, "owner-approve", "", "persona-owner", "ApproveCircleGroupMember")
	approveBody := decodeBody(t, approve)
	if approve.Code != http.StatusOK || approveBody["state"] != "active" || approveBody["version"] != float64(2) {
		t.Fatalf("approve drift: status=%d body=%s", approve.Code, approve.Body.String())
	}
	role := executeGroupMembershipCommand(t, http.MethodPatch, applyPath+"/persona-member/role", map[string]any{"role": "manager"}, "owner-role", "", "persona-owner", "UpdateCircleGroupMemberRole")
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

	leave := executeGroupMembershipCommand(t, http.MethodDelete, applyPath+"/self", nil, "member-leave", "", "persona-member", "LeaveCircleGroup")
	leaveBody := decodeBody(t, leave)
	if leave.Code != http.StatusOK || leaveBody["state"] != "left" || leaveBody["version"] != float64(4) {
		t.Fatalf("leave drift: status=%d body=%s", leave.Code, leave.Body.String())
	}
	conflict := executeGroupMembershipCommand(t, http.MethodDelete, applyPath+"/self", nil, "group-member-apply", "", "persona-member", "LeaveCircleGroup")
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
		messaging.NewCircleGroupMembershipStreamPublisher(circleMessageTransport), "group-membership-stream-api-test",
	)
	if count, err := streamRelay.Drain(context.Background(), 10); err != nil || count != 5 {
		t.Fatalf("group membership stream count=%d err=%v", count, err)
	}
}

func TestCircleGroupMembershipCapacityRejectsOneThousandAndFirstMember(t *testing.T) {
	cleanCollections(t)
	const (
		circleID = "circle-group-capacity"
		ownerID  = "persona-owner"
		firstID  = "persona-capacity-first"
		nextID   = "persona-capacity-next"
	)
	seedGroupCirclePolicy(t, circleID, ownerID, firstID)
	now := time.Now().UTC()
	if _, err := mongoDB.Collection("circle_memberships").InsertOne(context.Background(), bson.M{
		"_id": "cm-capacity-next", "version": 1, "circleId": circleID, "personaId": nextID,
		"role": "member", "state": "active", "createdAt": now, "updatedAt": now,
	}); err != nil {
		t.Fatal(err)
	}

	group := executeGroupCommand(t, http.MethodPost, "/circles/"+circleID+"/groups", map[string]any{
		"groupType": "self_built", "name": "容量边界群", "description": "1000 名成员上限",
		"visibility": "private", "joinPolicy": "apply_only", "storageEnabled": true, "noticeEnabled": true,
	}, "group-capacity-create", "", ownerID, "CreateCircleGroup")
	if group.Code != http.StatusCreated {
		t.Fatalf("create capacity group: status=%d body=%s", group.Code, group.Body.String())
	}
	groupID := decodeBody(t, group)["groupId"].(string)

	groupStore := grouppersistence.NewMongoAggregateStore(mongoDB)
	groupMembershipStore := groupmembershippersistence.NewMongoAggregateStore(mongoDB)
	groupMembershipReaders := groupmembershippersistence.NewMongoReaders(mongoDB)
	groupMembershipCommands := groupmembershipapp.NewCommandFacade(
		groupMembershipStore, groupMembershipReaders, groupMembershipReaders, groupMembershipReaders,
	)
	ownerRelay := groupapp.NewOutboxRelay(
		groupStore,
		groupStore,
		groupmembershipapp.NewCircleGroupOwnerProjector(groupMembershipCommands),
		"capacity-owner-membership",
	)
	if count, err := ownerRelay.Drain(context.Background(), 10); err != nil || count != 1 {
		t.Fatalf("project capacity group owner: count=%d err=%v", count, err)
	}

	seededMembers := make([]any, 0, 998)
	for index := 0; index < 998; index++ {
		seededMembers = append(seededMembers, bson.M{
			"_id": fmt.Sprintf("cgm-capacity-%04d", index), "version": 1,
			"circleId": circleID, "groupId": groupID, "personaId": fmt.Sprintf("persona-capacity-%04d", index),
			"role": "member", "state": "active", "joinedAt": now, "decidedAt": now,
			"decidedByPersonaId": ownerID, "createdAt": now, "updatedAt": now,
		})
	}
	if _, err := mongoDB.Collection("circle_group_memberships").InsertMany(context.Background(), seededMembers); err != nil {
		t.Fatal(err)
	}
	// The counter is an internal invariant ledger. Removing it simulates an
	// interrupted bootstrap: the next transaction must derive it from the
	// authoritative active membership set without allowing a 1001st member.
	if _, err := mongoDB.Collection("circle_group_membership_capacity_counters").DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatal(err)
	}

	applyPath := "/circles/" + circleID + "/groups/" + groupID + "/memberships"
	for _, personaID := range []string{firstID, nextID} {
		applied := executeGroupMembershipCommand(
			t,
			http.MethodPost,
			applyPath,
			nil,
			"capacity-apply-"+personaID,
			"",
			personaID,
			"ApplyJoinCircleGroup",
		)
		if applied.Code != http.StatusCreated || decodeBody(t, applied)["state"] != "pending" {
			t.Fatalf("apply %s must remain pending before capacity decision: status=%d body=%s", personaID, applied.Code, applied.Body.String())
		}
	}

	firstApproval := executeGroupMembershipCommand(
		t,
		http.MethodPost,
		applyPath+"/"+firstID+":approve",
		nil,
		"capacity-approve-first",
		"",
		ownerID,
		"ApproveCircleGroupMember",
	)
	if firstApproval.Code != http.StatusOK || decodeBody(t, firstApproval)["state"] != "active" {
		t.Fatalf("the 1000th active member must commit: status=%d body=%s", firstApproval.Code, firstApproval.Body.String())
	}

	full := executeGroupMembershipCommand(
		t,
		http.MethodPost,
		applyPath+"/"+nextID+":approve",
		nil,
		"capacity-approve-next",
		"",
		ownerID,
		"ApproveCircleGroupMember",
	)
	if full.Code != http.StatusConflict || decodeBody(t, full)["code"] != "CIRCLE.USER.group_membership_full" {
		t.Fatalf("the 1001st active member must be rejected: status=%d body=%s", full.Code, full.Body.String())
	}

	activeCount, err := mongoDB.Collection("circle_group_memberships").CountDocuments(context.Background(), bson.M{
		"groupId": groupID, "state": "active",
	})
	if err != nil || activeCount != 1000 {
		t.Fatalf("capacity rejection must not partially write membership: activeCount=%d err=%v", activeCount, err)
	}
	var rejected struct {
		State   string `bson:"state"`
		Version int64  `bson:"version"`
	}
	if err := mongoDB.Collection("circle_group_memberships").FindOne(context.Background(), bson.M{
		"groupId": groupID, "personaId": nextID,
	}).Decode(&rejected); err != nil {
		t.Fatal(err)
	}
	if rejected.State != "pending" || rejected.Version != 1 {
		t.Fatalf("rejected capacity target must retain pending state, got=%+v", rejected)
	}
	var capacity struct {
		ActiveMemberCount int64 `bson:"activeMemberCount"`
	}
	if err := mongoDB.Collection("circle_group_membership_capacity_counters").FindOne(
		context.Background(),
		bson.M{"_id": groupID},
	).Decode(&capacity); err != nil || capacity.ActiveMemberCount != 1000 {
		t.Fatalf("capacity ledger must commit with membership transaction: counter=%+v err=%v", capacity, err)
	}
}

func executeGroupMembershipCommand(t *testing.T, method, path string, body any, idempotencyKey, ifMatch, personaID, operationName string) *httptest.ResponseRecorder {
	t.Helper()
	request := groupMembershipRequest(t, method, path, body, idempotencyKey, ifMatch)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	template := "/circles/{circleId}/groups/{groupId}/memberships"
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
	template := "/circles/{circleId}/groups/{groupId}/memberships"
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
