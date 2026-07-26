package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
)

// 本文件覆盖群成员治理的授权矩阵与生命周期负例（metadata 声明的
// ownership_policy 必须由服务端强制执行，而不是只写在契约里）：
//   - AddMembers: 操作者必须是活跃成员；新成员互关/拉黑 gate；上限 group_full
//   - RemoveMember: 仅 owner/admin；owner 不可被移除；admin 不可移除 admin；禁止 self-remove
//   - LeaveConversation: 成员可退；owner 必须先转让；direct 不可退
//   - dissolved 终态: 成员命令返回 conversation_dissolved

func errorCodeOf(t *testing.T, body map[string]any) string {
	t.Helper()
	if code, ok := body["code"].(string); ok {
		return code
	}
	if nested, ok := body["error"].(map[string]any); ok {
		if code, ok := nested["code"].(string); ok {
			return code
		}
	}
	t.Fatalf("response has no error code: %v", body)
	return ""
}

func inboxContainsConversation(t *testing.T, body map[string]any, conversationID string) bool {
	t.Helper()
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("inbox response missing items: %v", body)
	}
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("inbox item is not an object: %v", raw)
		}
		if item["id"] == conversationID {
			return true
		}
	}
	return false
}

// postExpectingError 与 doPost 同源，但不对状态码 fatal（负例断言用）。
func postExpectingError(t *testing.T, path, payload, userId string) (int, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", userId)
	req.Header.Set("X-Client-Account-Id", userId)
	req.Header.Set("X-Client-Sub-Account-Id", userId)
	req.Header.Set("X-Client-Persona-Id", userId)
	req = commandOperationContext(req, path, userId)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	drainAggregateOutboxRelays(t, path)
	var result map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &result)
	return rec.Code, result
}

// TestAddMembers_NonMemberRejected：非群成员加人必须被拒（信息隐藏为 not_found）。
func TestAddMembers_NonMemberRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"authz add"}`)
	convId := conv["id"].(string)

	code, body := postExpectingError(
		t,
		"/chat/conversations/"+convId+"/members",
		`{"userIds":["user_x"]}`,
		"user_outsider_999",
	)
	if code != http.StatusNotFound {
		t.Fatalf("expected 404 for non-member AddMembers, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.conversation_not_found" {
		t.Fatalf("expected conversation_not_found, got %s", got)
	}
}

// TestAddMembers_NotMutualRejected：新成员必须与操作者互关。
func TestAddMembers_NotMutualRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"authz mutual"}`)
	convId := conv["id"].(string)

	code, body := postExpectingError(
		t,
		"/chat/conversations/"+convId+"/members",
		`{"userIds":["user_not_mutual_target"]}`,
		"user_test_001",
	)
	if code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-mutual invitee, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.group_member_not_mutual" {
		t.Fatalf("expected group_member_not_mutual, got %s", got)
	}
}

