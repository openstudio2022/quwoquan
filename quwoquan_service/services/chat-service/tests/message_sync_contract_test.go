package tests

import (
	"fmt"
	"testing"
)

func TestSyncMessagesGapFill(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"sync test"}`)
	convId := conv["_id"].(string)

	for i := 0; i < 10; i++ {
		sendMessage(t, convId, fmt.Sprintf(`{"type":"text","content":"sync msg %d","clientMsgId":"sync-uuid-%d"}`, i, i))
	}

	result := doPost(t, "/v1/chat/conversations/"+convId+"/sync",
		`{"lastSeq":5,"limit":100}`, "user_test_001", 200)

	msgs, ok := result["messages"].([]any)
	if !ok {
		t.Fatal("response missing messages array")
	}

	if len(msgs) < 5 {
		t.Errorf("expected >=5 messages after seq 5, got %d", len(msgs))
	}

	hasMore, _ := result["hasMore"].(bool)
	if hasMore {
		t.Error("expected hasMore=false for small dataset")
	}
}

func TestSyncMessagesFromZero(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"sync zero test"}`)
	convId := conv["_id"].(string)

	for i := 0; i < 3; i++ {
		sendMessage(t, convId, fmt.Sprintf(`{"type":"text","content":"msg %d","clientMsgId":"sync0-uuid-%d"}`, i, i))
	}

	result := doPost(t, "/v1/chat/conversations/"+convId+"/sync",
		`{"lastSeq":0,"limit":500}`, "user_test_001", 200)

	msgs, ok := result["messages"].([]any)
	if !ok {
		t.Fatal("response missing messages array")
	}
	if len(msgs) != 3 {
		t.Errorf("expected 3 messages from seq 0, got %d", len(msgs))
	}
}
