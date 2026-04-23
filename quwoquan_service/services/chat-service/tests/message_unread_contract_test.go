package tests

import (
	"net/http"
	"testing"
)

func TestMarkAsRead_UnreadCountCorrectlyDecremented(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"unread test"}`)
	convId := conv["_id"].(string)

	sendMessageAs(t, "user_sender", convId, `{"type":"text","content":"msg1","clientMsgId":"unread-1"}`)
	sendMessageAs(t, "user_sender", convId, `{"type":"text","content":"msg2","clientMsgId":"unread-2"}`)
	msg3 := sendMessageAs(t, "user_sender", convId, `{"type":"text","content":"msg3","clientMsgId":"unread-3"}`)
	sendMessageAs(t, "user_sender", convId, `{"type":"text","content":"msg4","clientMsgId":"unread-4"}`)
	msg5 := sendMessageAs(t, "user_sender", convId, `{"type":"text","content":"msg5","clientMsgId":"unread-5"}`)

	msg3Id := msg3["messageId"].(string)
	msg5Id := msg5["messageId"].(string)

	// Mark msg3 as read by user_test_001 → should have unreadCount = maxSeq - msg3.seq
	doPost(t, "/v1/chat/conversations/"+convId+"/messages/"+msg3Id+"/read", `{}`, "user_test_001", http.StatusOK)

	code, inbox := doGet(t, "/v1/chat/inbox?limit=50", "user_test_001")
	if code != http.StatusOK {
		t.Fatalf("inbox GET: expected 200, got %d", code)
	}
	items, ok := inbox["items"].([]any)
	if !ok || len(items) == 0 {
		t.Fatalf("inbox returned no items")
	}

	found := false
	for _, item := range items {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		itemConvId, _ := m["conversationId"].(string)
		if itemConvId != convId {
			continue
		}
		found = true
		unread, _ := m["unreadCount"].(float64)
		// maxSeq=5 (owner msg at seq 0 doesn't exist, 5 messages sent = seq 1..5)
		// marked msg3 read (seq=3) → unread = maxSeq(5) - 3 = 2
		if int(unread) != 2 {
			t.Errorf("expected unreadCount=2 after marking msg3 read (maxSeq=5), got %.0f", unread)
		}
		break
	}
	if !found {
		t.Error("conversation not found in inbox")
	}

	// Mark msg5 as read → unreadCount should be 0
	doPost(t, "/v1/chat/conversations/"+convId+"/messages/"+msg5Id+"/read", `{}`, "user_test_001", http.StatusOK)

	code2, inbox2 := doGet(t, "/v1/chat/inbox?limit=50", "user_test_001")
	if code2 != http.StatusOK {
		t.Fatalf("inbox GET: expected 200, got %d", code2)
	}
	items2, _ := inbox2["items"].([]any)
	for _, item := range items2 {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		itemConvId, _ := m["conversationId"].(string)
		if itemConvId != convId {
			continue
		}
		unread, _ := m["unreadCount"].(float64)
		if int(unread) != 0 {
			t.Errorf("expected unreadCount=0 after marking last msg read, got %.0f", unread)
		}
		break
	}
}

func TestMarkAsRead_IdempotentOnSameMessage(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"idempotent read"}`)
	convId := conv["_id"].(string)

	msg := sendMessage(t, convId, `{"type":"text","content":"hello","clientMsgId":"idem-read-1"}`)
	msgId := msg["messageId"].(string)

	doPost(t, "/v1/chat/conversations/"+convId+"/messages/"+msgId+"/read", `{}`, "user_test_001", http.StatusOK)
	doPost(t, "/v1/chat/conversations/"+convId+"/messages/"+msgId+"/read", `{}`, "user_test_001", http.StatusOK)
}
