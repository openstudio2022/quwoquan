// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-003
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-003.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-003.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-003.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-006
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-006.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-006.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-006.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-006.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-007
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-007.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-007.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-007.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-007.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-004.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-004.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-005.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-005.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-005.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-008
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-008.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-008.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-008.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-008.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-009
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-009.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-009.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-009.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-009.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-010
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-010.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-010.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-010.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-010.t4
// readiness_case: apply-join-circle-group-api
// readiness_case: leave-circle-group-api
// readiness_case: approve-circle-group-member-api
// readiness_case: list-circle-group-memberships-api
// readiness_case: get-my-circle-group-membership-api
// readiness_case: reject-circle-group-member-api
// readiness_case: remove-circle-group-member-api
// readiness_case: update-circle-group-member-role-api
//
// owner 合同证据：ApplyJoinCircleGroup / LeaveCircleGroup / ApproveCircleGroupMember
// 三命令各自证明 owner 收敛（receipt 与 readback 同一 membership/version、单次
// outbox）、幂等重放（同 key 返回同一身份、不推进 version/outbox）与失败原子性
// （canonical typed failure、owner state/receipt/outbox 无部分成功）。
package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/runtime/operation"
	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

const (
	ownerContractCircleID = "circle-owner-contract"
	ownerContractGroupID  = "group-owner-contract"
	ownerContractOwner    = "persona-oc-owner"
	ownerContractMember   = "persona-oc-member"
	ownerContractOutsider = "persona-oc-outsider"
)

type ownerContractHarness struct {
	database *mongo.Database
	handler  *httpadapter.Handler
}

