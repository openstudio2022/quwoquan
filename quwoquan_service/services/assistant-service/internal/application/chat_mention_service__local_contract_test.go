package application

import (
	"context"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

type fakeChatGroundingClient struct {
	listMessagesCalled bool
	listMembersCalled  bool
	sent               []ChatGroundingSendMessageRequest
}

func (f *fakeChatGroundingClient) ListMessages(_ context.Context, conversationID string, beforeSeq int64, limit int) ([]ChatGroundingMessage, error) {
	f.listMessagesCalled = conversationID == "conv-1" && beforeSeq == 12 && limit == 20
	return []ChatGroundingMessage{
		{MessageID: "msg-10", Seq: 10, SenderID: "user-a", SenderName: "小明", Content: "周末去川西怎么样？"},
		{MessageID: "msg-11", Seq: 11, SenderID: "user-b", SenderName: "小红", Content: "我想知道自驾路线和住宿。"},
	}, nil
}

func (f *fakeChatGroundingClient) ListMembers(_ context.Context, conversationID string, limit int) ([]ChatGroundingMember, error) {
	f.listMembersCalled = conversationID == "conv-1" && limit == 100
	return []ChatGroundingMember{
		{UserID: "user-a", DisplayName: "小明", MemberType: "user"},
		{UserID: "assistant", DisplayName: "小趣", MemberType: "assistant", AssistantSkillID: "general"},
	}, nil
}

func (f *fakeChatGroundingClient) SendMessage(_ context.Context, req ChatGroundingSendMessageRequest) error {
	f.sent = append(f.sent, req)
	return nil
}

func TestHandleAssistantMentionedReadsConversationContextAndReplies(t *testing.T) {
	chat := &fakeChatGroundingClient{}
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		nil,
		WithChatGroundingClient(chat),
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
	if !chat.listMembersCalled {
		t.Fatal("expected ListMembers to be called")
	}
	if len(chat.sent) != 1 {
		t.Fatalf("expected one reply, got %d", len(chat.sent))
	}
	reply := chat.sent[0]
	if reply.ConversationID != "conv-1" {
		t.Fatalf("reply conversation=%s, want conv-1", reply.ConversationID)
	}
	if reply.SenderID != "assistant" {
		t.Fatalf("reply sender=%s, want assistant", reply.SenderID)
	}
	if strings.TrimSpace(reply.Content) == "" {
		t.Fatal("expected non-empty assistant reply")
	}
	if !strings.HasPrefix(reply.ClientMsgID, "assistant-") {
		t.Fatalf("reply clientMsgId=%s, want assistant-*", reply.ClientMsgID)
	}
}
