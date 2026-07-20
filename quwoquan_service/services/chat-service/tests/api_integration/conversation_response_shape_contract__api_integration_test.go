package api_integration

import "testing"

func TestConversation_ResponseShape_HasRequiredFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"response shape"}`)

	requiredFields := []string{
		"id", "type", "title", "status", "createdAt", "updatedAt",
		"maxSeq", "memberCount", "maxGroupSize", "receiptEnabled",
	}
	for _, field := range requiredFields {
		if _, ok := conv[field]; !ok {
			t.Errorf("response missing required field: %s", field)
		}
	}
	// 契约单轨：wire 只认业务键 id，不暴露存储 _id。
	if _, exists := conv["_id"]; exists {
		t.Fatal("conversation response must not expose storage _id")
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

	conv := createConversation(t, `{"type":"direct","title":"message response","initialMemberIds":["user_test_002"]}`)
	convID := conv["id"].(string)

	sendMessage(t, convID, `{"type":"text","content":"hi","clientMsgId":"response-shape-uuid-1"}`)

	code, result := doGet(t, "/chat/conversations/"+convID+"/messages?limit=1", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}

	items, ok := result["items"].([]any)
	if !ok || len(items) == 0 {
		t.Fatal("expected at least 1 message")
	}
	msg, _ := items[0].(map[string]any)

	requiredMsgFields := []string{
		"id", "conversationId", "seq", "clientMsgId", "senderId",
		"type", "status", "timestamp",
	}
	for _, field := range requiredMsgFields {
		if _, ok := msg[field]; !ok {
			t.Errorf("message response missing required field: %s", field)
		}
	}
	if _, exists := msg["_id"]; exists {
		t.Fatal("message response must not expose removed _id alias")
	}
}
