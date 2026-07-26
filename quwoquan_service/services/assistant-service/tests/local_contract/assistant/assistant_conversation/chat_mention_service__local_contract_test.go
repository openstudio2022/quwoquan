// spec_ref: specs/feature-tree/runtime/runtime-assistant/assistant-mentioned-consumer/spec.md#gwt-001
package local_contract

import (
	"context"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/persistence"
)

type migratedChatMentionServiceFakeChatGroundingClient struct {
	listMessagesCalled bool
	membershipChecked  bool
	membershipDenied   bool
	sent               []ChatGroundingSendMessageRequest
}

func (f *migratedChatMentionServiceFakeChatGroundingClient) ListMessages(
	_ context.Context,
	conversationID string,
	creatorPersonaID string,
	assistantSkillID string,
	beforeSeq int64,
	limit int,
) ([]ChatGroundingMessage, error) {
	f.listMessagesCalled = conversationID == "conv-1" &&
		creatorPersonaID == "user-a" &&
		assistantSkillID == "general" &&
		beforeSeq == 12 &&
		limit == 20
	return []ChatGroundingMessage{
		{MessageID: "msg-10", Seq: 10, SenderID: "user-a", SenderName: "小明", Content: "周末去川西怎么样？"},
		{MessageID: "msg-11", Seq: 11, SenderID: "user-b", SenderName: "小红", Content: "我想知道自驾路线和住宿。"},
	}, nil
}

func (f *migratedChatMentionServiceFakeChatGroundingClient) ResolveAssistantDeliveryMembership(
	_ context.Context,
	conversationID string,
	creatorPersonaID string,
	assistantMemberID string,
	assistantSkillID string,
) (bool, error) {
	f.membershipChecked = conversationID == "conv-1" &&
		creatorPersonaID == "user-a" &&
		assistantMemberID == "assistant" &&
		assistantSkillID == "general"
	return !f.membershipDenied, nil
}

func (f *migratedChatMentionServiceFakeChatGroundingClient) SendMessage(_ context.Context, req ChatGroundingSendMessageRequest) error {
	f.sent = append(f.sent, req)
	return nil
}

func TestHandleAssistantMentionedReadsConversationContextAndReplies(t *testing.T) {
	chat := &migratedChatMentionServiceFakeChatGroundingClient{}
	service := NewAssistantService(
		persistence.NewMemoryConsentStore(),
		nil,
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		WithAgentLoop(NewAgentLoop(
			proactiveSkillRuntime{},
			ReactRuntime{Model: proactiveFinalModel{}},
			nil,
		)),
		WithChatGroundingClient(chat),
		testFrozenPolicyOption(),
	)

	err := service.HandleAssistantMentioned(context.Background(), AssistantMentionedEvent{
		ConversationID:    "conv-1",
		MessageID:         "msg-12",
		Seq:               12,
		SenderID:          "user-a",
		Content:           "@小趣 总结一下",
		AssistantMemberID: "assistant",
		AssistantSkillID:  "general",
	})
	if err != nil {
		t.Fatalf("HandleAssistantMentioned returned error: %v", err)
	}
	if !chat.listMessagesCalled {
		t.Fatal("expected ListMessages to be called with trigger seq window")
	}
	if !chat.membershipChecked {
		t.Fatal("expected exact creator and assistant membership check")
	}
	if len(chat.sent) != 1 {
		t.Fatalf("expected one reply, got %d", len(chat.sent))
	}
	reply := chat.sent[0]
	if reply.ConversationID != "conv-1" {
		t.Fatalf("reply conversation=%s, want conv-1", reply.ConversationID)
	}
	if reply.CreatorPersonaID != "user-a" ||
		reply.AssistantSkillID != "general" {
		t.Fatalf("reply authorization coordinates drifted: %+v", reply)
	}
	if strings.TrimSpace(reply.Content) == "" {
		t.Fatal("expected non-empty assistant reply")
	}
	if !strings.HasPrefix(reply.ClientMsgID, "assistant-") {
		t.Fatalf("reply clientMsgId=%s, want assistant-*", reply.ClientMsgID)
	}
}

func TestHandleAssistantMentionedDropsEventWhenAssistantWasRemoved(t *testing.T) {
	chat := &migratedChatMentionServiceFakeChatGroundingClient{
		membershipDenied: true,
	}
	service := NewAssistantService(
		persistence.NewMemoryConsentStore(),
		nil,
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		WithAgentLoop(NewAgentLoop(
			proactiveSkillRuntime{},
			ReactRuntime{Model: proactiveFinalModel{}},
			nil,
		)),
		WithChatGroundingClient(chat),
		testFrozenPolicyOption(),
	)

	err := service.HandleAssistantMentioned(context.Background(), AssistantMentionedEvent{
		ConversationID:    "conv-1",
		MessageID:         "msg-12",
		Seq:               12,
		SenderID:          "user-a",
		Content:           "@小趣 总结一下",
		AssistantMemberID: "assistant",
		AssistantSkillID:  "general",
	})
	if err != nil {
		t.Fatalf("removed assistant event must be ack-and-drop, got error: %v", err)
	}
	if !chat.membershipChecked {
		t.Fatal("expected membership to be checked before processing")
	}
	if chat.listMessagesCalled {
		t.Fatal("removed assistant event must not load the conversation window")
	}
	if len(chat.sent) != 0 {
		t.Fatalf("removed assistant event sent %d replies, want 0", len(chat.sent))
	}
}