func newOwnerContractHarness(t *testing.T, databaseName string) ownerContractHarness {
	t.Helper()
	database := testsupport.StartRealMongo(t, databaseName)
	ctx := context.Background()
	if _, err := database.Collection("circle_groups").InsertOne(ctx, bson.M{
		"_id": ownerContractGroupID, "circleId": ownerContractCircleID,
		"status": "active", "joinPolicy": "apply_only", "createdByPersonaId": ownerContractOwner,
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_memberships").InsertMany(ctx, []any{
		bson.M{
			"_id": "cm-oc-member", "circleId": ownerContractCircleID,
			"personaId": ownerContractMember, "role": "member", "state": "active",
		},
		bson.M{
			"_id": "cm-oc-outsider-bola", "circleId": ownerContractCircleID,
			"personaId": ownerContractOutsider, "role": "member", "state": "active",
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
	ownerContext := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "circle.circle_group_membership.ActivateOwner",
		IdempotencyKey: "activate-owner-contract",
		Actor:          operation.ActorContext{PersonaID: ownerContractOwner},
	})
	if _, err := commands.ActivateOwner(
		ownerContext, ownerContractCircleID, ownerContractGroupID, ownerContractOwner,
	); err != nil {
		t.Fatalf("activate CircleGroup owner: %v", err)
	}
	return ownerContractHarness{
		database: database,
		handler:  httpadapter.NewHandler(commands, app.NewQueryFacade(readers, readers)),
	}
}

func (h ownerContractHarness) serve(
	t *testing.T,
	method, path, operationID, personaID, idempotencyKey string,
	tail []string,
) *httptest.ResponseRecorder {
	t.Helper()
	return h.serveBody(t, method, path, nil, operationID, personaID, idempotencyKey, tail)
}

func (h ownerContractHarness) serveBody(
	t *testing.T,
	method, path string,
	body map[string]any,
	operationID, personaID, idempotencyKey string,
	tail []string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := testsupport.Request(t, method, path, body, operationID, personaID, idempotencyKey)
	recorder := httptest.NewRecorder()
	h.handler.ServeCircleGroupRoute(
		recorder, request, ownerContractCircleID, ownerContractGroupID, tail,
	)
	return recorder
}

func (h ownerContractHarness) count(t *testing.T, collection string) int64 {
	t.Helper()
	count, err := h.database.Collection(collection).CountDocuments(context.Background(), bson.M{})
	if err != nil {
		t.Fatal(err)
	}
	return count
}

func (h ownerContractHarness) apply(t *testing.T, personaID, idempotencyKey string) *httptest.ResponseRecorder {
	t.Helper()
	return h.serve(t, http.MethodPost,
		"/circles/"+ownerContractCircleID+"/groups/"+ownerContractGroupID+"/memberships",
		"circle.circle_group_membership.ApplyJoinCircleGroup", personaID, idempotencyKey, nil)
}

func (h ownerContractHarness) approve(t *testing.T, actorID, targetID, idempotencyKey string) *httptest.ResponseRecorder {
	t.Helper()
	return h.serve(t, http.MethodPost,
		"/circles/"+ownerContractCircleID+"/groups/"+ownerContractGroupID+"/memberships/"+targetID+":approve",
		"circle.circle_group_membership.ApproveCircleGroupMember", actorID, idempotencyKey,
		[]string{targetID + ":approve"})
}

func (h ownerContractHarness) leave(t *testing.T, personaID, idempotencyKey string) *httptest.ResponseRecorder {
	t.Helper()
	return h.serve(t, http.MethodDelete,
		"/circles/"+ownerContractCircleID+"/groups/"+ownerContractGroupID+"/memberships/self",
		"circle.circle_group_membership.LeaveCircleGroup", personaID, idempotencyKey,
		[]string{"self"})
}

func TestApplyJoinCircleGroupOwnerContract(t *testing.T) {
	h := newOwnerContractHarness(t, "circle_group_membership_owner_apply")
	receiptsBefore := h.count(t, "circle_group_membership_command_receipts")
	outboxBefore := h.count(t, "circle_group_membership_outbox")

	// t1：单次提交，receipt 与 authoritative readback 收敛到同一 membership/state。
	first := h.apply(t, ownerContractMember, "oc-apply-1")
	if first.Code != http.StatusCreated {
		t.Fatalf("apply status=%d body=%s", first.Code, first.Body.String())
	}
	firstBody := decodeGroupMembershipResponse(t, first)
	readback := h.serve(t, http.MethodGet,
		"/circles/"+ownerContractCircleID+"/groups/"+ownerContractGroupID+"/memberships/self",
		"circle.circle_group_membership.GetMyCircleGroupMembership", ownerContractMember,
		"oc-apply-readback", []string{"self"})
	readbackBody := decodeGroupMembershipResponse(t, readback)
	if readback.Code != http.StatusOK ||
		readbackBody["membershipId"] != firstBody["membershipId"] ||
		readbackBody["state"] != "pending" || firstBody["state"] != "pending" {
		t.Fatalf("apply readback must converge: first=%#v readback=%#v", firstBody, readbackBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("apply must commit exactly one receipt and one outbox event")
	}

	// t2：相同幂等键重放返回同一 membership 身份，不推进 version/receipt/outbox。
	replay := h.apply(t, ownerContractMember, "oc-apply-1")
	replayBody := decodeGroupMembershipResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["membershipId"] != firstBody["membershipId"] ||
		replayBody["version"] != firstBody["version"] {
		t.Fatalf("idempotent replay must return the same identity: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("idempotent replay must not append receipts or outbox events")
	}

	// t3：非 Circle 成员申请返回 canonical typed failure，无部分成功。
	membershipsBefore := h.count(t, "circle_group_memberships")
	denied := h.apply(t, "persona-oc-stranger", "oc-apply-denied")
	deniedBody := decodeGroupMembershipResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] != "CIRCLE.USER.not_member" {
		t.Fatalf("non circle member apply must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	if h.count(t, "circle_group_memberships") != membershipsBefore ||
		h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("failed apply must not partially commit state, receipt or outbox")
	}
}

func TestApproveCircleGroupMemberOwnerContract(t *testing.T) {
	h := newOwnerContractHarness(t, "circle_group_membership_owner_approve")
	if code := h.apply(t, ownerContractMember, "oc-approve-apply").Code; code != http.StatusCreated {
		t.Fatalf("seed apply status=%d", code)
	}
	receiptsBefore := h.count(t, "circle_group_membership_command_receipts")
	outboxBefore := h.count(t, "circle_group_membership_outbox")

	// t3（先证 BOLA 原子性）：非 owner/manager 审批返回 typed failure，pending 不变。
	bola := h.approve(t, ownerContractOutsider, ownerContractMember, "oc-approve-bola")
	bolaBody := decodeGroupMembershipResponse(t, bola)
	if bola.Code < http.StatusBadRequest || bolaBody["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("non-moderator approve must fail typed: status=%d body=%#v", bola.Code, bolaBody)
	}
	pending := h.serve(t, http.MethodGet,
		"/circles/"+ownerContractCircleID+"/groups/"+ownerContractGroupID+"/memberships/self",
		"circle.circle_group_membership.GetMyCircleGroupMembership", ownerContractMember,
		"oc-approve-pending-readback", []string{"self"})
	if decodeGroupMembershipResponse(t, pending)["state"] != "pending" {
		t.Fatal("failed approve must keep the target membership pending")
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore {
		t.Fatal("failed approve must not commit receipt or outbox")
	}

	// t1：owner 审批一次成功，readback 收敛 active 与新 version。
	approved := h.approve(t, ownerContractOwner, ownerContractMember, "oc-approve-1")
	approvedBody := decodeGroupMembershipResponse(t, approved)
	if approved.Code != http.StatusOK || approvedBody["state"] != "active" {
		t.Fatalf("approve status=%d body=%#v", approved.Code, approvedBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("approve must commit exactly one receipt and one outbox event")
	}

	// t2：相同幂等键重放返回同一 membership/version，不重复推进。
	replay := h.approve(t, ownerContractOwner, ownerContractMember, "oc-approve-1")
	replayBody := decodeGroupMembershipResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["membershipId"] != approvedBody["membershipId"] ||
		replayBody["version"] != approvedBody["version"] {
		t.Fatalf("approve replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("approve replay must not append receipts or outbox events")
	}
}

func TestLeaveCircleGroupOwnerContract(t *testing.T) {
	h := newOwnerContractHarness(t, "circle_group_membership_owner_leave")
	if code := h.apply(t, ownerContractMember, "oc-leave-apply").Code; code != http.StatusCreated {
		t.Fatalf("seed apply status=%d", code)
	}
	if code := h.approve(t, ownerContractOwner, ownerContractMember, "oc-leave-approve").Code; code != http.StatusOK {
		t.Fatalf("seed approve status=%d", code)
	}
	receiptsBefore := h.count(t, "circle_group_membership_command_receipts")
	outboxBefore := h.count(t, "circle_group_membership_outbox")

	// t3：owner 不可离开，typed failure 且 owner state/receipt/outbox 无部分成功。
	ownerLeave := h.leave(t, ownerContractOwner, "oc-leave-owner")
	ownerLeaveBody := decodeGroupMembershipResponse(t, ownerLeave)
	if ownerLeave.Code < http.StatusBadRequest ||
		ownerLeaveBody["code"] != "CIRCLE.USER.group_membership_owner_cannot_leave" {
		t.Fatalf("owner leave must fail typed: status=%d body=%#v", ownerLeave.Code, ownerLeaveBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore {
		t.Fatal("failed owner leave must not commit receipt or outbox")
	}

	// t1：成员离开一次成功，readback 收敛 left 与新 version。
	left := h.leave(t, ownerContractMember, "oc-leave-1")
	leftBody := decodeGroupMembershipResponse(t, left)
	if left.Code != http.StatusOK || leftBody["state"] != "left" {
		t.Fatalf("leave status=%d body=%#v", left.Code, leftBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("leave must commit exactly one receipt and one outbox event")
	}

	// t2：相同幂等键重放返回同一 membership/version，不重复推进。
	replay := h.leave(t, ownerContractMember, "oc-leave-1")
	replayBody := decodeGroupMembershipResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["membershipId"] != leftBody["membershipId"] ||
		replayBody["version"] != leftBody["version"] {
		t.Fatalf("leave replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("leave replay must not append receipts or outbox events")
	}
}

func TestListCircleGroupMembershipsOwnerContract(t *testing.T) {
	h := newOwnerContractHarness(t, "circle_group_membership_owner_list")
	if code := h.apply(t, ownerContractMember, "oc-list-apply-1").Code; code != http.StatusCreated {
		t.Fatalf("seed apply status=%d", code)
	}
	if code := h.approve(t, ownerContractOwner, ownerContractMember, "oc-list-approve-1").Code; code != http.StatusOK {
		t.Fatalf("seed approve status=%d", code)
	}
	if code := h.apply(t, ownerContractOutsider, "oc-list-apply-2").Code; code != http.StatusCreated {
		t.Fatalf("seed apply status=%d", code)
	}
	if code := h.approve(t, ownerContractOwner, ownerContractOutsider, "oc-list-approve-2").Code; code != http.StatusOK {
		t.Fatalf("seed approve status=%d", code)
	}

	base := "/circles/" + ownerContractCircleID + "/groups/" + ownerContractGroupID + "/memberships"
	list := func(personaID, query, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodGet, base+query,
			"circle.circle_group_membership.ListCircleGroupMemberships", personaID, key, nil)
	}

	// t1：nonempty typed 公开 slice，不暴露 storage identity 或 decision actor。
	first := list(ownerContractOwner, "?state=active&limit=2", "oc-list-page1")
	if first.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", first.Code, first.Body.String())
	}
	firstBody := decodeGroupMembershipResponse(t, first)
	firstItems, _ := firstBody["items"].([]any)
	if len(firstItems) != 2 {
		t.Fatalf("first page must hold the page limit: %#v", firstBody)
	}
	allowedKeys := map[string]bool{
		"membershipId": true, "version": true, "groupId": true, "circleId": true,
		"personaId": true, "role": true, "state": true, "joinedAt": true,
		"leftAt": true, "decidedAt": true, "createdAt": true, "updatedAt": true,
	}
	for _, raw := range firstItems {
		item, _ := raw.(map[string]any)
		if item["membershipId"] == "" || item["state"] != "active" {
			t.Fatalf("page item must be a typed public slice: %#v", item)
		}
		for key := range item {
			if !allowedKeys[key] {
				t.Fatalf("public membership slice leaked non-public key %q: %#v", key, item)
			}
		}
	}

	// t2：cursor 分页稳定顺序、不重复、不漏项。
	cursor, _ := firstBody["nextCursor"].(string)
	if cursor == "" {
		if fallback, ok := firstBody["cursor"].(string); ok {
			cursor = fallback
		}
	}
	if cursor == "" {
		t.Fatalf("first page must expose the owner cursor: %#v", firstBody)
	}
	second := list(ownerContractOwner, "?state=active&limit=2&cursor="+cursor, "oc-list-page2")
	if second.Code != http.StatusOK {
		t.Fatalf("second page status=%d body=%s", second.Code, second.Body.String())
	}
	secondItems, _ := decodeGroupMembershipResponse(t, second)["items"].([]any)
	seen := map[string]bool{}
	for _, raw := range append(firstItems, secondItems...) {
		item, _ := raw.(map[string]any)
		id, _ := item["membershipId"].(string)
		if seen[id] {
			t.Fatalf("cursor pagination must not repeat membership %q", id)
		}
		seen[id] = true
	}
	if len(seen) != 3 {
		t.Fatalf("cursor pagination must not drop members: got %d of 3", len(seen))
	}

	// t3：无权枚举返回 canonical typed failure，不合成成功空页。
	denied := list("persona-oc-list-stranger", "?limit=20", "oc-list-denied")
	deniedBody := decodeGroupMembershipResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("non-member roster listing must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	if _, hasItems := deniedBody["items"]; hasItems {
		t.Fatal("denied listing must not synthesize an empty success page")
	}
}

func TestGetMyCircleGroupMembershipOwnerContract(t *testing.T) {
	h := newOwnerContractHarness(t, "circle_group_membership_owner_getmy")
	if code := h.apply(t, ownerContractMember, "oc-getmy-apply").Code; code != http.StatusCreated {
		t.Fatalf("seed apply status=%d", code)
	}
	base := "/circles/" + ownerContractCircleID + "/groups/" + ownerContractGroupID + "/memberships/self"
	getMy := func(personaID, query, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodGet, base+query,
			"circle.circle_group_membership.GetMyCircleGroupMembership", personaID, key, []string{"self"})
	}

	// t1：nonempty typed slice 与 owner readback 一致。
	mine := getMy(ownerContractMember, "", "oc-getmy-1")
	mineBody := decodeGroupMembershipResponse(t, mine)
	if mine.Code != http.StatusOK ||
		mineBody["personaId"] != ownerContractMember ||
		mineBody["groupId"] != ownerContractGroupID ||
		mineBody["circleId"] != ownerContractCircleID ||
		mineBody["state"] != "pending" {
		t.Fatalf("self membership slice must converge with owner readback: status=%d body=%#v", mine.Code, mineBody)
	}

	// t2：查询主体固定为认证 Persona，query 无法探测其他 Persona。
	probe := getMy(ownerContractMember, "?personaId="+ownerContractOwner, "oc-getmy-probe")
	probeBody := decodeGroupMembershipResponse(t, probe)
	if probe.Code != http.StatusOK || probeBody["personaId"] != ownerContractMember {
		t.Fatalf("self query must ignore foreign persona probes: status=%d body=%#v", probe.Code, probeBody)
	}

	// t3：membership 不存在返回 canonical typed failure，不合成"未加入"成功态。
	missing := getMy("persona-oc-getmy-stranger", "", "oc-getmy-missing")
	missingBody := decodeGroupMembershipResponse(t, missing)
	if missing.Code < http.StatusBadRequest ||
		missingBody["code"] != "CIRCLE.USER.group_membership_not_found" {
		t.Fatalf("missing membership must fail typed: status=%d body=%#v", missing.Code, missingBody)
	}
}

func TestRejectCircleGroupMemberOwnerContract(t *testing.T) {
	h := newOwnerContractHarness(t, "circle_group_membership_owner_reject")
	if code := h.apply(t, ownerContractMember, "oc-reject-apply").Code; code != http.StatusCreated {
		t.Fatalf("seed apply status=%d", code)
	}
	receiptsBefore := h.count(t, "circle_group_membership_command_receipts")
	outboxBefore := h.count(t, "circle_group_membership_outbox")
	reject := func(actorID, targetID, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodPost,
			"/circles/"+ownerContractCircleID+"/groups/"+ownerContractGroupID+"/memberships/"+targetID+":reject",
			"circle.circle_group_membership.RejectCircleGroupMember", actorID, key,
			[]string{targetID + ":reject"})
	}

	// t4（先证 BOLA 原子性）：非 owner/manager 拒绝返回 typed failure，无部分成功。
	bola := reject(ownerContractOutsider, ownerContractMember, "oc-reject-bola")
	bolaBody := decodeGroupMembershipResponse(t, bola)
	if bola.Code < http.StatusBadRequest || bolaBody["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("non-moderator reject must fail typed: status=%d body=%#v", bola.Code, bolaBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore {
		t.Fatal("failed reject must not commit receipt or outbox")
	}

	// t1+t2：owner 拒绝一次成功收敛 rejected 与新 version，且只提交一次。
	rejected := reject(ownerContractOwner, ownerContractMember, "oc-reject-1")
	rejectedBody := decodeGroupMembershipResponse(t, rejected)
	if rejected.Code != http.StatusOK || rejectedBody["state"] != "rejected" {
		t.Fatalf("reject status=%d body=%#v", rejected.Code, rejectedBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("reject must commit exactly one receipt and one outbox event")
	}

	// t3：相同幂等键重放返回同一身份，不重复推进。
	replay := reject(ownerContractOwner, ownerContractMember, "oc-reject-1")
	replayBody := decodeGroupMembershipResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["membershipId"] != rejectedBody["membershipId"] ||
		replayBody["version"] != rejectedBody["version"] {
		t.Fatalf("reject replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("reject replay must not append receipts or outbox events")
	}
}

func TestRemoveCircleGroupMemberOwnerContract(t *testing.T) {
	h := newOwnerContractHarness(t, "circle_group_membership_owner_remove")
	if code := h.apply(t, ownerContractMember, "oc-remove-apply").Code; code != http.StatusCreated {
		t.Fatalf("seed apply status=%d", code)
	}
	if code := h.approve(t, ownerContractOwner, ownerContractMember, "oc-remove-approve").Code; code != http.StatusOK {
		t.Fatalf("seed approve status=%d", code)
	}
	receiptsBefore := h.count(t, "circle_group_membership_command_receipts")
	outboxBefore := h.count(t, "circle_group_membership_outbox")
	remove := func(actorID, targetID, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodDelete,
			"/circles/"+ownerContractCircleID+"/groups/"+ownerContractGroupID+"/memberships/"+targetID,
			"circle.circle_group_membership.RemoveCircleGroupMember", actorID, key,
			[]string{targetID})
	}

	// t4：受保护 owner 不可被移除，typed failure 且无部分成功。
	protected := remove(ownerContractOwner, ownerContractOwner, "oc-remove-owner")
	protectedBody := decodeGroupMembershipResponse(t, protected)
	if protected.Code < http.StatusBadRequest ||
		protectedBody["code"] != "CIRCLE.USER.group_membership_owner_cannot_remove" {
		t.Fatalf("protected owner removal must fail typed: status=%d body=%#v", protected.Code, protectedBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore {
		t.Fatal("failed removal must not commit receipt or outbox")
	}

	// t1+t2：owner 移除一次成功收敛 removed 与新 version，且只提交一次。
	removed := remove(ownerContractOwner, ownerContractMember, "oc-remove-1")
	removedBody := decodeGroupMembershipResponse(t, removed)
	if removed.Code != http.StatusOK || removedBody["state"] != "removed" {
		t.Fatalf("remove status=%d body=%#v", removed.Code, removedBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("remove must commit exactly one receipt and one outbox event")
	}

	// t3：相同幂等键重放返回同一身份，不重复推进。
	replay := remove(ownerContractOwner, ownerContractMember, "oc-remove-1")
	replayBody := decodeGroupMembershipResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["membershipId"] != removedBody["membershipId"] ||
		replayBody["version"] != removedBody["version"] {
		t.Fatalf("remove replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("remove replay must not append receipts or outbox events")
	}
}

func TestUpdateCircleGroupMemberRoleOwnerContract(t *testing.T) {
	h := newOwnerContractHarness(t, "circle_group_membership_owner_role")
	if code := h.apply(t, ownerContractMember, "oc-role-apply").Code; code != http.StatusCreated {
		t.Fatalf("seed apply status=%d", code)
	}
	if code := h.approve(t, ownerContractOwner, ownerContractMember, "oc-role-approve").Code; code != http.StatusOK {
		t.Fatalf("seed approve status=%d", code)
	}
	receiptsBefore := h.count(t, "circle_group_membership_command_receipts")
	outboxBefore := h.count(t, "circle_group_membership_outbox")
	updateRole := func(actorID, targetID, role, key string) *httptest.ResponseRecorder {
		return h.serveBody(t, http.MethodPatch,
			"/circles/"+ownerContractCircleID+"/groups/"+ownerContractGroupID+"/memberships/"+targetID+"/role",
			map[string]any{"role": role},
			"circle.circle_group_membership.UpdateCircleGroupMemberRole", actorID, key,
			[]string{targetID, "role"})
	}

	// t4a：BOLA——非 owner 调整角色返回 typed failure。
	bola := updateRole(ownerContractOutsider, ownerContractMember, "manager", "oc-role-bola")
	bolaBody := decodeGroupMembershipResponse(t, bola)
	if bola.Code < http.StatusBadRequest || bolaBody["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("non-owner role change must fail typed: status=%d body=%#v", bola.Code, bolaBody)
	}

	// t4b：非法角色返回 typed failure，无部分成功。
	invalid := updateRole(ownerContractOwner, ownerContractMember, "superuser", "oc-role-invalid")
	invalidBody := decodeGroupMembershipResponse(t, invalid)
	if invalid.Code < http.StatusBadRequest || invalidBody["code"] == nil {
		t.Fatalf("invalid role must fail typed: status=%d body=%#v", invalid.Code, invalidBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore {
		t.Fatal("failed role change must not commit receipt or outbox")
	}

	// t1+t2：owner 调整角色一次成功收敛新 role 与 version，且只提交一次。
	changed := updateRole(ownerContractOwner, ownerContractMember, "manager", "oc-role-1")
	changedBody := decodeGroupMembershipResponse(t, changed)
	if changed.Code != http.StatusOK || changedBody["role"] != "manager" {
		t.Fatalf("role change status=%d body=%#v", changed.Code, changedBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("role change must commit exactly one receipt and one outbox event")
	}

	// t3：相同幂等键重放返回同一身份，不重复推进。
	replay := updateRole(ownerContractOwner, ownerContractMember, "manager", "oc-role-1")
	replayBody := decodeGroupMembershipResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["membershipId"] != changedBody["membershipId"] ||
		replayBody["version"] != changedBody["version"] {
		t.Fatalf("role replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_group_membership_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_membership_outbox") != outboxBefore+1 {
		t.Fatal("role replay must not append receipts or outbox events")
	}
}
