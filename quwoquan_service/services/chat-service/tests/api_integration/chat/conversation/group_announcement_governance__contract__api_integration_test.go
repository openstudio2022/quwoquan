// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: list-conversation-timestamps-api
// readiness_case: batch-get-conversations-api
// readiness_case: update-conversation-title-api
// readiness_case: update-announcement-api
// readiness_case: update-group-governance-settings-api
// readiness_case: get-group-home-api
package api_integration

import (
	"net/http"
	"strings"
	"testing"
)

// 本文件覆盖群公告与群治理开关的权威对象链：
//   - UpdateAnnouncement: owner/admin 可发布；GroupHome 回读真实字段；
//     发布产生一条 type=system_announcement 会话消息（公告即触达）；
//     普通成员发布被拒。
//   - UpdateGroupGovernanceSettings: nameEditableByAdminOnly 持久化回读；
//     开启后普通成员改名被拒、owner 改名放行。

func patchExpectingStatus(t *testing.T, path, payload, userId string, want int) map[string]any {
	t.Helper()
	code, body := doPatch(t, path, payload, userId)
	if code != want {
		t.Fatalf("PATCH %s: expected %d, got %d: %v", path, want, code, body)
	}
	return body
}

// TestUpdateAnnouncement_OwnerPublishesAndReaches：公告写入、回读、消息触达闭环。
func TestUpdateAnnouncement_OwnerPublishesAndReaches(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"announcement e2e","initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	body := patchExpectingStatus(
		t,
		"/chat/conversations/"+convId+"/announcement",
		`{"announcement":"周六线下面基，老地方集合"}`,
		"user_test_001",
		http.StatusOK,
	)
	if got, _ := body["announcement"].(string); got != "周六线下面基，老地方集合" {
		t.Fatalf("announcement not persisted on conversation wire: %v", body["announcement"])
	}
	if got, _ := body["announcementUpdatedBy"].(string); got != "user_test_001" {
		t.Fatalf("announcementUpdatedBy mismatch: %v", body["announcementUpdatedBy"])
	}

	// GroupHome 投影消费同一权威字段（此前为硬编码空串的假实现）。
	code, home := doGet(t, "/chat/groups/"+convId+"/home", "user_b")
	if code != http.StatusOK {
		t.Fatalf("get group home: %d", code)
	}
	if got, _ := home["announcement"].(string); got != "周六线下面基，老地方集合" {
		t.Fatalf("group home announcement mismatch: %v", home["announcement"])
	}

	// 公告即触达：会话内出现一条 system_announcement 消息。
	code, msgs := doGet(t, "/chat/conversations/"+convId+"/messages?limit=20", "user_b")
	if code != http.StatusOK {
		t.Fatalf("list messages: %d", code)
	}
	items, _ := msgs["items"].([]any)
	foundSystemAnnouncement := false
	for _, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			continue
		}
		if m["type"] == "system_announcement" &&
			strings.Contains(m["content"].(string), "周六线下面基") {
			foundSystemAnnouncement = true
			break
		}
	}
	if !foundSystemAnnouncement {
		t.Fatalf("expected a system_announcement message after publishing, got %v", items)
	}
}

