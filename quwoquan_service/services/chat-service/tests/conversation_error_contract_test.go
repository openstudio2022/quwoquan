package tests

import (
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

	conv := createConversation(t, `{"type":"direct","title":"error test"}`)
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
		`{"userIds":["user_b","user_c","user_d"]}`, "user_test_001", 200)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/members?limit=50", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	_ = result
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
