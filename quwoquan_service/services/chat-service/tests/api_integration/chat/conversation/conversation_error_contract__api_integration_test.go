package api_integration

import (
	"net/http"
	"testing"
)

func TestConversation_NotFound_Returns404(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, _ := doGet(t, "/chat/conversations/nonexistent_conv_id_12345", "user_test_001")
	if code != 404 {
		t.Fatalf("expected 404 for non-existent conversation, got %d", code)
	}
}

func TestSendMessage_InvalidBody_Returns400(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"error test","initialMemberIds":["user_test_002"]}`)
	convId := conv["id"].(string)

	req := doPost(t, "/chat/conversations/"+convId+"/messages",
		`{invalid json`, "user_test_001", 400)
	_ = req
}

func TestAddMembers_ExceedsMaxGroupSize(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"max size test","maxGroupSize":2}`)
	convId := conv["id"].(string)

	doPost(t, "/chat/conversations/"+convId+"/members",
		`{"userIds":["user_b","user_c","user_d"]}`, "user_test_001", http.StatusBadRequest)

	code, result := doGet(t, "/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatalf("response missing items: %+v", result)
	}
	if len(items) != 1 {
		t.Fatalf("超限请求不得产生部分成员写入，got %d members: %+v", len(items), items)
	}
}

func TestCreateConversation_GroupSizePolicyIsSingleTrack(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	group := createConversation(t, `{"type":"group","title":"default capacity"}`)
	if group["maxGroupSize"] != float64(1000) {
		t.Fatalf("group default maxGroupSize=%v want=1000", group["maxGroupSize"])
	}
	direct := createConversation(
		t,
		`{"type":"direct","title":"direct capacity","maxGroupSize":1000,"initialMemberIds":["user_test_002"]}`,
	)
	if direct["maxGroupSize"] != float64(2) {
		t.Fatalf("direct maxGroupSize=%v want=2", direct["maxGroupSize"])
	}

	status, body := postExpectingError(
		t,
		"/chat/conversations",
		`{"type":"group","title":"oversized","maxGroupSize":1001}`,
		"user_test_001",
	)
	if status != http.StatusBadRequest {
		t.Fatalf("oversized group status=%d body=%#v", status, body)
	}
	if code := errorCodeOf(t, body); code != "CHAT.USER.group_full" {
		t.Fatalf("oversized group code=%s want=CHAT.USER.group_full", code)
	}
}

func TestListContacts_Empty(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, result := doGet(t, "/chat/contacts", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items")
	}
	_ = items
}

func TestListGroupCandidates_Empty(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, result := doGet(t, "/chat/group-candidates?limit=20", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items")
	}
	if len(items) != 0 {
		t.Fatalf("expected empty candidates without social source, got %d", len(items))
	}
}

func TestSearchContacts_RouteRemovedWithLocalOnlySearch(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	// chat 云侧搜索已随本地检索单轨裁决删除；路由必须不可用（404 未注册
	// 或 400 被 operation guard 拒绝，都证明云侧搜索无入口）。
	code, _ := doGet(t, "/chat/contacts/search?q=test", "user_test_001")
	if code < 400 {
		t.Fatalf("removed search route must not serve requests, got %d", code)
	}
}
