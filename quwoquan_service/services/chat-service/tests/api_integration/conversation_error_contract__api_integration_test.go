package api_integration

import (
	"net/http"
	"testing"
)

func TestConversation_NotFound_Returns404(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, _ := doGet(t, "/v1/chat/conversations/nonexistent_conv_id_12345", "user_test_001")
	if code != 404 {
		t.Fatalf("expected 404 for non-existent conversation, got %d", code)
	}
}

func TestSendMessage_InvalidBody_Returns400(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"error test","initialMemberIds":["user_test_002"]}`)
	convId := conv["_id"].(string)

	req := doPost(t, "/v1/chat/conversations/"+convId+"/messages",
		`{invalid json`, "user_test_001", 400)
	_ = req
}

func TestAddMembers_ExceedsMaxGroupSize(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"max size test","maxGroupSize":2}`)
	convId := conv["_id"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/members",
		`{"userIds":["user_b","user_c","user_d"]}`, "user_test_001", http.StatusBadRequest)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
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

func TestListContacts_Empty(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, result := doGet(t, "/v1/chat/contacts", "user_test_001")
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

	code, result := doGet(t, "/v1/chat/group-candidates?limit=20", "user_test_001")
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

func TestSearchContacts_Empty(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, result := doGet(t, "/v1/chat/contacts/search?q=test", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	if result["items"] == nil {
		t.Error("response missing items")
	}
}
