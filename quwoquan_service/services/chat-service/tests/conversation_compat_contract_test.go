package tests

import (
	"testing"
)

func TestConversation_ResponseShape_HasRequiredFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"compat test"}`)

	requiredFields := []string{
		"_id", "type", "title", "status", "createdAt", "updatedAt",
		"maxSeq", "memberCount", "maxGroupSize", "receiptEnabled",
	}
	for _, field := range requiredFields {
		if _, ok := conv[field]; !ok {
			t.Errorf("response missing required field: %s", field)
		}
	}
}

func TestConversation_ResponseShape_NoInternalFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"internal fields test"}`)

	internalFields := []string{"__v", "_class", "deletedAt"}
	for _, field := range internalFields {
		if _, ok := conv[field]; ok {
			t.Errorf("response should not expose internal field: %s", field)
		}
	}
}

func TestMessage_ResponseShape_HasRequiredFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"msg compat"}`)
	convId := conv["_id"].(string)

	sendMessage(t, convId, `{"type":"text","content":"hi","clientMsgId":"compat-uuid-1"}`)

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/messages?limit=1", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}

	items, ok := result["items"].([]any)
	if !ok || len(items) == 0 {
		t.Fatal("expected at least 1 message")
	}
	msg, _ := items[0].(map[string]any)

	requiredMsgFields := []string{
		"_id", "conversationId", "seq", "clientMsgId", "senderId",
		"type", "status", "timestamp",
	}
	for _, field := range requiredMsgFields {
		if _, ok := msg[field]; !ok {
			t.Errorf("message response missing required field: %s", field)
		}
	}
}