// TestUpdateAnnouncement_RegularMemberRejected：普通成员不能发布公告。
func TestUpdateAnnouncement_RegularMemberRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"announcement authz","initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	code, body := doPatch(
		t,
		"/chat/conversations/"+convId+"/announcement",
		`{"announcement":"我不该有权限"}`,
		"user_b",
	)
	if code != http.StatusForbidden {
		t.Fatalf("expected 403 for regular member announcement, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.group_governance_forbidden" {
		t.Fatalf("expected group_governance_forbidden, got %s", got)
	}
}

// TestGovernanceSettings_NameEditRestriction：治理开关真实生效链。
func TestGovernanceSettings_NameEditRestriction(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"governance e2e","initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	// 默认关闭：普通成员可以改名。
	code, _ := doPatch(t, "/chat/conversations/"+convId, `{"title":"成员改的名"}`, "user_b")
	if code != http.StatusOK {
		t.Fatalf("member rename with governance off: %d", code)
	}

	// owner 开启仅管理员改名。
	body := patchExpectingStatus(
		t,
		"/chat/conversations/"+convId+"/governance",
		`{"nameEditableByAdminOnly":true}`,
		"user_test_001",
		http.StatusOK,
	)
	if got, _ := body["nameEditableByAdminOnly"].(bool); !got {
		t.Fatalf("nameEditableByAdminOnly not persisted: %v", body["nameEditableByAdminOnly"])
	}

	// 回读详情验证持久化（GetConversation 是群设置页唯一事实源）。
	code, detail := doGet(t, "/chat/conversations/"+convId, "user_test_001")
	if code != http.StatusOK {
		t.Fatalf("get conversation: %d", code)
	}
	if got, _ := detail["nameEditableByAdminOnly"].(bool); !got {
		t.Fatalf("nameEditableByAdminOnly not readable on detail: %v", detail["nameEditableByAdminOnly"])
	}

	// 开启后普通成员改名被拒。
	code, renameBody := doPatch(t, "/chat/conversations/"+convId, `{"title":"成员又改名"}`, "user_b")
	if code != http.StatusForbidden {
		t.Fatalf("expected 403 member rename with governance on, got %d: %v", code, renameBody)
	}
	if got := errorCodeOf(t, renameBody); got != "CHAT.USER.group_governance_forbidden" {
		t.Fatalf("expected group_governance_forbidden, got %s", got)
	}

	// owner 改名放行。
	code, _ = doPatch(t, "/chat/conversations/"+convId, `{"title":"群主改的名"}`, "user_test_001")
	if code != http.StatusOK {
		t.Fatalf("owner rename with governance on: %d", code)
	}
}

// TestGovernanceSettings_RegularMemberRejected：普通成员不能改治理开关。
func TestGovernanceSettings_RegularMemberRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"governance authz","initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	code, body := doPatch(
		t,
		"/chat/conversations/"+convId+"/governance",
		`{"nameEditableByAdminOnly":true}`,
		"user_b",
	)
	if code != http.StatusForbidden {
		t.Fatalf("expected 403 for member governance update, got %d: %v", code, body)
	}
	if got := errorCodeOf(t, body); got != "CHAT.USER.group_governance_forbidden" {
		t.Fatalf("expected group_governance_forbidden, got %s", got)
	}
}

// TestConversationTimestampsAndBatch：既声明即实现（此前为声明未实现悬挂 operation）。
func TestConversationTimestampsAndBatch(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"ts batch","initialMemberIds":["user_b"]}`)
	convId := conv["id"].(string)

	code, ts := doGet(t, "/chat/conversations/timestamps", "user_test_001")
	if code != http.StatusOK {
		t.Fatalf("list conversation timestamps: %d", code)
	}
	rows, _ := ts["items"].([]any)
	foundTs := false
	for _, it := range rows {
		if m, ok := it.(map[string]any); ok && m["conversationId"] == convId {
			foundTs = true
			if _, hasUpdated := m["updatedAt"]; !hasUpdated {
				t.Fatal("timestamp row missing updatedAt")
			}
		}
	}
	if !foundTs {
		t.Fatalf("timestamps missing conversation %s: %v", convId, rows)
	}

	// batch：成员可见，非成员不可见（conversation_member ownership）。
	body := doPost(t, "/chat/conversations/batch", `{"ids":["`+convId+`"]}`, "user_b", http.StatusOK)
	items, _ := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("member batch lookup expected 1 item, got %d", len(items))
	}
	outsider := doPost(t, "/chat/conversations/batch", `{"ids":["`+convId+`"]}`, "user_outsider_999", http.StatusOK)
	outsiderItems, _ := outsider["items"].([]any)
	if len(outsiderItems) != 0 {
		t.Fatalf("non-member batch lookup must be empty, got %v", outsiderItems)
	}
}