// TestAddMembers_BlockedRejected：存在拉黑关系的目标不可入群。
func TestAddMembers_BlockedRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"authz blocked"}`)
	convId := conv["id"].(string)

	code, body := postExpectingError(
		t,
		"/chat/conversations/"+convId+"/members",
		`{"userIds":["user_blocked_target"]}`,
		"user_test_001",
	)
	if code != http.StatusForbidden {
		t.Fatalf("expected 403 for blocked invitee, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.group_member_blocked" {
		t.Fatalf("expected group_member_blocked, got %s", got)
	}
}

// TestAddMembers_GroupFull：超出 maxGroupSize 返回专属错误码。
func TestAddMembers_GroupFull(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"authz full","maxGroupSize":2,"initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	code, body := postExpectingError(
		t,
		"/chat/conversations/"+convId+"/members",
		`{"userIds":["user_c"]}`,
		"user_test_001",
	)
	if code != http.StatusBadRequest {
		t.Fatalf("expected 400 for group_full, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.group_full" {
		t.Fatalf("expected group_full, got %s", got)
	}
}

func TestAddMembers_AssistantDoesNotConsumeUserCapacity(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(
		t,
		`{"type":"group","title":"assistant capacity","maxGroupSize":2}`,
	)
	convID := conv["id"].(string)
	if _, err := requireMongoDB(t).Collection("conversation_memberships").InsertOne(
		context.Background(),
		bson.M{
			"_id":            "assistant-capacity-membership",
			"conversationId": convID,
			"userId":         "assistant-capacity-member",
			"displayName":    "小趣",
			"role":           "member",
			"memberType":     "assistant",
			"joinedAt":       time.Now().UTC(),
		},
	); err != nil {
		t.Fatalf("insert assistant membership: %v", err)
	}

	doPost(
		t,
		"/chat/conversations/"+convID+"/members",
		`{"userIds":["user_b"]}`,
		"user_test_001",
		http.StatusOK,
	)
	count, err := requireMongoDB(t).Collection("conversation_memberships").
		CountDocuments(context.Background(), bson.M{"conversationId": convID})
	if err != nil {
		t.Fatalf("count memberships: %v", err)
	}
	if count != 3 {
		t.Fatalf("assistant plus two users should coexist, memberships=%d", count)
	}
}

// TestRemoveMember_RegularMemberRejected：普通成员不能移出他人。
func TestRemoveMember_RegularMemberRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"authz remove","initialMemberIds":["user_b","user_c"]}`)
	convId := conv["id"].(string)

	code, body := doDelete(t, "/chat/conversations/"+convId+"/members/user_c", "user_b")
	if code != http.StatusForbidden {
		t.Fatalf("expected 403 for member removing member, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.group_governance_forbidden" {
		t.Fatalf("expected group_governance_forbidden, got %s", got)
	}
}

// TestRemoveMember_OwnerCannotBeRemoved：任何人不能移出群主。
func TestRemoveMember_OwnerCannotBeRemoved(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"authz owner","initialMemberIds":["user_admin_b"]}`)
	convId := conv["id"].(string)
	setGroupAdmins(t, convId, "user_test_001", `{"adminIds":["user_admin_b"]}`)

	code, body := doDelete(t, "/chat/conversations/"+convId+"/members/user_test_001", "user_admin_b")
	if code != http.StatusForbidden {
		t.Fatalf("expected 403 removing owner, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.group_governance_forbidden" {
		t.Fatalf("expected group_governance_forbidden, got %s", got)
	}
}

// TestRemoveMember_AdminCannotRemoveAdmin：管理员只能移出普通成员。
func TestRemoveMember_AdminCannotRemoveAdmin(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"authz admins","initialMemberIds":["user_admin_b","user_admin_c","user_d"]}`)
	convId := conv["id"].(string)
	setGroupAdmins(t, convId, "user_test_001", `{"adminIds":["user_admin_b","user_admin_c"]}`)

	code, body := doDelete(t, "/chat/conversations/"+convId+"/members/user_admin_c", "user_admin_b")
	if code != http.StatusForbidden {
		t.Fatalf("expected 403 admin removing admin, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.group_governance_forbidden" {
		t.Fatalf("expected group_governance_forbidden, got %s", got)
	}

	// 管理员移出普通成员是允许的。
	code, body = doDelete(t, "/chat/conversations/"+convId+"/members/user_d", "user_admin_b")
	if code != http.StatusOK {
		t.Fatalf("expected 200 admin removing regular member, got %d: %v", code, body)
	}
}

// TestRemoveMember_SelfRemovalRedirectsToLeave：自愿退出必须走 LeaveConversation。
func TestRemoveMember_SelfRemovalRedirectsToLeave(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"authz self","initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	code, body := doDelete(t, "/chat/conversations/"+convId+"/members/user_test_001", "user_test_001")
	if code != http.StatusBadRequest {
		t.Fatalf("expected 400 for self removal, got %d: %v", code, body)
	}
}

// TestLeaveConversation_MemberLeaves：普通成员退群成功且 roster 收敛。
func TestLeaveConversation_MemberLeaves(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"leave ok","initialMemberIds":["user_b","user_c"]}`)
	convId := conv["id"].(string)

	doPost(t, "/chat/conversations/"+convId+"/leave", `{}`, "user_b", http.StatusOK)

	code, result := doGet(t, "/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
	if code != http.StatusOK {
		t.Fatalf("list members after leave: %d", code)
	}
	for _, uid := range memberItemsUserIDs(t, result["items"].([]any)) {
		if uid == "user_b" {
			t.Fatal("user_b should have left the conversation")
		}
	}

	// 重复退出为 no-op（幂等回执）。
	doPost(t, "/chat/conversations/"+convId+"/leave", `{}`, "user_b", http.StatusOK)
}

// TestTerminalMembershipStateCleanup prevents removed/left users from retaining
// a private inbox row or recreating it via settings after their membership ends.
func TestTerminalMembershipStateCleanup(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	removedConv := createConversation(
		t,
		`{"type":"group","title":"removed inbox cleanup","initialMemberIds":["user_removed"]}`,
	)
	removedID := removedConv["id"].(string)
	_, beforeRemoval := doGet(t, "/chat/inbox?limit=50", "user_removed")
	if !inboxContainsConversation(t, beforeRemoval, removedID) {
		t.Fatal("new member must have an inbox row before removal")
	}

	if code, body := doDelete(
		t,
		"/chat/conversations/"+removedID+"/members/user_removed",
		"user_test_001",
	); code != http.StatusOK {
		t.Fatalf("remove member: %d %v", code, body)
	}
	_, afterRemoval := doGet(t, "/chat/inbox?limit=50", "user_removed")
	if inboxContainsConversation(t, afterRemoval, removedID) {
		t.Fatal("removed user must lose the inbox row in the membership transaction")
	}
	code, body := doPatch(
		t,
		"/chat/conversations/"+removedID+"/settings",
		`{"pinned":true}`,
		"user_removed",
	)
	if code != http.StatusNotFound || errorCodeOf(t, body) != "CHAT.USER.conversation_not_found" {
		t.Fatalf("removed user settings must be hidden as not found: %d %v", code, body)
	}
	_, afterDeniedSettings := doGet(t, "/chat/inbox?limit=50", "user_removed")
	if inboxContainsConversation(t, afterDeniedSettings, removedID) {
		t.Fatal("rejected settings command must not recreate removed user's inbox row")
	}

	leftConv := createConversation(
		t,
		`{"type":"group","title":"left inbox cleanup","initialMemberIds":["user_left"]}`,
	)
	leftID := leftConv["id"].(string)
	_, beforeLeave := doGet(t, "/chat/inbox?limit=50", "user_left")
	if !inboxContainsConversation(t, beforeLeave, leftID) {
		t.Fatal("new member must have an inbox row before leave")
	}
	doPost(t, "/chat/conversations/"+leftID+"/leave", `{}`, "user_left", http.StatusOK)

	// A MessageSent event committed before leave may reach the inbox projector
	// afterwards. Its deleted state is terminal, so this must remain a no-op.
	store := persistence.NewMongoChatStore(mongoDB)
	if err := store.AdvanceInboxUnread(
		context.Background(),
		"user_left",
		leftID,
		999,
		1,
		1,
		time.Now().UTC(),
	); err != nil {
		t.Fatalf("late inbox projection after leave must be no-op: %v", err)
	}
	_, afterLeave := doGet(t, "/chat/inbox?limit=50", "user_left")
	if inboxContainsConversation(t, afterLeave, leftID) {
		t.Fatal("left user must not regain an inbox row from a delayed projection")
	}
}

// TestLeaveConversation_OwnerMustTransferFirst：群主退群前必须转让。
func TestLeaveConversation_OwnerMustTransferFirst(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"leave owner","initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	code, body := postExpectingError(t, "/chat/conversations/"+convId+"/leave", `{}`, "user_test_001")
	if code != http.StatusConflict {
		t.Fatalf("expected 409 for owner leave, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.group_owner_must_transfer_before_leave" {
		t.Fatalf("expected group_owner_must_transfer_before_leave, got %s", got)
	}

	// 转让后可退。
	code, _ = doPatch(t, "/chat/conversations/"+convId+"/owner", `{"newOwnerId":"user_b"}`, "user_test_001")
	if code != http.StatusOK {
		t.Fatalf("transfer ownership: %d", code)
	}
	doPost(t, "/chat/conversations/"+convId+"/leave", `{}`, "user_test_001", http.StatusOK)
}

// TestLeaveConversation_DirectRejected：1v1 会话不支持退出。
func TestLeaveConversation_DirectRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	code, body := postExpectingError(t, "/chat/conversations/"+convId+"/leave", `{}`, "user_test_001")
	if code != http.StatusBadRequest {
		t.Fatalf("expected 400 for direct leave, got %d: %v", code, body)
	}
}

// TestDissolvedConversation_MembershipCommandsRejected：解散终态语义。
func TestDissolvedConversation_MembershipCommandsRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"dissolve target","initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	code, _ := doDelete(t, "/chat/conversations/"+convId, "user_test_001")
	if code != http.StatusOK {
		t.Fatalf("dissolve: %d", code)
	}

	// 解散后详情 status 必须是 dissolved（单轨状态）。
	code, detail := doGet(t, "/chat/conversations/"+convId, "user_test_001")
	if code != http.StatusOK {
		t.Fatalf("get dissolved conversation: %d", code)
	}
	if status, _ := detail["status"].(string); status != "dissolved" {
		t.Fatalf("expected status dissolved, got %q", detail["status"])
	}

	code, body := postExpectingError(
		t,
		"/chat/conversations/"+convId+"/members",
		`{"userIds":["user_c"]}`,
		"user_test_001",
	)
	if code != http.StatusConflict {
		t.Fatalf("expected 409 on dissolved AddMembers, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.conversation_dissolved" {
		t.Fatalf("expected conversation_dissolved, got %s", got)
	}

	code, body = postExpectingError(t, "/chat/conversations/"+convId+"/leave", `{}`, "user_b")
	if code != http.StatusConflict {
		t.Fatalf("expected 409 on dissolved leave, got %d: %v", code, body)
	}
}

func setGroupAdmins(t *testing.T, convId, operator, payload string) {
	t.Helper()
	code, body := doPut(t, "/chat/conversations/"+convId+"/admins", payload, operator)
	if code != http.StatusOK {
		t.Fatalf("set group admins: %d: %v", code, body)
	}
}
