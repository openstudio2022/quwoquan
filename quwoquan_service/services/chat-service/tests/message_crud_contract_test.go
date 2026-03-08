package tests

import (
	"fmt"
	"testing"
)

func TestSendMessageSeqAssignment(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"seq test"}`)
	convId := conv["_id"].(string)

	msg1 := sendMessage(t, convId, `{"type":"text","content":"hello","clientMsgId":"uuid-1"}`)
	msg2 := sendMessage(t, convId, `{"type":"text","content":"world","clientMsgId":"uuid-2"}`)

	seq1 := int64(msg1["seq"].(float64))
	seq2 := int64(msg2["seq"].(float64))

	if seq2 <= seq1 {
		t.Errorf("seq should be monotonically increasing: seq1=%d, seq2=%d", seq1, seq2)
	}

	if msg1["messageId"] == nil {
		t.Error("response missing messageId")
	}
	if msg1["timestamp"] == nil {
		t.Error("response missing timestamp")
	}
}

func TestSendMessageClientMsgIdDedup(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"dedup test"}`)
	convId := conv["_id"].(string)

	msg1 := sendMessage(t, convId, `{"type":"text","content":"hello","clientMsgId":"dedup-uuid-1"}`)
	msg2 := sendMessage(t, convId, `{"type":"text","content":"hello again","clientMsgId":"dedup-uuid-1"}`)

	if msg1["messageId"] != msg2["messageId"] {
		t.Errorf("dedup failed: different messageId returned for same clientMsgId: %v vs %v",
			msg1["messageId"], msg2["messageId"])
	}

	seq1 := int64(msg1["seq"].(float64))
	seq2 := int64(msg2["seq"].(float64))
	if seq1 != seq2 {
		t.Errorf("dedup failed: different seq returned: %d vs %d", seq1, seq2)
	}
}

func TestListMessages(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"list test"}`)
	convId := conv["_id"].(string)

	for i := 0; i < 5; i++ {
		sendMessage(t, convId, fmt.Sprintf(`{"type":"text","content":"msg %d","clientMsgId":"list-uuid-%d"}`, i, i))
	}

	code, result := doGet(t, "/v1/chat/conversations/"+convId+"/messages?limit=10", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items array")
	}
	if len(items) != 5 {
		t.Errorf("expected 5 messages, got %d", len(items))
	}
}

func TestRecallMessageWithinTimeLimit(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"direct","title":"recall test"}`)
	convId := conv["_id"].(string)

	msg := sendMessage(t, convId, `{"type":"text","content":"to recall","clientMsgId":"recall-uuid-1"}`)
	msgId := msg["messageId"].(string)

	result := doPost(t, "/v1/chat/conversations/"+convId+"/messages/"+msgId+"/recall",
		`{}`, "user_test_001", 200)

	if result["status"] != "recalled" {
		t.Errorf("expected status=recalled, got %v", result["status"])
	}
}
