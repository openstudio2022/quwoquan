// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/assistant-in-conversation/spec.md#gwt-001
package api_integration

import (
	"context"
	"net/http"
	"testing"
	"time"

	mqpkg "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/mq"
)

func TestAssistantMentionedWritesReliableStream(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	ctx := context.Background()
	if err := redisRouter.Scene("general").XGroupCreateMkStream(ctx, mqpkg.AssistantMentionedStream, "test-consumer", "0"); err != nil {
		t.Fatalf("create stream group: %v", err)
	}
	conv := createConversation(t, `{"type":"group","title":"assistant stream"}`)
	convId := conv["id"].(string)
	doPost(t, "/chat/conversations/"+convId+"/assistant", `{"skillId":"general"}`, "user_test_001", http.StatusOK)

	sendMessage(t, convId, `{"type":"text","content":"@小趣 帮忙总结","mentions":["assistant"],"clientMsgId":"stream-assistant-mentioned-1"}`)

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		messages, err := redisRouter.Scene("general").XReadGroup(
			ctx,
			"test-consumer",
			"worker-1",
			map[string]string{mqpkg.AssistantMentionedStream: ">"},
			1,
			50*time.Millisecond,
		)
		if err != nil {
			t.Fatalf("read stream: %v", err)
		}
		if len(messages) == 0 {
			continue
		}
		values := messages[0].Values
		if values["conversationId"] != convId {
			t.Fatalf("conversationId=%s, want %s", values["conversationId"], convId)
		}
		if values["assistantMemberId"] != "assistant" {
			t.Fatalf("assistantMemberId=%s, want assistant", values["assistantMemberId"])
		}
		if values["assistantSkillId"] != "general" {
			t.Fatalf("assistantSkillId=%s, want general", values["assistantSkillId"])
		}
		if values["content"] != "@小趣 帮忙总结" {
			t.Fatalf("content=%s", values["content"])
		}
		if err := redisRouter.Scene("general").XAck(
			ctx,
			mqpkg.AssistantMentionedStream,
			"test-consumer",
			messages[0].ID,
		); err != nil {
			t.Fatalf("ack stream: %v", err)
		}
		reclaimed, _, err := redisRouter.Scene("general").XAutoClaim(
			ctx,
			mqpkg.AssistantMentionedStream,
			"test-consumer",
			"recovery-worker",
			0,
			"0-0",
			1,
		)
		if err != nil {
			t.Fatalf("claim acknowledged stream: %v", err)
		}
		if len(reclaimed) != 0 {
			t.Fatalf("acknowledged stream message must not remain pending: %+v", reclaimed)
		}
		return
	}
	t.Fatal("assistant mentioned stream event not received")
}

func TestAssistantGeneratedMessageDoesNotWriteMentionStream(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	ctx := context.Background()
	if err := redisRouter.Scene("general").XGroupCreateMkStream(ctx, mqpkg.AssistantMentionedStream, "test-consumer", "0"); err != nil {
		t.Fatalf("create stream group: %v", err)
	}
	conv := createConversation(t, `{"type":"group","title":"assistant loop guard"}`)
	convId := conv["id"].(string)
	doPost(t, "/chat/conversations/"+convId+"/assistant", `{"skillId":"general"}`, "user_test_001", http.StatusOK)

	sendMessageAs(t, "assistant", convId, `{"type":"text","content":"我是小趣回复","mentions":["assistant"],"clientMsgId":"assistant-loop-1"}`)

	messages, err := redisRouter.Scene("general").XReadGroup(
		ctx,
		"test-consumer",
		"worker-1",
		map[string]string{mqpkg.AssistantMentionedStream: ">"},
		1,
		100*time.Millisecond,
	)
	if err != nil {
		t.Fatalf("read stream: %v", err)
	}
	if len(messages) != 0 {
		t.Fatalf("assistant generated message should not trigger stream, got %d", len(messages))
	}
}

func TestRemovedAssistantDoesNotWriteMentionStream(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	ctx := context.Background()
	if err := redisRouter.Scene("general").XGroupCreateMkStream(ctx, mqpkg.AssistantMentionedStream, "test-consumer", "0"); err != nil {
		t.Fatalf("create stream group: %v", err)
	}
	conv := createConversation(t, `{"type":"group","title":"assistant removed guard"}`)
	convID := conv["id"].(string)
	doPost(t, "/chat/conversations/"+convID+"/assistant", `{"skillId":"general"}`, "user_test_001", http.StatusOK)
	doDelete(t, "/chat/conversations/"+convID+"/assistant", "user_test_001")

	rejected := doPost(
		t,
		"/chat/conversations/"+convID+"/messages",
		`{"type":"text","content":"@小趣 还在吗","mentions":["assistant"],"clientMsgId":"assistant-removed-mention-1"}`,
		"user_test_001",
		http.StatusBadRequest,
	)
	if rejected["code"] != "CHAT.USER.message_invalid" {
		t.Fatalf("removed assistant mention must be rejected: %#v", rejected)
	}
	messages, err := redisRouter.Scene("general").XReadGroup(
		ctx,
		"test-consumer",
		"worker-1",
		map[string]string{mqpkg.AssistantMentionedStream: ">"},
		1,
		100*time.Millisecond,
	)
	if err != nil {
		t.Fatalf("read stream: %v", err)
	}
	if len(messages) != 0 {
		t.Fatalf("removed assistant mention must not reach stream: %+v", messages)
	}
}
