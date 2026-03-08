package tests

import (
	"testing"
)

func TestUpdateConversationSettings_Mute(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"settings test"}`)
	convId := conv["_id"].(string)

	code, result := doPatch(t, "/v1/chat/conversations/"+convId+"/settings",
		`{"muted":true}`, "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	if result["status"] != "ok" {
		t.Errorf("expected status=ok, got %v", result["status"])
	}
}

func TestUpdateConversationSettings_Pin(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"pin test"}`)
	convId := conv["_id"].(string)

	code, _ := doPatch(t, "/v1/chat/conversations/"+convId+"/settings",
		`{"pinned":true}`, "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
}

func TestMarkAsRead(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"read test"}`)
	convId := conv["_id"].(string)

	msg := sendMessage(t, convId, `{"type":"text","content":"unread msg","clientMsgId":"read-uuid-1"}`)
	msgId := msg["messageId"].(string)

	result := doPost(t, "/v1/chat/conversations/"+convId+"/messages/"+msgId+"/read",
		`{}`, "user_test_001", 200)

	if result["status"] != "ok" {
		t.Errorf("expected status=ok, got %v", result["status"])
	}
}

func TestGetReceipts(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"receipt test","maxGroupSize":10}`)
	convId := conv["_id"].(string)

	msg := sendMessage(t, convId, `{"type":"text","content":"receipt msg","clientMsgId":"receipt-uuid-1"}`)
	msgId := msg["messageId"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/messages/"+msgId+"/read",
		`{}`, "user_test_001", 200)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/messages/"+msgId+"/receipts", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	if result["items"] == nil {
		t.Error("response missing items")
	}
}
